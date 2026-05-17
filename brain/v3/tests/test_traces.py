"""Tests du ring buffer ShortTermMemory."""
import time

from brain.v3.traces import ShortTermMemory
from brain.v3.types import ReactionDecision, Stimulus


def _stim(canonical: str = "obj:cat:appeared") -> Stimulus:
    return Stimulus(canonical, "vision_object", 0.5, 0.0, "none", 0.3, time.monotonic(), {})


def _dec(action: str = "REACT") -> ReactionDecision:
    return ReactionDecision(action, 0.6, "react", 0.2, None)


def test_append_and_recent():
    mem = ShortTermMemory(window_sec=60.0)
    mem.append(_stim(), _dec())
    items = mem.recent(n=10)
    assert len(items) == 1
    assert items[0]["stimulus"] == "obj:cat:appeared"
    assert items[0]["action"] == "REACT"


def test_recent_limits_n():
    mem = ShortTermMemory(window_sec=60.0)
    for i in range(20):
        mem.append(_stim(f"obj:cat:{i}"), _dec())
    items = mem.recent(n=5)
    assert len(items) == 5
    # ordre récent en premier
    assert items[0]["stimulus"] == "obj:cat:19"


def test_window_drops_old_entries():
    mem = ShortTermMemory(window_sec=0.05)
    mem.append(_stim("old"), _dec())
    time.sleep(0.1)
    mem.append(_stim("new"), _dec())
    items = mem.recent(n=10)
    assert len(items) == 1
    assert items[0]["stimulus"] == "new"


def test_thread_safe_append():
    import threading

    mem = ShortTermMemory(window_sec=60.0)

    def worker():
        for _ in range(50):
            mem.append(_stim(), _dec())

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    items = mem.recent(n=500)
    assert len(items) == 200
