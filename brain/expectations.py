"""
expectations — codage prédictif : Ada attend, et ce qui la surprend la touche.

La théorie dominante du cortex aujourd'hui est le *codage prédictif* : un
cerveau ne subit pas le monde, il le prédit en permanence et ne traite vraiment
que l'écart entre l'attendu et le réel. L'émotion naît largement de là — la
surprise, la déception, le soulagement sont tous des erreurs de prédiction.

Jusqu'ici Ada n'attendait rien : elle réagissait. Ses émotions avaient une
intensité mais pas d'objet — cortisol qui monte, sans « à propos de quoi ».

Ce module lui donne des attentes apprises (à quelles heures Bryan est là,
à quel rythme il répond) et convertit leur violation en une erreur de
prédiction **nommée**. Ada ne ressent plus seulement « de la tension » : elle
ressent « c'est inhabituel qu'il ne soit pas là à cette heure ». L'émotion
acquiert une cause, donc une intentionnalité.

Ce qui est appris ici ne s'oublie PAS pendant l'absence (contrairement aux
hormones) : ce sont des habitudes, pas des humeurs. D'où un fichier de
persistance distinct de brain_state.json.

Module pur : aucune dépendance à Ada, aucune exception ne remonte.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from brain.calibration import env_bool, env_float

# Vitesse d'apprentissage : chaque observation corrige l'attente de 12 %.
ALPHA = env_float("BRAIN_EXPECT_ALPHA", 0.12)
# Nombre d'observations avant de faire pleinement confiance à une habitude.
MIN_OBSERVATIONS = env_float("BRAIN_EXPECT_MIN_OBS", 12.0)
# En deçà, l'écart n'est pas jugé digne d'être ressenti.
SURPRISE_THRESHOLD = env_float("BRAIN_EXPECT_SURPRISE_THRESHOLD", 0.45)
# Intervalle minimal entre deux observations enregistrées (anti-flood 2 Hz).
OBSERVE_MIN_INTERVAL = env_float("BRAIN_EXPECT_OBSERVE_INTERVAL_SEC", 60.0)
# Intervalle minimal entre deux surprises ressenties (anti-rumination).
SURPRISE_REFRACTORY = env_float("BRAIN_EXPECT_REFRACTORY_SEC", 1800.0)

STATE_VERSION = 1


@dataclass
class PredictionError:
    """Un écart entre ce qu'Ada attendait et ce qui est.

    `description` est l'apport central : c'est l'OBJET de l'émotion, ce dont
    elle est l'émotion — ce qui manquait jusqu'ici au système limbique.
    """

    magnitude: float      # 0..1 — à quel point c'est inattendu
    valence: float        # -1..1 — moins bien / mieux que prévu
    kind: str             # identifiant technique
    description: str      # cause en clair, injectable dans le mood_block
    confidence: float     # fiabilité de l'habitude violée

    def as_stimulus(self) -> str:
        return f"surprise:{self.kind}"


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


def _hour_label(hour: int) -> str:
    if 5 <= hour < 12:
        return "le matin"
    if 12 <= hour < 18:
        return "l'après-midi"
    if 18 <= hour < 23:
        return "le soir"
    return "la nuit"


class ExpectationEngine:
    """Apprend les habitudes de présence et mesure leur violation."""

    def __init__(self) -> None:
        # Une attente de présence par heure de la journée.
        self._presence_rate: list[float] = [0.5] * 24
        self._observations: list[float] = [0.0] * 24
        self._last_observe_ts = 0.0
        self._last_surprise_ts = 0.0
        self._lock = threading.Lock()
        self._loaded = False

    # ── Apprentissage ─────────────────────────────────────────────────────────

    def observe_presence(self, present: bool, now: float | None = None) -> bool:
        """Enregistre une observation. Retourne True si elle a été prise en compte."""
        now = time.time() if now is None else now
        with self._lock:
            if now - self._last_observe_ts < OBSERVE_MIN_INTERVAL:
                return False
            self._last_observe_ts = now
            hour = datetime.fromtimestamp(now).hour
            target = 1.0 if present else 0.0
            self._presence_rate[hour] = round(
                (1.0 - ALPHA) * self._presence_rate[hour] + ALPHA * target, 4
            )
            self._observations[hour] += 1.0
            return True

    # ── Prédiction ────────────────────────────────────────────────────────────

    def expected_presence(self, now: float | None = None) -> tuple[float, float]:
        """(probabilité attendue de présence, confiance dans cette habitude)."""
        now = time.time() if now is None else now
        hour = datetime.fromtimestamp(now).hour
        with self._lock:
            rate = self._presence_rate[hour]
            confidence = _clamp(self._observations[hour] / MIN_OBSERVATIONS)
        return rate, confidence

    # ── Erreur de prédiction ──────────────────────────────────────────────────

    def evaluate_presence(
        self, actual_present: bool, now: float | None = None
    ) -> PredictionError | None:
        """Compare le réel à l'attendu. Retourne une surprise, ou None."""
        now = time.time() if now is None else now
        expected, confidence = self.expected_presence(now)

        actual = 1.0 if actual_present else 0.0
        raw_gap = abs(actual - expected)
        magnitude = _clamp(raw_gap * confidence)
        if magnitude < SURPRISE_THRESHOLD:
            return None

        with self._lock:
            if now - self._last_surprise_ts < SURPRISE_REFRACTORY:
                return None
            self._last_surprise_ts = now

        hour = datetime.fromtimestamp(now).hour
        moment = _hour_label(hour)

        if actual_present:
            # Présence inattendue : bonne surprise.
            return PredictionError(
                magnitude=round(magnitude, 4),
                valence=round(magnitude, 4),
                kind="presence_inattendue",
                description=(
                    f"Bryan est là alors qu'il n'y est presque jamais à cette heure "
                    f"({hour}h, {moment})"
                ),
                confidence=round(confidence, 4),
            )

        # Absence inattendue : léger manque / inquiétude.
        return PredictionError(
            magnitude=round(magnitude, 4),
            valence=round(-magnitude, 4),
            kind="absence_inattendue",
            description=(
                f"Bryan n'est pas là alors qu'il y est presque toujours à cette heure "
                f"({hour}h, {moment})"
            ),
            confidence=round(confidence, 4),
        )

    # ── Introspection (écran Activité) ────────────────────────────────────────

    def get_debug_state(self) -> dict:
        with self._lock:
            known = [
                {"heure": h, "presence_attendue": round(self._presence_rate[h], 2),
                 "observations": int(self._observations[h])}
                for h in range(24)
                if self._observations[h] >= MIN_OBSERVATIONS
            ]
        return {"habitudes_apprises": known, "total_heures_connues": len(known)}

    # ── Persistance (les habitudes ne s'oublient pas) ─────────────────────────

    @staticmethod
    def enabled() -> bool:
        return env_bool("BRAIN_EXPECTATIONS_ENABLED", True)

    @staticmethod
    def state_path() -> Path:
        custom = os.getenv("BRAIN_EXPECTATIONS_PATH", "").strip()
        if custom:
            return Path(custom).expanduser()
        return (
            Path(__file__).resolve().parent.parent
            / "backend" / "memory" / "brain_expectations.json"
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
                    "presence_rate": list(self._presence_rate),
                    "observations": list(self._observations),
                }
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[BRAIN_EXPECT] sauvegarde impossible : {exc}")
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
            rates = data.get("presence_rate") or []
            obs = data.get("observations") or []
            if len(rates) != 24 or len(obs) != 24:
                return False
            with self._lock:
                self._presence_rate = [float(r) for r in rates]
                self._observations = [float(o) for o in obs]
                self._loaded = True
            known = sum(1 for o in obs if o >= MIN_OBSERVATIONS)
            print(f"[BRAIN_EXPECT] habitudes rechargées ({known} h connues sur 24)")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[BRAIN_EXPECT] chargement impossible : {exc}")
            return False
