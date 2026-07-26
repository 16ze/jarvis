"""
browser_bridge — Ada pilote le navigateur intégré, sans passer par la vision.

Pour agir sur le web, Ada devait jusqu'ici prendre une capture d'écran, la
donner au modèle, puis deviner des coordonnées de clic. Lent, coûteux, et
souvent faux — surtout sur les formulaires de connexion.

Le navigateur intégré étant désormais fonctionnel, on l'utilise comme un
ACTIONNEUR : le backend envoie des commandes structurées au webview, qui les
exécute et renvoie un résultat. Plus de pixels devinés, plus de vision.

Protocole (Socket.IO) :
    backend  ──'browser_command'{id, action, …}──▶  interface
    interface ──'browser_result'{id, ok, data}───▶  backend

Choix de sûreté : le modèle ne peut PAS injecter de JavaScript arbitraire. Il
choisit parmi des actions fermées (naviguer, lire, cliquer, remplir, valider),
chacune implémentée côté interface par un extrait figé. Cela évite qu'une page
malveillante — ou une consigne mal formulée — ne transforme le navigateur en
exécuteur de code quelconque.
"""

from __future__ import annotations

import asyncio
import uuid

DEFAULT_TIMEOUT = 25.0

# Actions acceptées. Toute autre valeur est refusée avant même l'envoi.
ACTIONS = {
    "navigate",   # {url}      → charge une page
    "read",       # {}         → texte visible de la page
    "click",      # {text}     → clique l'élément dont le libellé contient `text`
    "fill",       # {field, value} → remplit le champ désigné (label/placeholder/nom)
    "submit",     # {}         → valide le formulaire courant
    "back",       # {}         → page précédente
    "url",        # {}         → URL courante
}


class BrowserBridge:
    """Corrèle les commandes envoyées à l'interface et leurs réponses."""

    def __init__(self, emitter=None):
        self._emitter = emitter            # async (event, payload) -> None
        self._pending: dict[str, asyncio.Future] = {}
        self._lock = asyncio.Lock()

    def set_emitter(self, emitter) -> None:
        self._emitter = emitter

    @property
    def connected(self) -> bool:
        return self._emitter is not None

    async def send(self, action: str, timeout: float = DEFAULT_TIMEOUT, **params) -> dict:
        """Envoie une commande et attend la réponse de l'interface."""
        if action not in ACTIONS:
            return {"ok": False, "error": f"action inconnue : {action}"}
        if self._emitter is None:
            return {"ok": False, "error": "interface non connectée"}

        request_id = uuid.uuid4().hex[:12]
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()

        async with self._lock:
            self._pending[request_id] = future

        payload = {"id": request_id, "action": action, **params}
        try:
            await self._emitter("browser_command", payload)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return {"ok": False, "error": "le navigateur n'a pas répondu à temps"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"envoi impossible : {exc}"}
        finally:
            async with self._lock:
                self._pending.pop(request_id, None)

    def resolve(self, payload: dict) -> None:
        """Appelé par le serveur à la réception d'un 'browser_result'."""
        if not isinstance(payload, dict):
            return
        request_id = str(payload.get("id", ""))
        future = self._pending.get(request_id)
        if future is None or future.done():
            return
        future.set_result({
            "ok": bool(payload.get("ok", False)),
            "data": payload.get("data", ""),
            "error": payload.get("error", ""),
        })


_BRIDGE: BrowserBridge | None = None


def get_bridge() -> BrowserBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = BrowserBridge()
    return _BRIDGE


# ── Façade de haut niveau (ce que l'outil Gemini appelle) ─────────────────────

def _format(action: str, result: dict) -> str:
    """Traduit une réponse brute en phrase exploitable par le modèle."""
    if not result.get("ok"):
        return f"Échec ({action}) : {result.get('error') or 'raison inconnue'}"
    data = str(result.get("data", "")).strip()
    if action == "read":
        return data[:4000] if data else "La page ne contient aucun texte lisible."
    if action == "url":
        return f"URL courante : {data}"
    return data or "Fait."


async def run(action: str, **params) -> str:
    """Exécute une action navigateur et retourne un compte rendu lisible."""
    bridge = get_bridge()
    if not bridge.connected:
        return (
            "Le navigateur intégré n'est pas joignable — l'interface d'Ada "
            "doit être ouverte."
        )
    result = await bridge.send(action, **params)
    return _format(action, result)
