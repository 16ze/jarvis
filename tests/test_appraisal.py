"""Tests de l'évaluation émotionnelle fine (backend/appraisal.py + voie lente).

Vérifie l'architecture à double voie : la voie rapide (lexique) réagit, la voie
lente (LLM) corrige l'écart — sans jamais recompter ce qui l'a déjà été.
"""

import asyncio
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from appraisal import Appraisal, AppraisalEngine, parse  # noqa: E402
from brain.limbic import CerveauEmotif  # noqa: E402


# ── Parsing ───────────────────────────────────────────────────────────────────

def test_parse_valid_json():
    a = parse('{"valence":-0.6,"arousal":0.7,"dominance":0.3,'
              '"cause":"du sarcasme","target":"situation","certainty":0.9}')
    assert a.valence == pytest.approx(-0.6)
    assert a.cause == "du sarcasme"
    assert a.target == "situation"


def test_parse_strips_markdown():
    a = parse('```json\n{"valence":0.5,"arousal":0.2,"dominance":0.5,'
              '"cause":"un merci","target":"bryan","certainty":0.8}\n```')
    assert a is not None and a.valence == pytest.approx(0.5)


def test_parse_clamps_out_of_range_values():
    a = parse('{"valence":9,"arousal":-3,"dominance":42,"cause":"x",'
              '"target":"bryan","certainty":5}')
    assert a.valence == 1.0 and a.arousal == 0.0
    assert a.dominance == 1.0 and a.certainty == 1.0


def test_parse_normalises_unknown_target():
    a = parse('{"valence":0,"arousal":0,"dominance":0,"cause":"x",'
              '"target":"n_importe_quoi","certainty":0.5}')
    assert a.target == "situation"


@pytest.mark.parametrize("raw", ["", "pas du json", "null", "[1,2,3]"])
def test_parse_never_raises_on_garbage(raw):
    assert parse(raw) is None


# ── Voie lente : correction du jugement grossier ──────────────────────────────

def _appraisal(valence, cause="une cause", arousal=0.5, certainty=0.9):
    return Appraisal(valence=valence, arousal=arousal, dominance=0.5,
                     cause=cause, target="bryan", certainty=certainty)


def test_negation_is_corrected():
    """« je ne suis pas en colère » : le lexique voit la colère, pas la réalité."""
    lim = CerveauEmotif()
    lim.analyser_texte("je ne suis pas en colère contre toi, tout va bien")
    cortisol_rapide = lim.cortisol

    lim.reevaluer(_appraisal(0.4, "une mise au point rassurante"))

    assert lim.cortisol < cortisol_rapide  # la tension retombe


def test_irony_is_corrected_and_false_euphoria_fades():
    """« super, encore un bug » : le lexique s'enthousiasme à tort."""
    lim = CerveauEmotif()
    lim.analyser_texte("super, génial, encore un bug parfait")
    dopamine_rapide, cortisol_rapide = lim.dopamine, lim.cortisol

    lim.reevaluer(_appraisal(-0.6, "du sarcasme sur un échec"))

    assert lim.cortisol > cortisol_rapide     # la dureté réelle est ressentie
    assert lim.dopamine < dopamine_rapide     # la fausse euphorie retombe


def test_no_double_counting_when_both_paths_agree():
    """Si la voie rapide avait raison, la voie lente ne recompte rien."""
    lim = CerveauEmotif()
    lim.analyser_texte("merci beaucoup, c'est génial ce que tu fais")
    avant = (lim.dopamine, lim.cortisol, lim.serotonine)

    correction = lim.reevaluer(_appraisal(lim._derniere_valence_brute, "un compliment"))

    assert correction == 0.0
    assert (lim.dopamine, lim.cortisol, lim.serotonine) == avant


def test_cause_becomes_the_object_of_the_emotion():
    """La cause remonte dans dernier_stimulus → donc dans le mood_block."""
    lim = CerveauEmotif()
    lim.analyser_texte("bon, on verra ça plus tard")
    lim.reevaluer(_appraisal(-0.7, "un désintérêt blessant"))
    assert lim.dernier_stimulus == "un désintérêt blessant"


def test_low_certainty_dampens_the_correction():
    forte = CerveauEmotif()
    forte.analyser_texte("bon, on verra ça plus tard")
    c_forte = forte.reevaluer(_appraisal(-0.9, "x", certainty=1.0))

    faible = CerveauEmotif()
    faible.analyser_texte("bon, on verra ça plus tard")
    c_faible = faible.reevaluer(_appraisal(-0.9, "x", certainty=0.3))

    assert abs(c_faible) < abs(c_forte)


def test_reevaluer_with_none_is_safe():
    lim = CerveauEmotif()
    assert lim.reevaluer(None) == 0.0


# ── Moteur ────────────────────────────────────────────────────────────────────

def _client(payload):
    text = payload if isinstance(payload, str) else json.dumps(payload)

    class _C:
        class aio:
            class models:
                @staticmethod
                async def generate_content(**kwargs):
                    r = types.SimpleNamespace()
                    r.text = text
                    return r
    return _C()


def test_engine_returns_appraisal(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    engine = AppraisalEngine(client=_client(
        {"valence": -0.5, "arousal": 0.6, "dominance": 0.4,
         "cause": "une critique sèche", "target": "soi", "certainty": 0.8}))
    result = asyncio.run(engine.evaluate("tu t'es encore trompée"))
    assert result.cause == "une critique sèche"
    assert result.is_meaningful


def test_engine_ignores_too_short_messages():
    engine = AppraisalEngine(client=_client({"valence": 0.5}))
    assert asyncio.run(engine.evaluate("ok")) is None


def test_engine_disabled_by_env(monkeypatch):
    monkeypatch.setenv("APPRAISAL_ENABLED", "false")
    engine = AppraisalEngine(client=_client({"valence": 0.5}))
    assert asyncio.run(engine.evaluate("un message assez long")) is None


def test_engine_survives_unparseable_answer(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    engine = AppraisalEngine(client=_client("ceci n'est pas du JSON"))
    assert asyncio.run(engine.evaluate("un message assez long")) is None


def test_engine_without_api_key_returns_none(monkeypatch):
    """Sans clé : seule la voie rapide s'applique, comportement inchangé."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    engine = AppraisalEngine()
    assert asyncio.run(engine.evaluate("un message assez long")) is None


def test_low_certainty_appraisal_is_not_meaningful():
    assert Appraisal(0.5, 0.5, 0.5, "x", "bryan", 0.1).is_meaningful is False
