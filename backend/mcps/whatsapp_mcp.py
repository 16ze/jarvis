import os
import warnings

import httpx


class WhatsAppMCP:
    def __init__(self):
        self.api_url = os.getenv("WHATSAPP_API_URL", "").rstrip("/")
        self.api_key = os.getenv("WHATSAPP_API_KEY")
        self.instance = os.getenv("WHATSAPP_INSTANCE")
        self.default_number = os.getenv("WHATSAPP_DEFAULT_NUMBER")
        self.client = None
        if self._check_config():
            self.client = httpx.Client(
                timeout=20.0,
                headers={
                    "apikey": self.api_key,
                    "Content-Type": "application/json",
                },
            )

    def _check_config(self) -> bool:
        missing = [
            name
            for name, val in [
                ("WHATSAPP_API_URL", self.api_url),
                ("WHATSAPP_API_KEY", self.api_key),
                ("WHATSAPP_INSTANCE", self.instance),
                ("WHATSAPP_DEFAULT_NUMBER", self.default_number),
            ]
            if not val
        ]
        if missing:
            warnings.warn(
                f"[WhatsAppMCP] Variables d'environnement manquantes : {', '.join(missing)}. "
                "Le service WhatsApp est désactivé.",
                stacklevel=2,
            )
            return False
        return True

    def _endpoint(self, path: str) -> str:
        return f"{self.api_url}/{path}/{self.instance}"

    def send_message(self, number: str, text: str) -> str:
        """
        Envoie un message texte.
        number format : "33612345678@s.whatsapp.net"
        """
        if not self.client:
            return "Service WhatsApp non configuré — variables d'environnement manquantes."
        try:
            payload = {
                "number": number,
                "text": text,
            }
            response = self.client.post(
                self._endpoint("message/sendText"),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            msg_id = data.get("key", {}).get("id") or data.get("id", "?")
            return f"Message WhatsApp envoyé à {number} (id: {msg_id})."
        except httpx.HTTPStatusError as e:
            return f"Erreur WhatsAppMCP.send_message: HTTP {e.response.status_code} — {e.response.text[:200]}"
        except Exception as e:
            return f"Erreur WhatsAppMCP.send_message: {str(e)}"

    def send_media(self, number: str, media_url: str, caption: str = "") -> str:
        """
        Envoie un fichier ou une image via URL.
        number format : "33612345678@s.whatsapp.net"
        """
        if not self.client:
            return "Service WhatsApp non configuré — variables d'environnement manquantes."
        try:
            payload = {
                "number": number,
                "mediaUrl": media_url,
                "caption": caption,
            }
            response = self.client.post(
                self._endpoint("message/sendMedia"),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            msg_id = data.get("key", {}).get("id") or data.get("id", "?")
            return f"Média WhatsApp envoyé à {number} (id: {msg_id})."
        except httpx.HTTPStatusError as e:
            return f"Erreur WhatsAppMCP.send_media: HTTP {e.response.status_code} — {e.response.text[:200]}"
        except Exception as e:
            return f"Erreur WhatsAppMCP.send_media: {str(e)}"

    def get_recent_messages(self, number: str, limit: int = 20) -> str:
        """
        Récupère les messages récents d'une conversation.
        number format : "33612345678@s.whatsapp.net"
        """
        if not self.client:
            return "Service WhatsApp non configuré — variables d'environnement manquantes."
        try:
            params = {"count": limit}
            response = self.client.get(
                self._endpoint(f"chat/findMessages/{number}"),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            messages = data if isinstance(data, list) else data.get("messages", [])
            if not messages:
                return f"Aucun message trouvé pour {number}."

            lines = []
            for m in messages[-limit:]:
                key = m.get("key", {})
                from_me = key.get("fromMe", False)
                direction = "Moi" if from_me else "Eux"
                msg_content = m.get("message", {})
                text = (
                    msg_content.get("conversation")
                    or msg_content.get("extendedTextMessage", {}).get("text")
                    or "(media)"
                )
                timestamp = m.get("messageTimestamp", "")
                lines.append(f"[{timestamp}] {direction}: {text}")
            return "\n".join(lines)
        except httpx.HTTPStatusError as e:
            return f"Erreur WhatsAppMCP.get_recent_messages: HTTP {e.response.status_code} — {e.response.text[:200]}"
        except Exception as e:
            return f"Erreur WhatsAppMCP.get_recent_messages: {str(e)}"
