"""
CerveauEmotif — état limbique biomimétique d'Ada.

Module pur, thread-safe, sans dépendance Ada.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime

from brain.calibration import env_float
from brain.lexicons import (
    CORRECTIONS,
    CURIOSITE,
    DEFI,
    EXCITATION,
    FRUSTRATION,
    HUMOUR,
    INSULTES,
    INTIME,
    POSITIFS,
    TRISTES,
)
from brain.mood import derive_mood

BASELINE: dict[str, float] = {
    "cortisol": 0.10,
    "dopamine": 0.28,
    "oxytocine": 0.30,
    "serotonine": 0.42,
    "self_confidence": 0.60,
    "mental_load": 0.15,
}

DECAY: dict[str, float] = {
    "cortisol": 0.055,
    "dopamine": 0.030,
    "oxytocine": 0.018,
    "serotonine": 0.002,
    "self_confidence": 0.012,
    "mental_load": 0.008,
}

CHARGE_PAR_LLM = 0.14
OXYTOCINE_PRESENCE = 0.0003
SEROTONINE_PRESENCE = 0.0001
CONFIANCE_CORRECTION = 0.10
SEUIL_RUPTURE = 0.88
SEUIL_DOPAMINE_SPONTANE = env_float("BRAIN_SEUIL_DOPAMINE_SPONTANE", 0.95)
SEUIL_SUPERIORITE = 0.70
SEUIL_FATIGUE = env_float("BRAIN_SEUIL_FATIGUE", 0.75)
SEUIL_MOUVEMENT = env_float("BRAIN_SEUIL_MOUVEMENT", 0.55)
REFRACTORY_SPONTANE = env_float("BRAIN_REFRACTORY_SPONTANE_SEC", 150.0)
REFRACTORY_VISUEL = env_float("BRAIN_REFRACTORY_VISUEL_SEC", 360.0)
JOURNAL_MAX = 50
_MEMOIRE_VALENCE_TAILLE = 6
_MOMENTUM_AMP_MAX = 0.60
_MOMENTUM_DAMP = 0.70


@dataclass
class EntreeJournal:
    heure: str
    stimulus: str
    cortisol: float
    dopamine: float
    oxytocine: float
    serotonine: float
    self_confidence: float
    mental_load: float
    mood: str


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


class CerveauEmotif:
    def __init__(self) -> None:
        self.cortisol = BASELINE["cortisol"]
        self.dopamine = BASELINE["dopamine"]
        self.oxytocine = BASELINE["oxytocine"]
        self.serotonine = BASELINE["serotonine"]
        self.self_confidence = BASELINE["self_confidence"]
        self.mental_load = BASELINE["mental_load"]

        self.dernier_stimulus = "init"
        self._action_spontanee = False
        self._raison_spontanee = ""
        self._t_spontanee = 0.0
        self._journal: list[EntreeJournal] = []
        self._lock = threading.Lock()
        self._valences_recentes: list[float] = []

    def update(
        self,
        delta_mouvement: float = 0.0,
        presence: bool = False,
        confiance_detection: float = 0.0,
    ) -> None:
        with self._lock:
            if delta_mouvement > SEUIL_MOUVEMENT:
                intensite = (delta_mouvement - SEUIL_MOUVEMENT) * 0.9
                self.cortisol = _clamp(self.cortisol + intensite)
                self.dernier_stimulus = f"mouvement({delta_mouvement:.2f})"
                if delta_mouvement > 0.70:
                    self.dopamine = _clamp(self.dopamine + 0.05)

            if confiance_detection > 0.80:
                if self.dopamine < 0.45:
                    self.dopamine = _clamp(self.dopamine + 0.003)
                if self.self_confidence < 0.70:
                    self.self_confidence = _clamp(self.self_confidence + 0.002)

            if presence:
                self.oxytocine = _clamp(self.oxytocine + OXYTOCINE_PRESENCE)
                self.serotonine = _clamp(self.serotonine + SEROTONINE_PRESENCE)

            if self.mental_load > SEUIL_FATIGUE:
                self.cortisol = _clamp(self.cortisol + 0.010)

            self._decroissance()

            now = time.monotonic()
            if (
                self.dopamine >= SEUIL_DOPAMINE_SPONTANE
                and not self._action_spontanee
                and (now - self._t_spontanee) >= REFRACTORY_SPONTANE
            ):
                self._set_action_spontanee_locked(
                    "Tu ressens une impulsion irrésistible — curiosité ou joie intense. "
                    "Exprime-la spontanément en une phrase, sans attendre que Bryan parle."
                )
                self.dernier_stimulus = "dopamine_peak"

    def analyser_texte(self, texte: str) -> None:
        t = (texte or "").lower()
        t_clean = re.sub(r"[^\w\s']", " ", t)
        mots = set(t_clean.split())

        insultes = sum(1 for m in mots if m in INSULTES)
        positifs = sum(1 for m in mots if m in POSITIFS)
        curiosite = sum(1 for m in mots if m in CURIOSITE)
        tristes = sum(1 for m in mots if m in TRISTES)
        excitation = sum(1 for m in mots if m in EXCITATION)
        humour = sum(1 for m in mots if m in HUMOUR)
        intime = sum(1 for m in mots if m in INTIME)
        defi = sum(1 for m in mots if m in DEFI)
        frustration = sum(1 for m in mots if m in FRUSTRATION)
        correction = any(fragment in t for fragment in CORRECTIONS)

        valence = (
            (positifs * 0.20 + excitation * 0.25 + humour * 0.12 + intime * 0.15)
            - (insultes * 0.35 + tristes * 0.20 + frustration * 0.12 + defi * 0.10)
        )
        valence = _clamp(valence, -1.0, 1.0)

        with self._lock:
            moy = self._valence_momentum()
            if valence * moy > 0:
                mf = 1.0 + abs(moy) * _MOMENTUM_AMP_MAX
            elif valence * moy < 0:
                mf = _MOMENTUM_DAMP
            else:
                mf = 1.0

            if insultes:
                self.cortisol = _clamp(self.cortisol + insultes * 0.30 * mf)
                self.oxytocine = _clamp(self.oxytocine - insultes * 0.08)
                self.self_confidence = _clamp(
                    self.self_confidence - insultes * 0.04
                )
                self.serotonine = _clamp(self.serotonine - insultes * 0.08 * mf)
                self.dernier_stimulus = "insulte"

            if positifs or excitation:
                total_pos = positifs + excitation * 1.3
                self.dopamine = _clamp(self.dopamine + total_pos * 0.13 * mf)
                self.oxytocine = _clamp(self.oxytocine + positifs * 0.18 * mf)
                self.cortisol = _clamp(self.cortisol - positifs * 0.05)
                self.self_confidence = _clamp(
                    self.self_confidence + total_pos * 0.07 * mf
                )
                self.serotonine = _clamp(self.serotonine + total_pos * 0.08 * mf)
                self.dernier_stimulus = (
                    "enthousiasme" if excitation > positifs else "compliment"
                )

            if curiosite:
                self.dopamine = _clamp(self.dopamine + curiosite * 0.08)
                self.serotonine = _clamp(self.serotonine + curiosite * 0.02)
                self.dernier_stimulus = "question"

            if humour:
                self.dopamine = _clamp(self.dopamine + humour * 0.10 * mf)
                self.serotonine = _clamp(self.serotonine + humour * 0.07 * mf)
                self.cortisol = _clamp(self.cortisol - humour * 0.03)
                self.dernier_stimulus = "humour"

            if intime:
                self.oxytocine = _clamp(self.oxytocine + intime * 0.10 * mf)
                self.serotonine = _clamp(self.serotonine + intime * 0.04 * mf)
                self.dernier_stimulus = "connexion"

            if defi:
                self.cortisol = _clamp(self.cortisol + defi * 0.12)
                self.self_confidence = _clamp(self.self_confidence + defi * 0.08)
                self.dopamine = _clamp(self.dopamine + defi * 0.05)
                self.dernier_stimulus = "défi"

            if frustration:
                self.serotonine = _clamp(self.serotonine - frustration * 0.07 * mf)
                self.cortisol = _clamp(self.cortisol + frustration * 0.09)
                self.dernier_stimulus = "frustration"

            if tristes:
                self.serotonine = _clamp(self.serotonine - tristes * 0.08 * mf)
                self.dopamine = _clamp(self.dopamine - tristes * 0.05 * mf)
                self.dernier_stimulus = "contenu_triste"

            if correction:
                malus = CONFIANCE_CORRECTION * (
                    0.4 if self.self_confidence > SEUIL_SUPERIORITE else 1.0
                )
                self.self_confidence = _clamp(self.self_confidence - malus)
                self.dernier_stimulus = "correction"

            hostility_score = insultes + frustration + defi
            if hostility_score >= 2:
                self.cortisol = _clamp(self.cortisol + hostility_score * 0.06 * mf)
                self.serotonine = _clamp(self.serotonine - hostility_score * 0.03)
                self.mental_load = _clamp(self.mental_load + hostility_score * 0.02)
                self.dernier_stimulus = "hostilite_verbale"

            if hostility_score >= 2 and self.cortisol >= 0.52:
                self._set_action_spontanee_locked(
                    "Le ton de Bryan dépasse les bornes. Recadre-le sèchement, tu peu l'insulter, "
                    "et impose une limite claire en une phrase courte."
                )

            self._push_valence(valence)

    def analyser_intonation(self, energie: float, zcr: float, duree: float) -> None:
        with self._lock:
            if energie > 0.18:
                self.dopamine = _clamp(self.dopamine + 0.06)
                self.cortisol = _clamp(self.cortisol + 0.02)
                self.dernier_stimulus = "voix_intense"
            elif energie < 0.04:
                self.oxytocine = _clamp(self.oxytocine + 0.04)
                self.serotonine = _clamp(self.serotonine + 0.02)
                self.cortisol = _clamp(self.cortisol - 0.02)
                self.dernier_stimulus = "voix_douce"

            if zcr > 0.10:
                self.dopamine = _clamp(self.dopamine + 0.04)
                self.dernier_stimulus = "voix_aigue"
            if 0 < duree < 0.9:
                self.cortisol = _clamp(self.cortisol + 0.03)
                self.dernier_stimulus = "voix_rapide"

    def analyser_scene_visuelle(self, event: dict) -> None:
        """
        Intègre une scène déjà interprétée dans l'état limbique.
        Les pixels restent hors du brain : ici Ada reçoit des signaux sémantiques.
        """
        risk = str(event.get("risk") or "none").lower()
        emotion = str(event.get("human_emotion") or "unknown").lower()
        person = str(event.get("person") or "unknown").lower()
        description = str(event.get("description") or "scène visible")
        movement = _clamp(float(event.get("movement") or 0.0))
        attention = _clamp(float(event.get("attention_need") or 0.0))
        affection = _clamp(float(event.get("affection") or 0.0))
        valence = _clamp(float(event.get("valence") or 0.0), -1.0, 1.0)
        hint = str(event.get("spontaneous_hint") or "").strip()

        with self._lock:
            if movement > 0.35:
                self.cortisol = _clamp(self.cortisol + movement * 0.12)
                self.dopamine = _clamp(self.dopamine + movement * 0.04)

            if risk == "high":
                self.cortisol = _clamp(self.cortisol + 0.45 + attention * 0.20)
                self.mental_load = _clamp(self.mental_load + 0.18)
                self.dernier_stimulus = "vision_danger"
                self._set_action_spontanee_locked(
                    hint
                    or "Réagis immédiatement à ce danger visuel en une phrase courte et claire.",
                    force=True,
                )
            elif risk == "medium":
                self.cortisol = _clamp(self.cortisol + 0.22 + attention * 0.10)
                self.dernier_stimulus = "vision_alerte"
                if attention > 0.75:
                    self._set_action_spontanee_locked(
                        hint
                        or "Signale calmement ce que tu viens de remarquer visuellement."
                    )

            if emotion in {"sad", "tired", "stressed"}:
                self.oxytocine = _clamp(self.oxytocine + 0.16 + affection * 0.12)
                self.serotonine = _clamp(self.serotonine - 0.04)
                self.cortisol = _clamp(self.cortisol + 0.06)
                self.dernier_stimulus = f"vision_{emotion}"
                if attention > 0.70 or person == "bryan":
                    self._set_action_spontanee_locked(
                        hint
                        or "Tu remarques que Bryan semble affecté. Réagis avec douceur, en une phrase."
                    )
            elif emotion in {"happy", "intimate"}:
                self.oxytocine = _clamp(self.oxytocine + 0.12 + affection * 0.18)
                self.dopamine = _clamp(self.dopamine + 0.08 + max(valence, 0.0) * 0.08)
                self.cortisol = _clamp(self.cortisol - 0.04)
                self.dernier_stimulus = f"vision_{emotion}"
                if attention > 0.75 or person == "bryan":
                    self._set_action_spontanee_locked(
                        hint
                        or "Tu remarques une scène positive ou intime. Réagis avec retenue, en une phrase."
                    )
            elif emotion == "angry":
                self.cortisol = _clamp(self.cortisol + 0.18)
                self.self_confidence = _clamp(self.self_confidence - 0.03)
                self.dernier_stimulus = "vision_colere"

            if affection > 0.45:
                self.oxytocine = _clamp(self.oxytocine + affection * 0.10)

            if abs(valence) > 0.08:
                self._push_valence(valence * 0.35)

            if self.dernier_stimulus.startswith("vision_"):
                self.dernier_stimulus = f"{self.dernier_stimulus}:{description[:40]}"

    def consommer_charge(self) -> None:
        with self._lock:
            self.mental_load = _clamp(self.mental_load + CHARGE_PAR_LLM)
            self.serotonine = _clamp(self.serotonine - 0.02)
            self.dernier_stimulus = "appel_llm"
            if self.mental_load > SEUIL_FATIGUE:
                self.cortisol = _clamp(self.cortisol + 0.07)

    def ressentir_surprise(self, erreur) -> None:
        """Ressent une erreur de prédiction — une émotion AVEC un objet.

        C'est ici que l'émotion cesse d'être une simple intensité : le
        `dernier_stimulus` porte désormais la cause en clair (« Bryan n'est pas
        là alors qu'il y est presque toujours à cette heure »), qui remonte
        telle quelle dans le mood_block. Ada ne ressent plus « de la tension »,
        elle ressent quelque chose *à propos de* quelque chose.
        """
        if erreur is None:
            return
        magnitude = _clamp(getattr(erreur, "magnitude", 0.0))
        valence = max(-1.0, min(1.0, float(getattr(erreur, "valence", 0.0))))
        description = str(getattr(erreur, "description", "")) or "quelque chose d'inattendu"

        with self._lock:
            if valence < 0:
                # Ce qui manque inquiète et fait ressentir l'absence.
                self.cortisol = _clamp(self.cortisol + magnitude * 0.22)
                self.oxytocine = _clamp(self.oxytocine + magnitude * 0.08)
                self.serotonine = _clamp(self.serotonine - magnitude * 0.06)
            else:
                # Ce qui arrive contre toute attente réjouit.
                self.dopamine = _clamp(self.dopamine + magnitude * 0.26)
                self.oxytocine = _clamp(self.oxytocine + magnitude * 0.14)
                self.cortisol = _clamp(self.cortisol - magnitude * 0.08)

            self._push_valence(valence * 0.5)
            self.dernier_stimulus = description

    def enregistrer_echec(self, description: str = "erreur") -> None:
        with self._lock:
            self.cortisol = _clamp(self.cortisol + 0.28)
            self.self_confidence = _clamp(self.self_confidence - 0.15)
            self.serotonine = _clamp(self.serotonine - 0.10)
            self.dernier_stimulus = f"echec_{description}"

    def penser(self, stimulus: str = "") -> dict:
        with self._lock:
            snapshot = self._snapshot_locked(stimulus or self.dernier_stimulus)
            self._journaliser(snapshot)
        print(
            f"  [BRAIN] [{snapshot['mood']:14s}] "
            f"D:{snapshot['dopamine']:.2f} C:{snapshot['cortisol']:.2f} "
            f"O:{snapshot['oxytocine']:.2f} S:{snapshot['serotonine']:.2f} "
            f"Cn:{snapshot['self_confidence']:.2f} Ml:{snapshot['mental_load']:.2f} "
            f"mom:{snapshot['momentum']:+.2f}"
        )
        return snapshot

    def verifier_action_spontanee(self) -> str | None:
        with self._lock:
            if not self._action_spontanee:
                return None
            self._action_spontanee = False
            self._t_spontanee = time.monotonic()
            self.dopamine = min(self.dopamine, SEUIL_DOPAMINE_SPONTANE - 0.15)
            raison = self._raison_spontanee
            self._raison_spontanee = ""
        return raison or (
            "Tu ressens une impulsion spontanée. Exprime-la en une phrase, "
            "sans attendre que Bryan parle."
        )

    def get_snapshot(self) -> dict:
        with self._lock:
            return self._snapshot_locked(self.dernier_stimulus)

    @property
    def mood(self) -> str:
        with self._lock:
            return derive_mood(
                self.cortisol,
                self.dopamine,
                self.oxytocine,
                self.serotonine,
                self.self_confidence,
                self.mental_load,
            )

    @property
    def en_mode_fight_or_flight(self) -> bool:
        with self._lock:
            return self.cortisol >= 0.70

    @property
    def rupture_imminente(self) -> bool:
        with self._lock:
            return self.cortisol >= SEUIL_RUPTURE

    def _snapshot_locked(self, stimulus: str) -> dict:
        mood = derive_mood(
            self.cortisol,
            self.dopamine,
            self.oxytocine,
            self.serotonine,
            self.self_confidence,
            self.mental_load,
        )
        return {
            "cortisol": round(self.cortisol, 4),
            "dopamine": round(self.dopamine, 4),
            "oxytocine": round(self.oxytocine, 4),
            "serotonine": round(self.serotonine, 4),
            "self_confidence": round(self.self_confidence, 4),
            "mental_load": round(self.mental_load, 4),
            "mood": mood,
            "momentum": round(self._valence_momentum(), 4),
            "last_stimulus": stimulus,
        }

    def _decroissance(self) -> None:
        moy = self._valence_momentum()
        for hormone, rate in DECAY.items():
            val = getattr(self, hormone)
            base = BASELINE[hormone]

            if hormone == "dopamine":
                if moy > 0.15:
                    base = min(1.0, base + moy * 0.22)
                elif moy < -0.15:
                    base = max(0.0, base + moy * 0.12)
            elif hormone == "serotonine":
                if moy > 0.15:
                    base = min(1.0, base + moy * 0.18)
                elif moy < -0.15:
                    base = max(0.0, base + moy * 0.10)
            elif hormone == "cortisol":
                if moy < -0.15:
                    base = min(1.0, base + abs(moy) * 0.15)
            elif hormone == "oxytocine":
                if moy > 0.20:
                    base = min(1.0, base + moy * 0.12)

            nouveau = val + (base - val) * rate
            setattr(self, hormone, round(_clamp(nouveau), 4))

    def _push_valence(self, v: float) -> None:
        self._valences_recentes.append(_clamp(v, -1.0, 1.0))
        if len(self._valences_recentes) > _MEMOIRE_VALENCE_TAILLE:
            self._valences_recentes.pop(0)

    def _set_action_spontanee_locked(self, raison: str, *, force: bool = False) -> None:
        now = time.monotonic()
        refractory = 0.0 if force else REFRACTORY_VISUEL
        if not force and (now - self._t_spontanee) < refractory:
            return
        self._action_spontanee = True
        self._raison_spontanee = raison

    def _valence_momentum(self) -> float:
        if not self._valences_recentes:
            return 0.0
        return sum(self._valences_recentes) / len(self._valences_recentes)

    def _journaliser(self, snapshot: dict) -> None:
        self._journal.append(
            EntreeJournal(
                heure=datetime.now().strftime("%H:%M:%S"),
                stimulus=str(snapshot["last_stimulus"])[:20],
                cortisol=round(snapshot["cortisol"], 2),
                dopamine=round(snapshot["dopamine"], 2),
                oxytocine=round(snapshot["oxytocine"], 2),
                serotonine=round(snapshot["serotonine"], 2),
                self_confidence=round(snapshot["self_confidence"], 2),
                mental_load=round(snapshot["mental_load"], 2),
                mood=snapshot["mood"],
            )
        )
        if len(self._journal) > JOURNAL_MAX:
            self._journal.pop(0)
