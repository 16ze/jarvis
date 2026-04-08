import os
import warnings

try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    _SLACK_AVAILABLE = True
except ImportError:
    _SLACK_AVAILABLE = False


class SlackMCP:
    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN")
        self.client = None
        if not _SLACK_AVAILABLE:
            warnings.warn("[SlackMCP] slack_sdk non installé. Lancer: pip install slack_sdk", stacklevel=2)
            return
        if self._check_config():
            self.client = WebClient(token=self.token)

    def _check_config(self) -> bool:
        if not self.token:
            warnings.warn(
                "[SlackMCP] Variable d'environnement manquante : SLACK_BOT_TOKEN. "
                "Le service Slack est désactivé.",
                stacklevel=2,
            )
            return False
        return True

    def list_channels(self) -> str:
        if not self.client:
            return "Service Slack non configuré — SLACK_BOT_TOKEN manquant."
        try:
            response = self.client.conversations_list(
                types="public_channel,private_channel",
                exclude_archived=True,
                limit=200,
            )
            channels = response.get("channels", [])
            if not channels:
                return "Aucun channel trouvé."
            lines = [f"#{c['name']} (id: {c['id']})" for c in channels]
            return "\n".join(lines)
        except SlackApiError as e:
            return f"Erreur SlackMCP.list_channels: {str(e)}"
        except Exception as e:
            return f"Erreur SlackMCP.list_channels: {str(e)}"

    def read_channel(self, channel_id: str, limit: int = 20) -> str:
        if not self.client:
            return "Service Slack non configuré — SLACK_BOT_TOKEN manquant."
        try:
            response = self.client.conversations_history(
                channel=channel_id,
                limit=limit,
            )
            messages = response.get("messages", [])
            if not messages:
                return f"Aucun message dans le channel {channel_id}."
            lines = []
            for m in reversed(messages):
                user = m.get("user", m.get("bot_id", "inconnu"))
                text = m.get("text", "").replace("\n", " ")
                ts = m.get("ts", "")
                lines.append(f"[{ts}] {user}: {text}")
            return "\n".join(lines)
        except SlackApiError as e:
            return f"Erreur SlackMCP.read_channel: {str(e)}"
        except Exception as e:
            return f"Erreur SlackMCP.read_channel: {str(e)}"

    def send_message(self, channel_id: str, text: str) -> str:
        if not self.client:
            return "Service Slack non configuré — SLACK_BOT_TOKEN manquant."
        try:
            response = self.client.chat_postMessage(
                channel=channel_id,
                text=text,
            )
            ts = response.get("ts", "")
            return f"Message envoyé dans {channel_id} (ts: {ts})."
        except SlackApiError as e:
            return f"Erreur SlackMCP.send_message: {str(e)}"
        except Exception as e:
            return f"Erreur SlackMCP.send_message: {str(e)}"

    def search_messages(self, query: str, count: int = 10) -> str:
        if not self.client:
            return "Service Slack non configuré — SLACK_BOT_TOKEN manquant."
        try:
            response = self.client.search_messages(
                query=query,
                count=count,
                sort="timestamp",
                sort_dir="desc",
            )
            matches = response.get("messages", {}).get("matches", [])
            if not matches:
                return f"Aucun résultat pour '{query}'."
            lines = []
            for m in matches:
                channel_name = m.get("channel", {}).get("name", "?")
                user = m.get("username", m.get("user", "inconnu"))
                text = m.get("text", "").replace("\n", " ")[:200]
                ts = m.get("ts", "")
                lines.append(f"[#{channel_name} | {ts}] {user}: {text}")
            return "\n".join(lines)
        except SlackApiError as e:
            return f"Erreur SlackMCP.search_messages: {str(e)}"
        except Exception as e:
            return f"Erreur SlackMCP.search_messages: {str(e)}"
