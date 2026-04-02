import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

def test_import():
    from self_correction_agent import SelfCorrectionAgent
    assert SelfCorrectionAgent is not None

def test_validate_path_ok():
    from self_correction_agent import SelfCorrectionAgent
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)
    assert agent._validate_path("/Users/bryandev/jarvis/backend/ada.py") is True

def test_validate_path_blocked():
    from self_correction_agent import SelfCorrectionAgent
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)
    assert agent._validate_path("/etc/passwd") is False
    assert agent._validate_path("/Users/bryandev/jarvis/../../../etc/passwd") is False
