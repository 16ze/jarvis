"""
machine_context — Ada sait ce que tu es en train de faire.

Jusqu'ici Ada voyait l'écran (des pixels) sans rien comprendre de la situation :
quelle application est active, quel document est ouvert, depuis combien de temps
tu travailles, si la batterie tient, si le disque sature.

Un bras droit ne demande pas « sur quoi travailles-tu ? » toutes les cinq
minutes : il regarde. Ce module rassemble ce contexte par des appels système
directs — aucun modèle, aucune capture d'écran, quelques dizaines de
millisecondes.

Deux usages :
  - Ada répond juste sans qu'on lui explique le contexte (« enregistre ça »
    → elle sait dans quelle app on est) ;
  - le contexte est injecté dans ses instructions, donc elle anticipe.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CACHE_SEC = 5.0  # le contexte change lentement : inutile de tout relire sans cesse


def _run(args: list[str], timeout: float = 6.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _osa(script: str, timeout: float = 6.0) -> str:
    r = _run(["osascript", "-e", script], timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip())
    return (r.stdout or "").strip()


@dataclass
class MachineContext:
    app_active: str = ""
    document: str = ""
    titre_fenetre: str = ""
    apps_ouvertes: list[str] = field(default_factory=list)
    batterie: str = ""
    disque: str = ""
    reseau: str = ""
    heure: str = ""

    def to_prompt(self) -> str:
        """Bloc injectable dans les instructions d'Ada — court et factuel."""
        lignes = []
        if self.app_active:
            ligne = f"Bryan est dans {self.app_active}"
            if self.document:
                ligne += f", sur « {self.document} »"
            lignes.append(ligne + ".")
        if self.apps_ouvertes:
            lignes.append("Applications ouvertes : " + ", ".join(self.apps_ouvertes[:8]) + ".")
        etat = [x for x in (self.batterie, self.disque, self.reseau) if x]
        if etat:
            lignes.append(" | ".join(etat))
        if not lignes:
            return ""
        return "\nCE QUE TU VOIS DE SA MACHINE :\n" + "\n".join(f"- {l}" for l in lignes) + "\n"

    def to_speech(self) -> str:
        """Réponse parlée à « qu'est-ce que je fais ? »."""
        morceaux = []
        if self.app_active:
            m = f"Tu es dans {self.app_active}"
            if self.document:
                m += f", sur {self.document}"
            morceaux.append(m)
        if self.apps_ouvertes:
            morceaux.append(f"{len(self.apps_ouvertes)} applications ouvertes")
        for x in (self.batterie, self.disque):
            if x:
                morceaux.append(x)
        return ". ".join(morceaux) + "." if morceaux else "Je n'arrive pas à lire l'état de la machine."


# ── Lecture des signaux ───────────────────────────────────────────────────────

def _app_et_fenetre() -> tuple[str, str]:
    """Application au premier plan et titre de sa fenêtre."""
    try:
        nom = _osa(
            'tell application "System Events" to get name of first '
            "application process whose frontmost is true"
        )
    except Exception:
        return "", ""
    titre = ""
    try:
        titre = _osa(
            f'tell application "System Events" to tell process "{nom}" '
            "to get title of front window"
        )
    except Exception:
        pass
    return nom, titre


def _document_depuis_titre(app: str, titre: str) -> str:
    """Extrait un nom de document exploitable du titre de fenêtre."""
    if not titre:
        return ""
    # Beaucoup d'apps intitulent leur fenêtre comme elles-mêmes : annoncer
    # « tu es dans Claude, sur Claude » n'apprend rien.
    if titre.strip().lower() == (app or "").strip().lower():
        return ""
    # Les navigateurs mettent le nom de la page : on le garde tel quel.
    if app in {"Safari", "Google Chrome", "Firefox", "Arc"}:
        return titre[:80]
    # Les éditeurs suffixent souvent « — Nom du projet » ou « (modifié) ».
    nettoye = re.split(r"\s+[—–|]\s+", titre)[0]
    nettoye = re.sub(r"\s*\((modifié|edited|modified)\)\s*$", "", nettoye, flags=re.I)
    return nettoye.strip()[:80]


def _apps_ouvertes() -> list[str]:
    try:
        brut = _osa(
            'tell application "System Events" to get name of every '
            "application process whose background only is false"
        )
        apps = [a.strip() for a in brut.split(",") if a.strip()]
        # Le Finder est toujours là : il n'apprend rien.
        return [a for a in apps if a not in {"Finder"}]
    except Exception:
        return []


def _batterie() -> str:
    try:
        sortie = _run(["pmset", "-g", "batt"]).stdout or ""
        m = re.search(r"(\d+)%.*?;\s*([^;]+);", sortie)
        if not m:
            return ""
        pct, etat = int(m.group(1)), m.group(2).strip().lower()
        # Attention : « discharging » CONTIENT « charging ». Tester la décharge
        # d'abord, sinon une batterie qui se vide est annoncée « en charge ».
        en_decharge = "discharging" in etat
        if not en_decharge and ("charging" in etat or "AC attached" in sortie):
            return f"batterie {pct}% (en charge)"
        if pct <= 20:
            return f"batterie faible : {pct}%"
        return f"batterie {pct}%"
    except Exception:
        return ""


def _disque() -> str:
    try:
        u = shutil.disk_usage(str(Path.home()))
        libre_go = u.free / (1024 ** 3)
        pct = u.used / u.total * 100
        if pct >= 90:
            return f"disque presque plein ({libre_go:.0f} Go libres)"
        return f"disque {pct:.0f}% utilisé"
    except Exception:
        return ""


def _reseau() -> str:
    try:
        r = _run(["ping", "-c", "1", "-W", "1200", "1.1.1.1"], timeout=4)
        return "" if r.returncode == 0 else "hors ligne"
    except Exception:
        return ""


# ── Façade ────────────────────────────────────────────────────────────────────

_CACHE: tuple[float, MachineContext] | None = None


def _lire_sync() -> MachineContext:
    app, titre = _app_et_fenetre()
    return MachineContext(
        app_active=app,
        titre_fenetre=titre,
        document=_document_depuis_titre(app, titre),
        apps_ouvertes=_apps_ouvertes(),
        batterie=_batterie(),
        disque=_disque(),
        reseau=_reseau(),
        heure=datetime.now().strftime("%H:%M"),
    )


async def get_context(force: bool = False) -> MachineContext:
    """Contexte machine, avec un cache court. Ne lève jamais."""
    global _CACHE
    import time

    maintenant = time.monotonic()
    if not force and _CACHE and (maintenant - _CACHE[0]) < CACHE_SEC:
        return _CACHE[1]
    try:
        contexte = await asyncio.to_thread(_lire_sync)
    except Exception as exc:  # noqa: BLE001
        print(f"[CONTEXT] lecture impossible : {exc}")
        return MachineContext()
    _CACHE = (maintenant, contexte)
    return contexte


async def prompt_block() -> str:
    """Bloc de contexte à injecter dans les instructions d'Ada."""
    try:
        return (await get_context()).to_prompt()
    except Exception:
        return ""


# ── Routage depuis une phrase ─────────────────────────────────────────────────

async def route(task: str) -> str | None:
    """Répond aux questions sur l'état de la machine. None si non concernée."""
    tl = (task or "").strip().lower()
    if not tl:
        return None

    if re.search(r"\bqu'?est-ce que je fais\b|\bsur quoi je (suis|travaille)\b|"
                 r"\bje fais quoi\b|\btu vois quoi\b|\bo[ùu] j'?en suis\b", tl):
        return (await get_context(force=True)).to_speech()

    if re.search(r"\bquelle? (app|application)\b.*\b(ouverte|active|devant)\b|"
                 r"\bje suis dans quoi\b", tl):
        c = await get_context(force=True)
        return f"Tu es dans {c.app_active}." + (f" Sur « {c.document} »." if c.document else "")

    if re.search(r"\bquelles? (apps?|applications?)\b.*\bouvertes?\b|"
                 r"\bqu'?est-ce qui (est|tourne) ouvert\b", tl):
        c = await get_context(force=True)
        if not c.apps_ouvertes:
            return "Je ne vois aucune application ouverte."
        return f"{len(c.apps_ouvertes)} ouvertes : " + ", ".join(c.apps_ouvertes[:10]) + "."

    # Fiabilité : Ada rend compte honnêtement de ses propres résultats.
    if re.search(r"\btu es fiable\b|\btu te débrouilles\b|\btu te debrouilles\b|"
                 r"\btes r[ée]sultats\b|\bton taux\b|\btu r[ée]ussis\b|"
                 r"\bcombien.*(r[ée]ussi|[ée]chou)|\btu progresses\b", tl):
        try:
            import reliability

            return reliability.get_tracker().to_speech()
        except Exception:
            return None

    if re.search(r"\bbatterie\b|\bautonomie\b|\bcombien de batterie\b", tl):
        c = await get_context(force=True)
        return c.batterie.capitalize() + "." if c.batterie else "Je ne lis pas l'état de la batterie."

    return None
