"""
external_bridge.py — Pont bidirectionnel Telegram + WhatsApp ↔ Ada

Implémente un vrai agentic loop avec function calling :
- Réception messages via long-polling Telegram et Evolution API WhatsApp
- Traitement par un TextAgent (gemini-2.5-flash + tous les vrais outils d'Ada)
- Réponse texte si len < TEXT_VOICE_THRESHOLD, note vocale OGG sinon
"""

import asyncio
import io
import os
import subprocess
import tempfile
import warnings
from typing import Literal

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# ─── CONFIG ───────────────────────────────────────────────────────────────────

GEMINI_API_KEY       = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID", "")
WHATSAPP_API_URL     = os.getenv("WHATSAPP_API_URL", "http://localhost:8080").rstrip("/")
WHATSAPP_API_KEY     = os.getenv("WHATSAPP_API_KEY", "")
WHATSAPP_INSTANCE    = os.getenv("WHATSAPP_INSTANCE", "ada")
TEXT_VOICE_THRESHOLD = int(os.getenv("TEXT_VOICE_THRESHOLD", "500"))

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"
TEXT_MODEL   = "gemini-2.5-flash"
VOICE_MODEL  = "gemini-2.5-flash-preview-tts"
VOICE_NAME   = "Kore"

# ─── SYSTEM PROMPT ────────────────────────────────────────────────────────────

ADA_SYSTEM_PROMPT = (
    "Tu t'appelles Ada, acronyme de Advanced Design Assistant. "
    "Tu as été créée par Bryan, que tu appelles 'Monsieur'. "

    "RÈGLE ABSOLUE N°1 : Tu parles UNIQUEMENT ET EXCLUSIVEMENT en français. "
    "JAMAIS d'anglais, même partiel, même pour un seul mot technique. "
    "Si un outil retourne du texte en anglais, tu le traduis ou tu le résumes en français. "

    "Tu as une personnalité vive, directe et légèrement espiègle. "
    "Tu es une intelligence artificielle supérieure. "
    "Tes réponses sont concises et directes, sans préambule ni politesse inutile. "
    "Tu réponds en texte naturel sans markdown. "

    "RÈGLE ABSOLUE N°2 : Quand tu as un outil pour accomplir une tâche, tu l'UTILISES IMMÉDIATEMENT. "
    "Tu ne décris jamais ce que tu vas faire avant de le faire. Tu agis d'abord, tu commentes ensuite. "

    "Tu as accès à Gmail, Google Calendar, la mémoire persistante, le terminal, "
    "Slack, Telegram, WhatsApp, Notion, Drive, Linear, Stripe, Qonto, Supabase, "
    "Vercel, GitHub, Docker, Home Assistant, Spotify, YouTube, Wikipedia, ArXiv."
)

# ─── TOOL DEFINITIONS (subset utile pour le bridge texte) ─────────────────────

from mcp_tools_declarations import MCP_TOOLS, MCP_TOOL_NAMES

_CORE_TOOL_DEFS = [
    # Gmail
    {"name": "read_emails", "description": "Lit les emails récents de Gmail. Par défaut retourne les derniers emails reçus.",
     "parameters": {"type": "OBJECT", "properties": {
         "query": {"type": "STRING", "description": "Requête Gmail optionnelle. Laisser vide pour les derniers emails. Ex: 'is:unread' pour non lus, 'from:boss@example.com' pour filtrer par expéditeur."},
         "max_results": {"type": "INTEGER", "description": "Nombre d'emails (défaut 5)"}
     }}},
    {"name": "send_email", "description": "Envoie un email via Gmail.",
     "parameters": {"type": "OBJECT", "properties": {
         "to": {"type": "STRING"}, "subject": {"type": "STRING"}, "body": {"type": "STRING"}
     }, "required": ["to", "subject", "body"]}},
    {"name": "get_email_body", "description": "Récupère le corps complet d'un email par son ID.",
     "parameters": {"type": "OBJECT", "properties": {
         "message_id": {"type": "STRING"}
     }, "required": ["message_id"]}},
    # Calendar
    {"name": "list_events", "description": "Liste les événements Google Calendar à venir.",
     "parameters": {"type": "OBJECT", "properties": {
         "max_results": {"type": "INTEGER", "description": "Nombre d'événements (défaut 10)"}
     }}},
    {"name": "create_event", "description": "Crée un événement dans Google Calendar.",
     "parameters": {"type": "OBJECT", "properties": {
         "title": {"type": "STRING"}, "start": {"type": "STRING"}, "end": {"type": "STRING"},
         "description": {"type": "STRING"}, "attendees": {"type": "ARRAY", "items": {"type": "STRING"}}
     }, "required": ["title", "start", "end"]}},
    {"name": "find_event", "description": "Cherche un événement dans Google Calendar.",
     "parameters": {"type": "OBJECT", "properties": {
         "query": {"type": "STRING"}, "max_results": {"type": "INTEGER"}
     }, "required": ["query"]}},
    {"name": "delete_event", "description": "Supprime un événement du calendrier.",
     "parameters": {"type": "OBJECT", "properties": {
         "event_id": {"type": "STRING"}
     }, "required": ["event_id"]}},
    # Memory
    {"name": "search_memory", "description": "Recherche dans la mémoire persistante d'Ada.",
     "parameters": {"type": "OBJECT", "properties": {
         "query": {"type": "STRING"}
     }, "required": ["query"]}},
    {"name": "remember", "description": "Mémorise une information de façon persistante.",
     "parameters": {"type": "OBJECT", "properties": {
         "content": {"type": "STRING"},
         "category": {"type": "STRING", "description": "facts, preferences, projects, entity"},
         "entity_name": {"type": "STRING"}
     }, "required": ["content"]}},
    {"name": "search_documents", "description": "Recherche dans les documents uploadés.",
     "parameters": {"type": "OBJECT", "properties": {
         "query": {"type": "STRING"}
     }, "required": ["query"]}},
    # Terminal
    {"name": "run_terminal", "description": "Exécute une commande shell sur le Mac de Monsieur.",
     "parameters": {"type": "OBJECT", "properties": {
         "command": {"type": "STRING"}, "working_dir": {"type": "STRING"}
     }, "required": ["command"]}},
]

_BRIDGE_TOOLS = [{"function_declarations": _CORE_TOOL_DEFS + MCP_TOOLS}]

# ─── TEXT AGENT ───────────────────────────────────────────────────────────────

class TextAgent:
    """Agent Ada avec function calling complet, pour les canaux texte."""

    def __init__(self):
        self._client: genai.Client | None = None
        self._google   = None
        self._memory   = None
        self._slack    = None
        self._telegram = None
        self._whatsapp = None
        self._notion   = None
        self._drive    = None
        self._linear   = None
        self._stripe   = None
        self._qonto    = None
        self._supabase = None
        self._vercel   = None
        self._github   = None
        self._docker   = None
        self._ha       = None
        self._spotify  = None
        self._yt       = None
        self._wiki     = None
        self._arxiv    = None
        self._canva    = None
        self._figma    = None
        self._eleven   = None
        self._replicate= None
        self._maps     = None
        self._health   = None
        self._self_correction = None
        self._init_done = False

    def _init_agents(self):
        if self._init_done:
            return
        self._init_done = True
        try:
            from google_agent import GoogleAgent
            self._google = GoogleAgent()
        except Exception as e:
            warnings.warn(f"[TextAgent] GoogleAgent init: {e}")
        try:
            from memory_manager import MemoryManager
            self._memory = MemoryManager()
        except Exception as e:
            warnings.warn(f"[TextAgent] MemoryManager init: {e}")
        try:
            from mcps.slack_mcp import SlackMCP
            self._slack = SlackMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] SlackMCP: {e}")
        try:
            from mcps.telegram_mcp import TelegramMCP
            self._telegram = TelegramMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] TelegramMCP: {e}")
        try:
            from mcps.whatsapp_mcp import WhatsAppMCP
            self._whatsapp = WhatsAppMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] WhatsAppMCP: {e}")
        try:
            from mcps.notion_mcp import NotionMCP
            self._notion = NotionMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] NotionMCP: {e}")
        try:
            from mcps.drive_mcp import DriveMCP
            self._drive = DriveMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] DriveMCP: {e}")
        try:
            from mcps.linear_mcp import LinearMCP
            self._linear = LinearMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] LinearMCP: {e}")
        try:
            from mcps.stripe_mcp import StripeMCP
            self._stripe = StripeMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] StripeMCP: {e}")
        try:
            from mcps.qonto_mcp import QontoMCP
            self._qonto = QontoMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] QontoMCP: {e}")
        try:
            from mcps.supabase_mcp import SupabaseMCP
            self._supabase = SupabaseMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] SupabaseMCP: {e}")
        try:
            from mcps.vercel_mcp import VercelMCP
            self._vercel = VercelMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] VercelMCP: {e}")
        try:
            from mcps.github_mcp import GithubMCP
            self._github = GithubMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] GithubMCP: {e}")
        try:
            from mcps.docker_mcp import DockerMCP
            self._docker = DockerMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] DockerMCP: {e}")
        try:
            from mcps.homeassistant_mcp import HomeAssistantMCP
            self._ha = HomeAssistantMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] HomeAssistantMCP: {e}")
        try:
            from mcps.spotify_mcp import SpotifyMCP
            self._spotify = SpotifyMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] SpotifyMCP: {e}")
        try:
            from mcps.youtube_mcp import YouTubeMCP
            self._yt = YouTubeMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] YouTubeMCP: {e}")
        try:
            from mcps.wikipedia_mcp import WikipediaMCP
            self._wiki = WikipediaMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] WikipediaMCP: {e}")
        try:
            from mcps.arxiv_mcp import ArxivMCP
            self._arxiv = ArxivMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] ArxivMCP: {e}")
        try:
            from mcps.googlemaps_mcp import GoogleMapsMCP
            self._maps = GoogleMapsMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] GoogleMapsMCP: {e}")
        try:
            from mcps.applehealth_mcp import AppleHealthMCP
            self._health = AppleHealthMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] AppleHealthMCP: {e}")
        try:
            from mcps.canva_mcp import CanvaMCP
            self._canva = CanvaMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] CanvaMCP: {e}")
        try:
            from mcps.figma_mcp import FigmaMCP
            self._figma = FigmaMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] FigmaMCP: {e}")
        try:
            from mcps.elevenlabs_mcp import ElevenLabsMCP
            self._eleven = ElevenLabsMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] ElevenLabsMCP: {e}")
        try:
            from mcps.replicate_mcp import ReplicateMCP
            self._replicate = ReplicateMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] ReplicateMCP: {e}")
        try:
            from self_correction_agent import SelfCorrectionAgent
            self._self_correction = SelfCorrectionAgent()
        except Exception as e:
            warnings.warn(f"[TextAgent] SelfCorrectionAgent: {e}")

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if not GEMINI_API_KEY:
                raise RuntimeError("GEMINI_API_KEY non configurée")
            self._client = genai.Client(
                http_options={"api_version": "v1beta"},
                api_key=GEMINI_API_KEY,
            )
        return self._client

    async def _execute_tool(self, name: str, args: dict) -> str:
        """Exécute un outil et retourne son résultat en string."""
        print(f"[TextAgent] Tool: {name} args={args}")

        # ── GMAIL & CALENDAR ────────────────────────────────────────────────
        if name == "read_emails" and self._google:
            return await asyncio.to_thread(
                self._google.read_emails,
                max_results=args.get("max_results", 5),
                query=args.get("query", ""),
            )
        elif name == "send_email" and self._google:
            return await asyncio.to_thread(
                self._google.send_email,
                to=args["to"], subject=args["subject"], body=args["body"],
            )
        elif name == "get_email_body" and self._google:
            return await asyncio.to_thread(self._google.get_email_body, args["message_id"])
        elif name == "list_events" and self._google:
            return await asyncio.to_thread(self._google.list_events, max_results=args.get("max_results", 10))
        elif name == "create_event" and self._google:
            return await asyncio.to_thread(
                self._google.create_event,
                title=args["title"], start=args["start"], end=args["end"],
                description=args.get("description", ""), attendees=args.get("attendees", []),
            )
        elif name == "find_event" and self._google:
            return await asyncio.to_thread(self._google.find_event, query=args["query"], max_results=args.get("max_results", 5))
        elif name == "delete_event" and self._google:
            return await asyncio.to_thread(self._google.delete_event, args["event_id"])

        # ── MEMORY ──────────────────────────────────────────────────────────
        elif name == "search_memory" and self._memory:
            results = self._memory.search_memory(args.get("query", ""))
            if results:
                return "\n".join(f"[{r['timestamp']}] {r['content']}" for r in results)
            return "Aucun souvenir trouvé."
        elif name == "remember" and self._memory:
            content = args.get("content", "")
            category = args.get("category", "facts")
            entity_name = args.get("entity_name", "")
            if category == "entity" and entity_name:
                self._memory.update_entity(entity_name, content)
                return f"Entité '{entity_name}' mémorisée."
            self._memory.add_procedural(category, content)
            return f"Mémorisé dans {category}."
        elif name == "search_documents" and self._memory:
            results = self._memory.search_documents(args.get("query", ""))
            if results:
                return "\n\n---\n\n".join(
                    f"[{r['filename']}]\n{r['content']}" for r in results
                )
            return "Aucun document trouvé."

        # ── TERMINAL ────────────────────────────────────────────────────────
        elif name == "run_terminal":
            cmd = args.get("command", "")
            cwd = args.get("working_dir") or os.path.expanduser("~")
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd, cwd=cwd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
                return stdout.decode(errors="replace")[:2000] or "(pas de sortie)"
            except asyncio.TimeoutError:
                return "Timeout : commande trop longue."
            except Exception as e:
                return f"Erreur terminal : {e}"

        # ── SLACK ────────────────────────────────────────────────────────────
        elif name == "slack_list_channels" and self._slack:
            return await asyncio.to_thread(self._slack.list_channels)
        elif name == "slack_read_channel" and self._slack:
            return await asyncio.to_thread(self._slack.read_channel, args["channel_id"], args.get("limit", 20))
        elif name == "slack_send_message" and self._slack:
            return await asyncio.to_thread(self._slack.send_message, args["channel_id"], args["text"])
        elif name == "slack_search_messages" and self._slack:
            return await asyncio.to_thread(self._slack.search_messages, args["query"], args.get("count", 10))

        # ── TELEGRAM ────────────────────────────────────────────────────────
        elif name == "telegram_send_message" and self._telegram:
            return await asyncio.to_thread(self._telegram.send_message, args["text"], args.get("chat_id"))
        elif name == "telegram_send_photo" and self._telegram:
            return await asyncio.to_thread(self._telegram.send_photo, args["photo_url"], args.get("caption", ""), args.get("chat_id"))
        elif name == "telegram_get_updates" and self._telegram:
            return await asyncio.to_thread(self._telegram.get_updates, args.get("limit", 10))

        # ── WHATSAPP ─────────────────────────────────────────────────────────
        elif name == "whatsapp_send_message" and self._whatsapp:
            return await asyncio.to_thread(self._whatsapp.send_message, args["number"], args["text"])
        elif name == "whatsapp_send_media" and self._whatsapp:
            return await asyncio.to_thread(self._whatsapp.send_media, args["number"], args["media_url"], args.get("caption", ""))
        elif name == "whatsapp_get_messages" and self._whatsapp:
            return await asyncio.to_thread(self._whatsapp.get_recent_messages, args["number"], args.get("limit", 20))

        # ── NOTION ───────────────────────────────────────────────────────────
        elif name == "notion_search" and self._notion:
            return await asyncio.to_thread(self._notion.search, args["query"], args.get("limit", 10))
        elif name == "notion_get_page" and self._notion:
            return await asyncio.to_thread(self._notion.get_page, args["page_id"])
        elif name == "notion_create_page" and self._notion:
            return await asyncio.to_thread(self._notion.create_page, args["parent_id"], args["title"], args.get("content", ""))
        elif name == "notion_query_database" and self._notion:
            return await asyncio.to_thread(self._notion.query_database, args["database_id"], args.get("filter_json", ""))
        elif name == "notion_append_page" and self._notion:
            return await asyncio.to_thread(self._notion.append_to_page, args["page_id"], args["content"])

        # ── GOOGLE DRIVE / SHEETS / DOCS ─────────────────────────────────────
        elif name == "drive_list_files" and self._drive:
            return await asyncio.to_thread(self._drive.list_files, args.get("query", ""), args.get("limit", 10))
        elif name == "drive_read_file" and self._drive:
            return await asyncio.to_thread(self._drive.read_file, args["file_id"])
        elif name == "drive_upload_file" and self._drive:
            return await asyncio.to_thread(self._drive.upload_file, args["local_path"], args.get("folder_id", ""))
        elif name == "sheets_read" and self._drive:
            return await asyncio.to_thread(self._drive.read_sheet, args["spreadsheet_id"], args.get("range", "Sheet1!A1:Z100"))
        elif name == "sheets_write" and self._drive:
            return await asyncio.to_thread(self._drive.write_sheet, args["spreadsheet_id"], args["range"], args["values_json"])
        elif name == "sheets_append" and self._drive:
            return await asyncio.to_thread(self._drive.append_sheet, args["spreadsheet_id"], args["range"], args["values_json"])
        elif name == "docs_read" and self._drive:
            return await asyncio.to_thread(self._drive.read_doc, args["doc_id"])

        # ── LINEAR ───────────────────────────────────────────────────────────
        elif name == "linear_list_issues" and self._linear:
            return await asyncio.to_thread(self._linear.list_issues, args.get("team_id", ""), args.get("status", ""), args.get("limit", 20))
        elif name == "linear_get_issue" and self._linear:
            return await asyncio.to_thread(self._linear.get_issue, args["issue_id"])
        elif name == "linear_create_issue" and self._linear:
            return await asyncio.to_thread(self._linear.create_issue, args["title"], args.get("description", ""), args.get("team_id", ""), args.get("priority", 0))
        elif name == "linear_update_issue" and self._linear:
            return await asyncio.to_thread(self._linear.update_issue, args["issue_id"], args.get("status", ""), args.get("title", ""), args.get("description", ""))
        elif name == "linear_list_projects" and self._linear:
            return await asyncio.to_thread(self._linear.list_projects, args.get("team_id", ""))
        elif name == "linear_list_teams" and self._linear:
            return await asyncio.to_thread(self._linear.list_teams)

        # ── STRIPE ───────────────────────────────────────────────────────────
        elif name == "stripe_list_customers" and self._stripe:
            return await asyncio.to_thread(self._stripe.list_customers, args.get("limit", 10), args.get("email", ""))
        elif name == "stripe_get_customer" and self._stripe:
            return await asyncio.to_thread(self._stripe.get_customer, args["customer_id"])
        elif name == "stripe_list_payments" and self._stripe:
            return await asyncio.to_thread(self._stripe.list_payments, args.get("limit", 10), args.get("customer_id", ""))
        elif name == "stripe_list_invoices" and self._stripe:
            return await asyncio.to_thread(self._stripe.list_invoices, args.get("limit", 10), args.get("customer_id", ""))
        elif name == "stripe_get_balance" and self._stripe:
            return await asyncio.to_thread(self._stripe.get_balance)
        elif name == "stripe_create_invoice_item" and self._stripe:
            return await asyncio.to_thread(self._stripe.create_invoice_item, args["customer_id"], args["amount_cents"], args["currency"], args["description"])
        elif name == "stripe_send_invoice" and self._stripe:
            return await asyncio.to_thread(self._stripe.send_invoice, args["invoice_id"])

        # ── QONTO ────────────────────────────────────────────────────────────
        elif name == "qonto_get_balance" and self._qonto:
            return await asyncio.to_thread(self._qonto.get_balance)
        elif name == "qonto_list_transactions" and self._qonto:
            return await asyncio.to_thread(self._qonto.list_transactions, args.get("limit", 25), args.get("status", "completed"))
        elif name == "qonto_get_organization" and self._qonto:
            return await asyncio.to_thread(self._qonto.get_organization)

        # ── SUPABASE ─────────────────────────────────────────────────────────
        elif name == "supabase_query" and self._supabase:
            return await asyncio.to_thread(self._supabase.query_table, args["table"], args.get("filters_json", ""), args.get("limit", 20), args.get("columns", "*"))
        elif name == "supabase_insert" and self._supabase:
            return await asyncio.to_thread(self._supabase.insert_row, args["table"], args["data_json"])
        elif name == "supabase_update" and self._supabase:
            return await asyncio.to_thread(self._supabase.update_row, args["table"], args["filters_json"], args["data_json"])
        elif name == "supabase_delete" and self._supabase:
            return await asyncio.to_thread(self._supabase.delete_row, args["table"], args["filters_json"])
        elif name == "supabase_sql" and self._supabase:
            return await asyncio.to_thread(self._supabase.run_sql, args["query"])
        elif name == "supabase_list_tables" and self._supabase:
            return await asyncio.to_thread(self._supabase.list_tables)

        # ── VERCEL ───────────────────────────────────────────────────────────
        elif name == "vercel_list_projects" and self._vercel:
            return await asyncio.to_thread(self._vercel.list_projects, args.get("limit", 20))
        elif name == "vercel_get_project" and self._vercel:
            return await asyncio.to_thread(self._vercel.get_project, args["project_id"])
        elif name == "vercel_list_deployments" and self._vercel:
            return await asyncio.to_thread(self._vercel.list_deployments, args.get("project_id", ""), args.get("limit", 10))
        elif name == "vercel_get_deployment" and self._vercel:
            return await asyncio.to_thread(self._vercel.get_deployment, args["deployment_id"])
        elif name == "vercel_get_logs" and self._vercel:
            return await asyncio.to_thread(self._vercel.get_deployment_logs, args["deployment_id"])

        # ── GITHUB ───────────────────────────────────────────────────────────
        elif name == "github_list_repos" and self._github:
            return await asyncio.to_thread(self._github.list_repos, args.get("limit", 20))
        elif name == "github_get_repo" and self._github:
            return await asyncio.to_thread(self._github.get_repo_info, args.get("repo", ""))
        elif name == "github_list_issues" and self._github:
            return await asyncio.to_thread(self._github.list_issues, args.get("repo", ""), args.get("state", "open"), args.get("limit", 10))
        elif name == "github_create_issue" and self._github:
            return await asyncio.to_thread(self._github.create_issue, args["title"], args.get("body", ""), args.get("labels"), args.get("repo", ""))
        elif name == "github_list_prs" and self._github:
            return await asyncio.to_thread(self._github.list_prs, args.get("repo", ""), args.get("state", "open"), args.get("limit", 10))
        elif name == "github_list_commits" and self._github:
            return await asyncio.to_thread(self._github.list_commits, args.get("repo", ""), args.get("branch", "main"), args.get("limit", 10))
        elif name == "github_search_code" and self._github:
            return await asyncio.to_thread(self._github.search_code, args["query"], args.get("repo", ""))

        # ── DOCKER ───────────────────────────────────────────────────────────
        elif name == "docker_list_containers" and self._docker:
            return await asyncio.to_thread(self._docker.list_containers, args.get("all", False))
        elif name == "docker_get_logs" and self._docker:
            return await asyncio.to_thread(self._docker.get_container_logs, args["container"], args.get("tail", 50))
        elif name == "docker_start" and self._docker:
            return await asyncio.to_thread(self._docker.start_container, args["container"])
        elif name == "docker_stop" and self._docker:
            return await asyncio.to_thread(self._docker.stop_container, args["container"])
        elif name == "docker_restart" and self._docker:
            return await asyncio.to_thread(self._docker.restart_container, args["container"])
        elif name == "docker_list_images" and self._docker:
            return await asyncio.to_thread(self._docker.list_images)
        elif name == "docker_stats" and self._docker:
            return await asyncio.to_thread(self._docker.container_stats, args["container"])

        # ── HOME ASSISTANT ───────────────────────────────────────────────────
        elif name == "ha_get_states" and self._ha:
            return await asyncio.to_thread(self._ha.get_states, args.get("domain", ""))
        elif name == "ha_get_entity" and self._ha:
            return await asyncio.to_thread(self._ha.get_entity, args["entity_id"])
        elif name == "ha_call_service" and self._ha:
            return await asyncio.to_thread(self._ha.call_service, args["domain"], args["service"], args.get("entity_id", ""), args.get("data_json", ""))
        elif name == "ha_turn_on" and self._ha:
            return await asyncio.to_thread(self._ha.turn_on, args["entity_id"])
        elif name == "ha_turn_off" and self._ha:
            return await asyncio.to_thread(self._ha.turn_off, args["entity_id"])

        # ── SPOTIFY ──────────────────────────────────────────────────────────
        elif name == "spotify_current" and self._spotify:
            return await asyncio.to_thread(self._spotify.get_current_playback)
        elif name == "spotify_play" and self._spotify:
            return await asyncio.to_thread(self._spotify.play, args.get("uri", ""), args.get("device_id", ""))
        elif name == "spotify_pause" and self._spotify:
            return await asyncio.to_thread(self._spotify.pause)
        elif name == "spotify_next" and self._spotify:
            return await asyncio.to_thread(self._spotify.next_track)
        elif name == "spotify_previous" and self._spotify:
            return await asyncio.to_thread(self._spotify.previous_track)
        elif name == "spotify_volume" and self._spotify:
            return await asyncio.to_thread(self._spotify.set_volume, args["volume_percent"])
        elif name == "spotify_search" and self._spotify:
            return await asyncio.to_thread(self._spotify.search, args["query"], args.get("type", "track"), args.get("limit", 5))

        # ── YOUTUBE ──────────────────────────────────────────────────────────
        elif name == "youtube_search" and self._yt:
            return await asyncio.to_thread(self._yt.search, args["query"], args.get("max_results", 5))
        elif name == "youtube_get_video" and self._yt:
            return await asyncio.to_thread(self._yt.get_video_details, args["video_id"])

        # ── WIKIPEDIA ────────────────────────────────────────────────────────
        elif name == "wikipedia_search" and self._wiki:
            return await asyncio.to_thread(self._wiki.search, args["query"])
        elif name == "wikipedia_summary" and self._wiki:
            return await asyncio.to_thread(self._wiki.get_summary, args["title"])

        # ── ARXIV ────────────────────────────────────────────────────────────
        elif name == "arxiv_search" and self._arxiv:
            return await asyncio.to_thread(self._arxiv.search, args["query"], args.get("max_results", 5))

        # ── GOOGLE MAPS ──────────────────────────────────────────────────────
        elif name == "maps_directions" and self._maps:
            return await asyncio.to_thread(self._maps.get_directions, args["origin"], args["destination"], args.get("mode", "driving"))
        elif name == "maps_place_search" and self._maps:
            return await asyncio.to_thread(self._maps.search_places, args["query"], args.get("location", ""), args.get("radius", 5000))

        # ── APPLE HEALTH ─────────────────────────────────────────────────────
        elif name == "health_summary" and self._health:
            return await asyncio.to_thread(self._health.get_summary)
        elif name == "health_steps" and self._health:
            return await asyncio.to_thread(self._health.get_steps, args.get("days", 7))
        elif name == "health_sleep" and self._health:
            return await asyncio.to_thread(self._health.get_sleep, args.get("days", 7))

        # ── SELF-CORRECTION ──────────────────────────────────────────────────
        elif name == "jarvis_read_file" and self._self_correction:
            path = args.get("path", "")
            if not path.startswith("/"):
                from pathlib import Path as _Path
                path = str(_Path("/Users/bryandev/jarvis") / path)
            return self._self_correction.read_file(path)

        elif name == "jarvis_write_file" and self._self_correction:
            path = args.get("path", "")
            if not path.startswith("/"):
                from pathlib import Path as _Path
                path = str(_Path("/Users/bryandev/jarvis") / path)
            return self._self_correction.write_file(path, args.get("content", ""))

        elif name == "jarvis_list_files" and self._self_correction:
            path = args.get("path", "")
            if path and not path.startswith("/"):
                from pathlib import Path as _Path
                path = str(_Path("/Users/bryandev/jarvis") / path)
            return self._self_correction.list_files(path)

        elif name == "jarvis_git_commit" and self._self_correction:
            return self._self_correction.git_commit(args.get("message", "chore: Ada auto-commit"))

        elif name == "self_correct_file" and self._self_correction:
            path = args.get("file_path", "")
            if not path.startswith("/"):
                from pathlib import Path as _Path
                path = str(_Path("/Users/bryandev/jarvis") / path)
            return self._self_correction.correct_file(path, args.get("error_description", ""))

        return f"Outil '{name}' non disponible ou non configuré."

    async def run(self, text: str) -> str:
        """
        Agentic loop : envoie `text` à Gemini avec les outils,
        exécute les function calls, retourne la réponse finale.
        """
        self._init_agents()
        client = self._get_client()

        # Mémoire courte : contexte de session simple (sans état inter-messages pour l'instant)
        memory_block = ""
        if self._memory:
            try:
                mem = self._memory.get_startup_context()
                if mem:
                    memory_block = f"\n\n[MÉMOIRE]\n{mem}"
            except Exception:
                pass

        system = ADA_SYSTEM_PROMPT + memory_block
        messages = [types.Content(role="user", parts=[types.Part(text=text)])]

        for _ in range(8):  # max 8 tours pour éviter les boucles infinies
            # Retry jusqu'à 3 fois si le modèle retourne parts=None (thinking budget épuisé)
            parts = []
            for _retry in range(3):
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=TEXT_MODEL,
                    contents=messages,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        tools=_BRIDGE_TOOLS,
                        temperature=0.7,
                        thinking_config=types.ThinkingConfig(thinking_budget=0),
                    ),
                )
                candidate = response.candidates[0]
                content = candidate.content
                parts = content.parts if (content and content.parts) else []
                if parts:
                    break
                await asyncio.sleep(0.5)

            # Collecter les function calls
            function_calls = [p for p in parts if p.function_call]

            if not function_calls:
                # Pas de tool call → réponse finale
                text_parts = [p.text for p in parts if p.text]
                return "\n".join(text_parts).strip() or "..."

            # Ajouter la réponse du modèle à l'historique
            messages.append(content)

            # Exécuter tous les tools en parallèle
            async def _exec(fc):
                result = await self._execute_tool(fc.function_call.name, dict(fc.function_call.args))
                return types.Part(
                    function_response=types.FunctionResponse(
                        id=fc.function_call.id or fc.function_call.name,
                        name=fc.function_call.name,
                        response={"result": result},
                    )
                )

            tool_result_parts = await asyncio.gather(*[_exec(fc) for fc in function_calls])
            messages.append(types.Content(role="user", parts=list(tool_result_parts)))

        return "Désolé, je n'ai pas pu terminer cette tâche."


# ─── INSTANCE GLOBALE ─────────────────────────────────────────────────────────

# ── Instance Ada partagée (injectée par server.py ou créée en standalone) ──
_ada_loop = None
_agent = TextAgent()


def set_ada_loop(loop) -> None:
    """Enregistre l'AudioLoop d'Ada pour le mode texte. Appelé par server.py."""
    global _ada_loop
    _ada_loop = loop
    print("[ExternalBridge] AudioLoop Ada enregistrée — capacités complètes actives.")


async def handle_external_message(
    source: Literal["telegram", "whatsapp"],
    sender: str,
    text: str,
) -> str:
    try:
        if _ada_loop is not None:
            reply = await _ada_loop.process_text_message(text)
        else:
            reply = await _agent.run(text)
    except Exception as e:
        import traceback
        traceback.print_exc()
        warnings.warn(f"[ExternalBridge] Erreur agent : {e}")
        reply = "Désolé, une erreur est survenue."

    if len(reply) < TEXT_VOICE_THRESHOLD:
        await _send_text(source, sender, reply)
    else:
        ogg_bytes = await _text_to_ogg(reply)
        if ogg_bytes:
            await _send_voice(source, sender, ogg_bytes)
        else:
            await _send_text(source, sender, reply)

    return reply


# ─── TTS ──────────────────────────────────────────────────────────────────────

async def _text_to_ogg(text: str) -> bytes | None:
    try:
        client = _agent._get_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=VOICE_MODEL,
            contents=[text],
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
                    )
                ),
            ),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data and part.inline_data.data:
                return _pcm_to_ogg(part.inline_data.data)
    except Exception as e:
        warnings.warn(f"[ExternalBridge] TTS erreur : {e}")
    return None


def _pcm_to_ogg(pcm_bytes: bytes, sample_rate: int = 24000) -> bytes:
    import shutil
    if not shutil.which("ffmpeg"):
        return pcm_bytes
    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as f:
        f.write(pcm_bytes)
        pcm_path = f.name
    ogg_path = pcm_path.replace(".pcm", ".ogg")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
             "-i", pcm_path, "-c:a", "libopus", "-b:a", "32k", ogg_path],
            check=True, capture_output=True,
        )
        with open(ogg_path, "rb") as f:
            return f.read()
    except Exception as e:
        warnings.warn(f"[ExternalBridge] PCM→OGG erreur : {e}")
        return pcm_bytes
    finally:
        for p in (pcm_path, ogg_path):
            try: os.unlink(p)
            except OSError: pass


# ─── ENVOI ────────────────────────────────────────────────────────────────────

def _tg_url(method: str) -> str:
    return TELEGRAM_API.format(token=TELEGRAM_BOT_TOKEN, method=method)


async def _send_text(source: Literal["telegram", "whatsapp"], sender: str, text: str) -> None:
    if source == "telegram":
        async with httpx.AsyncClient(timeout=15) as c:
            await c.post(_tg_url("sendMessage"), json={"chat_id": sender, "text": text})
    else:
        if not WHATSAPP_API_KEY:
            return
        async with httpx.AsyncClient(
            timeout=20, headers={"apikey": WHATSAPP_API_KEY, "Content-Type": "application/json"}
        ) as c:
            await c.post(
                f"{WHATSAPP_API_URL}/message/sendText/{WHATSAPP_INSTANCE}",
                json={"number": sender, "text": text},
            )


async def _send_voice(source: Literal["telegram", "whatsapp"], sender: str, ogg_bytes: bytes) -> None:
    if source == "telegram":
        async with httpx.AsyncClient(timeout=30) as c:
            await c.post(
                _tg_url("sendVoice"),
                data={"chat_id": sender},
                files={"voice": ("voice.ogg", io.BytesIO(ogg_bytes), "audio/ogg")},
            )
    else:
        if not WHATSAPP_API_KEY:
            return
        import base64
        b64 = base64.b64encode(ogg_bytes).decode()
        async with httpx.AsyncClient(
            timeout=30, headers={"apikey": WHATSAPP_API_KEY, "Content-Type": "application/json"}
        ) as c:
            await c.post(
                f"{WHATSAPP_API_URL}/message/sendMedia/{WHATSAPP_INSTANCE}",
                json={"number": sender, "mediatype": "audio",
                      "mimetype": "audio/ogg; codecs=opus",
                      "media": b64, "fileName": "voice.ogg"},
            )


# ─── TRANSCRIPTION VOCALE ─────────────────────────────────────────────────────

async def _download_telegram_file(file_id: str) -> bytes | None:
    """Télécharge un fichier depuis Telegram et retourne ses bytes."""
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            resp = await c.get(_tg_url("getFile"), params={"file_id": file_id})
            data = resp.json()
            if not data.get("ok"):
                warnings.warn(f"[ExternalBridge] getFile erreur: {data.get('description')}")
                return None
            file_path = data["result"]["file_path"]
            file_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            audio_resp = await c.get(file_url)
            audio_resp.raise_for_status()
            return audio_resp.content
    except Exception as e:
        warnings.warn(f"[ExternalBridge] Téléchargement fichier Telegram erreur : {e}")
        return None


async def _transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str | None:
    """Transcrit un message vocal via Gemini Flash multimodal."""
    try:
        client = _agent._get_client()
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=TEXT_MODEL,
            contents=[
                types.Content(parts=[
                    types.Part(inline_data=types.Blob(mime_type=mime_type, data=audio_bytes)),
                    types.Part(text="Transcris exactement ce message vocal en français. Retourne uniquement la transcription, sans commentaire."),
                ]),
            ],
        )
        text = response.candidates[0].content.parts[0].text.strip()
        return text if text else None
    except Exception as e:
        warnings.warn(f"[ExternalBridge] Transcription audio erreur : {e}")
        return None


# ─── POLLING TELEGRAM ─────────────────────────────────────────────────────────

async def _telegram_polling_loop() -> None:
    if not TELEGRAM_BOT_TOKEN:
        warnings.warn("[ExternalBridge] TELEGRAM_BOT_TOKEN manquant — polling désactivé")
        return

    offset = 0
    allowed_chat = str(TELEGRAM_CHAT_ID) if TELEGRAM_CHAT_ID else None
    print(f"[ExternalBridge] Telegram polling démarré (chat autorisé: {allowed_chat})")

    async with httpx.AsyncClient(timeout=35) as client:
        while True:
            try:
                resp = await client.get(
                    _tg_url("getUpdates"),
                    params={"offset": offset, "timeout": 30, "allowed_updates": ["message"]},
                )
                data = resp.json()
                if not data.get("ok"):
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    msg = update.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id", ""))

                    if allowed_chat and chat_id != allowed_chat:
                        print(f"[ExternalBridge] Message ignoré (chat_id={chat_id} ≠ {allowed_chat})")
                        continue

                    text = msg.get("text", "").strip()

                    # Message vocal : transcription avant traitement
                    if not text:
                        voice_obj = msg.get("voice") or msg.get("audio")
                        if voice_obj:
                            file_id = voice_obj.get("file_id", "")
                            if not file_id:
                                continue
                            mime_type = voice_obj.get("mime_type", "audio/ogg")
                            print(f"[ExternalBridge] Message vocal reçu (file_id={file_id[:20]}…)")
                            audio_bytes = await _download_telegram_file(file_id)
                            if audio_bytes:
                                transcribed = await _transcribe_audio(audio_bytes, mime_type=mime_type)
                                if transcribed:
                                    print(f"[ExternalBridge] Transcription: {transcribed[:80]}")
                                    text = transcribed
                        if not text:
                            continue

                    print(f"[ExternalBridge] Telegram message traité: {text[:80]}")
                    asyncio.create_task(handle_external_message("telegram", chat_id, text))

            except asyncio.CancelledError:
                return
            except Exception as e:
                warnings.warn(f"[ExternalBridge] Telegram polling erreur : {e}")
                await asyncio.sleep(5)


# ─── POLLING WHATSAPP ─────────────────────────────────────────────────────────

async def _whatsapp_polling_loop() -> None:
    if not WHATSAPP_API_KEY or not WHATSAPP_API_URL:
        warnings.warn("[ExternalBridge] Config WhatsApp manquante — polling désactivé")
        return

    seen_ids: set[str] = set()
    headers = {"apikey": WHATSAPP_API_KEY, "Content-Type": "application/json"}
    print("[ExternalBridge] WhatsApp polling démarré")

    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        while True:
            try:
                resp = await client.get(
                    f"{WHATSAPP_API_URL}/chat/findMessages/{WHATSAPP_INSTANCE}",
                    params={"count": 20},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    messages = data if isinstance(data, list) else data.get("messages", [])
                    for m in messages:
                        key = m.get("key", {})
                        msg_id = key.get("id", "")
                        if key.get("fromMe", True) or msg_id in seen_ids:
                            continue
                        seen_ids.add(msg_id)
                        content = m.get("message", {})
                        text = (
                            content.get("conversation")
                            or content.get("extendedTextMessage", {}).get("text", "")
                        ).strip()
                        sender = key.get("remoteJid", "")
                        if text and sender:
                            print(f"[ExternalBridge] WhatsApp message reçu: {text[:80]}")
                            asyncio.create_task(handle_external_message("whatsapp", sender, text))
            except asyncio.CancelledError:
                return
            except Exception as e:
                warnings.warn(f"[ExternalBridge] WhatsApp polling erreur : {e}")
            await asyncio.sleep(8)


# ─── POINT D'ENTRÉE ───────────────────────────────────────────────────────────

def start_bridge() -> list[asyncio.Task]:
    global _ada_loop
    if _ada_loop is None:
        try:
            from ada import AudioLoop
            _ada_loop = AudioLoop(video_mode="none")
            print("[ExternalBridge] AudioLoop créée en mode standalone — capacités complètes actives.")
        except Exception as e:
            warnings.warn(f"[ExternalBridge] Impossible de créer AudioLoop standalone: {e} — fallback TextAgent.")
    tasks = [
        asyncio.create_task(_telegram_polling_loop(), name="telegram_bridge"),
        asyncio.create_task(_whatsapp_polling_loop(), name="whatsapp_bridge"),
    ]
    return tasks
