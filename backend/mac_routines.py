"""
mac_routines — actions macOS natives, sans vision ni LLM.

Le constat de terrain est net : chaque fois qu'une commande tombe dans la
boucle vision (capture d'écran → modèle → clics devinés), elle devient lente
et rate souvent. Chaque fois qu'on lui donne une routine native, elle marche
du premier coup, en quelques centaines de millisecondes.

Ce module étend donc la couverture native aux commandes du quotidien :
panneaux de Réglages, fenêtres, capture d'écran, luminosité, média, verrouillage.

Deux principes :
  - un panneau de Réglages s'ouvre par son URL (`x-apple.systempreferences:`),
    jamais en cliquant dans l'interface ;
  - toute fonction renvoie une `str` lisible, et ne lève jamais.
"""

from __future__ import annotations

import asyncio
import re
import subprocess

# ─── Panneaux de Réglages Système (URL directes, zéro clic) ───────────────────

_PANNEAUX: dict[str, tuple[str, str]] = {
    # motif reconnu            → (identifiant du panneau, libellé)
    "son":                     ("com.apple.preference.sound", "Son"),
    "audio":                   ("com.apple.preference.sound", "Son"),
    "volume":                  ("com.apple.preference.sound", "Son"),
    "écran":                   ("com.apple.preference.displays", "Moniteurs"),
    "ecran":                   ("com.apple.preference.displays", "Moniteurs"),
    "moniteur":                ("com.apple.preference.displays", "Moniteurs"),
    "affichage":               ("com.apple.preference.displays", "Moniteurs"),
    "luminosité":              ("com.apple.preference.displays", "Moniteurs"),
    "luminosite":              ("com.apple.preference.displays", "Moniteurs"),
    "bluetooth":               ("com.apple.preferences.Bluetooth", "Bluetooth"),
    "wifi":                    ("com.apple.wifi-settings-extension", "Wi-Fi"),
    "wi-fi":                   ("com.apple.wifi-settings-extension", "Wi-Fi"),
    "réseau":                  ("com.apple.Network-Settings.extension", "Réseau"),
    "reseau":                  ("com.apple.Network-Settings.extension", "Réseau"),
    "confidentialité":         ("com.apple.settings.PrivacySecurity.extension", "Confidentialité et sécurité"),
    "confidentialite":         ("com.apple.settings.PrivacySecurity.extension", "Confidentialité et sécurité"),
    "sécurité":                ("com.apple.settings.PrivacySecurity.extension", "Confidentialité et sécurité"),
    "securite":                ("com.apple.settings.PrivacySecurity.extension", "Confidentialité et sécurité"),
    "caméra":                  ("com.apple.preference.security?Privacy_Camera", "Caméra"),
    "camera":                  ("com.apple.preference.security?Privacy_Camera", "Caméra"),
    "micro":                   ("com.apple.preference.security?Privacy_Microphone", "Microphone"),
    "microphone":              ("com.apple.preference.security?Privacy_Microphone", "Microphone"),
    "accessibilité":           ("com.apple.preference.security?Privacy_Accessibility", "Accessibilité"),
    "accessibilite":           ("com.apple.preference.security?Privacy_Accessibility", "Accessibilité"),
    "notifications":           ("com.apple.Notifications-Settings.extension", "Notifications"),
    "batterie":                ("com.apple.Battery-Settings.extension", "Batterie"),
    "clavier":                 ("com.apple.Keyboard-Settings.extension", "Clavier"),
    "souris":                  ("com.apple.Mouse-Settings.extension", "Souris"),
    "trackpad":                ("com.apple.Trackpad-Settings.extension", "Trackpad"),
    "fond d'écran":            ("com.apple.Wallpaper-Settings.extension", "Fond d'écran"),
    "utilisateurs":            ("com.apple.Users-Groups-Settings.extension", "Utilisateurs et groupes"),
    "stockage":                ("com.apple.settings.Storage", "Stockage"),
    "mise à jour":             ("com.apple.Software-Update-Settings.extension", "Mise à jour"),
    "mise a jour":             ("com.apple.Software-Update-Settings.extension", "Mise à jour"),
}


def _run(args: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _osa(script: str, timeout: float = 10.0) -> str:
    r = _run(["osascript", "-e", script], timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "").strip())
    return (r.stdout or "").strip()


# ─── Routines ─────────────────────────────────────────────────────────────────

async def open_settings_panel(sujet: str) -> str | None:
    """Ouvre un panneau précis des Réglages Système. None si sujet inconnu."""
    s = (sujet or "").strip().lower()
    entree = _PANNEAUX.get(s)
    if entree is None:
        for motif, valeur in _PANNEAUX.items():
            if motif in s:
                entree = valeur
                break
    if entree is None:
        return None

    panneau, libelle = entree
    try:
        await asyncio.to_thread(_run, ["open", f"x-apple.systempreferences:{panneau}"])
        await asyncio.sleep(0.8)
        return f"Réglages ouverts sur {libelle}."
    except Exception as exc:  # noqa: BLE001
        return f"Impossible d'ouvrir les réglages {libelle} : {exc}"


async def window_action(action: str) -> str:
    """Agit sur la fenêtre au premier plan (réduire, agrandir, plein écran…)."""
    try:
        if action == "minimiser":
            await asyncio.to_thread(
                _osa,
                'tell application "System Events" to keystroke "m" using command down',
            )
            return "Fenêtre réduite."
        if action == "fermer_fenetre":
            await asyncio.to_thread(
                _osa,
                'tell application "System Events" to keystroke "w" using command down',
            )
            return "Fenêtre fermée."
        if action == "plein_ecran":
            await asyncio.to_thread(
                _osa,
                'tell application "System Events" to keystroke "f" using '
                "{control down, command down}",
            )
            return "Plein écran basculé."
        if action == "tout_masquer":
            await asyncio.to_thread(
                _osa,
                'tell application "System Events" to keystroke "h" using '
                "{command down, option down}",
            )
            return "Toutes les autres fenêtres masquées."
        return f"Action de fenêtre inconnue : {action}"
    except Exception as exc:  # noqa: BLE001
        return f"Action fenêtre impossible : {exc}"


async def media_control(action: str) -> str:
    """Lecture / pause / piste suivante via les touches multimédia."""
    codes = {"playpause": 16, "suivant": 17, "precedent": 18}
    code = codes.get(action)
    if code is None:
        return f"Commande média inconnue : {action}"
    try:
        # key code multimédia via System Events (fonctionne hors app musicale).
        await asyncio.to_thread(
            _osa,
            f'tell application "System Events" to key code {code} using function down',
        )
        libelles = {"playpause": "Lecture/pause",
                    "suivant": "Piste suivante", "precedent": "Piste précédente"}
        return f"{libelles[action]}."
    except Exception:
        # Repli : piloter Music/Spotify directement s'ils tournent.
        for app in ("Spotify", "Music"):
            try:
                verbe = {"playpause": "playpause",
                         "suivant": "next track",
                         "precedent": "previous track"}[action]
                await asyncio.to_thread(
                    _osa, f'tell application "{app}" to {verbe}'
                )
                return f"{app} : {action}."
            except Exception:
                continue
        return "Aucun lecteur média n'a répondu."


async def set_brightness(niveau: int) -> str:
    """Règle la luminosité (0-100) via les touches système."""
    niveau = max(0, min(100, int(niveau)))
    try:
        # 16 crans : on descend au minimum puis on remonte au niveau voulu.
        await asyncio.to_thread(
            _osa,
            'tell application "System Events" to repeat 16 times\n'
            "key code 145\nend repeat",
            timeout=15,
        )
        crans = round(niveau / 100 * 16)
        if crans:
            await asyncio.to_thread(
                _osa,
                f'tell application "System Events" to repeat {crans} times\n'
                "key code 144\nend repeat",
                timeout=15,
            )
        return f"Luminosité réglée à environ {niveau}%."
    except Exception as exc:  # noqa: BLE001
        return f"Réglage de luminosité impossible : {exc}"


async def screenshot(zone: str = "ecran") -> str:
    """Capture d'écran enregistrée sur le Bureau."""
    from datetime import datetime
    from pathlib import Path

    nom = f"capture-{datetime.now():%Y%m%d-%H%M%S}.png"
    chemin = Path.home() / "Desktop" / nom
    args = ["screencapture", "-x"]
    if zone == "selection":
        args = ["screencapture", "-i"]
    elif zone == "fenetre":
        args = ["screencapture", "-w"]
    args.append(str(chemin))
    try:
        await asyncio.to_thread(_run, args, 30.0)
        return f"Capture enregistrée sur le Bureau : {nom}" if chemin.exists() else "Capture annulée."
    except Exception as exc:  # noqa: BLE001
        return f"Capture impossible : {exc}"


async def lock_screen() -> str:
    try:
        await asyncio.to_thread(
            _osa,
            'tell application "System Events" to keystroke "q" using '
            "{control down, command down}",
        )
        return "Écran verrouillé."
    except Exception as exc:  # noqa: BLE001
        return f"Verrouillage impossible : {exc}"


async def empty_trash() -> str:
    """Vide la corbeille — action irréversible, appelée uniquement sur demande explicite."""
    try:
        await asyncio.to_thread(_osa, 'tell application "Finder" to empty trash')
        return "Corbeille vidée."
    except Exception as exc:  # noqa: BLE001
        return f"Impossible de vider la corbeille : {exc}"


# ─── Routage depuis une phrase ────────────────────────────────────────────────

async def route(task: str) -> str | None:
    """Tente de traiter la demande nativement. None si non concernée."""
    t = (task or "").strip()
    tl = t.lower()
    if not tl:
        return None

    # Réglages système ciblés : « ouvre les réglages de son », « règle le bluetooth »
    m = re.search(
        r"(?:ouvre|ouvrir|affiche|va\s+(?:dans|sur|à)|montre|règle|regle|paramètre|parametre)\s+"
        r"(?:les?\s+|la\s+|le\s+)?(?:réglages?|reglages?|préférences?|preferences?|paramètres?|parametres?)"
        r"(?:\s+(?:de|du|des|d'|sur|pour)\s*)?(.*)$",
        tl,
    )
    if m:
        sujet = m.group(1).strip(" .")
        if sujet:
            res = await open_settings_panel(sujet)
            if res:
                return res
        return None  # « ouvre les réglages » tout court → ouverture d'app classique

    # Panneau nommé sans le mot « réglages » : « ouvre les paramètres caméra »
    m = re.search(r"^(?:ouvre|affiche|va\s+(?:dans|sur))\s+(?:le\s+|la\s+|les\s+)?"
                  r"(bluetooth|wifi|wi-fi)\s*$", tl)
    if m:
        return await open_settings_panel(m.group(1))

    # Fenêtres
    if re.search(r"\b(réduis|reduis|minimise)\b.*\b(fenêtre|fenetre)\b", tl):
        return await window_action("minimiser")
    if re.search(r"\b(plein[- ]écran|plein[- ]ecran)\b", tl):
        return await window_action("plein_ecran")
    if re.search(r"\bferme\s+(?:cette\s+|la\s+)?fenêtre\b|\bferme\s+l'onglet\b", tl):
        return await window_action("fermer_fenetre")
    if re.search(r"\bmasque\s+(?:tout|les autres)\b", tl):
        return await window_action("tout_masquer")

    # Média
    if re.search(r"\b(pause|mets? en pause|reprends la lecture|play)\b", tl):
        return await media_control("playpause")
    if re.search(r"\b(chanson|morceau|titre|piste|musique)\s+suivante?\b|\bsuivant\b", tl):
        return await media_control("suivant")
    if re.search(r"\b(chanson|morceau|titre|piste|musique)\s+précédente?\b|\bprécédent\b", tl):
        return await media_control("precedent")

    # Luminosité
    m = re.search(r"\b(?:luminosité|luminosite|brightness)\b.*?(\d{1,3})\s*%?", tl)
    if m:
        return await set_brightness(int(m.group(1)))
    if re.search(r"\b(baisse|diminue|réduis|reduis)\s+la\s+luminosité", tl):
        return await set_brightness(30)
    if re.search(r"\b(monte|augmente)\s+la\s+luminosité", tl):
        return await set_brightness(90)

    # Capture d'écran
    if re.search(r"\b(capture|screenshot|copie)\s+(?:d'|de\s+l')?écran\b|\bfais une capture\b", tl):
        if "sélection" in tl or "selection" in tl or "zone" in tl:
            return await screenshot("selection")
        if "fenêtre" in tl or "fenetre" in tl:
            return await screenshot("fenetre")
        return await screenshot("ecran")

    # Verrouillage
    if re.search(r"\bverrouille?\b.*\b(écran|ecran|mac|session)\b|\bverrouille le mac\b", tl):
        return await lock_screen()

    return None
