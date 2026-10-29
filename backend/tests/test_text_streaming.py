"""Tests unitaires du protocole de streaming texte, sans réseau ni clé API."""

import base64
from types import SimpleNamespace

import pytest

from text_streaming import (
    TextGenerationState,
    collect_gemini_stream,
    decode_image_payload,
    deduplicate_function_calls,
    run_streamed_text_turn,
)


def _chunk(*parts: object) -> SimpleNamespace:
    content = SimpleNamespace(parts=list(parts))
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(candidates=[candidate])


async def _stream(*chunks: object):
    for chunk in chunks:
        yield chunk


@pytest.mark.asyncio
async def test_collect_gemini_stream_emits_each_text_delta_in_order() -> None:
    received: list[str] = []

    async def on_delta(delta: str) -> None:
        received.append(delta)

    result = await collect_gemini_stream(
        _stream(
            _chunk(SimpleNamespace(text="Bon", thought=False, function_call=None)),
            _chunk(SimpleNamespace(text="jour", thought=False, function_call=None)),
        ),
        on_delta=on_delta,
    )

    assert received == ["Bon", "jour"]
    assert result.text == "Bonjour"
    assert len(result.parts) == 2


@pytest.mark.asyncio
async def test_collect_gemini_stream_keeps_tool_parts_without_emitting_them() -> None:
    received: list[str] = []
    tool_part = SimpleNamespace(text=None, thought=False, function_call=object())
    thought_part = SimpleNamespace(text="raisonnement privé", thought=True, function_call=None)

    result = await collect_gemini_stream(
        _stream(_chunk(tool_part, thought_part)),
        on_delta=received.append,
    )

    assert received == []
    assert result.text == ""
    assert result.parts == [tool_part, thought_part]


@pytest.mark.asyncio
async def test_text_generation_state_tracks_concurrency_and_cleans_up() -> None:
    state = TextGenerationState()

    assert state.is_active is False
    async with state.track():
        assert state.is_active is True
        async with state.track():
            assert state.is_active is True
        assert state.is_active is True
    assert state.is_active is False


@pytest.mark.asyncio
async def test_text_generation_state_cleans_up_after_error() -> None:
    state = TextGenerationState()

    with pytest.raises(RuntimeError):
        async with state.track():
            raise RuntimeError("échec simulé")

    assert state.is_active is False


def test_deduplicate_function_calls_keeps_latest_part_by_id() -> None:
    first = SimpleNamespace(
        function_call=SimpleNamespace(id="call-1", name="outil", args={"q": "ancien"})
    )
    latest = SimpleNamespace(
        function_call=SimpleNamespace(id="call-1", name="outil", args={"q": "final"})
    )

    assert deduplicate_function_calls([first, latest]) == [latest]


def test_decode_image_payload_accepts_only_valid_images() -> None:
    image = b"image-test"

    assert decode_image_payload(
        {"mime_type": "image/jpeg", "data": base64.b64encode(image).decode()}
    ) == (image, "image/jpeg")
    assert decode_image_payload({"mime_type": "text/plain", "data": "abc"}) is None
    assert decode_image_payload({"mime_type": "image/jpeg", "data": "!!!"}) is None


@pytest.mark.asyncio
async def test_streamed_text_turn_orders_speaking_and_deltas_without_duplicate() -> None:
    events: list[tuple[str, object]] = []
    state = TextGenerationState()

    async def generate(on_delta) -> str:
        await on_delta("Bon")
        await on_delta("jour")
        return "Bonjour"

    await run_streamed_text_turn(
        generate=generate,
        emit_delta=lambda delta: events.append(("delta", delta)),
        set_active=lambda on: events.append(("speaking", on)),
        state=state,
        remaining_active=lambda: state.is_active,
    )

    assert events == [
        ("speaking", True),
        ("delta", "Bon"),
        ("delta", "jour"),
        ("speaking", False),
    ]


@pytest.mark.asyncio
async def test_streamed_text_turn_cleans_up_and_marks_partial_error() -> None:
    events: list[tuple[str, object]] = []
    state = TextGenerationState()

    async def generate(on_delta) -> str:
        await on_delta("Début")
        raise RuntimeError("échec simulé")

    await run_streamed_text_turn(
        generate=generate,
        emit_delta=lambda delta: events.append(("delta", delta)),
        set_active=lambda on: events.append(("speaking", on)),
        state=state,
        remaining_active=lambda: state.is_active,
    )

    assert events == [
        ("speaking", True),
        ("delta", "Début"),
        ("delta", "\n\n_Réponse interrompue par une erreur._"),
        ("speaking", False),
    ]
