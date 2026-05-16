"""
ReseauAttention — réseau d'attention thalamique à 2 couches.

Couche 1 (sensorielle) : vision, mouvement, audition, textuel.
Couche 2 (intégrateur) : thalamus (longue période réfractaire = anti-spam).

Ce module NE déclenche RIEN dans Ada (pas de réveil LLM). C'est un
observateur : ses spikes sont consommés par limbic via le brain_manager.
"""

from enum import Enum

from brain.neurons import NeuroneLIF


class EtatEveil(Enum):
    SOMMEIL = "😴 SOMMEIL"
    ALERTE  = "👁️  ALERTE"
    EVEIL   = "⚡ ÉVEIL"


class ReseauAttention:
    def __init__(self) -> None:
        self.n_vision    = NeuroneLIF("vision",    seuil=0.65, fuite=0.12, periode_refractaire=0.3)
        self.n_mouvement = NeuroneLIF("mouvement", seuil=0.45, fuite=0.22, periode_refractaire=0.3)
        self.n_audition  = NeuroneLIF("audition",  seuil=0.55, fuite=0.15, periode_refractaire=0.3)
        self.n_textuel   = NeuroneLIF("textuel",   seuil=0.55, fuite=0.18, periode_refractaire=0.5)
        self.n_thalamus  = NeuroneLIF("thalamus",  seuil=1.0,  fuite=0.07, periode_refractaire=25.0)
        self._etat = EtatEveil.SOMMEIL

    def tick_visual(self, presence: float, mouvement: float) -> bool:
        spike_v = self.n_vision.exciter(presence * 0.75)
        spike_m = self.n_mouvement.exciter(mouvement * 1.8)
        if spike_v or spike_m:
            spike_t = self.n_thalamus.exciter(presence * 0.5 + mouvement * 0.4)
        else:
            self.n_thalamus.exciter(0.0)
            spike_t = False
        self._etat = self._calculer_etat(spike_t)
        return spike_t

    def tick_audio(self, energie: float) -> bool:
        spike_a = self.n_audition.exciter(energie)
        spike_t = False
        if spike_a:
            spike_t = self.n_thalamus.exciter(energie * 1.3)
        self._etat = self._calculer_etat(spike_t)
        return spike_t

    def tick_text(self, valence_abs: float) -> bool:
        spike_x = self.n_textuel.exciter(valence_abs * 1.2)
        spike_t = False
        if spike_x:
            spike_t = self.n_thalamus.exciter(valence_abs * 0.8)
        self._etat = self._calculer_etat(spike_t)
        return spike_t

    @property
    def etat(self) -> EtatEveil:
        return self._etat

    def _calculer_etat(self, spike: bool) -> EtatEveil:
        if spike:
            return EtatEveil.EVEIL
        ratio = self.n_thalamus.potentiel / self.n_thalamus.seuil
        if ratio > 0.25:
            return EtatEveil.ALERTE
        return EtatEveil.SOMMEIL

    def afficher_potentiels(self) -> None:
        print(
            f"\n  ┌─ Réseau Neuronal ─────────────────────┐\n"
            f"  │ {self.n_vision}\n"
            f"  │ {self.n_mouvement}\n"
            f"  │ {self.n_audition}\n"
            f"  │ {self.n_textuel}\n"
            f"  │ {self.n_thalamus}\n"
            f"  │ État : {self._etat.value}\n"
            f"  └────────────────────────────────────────┘"
        )
