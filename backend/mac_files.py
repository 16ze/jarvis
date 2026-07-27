"""
mac_files — Ada agit sur tes fichiers, nativement.

C'était le plus gros trou de la couverture : chercher, ouvrir, ranger, renommer
un fichier passait par la boucle vision (capture d'écran → modèle → clics), donc
lentement et sans garantie. Or c'est l'activité la plus banale d'un ordinateur.

Tout passe ici par le système : `mdfind` pour l'index Spotlight (l'INDEX, pas
l'interface Spotlight qui reste interdite), `open` pour l'ouverture, AppleScript
pour le Finder.

RÈGLE DE SÛRETÉ ABSOLUE : rien n'est jamais supprimé définitivement. Toute
« suppression » met à la corbeille, d'où l'on peut revenir. Un assistant qui se
trompe de fichier ne doit jamais causer de perte irréparable.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

MAX_RESULTATS = 15
# Dossiers où l'on cherche en priorité : le travail vit là.
DOSSIERS_USUELS = ("Desktop", "Documents", "Downloads")


def _run(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _osa(script: str, timeout: float = 15.0) -> str:
    r = _run(["osascript", "-e", script], timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip())
    return (r.stdout or "").strip()


def _lisible(chemin: Path) -> str:
    """Chemin raccourci pour être dit à voix haute."""
    try:
        return "~/" + str(chemin.relative_to(Path.home()))
    except ValueError:
        return str(chemin)


def _taille(octets: float) -> str:
    for unite in ("o", "Ko", "Mo", "Go", "To"):
        if octets < 1024:
            return f"{octets:.0f} {unite}"
        octets /= 1024
    return f"{octets:.0f} To"


# ── Recherche ─────────────────────────────────────────────────────────────────

async def find_files(requete: str, limite: int = MAX_RESULTATS) -> str:
    """Cherche des fichiers par nom via l'index Spotlight."""
    requete = (requete or "").strip()
    if not requete:
        return "Aucun terme de recherche fourni."

    safe = requete.replace('"', "").replace("'", "")
    try:
        r = await asyncio.to_thread(
            _run, ["mdfind", "-onlyin", str(Path.home()), f'kMDItemDisplayName == "*{safe}*"cd'], 20.0
        )
        chemins = [c for c in (r.stdout or "").splitlines() if c.strip()]
    except Exception as exc:  # noqa: BLE001
        return f"Recherche impossible : {exc}"

    if not chemins:
        return f"Aucun fichier trouvé pour « {requete} »."

    # Les fichiers récemment modifiés d'abord : c'est presque toujours ce qu'on cherche.
    infos = []
    for c in chemins[:80]:
        try:
            p = Path(c)
            infos.append((p.stat().st_mtime, p))
        except Exception:
            continue
    infos.sort(reverse=True)

    lignes = [f"{len(chemins)} résultat(s) pour « {requete} » — les plus récents :"]
    for mtime, p in infos[:limite]:
        quand = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y")
        lignes.append(f"  {p.name}  ({_lisible(p.parent)}, {quand})")
    return "\n".join(lignes)


async def recent_files(jours: int = 3, limite: int = MAX_RESULTATS) -> str:
    """Fichiers modifiés récemment dans les dossiers de travail."""
    trouves = []
    limite_ts = datetime.now().timestamp() - jours * 86400
    for dossier in DOSSIERS_USUELS:
        base = Path.home() / dossier
        if not base.exists():
            continue
        try:
            for p in base.rglob("*"):
                if p.is_file() and not p.name.startswith("."):
                    try:
                        m = p.stat().st_mtime
                        if m >= limite_ts:
                            trouves.append((m, p))
                    except Exception:
                        continue
        except Exception:
            continue

    if not trouves:
        return f"Aucun fichier modifié depuis {jours} jour(s)."
    trouves.sort(reverse=True)
    lignes = [f"Modifiés ces {jours} derniers jours :"]
    for m, p in trouves[:limite]:
        lignes.append(f"  {p.name}  ({_lisible(p.parent)}, {datetime.fromtimestamp(m):%d/%m %H:%M})")
    return "\n".join(lignes)


# ── Ouverture / navigation ────────────────────────────────────────────────────

def _resoudre(cible: str) -> Path | None:
    """Trouve un fichier ou dossier à partir d'un nom approximatif."""
    cible = (cible or "").strip().strip("'\"«»")
    if not cible:
        return None

    direct = Path(cible).expanduser()
    if direct.exists():
        return direct

    for dossier in DOSSIERS_USUELS + ("",):
        base = Path.home() / dossier if dossier else Path.home()
        candidat = base / cible
        if candidat.exists():
            return candidat

    safe = cible.replace('"', "")
    try:
        r = _run(["mdfind", "-onlyin", str(Path.home()),
                  f'kMDItemDisplayName == "*{safe}*"cd'], 15.0)
        chemins = [Path(c) for c in (r.stdout or "").splitlines() if c.strip()]
        chemins = [c for c in chemins if c.exists()]
        if chemins:
            chemins.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return chemins[0]
    except Exception:
        pass
    return None


async def open_path(cible: str) -> str:
    """Ouvre un fichier ou un dossier avec l'application par défaut."""
    p = await asyncio.to_thread(_resoudre, cible)
    if p is None:
        return f"Introuvable : « {cible} »."
    try:
        await asyncio.to_thread(_run, ["open", str(p)])
        return f"{p.name} ouvert."
    except Exception as exc:  # noqa: BLE001
        return f"Ouverture impossible : {exc}"


async def reveal_in_finder(cible: str) -> str:
    """Affiche un fichier dans le Finder (sans l'ouvrir)."""
    p = await asyncio.to_thread(_resoudre, cible)
    if p is None:
        return f"Introuvable : « {cible} »."
    try:
        await asyncio.to_thread(_run, ["open", "-R", str(p)])
        return f"{p.name} affiché dans le Finder ({_lisible(p.parent)})."
    except Exception as exc:  # noqa: BLE001
        return f"Impossible d'afficher : {exc}"


# ── Organisation ──────────────────────────────────────────────────────────────

async def create_folder(nom: str, dans: str = "Desktop") -> str:
    nom = (nom or "").strip().strip("'\"«»")
    if not nom:
        return "Aucun nom de dossier fourni."
    base = Path.home() / dans if not Path(dans).expanduser().is_absolute() else Path(dans).expanduser()
    cible = base / nom
    try:
        if cible.exists():
            return f"Le dossier « {nom} » existe déjà ({_lisible(cible.parent)})."
        # Arguments nommés obligatoires : en positionnel, le premier paramètre
        # de mkdir() est le MODE de permissions, pas `parents` — le dossier se
        # créait alors sans droit d'écriture.
        await asyncio.to_thread(
            lambda: cible.mkdir(parents=True, exist_ok=True)
        )
        return f"Dossier « {nom} » créé dans {_lisible(base)}."
    except Exception as exc:  # noqa: BLE001
        return f"Création impossible : {exc}"


async def move_file(source: str, destination: str) -> str:
    p = await asyncio.to_thread(_resoudre, source)
    if p is None:
        return f"Introuvable : « {source} »."
    dest = Path(destination).expanduser()
    if not dest.is_absolute():
        dest = Path.home() / destination
    try:
        if dest.is_dir():
            dest = dest / p.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            return f"« {dest.name} » existe déjà à destination — rien n'a été écrasé."
        await asyncio.to_thread(shutil.move, str(p), str(dest))
        return f"{p.name} déplacé vers {_lisible(dest.parent)}."
    except Exception as exc:  # noqa: BLE001
        return f"Déplacement impossible : {exc}"


async def rename_file(cible: str, nouveau_nom: str) -> str:
    p = await asyncio.to_thread(_resoudre, cible)
    if p is None:
        return f"Introuvable : « {cible} »."
    nouveau_nom = (nouveau_nom or "").strip().strip("'\"«»")
    if not nouveau_nom:
        return "Aucun nouveau nom fourni."
    # Conserver l'extension si l'utilisateur ne l'a pas donnée.
    if p.suffix and not Path(nouveau_nom).suffix:
        nouveau_nom += p.suffix
    dest = p.parent / nouveau_nom
    try:
        if dest.exists():
            return f"« {nouveau_nom} » existe déjà ici — rien n'a été écrasé."
        await asyncio.to_thread(p.rename, dest)
        return f"Renommé en « {nouveau_nom} »."
    except Exception as exc:  # noqa: BLE001
        return f"Renommage impossible : {exc}"


async def trash_file(cible: str) -> str:
    """Met à la corbeille — JAMAIS de suppression définitive."""
    p = await asyncio.to_thread(_resoudre, cible)
    if p is None:
        return f"Introuvable : « {cible} »."
    # Déplacement direct vers ~/.Trash : c'est ce qu'est la corbeille, et c'est
    # fiable. Passer par le Finder en AppleScript expirait régulièrement
    # (l'application doit être au premier plan et répondre).
    corbeille = Path.home() / ".Trash"
    try:
        corbeille.mkdir(exist_ok=True)
        destination = corbeille / p.name
        # Ne jamais écraser un élément déjà présent dans la corbeille.
        if destination.exists():
            horodatage = datetime.now().strftime("%H-%M-%S")
            destination = corbeille / f"{p.stem} {horodatage}{p.suffix}"
        await asyncio.to_thread(shutil.move, str(p), str(destination))
        return f"{p.name} mis à la corbeille (récupérable)."
    except Exception as exc:  # noqa: BLE001
        return f"Mise à la corbeille impossible : {exc}"


# ── Informations ──────────────────────────────────────────────────────────────

async def disk_usage() -> str:
    try:
        u = await asyncio.to_thread(shutil.disk_usage, str(Path.home()))
        pct = u.used / u.total * 100
        return (f"Disque : {_taille(u.free)} libres sur {_taille(u.total)} "
                f"({pct:.0f}% utilisé).")
    except Exception as exc:  # noqa: BLE001
        return f"Lecture du disque impossible : {exc}"


async def file_info(cible: str) -> str:
    p = await asyncio.to_thread(_resoudre, cible)
    if p is None:
        return f"Introuvable : « {cible} »."
    try:
        st = p.stat()
        genre = "dossier" if p.is_dir() else "fichier"
        taille = ""
        if p.is_file():
            taille = f", {_taille(st.st_size)}"
        elif p.is_dir():
            n = sum(1 for _ in p.iterdir())
            taille = f", {n} élément(s)"
        return (f"{p.name} — {genre}{taille}, modifié le "
                f"{datetime.fromtimestamp(st.st_mtime):%d/%m/%Y à %H:%M}, "
                f"dans {_lisible(p.parent)}.")
    except Exception as exc:  # noqa: BLE001
        return f"Lecture impossible : {exc}"


async def read_text_file(cible: str, max_chars: int = 3000) -> str:
    p = await asyncio.to_thread(_resoudre, cible)
    if p is None:
        return f"Introuvable : « {cible} »."
    if p.is_dir():
        return f"« {p.name} » est un dossier, pas un fichier."
    try:
        contenu = await asyncio.to_thread(
            p.read_text, "utf-8", "ignore"
        )
        if not contenu.strip():
            return f"{p.name} est vide."
        suite = "" if len(contenu) <= max_chars else "\n[…suite tronquée]"
        return f"Contenu de {p.name} :\n{contenu[:max_chars]}{suite}"
    except Exception as exc:  # noqa: BLE001
        return f"Lecture impossible : {exc}"


# ── Routage depuis une phrase ─────────────────────────────────────────────────

async def route(task: str) -> str | None:
    """Traite la demande nativement si elle concerne les fichiers. None sinon."""
    t = (task or "").strip()
    tl = t.lower()
    if not tl:
        return None

    # Espace disque
    if re.search(r"\b(espace|place)\s+(disque|libre|dispo)|\bdisque\s+plein\b|"
                 r"\bcombien.*(place|espace)\b", tl):
        return await disk_usage()

    # Fichiers récents
    m = re.search(r"\b(fichiers?|documents?)\s+récents?\b|"
                  r"\bsur quoi j'?ai travaill|\bderniers?\s+fichiers?\b", tl)
    if m:
        return await recent_files()

    # Recherche
    m = re.search(
        r"\b(?:cherche|trouve|recherche|où est|ou est|retrouve)\s+"
        r"(?:le\s+|la\s+|les\s+|mon\s+|ma\s+|mes\s+|un\s+|une\s+)?"
        r"(?:fichiers?|documents?|dossiers?)?\s*"
        r"(?:qui\s+s'appelle\s+|nommé\s+|appelé\s+)?[«\"']?([^«»\"']{2,60})[«\"']?\s*$",
        tl,
    )
    if m and re.search(r"\b(fichier|document|dossier)\b", tl):
        return await find_files(m.group(1).strip())

    # Ouvrir un fichier/dossier précis
    m = re.search(r"^(?:ouvre|ouvrir|affiche)\s+(?:le\s+|la\s+|mon\s+|ma\s+)?"
                  r"(?:fichier|document|dossier)\s+[«\"']?([^«»\"']+?)[«\"']?\s*$", tl)
    if m:
        return await open_path(m.group(1).strip())

    # Révéler dans le Finder
    m = re.search(r"\b(?:montre|affiche|révèle|revele|localise)\s+.*\bdans le finder\b|"
                  r"\bouvre le finder sur\s+(.+)$", tl)
    if m:
        cible = m.group(1) if m.lastindex else re.sub(
            r"\b(montre|affiche|révèle|revele|localise|moi|le|la|fichier|dossier|dans le finder)\b",
            "", tl).strip()
        if cible:
            return await reveal_in_finder(cible)

    # Créer un dossier
    m = re.search(r"\b(?:crée|cree|créer|nouveau)\s+(?:un\s+)?dossier\s+"
                  r"(?:nommé\s+|appelé\s+)?[«\"']?([^«»\"']+?)[«\"']?"
                  r"(?:\s+(?:dans|sur)\s+(?:le\s+)?([a-zà-ÿ]+))?\s*$", tl)
    if m:
        dossier = {"bureau": "Desktop", "documents": "Documents",
                   "téléchargements": "Downloads", "telechargements": "Downloads"}.get(
            (m.group(2) or "").strip(), "Desktop")
        return await create_folder(m.group(1).strip(), dossier)

    # Renommer
    m = re.search(r"\brenomme\s+[«\"']?([^«»\"']+?)[«\"']?\s+en\s+[«\"']?([^«»\"']+?)[«\"']?\s*$", tl)
    if m:
        return await rename_file(m.group(1).strip(), m.group(2).strip())

    # Mettre à la corbeille — les deux ordres de mots sont courants :
    # « mets X à la corbeille » et « supprime X » / « mets à la corbeille X ».
    m = re.search(r"\b(?:mets?|mettre|jette|place)\s+(?:le\s+|la\s+|les\s+)?"
                  r"(?:fichiers?|dossiers?)?\s*[«\"']?([^«»\"']+?)[«\"']?\s+"
                  r"(?:à|a|dans)\s+la\s+corbeille\s*$", tl)
    if m:
        return await trash_file(m.group(1).strip())

    m = re.search(r"\b(?:supprime|efface|jette|mets? à la corbeille)\s+"
                  r"(?:le\s+|la\s+)?(?:fichiers?|dossiers?)?\s*[«\"']?([^«»\"']+?)[«\"']?\s*$", tl)
    if m:
        return await trash_file(m.group(1).strip())

    return None
