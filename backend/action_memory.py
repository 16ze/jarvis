"""
action_memory — Ada ne refait plus deux fois la même erreur.

Observé en conditions réelles : pour fermer une application, Ada a tenté le
clic droit sur le Dock, échoué, puis recommencé exactement pareil. Rien dans le
système n'enregistrait « cette approche ne marche pas ». Chaque tentative
repartait de zéro, avec la même idée et le même échec.

Ce module donne à la couche d'exécution une mémoire procédurale : pour un TYPE
de tâche donné (« fermer une app », « écrire dans une app »), il retient quelles
APPROCHES ont réussi et lesquelles ont échoué. Ces statistiques sont ensuite
injectées dans le prompt du planificateur, qui cesse de proposer ce qui rate.

C'est la forme la plus utile du conditionnement associatif : Ada n'apprend pas
seulement à ressentir, elle apprend à FAIRE.

Module pur : aucune dépendance à Ada, aucune exception ne remonte.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

# Nombre d'observations avant de considérer un verdict comme fiable.
MIN_OBSERVATIONS = int(os.getenv("ACTION_MEMORY_MIN_OBS", "3"))
# Taux d'échec au-delà duquel une approche est déconseillée.
FAILURE_THRESHOLD = float(os.getenv("ACTION_MEMORY_FAILURE_THRESHOLD", "0.7"))
# Nombre maximum de signatures suivies (éviction des plus anciennes).
MAX_SIGNATURES = int(os.getenv("ACTION_MEMORY_MAX_SIGNATURES", "200"))

STATE_VERSION = 1

# Verbes ramenés à une intention canonique : « ferme », « quitte » et « éteins »
# décrivent la même chose et doivent partager le même apprentissage.
_VERBES = {
    "ferme": "fermer", "fermer": "fermer", "quitte": "fermer", "quitter": "fermer",
    "éteins": "fermer", "eteins": "fermer", "close": "fermer", "quit": "fermer",
    "ouvre": "ouvrir", "ouvrir": "ouvrir", "lance": "ouvrir", "lancer": "ouvrir",
    "démarre": "ouvrir", "demarre": "ouvrir", "open": "ouvrir", "start": "ouvrir",
    "écris": "ecrire", "ecris": "ecrire", "écrire": "ecrire", "rédige": "ecrire",
    "tape": "ecrire", "saisis": "ecrire", "colle": "ecrire",
    "envoie": "envoyer", "envoyer": "envoyer",
    "appelle": "appeler", "appeler": "appeler", "téléphone": "appeler",
    "cherche": "chercher", "recherche": "chercher", "trouve": "chercher",
    "clique": "cliquer", "clic": "cliquer",
    "règle": "regler", "regle": "regler", "mets": "regler",
}


def signature(task: str) -> str:
    """Ramène une demande à son TYPE, pour généraliser d'une fois sur l'autre.

    « ferme les Réglages Système » et « quitte Safari » partagent la signature
    « fermer » : ce qui a échoué pour l'une renseigne sur l'autre.
    """
    mots = re.findall(r"[a-zà-öø-ÿ']+", (task or "").lower())
    for mot in mots:
        canonique = _VERBES.get(mot.strip("'"))
        if canonique:
            return canonique
    return "autre"


class ActionMemory:
    """Mémoire procédurale : quelles approches marchent, lesquelles ratent."""

    def __init__(self) -> None:
        # {signature: {approche: [succès, échecs, dernier_ts]}}
        self._stats: dict[str, dict[str, list]] = {}
        self._lock = threading.Lock()

    # ── Enregistrement ────────────────────────────────────────────────────────

    def record(self, task: str, approach: str, success: bool,
               now: float | None = None) -> None:
        """Enregistre l'issue d'une approche pour un type de tâche."""
        approach = (approach or "").strip()
        if not approach:
            return
        now = time.time() if now is None else now
        sig = signature(task)

        with self._lock:
            if sig not in self._stats and len(self._stats) >= MAX_SIGNATURES:
                plus_ancienne = min(
                    self._stats,
                    key=lambda s: max((v[2] for v in self._stats[s].values()), default=0.0),
                )
                del self._stats[plus_ancienne]

            approches = self._stats.setdefault(sig, {})
            entree = approches.setdefault(approach, [0, 0, now])
            entree[0 if success else 1] += 1
            entree[2] = now

    def record_plan(self, task: str, actions: list[str], success: bool) -> None:
        """Enregistre l'issue globale d'un plan pour chacune de ses approches."""
        for action in dict.fromkeys(a for a in actions if a):
            self.record(task, action, success)

    # ── Exploitation ──────────────────────────────────────────────────────────

    def failing_approaches(self, task: str) -> list[str]:
        """Approches à éviter pour ce type de tâche (verdict fiable seulement)."""
        sig = signature(task)
        with self._lock:
            approches = dict(self._stats.get(sig, {}))
        a_eviter = []
        for approche, (succes, echecs, _) in approches.items():
            total = succes + echecs
            if total >= MIN_OBSERVATIONS and (echecs / total) >= FAILURE_THRESHOLD:
                a_eviter.append(approche)
        return sorted(a_eviter)

    def working_approaches(self, task: str) -> list[str]:
        """Approches qui ont fait leurs preuves pour ce type de tâche."""
        sig = signature(task)
        with self._lock:
            approches = dict(self._stats.get(sig, {}))
        qui_marchent = []
        for approche, (succes, echecs, _) in approches.items():
            total = succes + echecs
            if total >= MIN_OBSERVATIONS and (succes / total) > 0.5:
                qui_marchent.append(approche)
        return sorted(qui_marchent)

    def advice(self, task: str) -> str:
        """Conseil injectable dans le prompt du planificateur. '' si rien appris."""
        a_eviter = self.failing_approaches(task)
        qui_marchent = self.working_approaches(task)
        if not a_eviter and not qui_marchent:
            return ""

        lignes = ["EXPÉRIENCE ACQUISE SUR CE TYPE DE TÂCHE :"]
        if a_eviter:
            lignes.append(
                "- Ces approches ont déjà échoué ici, ne les reprends pas : "
                + ", ".join(a_eviter)
            )
        if qui_marchent:
            lignes.append(
                "- Ces approches ont fonctionné, privilégie-les : "
                + ", ".join(qui_marchent)
            )
        return "\n".join(lignes)

    def get_debug_state(self) -> dict:
        with self._lock:
            return {
                sig: {
                    approche: {"succès": v[0], "échecs": v[1]}
                    for approche, v in approches.items()
                }
                for sig, approches in self._stats.items()
            }

    # ── Persistance ───────────────────────────────────────────────────────────

    @staticmethod
    def enabled() -> bool:
        return os.getenv("ACTION_MEMORY_ENABLED", "true").strip().lower() in {
            "1", "true", "yes", "on"
        }

    @staticmethod
    def state_path() -> Path:
        custom = os.getenv("ACTION_MEMORY_PATH", "").strip()
        if custom:
            return Path(custom).expanduser()
        return Path(__file__).resolve().parent / "memory" / "action_memory.json"

    def save(self) -> bool:
        if not self.enabled():
            return False
        try:
            path = self.state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = {"version": STATE_VERSION, "saved_at": time.time(),
                           "stats": self._stats}
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(path)
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[ACTION_MEM] sauvegarde impossible : {exc}")
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
                self._stats = {
                    str(sig): {
                        str(a): [int(v[0]), int(v[1]), float(v[2])]
                        for a, v in approches.items()
                    }
                    for sig, approches in (data.get("stats") or {}).items()
                }
            total = sum(len(a) for a in self._stats.values())
            print(f"[ACTION_MEM] expérience rechargée ({total} approche(s) connues)")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[ACTION_MEM] chargement impossible : {exc}")
            return False


_INSTANCE: ActionMemory | None = None


def get_action_memory() -> ActionMemory:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = ActionMemory()
        _INSTANCE.load()
    return _INSTANCE
