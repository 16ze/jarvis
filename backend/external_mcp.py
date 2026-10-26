"""
external_mcp.py — Client MCP générique pour Ada.

Permet de brancher N'IMPORTE QUEL serveur MCP externe (comme le font Claude et
Codex), sans écrire un connecteur Python par service. Tu déclares le serveur
dans backend/mcp_servers.json (voir mcp_servers.example.json), et Ada peut
lister ses outils et les appeler.

Transports supportés : stdio (commande locale) et sse/http (URL).
Connexion par appel (sans état) : simple et robuste. Nécessite le SDK `mcp`
(`pip install mcp`) ; en son absence, un message clair est renvoyé.
"""

import json
import os
from pathlib import Path

CONFIG_PATH = Path(os.getenv("MCP_SERVERS_CONFIG", str(Path(__file__).parent / "mcp_servers.json")))


def _load_config() -> dict:
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return data.get("servers", data) or {}
    except Exception as e:
        print(f"[MCP] config illisible ({CONFIG_PATH}): {e}")
    return {}


def _server(name: str) -> dict | None:
    return _load_config().get(name)


async def _with_session(cfg: dict, fn):
    """Ouvre une session MCP selon le transport du serveur et exécute fn(session).
    Retourne (resultat, erreur_str)."""
    try:
        from mcp import ClientSession
    except Exception:
        return None, "SDK MCP absent — installe-le avec `pip install mcp`."

    transport = (cfg.get("transport") or ("sse" if cfg.get("url") else "stdio")).lower()
    try:
        if transport in ("sse", "http", "streamable-http"):
            from mcp.client.sse import sse_client
            async with sse_client(cfg["url"]) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session), None
        else:
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client
            env = {**os.environ, **(cfg.get("env") or {})}
            params = StdioServerParameters(
                command=cfg["command"], args=cfg.get("args", []), env=env
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return await fn(session), None
    except Exception as e:
        return None, f"échec connexion MCP : {e}"


async def list_servers() -> str:
    cfg = _load_config()
    if not cfg:
        return ("Aucun serveur MCP externe configuré. Crée backend/mcp_servers.json "
                "(voir mcp_servers.example.json) pour brancher un connecteur comme sur Claude.")
    lines = ["Serveurs MCP externes configurés :"]
    for name, c in cfg.items():
        kind = c.get("transport") or ("sse" if c.get("url") else "stdio")
        lines.append(f"  - {name} ({kind})")
    return "\n".join(lines)


async def list_tools(server: str) -> str:
    cfg = _server(server)
    if not cfg:
        return f"Serveur MCP '{server}' inconnu. Utilise mcp_list_servers pour voir la liste."

    async def _fn(session):
        res = await session.list_tools()
        return res.tools

    tools, err = await _with_session(cfg, _fn)
    if err:
        return f"Erreur ({server}) : {err}"
    if not tools:
        return f"'{server}' n'expose aucun outil."
    lines = [f"Outils de '{server}' :"]
    for t in tools:
        lines.append(f"  - {t.name} : {(t.description or '')[:140]}")
    return "\n".join(lines)


async def call_tool(server: str, tool: str, arguments_json: str = "{}") -> str:
    cfg = _server(server)
    if not cfg:
        return f"Serveur MCP '{server}' inconnu."
    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except Exception as e:
        return f"arguments_json invalide : {e}"

    # Traçabilité (journal d'audit du gate), sans blocage : c'est un connecteur voulu.
    try:
        import security_gate
        security_gate.audit("mcp_call", f"{server}.{tool}", source="ai")
    except Exception:
        pass

    async def _fn(session):
        return await session.call_tool(tool, args)

    res, err = await _with_session(cfg, _fn)
    if err:
        return f"Erreur ({server}.{tool}) : {err}"

    parts = []
    for block in getattr(res, "content", []) or []:
        txt = getattr(block, "text", None)
        parts.append(txt if txt is not None else str(block))
    out = "\n".join(parts) or "(aucune sortie)"
    return out[:4000] + ("\n…(tronqué)" if len(out) > 4000 else "")
