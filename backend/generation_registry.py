"""Registre léger des générations texte annulables par client Socket.IO."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(slots=True)
class ActiveGeneration:
    request_id: str
    task: asyncio.Task


class GenerationRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, ActiveGeneration] = {}

    def register(self, client_id: str, request_id: str, task: asyncio.Task) -> bool:
        current = self._entries.get(client_id)
        if current is not None and not current.task.done():
            return False
        self._entries[client_id] = ActiveGeneration(request_id=request_id, task=task)
        return True

    def remove(self, client_id: str, task: asyncio.Task) -> None:
        current = self._entries.get(client_id)
        if current and current.task is task:
            self._entries.pop(client_id, None)

    def cancel(self, client_id: str, request_id: str | None = None) -> bool:
        current = self._entries.get(client_id)
        if current is None:
            return False
        if request_id and current.request_id != request_id:
            return False
        if current.task.done():
            self._entries.pop(client_id, None)
            return False

        current.task.cancel()
        return True
