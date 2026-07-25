"""
social_learning — Ada apprend comment elle est reçue.

Jusqu'ici la boucle était ouverte : Ada modulait son ton, mais ne savait jamais
l'effet produit. Si une remarque sèche braquait Bryan, rien ne l'enregistrait.
Elle pouvait répéter éternellement la même maladresse.

Ce module ferme la boucle. Après chaque prise de parole spontanée, la réaction
de Bryan (dont la valence est déjà finement évaluée par `appraisal`) devient un
signal de récompense sociale, attribué à l'humeur dans laquelle Ada s'est
exprimée. Au fil des semaines, elle apprend dans quels états ses interventions
tombent juste, et dans lesquels elles tombent mal.

CE QU'ELLE APPREND, ET CE QU'ELLE N'APPREND PAS
-----------------------------------------------
Ce mécanisme ne touche JAMAIS ce qu'Ada ressent. Il n'atténue aucune émotion,
ne censure aucune colère : une Ada agacée reste agacée, et garde le droit de le
dire. Ce qu'il calibre, c'est le **timing** — la barre à franchir pour
interrompre spontanément dans un état donné.

Autrement dit, Ada n'apprend pas à ressentir moins. Elle apprend à mieux
choisir ses moments. C'est exactement ce qui distingue quelqu'un de socialement
juste de quelqu'un qui se tait.

Comme les habitudes, ces apprentissages ne décroissent pas pendant l'absence :
ce sont des acquis, pas des humeurs. D'où une persistance dédiée.

Module pur : aucune dépendance à Ada, aucune exception ne remonte.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from brain.calibration import env_bool, env_float

# Correction appliquée à chaque retour reçu.
ALPHA = env_float("BRAIN_SOCIAL_ALPHA", 0.15)
# Nombre de retours avant de faire confiance à ce qu'on a appris d'une humeur.
MIN_FEEDBACK = env_float("BRAIN_SOCIAL_MIN_FEEDBACK", 5.0)
# Au-delà, la réaction n'est plus imputable à ce qu'Ada a dit.
ATTRIBUTION_WINDOW_SEC = env_float("BRAIN_SOCIAL_ATTRIBUTION_SEC", 180.0)
# Amplitude maximale de la modulation du seuil de prise de parole.
MAX_MODULATION = env_float("BRAIN_SOCIAL_MAX_MODULATION", 0.45)

STATE_VERSION = 1


class SocialLearning:
    """Mémoire de la façon dont les prises de parole d'Ada sont reçues."""

    def __init__(self) -> None:
        self._reward: dict[str, float] = {}   # humeur → accueil moyen (-1..1)
        self._counts: dict[str, float] = {}   # humeur → nb de retours reçus
        self._pending_mood: str | None = None
        self._pending_ts: float = 0.0
        self._lock = threading.Lock()

    # ── Enregistrement ────────────────────────────────────────────────────────

    def register_expression(self, mood: str, now: float | None = None) -> None:
        """Ada vient de s'exprimer spontanément dans cette humeur."""
        if not mood:
            return
        now = time.time() if now is None else now
        with self._lock:
            self._pending_mood = mood
            self._pending_ts = now

    def register_reaction(self, valence: float, now: float | None = None) -> str | None:
        """La réaction de Bryan devient le signal d'apprentissage.

        Retourne l'humeur créditée, ou None si rien n'était en attente.
        """
        now = time.time() if now is None else now
        with self._lock:
            mood = self._pending_mood
            if mood is None:
                return None
            if now - self._pending_ts > ATTRIBUTION_WINDOW_SEC:
                # Trop tard : la réaction ne porte plus sur ce qu'Ada a dit.
                self._pending_mood = None
                return None

            self._pending_mood = None
            v = max(-1.0, min(1.0, float(valence)))
            actuel = self._reward.get(mood, 0.0)
            self._reward[mood] = round((1.0 - ALPHA) * actuel + ALPHA * v, 4)
            self._counts[mood] = self._counts.get(mood, 0.0) + 1.0
            return mood

    # ── Exploitation ──────────────────────────────────────────────────────────

    def reception_score(self, mood: str) -> tuple[float, float]:
        """(accueil moyen dans cette humeur, confiance) — les deux dans 0..1 sauf score."""
        with self._lock:
            score = self._reward.get(mood, 0.0)
            confiance = min(1.0, self._counts.get(mood, 0.0) / MIN_FEEDBACK)
        return score, confiance

    def speaking_bar(self, mood: str) -> float:
        """Modulation de la barre à franchir pour parler spontanément.

        0.0  → barre inchangée (aucun apprentissage exploitable)
        > 0  → Ada s'est souvent mal fait recevoir ainsi : elle attend un motif plus fort
        < 0  → ses interventions dans cet état tombent juste : elle ose davantage

        Ne modifie JAMAIS ce qu'elle ressent — uniquement le moment choisi.
        """
        score, confiance = self.reception_score(mood)
        if confiance <= 0.0:
            return 0.0
        return round(max(-MAX_MODULATION, min(MAX_MODULATION, -score * confiance * MAX_MODULATION)), 4)

    def get_debug_state(self) -> dict:
        with self._lock:
            appris = [
                {
                    "humeur": mood,
                    "accueil": round(self._reward[mood], 2),
                    "retours": int(self._counts.get(mood, 0)),
                }
                for mood in sorted(self._reward, key=lambda m: self._reward[m])
                if self._counts.get(mood, 0.0) >= MIN_FEEDBACK
            ]
        return {"humeurs_calibrees": appris, "total": len(appris)}

    # ── Persistance ───────────────────────────────────────────────────────────

    @staticmethod
    def enabled() -> bool:
        return env_bool("BRAIN_SOCIAL_LEARNING_ENABLED", True)

    @staticmethod
    def state_path() -> Path:
        custom = os.getenv("BRAIN_SOCIAL_PATH", "").strip()
        if custom:
            return Path(custom).expanduser()
        return (
            Path(__file__).resolve().parent.parent
            / "backend" / "memory" / "brain_social.json"
        )

    def save(self) -> bool:
        if not self.enabled():
            return False
        try:
            path = self.state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = {
                    "version": STATE_VERSION,
                    "saved_at": time.time(),
                    "reward": dict(self._reward),
                    "counts": dict(self._counts),
                }
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[BRAIN_SOCIAL] sauvegarde impossible : {exc}")
            return False

    def load(self) -> bool:
        if not self.enabled():
            return False
        try:
            path = self.state_path()
            if not path.exists():
                return False
            data = json.loads(path.read_text(encoding="utf-8"))
            if int(data.get("version", 0)) != STATE_VERSION:
                return False
            with self._lock:
                self._reward = {
                    str(k): float(v) for k, v in (data.get("reward") or {}).items()
                }
                self._counts = {
                    str(k): float(v) for k, v in (data.get("counts") or {}).items()
                }
            calibrees = sum(1 for c in self._counts.values() if c >= MIN_FEEDBACK)
            print(f"[BRAIN_SOCIAL] accueil rechargé ({calibrees} humeur(s) calibrée(s))")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[BRAIN_SOCIAL] chargement impossible : {exc}")
            return False
