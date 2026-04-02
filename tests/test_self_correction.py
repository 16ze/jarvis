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

def test_write_and_read_file():
    from self_correction_agent import SelfCorrectionAgent, JARVIS_ROOT
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)
    test_file = JARVIS_ROOT / "tests" / "_test_tmp_ada.py"
    content = "# test\ndef hello():\n    return 'world'\n"
    result = agent.write_file(str(test_file), content)
    assert "écrit avec succès" in result, result
    read_back = agent.read_file(str(test_file))
    assert read_back == content
    test_file.unlink(missing_ok=True)

def test_blocked_path():
    from self_correction_agent import SelfCorrectionAgent
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)
    result = agent.read_file("/etc/passwd")
    assert "non autorisé" in result

def test_syntax_error_blocked():
    from self_correction_agent import SelfCorrectionAgent, JARVIS_ROOT
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)
    bad_python = "def broken(:\n    pass"
    test_file = JARVIS_ROOT / "tests" / "_test_syntax_err.py"
    result = agent.write_file(str(test_file), bad_python)
    assert "ERREUR syntaxe" in result
    assert not test_file.exists()
