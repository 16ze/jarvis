"""
safe_exec — politique d'exécution des commandes shell d'Ada.

Remplace l'ancienne blocklist par sous-chaîne (contournable trivialement :
`/bin/rm`, `r""m`, base64, find -delete…) par une classification robuste :

  1. HARD_BLOCK — patterns catastrophiques, jamais exécutés (même confirmés).
  2. Analyse du VRAI binaire via shlex (résiste à /bin/rm, chemins, quotes).
  3. Décision selon la source :
       - source="user"  → l'utilisateur a tapé la commande lui-même → ALLOW
                          (sauf HARD_BLOCK).
       - source="ai"    → commande initiée par le modèle → ALLOW seulement si
                          le binaire est dans AUTO_ALLOW (lecture seule) ; sinon
                          CONFIRM (l'appelant doit demander validation humaine).

Point d'entrée unique : `classify(command, source) -> Decision`.
`run(command, source, ...)` exécute si et seulement si la décision est ALLOW.

Aucune exception ne remonte : tout est renvoyé sous forme de chaîne.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import PurePath

# ── Décisions ────────────────────────────────────────────────────────────────
ALLOW = "allow"
CONFIRM = "confirm"
BLOCK = "block"


@dataclass
class Decision:
    action: str          # ALLOW | CONFIRM | BLOCK
    reason: str          # explication lisible
    binary: str = ""     # binaire détecté (pour logs / confirmation)

    @property
    def allowed(self) -> bool:
        return self.action == ALLOW


# ── Patterns catastrophiques — JAMAIS exécutés ───────────────────────────────
# Testés sur la commande normalisée (espaces compressés). Volontairement larges.
_HARD_BLOCK = [
    (re.compile(r":\s*\(\s*\)\s*\{.*:\|:.*&.*\}"), "fork bomb"),
    (re.compile(r"\brm\b.*-[a-z]*r[a-z]*f?.*\s+(/|~|\$HOME)(\s|$)"), "rm récursif sur racine/home"),
    (re.compile(r"\brm\b.*\s+-[a-z]*f[a-z]*r.*\s+(/|~)(\s|$)"), "rm forcé récursif sur racine/home"),
    (re.compile(r"\bmkfs\b"), "formatage de système de fichiers"),
    (re.compile(r"\bdd\b.*\bof=/dev/"), "écriture disque brute (dd)"),
    (re.compile(r">\s*/dev/(sd|disk|nvme|rdisk)"), "écriture sur périphérique disque"),
    (re.compile(r"\bchmod\b.*-[a-z]*R.*\s+777\s+/"), "chmod 777 récursif sur racine"),
    (re.compile(r"\b(curl|wget)\b.*\|\s*(sudo\s+)?(sh|bash|zsh)\b"), "pipe réseau → shell (exécution distante)"),
    (re.compile(r"\bdiskutil\b.*\b(erase|reformat|zeroDisk)\b"), "effacement disque (diskutil)"),
    (re.compile(r"\b(shutdown|reboot|halt)\b"), "arrêt/redémarrage système"),
]

# ── Binaires en lecture seule — auto-autorisés même pour l'IA ────────────────
_AUTO_ALLOW = {
    "ls", "pwd", "echo", "cat", "head", "tail", "wc", "grep", "egrep", "fgrep",
    "find", "which", "type", "file", "stat", "date", "whoami", "id", "hostname",
    "uname", "df", "du", "ps", "top", "env", "printenv", "cal", "uptime",
    "sort", "uniq", "cut", "tr", "awk", "sed", "jq", "diff", "tree", "basename",
    "dirname", "realpath", "readlink", "man", "help", "history", "open",
}

# ── Binaires modifiants (info pour l'UI / logs) ───────────────────────────────
_WRITE_HINTS = {"rm", "mv", "cp", "chmod", "chown", "kill", "killall", "pkill",
                "sudo", "dd", "git", "npm", "pip", "brew", "docker"}


def _real_binary(command: str) -> str:
    """Extrait le binaire réel, résistant aux chemins (/bin/rm → rm)."""
    try:
        parts = shlex.split(command)
    except ValueError:
        # Guillemets non fermés, etc. — on retombe sur un split naïf.
        parts = command.strip().split()
    if not parts:
        return ""
    # Ignore les assignations d'env en tête : FOO=bar cmd
    idx = 0
    while idx < len(parts) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", parts[idx]):
        idx += 1
    if idx >= len(parts):
        return ""
    token = parts[idx]
    # env / command / nice / nohup … → binaire réel = token suivant
    if token in {"env", "command", "nice", "nohup", "time", "xargs", "sudo", "doas"}:
        for nxt in parts[idx + 1:]:
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", nxt):
                continue
            if nxt.startswith("-"):
                continue
            token = nxt
            break
    return PurePath(token).name.lower()


def _normalize(command: str) -> str:
    return re.sub(r"\s+", " ", command.strip())


def classify(command: str, source: str = "ai") -> Decision:
    """Classe une commande. source ∈ {"user", "ai"}."""
    norm = _normalize(command)
    if not norm:
        return Decision(BLOCK, "commande vide")

    # 1. Blocages durs — priorité absolue, quelle que soit la source.
    for pattern, label in _HARD_BLOCK:
        if pattern.search(norm):
            return Decision(BLOCK, f"commande interdite ({label})")

    binary = _real_binary(command)

    # 2. sudo → toujours confirmation pour l'IA (élévation de privilèges).
    if binary == "sudo" or norm.startswith("sudo ") or " | sudo " in norm:
        if source == "user":
            return Decision(ALLOW, "sudo saisi manuellement par l'utilisateur", binary)
        return Decision(CONFIRM, "élévation de privilèges (sudo) — confirmation requise", binary)

    # 3. Utilisateur maître de son terminal (hors HARD_BLOCK déjà filtré).
    if source == "user":
        return Decision(ALLOW, "commande saisie par l'utilisateur", binary)

    # 4. Source IA : lecture seule auto-autorisée, reste en confirmation.
    if binary in _AUTO_ALLOW:
        return Decision(ALLOW, f"lecture seule ({binary})", binary)
    return Decision(
        CONFIRM,
        f"commande potentiellement modifiante ({binary or 'inconnu'}) — confirmation requise",
        binary,
    )


def run(
    command: str,
    source: str = "ai",
    *,
    cwd: str | None = None,
    timeout: int = 60,
    allow_confirm: bool = False,
) -> tuple[Decision, str]:
    """Exécute la commande SSI la politique l'autorise.

    allow_confirm=True traite CONFIRM comme ALLOW (à n'utiliser qu'après avoir
    obtenu une validation humaine explicite en amont).
    Retourne (Decision, output_str).
    """
    decision = classify(command, source)
    if decision.action == BLOCK:
        return decision, f"[BLOQUÉ] {decision.reason}"
    if decision.action == CONFIRM and not allow_confirm:
        return decision, f"[CONFIRMATION REQUISE] {decision.reason}"

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or os.path.expanduser("~"),
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        output = out
        if err:
            output += (f"\n[stderr]: {err}" if output else f"[stderr]: {err}")
        return decision, (output or "(aucune sortie)")
    except subprocess.TimeoutExpired:
        return decision, f"[Erreur] Timeout après {timeout}s."
    except Exception as exc:  # noqa: BLE001 — convention Ada : jamais d'exception nue
        return decision, f"[Erreur] {exc}"
