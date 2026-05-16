import threading
import time

from brain.neurons import NeuroneLIF


def test_spike_sur_intensite_superieure_au_seuil():
    n = NeuroneLIF("test", seuil=1.0, periode_refractaire=0.01)
    assert n.exciter(1.2) is True


def test_pas_de_spike_en_refractaire():
    n = NeuroneLIF("test", seuil=1.0, periode_refractaire=0.2)
    assert n.exciter(1.2) is True
    assert n.exciter(1.2) is False
    assert n.en_refractaire is True


def test_fuite_ramene_vers_repos():
    n = NeuroneLIF("test", seuil=1.0, fuite=0.5, periode_refractaire=0.01)
    assert n.exciter(0.8) is False
    before = n.potentiel
    assert n.exciter(0.0) is False
    assert n.potentiel < before


def test_thread_safety_concurrent_excitations():
    n = NeuroneLIF("test", seuil=50.0, fuite=0.0, periode_refractaire=0.0)

    def worker():
        for _ in range(100):
            n.exciter(0.01)
            time.sleep(0.0001)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert 0.0 <= n.potentiel <= n.seuil * 2
