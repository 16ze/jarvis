import pytest
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

def _clean_modules():
    for mod in ["user_profile_manager", "voice_recognizer", "presence_manager"]:
        if mod in sys.modules:
            del sys.modules[mod]

def test_update_face_detection_adds_face_speaker(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    _clean_modules()
    from presence_manager import PresenceManager
    pm = PresenceManager()
    pm.update_face_detection([{"user": "rose", "confidence": 0.9, "location": "bureau"}])
    assert any(s["user"] == "rose" for s in pm.active_speakers)

def test_voice_does_not_duplicate_face(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    _clean_modules()
    from presence_manager import PresenceManager
    pm = PresenceManager()
    pm._active_speakers = [{"user": "bryan", "source": "voice", "confidence": 0.92}]
    pm.update_face_detection([{"user": "bryan", "confidence": 0.95, "location": "bureau"}])
    bryan_entries = [s for s in pm.active_speakers if s["user"] == "bryan"]
    assert len(bryan_entries) == 1
    assert bryan_entries[0]["source"] == "voice"

def test_get_context_block_empty_when_no_speakers(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    _clean_modules()
    from presence_manager import PresenceManager
    pm = PresenceManager()
    assert pm.get_context_block() == ""

def test_get_context_block_with_known_user(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    _clean_modules()
    import json, os
    users_dir = tmp_path / "backend" / "memory" / "users"
    users_dir.mkdir(parents=True)
    (users_dir / "bryan.json").write_text(json.dumps({
        "id": "bryan", "name": "Bryan", "role": "owner",
        "preferences": ["Aime le café"], "habits": [], "goals": [], "facts": [],
        "created_at": "2026-01-01"
    }))
    from presence_manager import PresenceManager
    pm = PresenceManager()
    pm._active_speakers = [{"user": "bryan", "source": "voice", "confidence": 0.92}]
    ctx = pm.get_context_block()
    assert "Bryan" in ctx
    assert "Aime le café" in ctx

@pytest.mark.asyncio
async def test_run_handles_empty_queue_gracefully(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    _clean_modules()
    from presence_manager import PresenceManager
    pm = PresenceManager()
    task = asyncio.create_task(pm.run())
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
