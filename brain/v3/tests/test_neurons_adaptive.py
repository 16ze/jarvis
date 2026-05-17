"""Tests du neurone AdaptiveLIF (LIF + threshold drift + AHP + modulation)."""
import threading
import time

from brain.v3.neurons import AdaptiveLIF


def test_spike_above_threshold():
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.01)
    assert n.exciter(1.2) is True


def test_refractory_blocks_immediate_repeat():
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.5)
    assert n.exciter(1.5) is True
    assert n.exciter(1.5) is False


def test_modulation_lowers_effective_threshold():
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.01)
    assert n.exciter(0.7) is False
    n2 = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.01)
    assert n2.exciter(0.7, modulation=0.6) is True


def test_threshold_drift_up_after_spike():
    n = AdaptiveLIF(
        "test",
        seuil_base=1.0,
        periode_refractaire=0.0,
        threshold_drift_rate=0.05,
        threshold_max=2.0,
    )
    before = n.seuil_courant
    assert n.exciter(1.5) is True
    after = n.seuil_courant
    assert after > before


def test_threshold_drift_down_when_no_spike():
    n = AdaptiveLIF(
        "test",
        seuil_base=1.0,
        periode_refractaire=0.0,
        threshold_drift_rate=0.1,
        threshold_max=2.0,
        threshold_min=0.5,
    )
    n._seuil_courant = 1.5
    n.exciter(0.0)
    assert n._seuil_courant < 1.5


def test_ahp_post_spike_makes_next_excitation_harder():
    n = AdaptiveLIF(
        "test",
        seuil_base=1.0,
        periode_refractaire=0.0,
        ahp_amplitude=0.5,
        ahp_decay=0.99,
    )
    assert n.exciter(1.5) is True
    assert n.exciter(1.0) is False


def test_threshold_stays_within_bounds():
    n = AdaptiveLIF(
        "test",
        seuil_base=1.0,
        periode_refractaire=0.0,
        threshold_drift_rate=0.5,
        threshold_min=0.4,
        threshold_max=2.0,
    )
    for _ in range(100):
        n.exciter(3.0)
    assert n.seuil_courant <= 2.0
    n2 = AdaptiveLIF(
        "test2",
        seuil_base=1.0,
        threshold_drift_rate=0.5,
        threshold_min=0.4,
        threshold_max=2.0,
    )
    for _ in range(100):
        n2.exciter(0.0)
    assert n2.seuil_courant >= 0.4


def test_thread_safety_concurrent_excitations():
    n = AdaptiveLIF(
        "test",
        seuil_base=50.0,
        fuite=0.0,
        periode_refractaire=0.0,
        threshold_drift_rate=0.0,
    )

    def worker():
        for _ in range(100):
            n.exciter(0.01)
            time.sleep(0.0001)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert n._potentiel >= 0.0
