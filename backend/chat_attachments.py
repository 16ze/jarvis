"""Validation des pièces jointes image envoyées dans le fil de conversation.

Le chemin texte d'Ada accepte déjà un ``image_payload`` au format
``{"mime_type": "image/jpeg", "data": "<base64>"}`` (même canal que la frame
caméra/écran). Ce module normalise/valide une pièce jointe envoyée par le front
avant de la transmettre à ``process_text_message``. Zéro dépendance lourde.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any


# Types MIME image acceptés (Gemini multimodal).
ALLOWED_MIME_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif"}
)

# Plafond sur les octets décodés (6 Mo) — borne la charge réseau et mémoire.
MAX_IMAGE_BYTES = 6 * 1024 * 1024


def normalize_image_attachment(raw: Any) -> dict[str, str] | None:
    """Retourne un ``{"mime_type", "data"}`` valide, ou ``None`` si invalide/absent.

    Ne lève jamais : toute entrée douteuse renvoie ``None`` (l'appelant retombe
    alors sur l'éventuelle frame caméra). ``data`` est une chaîne base64 nue
    (sans préfixe ``data:``), telle qu'attendue par le pipeline existant.
    """

    if not isinstance(raw, dict):
        return None

    mime_type = raw.get("mime_type") or raw.get("mimeType")
    data = raw.get("data")
    if not isinstance(mime_type, str) or not isinstance(data, str):
        return None

    mime_type = mime_type.strip().lower()
    if mime_type not in ALLOWED_MIME_TYPES:
        return None

    # Tolère un préfixe data-URL « data:image/png;base64, » et le retire.
    if data.startswith("data:"):
        comma = data.find(",")
        if comma == -1:
            return None
        data = data[comma + 1 :]

    data = data.strip()
    if not data:
        return None

    # Vérifie que c'est bien du base64 décodable et sous le plafond.
    try:
        decoded = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not decoded or len(decoded) > MAX_IMAGE_BYTES:
        return None

    return {"mime_type": mime_type, "data": data}
