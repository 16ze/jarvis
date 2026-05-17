"""Neurones adaptatifs pour Brain v3."""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time


@dataclass
class AdaptiveLIF:
    """Leaky integrate-and-fire avec seuil adaptatif et AHP."""

    nom: str
    seuil_base: float = 1.0
    fuite: float = 0.18
    potentiel_repos: float = 0.0
    periode_refractaire: float = 0.3
    ahp_amplitude: float = 0.15
    ahp_decay: float = 0.92
    threshold_drift_rate: float = 0.005
    threshold_min: float = 0.4
    threshold_max: float = 2.0
    _potentiel: float = field(default=0.0, init=False, repr=False)
    _ahp: float = field(default=0.0, init=False, repr=False)
    _seuil_courant: float | None = field(default=None, init=False, repr=False)
    _t_dernier_spike: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self._seuil_courant is None:
            self._seuil_courant = self.seuil_base

    def exciter(self, intensite: float, modulation: float = 1.0) -> bool:
        """Excite le neurone et retourne True si un spike est émis."""
        with self._lock:
            now = time.monotonic()
            if now - self._t_dernier_spike < self.periode_refractaire:
                return False

            self._potentiel *= 1.0 - self.fuite
            self._potentiel = max(self._potentiel - self._ahp, self.potentiel_repos)
            self._ahp *= self.ahp_decay

            seuil_effectif = self._seuil_courant * max(0.1, modulation)
            self._potentiel = min(
                self._potentiel + float(intensite),
                seuil_effectif * 2.0,
            )

            if self._potentiel >= seuil_effectif:
                self._potentiel = self.potentiel_repos
                self._ahp = self.ahp_amplitude
                self._t_dernier_spike = now
                self._adapt_threshold(spiked=True)
                return True

            self._adapt_threshold(spiked=False)
            return False

    def _adapt_threshold(self, spiked: bool) -> None:
        if spiked:
            self._seuil_courant = min(
                self._seuil_courant + self.threshold_drift_rate * 10.0,
                self.threshold_max,
            )
            return

        drift = (self.seuil_base - self._seuil_courant) * self.threshold_drift_rate
        self._seuil_courant = max(self._seuil_courant + drift, self.threshold_min)

    @property
    def potentiel(self) -> float:
        with self._lock:
            return round(self._potentiel, 4)

    @property
    def seuil_courant(self) -> float:
        with self._lock:
            return round(self._seuil_courant, 4)

    @property
    def en_refractaire(self) -> bool:
        with self._lock:
            return time.monotonic() - self._t_dernier_spike < self.periode_refractaire
