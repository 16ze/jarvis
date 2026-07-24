"""Tests de la vie mentale au repos (backend/idle_mind.py)."""

import asyncio
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from idle_mind import IdleMind  # noqa: E402

SNAPSHOT = {"cortisol": 0.70, "dopamine": 0.30, "oxytocine": 0.40,
            "serotonine": 0.30, "mood": "Contrariété"}


class FakeMemory:
    def __init__(self, traces=None, associations=None):
        self._traces = traces if traces is not None else ["User: Vercel a échoué"]
        self._assoc = associations if associations is not None else []
        self.saved = []
        self.last_search_state = "unset"

    def recent_conversations(self, n=6):
        return list(self._traces)

    def search_memory(self, query, n_results=5, emotional_state=None):
        self.last_search_state = emotional_state
        return [{"content": c} for c in self._assoc]

    def save_conversation(self, content, metadata=None, emotional_state=None):
        self.saved.append({"content": content, "metadata": metadata,
                           "emotional_state": emotional_state})


class FakeBrain:
    def get_affect_snapshot(self):
        return dict(SNAPSHOT)


def make_client(payload, capture=None):
    """Client LLM factice renvoyant `payload` (dict ou str brute)."""
    text = payload if isinstance(payload, str) else json.dumps(payload)

    class _Client:
        class aio:
            class models:
                @staticmethod
                async def generate_content(**kwargs):
                    if capture is not None:
                        capture["prompt"] = kwargs.get("contents", "")
                    resp = types.SimpleNamespace()
                    resp.text = text
                    return resp

    return _Client()


def _mind(payload, memory=None, capture=None) -> tuple[IdleMind, FakeMemory]:
    mem = memory or FakeMemory()
    mind = IdleMind(memory=mem, brain=FakeBrain(), client=make_client(payload, capture))
    return mind, mem


def test_rumination_consolidates_reflection_into_memory():
    """Ce qu'Ada retient est écrit en mémoire, marqué de son affect."""
    mind, mem = _mind({"reflection": "Vercel bloque souvent.",
                       "thought": "j'ai repensé à Vercel", "share": True})
    asyncio.run(mind.ruminate())

    assert len(mem.saved) == 1
    entry = mem.saved[0]
    assert "[réflexion]" in entry["content"]
    assert entry["metadata"]["type"] == "reflection"
    assert entry["emotional_state"]["mood"] == "Contrariété"


def test_shared_thought_is_available_once_then_consumed():
    mind, _ = _mind({"reflection": "r", "thought": "j'ai repensé à ça", "share": True})
    asyncio.run(mind.ruminate())

    assert mind.has_pending_thought
    assert mind.take_thought()["thought"] == "j'ai repensé à ça"
    assert mind.take_thought() is None  # consommée


def test_unshared_thought_stays_silent():
    """share=false : Ada garde sa pensée pour elle."""
    mind, mem = _mind({"reflection": "pensée banale", "thought": "bof", "share": False})
    asyncio.run(mind.ruminate())

    assert mind.has_pending_thought is False
    assert len(mem.saved) == 1  # consolidée quand même


def test_associations_are_filtered_by_current_mood():
    """Le rappel associatif passe par l'humeur (congruence)."""
    mem = FakeMemory(associations=["souvenir lié"])
    mind, _ = _mind({"reflection": "r", "thought": "t", "share": True}, memory=mem)
    asyncio.run(mind.ruminate())

    assert mem.last_search_state is not None
    assert mem.last_search_state["mood"] == "Contrariété"


def test_prompt_contains_traces_associations_and_mood(capsys):
    capture = {}
    mem = FakeMemory(traces=["User: Vercel a échoué"], associations=["déjà bloqué avant"])
    mind, _ = _mind({"reflection": "r", "thought": "t", "share": True},
                    memory=mem, capture=capture)
    asyncio.run(mind.ruminate(idle_for=900))

    prompt = capture["prompt"]
    assert "Vercel" in prompt              # trace récente
    assert "déjà bloqué avant" in prompt   # association
    assert "Contrariété" in prompt         # humeur
    assert "15 min" in prompt              # durée d'absence


def test_no_traces_means_no_rumination():
    mem = FakeMemory(traces=[])
    mind, _ = _mind({"reflection": "r", "thought": "t", "share": True}, memory=mem)
    assert asyncio.run(mind.ruminate()) is None
    assert mem.saved == []


def test_markdown_wrapped_json_is_parsed():
    mind, mem = _mind('```json\n{"reflection":"r","thought":"t","share":true}\n```')
    assert asyncio.run(mind.ruminate()) is not None
    assert len(mem.saved) == 1


def test_unparseable_answer_never_raises():
    mind, mem = _mind("ceci n'est pas du JSON")
    assert asyncio.run(mind.ruminate()) is None
    assert mem.saved == []


def test_activity_resets_idle_timer():
    mind, _ = _mind({"reflection": "r", "thought": "t", "share": True})
    before = mind._last_activity
    mind.notify_activity()
    assert mind._last_activity >= before


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("IDLE_MIND_ENABLED", "false")
    mind, _ = _mind({"reflection": "r", "thought": "t", "share": True})
    assert mind.enabled is False
    mind.start()
    assert mind._task is None  # aucune boucle lancée


def test_history_keeps_recent_reflections():
    mind, _ = _mind({"reflection": "une pensée", "thought": "t", "share": False})
    asyncio.run(mind.ruminate())
    asyncio.run(mind.ruminate())
    assert len(mind.recent_reflections()) == 2
