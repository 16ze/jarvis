from brain.modulators import get_gemini_params


def test_rupture_temperature_basse():
    assert get_gemini_params("Rupture")["temperature"] == 0.30


def test_euphorie_temperature_haute():
    assert get_gemini_params("Euphorie")["temperature"] == 0.90


def test_smoothing_temperature():
    params = get_gemini_params("Rupture", previous_temp=0.7)
    assert params["temperature"] == 0.58


def test_pas_de_voice_name_dans_params():
    params = get_gemini_params("Neutre")
    assert "voice_name" not in params
