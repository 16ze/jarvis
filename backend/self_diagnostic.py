"""
self_diagnostic — Ada sait dire ce qui ne marche pas chez elle.

Le rapport de santé existant produit un JSON que personne ne lit, et il ne
teste justement pas les deux choses qui tombent en pratique : l'accès caméra
(permission macOS) et l'expiration des jetons OAuth. Résultat : Ada échoue
silencieusement et l'utilisateur cherche pendant des heures.

Ce module fait l'inverse : peu de vérifications, mais celles qui bloquent
réellement l'usage, et un résumé formulé en français que Ada peut DIRE.

Principe : ne signaler que ce qui est cassé ET actionnable. Une clé d'API
optionnelle absente n'intéresse personne ; une caméra refusée, si.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent


@dataclass
class Issue:
    """Un problème détecté, formulé pour être dit à voix haute."""

    gravite: str      # "bloquant" | "gênant"
    resume: str       # ce qu'Ada dit
    remede: str       # ce que l'utilisateur doit faire

    @property
    def is_blocking(self) -> bool:
        return self.gravite == "bloquant"


# ── Vérifications ─────────────────────────────────────────────────────────────

def check_camera() -> Issue | None:
    """Teste l'accès réel à la caméra (permission macOS incluse)."""
    try:
        import cv2
    except Exception:
        return None  # OpenCV absent : la vision n'est pas censée tourner

    cap = None
    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            return Issue(
                "gênant",
                "je n'ai pas accès à la caméra",
                "Réglages Système → Confidentialité et sécurité → Caméra : "
                "autoriser Terminal (ou l'app qui lance Ada), puis relancer.",
            )
        ok, frame = cap.read()
        if not ok or frame is None:
            return Issue(
                "gênant",
                "la caméra est détectée mais ne renvoie pas d'image",
                "Une autre application l'utilise peut-être — ferme-la et relance Ada.",
            )
        return None
    except Exception as exc:  # noqa: BLE001
        return Issue("gênant", "la caméra est inaccessible",
                     f"Erreur technique : {exc}")
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass


def check_google_token() -> Issue | None:
    """Vérifie la validité du jeton Google (Gmail, Agenda, Drive)."""
    path = _BACKEND / "google_token.json"
    if not path.exists():
        return None  # jamais configuré : ce n'est pas une panne

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return Issue("gênant", "mon accès Google est illisible",
                     "Le fichier backend/google_token.json est corrompu — refais l'autorisation.")

    expiry = str(data.get("expiry") or "")
    if not expiry:
        return None
    try:
        exp = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
    except Exception:
        return None

    jours = (datetime.now(timezone.utc) - exp).days
    if jours < 0:
        return None  # encore valide

    # Un refresh_token renouvelle normalement tout seul : s'il est là et que le
    # jeton est périmé depuis longtemps, c'est que Google l'a révoqué.
    if data.get("refresh_token") and jours > 7:
        return Issue(
            "gênant",
            "mon accès à Gmail et à l'agenda a expiré",
            f"Le jeton est périmé depuis {jours} jours et Google l'a révoqué "
            "(app OAuth en mode « Test »). Refais l'autorisation Google, ou passe "
            "l'application en mode « Production » dans Google Cloud.",
        )
    if not data.get("refresh_token"):
        return Issue("gênant", "mon accès Google a expiré",
                     "Aucun jeton de rafraîchissement — refais l'autorisation Google.")
    return None


def check_accessibility() -> Issue | None:
    """Vérifie que le contrôle du Mac est autorisé (essentiel)."""
    try:
        r = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to return name of first process'],
            capture_output=True, text=True, timeout=8,
        )
        if r.returncode != 0:
            err = (r.stderr or "").lower()
            if "not allowed" in err or "1743" in err or "assistive" in err:
                return Issue(
                    "bloquant",
                    "je n'ai pas le droit de contrôler ton Mac",
                    "Réglages Système → Confidentialité et sécurité → Accessibilité : "
                    "autoriser Terminal, puis relancer Ada.",
                )
            return Issue("gênant", "le contrôle du Mac répond mal",
                         f"Détail : {(r.stderr or '').strip()[:120]}")
        return None
    except Exception as exc:  # noqa: BLE001
        return Issue("gênant", "je n'arrive pas à vérifier le contrôle du Mac",
                     f"Erreur : {exc}")


def check_core_keys() -> Issue | None:
    """Seule la clé du modèle est réellement bloquante."""
    if not os.getenv("GEMINI_API_KEY"):
        return Issue("bloquant", "ma clé Gemini n'est pas configurée",
                     "Renseigne GEMINI_API_KEY dans le fichier .env.")
    return None


def check_brain_enabled() -> Issue | None:
    """Le brain désactivé n'est pas une panne, mais mérite d'être signalé."""
    actif = os.getenv("BRAIN_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    if not actif:
        return Issue(
            "gênant",
            "mon système émotionnel est désactivé",
            "Lance Ada via start_ada.sh, ou mets BRAIN_ENABLED=true dans .env.",
        )
    return None


_CHECKS = (
    check_core_keys,
    check_accessibility,
    check_camera,
    check_google_token,
    check_brain_enabled,
)


# ── Agrégation ────────────────────────────────────────────────────────────────

def run_checks() -> list[Issue]:
    """Exécute toutes les vérifications. Ne lève jamais."""
    issues: list[Issue] = []
    for check in _CHECKS:
        try:
            issue = check()
        except Exception as exc:  # noqa: BLE001
            print(f"[DIAG] vérification {check.__name__} échouée : {exc}")
            continue
        if issue is not None:
            issues.append(issue)
    return issues


async def run_checks_async() -> list[Issue]:
    """Version non bloquante (les tests caméra/AppleScript sont lents)."""
    return await asyncio.to_thread(run_checks)


def spoken_summary(issues: list[Issue]) -> str | None:
    """Phrase naturelle qu'Ada peut dire. None si tout va bien."""
    if not issues:
        return None

    bloquants = [i for i in issues if i.is_blocking]
    autres = [i for i in issues if not i.is_blocking]
    ordonnes = bloquants + autres
    resumes = [i.resume for i in ordonnes]

    if len(resumes) == 1:
        corps = resumes[0]
    else:
        corps = ", ".join(resumes[:-1]) + f" et {resumes[-1]}"

    prefixe = "Avant qu'on commence : " if bloquants else "Petit point : "
    return f"{prefixe}{corps}."


def detailed_report(issues: list[Issue]) -> str:
    """Version écrite avec les remèdes — pour la console et l'écran Activité."""
    if not issues:
        return "✅ Diagnostic : tout est opérationnel."
    lignes = ["⚠️  Diagnostic Ada — points à corriger :"]
    for i in issues:
        marque = "❌" if i.is_blocking else "⚠️ "
        lignes.append(f"  {marque} {i.resume}")
        lignes.append(f"      → {i.remede}")
    return "\n".join(lignes)
