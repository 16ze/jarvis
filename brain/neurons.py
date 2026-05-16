"""
NeuroneLIF — Leaky Integrate-and-Fire neuron, thread-safe.

À chaque appel exciter(intensite) :
  1. Période réfractaire : sourd post-spike
  2. Fuite membranaire : potentiel *= (1 - fuite), clamp >= repos
  3. Intégration : potentiel = min(potentiel + intensite, seuil * 2)
  4. Test de seuil : si potentiel >= seuil → reset, return True (SPIKE)
"""

import threading
import time
from dataclasses import dataclass, field


@dataclass
class NeuroneLIF:
    nom: str
    seuil: float = 1.0
    fuite: float = 0.18
    potentiel_repos: float = 0.0
    periode_refractaire: float = 0.3

    _potentiel: float = field(default=0.0, init=False, repr=False)
    _t_dernier_spike: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, init=False, repr=False
    )

    def exciter(self, intensite: float) -> bool:
        with self._lock:
            now = time.monotonic()

            if now - self._t_dernier_spike < self.periode_refractaire:
                return False

            self._potentiel *= (1.0 - self.fuite)
            if self._potentiel < self.potentiel_repos:
                self._potentiel = self.potentiel_repos

            self._potentiel = min(self._potentiel + intensite, self.seuil * 2)

            if self._potentiel >= self.seuil:
                self._potentiel = self.potentiel_repos
                self._t_dernier_spike = now
                return True

            return False

    @property
    def potentiel(self) -> float:
        with self._lock:
            return round(self._potentiel, 3)

    @property
    def en_refractaire(self) -> bool:
        with self._lock:
            return (time.monotonic() - self._t_dernier_spike) < self.periode_refractaire

    def __str__(self) -> str:
        ratio = max(0.0, min(1.0, self.potentiel / self.seuil))
        barre = int(ratio * 10)
        return f"{self.nom:12s} [{'█' * barre}{'░' * (10 - barre)}] {self.potentiel:.3f}V"
