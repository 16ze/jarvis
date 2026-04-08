import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

def test_get_nonexistent_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    assert mgr.get_profile("nobody") is None

def test_save_and_get_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    mgr.save_profile({"id": "bryan", "name": "Bryan", "role": "owner",
                      "preferences": [], "habits": [], "goals": [], "facts": [],
                      "created_at": "2026-01-01"})
    profile = mgr.get_profile("bryan")
    assert profile["name"] == "Bryan"

def test_save_preference_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    mgr.save_profile({"id": "bryan", "name": "Bryan", "role": "owner",
                      "preferences": [], "habits": [], "goals": [], "facts": [],
                      "created_at": "2026-01-01"})
    mgr.save_preference("bryan", "Aime le café")
    assert "Aime le café" in mgr.get_profile("bryan")["preferences"]

def test_save_preference_no_duplicate(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    mgr.save_profile({"id": "bryan", "name": "Bryan", "role": "owner",
                      "preferences": ["Aime le café"], "habits": [], "goals": [], "facts": [],
                      "created_at": "2026-01-01"})
    mgr.save_preference("bryan", "Aime le café")
    assert mgr.get_profile("bryan")["preferences"].count("Aime le café") == 1

def test_create_guest_persistent(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    guest = mgr.create_guest("Marco")
    assert guest["id"] == "marco"
    assert guest["role"] == "guest"
    guest2 = mgr.create_guest("Marco")
    assert guest2["id"] == "marco"

def test_get_active_context_single(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    mgr.save_profile({"id": "bryan", "name": "Bryan", "role": "owner",
                      "preferences": ["Aime coder le matin"], "habits": [], "goals": [], "facts": [],
                      "created_at": "2026-01-01"})
    ctx = mgr.get_active_context([{"user": "bryan", "source": "voice", "confidence": 0.92}])
    assert "Bryan" in ctx
    assert "Aime coder le matin" in ctx

def test_get_active_context_dual_has_explicit_reply_instruction(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    for uid, name in [("bryan", "Bryan"), ("rose", "Rose")]:
        mgr.save_profile({"id": uid, "name": name, "role": "owner",
                          "preferences": [], "habits": [], "goals": [], "facts": [],
                          "created_at": "2026-01-01"})
    ctx = mgr.get_active_context([
        {"user": "bryan", "source": "voice", "confidence": 0.9},
        {"user": "rose",  "source": "face",  "confidence": 0.85},
    ])
    assert "réponds à chacun explicitement" in ctx

def test_get_active_context_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    assert mgr.get_active_context([]) == ""
