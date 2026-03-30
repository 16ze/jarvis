"""
Ada Memory Manager
Gère 4 types de mémoire :
  - Vectorielle   : conversations passées (ChromaDB)
  - Entités       : personnes, projets, clients (ChromaDB)
  - Procédurale   : profil de Bryan (JSON)
  - Documents RAG : fichiers uploadés, chunked + indexés (ChromaDB)
"""

import json
import chromadb
from datetime import datetime
from pathlib import Path

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

        # Mémoire procédurale — fichier JSON
        self.procedural_path = MEMORY_DIR / "procedural.json"
        if not self.procedural_path.exists():
            self._write_procedural({
                "preferences": [],
                "habits": [],
                "goals": [],
                "facts": []
            })

    # ─── HELPERS ────────────────────────────────────────────────────────────

    def _write_procedural(self, data: dict):
        self.procedural_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _read_procedural(self) -> dict:
        return json.loads(self.procedural_path.read_text(encoding="utf-8"))

    # ─── CONVERSATIONS ───────────────────────────────────────────────────────

    def save_conversation(self, content: str, metadata: dict | None = None):
        """Sauvegarde un échange ou une info importante dans la mémoire vectorielle."""
        if not content.strip():
            return
        doc_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        meta = {"timestamp": datetime.now().isoformat(), "type": "conversation"}
        if metadata:
            meta.update(metadata)
        try:
            self.conversations.add(documents=[content], metadatas=[meta], ids=[doc_id])
        except Exception as e:
            print(f"[MEMORY] save_conversation error: {e}")

    def search_memory(self, query: str, n_results: int = 5) -> list[dict]:
        """Recherche sémantique dans les conversations passées."""
        try:
            count = self.conversations.count()
            if count == 0:
                return []
            results = self.conversations.query(
                query_texts=[query],
                n_results=min(n_results, count)
            )
            return [
                {"content": doc, "timestamp": meta.get("timestamp", "")[:16]}
                for doc, meta in zip(results["documents"][0], results["metadatas"][0])
            ]
        except Exception as e:
            print(f"[MEMORY] search_memory error: {e}")
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
        data = self._read_procedural()
        if category not in data:
            data[category] = []
        if item not in data[category]:
            data[category].append(item)
            self._write_procedural(data)

    def get_procedural(self) -> dict:
        return self._read_procedural()

    # ─── DERNIÈRE SESSION ────────────────────────────────────────────────────

    def append_to_session(self, text: str):
        """Ajoute un échange au fichier de la dernière session (ring buffer de 30 entrées)."""
        if not text.strip():
            return
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
