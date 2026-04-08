"""
MonitoringAgent — Sub-agent de surveillance d'événements en background.

Architecture :
  - run(watch_config)  : parse la config JSON (ou langage naturel via Gemini),
                         lance chaque watcher via asyncio.create_task() — NON bloquant
  - stop()             : annule tous les create_task watchers
  - _watch_loop(cfg)   : boucle de polling pour un watcher unique
  - _evaluate_condition: Gemini décide si la condition est déclenchée
  - _send_notification : Telegram ou Slack selon config

watch_config JSON exemple :
{
  "watchers": [
    {
      "id": "emails_non_lus",
      "type": "email",
      "interval_seconds": 120,
      "condition": "nouvel email non lu de clients ou prospects",
      "notify": "telegram",
      "notify_target": ""
    },
    {
      "id": "github_prs",
      "type": "github_prs",
      "interval_seconds": 300,
      "condition": "nouvelle PR ouverte ou PR reviewée",
      "notify": "telegram",
      "notify_target": ""
    }
  ]
}

Types de watcher supportés : email | slack_channel | github_issues | github_prs | telegram

Usage depuis ada.py :
    result = await self.monitoring_agent.run(watch_config_json_str)
    result = await self.monitoring_agent.stop()
"""

import asyncio
import json
import os
import re
from typing import Optional

from google import genai

SUB_MODEL = "gemini-2.0-flash-lite"
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


class MonitoringAgent:
    def __init__(
        self,
        telegram=None,
        slack=None,
        github=None,
        google_agent=None,
    ):
        self._telegram = telegram
        self._slack = slack
        self._github = github
        self._google_agent = google_agent

        self._tasks: list[asyncio.Task] = []
        self._running = False

    # ─── PUBLIC ──────────────────────────────────────────────────────────────

    async def run(self, watch_config: str) -> str:
        """Parse la config et démarre les watchers. Non-bloquant (create_task)."""
        config = await self._parse_config(watch_config)
        watchers = config.get("watchers", [])
        if not watchers:
            return "Aucun watcher défini dans la configuration."

        self._running = True
        started: list[str] = []
        for watcher in watchers:
            task = asyncio.create_task(self._watch_loop(watcher))
            self._tasks.append(task)
            started.append(watcher.get("id") or watcher.get("type", "?"))

        return (
            f"Monitoring démarré : {', '.join(started)} "
            f"({len(started)} watcher(s) actif(s))."
        )

    async def stop(self) -> str:
        """Annule tous les watchers en cours."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        count = len(self._tasks)
        self._tasks.clear()
        return f"{count} watcher(s) arrêté(s)."

    # ─── CONFIG PARSING ──────────────────────────────────────────────────────

    async def _parse_config(self, watch_config: str) -> dict:
        """Tente JSON direct, puis Gemini pour le langage naturel."""
        try:
            return json.loads(watch_config)
        except json.JSONDecodeError:
            pass

        response = await _client.aio.models.generate_content(
            model=SUB_MODEL,
            contents=(
                "Convertis cette description de monitoring en JSON valide.\n\n"
                f"{watch_config}\n\n"
                "Format attendu :\n"
                '{"watchers": [{"id": "...", "type": "email|slack_channel|github_issues|'
                'github_prs|telegram", "interval_seconds": 60, '
                '"condition": "...", "notify": "telegram|slack", '
                '"notify_target": ""}]}\n\n'
                "Réponds UNIQUEMENT avec le JSON."
            ),
        )
        try:
            m = re.search(r"\{.*\}", response.text, re.DOTALL)
            return json.loads(m.group())
        except Exception:
            return {}

    # ─── WATCHER LOOP ────────────────────────────────────────────────────────

    async def _watch_loop(self, watcher: dict):
        """Boucle de surveillance pour un watcher unique. Lancée via create_task."""
        watcher_id = watcher.get("id") or watcher.get("type", "unknown")
        watcher_type = watcher.get("type", "")
        interval = max(10, int(watcher.get("interval_seconds", 60)))
        condition = watcher.get("condition", "")
        notify = watcher.get("notify", "telegram")
        notify_target = watcher.get("notify_target", "") or None

        print(f"[MonitoringAgent] Watcher '{watcher_id}' démarré (interval={interval}s)")

        while self._running:
            try:
                data = await self._fetch_data(watcher_type, watcher)
                if data:
                    notification = await self._evaluate_condition(data, condition)
                    if notification:
                        await self._send_notification(notification, notify, notify_target)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[MonitoringAgent] Watcher '{watcher_id}' erreur : {e}")

            await asyncio.sleep(interval)

        print(f"[MonitoringAgent] Watcher '{watcher_id}' arrêté.")

    # ─── DATA FETCHING ───────────────────────────────────────────────────────

    async def _fetch_data(self, watcher_type: str, watcher: dict) -> Optional[str]:
        """Récupère les données selon le type de watcher."""
        try:
            if watcher_type == "email" and self._google_agent:
                return await asyncio.to_thread(
                    self._google_agent.read_emails, 10, "is:unread"
                )
            elif watcher_type == "slack_channel" and self._slack:
                channel_id = watcher.get("channel_id", "")
                if channel_id:
                    return await asyncio.to_thread(
                        self._slack.read_channel, channel_id, 10
                    )
            elif watcher_type == "github_issues" and self._github:
                repo = watcher.get("repo", "")
                return await asyncio.to_thread(
                    self._github.list_issues, repo, "open", 10
                )
            elif watcher_type == "github_prs" and self._github:
                repo = watcher.get("repo", "")
                return await asyncio.to_thread(
                    self._github.list_prs, repo, "open", 10
                )
            elif watcher_type == "telegram" and self._telegram:
                return await asyncio.to_thread(self._telegram.get_updates, 5)
        except Exception as e:
            print(f"[MonitoringAgent] Fetch error ({watcher_type}) : {e}")
        return None

    # ─── CONDITION EVALUATION ────────────────────────────────────────────────

    async def _evaluate_condition(
        self, data: str, condition: str
    ) -> Optional[str]:
        """Demande à Gemini si la condition est déclenchée. Retourne le message ou None."""
        response = await _client.aio.models.generate_content(
            model=SUB_MODEL,
            contents=(
                "Tu surveilles les données suivantes :\n"
                f"{data[:1500]}\n\n"
                f"Condition à vérifier : {condition}\n\n"
                "La condition est-elle déclenchée ?\n"
                "- Si OUI : retourne un message de notification court et factuel (1-2 phrases).\n"
                "- Si NON : retourne exactement le mot NO_TRIGGER et rien d'autre.\n\n"
                "Réponds UNIQUEMENT avec le message OU NO_TRIGGER."
            ),
        )
        result = (response.text or "").strip()
        if result and result != "NO_TRIGGER":
            return result
        return None

    # ─── NOTIFICATIONS ───────────────────────────────────────────────────────

    async def _send_notification(
        self, message: str, notify: str, target: Optional[str]
    ):
        """Envoie la notification via le canal configuré."""
        print(f"[MonitoringAgent] TRIGGER : {message[:120]}")
        full_message = f"[Ada Monitoring] {message}"
        try:
            if notify == "telegram" and self._telegram:
                await asyncio.to_thread(
                    self._telegram.send_message, full_message, target
                )
            elif notify == "slack" and self._slack and target:
                await asyncio.to_thread(
                    self._slack.send_message, target, full_message
                )
        except Exception as e:
            print(f"[MonitoringAgent] Erreur notification : {e}")
