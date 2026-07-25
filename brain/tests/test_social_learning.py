"""Tests de la boucle de feedback social (brain/social_learning.py).

Vérifie qu'Ada apprend comment ses prises de parole sont reçues et calibre son
TIMING — et jamais ce qu'elle ressent.
"""

import pytest

from brain.limbic import CerveauEmotif
from brain.social_learning import SocialLearning


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_SOCIAL_PATH", str(tmp_path / "social.json"))


def _feedback(engine, mood, valence, n=8, t0=1000.0):
    for i in range(n):
        at = t0 + i * 300
        engine.register_expression(mood, now=at)
        engine.register_reaction(valence, now=at + 20)


def test_learns_that_a_mood_lands_badly():
    s = SocialLearning()
    _feedback(s, "Agacement", -0.7)
    score, confiance = s.reception_score("Agacement")
    assert score < -0.3
    assert confiance == pytest.approx(1.0)


def test_learns_that_a_mood_lands_well():
    s = SocialLearning()
    _feedback(s, "Curieux", 0.6)
    score, _ = s.reception_score("Curieux")
    assert score > 0.3


def test_bad_reception_raises_the_speaking_bar():
    """Ada exige un motif plus fort pour interrompre dans cet état."""
    s = SocialLearning()
    _feedback(s, "Agacement", -0.7)
    assert s.speaking_bar("Agacement") > 0


def test_good_reception_lowers_the_speaking_bar():
    s = SocialLearning()
    _feedback(s, "Curieux", 0.6)
    assert s.speaking_bar("Curieux") < 0


def test_unknown_mood_does_not_modulate():
    assert SocialLearning().speaking_bar("Inconnu") == 0.0


def test_few_feedbacks_modulate_less_than_many():
    peu = SocialLearning()
    _feedback(peu, "Agacement", -0.7, n=2)
    beaucoup = SocialLearning()
    _feedback(beaucoup, "Agacement", -0.7, n=10)
    assert beaucoup.speaking_bar("Agacement") > peu.speaking_bar("Agacement")


def test_modulation_is_bounded():
    s = SocialLearning()
    _feedback(s, "Rage", -1.0, n=50)
    assert abs(s.speaking_bar("Rage")) <= 0.45


def test_late_reaction_is_not_attributed():
    """Une réaction hors fenêtre ne porte plus sur ce qu'Ada a dit."""
    s = SocialLearning()
    s.register_expression("Joie", now=0)
    assert s.register_reaction(0.9, now=600) is None
    assert s.reception_score("Joie") == (0.0, 0.0)


def test_reaction_without_expression_is_ignored():
    assert SocialLearning().register_reaction(0.9) is None


def test_reaction_is_consumed_once():
    s = SocialLearning()
    s.register_expression("Joie", now=0)
    assert s.register_reaction(0.5, now=10) == "Joie"
    assert s.register_reaction(0.5, now=20) is None


def test_learning_survives_save_and_load():
    s = SocialLearning()
    _feedback(s, "Agacement", -0.7)
    assert s.save() is True

    rechargé = SocialLearning()
    assert rechargé.load() is True
    assert rechargé.reception_score("Agacement")[0] < -0.3


def test_load_without_file_is_safe():
    assert SocialLearning().load() is False


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("BRAIN_SOCIAL_LEARNING_ENABLED", "false")
    s = SocialLearning()
    assert s.save() is False
    assert s.load() is False


def test_learning_never_alters_felt_emotion():
    """Garde-fou : l'apprentissage social ne touche PAS les hormones.

    Ada apprend à choisir ses moments, jamais à ressentir moins fort.
    """
    lim = CerveauEmotif()
    lim.analyser_texte("espèce d'idiote, tu es pénible")
    apres_colere = (lim.cortisol, lim.dopamine, lim.serotonine, lim.oxytocine)

    s = SocialLearning()
    _feedback(s, lim.mood, -0.9, n=20)   # cette humeur est très mal reçue
    s.speaking_bar(lim.mood)

    assert (lim.cortisol, lim.dopamine, lim.serotonine, lim.oxytocine) == apres_colere


def test_debug_state_lists_calibrated_moods():
    s = SocialLearning()
    _feedback(s, "Agacement", -0.7)
    state = s.get_debug_state()
    assert state["total"] == 1
    assert state["humeurs_calibrees"][0]["humeur"] == "Agacement"
