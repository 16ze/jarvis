"""Tests du moteur de planification (backend/planner.py).

Vérifie le cycle Plan → Exécute → Vérifie → Répare, la reprise après
interruption, et surtout le garde-fou : aucune action irréversible n'est
déclenchée sans validation humaine.
"""

import asyncio
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from planner import (  # noqa: E402
    MAX_REPAIRS,
    Plan,
    Planner,
    Step,
    looks_like_failure,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("PLANNER_STATE_PATH", str(tmp_path / "plan.json"))


# ── Détection d'échec ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("result", [
    "Erreur : paramètre manquant", "Error: not found", "Impossible d'ouvrir",
    "Échec de la connexion", "introuvable", "[BLOQUÉ] commande refusée", "", None,
])
def test_failures_are_detected(result):
    assert looks_like_failure(result) is True


@pytest.mark.parametrize("result", [
    "Fichier écrit.", "Résultats web pour « météo »", "ok", "3 messages envoyés",
])
def test_successes_are_not_flagged(result):
    assert looks_like_failure(result) is False


# ── Fabriques ─────────────────────────────────────────────────────────────────

def _client(plan_payload, repair_payload=None):
    class _C:
        class aio:
            class models:
                @staticmethod
                async def generate_content(**kw):
                    system = kw["config"].system_instruction
                    r = types.SimpleNamespace()
                    if "décomposes" in system:
                        r.text = json.dumps(plan_payload)
                    else:
                        r.text = json.dumps(repair_payload or {"tool": None})
                    return r
    return _C()


def _plan(*steps):
    p = Plan(objective="objectif de test")
    for i, (tool, args) in enumerate(steps, start=1):
        p.steps.append(Step(id=i, description=f"étape {i}", tool=tool, args=args))
    return p


# ── Planification ─────────────────────────────────────────────────────────────

def test_plan_is_built_from_objective():
    planner = Planner(client=_client({"steps": [
        {"description": "chercher", "tool": "web_search",
         "args": {"query": "x"}, "success_criteria": "des résultats"}]}))
    plan = asyncio.run(planner.make_plan("trouve x", ["web_search"]))
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "web_search"


def test_unknown_tools_are_dropped_from_plan():
    """Le modèle ne peut pas inventer un outil inexistant."""
    planner = Planner(client=_client({"steps": [
        {"description": "ok", "tool": "web_search", "args": {}},
        {"description": "inventé", "tool": "outil_imaginaire", "args": {}}]}))
    plan = asyncio.run(planner.make_plan("obj", ["web_search"]))
    assert [s.tool for s in plan.steps] == ["web_search"]


def test_run_without_client_reports_clearly(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    planner = Planner(executor=lambda t, a: None)
    out = asyncio.run(planner.run("un objectif", ["web_search"]))
    assert "pas réussi à décomposer" in out


# ── Exécution ─────────────────────────────────────────────────────────────────

def test_successful_plan_runs_all_steps():
    appels = []

    async def executor(tool, args):
        appels.append(tool)
        return "ok"

    planner = Planner(executor=executor)
    out = asyncio.run(planner.execute(_plan(("web_search", {}), ("write_file", {}))))
    assert appels == ["web_search", "write_file"]
    assert "2/2" in out


def test_failed_step_is_repaired_without_replaying_the_whole_plan():
    appels = []

    async def executor(tool, args):
        appels.append((tool, args.get("content")))
        if tool == "write_file" and args.get("content") != "corrigé":
            return "Erreur : contenu manquant"
        return "ok"

    planner = Planner(
        executor=executor,
        client=_client({}, {"tool": "write_file", "args": {"content": "corrigé"},
                            "reason": "contenu réinjecté"}),
    )
    out = asyncio.run(planner.execute(_plan(("web_search", {}), ("write_file", {}))))

    assert "2/2" in out
    # web_search n'est joué qu'UNE fois : seule l'étape fautive est rejouée.
    assert [t for t, _ in appels].count("web_search") == 1


def test_repairs_are_bounded():
    appels = []

    async def executor(tool, args):
        appels.append(tool)
        return "Erreur systématique"

    planner = Planner(
        executor=executor,
        client=_client({}, {"tool": "write_file", "args": {}, "reason": "retente"}),
    )
    out = asyncio.run(planner.execute(_plan(("write_file", {}))))
    assert "Bloquée" in out
    assert len(appels) <= MAX_REPAIRS + 2  # borné, pas de boucle infinie


def test_step_results_flow_into_later_steps():
    """{{etape_1}} est remplacé par le résultat réel de l'étape 1."""
    recu = {}

    async def executor(tool, args):
        if tool == "write_file":
            recu.update(args)
            return "ok"
        return "28°C nuageux"

    plan = _plan(("web_search", {}), ("write_file", {"content": "météo: {{etape_1}}"}))
    asyncio.run(Planner(executor=executor).execute(plan))
    assert recu["content"] == "météo: 28°C nuageux"


# ── Sûreté ────────────────────────────────────────────────────────────────────

def test_sensitive_step_stops_the_plan_and_asks():
    """Aucune action irréversible n'est déclenchée automatiquement."""
    appels = []

    async def executor(tool, args):
        appels.append(tool)
        return "ok"

    plan = _plan(("web_search", {}), ("send_email", {"to": "x@y.z"}))
    out = asyncio.run(Planner(executor=executor).execute(plan))

    assert "send_email" not in appels        # jamais exécuté
    assert "irréversible" in out
    assert plan.status == "blocked"


def test_sensitive_tool_is_recognised():
    assert Step(1, "d", "send_email").is_sensitive is True
    assert Step(1, "d", "web_search").is_sensitive is False


# ── Persistance / reprise ─────────────────────────────────────────────────────

def test_plan_is_persisted_during_execution():
    async def executor(tool, args):
        return "ok"

    asyncio.run(Planner(executor=executor).execute(_plan(("web_search", {}))))
    assert Planner.state_path().exists()


def test_interrupted_plan_can_be_reloaded():
    async def executor(tool, args):
        return "ok"

    plan = _plan(("web_search", {}), ("send_email", {}))
    asyncio.run(Planner(executor=executor).execute(plan))  # bloque sur send_email

    repris = Planner.load_plan()
    assert repris is not None
    assert repris.status == "blocked"
    assert repris.steps[0].status == "done"      # l'étape faite n'est pas perdue


def test_completed_plan_is_not_reloaded():
    async def executor(tool, args):
        return "ok"

    asyncio.run(Planner(executor=executor).execute(_plan(("web_search", {}))))
    assert Planner.load_plan() is None  # rien à reprendre


def test_execute_without_executor_is_safe():
    out = asyncio.run(Planner().execute(_plan(("web_search", {}))))
    assert "Aucun exécuteur" in out
