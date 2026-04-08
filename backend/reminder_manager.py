"""
reminder_manager.py — Gestion des rappels persistants d'Ada

Stockage : JSON (backend/memory/reminders.json)
Déclenchement : boucle asyncio poll toutes les 30 secondes
Quand un rappel expire : appelle le callback on_reminder(message)
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

REMINDERS_PATH = Path(__file__).parent / "memory" / "reminders.json"


class ReminderManager:
    def __init__(self):
        REMINDERS_PATH.parent.mkdir(exist_ok=True)
        self._reminders: list[dict] = self._load()
        self._task: asyncio.Task | None = None
        self.on_reminder = None  # callback(message: str) — défini par ada.py / external_bridge.py

    # ─── PERSISTANCE ─────────────────────────────────────────────────────────

    def _load(self) -> list[dict]:
        if REMINDERS_PATH.exists():
            try:
                return json.loads(REMINDERS_PATH.read_text(encoding="utf-8"))
            except Exception:
                pass
        return []

    def _save(self):
        REMINDERS_PATH.write_text(
            json.dumps(self._reminders, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ─── API ─────────────────────────────────────────────────────────────────

    def set(self, message: str, dt_iso: str) -> str:
        """
        Crée un rappel.
        dt_iso : datetime ISO 8601, ex: '2026-04-03T15:30:00' (heure locale Paris)
        Retourne une confirmation avec l'ID.
        """
        try:
            # Accepte avec ou sans timezone — on normalise en UTC
            dt = datetime.fromisoformat(dt_iso)
            if dt.tzinfo is None:
                # Assume Europe/Paris
                import zoneinfo
                dt = dt.replace(tzinfo=zoneinfo.ZoneInfo("Europe/Paris"))
            dt_utc = dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return f"Format de date invalide : '{dt_iso}'. Utilise le format ISO 8601, ex: '2026-04-03T15:30:00'."

        reminder_id = str(uuid.uuid4())[:8]
        self._reminders.append({
            "id": reminder_id,
            "message": message,
            "trigger_utc": dt_utc,
            "created_utc": datetime.now(timezone.utc).isoformat(),
        })
        self._save()

        local_str = dt.strftime("%d/%m/%Y à %H:%M")
        return f"Rappel #{reminder_id} créé : '{message}' — prévu le {local_str}."

    def list_reminders(self) -> str:
        """Liste les rappels actifs (non encore déclenchés)."""
        if not self._reminders:
            return "Aucun rappel actif."
        now_utc = datetime.now(timezone.utc)
        lines = []
        for r in sorted(self._reminders, key=lambda x: x["trigger_utc"]):
            dt = datetime.fromisoformat(r["trigger_utc"])
            import zoneinfo
            dt_local = dt.astimezone(zoneinfo.ZoneInfo("Europe/Paris"))
            remaining = dt - now_utc
            mins = int(remaining.total_seconds() // 60)
            if mins < 0:
                timing = "en attente de déclenchement"
            elif mins < 60:
                timing = f"dans {mins} min"
            else:
                timing = f"dans {mins // 60}h{mins % 60:02d}"
            lines.append(f"• #{r['id']} — {r['message']} ({dt_local.strftime('%d/%m à %H:%M')}, {timing})")
        return "\n".join(lines)

    def delete(self, reminder_id: str) -> str:
        """Supprime un rappel par son ID."""
        before = len(self._reminders)
        self._reminders = [r for r in self._reminders if r["id"] != reminder_id]
        if len(self._reminders) == before:
            return f"Rappel #{reminder_id} introuvable."
        self._save()
        return f"Rappel #{reminder_id} supprimé."

    # ─── BOUCLE DE DÉCLENCHEMENT ──────────────────────────────────────────────

    def start(self, loop: asyncio.AbstractEventLoop | None = None):
        """Lance la boucle de poll en tâche asyncio de fond."""
        if self._task and not self._task.done():
            return
        self._task = asyncio.ensure_future(self._poll_loop())

    async def _poll_loop(self):
        while True:
            await asyncio.sleep(30)
            await self._check_due()

    async def _check_due(self):
        now_utc = datetime.now(timezone.utc)
        fired = []
        remaining = []
        for r in self._reminders:
            trigger = datetime.fromisoformat(r["trigger_utc"])
            if trigger <= now_utc:
                fired.append(r)
            else:
                remaining.append(r)

        if fired:
            self._reminders = remaining
            self._save()
            for r in fired:
                print(f"[REMINDER] Déclenché : {r['message']}")
                if self.on_reminder:
                    try:
                        await self.on_reminder(r["message"])
                    except Exception as e:
                        print(f"[REMINDER] callback error: {e}")
