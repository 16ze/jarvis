import os
import warnings

import httpx


TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


class TelegramMCP:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.default_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.client = None
        if self._check_config():
            self.client = httpx.Client(timeout=15.0)

    def _check_config(self) -> bool:
        missing = []
        if not self.token:
            missing.append("TELEGRAM_BOT_TOKEN")
        if not self.default_chat_id:
            missing.append("TELEGRAM_CHAT_ID")
        if missing:
            warnings.warn(
                f"[TelegramMCP] Variables d'environnement manquantes : {', '.join(missing)}. "
                "Le service Telegram est désactivé.",
                stacklevel=2,
            )
            return False
        return True

    def _url(self, method: str) -> str:
        return TELEGRAM_API_BASE.format(token=self.token, method=method)

    def _resolve_chat_id(self, chat_id) -> str:
        return str(chat_id) if chat_id is not None else str(self.default_chat_id)

    def send_message(self, text: str, chat_id=None) -> str:
        if not self.client:
            return "Service Telegram non configuré — variables d'environnement manquantes."
        try:
            payload = {
                "chat_id": self._resolve_chat_id(chat_id),
                "text": text,
                "parse_mode": "HTML",
            }
            response = self.client.post(self._url("sendMessage"), json=payload)
            data = response.json()
            if not data.get("ok"):
                return f"Erreur TelegramMCP.send_message: {data.get('description', 'inconnu')}"
            msg_id = data["result"]["message_id"]
            return f"Message Telegram envoyé (id: {msg_id})."
        except Exception as e:
            return f"Erreur TelegramMCP.send_message: {str(e)}"

    def send_photo(self, photo_url: str, caption: str = "", chat_id=None) -> str:
        if not self.client:
            return "Service Telegram non configuré — variables d'environnement manquantes."
        try:
            payload = {
                "chat_id": self._resolve_chat_id(chat_id),
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "HTML",
            }
            response = self.client.post(self._url("sendPhoto"), json=payload)
            data = response.json()
            if not data.get("ok"):
                return f"Erreur TelegramMCP.send_photo: {data.get('description', 'inconnu')}"
            msg_id = data["result"]["message_id"]
            return f"Photo Telegram envoyée (id: {msg_id})."
        except Exception as e:
            return f"Erreur TelegramMCP.send_photo: {str(e)}"

    def get_updates(self, limit: int = 10) -> str:
        if not self.client:
            return "Service Telegram non configuré — variables d'environnement manquantes."
        try:
            params = {"limit": limit, "timeout": 0}
            response = self.client.get(self._url("getUpdates"), params=params)
            data = response.json()
            if not data.get("ok"):
                return f"Erreur TelegramMCP.get_updates: {data.get('description', 'inconnu')}"
            updates = data.get("result", [])
            if not updates:
                return "Aucun message reçu."
            lines = []
            for u in updates:
                msg = u.get("message") or u.get("edited_message", {})
                if not msg:
                    continue
                sender = msg.get("from", {})
                name = sender.get("username") or sender.get("first_name", "inconnu")
                text = msg.get("text", "(media)")
                date = msg.get("date", "")
                chat = msg.get("chat", {}).get("id", "?")
                lines.append(f"[{date}] @{name} (chat: {chat}): {text}")
            return "\n".join(lines) if lines else "Aucun message texte dans les updates."
        except Exception as e:
            return f"Erreur TelegramMCP.get_updates: {str(e)}"
