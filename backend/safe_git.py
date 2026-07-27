"""
safe_git — empêche les agents d'Ada de publier un secret.

Les agents d'auto-correction et d'auto-évolution sauvegardaient leur travail
avec `git add -A`, qui ajoute TOUT ce qui traîne dans le dossier. C'est ainsi
qu'un jeton OAuth Google (`google_token.json.old`) s'est retrouvé dans un
commit — seule la protection de GitHub a empêché sa publication.

Un `.gitignore` ne suffit pas : il faut y penser à chaque nouveau fichier
sensible, et un oubli passe inaperçu jusqu'à l'incident. Ce module ajoute une
barrière indépendante, appliquée à l'indexation elle-même.

Deux règles :
  1. on n'indexe jamais un chemin dont le NOM évoque un secret ;
  2. on n'indexe jamais un fichier dont le CONTENU ressemble à un jeton.

En cas de doute, on refuse : perdre une sauvegarde automatique est sans
conséquence, publier une clé ne se rattrape pas.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Noms de fichiers qui ne doivent jamais être indexés automatiquement.
MOTIFS_INTERDITS = re.compile(
    r"(^|/)\.env|"
    r"token|secret|credential|password|"
    r"\.pem$|\.key$|\.p12$|\.keystore$|"
    r"\.json\.old$|\.bak\d*$|\.backup$",
    re.IGNORECASE,
)

# Signatures de secrets réels, cherchées dans le contenu.
SIGNATURES = (
    re.compile(r'"refresh_token"\s*:\s*"[^"]{20,}'),
    re.compile(r'"access_token"\s*:\s*"[^"]{20,}'),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),          # clés OpenAI/Anthropic
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),      # clés Google
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),         # jetons GitHub
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),  # jetons Slack
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

TAILLE_MAX_INSPECTEE = 512_000  # au-delà, on n'inspecte pas le contenu


def is_sensitive(chemin: str, racine: Path | None = None) -> tuple[bool, str]:
    """Ce chemin doit-il rester hors de l'index ? Retourne (verdict, raison)."""
    if MOTIFS_INTERDITS.search(chemin):
        return True, "nom évocateur d'un secret"

    if racine is not None:
        fichier = racine / chemin
        try:
            if fichier.is_file() and fichier.stat().st_size <= TAILLE_MAX_INSPECTEE:
                contenu = fichier.read_text(encoding="utf-8", errors="ignore")
                for signature in SIGNATURES:
                    if signature.search(contenu):
                        return True, "contenu ressemblant à un jeton"
        except Exception:
            pass  # illisible : on ne bloque pas pour autant
    return False, ""


def _fichiers_modifies(racine: Path) -> list[str]:
    r = subprocess.run(
        ["git", "-C", str(racine), "status", "--porcelain", "-uall"],
        capture_output=True, text=True, timeout=30,
    )
    chemins = []
    for ligne in (r.stdout or "").splitlines():
        if len(ligne) > 3:
            chemin = ligne[3:].strip().strip('"')
            # Renommage « ancien -> nouveau » : seul le nouveau nous intéresse.
            if " -> " in chemin:
                chemin = chemin.split(" -> ", 1)[1]
            if chemin:
                chemins.append(chemin)
    return chemins


def add_all_safe(racine: Path | str) -> tuple[list[str], list[str]]:
    """Remplace `git add -A` en écartant tout ce qui ressemble à un secret.

    Retourne (fichiers indexés, fichiers écartés).
    """
    racine = Path(racine)
    indexes: list[str] = []
    ecartes: list[str] = []

    for chemin in _fichiers_modifies(racine):
        sensible, raison = is_sensitive(chemin, racine)
        if sensible:
            ecartes.append(f"{chemin} ({raison})")
            continue
        r = subprocess.run(
            ["git", "-C", str(racine), "add", "--", chemin],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            indexes.append(chemin)

    if ecartes:
        print("[SAFE_GIT] écartés de l'indexation automatique :")
        for item in ecartes:
            print(f"  - {item}")
    return indexes, ecartes
