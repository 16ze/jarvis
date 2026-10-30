from array import array

from microphone_diagnostic import pcm16_level, summarize_levels


def test_pcm16_level_measures_rms_and_peak():
    samples = array("h", [0, 1000, -1000, 2000, -2000])

    rms, peak = pcm16_level(samples.tobytes())

    assert 1300 < rms < 1500
    assert peak == 2000


def test_summarize_levels_accepts_clear_voice():
    result = summarize_levels(
        [50, 100, 900, 1200, 1500, 1000, 80],
        [100, 200, 2500, 4000, 5000, 3000, 150],
        vad_threshold=800,
    )

    assert result["status"] == "ok"
    assert result["active_ratio"] > 0.05
    assert result["clipping"] is False


def test_summarize_levels_reports_low_signal():
    result = summarize_levels(
        [20, 50, 100, 200],
        [50, 100, 300, 500],
        vad_threshold=800,
    )

    assert result["status"] == "too_low"
    assert "ne franchit jamais" in result["message"]


def test_summarize_levels_reports_silence():
    result = summarize_levels([0, 2, 3], [0, 10, 20], vad_threshold=800)

    assert result["status"] == "silent"
