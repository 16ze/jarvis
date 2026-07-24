"""Tests de la mémoire émotionnelle (backend/emotional_memory.py).

Vérifie les deux mécanismes humains reproduits :
  - encodage pondéré par l'émotion (consolidation) ;
  - rappel congruent à l'humeur.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import emotional_memory as em  # noqa: E402

STRESS = {"cortisol": 0.85, "dopamine": 0.30, "oxytocine": 0.25,
          "serotonine": 0.20, "mood": "Anxiété"}
JOIE = {"cortisol": 0.08, "dopamine": 0.80, "oxytocine": 0.75,
        "serotonine": 0.70, "mood": "Joie"}
NEUTRE = {"cortisol": 0.10, "dopamine": 0.28, "oxytocine": 0.30,
          "serotonine": 0.42, "mood": "Neutre"}


def test_valence_sign_matches_emotional_state():
    assert em.affect_from_hormones(STRESS)["valence"] < 0
    assert em.affect_from_hormones(JOIE)["valence"] > 0


def test_emotional_events_are_more_intense_than_neutral_ones():
    """Le neutre se grave moins profondément — c'est la courbe d'oubli."""
    neutre = em.affect_from_hormones(NEUTRE)["intensity"]
    assert em.affect_from_hormones(STRESS)["intensity"] > neutre
    assert em.affect_from_hormones(JOIE)["intensity"] > neutre


def test_affect_of_empty_state_is_flat():
    assert em.affect_from_hormones(None) == {
        "valence": 0.0, "arousal": 0.0, "intensity": 0.0
    }


def test_encoded_metadata_is_chroma_compatible():
    """ChromaDB n'accepte que des scalaires en métadonnées."""
    meta = em.encode_metadata(JOIE)
    assert set(meta) >= {"aff_valence", "aff_arousal", "aff_intensity"}
    assert all(isinstance(v, (int, float, str, bool)) for v in meta.values())


def _corpus():
    docs = ["souvenir joyeux", "souvenir stressant", "souvenir banal"]
    metas = [em.encode_metadata(JOIE), em.encode_metadata(STRESS),
             em.encode_metadata(NEUTRE)]
    distances = [0.5, 0.5, 0.5]  # strictement équivalents sémantiquement
    return docs, metas, distances


def test_recall_is_mood_congruent():
    """À requête égale, l'état intérieur change ce qui remonte."""
    docs, metas, dists = _corpus()

    anxieuse = em.rerank(docs, metas, dists, STRESS, 3)
    joyeuse = em.rerank(docs, metas, dists, JOIE, 3)

    assert anxieuse[0]["content"] == "souvenir stressant"
    assert joyeuse[0]["content"] == "souvenir joyeux"


def test_neutral_memories_rank_last_when_emotionally_charged():
    docs, metas, dists = _corpus()
    ranked = em.rerank(docs, metas, dists, STRESS, 3)
    assert ranked[-1]["content"] == "souvenir banal"


def test_without_state_semantic_order_is_preserved():
    """Rétro-compatibilité stricte : sans état, rien ne change."""
    docs, metas, dists = _corpus()
    ranked = em.rerank(docs, metas, dists, None, 3)
    assert [r["content"] for r in ranked] == docs


def test_semantic_relevance_still_dominates():
    """L'affect pondère, il ne doit pas écraser la pertinence sémantique."""
    docs = ["réponse pertinente", "hors sujet mais très chargé"]
    metas = [em.encode_metadata(NEUTRE), em.encode_metadata(STRESS)]
    distances = [0.05, 3.0]  # le premier est bien plus proche
    ranked = em.rerank(docs, metas, distances, STRESS, 2)
    assert ranked[0]["content"] == "réponse pertinente"


def test_rerank_handles_missing_metadata_and_distances():
    ranked = em.rerank(["a", "b"], [{}, {}], None, JOIE, 2)
    assert len(ranked) == 2


def test_rerank_on_empty_input():
    assert em.rerank([], [], [], JOIE, 5) == []
