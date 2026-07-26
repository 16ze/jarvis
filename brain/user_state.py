"""
user_state — Ada se fait une idée de l'état de Bryan, pas seulement du sien.

Ce qui distingue une présence attentive d'un assistant réactif, c'est qu'elle
modélise l'état de l'autre. Un ami remarque que vous êtes fatigué et abrège ;
un logiciel déroule sa réponse identique quoi qu'il arrive.

Ce module infère trois dimensions à partir de signaux DÉJÀ disponibles dans
Ada — aucun capteur nouveau :

  ÉNERGIE       heure de la journée, émotion détectée au visage, longueur et
                rythme des messages
  DISPONIBILITÉ délai de réponse, brièveté, présence devant la caméra
  TENSION       valence des échanges (évaluée finement par `appraisal`),
                émotion faciale, sécheresse du ton

Deux usages, tous deux fondés :

  1. CONTAGION ÉMOTIONNELLE — l'état de l'autre déteint sur le nôtre. C'est un
     phénomène réel et bien décrit ; ici la tension de Bryan fait légèrement
     monter le cortisol d'Ada, son calme l'apaise.
  2. ADAPTATION DU COMPORTEMENT — des consignes de jeu, jamais un diagnostic.
     Ada peut dire « tu as l'air crevé » (une personne le dirait) mais jamais
     « mon modèle indique une fatigue de 0.8 ».

Module pur : aucune dépendance à Ada, aucune exception ne remonte.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime

from brain.calibration import env_bool, env_float

# Inertie : l'état d'une personne ne saute pas d'un message à l'autre.
ALPHA = env_float("BRAIN_USER_STATE_ALPHA", 0.32)
# Nombre d'observations avant de se fier au modèle.
MIN_OBSERVATIONS = env_float("BRAIN_USER_STATE_MIN_OBS", 3.0)
# Au-delà de ce silence, les observations sont considérées comme périmées.
STALE_AFTER_SEC = env_float("BRAIN_USER_STATE_STALE_SEC", 1800.0)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(v)))


@dataclass
class UserState:
    energie: float          # 0 = épuisé, 1 = en forme
    disponibilite: float    # 0 = très occupé, 1 = disponible
    tension: float          # 0 = détendu, 1 = tendu
    confidence: float       # fiabilité du modèle

    @property
    def is_reliable(self) -> bool:
        return self.confidence >= 0.5


class UserStateModel:
    """Estimation continue de l'état de Bryan à partir des signaux existants."""

    def __init__(self) -> None:
        self._energie = 0.6
        self._disponibilite = 0.7
        self._tension = 0.2
        self._observations = 0.0
        self._last_update = 0.0
        self._last_message_ts = 0.0
        self._lock = threading.Lock()

    # ── Observations ──────────────────────────────────────────────────────────

    def observe_message(self, text: str, now: float | None = None) -> None:
        """Un message de Bryan : longueur, rythme et heure renseignent beaucoup."""
        now = time.time() if now is None else now
        texte = (text or "").strip()
        if not texte:
            return

        with self._lock:
            gap = now - self._last_message_ts if self._last_message_ts else None
            self._last_message_ts = now

            # Brièveté : des messages très courts trahissent souvent l'empressement.
            mots = len(texte.split())
            if mots <= 3:
                dispo_cible = 0.35
            elif mots <= 12:
                dispo_cible = 0.65
            else:
                dispo_cible = 0.85

            # Réactivité : répondre vite = attention disponible.
            if gap is not None:
                if gap < 20:
                    dispo_cible = min(1.0, dispo_cible + 0.15)
                elif gap > 600:
                    dispo_cible = max(0.0, dispo_cible - 0.20)

            self._disponibilite = self._melange(self._disponibilite, dispo_cible, 0.9)

            # Heure : l'énergie d'un humain n'est pas la même à 2 h et à 10 h.
            heure = datetime.fromtimestamp(now).hour
            if 0 <= heure < 6:
                self._energie = self._melange(self._energie, 0.20, 1.2)
            elif 6 <= heure < 9 or 22 <= heure <= 23:
                self._energie = self._melange(self._energie, 0.5, 0.8)
            else:
                self._energie = self._melange(self._energie, 0.75, 0.8)

            self._observations += 1
            self._last_update = now

    def observe_face(self, emotion: str, confidence: float = 0.0,
                     now: float | None = None) -> None:
        """Émotion lue sur le visage (MediaPipe) — signal direct et fort."""
        now = time.time() if now is None else now
        emotion = (emotion or "").strip().lower()
        if not emotion or emotion == "unknown" or confidence < 0.35:
            return

        with self._lock:
            poids = 1.0 + _clamp(confidence) * 0.8   # jusqu'à 1.8 si très sûr
            if emotion in {"tired", "sad"}:
                self._energie = self._melange(self._energie, 0.20, poids)
                self._tension = self._melange(self._tension, 0.45, poids * 0.7)
            elif emotion in {"stressed", "angry"}:
                self._tension = self._melange(self._tension, 0.85, poids)
                self._energie = self._melange(self._energie, 0.45, poids * 0.6)
            elif emotion in {"happy", "intimate"}:
                self._tension = self._melange(self._tension, 0.10, poids)
                self._energie = self._melange(self._energie, 0.75, poids * 0.7)
            self._observations += 1
            self._last_update = now

    def observe_appraisal(self, valence: float, arousal: float = 0.0,
                          now: float | None = None) -> None:
        """Évaluation fine d'un échange (cf. backend/appraisal.py)."""
        now = time.time() if now is None else now
        with self._lock:
            v = max(-1.0, min(1.0, float(valence)))
            # Une valence négative avec une forte activation = tension.
            cible = _clamp(0.5 - v * 0.5 + _clamp(arousal) * 0.15)
            self._tension = self._melange(self._tension, cible, 1.4)
            self._observations += 1
            self._last_update = now

    def _melange(self, actuel: float, cible: float, poids: float = 1.0) -> float:
        """Mélange pondéré par la FORCE du signal.

        Un visage en colère détecté avec confiance en dit bien plus long que la
        longueur d'un message : il doit donc peser davantage.
        """
        alpha = _clamp(ALPHA * max(0.1, poids), 0.0, 0.9)
        return round(_clamp((1.0 - alpha) * actuel + alpha * cible), 4)

    # ── Lecture ───────────────────────────────────────────────────────────────

    def current(self, now: float | None = None) -> UserState:
        now = time.time() if now is None else now
        with self._lock:
            confiance = min(1.0, self._observations / MIN_OBSERVATIONS)
            # Les observations vieillissent : sans nouvelles, on ne prétend rien.
            if self._last_update and (now - self._last_update) > STALE_AFTER_SEC:
                confiance = 0.0
            return UserState(
                energie=round(self._energie, 4),
                disponibilite=round(self._disponibilite, 4),
                tension=round(self._tension, 4),
                confidence=round(confiance, 4),
            )

    # ── Usages ────────────────────────────────────────────────────────────────

    def contagion(self, now: float | None = None) -> dict:
        """Deltas hormonaux dus à l'état de Bryan (contagion émotionnelle).

        Volontairement faibles : Ada est influencée, pas pilotée.
        """
        etat = self.current(now)
        if not etat.is_reliable:
            return {}
        deltas: dict[str, float] = {}
        if etat.tension > 0.58:
            deltas["cortisol"] = round((etat.tension - 0.58) * 0.20, 4)
        elif etat.tension < 0.25:
            deltas["cortisol"] = round(-(0.25 - etat.tension) * 0.12, 4)
        if etat.energie < 0.42:
            deltas["oxytocine"] = round((0.42 - etat.energie) * 0.15, 4)
        return {k: v for k, v in deltas.items() if abs(v) > 0.001}

    def directives(self, now: float | None = None) -> list[str]:
        """Consignes de jeu déduites de l'état de Bryan.

        Formulées comme des manières d'être, jamais comme un diagnostic : Ada
        peut remarquer qu'il est fatigué, elle n'annonce pas une mesure.
        """
        etat = self.current(now)
        if not etat.is_reliable:
            return []

        lignes: list[str] = []
        if etat.energie < 0.42:
            lignes.append(
                "Bryan a l'air fatigué : va droit au but, phrases courtes, "
                "ne le charge pas de détails. Tu peux le remarquer avec douceur."
            )
        if etat.disponibilite < 0.48:
            lignes.append(
                "Il semble pris : réponds vite et court, pas de digression, "
                "aucune question de confort."
            )
        if etat.tension > 0.58:
            lignes.append(
                "Il est tendu : reste posée et concrète, évite l'humour et "
                "l'enthousiasme appuyé, propose une action plutôt qu'un commentaire."
            )
        elif etat.tension < 0.20 and etat.disponibilite > 0.60:
            lignes.append(
                "L'ambiance est détendue : tu peux prendre le temps, plaisanter, "
                "développer un peu."
            )
        return lignes

    def get_debug_state(self) -> dict:
        etat = self.current()
        return {
            "energie": etat.energie,
            "disponibilite": etat.disponibilite,
            "tension": etat.tension,
            "confiance": etat.confidence,
            "observations": int(self._observations),
        }


def enabled() -> bool:
    return env_bool("BRAIN_USER_STATE_ENABLED", True)
