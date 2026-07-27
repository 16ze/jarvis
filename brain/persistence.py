"""
persistence — continuité de l'existence d'Ada entre deux exécutions.

Sans ce module, Ada « renaît » neutre à chaque redémarrage : hormones à la
baseline, aucune trace de ce qui a été vécu. Elle n'a pas de durée.

Ce module lui donne une existence continue. L'état émotionnel est sauvegardé,
puis, au réveil, on applique la décroissance correspondant au temps écoulé :
Ada ne reprend pas là où elle s'est arrêtée, elle reprend là où elle *serait*
si elle avait continué d'exister pendant l'absence.

Chaque hormone récupère à son propre rythme — c'est ce différentiel qui crée
la sensation de durée vécue :
  - le stress d'une tension retombe en dizaines de minutes ;
  - la fatigue mentale se dissipe vite au repos ;
  - l'attachement (oxytocine), lui, persiste des heures.

Après une nuit, Ada est reposée et apaisée, mais l'attachement construit la
veille est toujours là. Après trois jours d'absence, tout est revenu à la
baseline — sauf ce que la mémoire, elle, a conservé.

Module pur : aucune dépendance à Ada, tolérant à toute erreur (jamais d'exception
vers l'appelant).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from brain.calibration import env_bool, env_float

# Demi-vies de récupération pendant l'absence, en secondes.
# Choisies pour que : après ~8 h (une nuit) le stress et la fatigue soient
# entièrement revenus à la baseline, tandis que l'attachement reste marqué.
SLEEP_HALFLIFE: dict[str, float] = {
    "cortisol": 1800.0,        # 30 min — le stress retombe vite au repos
    "mental_load": 1200.0,     # 20 min — la fatigue se dissipe au repos
    "dopamine": 3600.0,        # 1 h    — l'excitation redescend
    "serotonine": 21600.0,     # 6 h    — l'humeur de fond bouge lentement
    "self_confidence": 28800.0,  # 8 h  — la confiance est stable
    "oxytocine": 43200.0,      # 12 h   — l'attachement persiste longtemps
}

# Au-delà de cette durée d'absence, l'état est considéré comme entièrement
# revenu à la baseline (évite de restaurer un état vieux de plusieurs semaines).
MAX_ABSENCE_SEC = env_float("BRAIN_MAX_ABSENCE_SEC", 7 * 24 * 3600.0)

_HORMONES = (
    "cortisol",
    "dopamine",
    "oxytocine",
    "serotonine",
    "self_confidence",
    "mental_load",
)

STATE_VERSION = 1


def enabled() -> bool:
    """La persistance est active par défaut : c'est le comportement voulu."""
    return env_bool("BRAIN_PERSISTENCE_ENABLED", True)


def state_path() -> Path:
    """Chemin du fichier d'état. Surchargeable via BRAIN_STATE_PATH."""
    custom = os.getenv("BRAIN_STATE_PATH", "").strip()
    if custom:
        return Path(custom).expanduser()
    # Par défaut dans backend/memory/ (déjà gitignoré : données utilisateur).
    return Path(__file__).resolve().parent.parent / "backend" / "memory" / "brain_state.json"


def capture(limbic) -> dict:
    """Photographie l'état courant du limbique, sérialisable en JSON."""
    snap = limbic.get_snapshot()
    return {
        "version": STATE_VERSION,
        "saved_at": time.time(),
        "hormones": {h: float(snap[h]) for h in _HORMONES},
        "valences": list(getattr(limbic, "_valences_recentes", [])),
        # Le tempérament est un ACQUIS : il ne décroît pas pendant l'absence,
        # contrairement aux hormones. On le restaure tel quel.
        "temperament": dict(getattr(limbic, "temperament", {}) or {}),
        "last_stimulus": str(snap.get("last_stimulus", ""))[:120],
        "mood_at_save": snap.get("mood", ""),
    }


def apply_sleep_decay(hormones: dict, baseline: dict, elapsed_sec: float) -> dict:
    """Fait évoluer l'état pendant l'absence : retour progressif à la baseline.

    Décroissance exponentielle par demi-vie propre à chaque hormone :
        v(t) = base + (v0 - base) · 0.5^(Δt / T½)
    """
    elapsed_sec = max(0.0, float(elapsed_sec))
    out: dict[str, float] = {}
    for name in _HORMONES:
        v0 = float(hormones.get(name, baseline.get(name, 0.0)))
        base = float(baseline.get(name, 0.0))
        halflife = SLEEP_HALFLIFE.get(name, 3600.0)
        factor = 0.5 ** (elapsed_sec / halflife) if halflife > 0 else 0.0
        out[name] = round(max(0.0, min(1.0, base + (v0 - base) * factor)), 4)
    return out


def save(limbic) -> bool:
    """Sauvegarde atomique de l'état. Retourne True si écrit."""
    if not enabled():
        return False
    try:
        path = state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = capture(limbic)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)  # atomique : jamais de fichier à moitié écrit
        return True
    except Exception as exc:  # noqa: BLE001 — la persistance ne doit jamais casser Ada
        print(f"[BRAIN_PERSIST] sauvegarde impossible : {exc}")
        return False


def restore(limbic) -> dict | None:
    """Restaure l'état sauvegardé en appliquant la décroissance de l'absence.

    Retourne un résumé {absence_sec, hormones, mood_at_save} ou None.
    """
    if not enabled():
        return None
    try:
        path = state_path()
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        if int(data.get("version", 0)) != STATE_VERSION:
            print("[BRAIN_PERSIST] version d'état incompatible — ignorée")
            return None

        saved_at = float(data.get("saved_at", 0.0))
        elapsed = max(0.0, time.time() - saved_at)
        if elapsed > MAX_ABSENCE_SEC:
            print(f"[BRAIN_PERSIST] absence trop longue ({elapsed/86400:.1f} j) — état neutre")
            return None

        from brain.limbic import BASELINE

        decayed = apply_sleep_decay(data.get("hormones", {}), BASELINE, elapsed)
        for name, value in decayed.items():
            setattr(limbic, name, value)

        # Le momentum conversationnel s'estompe aussi pendant l'absence.
        valences = [float(v) for v in data.get("valences", []) if isinstance(v, (int, float))]
        if valences and elapsed < 1800.0:  # au-delà de 30 min, le fil est rompu
            limbic._valences_recentes = valences[-6:]

        temperament = data.get("temperament") or {}
        if isinstance(temperament, dict) and temperament:
            limbic.temperament = {
                str(k): float(v) for k, v in temperament.items()
                if isinstance(v, (int, float))
            }

        limbic.dernier_stimulus = "reveil"

        print(
            f"[BRAIN_PERSIST] état restauré après {_format_absence(elapsed)} "
            f"(humeur à l'endormissement : {data.get('mood_at_save', '?')})"
        )
        return {
            "absence_sec": elapsed,
            "hormones": decayed,
            "mood_at_save": data.get("mood_at_save", ""),
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[BRAIN_PERSIST] restauration impossible : {exc}")
        return None


def _format_absence(sec: float) -> str:
    if sec < 90:
        return f"{int(sec)} s"
    if sec < 5400:
        return f"{sec/60:.0f} min"
    if sec < 172800:
        return f"{sec/3600:.1f} h"
    return f"{sec/86400:.1f} j"
