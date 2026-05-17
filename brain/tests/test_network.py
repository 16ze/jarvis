from brain.network import EtatEveil, ReseauAttention


def test_single_visual_novelty_does_not_spike():
    network = ReseauAttention()

    spike = network.tick_visual(presence=0.6, mouvement=0.2)

    assert spike is False
    assert network.etat == EtatEveil.SOMMEIL


def test_high_motion_can_raise_alert_without_speaking():
    network = ReseauAttention()

    spike = network.tick_visual(presence=1.0, mouvement=0.0)

    assert spike is False
    assert network.etat in {EtatEveil.SOMMEIL, EtatEveil.ALERTE}
