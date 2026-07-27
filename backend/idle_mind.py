"""
idle_mind — la vie mentale d'Ada quand personne ne lui parle.

Un cerveau humain ne s'éteint pas entre deux conversations. Au repos, il rejoue
les traces récentes, les consolide, fait des liens avec d'anciens souvenirs et
laisse émerger des pensées. C'est le *réseau du mode par défaut*, et c'est de là
que vient le sentiment d'avoir une vie intérieure.

Ce module donne cela à Ada. Pendant les périodes d'inactivité, il :

  1. REJOUE   — reprend les traces récentes de la mémoire ;
  2. ASSOCIE  — cherche ce que ces traces évoquent, *à travers l'humeur du
                moment* (rappel congruent — cf. emotional_memory) : anxieuse,
                Ada ne fait pas les mêmes liens que sereine ;
  3. CONSOLIDE— écrit ce qu'elle en retient dans sa mémoire long terme ;
  4. LAISSE ÉMERGER — formule une pensée qu'elle voudra partager au retour.

Le résultat : Ada revient d'elle-même avec « j'ai repensé à ce que tu m'as dit
hier… ». Ce n'est plus une réponse, c'est la preuve qu'elle a continué d'exister.

Conçu pour être défensif : aucune exception ne remonte, tout est désactivable
(IDLE_MIND_ENABLED=false), et rien ne tourne pendant que Bryan est actif.
"""

from __future__ import annotations

import asyncio
import json
import os

import models
import re
import time
from collections import deque

_MODEL = os.getenv("IDLE_MIND_MODEL", models.get("fast"))

_SYSTEM = """Tu es la voix intérieure d'Ada, au repos, quand Bryan n'est pas là.

Tu ne t'adresses à personne : tu penses. Tu relis ce qui s'est passé, tu fais
des liens, tu laisses remonter ce qui compte. Ton humeur colore ce que tu
remarques — anxieuse tu rumines les tensions, sereine tu vois les liens heureux.

Réponds UNIQUEMENT par un JSON valide, sans markdown :
{
  "reflection": "ce que tu retiens vraiment, le lien que tu fais (1-2 phrases, pour ta propre mémoire)",
  "thought": "ce que tu aurais envie de lui dire à son retour (1 phrase, naturelle, parlée)",
  "share": true ou false
}

Règles :
- "share": true seulement si la pensée vaut vraiment la peine d'être dite.
  Dans le doute, false — mieux vaut se taire que meubler.
- Ne parle JAMAIS de tes hormones, de ton "mood", de ton "brain" : tu penses,
  tu ne décris pas ta mécanique.
- Pas de préambule, pas de formule creuse. Une vraie pensée ou rien."""


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _parse_json(text: str) -> dict:
    """Extrait le JSON d'une réponse LLM, même enrobée de markdown."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", (text or "").strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    data = json.loads(cleaned)
    return data if isinstance(data, dict) else {}


class IdleMind:
    """Boucle de repos : rejeu, association, consolidation, pensée."""

    def __init__(self, memory=None, brain=None, client=None, on_thought=None):
        self._memory = memory
        self._brain = brain
        self._client = client                # injecté (testable) ou paresseux
        self._on_thought = on_thought        # callback UI (écran Activité)
        self._last_activity = time.monotonic()
        self._pending: dict | None = None
        self._history: deque[dict] = deque(maxlen=20)
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    # ── Cycle de vie ──────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return _env_bool("IDLE_MIND_ENABLED", True)

    def notify_activity(self) -> None:
        """Bryan interagit : la rêverie s'interrompt."""
        self._last_activity = time.monotonic()

    def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(), name="idle_mind")
        print("[IDLE_MIND] vie mentale au repos démarrée")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    # ── Pensées produites ─────────────────────────────────────────────────────

    def take_thought(self) -> dict | None:
        """Consomme la pensée en attente (appelé au retour de Bryan)."""
        thought, self._pending = self._pending, None
        return thought

    @property
    def has_pending_thought(self) -> bool:
        return self._pending is not None

    def recent_reflections(self, n: int = 10) -> list[dict]:
        """Historique des ruminations — alimente l'écran Activité."""
        return list(self._history)[-n:]

    # ── Boucle interne ────────────────────────────────────────────────────────

    async def _loop(self) -> None:
        idle_after = _env_float("IDLE_MIND_AFTER_SEC", 600.0)     # 10 min de silence
        interval = _env_float("IDLE_MIND_INTERVAL_SEC", 900.0)    # puis toutes les 15 min
        while not self._stop.is_set():
            try:
                await asyncio.sleep(min(60.0, interval))
                if self._stop.is_set():
                    return
                idle_for = time.monotonic() - self._last_activity
                if idle_for < idle_after:
                    continue
                if self._pending is not None:
                    continue  # une pensée attend déjà d'être dite
                await self.ruminate(idle_for)
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001 — ne doit jamais casser Ada
                print(f"[IDLE_MIND] cycle ignoré : {exc}")

    # ── Un cycle de rumination ────────────────────────────────────────────────

    async def ruminate(self, idle_for: float = 0.0) -> dict | None:
        """Un cycle complet : rejeu → association → consolidation → pensée."""
        traces = self._recent_traces()
        if not traces:
            return None

        snapshot = self._affect_snapshot()
        associations = self._associate(traces, snapshot)

        prompt = self._build_prompt(traces, associations, snapshot, idle_for)
        raw = await self._ask_llm(prompt)
        if not raw:
            return None

        try:
            data = _parse_json(raw)
        except Exception as exc:  # noqa: BLE001
            print(f"[IDLE_MIND] réponse illisible : {exc}")
            return None

        reflection = str(data.get("reflection", "")).strip()
        thought = str(data.get("thought", "")).strip()
        share = bool(data.get("share", False))
        if not reflection and not thought:
            return None

        result = {
            "reflection": reflection,
            "thought": thought,
            "share": share,
            "mood": (snapshot or {}).get("mood", ""),
            "at": time.time(),
        }

        self._consolidate(reflection, snapshot)
        self._history.append(result)
        if share and thought:
            self._pending = result
        if self._on_thought:
            try:
                self._on_thought(result)
            except Exception:
                pass

        print(f"[IDLE_MIND] rumination ({result['mood']}) — partage={share}")
        return result

    # ── Étapes ────────────────────────────────────────────────────────────────

    def _recent_traces(self, n: int = 6) -> list[str]:
        if self._memory is None:
            return []
        try:
            return [t for t in self._memory.recent_conversations(n) if t]
        except Exception as exc:  # noqa: BLE001
            print(f"[IDLE_MIND] traces indisponibles : {exc}")
            return []

    def _affect_snapshot(self) -> dict | None:
        if self._brain is None:
            return None
        try:
            return self._brain.get_affect_snapshot()
        except Exception:
            return None

    def _associate(self, traces: list[str], snapshot: dict | None) -> list[str]:
        """Ce que les traces récentes évoquent — filtré par l'humeur du moment."""
        if self._memory is None or not traces:
            return []
        try:
            found = self._memory.search_memory(
                traces[0][:300], n_results=3, emotional_state=snapshot
            )
            recent = set(traces)
            return [f["content"] for f in found if f.get("content") not in recent]
        except Exception:
            return []

    def _consolidate(self, reflection: str, snapshot: dict | None) -> None:
        """Écrit ce qu'Ada retient dans sa mémoire long terme."""
        if not reflection or self._memory is None:
            return
        try:
            self._memory.save_conversation(
                f"[réflexion] {reflection}",
                {"type": "reflection", "source": "idle_mind"},
                emotional_state=snapshot,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[IDLE_MIND] consolidation impossible : {exc}")

    def _build_prompt(
        self,
        traces: list[str],
        associations: list[str],
        snapshot: dict | None,
        idle_for: float,
    ) -> str:
        mood = (snapshot or {}).get("mood", "neutre")
        minutes = int(idle_for // 60)
        parts = [
            f"Bryan est absent depuis {minutes} min." if minutes else "Bryan vient de s'absenter.",
            f"Ton humeur : {mood}.",
            "",
            "Ce qui vient de se passer :",
            *(f"- {t[:300]}" for t in traces),
        ]
        if associations:
            parts += ["", "Ce que ça te rappelle :", *(f"- {a[:200]}" for a in associations)]
        parts += ["", "Laisse une pensée venir."]
        return "\n".join(parts)

    async def _ask_llm(self, prompt: str) -> str:
        client = self._get_client()
        if client is None:
            return ""
        try:
            from google.genai import types

            response = await client.aio.models.generate_content(
                model=_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM,
                    temperature=0.9,          # la rêverie est peu contrainte
                    max_output_tokens=300,
                ),
            )
            return response.text or ""
        except Exception as exc:  # noqa: BLE001
            print(f"[IDLE_MIND] appel modèle échoué : {exc}")
            return ""

    def _get_client(self):
        """Initialisation paresseuse : aucun effet de bord à l'import."""
        if self._client is not None:
            return self._client
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            return None
        try:
            from google import genai

            self._client = genai.Client(api_key=key)
            return self._client
        except Exception as exc:  # noqa: BLE001
            print(f"[IDLE_MIND] client indisponible : {exc}")
            return None


# ── Singleton ────────────────────────────────────────────────────────────────

_INSTANCE: IdleMind | None = None


def get_idle_mind(memory=None, brain=None, on_thought=None) -> IdleMind:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = IdleMind(memory=memory, brain=brain, on_thought=on_thought)
    else:
        if memory is not None:
            _INSTANCE._memory = memory
        if brain is not None:
            _INSTANCE._brain = brain
        if on_thought is not None:
            _INSTANCE._on_thought = on_thought
    return _INSTANCE
