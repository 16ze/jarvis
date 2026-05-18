"""AttentionField — couche thalamique v3.

Six neurones AdaptiveLIF spécialisés par canal (vision_object, vision_scene,
face_motion, gesture, audio_user, text) avec une inhibition latérale soft : un spike
sur un canal soustrait une fraction du potentiel des autres canaux à la
tick suivante (pour éviter les doublons multi-canaux sur un même événement).
"""
from __future__ import annotations

import threading
import time

from brain.calibration import env_float
from brain.v3.neurons import AdaptiveLIF
from brain.v3.types import ModulationVector, Stimulus


class AttentionField:
    """Champ d'attention v3 avec inhibition latérale."""

    def __init__(self) -> None:
        # Seuil de spike LIF par canal. Bas = neurone facile à déclencher
        # (utile pour les événements one-shot type face/gesture/objet).
        # Haut = il faut une accumulation temporelle (vision_scene, audio, texte).
        self._neurons: dict[str, AdaptiveLIF] = {
            "vision_object": AdaptiveLIF(
                "vision_object",
                seuil_base=env_float("BRAIN_V3_SEUIL_VISION_OBJECT", 0.50),
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_VISION_OBJECT", 2.0),
                ahp_amplitude=env_float("BRAIN_V3_AHP_AMPLITUDE", 0.15),
                ahp_decay=env_float("BRAIN_V3_AHP_DECAY", 0.92),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
                threshold_min=env_float("BRAIN_V3_THRESHOLD_MIN", 0.4),
                threshold_max=env_float("BRAIN_V3_THRESHOLD_MAX", 2.0),
            ),
            "vision_scene": AdaptiveLIF(
                "vision_scene",
                seuil_base=env_float("BRAIN_V3_SEUIL_VISION_SCENE", 0.85),
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_VISION_SCENE", 8.0),
                ahp_amplitude=env_float("BRAIN_V3_AHP_AMPLITUDE", 0.15),
                ahp_decay=env_float("BRAIN_V3_AHP_DECAY", 0.92),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
                threshold_min=env_float("BRAIN_V3_THRESHOLD_MIN", 0.4),
                threshold_max=env_float("BRAIN_V3_THRESHOLD_MAX", 2.0),
            ),
            "face_motion": AdaptiveLIF(
                "face_motion",
                seuil_base=env_float("BRAIN_V3_SEUIL_FACE_MOTION", 0.45),
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_FACE_MOTION", 1.0),
                ahp_amplitude=env_float("BRAIN_V3_AHP_AMPLITUDE", 0.15),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
            ),
            "gesture": AdaptiveLIF(
                "gesture",
                seuil_base=env_float("BRAIN_V3_SEUIL_GESTURE", 0.45),
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_GESTURE", 1.2),
                ahp_amplitude=env_float("BRAIN_V3_AHP_AMPLITUDE", 0.15),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
            ),
            "audio_user": AdaptiveLIF(
                "audio_user",
                seuil_base=env_float("BRAIN_V3_SEUIL_AUDIO", 0.80),
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_AUDIO", 0.5),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
            ),
            "text": AdaptiveLIF(
                "text",
                seuil_base=env_float("BRAIN_V3_SEUIL_TEXT", 0.80),
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_TEXT", 0.3),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
            ),
        }
        self._inhibition_strength = env_float("BRAIN_V3_INHIBITION_STRENGTH", 0.3)
        self._habituation_gain = env_float("BRAIN_V3_HABITUATION_GAIN", 0.70)
        self._lock = threading.Lock()
        self._last_winner: str | None = None
        self._last_winner_ts: float = 0.0

    def tick(
        self,
        stimulus: Stimulus,
        modulation: ModulationVector,
        habituation,
    ) -> bool:
        """Excite le neurone correspondant au canal, retourne True si spike."""
        neuron = self._neurons.get(stimulus.channel)
        if neuron is None:
            return False

        familiarity = habituation.familiarity(stimulus.canonical_id)
        effective_intensity = stimulus.intensity * (
            1.0 - familiarity * self._habituation_gain
        )

        with self._lock:
            inhib = 0.0
            if (
                self._last_winner is not None
                and self._last_winner != stimulus.channel
                and time.monotonic() - self._last_winner_ts < 1.0
            ):
                inhib = self._inhibition_strength

        adjusted = max(0.0, effective_intensity - inhib)
        spiked = neuron.exciter(adjusted, modulation=modulation.threshold_gain)

        if spiked:
            with self._lock:
                self._last_winner = stimulus.channel
                self._last_winner_ts = time.monotonic()
        return spiked

    def get_state(self) -> dict:
        """Snapshot debug : potentiels et seuils courants."""
        return {
            name: {
                "potentiel": neuron.potentiel,
                "seuil_courant": neuron.seuil_courant,
                "en_refractaire": neuron.en_refractaire,
            }
            for name, neuron in self._neurons.items()
        }
