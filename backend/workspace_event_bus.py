"""Bus d'événements Socket.IO pour ADA OS Environment."""

from __future__ import annotations

from typing import Awaitable, Callable


EmitCallable = Callable[[str, dict], Awaitable[None]]


class WorkspaceEventBus:
    def __init__(self, emit: EmitCallable | None = None):
        self._emit = emit

    async def emit_status(self, message: str, level: str = "info") -> None:
        await self._safe_emit("workspace_status", {"message": message, "level": level})

    async def emit_item_created(self, item: dict) -> None:
        await self._safe_emit("workspace_item_created", item)

    async def emit_activity(self, activity: dict) -> None:
        await self._safe_emit("workspace_activity", activity)

    async def emit_state(self, state: dict) -> None:
        await self._safe_emit("workspace_state", state)

    async def emit_research_result(
        self,
        workspace: str,
        markdown: str,
        *,
        query: str = "",
        depth: str = "standard",
        synthesized: bool = False,
        results: list[dict] | None = None,
    ) -> None:
        payload = {
            "workspace": workspace,
            "markdown": markdown,
            "query": query,
            "depth": depth,
            "synthesized": synthesized,
            "results": results or [],
        }
        await self._safe_emit("workspace_research_result", payload)

    async def emit_browser_frame(self, image: str | None, log: str) -> None:
        await self._safe_emit("workspace_browser_frame", {"image": image, "log": log})

    async def _safe_emit(self, event: str, payload: dict) -> None:
        if not self._emit:
            return
        await self._emit(event, payload)
