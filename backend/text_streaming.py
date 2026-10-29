"""Primitives légères pour le streaming des réponses texte d'Ada."""

from __future__ import annotations

import asyncio
import base64
import binascii
import inspect
import json
from collections.abc import AsyncIterable, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator


TextDeltaCallback = Callable[[str], Awaitable[None] | None]
ActiveStateCallback = Callable[[bool], Awaitable[None] | None]


@dataclass(frozen=True, slots=True)
class StreamedResponse:
    """Contenu agrégé d'une réponse Gemini reçue par petits deltas."""

    parts: list[Any]
    text: str


async def collect_gemini_stream(
    stream: AsyncIterable[Any],
    on_delta: TextDeltaCallback | None = None,
) -> StreamedResponse:
    """Collecte un flux Gemini tout en transmettant immédiatement ses deltas texte."""

    parts: list[Any] = []
    text_chunks: list[str] = []

    async for chunk in stream:
        candidates = getattr(chunk, "candidates", None) or []
        if not candidates:
            continue

        content = getattr(candidates[0], "content", None)
        for part in (getattr(content, "parts", None) or []):
            parts.append(part)
            delta = getattr(part, "text", None)
            if not delta or getattr(part, "thought", False):
                continue

            text_chunks.append(delta)
            if on_delta is not None:
                callback_result = on_delta(delta)
                if inspect.isawaitable(callback_result):
                    await callback_result

    return StreamedResponse(parts=parts, text="".join(text_chunks))


def deduplicate_function_calls(parts: list[Any]) -> list[Any]:
    """Conserve un seul exemplaire de chaque function call streamé."""

    result: list[Any] = []
    indexes_by_id: dict[str, int] = {}
    calls_without_id: set[tuple[str, str]] = set()

    for part in parts:
        function_call = getattr(part, "function_call", None)
        if function_call is None:
            result.append(part)
            continue

        call_id = str(getattr(function_call, "id", "") or "")
        if call_id:
            if call_id in indexes_by_id:
                result[indexes_by_id[call_id]] = part
            else:
                indexes_by_id[call_id] = len(result)
                result.append(part)
            continue

        name = str(getattr(function_call, "name", "") or "")
        raw_args = getattr(function_call, "args", {}) or {}
        try:
            stable_args = json.dumps(dict(raw_args), sort_keys=True, default=str)
        except (TypeError, ValueError):
            stable_args = str(raw_args)
        key = (name, stable_args)
        if key not in calls_without_id:
            calls_without_id.add(key)
            result.append(part)

    return result


def decode_image_payload(payload: dict[str, Any] | None) -> tuple[bytes, str] | None:
    """Valide et décode le format image interne utilisé par la session Live."""

    if not payload:
        return None

    mime_type = str(payload.get("mime_type", "")).strip()
    encoded_data = payload.get("data")
    if not mime_type.startswith("image/") or not encoded_data:
        return None

    try:
        if isinstance(encoded_data, str):
            image_bytes = base64.b64decode(encoded_data, validate=True)
        elif isinstance(encoded_data, bytes):
            image_bytes = encoded_data
        else:
            return None
    except (binascii.Error, ValueError, TypeError):
        return None

    return (image_bytes, mime_type) if image_bytes else None


class TextGenerationState:
    """Compte les générations texte actives sans confondre texte et audio."""

    def __init__(self) -> None:
        self._active_count = 0

    @property
    def is_active(self) -> bool:
        return self._active_count > 0

    @asynccontextmanager
    async def track(self) -> AsyncIterator[None]:
        self._active_count += 1
        try:
            yield
        finally:
            self._active_count = max(0, self._active_count - 1)


async def run_streamed_text_turn(
    generate: Callable[[TextDeltaCallback], Awaitable[str]],
    emit_delta: TextDeltaCallback,
    set_active: ActiveStateCallback,
    state: TextGenerationState,
    remaining_active: Callable[[], bool],
    on_error: Callable[[Exception], None] | None = None,
) -> None:
    """Orchestre un tour texte et garantit le contrat d'événements de l'UI."""

    emitted_delta = False

    async def _call(callback: Callable[..., Any], *args: Any) -> None:
        result = callback(*args)
        if inspect.isawaitable(result):
            await result

    async def _forward(delta: str) -> None:
        nonlocal emitted_delta
        if not delta:
            return
        emitted_delta = True
        await _call(emit_delta, delta)

    try:
        async with state.track():
            await _call(set_active, True)
            reply = await generate(_forward)
            if reply and not emitted_delta:
                await _forward(reply)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if on_error is not None:
            on_error(exc)
        error_delta = (
            "Désolé, une erreur est survenue pendant la génération de la réponse."
            if not emitted_delta
            else "\n\n_Réponse interrompue par une erreur._"
        )
        await _forward(error_delta)
    finally:
        await _call(set_active, remaining_active())
