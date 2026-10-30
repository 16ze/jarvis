"""Tests du registre d'annulation des générations texte."""

import asyncio

import pytest

from generation_registry import GenerationRegistry


@pytest.mark.asyncio
async def test_cancel_only_matching_request() -> None:
    registry = GenerationRegistry()
    task = asyncio.create_task(asyncio.sleep(30))
    assert registry.register("client-1", "request-1", task) is True

    assert registry.cancel("client-1", "autre-request") is False
    assert task.cancelled() is False
    assert registry.cancel("client-1", "request-1") is True

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_remove_does_not_delete_a_newer_generation() -> None:
    registry = GenerationRegistry()
    old_task = asyncio.create_task(asyncio.sleep(30))
    new_task = asyncio.create_task(asyncio.sleep(30))
    assert registry.register("client-1", "old", old_task) is True
    assert registry.register("client-1", "new", new_task) is False

    registry.remove("client-1", old_task)
    assert registry.register("client-1", "new", new_task) is True
    assert registry.cancel("client-1", "new") is True

    old_task.cancel()
    for task in (old_task, new_task):
        with pytest.raises(asyncio.CancelledError):
            await task
