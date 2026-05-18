from brain.limbic import BASELINE, CerveauEmotif


def test_texte_positif_monte_dopamine_et_oxytocine():
    c = CerveauEmotif()
    c.analyser_texte("merci genial super")
    snap = c.get_snapshot()
    assert snap["dopamine"] > BASELINE["dopamine"]
    assert snap["oxytocine"] > BASELINE["oxytocine"]


def test_texte_negatif_monte_cortisol():
    c = CerveauEmotif()
    c.analyser_texte("idiot inutile")
    assert c.get_snapshot()["cortisol"] > BASELINE["cortisol"]


def test_hostilite_verbale_declenche_recadrage_spontane():
    c = CerveauEmotif()
    c.analyser_texte("idiot pénible prouve-le")
    snap = c.get_snapshot()
    assert snap["last_stimulus"] == "hostilite_verbale"
    impulse = c.verifier_action_spontanee()
    assert impulse is not None
    assert "sans l'insulter" in impulse


def test_decroissance_ramene_vers_baseline():
    c = CerveauEmotif()
    c.cortisol = 0.8
    c._decroissance()
    assert c.cortisol < 0.8


def test_momentum_amplifie_direction_coherente():
    c = CerveauEmotif()
    c.analyser_texte("merci super")
    first = c.get_snapshot()["dopamine"]
    c.analyser_texte("bravo excellent")
    second_delta = c.get_snapshot()["dopamine"] - first
    assert c.get_snapshot()["momentum"] > 0
    assert second_delta > 0.0


def test_scene_visuelle_danger_declenche_spontaneite():
    c = CerveauEmotif()
    c.analyser_scene_visuelle(
        {
            "description": "fumee visible dans la cuisine",
            "risk": "high",
            "human_emotion": "unknown",
            "movement": 0.2,
            "attention_need": 1.0,
            "spontaneous_hint": "Attention, je vois de la fumee.",
        }
    )
    assert c.get_snapshot()["cortisol"] > BASELINE["cortisol"]
    assert "fumee" in c.verifier_action_spontanee()


def test_scene_visuelle_triste_augmente_attachement():
    c = CerveauEmotif()
    c.analyser_scene_visuelle(
        {
            "description": "Bryan semble fatigue",
            "person": "Bryan",
            "risk": "none",
            "human_emotion": "tired",
            "attention_need": 0.7,
            "affection": 0.6,
        }
    )
    assert c.get_snapshot()["oxytocine"] > BASELINE["oxytocine"]
    assert c.verifier_action_spontanee()


def test_scene_visuelle_banal_reste_silencieuse():
    c = CerveauEmotif()
    c.analyser_scene_visuelle(
        {
            "description": "une table et une tasse",
            "risk": "none",
            "human_emotion": "unknown",
            "movement": 0.05,
            "attention_need": 0.10,
            "affection": 0.0,
            "valence": 0.0,
        }
    )
    assert c.verifier_action_spontanee() is None
