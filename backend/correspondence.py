"""
correspondence — Ada traite ta correspondance, mais n'envoie jamais seule.

C'est le cas d'usage central : « réponds à mes mails », « réponds à mes messages
Instagram ». Le cycle est toujours le même, quel que soit le canal :

    1. LIRE      les messages en attente
    2. RÉDIGER   une réponse pour chacun, dans la voix de Bryan
    3. SOUMETTRE l'ensemble à sa validation
    4. ENVOYER   uniquement ceux qu'il approuve, un par un ou en bloc

RÈGLE ABSOLUE : rien ne part sans un accord explicite. Pas de « je pense qu'il
aurait voulu », pas d'envoi optimiste. Un message envoyé ne se rattrape pas, et
c'est sa parole qui est engagée, pas celle d'Ada.

Les brouillons vivent en mémoire jusqu'à validation. Un redémarrage les perd —
c'est volontaire : mieux vaut refaire une lecture que réveiller un brouillon
dont on ne se souvient plus.
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

import models

MAX_MESSAGES = int(os.getenv("CORRESPONDENCE_MAX", "8"))

_SYSTEM_REDACTION = """Tu rédiges des réponses à la place de Bryan, dans SA voix.

Ce ne sont pas tes messages : ce sont les siens. Écris donc comme lui, à la
première personne, en français naturel.

Règles :
- adapte le registre à l'expéditeur (client, ami, administration, inconnu) ;
- réponds réellement à ce qui est demandé, sans remplissage ;
- bref : deux à cinq phrases sauf si le sujet exige plus ;
- pas de formule pompeuse (« Je me permets de revenir vers vous »), pas de
  markdown, pas de signature (elle sera ajoutée automatiquement) ;
- si le message demande une information que tu n'as pas (un prix, une date, une
  décision personnelle), NE L'INVENTE PAS : écris la réponse en laissant un
  marqueur explicite [À COMPLÉTER : quoi] à l'endroit exact.

Renseigne « confiance » (0 à 1) et, si une information te manque pour répondre
correctement, décris-la dans « manque ». Sinon laisse « manque » vide."""


@dataclass
class Message:
    """Un message entrant, quel que soit le canal."""
    id: str
    canal: str              # "mail" | "instagram"
    expediteur: str
    sujet: str = ""
    corps: str = ""
    recu_le: str = ""

    def resume(self) -> str:
        base = f"{self.expediteur}"
        if self.sujet:
            base += f" — {self.sujet}"
        extrait = re.sub(r"\s+", " ", self.corps).strip()[:120]
        return f"{base} : {extrait}" if extrait else base


@dataclass
class Draft:
    """Une réponse rédigée, en attente de validation."""
    message: Message
    texte: str
    confiance: float = 0.0
    manque: str = ""
    statut: str = "en_attente"   # en_attente | envoye | rejete | echec

    @property
    def incomplet(self) -> bool:
        return "[À COMPLÉTER" in self.texte or bool(self.manque)


class CorrespondenceAssistant:
    """Lit, rédige, soumet — et n'envoie que sur accord."""

    def __init__(self, google_agent=None, browser=None, client=None):
        self._google = google_agent
        self._browser = browser
        self._client = client
        self._brouillons: list[Draft] = []

    # ── Lecture ───────────────────────────────────────────────────────────────

    async def fetch_mail(self, limite: int = MAX_MESSAGES) -> list[Message]:
        """Mails non lus de la boîte de réception."""
        if self._google is None:
            return []
        try:
            brut = await asyncio.to_thread(
                self._google.read_emails, limite, "in:inbox is:unread"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[CORRESPONDANCE] lecture mail impossible : {exc}")
            return []
        return _parser_mails(brut, limite)

    async def fetch_instagram(self, limite: int = MAX_MESSAGES) -> list[Message]:
        """Messages Instagram, lus via le navigateur intégré."""
        if self._browser is None:
            return []
        try:
            await self._browser("navigate", url="https://www.instagram.com/direct/inbox/")
            await asyncio.sleep(3.0)
            contenu = await self._browser("read")
        except Exception as exc:  # noqa: BLE001
            print(f"[CORRESPONDANCE] lecture Instagram impossible : {exc}")
            return []
        if not contenu or "connexion" in contenu.lower() or "log in" in contenu.lower():
            return []
        return _parser_instagram(contenu, limite)

    # ── Rédaction ─────────────────────────────────────────────────────────────

    async def draft_all(self, messages: list[Message], contexte: str = "") -> list[Draft]:
        """Rédige une réponse par message. Les brouillons attendent validation."""
        self._brouillons = []
        for message in messages:
            texte, confiance, manque = await self._rediger(message, contexte)
            self._brouillons.append(
                Draft(message=message, texte=texte, confiance=confiance, manque=manque)
            )
        return self._brouillons

    async def _rediger(self, message: Message, contexte: str) -> tuple[str, float, str]:
        client = self._get_client()
        if client is None:
            return ("", 0.0, "moteur de rédaction indisponible")

        prompt = (
            f"Canal : {message.canal}\n"
            f"Expéditeur : {message.expediteur}\n"
            f"Sujet : {message.sujet or '(aucun)'}\n"
            f"Message reçu :\n{message.corps[:2000]}"
        )
        if contexte:
            prompt += f"\n\nContexte utile : {contexte}"

        try:
            import json

            from google.genai import types

            # Sortie structurée native : un texte de message contient des
            # retours à la ligne, qui invalident un JSON rédigé « à la main ».
            # On laisse donc le modèle produire du JSON garanti valide.
            reponse = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=models.get("reasoning"),
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=_SYSTEM_REDACTION,
                        temperature=0.6,
                        max_output_tokens=3000,
                        response_mime_type="application/json",
                        response_schema={
                            "type": "OBJECT",
                            "properties": {
                                "reponse": {"type": "STRING"},
                                "confiance": {"type": "NUMBER"},
                                "manque": {"type": "STRING"},
                            },
                            "required": ["reponse"],
                        },
                    ),
                ),
                timeout=40,
            )
            brut = (reponse.text or "").strip()
            try:
                data = json.loads(brut)
            except json.JSONDecodeError:
                # Repli : mieux vaut un brouillon brut qu'aucun brouillon.
                nettoye = re.sub(r"^```(?:json)?\s*|\s*```$", "", brut).strip()
                return (nettoye, 0.4, "format inattendu — relis attentivement")
            return (
                str(data.get("reponse", "")).strip(),
                float(data.get("confiance", 0.0) or 0.0),
                str(data.get("manque", "")).strip(),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[CORRESPONDANCE] rédaction échouée : {exc}")
            return ("", 0.0, f"rédaction impossible : {exc}")

    # ── Soumission à validation ───────────────────────────────────────────────

    def to_review(self) -> str:
        """Présentation des brouillons pour validation — c'est ce qu'Ada dit."""
        en_attente = [d for d in self._brouillons if d.statut == "en_attente"]
        if not en_attente:
            return "Aucun brouillon en attente."

        lignes = [f"J'ai préparé {len(en_attente)} réponse(s). Rien n'est envoyé :"]
        for i, d in enumerate(en_attente, start=1):
            lignes.append(f"\n{i}. À {d.message.expediteur}"
                          + (f" — {d.message.sujet}" if d.message.sujet else ""))
            recu = re.sub(r"\s+", " ", d.message.corps)[:100]
            lignes.append(f"   Reçu : {recu}")
            lignes.append(f"   Ma réponse : {d.texte[:300]}")
            if d.incomplet:
                lignes.append(f"   ⚠ Il me manque : {d.manque or 'une information à compléter'}")
        lignes.append("\nDis-moi lesquelles envoyer — « envoie tout », « envoie la 2 », "
                      "ou « laisse tomber ».")
        return "\n".join(lignes)

    @property
    def pending(self) -> list[Draft]:
        return [d for d in self._brouillons if d.statut == "en_attente"]

    # ── Envoi (uniquement après accord) ───────────────────────────────────────

    async def send(self, indices: list[int] | None = None) -> str:
        """Envoie les brouillons approuvés. `indices` en base 1 ; None = tous."""
        en_attente = self.pending
        if not en_attente:
            return "Aucun brouillon à envoyer."

        if indices is None:
            cibles = list(en_attente)
        else:
            cibles = [en_attente[i - 1] for i in indices
                      if 1 <= i <= len(en_attente)]
        if not cibles:
            return "Aucun brouillon ne correspond à ce que tu as indiqué."

        # Un brouillon incomplet ne part jamais : c'est la parole de Bryan.
        bloques = [d for d in cibles if d.incomplet]
        cibles = [d for d in cibles if not d.incomplet]

        envoyes, echecs = [], []
        for d in cibles:
            ok = await self._envoyer_un(d)
            d.statut = "envoye" if ok else "echec"
            (envoyes if ok else echecs).append(d.message.expediteur)

        parties = []
        if envoyes:
            parties.append(f"Envoyé à {', '.join(envoyes)}.")
        if echecs:
            parties.append(f"Échec pour {', '.join(echecs)}.")
        if bloques:
            noms = ", ".join(d.message.expediteur for d in bloques)
            parties.append(f"Pas envoyé à {noms} : il me manque une information.")
        return " ".join(parties)

    async def _envoyer_un(self, d: Draft) -> bool:
        try:
            if d.message.canal == "mail":
                if self._google is None:
                    return False
                sujet = d.message.sujet or "Réponse"
                if not sujet.lower().startswith("re"):
                    sujet = f"Re: {sujet}"
                await asyncio.to_thread(
                    self._google.send_email, d.message.expediteur, sujet, d.texte
                )
                return True
            if d.message.canal == "instagram":
                if self._browser is None:
                    return False
                await self._browser("fill", field="message", value=d.texte)
                resultat = await self._browser("submit")
                return "échec" not in str(resultat).lower()
        except Exception as exc:  # noqa: BLE001
            print(f"[CORRESPONDANCE] envoi échoué : {exc}")
        return False

    def discard(self) -> str:
        n = len(self.pending)
        for d in self._brouillons:
            if d.statut == "en_attente":
                d.statut = "rejete"
        return f"{n} brouillon(s) abandonné(s). Rien n'a été envoyé."

    # ── Utilitaires ───────────────────────────────────────────────────────────

    def _get_client(self):
        if self._client is not None:
            return self._client
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            return None
        try:
            from google import genai

            self._client = genai.Client(api_key=key)
            return self._client
        except Exception:
            return None


# ── Analyse des sources ───────────────────────────────────────────────────────

def _parser_mails(brut: str, limite: int) -> list[Message]:
    """Transforme la sortie texte de google_agent en messages structurés."""
    messages: list[Message] = []
    if not brut:
        return messages
    blocs = re.split(r"\n(?=(?:De|From)\s*:)", str(brut))
    for i, bloc in enumerate(blocs[:limite]):
        exp = re.search(r"(?:De|From)\s*:\s*(.+)", bloc)
        suj = re.search(r"(?:Objet|Sujet|Subject)\s*:\s*(.+)", bloc)
        if not exp:
            continue
        expediteur = exp.group(1).strip()
        adresse = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", expediteur)
        corps = re.sub(r"^(?:De|From|Objet|Sujet|Subject|Date)\s*:.*$", "",
                       bloc, flags=re.MULTILINE).strip()
        messages.append(Message(
            id=f"mail_{i}",
            canal="mail",
            expediteur=adresse.group(0) if adresse else expediteur,
            sujet=suj.group(1).strip() if suj else "",
            corps=corps[:3000],
            recu_le=datetime.now().strftime("%d/%m %H:%M"),
        ))
    return messages


def _parser_instagram(contenu: str, limite: int) -> list[Message]:
    """Extrait les conversations de la page de messagerie Instagram."""
    messages: list[Message] = []
    lignes = [l.strip() for l in (contenu or "").splitlines() if l.strip()]
    ignorer = {"instagram", "messages", "demandes", "recherche", "accueil",
               "explorer", "reels", "profil", "discussion", "nouveau message"}
    i = 0
    while i < len(lignes) - 1 and len(messages) < limite:
        nom = lignes[i]
        apercu = lignes[i + 1]
        plausible = (
            2 <= len(nom) <= 40
            and nom.lower() not in ignorer
            and not nom.startswith(("http", "•"))
            and len(apercu) > 3
            and apercu.lower() not in ignorer
        )
        if plausible:
            messages.append(Message(
                id=f"ig_{len(messages)}",
                canal="instagram",
                expediteur=nom,
                corps=apercu[:500],
                recu_le=datetime.now().strftime("%d/%m %H:%M"),
            ))
            i += 2
        else:
            i += 1
    return messages
