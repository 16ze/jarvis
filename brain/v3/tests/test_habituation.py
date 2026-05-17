"""Tests du HabituationTracker (LRU + decay temporel)."""
import threading
import time

from brain.v3.habituation import HabituationTracker


def test_unknown_id_returns_zero():
    h = HabituationTracker(halflife_sec=120.0)
    assert h.familiarity("never:seen") == 0.0


def test_imprint_increases_familiarity():
    h = HabituationTracker(halflife_sec=120.0)
    canonical = "obj:cat:appeared"
    f0 = h.familiarity(canonical)
    h.imprint(canonical)
    f1 = h.familiarity(canonical)
    assert f1 > f0


def test_repeated_imprint_saturates_at_one():
    h = HabituationTracker(halflife_sec=3600.0)
    for _ in range(100):
        h.imprint("obj:cat:appeared")
    assert h.familiarity("obj:cat:appeared") <= 1.0
    assert h.familiarity("obj:cat:appeared") >= 0.9


def test_decay_halflife_reduces_familiarity():
    h = HabituationTracker(halflife_sec=0.1)
    h.imprint("obj:cat:appeared")
    f_before = h.familiarity("obj:cat:appeared")
    time.sleep(0.2)
    f_after = h.familiarity("obj:cat:appeared")
    assert f_after < f_before * 0.4


def test_lru_eviction_drops_oldest():
    h = HabituationTracker(halflife_sec=120.0, max_keys=3)
    h.imprint("a")
    time.sleep(0.01)
    h.imprint("b")
    time.sleep(0.01)
    h.imprint("c")
    time.sleep(0.01)
    h.imprint("d")
    assert h.familiarity("a") == 0.0
    assert h.familiarity("b") > 0.0
    assert h.familiarity("c") > 0.0
    assert h.familiarity("d") > 0.0


def test_thread_safe_imprint():
    h = HabituationTracker(halflife_sec=3600.0)

    def worker():
        for _ in range(100):
            h.imprint("obj:cat:appeared")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert h.familiarity("obj:cat:appeared") > 0.0
