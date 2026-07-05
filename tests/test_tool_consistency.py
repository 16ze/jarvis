"""
Cohérence du câblage des outils — anti-drift.

L'audit (AUDIT.md §3) a relevé que chaque outil doit être câblé à ~4 endroits
(déclaration MCP, liste voix, dispatch ada.py, dispatch external_bridge), ce qui
provoque des oublis silencieux. Ces tests verrouillent les invariants les plus
dangereux, sans exécuter le backend (imports légers / parsing AST).

Bugs attrapés :
  - deux outils avec le même nom (l'un masque l'autre silencieusement) ;
  - un outil "core" local déclaré mais SANS handler de dispatch → il échoue
    silencieusement à l'exécution.
"""

import ast
import os
import re

BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")


def _read(name: str) -> str:
    with open(os.path.join(BACKEND, name), encoding="utf-8") as fh:
        return fh.read()


def _core_tools() -> set[str]:
    """Extrait le set littéral _CORE_TOOLS d'ada.py via AST (sans importer)."""
    tree = ast.parse(_read("ada.py"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "_CORE_TOOLS" for t in node.targets
        ):
            if isinstance(node.value, ast.Set):
                return {
                    el.value for el in node.value.elts
                    if isinstance(el, ast.Constant) and isinstance(el.value, str)
                }
    raise AssertionError("_CORE_TOOLS introuvable dans ada.py")


def _dispatch_handlers() -> set[str]:
    """Noms d'outils avec un handler explicite `name == "X"` / `fc.name == "X"`."""
    src = _read("ada.py")
    return set(re.findall(r'(?:fc\.)?name == "([a-zA-Z0-9_]+)"', src))


def test_no_duplicate_mcp_tool_names():
    import sys
    sys.path.insert(0, BACKEND)
    import mcp_tools_declarations as d
    names = [t["name"] for t in d.MCP_TOOLS]
    assert len(names) == len(set(names)), (
        f"noms MCP en double : {[n for n in names if names.count(n) > 1]}"
    )


def test_every_core_tool_has_a_dispatch_handler():
    core = _core_tools()
    handled = _dispatch_handlers()
    missing = core - handled
    assert not missing, (
        f"Outils 'core' déclarés mais SANS handler de dispatch (échec silencieux) : "
        f"{sorted(missing)}"
    )


# Collisions core/MCP connues et tolérées : outils smart-home dont le handler
# LOCAL (tuya_agent) est prioritaire dans le dispatch, la déclaration MCP étant
# ainsi masquée. À nettoyer (AUDIT.md §3) : dédupliquer la déclaration Gemini.
# Ce test empêche toute NOUVELLE collision non documentée.
_KNOWN_CORE_MCP_OVERLAP = {"control_light", "list_smart_devices"}


def test_no_new_core_mcp_collision():
    """Aucune collision core/MCP au-delà des overlaps connus et documentés."""
    import sys
    sys.path.insert(0, BACKEND)
    import mcp_tools_declarations as d
    overlap = _core_tools() & set(d.MCP_TOOL_NAMES)
    new = overlap - _KNOWN_CORE_MCP_OVERLAP
    assert not new, (
        f"NOUVELLE collision noms core/MCP (un handler en masque un autre) : {sorted(new)}"
    )
