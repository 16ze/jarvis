import pytest
import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

def test_identify_returns_none_when_no_embeddings(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    audio = np.zeros(32000, dtype=np.float32)
    result = vr.identify(audio)
    assert result is None

def test_enroll_from_array_creates_npy(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    audio = np.zeros(16000 * 5, dtype=np.float32)
    vr.enroll_from_array("testuser", audio)
    npy_path = tmp_path / "backend" / "memory" / "voice_prints" / "guests" / "testuser.npy"
    assert npy_path.exists()

def test_identify_known_user_above_threshold(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    t = np.linspace(0, 5, 16000 * 5, dtype=np.float32)
    audio = np.sin(2 * np.pi * 440 * t) * 0.5
    vr.enroll_from_array("bryan", audio)
    result = vr.identify(audio[:32000])
    assert result is not None
    assert result["user"] == "bryan"
    assert result["confidence"] >= 0.75

def test_feed_chunk_accumulates_before_identifying(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    t = np.linspace(0, 5, 16000 * 5, dtype=np.float32)
    audio = np.sin(2 * np.pi * 440 * t) * 0.5
    vr.enroll_from_array("bryan", audio)
    chunk = (audio[:1024] * 32767).astype(np.int16).tobytes()
    result = vr.feed_chunk(chunk)
    assert result is None

def test_feed_chunk_returns_result_after_2s(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    t = np.linspace(0, 5, 16000 * 5, dtype=np.float32)
    audio = np.sin(2 * np.pi * 440 * t) * 0.5
    vr.enroll_from_array("bryan", audio)
    audio_2s = audio[:32000]
    pcm_bytes = (audio_2s * 32767).astype(np.int16).tobytes()
    result = vr.feed_chunk(pcm_bytes)
    assert result is not None
