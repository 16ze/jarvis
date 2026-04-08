#!/usr/bin/env python3
"""
Test complet de tous les outils Ada.
Vérifie : wiring ada.py, wiring external_bridge.py, env vars, connectivité réelle.
Usage : conda run -n ada_v2 python backend/test_tools.py
"""

import os, re, sys, asyncio
from pathlib import Path
from dotenv import load_dotenv

BACKEND = Path(__file__).parent
ROOT    = BACKEND.parent
os.chdir(BACKEND)
load_dotenv(ROOT / ".env")   # .env est à la racine du projet
sys.path.insert(0, str(BACKEND))

# ─── couleurs ────────────────────────────────────────────────────────────────
OK  = "\033[92m✓\033[0m"
ERR = "\033[91m✗\033[0m"
WARN= "\033[93m~\033[0m"
DIM = "\033[2m"
RST = "\033[0m"

results = []  # (tool_name, status, detail)

def log(tool, status, detail=""):
    results.append((tool, status, detail))
    sym = OK if status == "ok" else (WARN if status == "warn" else ERR)
    print(f"  {sym} {tool:<40} {DIM}{detail}{RST}")

# ─── 1. Extraire les noms wirés depuis ada.py et external_bridge.py ──────────

def extract_wired(filepath: str) -> set:
    """Parse les if/elif n == / if/elif name == du fichier."""
    text = Path(filepath).read_text()
    return set(re.findall(r'(?:if|elif)\s+(?:n|name)\s*==\s*["\']([^"\']+)["\']', text))

ada_wired    = extract_wired("ada.py")
bridge_wired = extract_wired("external_bridge.py")

# ─── 2. Charger MCP_TOOLS ────────────────────────────────────────────────────

from mcp_tools_declarations import MCP_TOOLS
mcp_names = {t["name"] for t in MCP_TOOLS}

# Outils de base déclarés dans tools.py (hors MCP_TOOLS)
base_tools = {"read_file", "read_directory", "write_file",
              "run_terminal", "run_web_agent", "control_computer",
              "read_emails", "send_email", "get_email_body",
              "list_events", "create_event", "find_event", "delete_event",
              "search_memory", "remember", "search_documents",
              "generate_cad", "iterate_cad", "print_stl",
              "run_research", "run_task", "anticipate",
              "start_monitoring", "stop_monitoring",
              "create_project", "switch_project", "list_projects"}

all_tools = mcp_names | base_tools

# Outils intentionnellement exclus du bridge (sécurité)
BRIDGE_EXCLUDED = {"execute_pc_task", "run_terminal", "control_computer",
                   "run_web_agent"}

# ─── 3. Vérification du wiring ───────────────────────────────────────────────

print("\n" + "═"*60)
print("  1/3  WIRING — ada.py vs external_bridge.py")
print("═"*60)

missing_ada    = all_tools - ada_wired - base_tools  # outils MCP pas dans ada
missing_bridge = (mcp_names - bridge_wired - BRIDGE_EXCLUDED)

print(f"\n[ada.py]  {len(ada_wired)} outils wirés")
if missing_ada:
    for t in sorted(missing_ada):
        log(t, "err", "déclaré dans MCP_TOOLS mais PAS wiré dans ada.py")
else:
    print(f"  {OK} Tous les MCP_TOOLS sont wirés dans ada.py")

print(f"\n[external_bridge.py]  {len(bridge_wired)} outils wirés")
for t in sorted(missing_bridge):
    log(t, "warn", "déclaré dans MCP_TOOLS mais PAS wiré dans external_bridge.py")

if not missing_bridge:
    print(f"  {OK} Tous les MCP_TOOLS non-exclus sont wirés dans external_bridge.py")

# ─── 4. Vérification des env vars ────────────────────────────────────────────

print("\n" + "═"*60)
print("  2/3  ENV VARS — présence des clés requises")
print("═"*60 + "\n")

ENV_MAP = {
    "Gemini"       : ["GEMINI_API_KEY"],
    "Anthropic"    : ["ANTHROPIC_API_KEY"],
    "Telegram"     : ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"],
    "WhatsApp"     : ["WHATSAPP_EVOLUTION_API_URL", "WHATSAPP_EVOLUTION_API_KEY"],
    "Twilio"       : ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"],
    "Slack"        : ["SLACK_BOT_TOKEN"],
    "Notion"       : ["NOTION_API_KEY"],
    "Google/Drive" : ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
    "Linear"       : ["LINEAR_API_KEY"],
    "Stripe"       : ["STRIPE_SECRET_KEY"],
    "Qonto"        : ["QONTO_API_KEY"],
    "Supabase"     : ["SUPABASE_URL", "SUPABASE_KEY"],
    "Vercel"       : ["VERCEL_TOKEN"],
    "GitHub"       : ["GITHUB_TOKEN"],
    "Docker"       : [],  # local, pas de clé
    "Tuya"         : ["TUYA_API_KEY", "TUYA_API_SECRET"],
    "HomeAssist"   : ["HOME_ASSISTANT_URL", "HOME_ASSISTANT_TOKEN"],
    "Spotify"      : ["SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET"],
    "Maps"         : ["GOOGLE_MAPS_API_KEY"],
    "Replicate"    : ["REPLICATE_API_TOKEN"],
    "ElevenLabs"   : ["ELEVENLABS_API_KEY"],
    "Canva"        : ["CANVA_API_KEY"],
    "Figma"        : ["FIGMA_API_KEY"],
    "AppleHealth"  : [],  # local
}

env_ok = {}
for service, keys in ENV_MAP.items():
    if not keys:
        print(f"  {OK} {service:<15} (local — pas de clé requise)")
        env_ok[service] = True
        continue
    missing = [k for k in keys if not os.getenv(k)]
    if missing:
        print(f"  {ERR} {service:<15} manque : {', '.join(missing)}")
        env_ok[service] = False
    else:
        print(f"  {OK} {service:<15} ({', '.join(keys)})")
        env_ok[service] = True

# ─── 5. Tests de connectivité réelle ─────────────────────────────────────────

print("\n" + "═"*60)
print("  3/3  CONNECTIVITÉ — appels réels (read-only / safe)")
print("═"*60 + "\n")

async def test_connectivity():

    # ── GEMINI ─────────────────────────────────────────────────────────────
    if env_ok.get("Gemini"):
        try:
            from google import genai
            client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"),
                                  http_options={"api_version": "v1beta"})
            r = client.models.generate_content(
                model="gemini-2.5-flash",
                contents="ping"
            )
            log("gemini (2.5-flash)", "ok", r.text[:40].replace("\n"," "))
        except Exception as e:
            log("gemini", "err", str(e)[:80])

    # ── ANTHROPIC ──────────────────────────────────────────────────────────
    if env_ok.get("Anthropic"):
        try:
            import anthropic
            ac = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            m = ac.messages.create(model="claude-haiku-4-5-20251001",
                                   max_tokens=10, messages=[{"role":"user","content":"ping"}])
            log("anthropic (haiku)", "ok", m.content[0].text[:40])
        except Exception as e:
            log("anthropic", "err", str(e)[:80])

    # ── TELEGRAM ───────────────────────────────────────────────────────────
    if env_ok.get("Telegram"):
        try:
            import aiohttp
            token = os.getenv("TELEGRAM_BOT_TOKEN")
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://api.telegram.org/bot{token}/getMe") as r:
                    data = await r.json()
            if data.get("ok"):
                log("telegram_get_updates", "ok", f"bot={data['result']['username']}")
            else:
                log("telegram_get_updates", "err", str(data))
        except Exception as e:
            log("telegram_get_updates", "err", str(e)[:80])

    # ── SLACK ──────────────────────────────────────────────────────────────
    if env_ok.get("Slack"):
        try:
            from mcps.slack_mcp import SlackMCP
            slack = SlackMCP()
            r = await slack.list_channels()
            log("slack_list_channels", "ok", r[:60])
        except Exception as e:
            log("slack_list_channels", "err", str(e)[:80])

    # ── NOTION ─────────────────────────────────────────────────────────────
    if env_ok.get("Notion"):
        try:
            from mcps.notion_mcp import NotionMCP
            notion = NotionMCP()
            r = await notion.search("test", limit=1)
            log("notion_search", "ok", r[:60])
        except Exception as e:
            log("notion_search", "err", str(e)[:80])

    # ── GITHUB ─────────────────────────────────────────────────────────────
    if env_ok.get("GitHub"):
        try:
            from mcps.github_mcp import GitHubMCP
            gh = GitHubMCP()
            r = await gh.list_repos(limit=1)
            log("github_list_repos", "ok", r[:60])
        except Exception as e:
            log("github_list_repos", "err", str(e)[:80])

    # ── GOOGLE / GMAIL ─────────────────────────────────────────────────────
    token_path = Path(__file__).parent / "google_token.json"
    if token_path.exists():
        try:
            from google_agent import GoogleAgent
            ga = GoogleAgent()
            r = ga.read_emails(max_results=1, query="")
            log("read_emails (gmail)", "ok", r[:60])
        except Exception as e:
            log("read_emails (gmail)", "err", str(e)[:80])
    else:
        log("read_emails (gmail)", "warn", "google_token.json absent — pas d'auth")

    # ── SPOTIFY ────────────────────────────────────────────────────────────
    spotify_token = Path(__file__).parent / ".spotify_token"
    if env_ok.get("Spotify") and spotify_token.exists():
        try:
            from mcps.spotify_mcp import SpotifyMCP
            sp = SpotifyMCP()
            r = await sp.current_track()
            log("spotify_current", "ok", r[:60])
        except Exception as e:
            log("spotify_current", "err", str(e)[:80])
    else:
        log("spotify_current", "warn", ".spotify_token absent — run /spotify/auth")

    # ── STRIPE ─────────────────────────────────────────────────────────────
    if env_ok.get("Stripe"):
        try:
            from mcps.stripe_mcp import StripeMCP
            st = StripeMCP()
            r = await st.get_balance()
            log("stripe_get_balance", "ok", r[:60])
        except Exception as e:
            log("stripe_get_balance", "err", str(e)[:80])

    # ── SUPABASE ───────────────────────────────────────────────────────────
    if env_ok.get("Supabase"):
        try:
            from mcps.supabase_mcp import SupabaseMCP
            sb = SupabaseMCP()
            r = await sb.list_tables()
            log("supabase_list_tables", "ok", r[:60])
        except Exception as e:
            log("supabase_list_tables", "err", str(e)[:80])

    # ── VERCEL ─────────────────────────────────────────────────────────────
    if env_ok.get("Vercel"):
        try:
            from mcps.vercel_mcp import VercelMCP
            vc = VercelMCP()
            r = await vc.list_projects()
            log("vercel_list_projects", "ok", r[:60])
        except Exception as e:
            log("vercel_list_projects", "err", str(e)[:80])

    # ── WIKIPEDIA ──────────────────────────────────────────────────────────
    try:
        from mcps.wikipedia_mcp import WikipediaMCP
        wiki = WikipediaMCP()
        r = await asyncio.to_thread(wiki.search, "Python programming", 1)
        log("wikipedia_search", "ok", r[:60])
    except Exception as e:
        log("wikipedia_search", "err", str(e)[:80])

    # ── ARXIV ──────────────────────────────────────────────────────────────
    try:
        from mcps.arxiv_mcp import ArxivMCP
        ax = ArxivMCP()
        r = await asyncio.to_thread(ax.search, "machine learning", 1)
        log("arxiv_search", "ok", r[:60])
    except Exception as e:
        log("arxiv_search", "err", str(e)[:80])

    # ── TUYA LOCAL ─────────────────────────────────────────────────────────
    if env_ok.get("Tuya"):
        try:
            from tuya_agent import TuyaAgent
            ta = TuyaAgent()
            r = await ta.list_devices()  # async
            log("list_smart_devices", "ok", r[:60])
        except Exception as e:
            log("list_smart_devices", "err", str(e)[:80])
    else:
        # Tester depuis devices.json sans Tuya cloud
        devices_path = BACKEND / "devices.json"
        if devices_path.exists():
            import json
            devices = json.loads(devices_path.read_text())
            log("list_smart_devices (local)", "ok", f"{len(devices)} devices en cache")

    # ── MÉMOIRE ────────────────────────────────────────────────────────────
    try:
        from memory_manager import MemoryManager
        mm = MemoryManager()
        r = mm.search_memory("test")
        log("search_memory", "ok", f"{len(r)} résultats")
    except Exception as e:
        log("search_memory", "err", str(e)[:80])

    # ── RAPPELS ────────────────────────────────────────────────────────────
    try:
        from reminder_manager import ReminderManager
        rm = ReminderManager()
        r = rm.list_reminders()
        log("reminder_list", "ok", r[:60])
    except Exception as e:
        log("reminder_list", "err", str(e)[:80])

    # ── JARVIS FILE TOOLS ──────────────────────────────────────────────────
    try:
        from self_correction_agent import SelfCorrectionAgent
        sca = SelfCorrectionAgent()
        r = await asyncio.to_thread(sca.list_files, "backend")
        log("jarvis_list_files", "ok", r[:60])
    except Exception as e:
        log("jarvis_list_files", "err", str(e)[:80])

    # ── GOOGLE MAPS ────────────────────────────────────────────────────────
    if env_ok.get("Maps"):
        try:
            from mcps.googlemaps_mcp import GoogleMapsMCP
            gm = GoogleMapsMCP()
            r = await asyncio.to_thread(gm.search_places, "café Paris")
            log("maps_search_places", "ok", r[:60])
        except Exception as e:
            log("maps_search_places", "err", str(e)[:80])

    # ── YOUTUBE ────────────────────────────────────────────────────────────
    try:
        from mcps.youtube_mcp import YouTubeMCP
        yt = YouTubeMCP()
        r = await asyncio.to_thread(yt.search_videos, "python tutorial", 1)
        log("youtube_search", "ok", r[:60])
    except Exception as e:
        log("youtube_search", "err", str(e)[:80])

    # ── DOCKER ─────────────────────────────────────────────────────────────
    try:
        from mcps.docker_mcp import DockerMCP
        dk = DockerMCP()
        r = await asyncio.to_thread(dk.list_containers)
        log("docker_list_containers", "ok", r[:60])
    except Exception as e:
        log("docker_list_containers", "err", str(e)[:80])

    # ── QONTO ──────────────────────────────────────────────────────────────
    if env_ok.get("Qonto"):
        try:
            from mcps.qonto_mcp import QontoMCP
            qo = QontoMCP()
            r = await qo.get_balance()
            log("qonto_get_balance", "ok", r[:60])
        except Exception as e:
            log("qonto_get_balance", "err", str(e)[:80])

    # ── LINEAR ─────────────────────────────────────────────────────────────
    if env_ok.get("Linear"):
        try:
            from mcps.linear_mcp import LinearMCP
            li = LinearMCP()
            r = await li.list_teams()
            log("linear_list_teams", "ok", r[:60])
        except Exception as e:
            log("linear_list_teams", "err", str(e)[:80])

    # ── HOME ASSISTANT ─────────────────────────────────────────────────────
    if env_ok.get("HomeAssist"):
        try:
            from mcps.homeassistant_mcp import HomeAssistantMCP
            ha = HomeAssistantMCP()
            r = await ha.get_states()
            log("ha_get_states", "ok", r[:60])
        except Exception as e:
            log("ha_get_states", "err", str(e)[:80])

    # ── REPLICATE ──────────────────────────────────────────────────────────
    if env_ok.get("Replicate"):
        try:
            from mcps.replicate_mcp import ReplicateMCP
            rp = ReplicateMCP()
            # Pas d'appel réel (génération payante) — juste instanciation
            log("replicate_generate_image", "ok", "instanciation OK (pas de run — payant)")
        except Exception as e:
            log("replicate_generate_image", "err", str(e)[:80])

    # ── ELEVENLABS ─────────────────────────────────────────────────────────
    if env_ok.get("ElevenLabs"):
        try:
            from mcps.elevenlabs_mcp import ElevenLabsMCP
            el = ElevenLabsMCP()
            r = await el.list_voices()
            log("elevenlabs_list_voices", "ok", r[:60])
        except Exception as e:
            log("elevenlabs_list_voices", "err", str(e)[:80])

    # ── CANVA ──────────────────────────────────────────────────────────────
    if env_ok.get("Canva"):
        try:
            from mcps.canva_mcp import CanvaMCP
            ca = CanvaMCP()
            r = await ca.list_designs(limit=1)
            log("canva_list_designs", "ok", r[:60])
        except Exception as e:
            log("canva_list_designs", "err", str(e)[:80])

    # ── FIGMA ──────────────────────────────────────────────────────────────
    if env_ok.get("Figma"):
        try:
            from mcps.figma_mcp import FigmaMCP
            fg = FigmaMCP()
            r = await fg.list_files()
            log("figma_list_files", "ok", r[:60])
        except Exception as e:
            log("figma_list_files", "err", str(e)[:80])

# ─── Run ──────────────────────────────────────────────────────────────────────

asyncio.run(test_connectivity())

# ─── Résumé final ─────────────────────────────────────────────────────────────

print("\n" + "═"*60)
print("  RÉSUMÉ")
print("═"*60)

ok_count   = sum(1 for _, s, _ in results if s == "ok")
warn_count = sum(1 for _, s, _ in results if s == "warn")
err_count  = sum(1 for _, s, _ in results if s == "err")

print(f"\n  {OK} OK     : {ok_count}")
print(f"  {WARN} WARN   : {warn_count}  (non-bloquant — config manquante ou service non utilisé)")
print(f"  {ERR} ERREUR : {err_count}")

if missing_ada:
    print(f"\n  {ERR} Outils MCP non wirés dans ada.py ({len(missing_ada)}) :")
    for t in sorted(missing_ada):
        print(f"       - {t}")

if missing_bridge:
    print(f"\n  {WARN} Outils MCP non wirés dans external_bridge.py ({len(missing_bridge)}) :")
    for t in sorted(missing_bridge):
        print(f"       - {t}")

if err_count == 0 and not missing_ada:
    print(f"\n  {OK} Tous les outils sont opérationnels.\n")
else:
    print(f"\n  Voir les lignes {ERR} ci-dessus pour les corrections.\n")
