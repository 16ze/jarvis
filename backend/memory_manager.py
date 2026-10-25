"""
Ada Memory Manager
Gère 4 types de mémoire :
  - Vectorielle   : conversations passées (ChromaDB)
  - Entités       : personnes, projets, clients (ChromaDB)
  - Procédurale   : profil de Bryan (JSON)
  - Documents RAG : fichiers uploadés, chunked + indexés (ChromaDB)
"""

import json
import re
import chromadb
from datetime import datetime
from pathlib import Path

import emotional_memory

MEMORY_DIR = Path(__file__).parent / "memory"
DOCUMENTS_DIR = MEMORY_DIR / "documents"  # Fichiers originaux conservés


class MemoryManager:
    def __init__(self):
        MEMORY_DIR.mkdir(exist_ok=True)
        DOCUMENTS_DIR.mkdir(exist_ok=True)

        self.client = chromadb.PersistentClient(path=str(MEMORY_DIR / "chroma"))

        self.conversations = self.client.get_or_create_collection("conversations")
        self.entities = self.client.get_or_create_collection("entities")
        self.documents = self.client.get_or_create_collection("documents")

        # Collection pour la couche vision objet (YOLO)
        # Tolère un échec d'init : la couche vision sait fonctionner sans Chroma.
        try:
            self.vision_collection = self.client.get_or_create_collection("vision_objects")
        except Exception as exc:
            print(f"[MEMORY] vision_objects collection init failed: {exc}")
            self.vision_collection = None

        # Mémoire procédurale — fichier JSON
        self.procedural_path = MEMORY_DIR / "procedural.json"
        if not self.procedural_path.exists():
            self._write_procedural({
                "preferences": [],
                "habits": [],
                "goals": [],
                "facts": []
            })

        # Dé-duplication : dernier contenu de conversation enregistré
        # (évite les doublons consécutifs / boucles).
        self._last_conv_content = None

    # ─── HELPERS ────────────────────────────────────────────────────────────

    def _write_procedural(self, data: dict):
        self.procedural_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _read_procedural(self) -> dict:
        return json.loads(self.procedural_path.read_text(encoding="utf-8"))

    # ─── CONVERSATIONS ───────────────────────────────────────────────────────

    def save_conversation(
        self,
        content: str,
        metadata: dict | None = None,
        emotional_state: dict | None = None,
    ):
        """Sauvegarde un échange dans la mémoire vectorielle.

        `emotional_state` (snapshot du brain) marque le souvenir de sa charge
        affective : c'est ce qui décidera plus tard de sa saillance au rappel
        (consolidation émotionnelle — cf. backend/emotional_memory.py).
        """
        if not content.strip():
            return
        # Dé-duplication : ignorer un contenu identique au précédent.
        norm_content = content.strip()
        if norm_content == self._last_conv_content:
            return
        self._last_conv_content = norm_content
        doc_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        meta = {"timestamp": datetime.now().isoformat(), "type": "conversation"}
        if emotional_state:
            meta.update(emotional_memory.encode_metadata(emotional_state))
        if metadata:
            meta.update(metadata)
        try:
            self.conversations.add(documents=[content], metadatas=[meta], ids=[doc_id])
        except Exception as e:
            print(f"[MEMORY] save_conversation error: {e}")

    def search_memory(
        self,
        query: str,
        n_results: int = 5,
        emotional_state: dict | None = None,
    ) -> list[dict]:
        """Recherche dans les conversations passées.

        Avec `emotional_state`, le rappel devient congruent à l'humeur : à
        requête égale, Ada ne remonte pas tout à fait les mêmes souvenirs selon
        son état — les souvenirs marquants et affectivement proches ressortent.
        Sans état fourni, le comportement reste purement sémantique.
        """
        try:
            count = self.conversations.count()
            if count == 0:
                return []

            # On élargit le filet quand un état affectif doit reclasser.
            fetch = min(count, n_results * 3 if emotional_state else n_results)
            results = self.conversations.query(
                query_texts=[query],
                n_results=fetch,
                include=["documents", "metadatas", "distances"],
            )
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            dists = (results.get("distances") or [[]])[0]

            ranked = emotional_memory.rerank(
                docs, metas, dists, emotional_state, n_results
            )
            return [
                {
                    "content": item["content"],
                    "timestamp": (item["metadata"] or {}).get("timestamp", "")[:16],
                }
                for item in ranked
            ]
        except Exception as e:
            print(f"[MEMORY] search_memory error: {e}")
            return []

    def recent_conversations(self, n: int = 6) -> list[str]:
        """Les n échanges les plus récents, du plus ancien au plus récent.

        Rejeu temporel (et non sémantique) : c'est la matière première de la
        consolidation au repos — cf. backend/idle_mind.py.
        """
        try:
            count = self.conversations.count()
            if count == 0:
                return []
            # Chroma ne trie pas : on récupère un lot puis on trie par timestamp.
            batch = self.conversations.get(
                limit=min(count, max(n * 10, 50)),
                include=["documents", "metadatas"],
            )
            docs = batch.get("documents") or []
            metas = batch.get("metadatas") or []
            paired = [
                ((meta or {}).get("timestamp", ""), doc)
                for doc, meta in zip(docs, metas)
                if doc
            ]
            paired.sort(key=lambda item: item[0])
            return [doc for _, doc in paired[-n:]]
        except Exception as e:
            print(f"[MEMORY] recent_conversations error: {e}")
            return []

    # ─── ENTITÉS ────────────────────────────────────────────────────────────

    def update_entity(self, name: str, info: str):
        """Crée ou met à jour une entité (personne, client, projet)."""
        entity_id = f"entity_{name.lower().replace(' ', '_')}"
        try:
            existing = self.entities.get(ids=[entity_id])
            if existing["documents"]:
                self.entities.delete(ids=[entity_id])
        except Exception:
            pass
        try:
            self.entities.add(
                documents=[info],
                metadatas=[{"name": name, "updated": datetime.now().isoformat()}],
                ids=[entity_id]
            )
        except Exception as e:
            print(f"[MEMORY] update_entity error: {e}")

    def get_entity(self, name: str) -> str | None:
        """Récupère les infos d'une entité par son nom exact."""
        entity_id = f"entity_{name.lower().replace(' ', '_')}"
        try:
            result = self.entities.get(ids=[entity_id])
            if result["documents"]:
                return result["documents"][0]
        except Exception:
            pass
        return None

    def search_entities(self, query: str, n: int = 3) -> list[dict]:
        """Recherche sémantique dans les entités."""
        try:
            count = self.entities.count()
            if count == 0:
                return []
            results = self.entities.query(
                query_texts=[query],
                n_results=min(n, count)
            )
            return [
                {"name": meta["name"], "info": doc}
                for doc, meta in zip(results["documents"][0], results["metadatas"][0])
            ]
        except Exception as e:
            print(f"[MEMORY] search_entities error: {e}")
            return []

    # ─── MÉMOIRE PROCÉDURALE ─────────────────────────────────────────────────

    def add_procedural(self, category: str, item: str):
        """Ajoute un fait au profil de Bryan. Catégories: preferences | habits | goals | facts"""
        item = (item or "").strip()
        if not item:
            return
        data = self._read_procedural()
        if category not in data:
            data[category] = []
        norm = self._normalize(item)
        if all(self._normalize(x) != norm for x in data[category]):
            data[category].append(item)
            self._write_procedural(data)

    @staticmethod
    def _normalize(s: str) -> str:
        return re.sub(r"\s+", " ", (s or "").strip().lower())

    def dedupe_procedural(self) -> None:
        """Nettoie le profil : retire les doublons normalisés dans chaque catégorie."""
        try:
            data = self._read_procedural()
            changed = False
            for cat, items in list(data.items()):
                if not isinstance(items, list):
                    continue
                seen, cleaned = set(), []
                for it in items:
                    n = self._normalize(it)
                    if n and n not in seen:
                        seen.add(n)
                        cleaned.append(it)
                if len(cleaned) != len(items):
                    data[cat] = cleaned
                    changed = True
            if changed:
                self._write_procedural(data)
        except Exception as e:
            print(f"[MEMORY] dedupe_procedural error: {e}")

    # Déclencheurs explicites de mémorisation — phrases de Bryan UNIQUEMENT.
    # Prudent par conception : on ne mémorise que sur intention claire, pour ne
    # jamais stocker une info inventée ou une erreur.
    _AUTO_RULES = [
        (re.compile(r"\b(?:retiens|souviens[- ]toi|note)\s+(?:bien\s+)?(?:que\s+|:\s*)?(.+)", re.I), "facts"),
        (re.compile(r"\bn['e ]oublie\s+pas\s+(?:que\s+|:\s*)?(.+)", re.I), "facts"),
        (re.compile(r"\bje\s+pr[ée]f[èe]re\s+(.+)", re.I), "preferences"),
        (re.compile(r"\bje\s+d[ée]teste\s+(.+)", re.I), "preferences"),
        (re.compile(r"\bj['e ]habite\s+(?:à|a|au|en)\s+(.+)", re.I), "facts"),
        (re.compile(r"\bje\s+travaille\s+(?:chez|à|a|au|en|pour)\s+(.+)", re.I), "facts"),
        (re.compile(r"\bmon\s+objectif\s+(?:est\s+|:\s*)?(.+)", re.I), "goals"),
        (re.compile(r"\bmon\s+anniversaire\s+(?:est\s+|:\s*|c['e]st\s+)?(.+)", re.I), "facts"),
    ]

    def auto_remember(self, text: str) -> None:
        """Mémorisation automatique PRUDENTE : n'extrait des faits durables que
        des phrases de Bryan (jamais d'Ada) et seulement sur déclencheur
        explicite — ne jamais enregistrer une info inventée ou une erreur."""
        if not text or not text.strip():
            return
        # Format attendu : "<émetteur>: <texte>" (cf. append_to_session).
        prefix, sep, body = text.partition(":")
        if not sep or not prefix.strip().lower().startswith("bryan"):
            return  # on ignore les tours d'Ada et tout ce qui n'est pas de Bryan
        body = body.strip()
        if not body:
            return
        for rx, cat in self._AUTO_RULES:
            m = rx.search(body)
            if m:
                fait = m.group(1).strip().rstrip(" .!?,;")
                if 2 <= len(fait) <= 160:
                    self.add_procedural(cat, fait)
                break

    def get_procedural(self) -> dict:
        return self._read_procedural()

    # ─── DERNIÈRE SESSION ────────────────────────────────────────────────────

    def append_to_session(self, text: str):
        """Ajoute un échange au fichier de la dernière session (ring buffer de 30 entrées)."""
        if not text.strip():
            return
        # Mémorisation automatique prudente (faits durables énoncés par Bryan).
        try:
            self.auto_remember(text)
        except Exception as e:
            print(f"[MEMORY] auto_remember error: {e}")
        path = MEMORY_DIR / "last_session.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            data.append({"ts": datetime.now().isoformat(), "text": text})
            # Garder les 30 derniers échanges
            if len(data) > 30:
                data = data[-30:]
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"[MEMORY] append_to_session error: {e}")

    def get_last_session(self) -> list[dict]:
        """Retourne les échanges de la dernière session."""
        path = MEMORY_DIR / "last_session.json"
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return []

    def clear_session(self):
        """Efface le fichier de session courante (appeler en début de nouvelle session)."""
        path = MEMORY_DIR / "last_session.json"
        try:
            if path.exists():
                # Archiver dans ChromaDB avant d'effacer
                data = json.loads(path.read_text(encoding="utf-8"))
                for entry in data:
                    self.save_conversation(entry["text"], {"source": "session_archive"})
                path.unlink()
        except Exception as e:
            print(f"[MEMORY] clear_session error: {e}")

    # ─── CONTEXTE AU DÉMARRAGE ───────────────────────────────────────────────

    def get_startup_context(self) -> str:
        """Génère le bloc de contexte à injecter au démarrage de la session."""
        self.dedupe_procedural()  # nettoyage des doublons du profil à chaque démarrage
        lines = []

        # Profil Bryan
        proc = self._read_procedural()
        has_proc = any(v for v in proc.values())
        if has_proc:
            lines.append("=== CE QUE TU SAIS SUR BRYAN ===")
            for cat, items in proc.items():
                if items:
                    lines.append(f"• {cat.upper()}: {', '.join(items)}")

        # Entités connues
        try:
            count = self.entities.count()
            if count > 0:
                all_entities = self.entities.get(include=["documents", "metadatas"])
                if all_entities["documents"]:
                    lines.append("\n=== PERSONNES & PROJETS CONNUS ===")
                    for doc, meta in zip(all_entities["documents"], all_entities["metadatas"]):
                        lines.append(f"• {meta['name']}: {doc[:150]}")
        except Exception:
            pass

        # Dernière session (échanges récents — triés chronologiquement)
        last = self.get_last_session()
        if last:
            lines.append("\n=== DERNIÈRE SESSION (ce dont vous parliez avant le redémarrage) ===")
            for entry in last[-15:]:  # 15 derniers échanges
                ts = entry.get("ts", "")[:16]
                lines.append(f"[{ts}] {entry['text'][:250]}")

        # Conversations passées triées par timestamp (ChromaDB)
        try:
            count = self.conversations.count()
            if count > 0:
                all_convs = self.conversations.get(include=["documents", "metadatas"])
                pairs = sorted(
                    zip(all_convs["documents"], all_convs["metadatas"]),
                    key=lambda x: x[1].get("timestamp", ""),
                    reverse=True
                )[:5]
                if pairs:
                    lines.append("\n=== MÉMOIRE LONG TERME (conversations archivées) ===")
                    for doc, meta in pairs:
                        ts = meta.get("timestamp", "")[:16]
                        lines.append(f"[{ts}] {doc[:200]}")
        except Exception:
            pass

        # Documents disponibles
        docs = self.list_documents()
        if docs:
            lines.append("\n=== DOCUMENTS DISPONIBLES (utilise search_documents pour les consulter) ===")
            for d in docs:
                lines.append(f"• {d['filename']} ({d['chunks']} chunks, ajouté le {d['added'][:10]})")

        if not lines:
            return ""

        return (
            "[MÉMOIRE — contexte chargé automatiquement]\n"
            + "\n".join(lines)
            + "\n[FIN MÉMOIRE]\n"
        )

    # ─── DOCUMENTS RAG ───────────────────────────────────────────────────────

    def _chunk_text(self, text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
        """Découpe le texte en chunks avec chevauchement."""
        words = text.split()
        if not words:
            return []
        chunks = []
        i = 0
        while i < len(words):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk)
            i += chunk_size - overlap
        return chunks

    def ingest_document(self, filename: str, text: str) -> int:
        """Chunk, embed et indexe un document. Retourne le nombre de chunks."""
        if not text.strip():
            return 0

        # Supprimer les anciens chunks de ce fichier
        self.delete_document(filename)

        chunks = self._chunk_text(text)
        added = datetime.now().isoformat()

        for i, chunk in enumerate(chunks):
            chunk_id = f"doc_{filename}_{i}"
            try:
                self.documents.add(
                    documents=[chunk],
                    metadatas=[{
                        "filename": filename,
                        "chunk": i,
                        "total_chunks": len(chunks),
                        "added": added,
                    }],
                    ids=[chunk_id]
                )
            except Exception as e:
                print(f"[MEMORY] ingest chunk {i} error: {e}")

        # Sauvegarder le fichier original
        original_path = DOCUMENTS_DIR / filename
        # (le contenu binaire est sauvegardé par server.py)

        print(f"[MEMORY] Ingested '{filename}': {len(chunks)} chunks")
        return len(chunks)

    def search_documents(self, query: str, n: int = 5) -> list[dict]:
        """Recherche sémantique dans les documents uploadés."""
        try:
            count = self.documents.count()
            if count == 0:
                return []
            results = self.documents.query(
                query_texts=[query],
                n_results=min(n, count)
            )
            return [
                {
                    "filename": meta["filename"],
                    "content": doc,
                    "chunk": meta["chunk"],
                    "total_chunks": meta.get("total_chunks", "?"),
                }
                for doc, meta in zip(results["documents"][0], results["metadatas"][0])
            ]
        except Exception as e:
            print(f"[MEMORY] search_documents error: {e}")
            return []

    def list_documents(self) -> list[dict]:
        """Liste les documents ingérés avec métadonnées."""
        try:
            count = self.documents.count()
            if count == 0:
                return []
            all_chunks = self.documents.get(include=["metadatas"])
            seen = {}
            for meta in all_chunks["metadatas"]:
                fn = meta["filename"]
                if fn not in seen:
                    seen[fn] = {
                        "filename": fn,
                        "chunks": meta.get("total_chunks", "?"),
                        "added": meta.get("added", ""),
                    }
            return sorted(seen.values(), key=lambda x: x["added"], reverse=True)
        except Exception as e:
            print(f"[MEMORY] list_documents error: {e}")
            return []

    def delete_document(self, filename: str):
        """Supprime tous les chunks d'un document."""
        try:
            count = self.documents.count()
            if count == 0:
                return
            all_chunks = self.documents.get(include=["metadatas"])
            ids_to_delete = [
                id_ for id_, meta in zip(all_chunks["ids"], all_chunks["metadatas"])
                if meta["filename"] == filename
            ]
            if ids_to_delete:
                self.documents.delete(ids=ids_to_delete)
                print(f"[MEMORY] Deleted {len(ids_to_delete)} chunks for '{filename}'")
        except Exception as e:
            print(f"[MEMORY] delete_document error: {e}")
