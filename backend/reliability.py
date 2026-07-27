"""
reliability — la confiance cesse d'être une impression, elle devient un chiffre.

« Pouvoir tout lui confier sans le moindre souci » est l'objectif final du
projet. Or la confiance ne se code pas : elle s'accumule à mesure que les
tâches réussissent. Ce qu'on PEUT coder, c'est la rendre visible et honnête.

Ce module enregistre l'issue de chaque tâche exécutée et en tire un taux de
réussite réel, global et par catégorie. Trois conséquences :

1. Ada répond honnêtement quand on l'interroge sur elle-même (« je réussis
   47 tâches sur 52 en ce moment, mes échecs sont surtout sur le web »).
2. Les catégories fragiles sautent aux yeux — on sait quoi corriger ensuite,
   au lieu de deviner.
3. La progression devient mesurable dans le temps, donc démontrable.

Principe directeur : ne jamais embellir. Un compagnon qui surestime sa
fiabilité détruit exactement la confiance qu'il prétend construire.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path

MAX_HISTORIQUE = int(os.getenv("RELIABILITY_HISTORY", "500"))
# En dessous, un taux n'a pas de sens statistique et n'est pas annoncé.
MIN_POUR_TAUX = int(os.getenv("RELIABILITY_MIN_SAMPLES", "5"))
STATE_VERSION = 1


def _categoriser(tache: str, outil: str = "") -> str:
    """Range la tâche dans une famille, pour repérer les points faibles."""
    t = f"{outil} {tache}".lower()
    if any(k in t for k in ("browser", "web_search", "http", "site", "navigateur")):
        return "web"
    if any(k in t for k in ("fichier", "dossier", "mac_files", "corbeille", "renomme")):
        return "fichiers"
    if any(k in t for k in ("message", "mail", "appel", "sms", "telegram", "whatsapp")):
        return "communication"
    if any(k in t for k in ("réglages", "reglages", "volume", "luminosité", "fenêtre",
                            "capture", "bluetooth", "wifi")):
        return "système"
    if any(k in t for k in ("ouvre", "ferme", "app", "lance")):
        return "applications"
    if any(k in t for k in ("lumière", "lumiere", "tuya", "chromecast", "caméra")):
        return "domotique"
    if any(k in t for k in ("think_deeply", "explique", "question", "recherche")):
        return "réflexion"
    return "autre"


class ReliabilityTracker:
    """Mémoire honnête de ce qui réussit et de ce qui échoue."""

    def __init__(self) -> None:
        self._historique: deque = deque(maxlen=MAX_HISTORIQUE)
        self._lock = threading.Lock()

    # ── Enregistrement ────────────────────────────────────────────────────────

    def record(self, tache: str, succes: bool, outil: str = "",
               detail: str = "", now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._historique.append({
                "t": now,
                "ok": bool(succes),
                "cat": _categoriser(tache, outil),
                "tache": str(tache)[:120],
                "detail": str(detail)[:200],
            })

    # ── Lecture ───────────────────────────────────────────────────────────────

    def stats(self, depuis_sec: float | None = None) -> dict:
        with self._lock:
            entrees = list(self._historique)
        if depuis_sec is not None:
            limite = time.time() - depuis_sec
            entrees = [e for e in entrees if e["t"] >= limite]

        total = len(entrees)
        reussies = sum(1 for e in entrees if e["ok"])

        par_cat: dict[str, dict] = {}
        for e in entrees:
            c = par_cat.setdefault(e["cat"], {"total": 0, "ok": 0})
            c["total"] += 1
            c["ok"] += 1 if e["ok"] else 0
        for c in par_cat.values():
            c["taux"] = round(c["ok"] / c["total"], 3) if c["total"] else 0.0

        return {
            "total": total,
            "reussies": reussies,
            "echouees": total - reussies,
            "taux": round(reussies / total, 3) if total else None,
            "par_categorie": par_cat,
            "fiable": total >= MIN_POUR_TAUX,
        }

    def weakest_categories(self, minimum: int = 3) -> list[tuple[str, float]]:
        """Catégories les moins fiables — c'est là qu'il faut travailler."""
        s = self.stats()
        faibles = [
            (cat, infos["taux"])
            for cat, infos in s["par_categorie"].items()
            if infos["total"] >= minimum and infos["taux"] < 0.8
        ]
        return sorted(faibles, key=lambda x: x[1])

    def recent_failures(self, n: int = 5) -> list[dict]:
        with self._lock:
            echecs = [e for e in self._historique if not e["ok"]]
        return echecs[-n:]

    # ── Restitution parlée ────────────────────────────────────────────────────

    def to_speech(self) -> str:
        """Réponse honnête à « tu es fiable ? », « tu te débrouilles bien ? »."""
        s = self.stats()
        if not s["fiable"]:
            return ("Je n'ai pas encore assez d'historique pour te répondre "
                    "honnêtement — laisse-moi quelques tâches de plus.")

        pct = round(s["taux"] * 100)
        phrase = f"Sur mes {s['total']} dernières tâches, j'en ai réussi {s['reussies']}, soit {pct}%."

        faibles = self.weakest_categories()
        if faibles:
            noms = ", ".join(cat for cat, _ in faibles[:2])
            phrase += f" Là où je pèche encore : {noms}."
        elif pct >= 90:
            phrase += " Rien ne ressort comme point faible pour l'instant."
        return phrase

    def get_debug_state(self) -> dict:
        s = self.stats()
        return {
            "taux_global": s["taux"],
            "total": s["total"],
            "par_categorie": s["par_categorie"],
            "points_faibles": self.weakest_categories(),
        }

    # ── Persistance ───────────────────────────────────────────────────────────

    @staticmethod
    def enabled() -> bool:
        return os.getenv("RELIABILITY_ENABLED", "true").strip().lower() in {
            "1", "true", "yes", "on"
        }

    @staticmethod
    def state_path() -> Path:
        custom = os.getenv("RELIABILITY_PATH", "").strip()
        if custom:
            return Path(custom).expanduser()
        return Path(__file__).resolve().parent / "memory" / "reliability.json"

    def save(self) -> bool:
        if not self.enabled():
            return False
        try:
            path = self.state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = {"version": STATE_VERSION, "saved_at": time.time(),
                           "historique": list(self._historique)}
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[RELIABILITY] sauvegarde impossible : {exc}")
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
                self._historique = deque(data.get("historique", []), maxlen=MAX_HISTORIQUE)
            s = self.stats()
            if s["taux"] is not None:
                print(f"[RELIABILITY] historique rechargé : {s['total']} tâches, "
                      f"{round(s['taux']*100)}% de réussite")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[RELIABILITY] chargement impossible : {exc}")
            return False


_TRACKER: ReliabilityTracker | None = None


def get_tracker() -> ReliabilityTracker:
    global _TRACKER
    if _TRACKER is None:
        _TRACKER = ReliabilityTracker()
        _TRACKER.load()
    return _TRACKER


def record(tache: str, succes: bool, outil: str = "", detail: str = "") -> None:
    """Enregistre une issue. Ne lève jamais — le suivi ne doit rien casser."""
    try:
        tracker = get_tracker()
        tracker.record(tache, succes, outil, detail)
        # Sauvegarde peu fréquente : inutile d'écrire à chaque tâche.
        if len(tracker._historique) % 10 == 0:
            tracker.save()
    except Exception as exc:  # noqa: BLE001
        print(f"[RELIABILITY] enregistrement impossible : {exc}")
