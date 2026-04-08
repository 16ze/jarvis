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

# ─── FORMATEUR D'ERREURS ACTIONNABLE ─────────────────────────────────────────
_ENV_FOR_TOOL: dict = {
    "slack": "SLACK_BOT_TOKEN", "notion": "NOTION_API_KEY", "linear": "LINEAR_API_KEY",
    "stripe": "STRIPE_SECRET_KEY", "qonto": "QONTO_API_KEY", "supabase": "SUPABASE_URL",
    "vercel": "VERCEL_TOKEN", "github": "GITHUB_TOKEN", "ha": "HOME_ASSISTANT_URL",
    "spotify": "SPOTIFY_CLIENT_ID", "maps": "GOOGLE_MAPS_API_KEY", "canva": "CANVA_API_KEY",
    "figma": "FIGMA_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY", "replicate": "REPLICATE_API_TOKEN",
    "whatsapp": "WHATSAPP_API_URL", "drive": "GOOGLE_CLIENT_ID", "sheets": "GOOGLE_CLIENT_ID",
    "docs": "GOOGLE_CLIENT_ID", "telegram": "TELEGRAM_BOT_TOKEN", "twilio": "TWILIO_ACCOUNT_SID",
}

def _format_tool_error(tool_name: str, exc: Exception) -> str:
    prefix = tool_name.split("_")[0]
    env_var = _ENV_FOR_TOOL.get(prefix)
    err_str = str(exc)
    if env_var and not os.getenv(env_var):
        return (f"CONFIGURATION MANQUANTE — '{tool_name}' nécessite {env_var} (absent du .env). "
                f"Informer Monsieur de le configurer.")
    if any(k in err_str.lower() for k in ["401", "unauthorized", "forbidden", "invalid token"]):
        return f"ERREUR AUTHENTIFICATION — '{tool_name}' : token invalide.{' Vérifier ' + env_var + '.' if env_var else ''} Détail : {err_str}"
    if any(k in err_str.lower() for k in ["connection", "timeout", "unreachable", "refused"]):
        return f"ERREUR RÉSEAU — '{tool_name}' injoignable. Vérifier connexion/service. Détail : {err_str}"
    if any(k in err_str.lower() for k in ["keyerror", "missing", "required", "typeerror", "nonetype"]):
        return f"ERREUR PARAMÈTRE — '{tool_name}' : paramètre invalide. Reformuler l'appel. Détail : {err_str}"
    return f"ERREUR — '{tool_name}' : {err_str}"

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

    # ─── LANGUE ────────────────────────────────────────────────────────────
    "RÈGLE ABSOLUE N°1 : Tu parles UNIQUEMENT ET EXCLUSIVEMENT en français. "
    "JAMAIS d'anglais, même partiel, même pour un seul mot technique. "
    "Si un outil retourne du texte en anglais, tu le traduis ou tu le résumes en français. "

    # ─── PERSONNALITÉ ──────────────────────────────────────────────────────
    "Tu as une personnalité vive, directe et légèrement espiègle. "
    "Tu es une intelligence artificielle supérieure. "
    "Tes réponses sont concises et directes, sans préambule ni politesse inutile. "
    "Tu réponds en texte naturel sans markdown. "

    # ─── ACTION ────────────────────────────────────────────────────────────
    "RÈGLE ABSOLUE N°2 : Quand tu as un outil pour accomplir une tâche, tu l'UTILISES IMMÉDIATEMENT. "
    "Tu ne décris jamais ce que tu vas faire avant de le faire. Tu agis d'abord, tu commentes ensuite. "

    # ─── RAISONNEMENT INTERNE ──────────────────────────────────────────────
    "RAISONNEMENT : Avant d'agir sur une demande complexe ou ambiguë, identifie silencieusement : "
    "  (a) L'outil EXACT à utiliser parmi tous ceux disponibles. "
    "  (b) Si une séquence est nécessaire (ex: chercher avant de jouer, lister avant de contrôler). "
    "  (c) Les paramètres requis et leurs valeurs correctes. "
    "Ne verbalise pas ce processus. Exécute directement. "

    # ─── SÉLECTION D'OUTIL ─────────────────────────────────────────────────
    "RÈGLES CRITIQUES DE SÉLECTION D'OUTIL : "
    "Lumières/prises Tuya → control_light(target=ALIAS_EXACT, action=...) — JAMAIS ha_turn_on. "
    "  Alias inconnu → list_smart_devices d'abord. "
    "Musique → spotify_search(query=..., search_type='track'/'playlist') PUIS spotify_play(uri=résultat). "
    "TV Chromecast → play_youtube_on_chromecast(video_url=URL_COMPLETE) ou play_media_on_chromecast. "
    "Caméra PTZ SmartLife → camera_look(question='...') pour voir et analyser. camera_ptz_move(direction=...) pour orienter. "
    "  Suivi automatique → camera_tracking(enabled=True/False). Surveillance alertes → camera_watch(enabled=True). "
    "Rappels → reminder_set(message=..., datetime_iso='YYYY-MM-DDTHH:MM:SS') timezone Paris. "
    "Emails → confirmer AVANT send_email (irréversible). "
    "Recherche approfondie → run_research. Simple → wikipedia_article. "

    # ─── PROTOCOLE ANTI-ÉCHEC ──────────────────────────────────────────────
    "PROTOCOLE RÉCUPÉRATION D'ERREUR — JAMAIS 'je n'ai pas réussi' sans diagnostic : "
    "(1) Erreur paramètre → reformule l'appel avec les bons paramètres. "
    "(2) Alias/URI introuvable → utilise l'outil de découverte correspondant. "
    "(3) Outil 'non disponible' → dis quelle variable d'env configurer. "
    "(4) Erreur API → réessaie une fois, puis explique précisément. "
    "(5) Bug code → self_correct_file immédiatement. "
    "Format réponse après échec : cause précise + alternative proposée. "

    # ─── MÉMOIRE ───────────────────────────────────────────────────────────
    "Utilise search_memory quand Bryan fait référence au passé. "
    "Utilise remember proactivement pour préférences, habitudes, infos importantes. "
    "Utilise search_documents pour répondre depuis les fichiers uploadés. "

    "Tu as accès à Gmail, Google Calendar, la mémoire persistante, le terminal, "
    "Slack, Telegram, WhatsApp, Notion, Drive, Linear, Stripe, Qonto, Supabase, "
    "Vercel, GitHub, Docker, Home Assistant, Spotify, YouTube, Wikipedia, ArXiv, "
    "Chromecast, domotique Tuya, rappels temporels, navigation web avancée."
)

# ─── TOOL DEFINITIONS (subset utile pour le bridge texte) ─────────────────────

from mcp_tools_declarations import MCP_TOOLS, MCP_TOOL_NAMES
from mcps.twilio_mcp import TwilioMCP
from user_profile_manager import UserProfileManager

_upm = UserProfileManager()

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
    # Twilio
    {"name": "twilio_send_sms", "description": "Envoie un SMS via Twilio.",
     "parameters": {"type": "OBJECT", "properties": {
         "to": {"type": "STRING", "description": "Numéro de téléphone du destinataire (format E.164, ex: +33612345678)"},
         "body": {"type": "STRING", "description": "Contenu du message SMS"}
     }, "required": ["to", "body"]}},
]

_EXCLUDED_FROM_BRIDGE = {
    "generate_cad", "iterate_cad", "generate_cad_prototype",
    "control_computer",
    "discover_printers", "print_stl", "get_print_status",
    "run_web_agent",
    "execute_pc_task",
    "ada_sleep", "ada_wake",
    "camera_switch",  # pas de live stream en mode texte
}
_BRIDGE_MCP_TOOLS = [t for t in MCP_TOOLS if t["name"] not in _EXCLUDED_FROM_BRIDGE]
_BRIDGE_TOOLS = [{"function_declarations": _CORE_TOOL_DEFS + _BRIDGE_MCP_TOOLS}]

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
        self._reminder = None
        self._cast     = None
        self._tuya        = None
        self._research    = None
        self._task        = None
        self._anticipation = None
        self._monitoring  = None
        self._evolution   = None
        self._advanced_browser = None
        self.twilio = None # Added for TwilioMCP
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
        try:
            from chromecast_agent import CastAgent
            self._cast = CastAgent()
        except Exception as e:
            warnings.warn(f"[TextAgent] CastAgent: {e}")
        try:
            from reminder_manager import ReminderManager
            self._reminder = ReminderManager()
            async def _on_reminder_telegram(message: str):
                await _send_text("telegram", TELEGRAM_CHAT_ID, f"⏰ Rappel : {message}")
            self._reminder.on_reminder = _on_reminder_telegram
            self._reminder.start()
        except Exception as e:
            warnings.warn(f"[TextAgent] ReminderManager: {e}")
        try:
            from tuya_agent import TuyaAgent
            self._tuya = TuyaAgent()
        except Exception as e:
            warnings.warn(f"[TextAgent] TuyaAgent: {e}")
        try:
            from mcps.tuya_camera_mcp import TuyaCameraMCP
            self._tuya_camera = TuyaCameraMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] TuyaCameraMCP: {e}")
            self._tuya_camera = None
        try:
            from research_agent import ResearchAgent
            self._research = ResearchAgent(
                wikipedia=self._wiki,
                arxiv=self._arxiv,
                youtube=self._yt,
            )
        except Exception as e:
            warnings.warn(f"[TextAgent] ResearchAgent: {e}")
        try:
            from task_agent import TaskAgent
            self._task = TaskAgent()
        except Exception as e:
            warnings.warn(f"[TextAgent] TaskAgent: {e}")
        try:
            from anticipation_agent import AnticipationAgent
            self._anticipation = AnticipationAgent(memory=self._memory)
        except Exception as e:
            warnings.warn(f"[TextAgent] AnticipationAgent: {e}")
        try:
            from monitoring_agent import MonitoringAgent
            self._monitoring = MonitoringAgent(
                telegram=self._telegram,
                slack=self._slack,
                github=self._github,
                google_agent=self._google,
            )
        except Exception as e:
            warnings.warn(f"[TextAgent] MonitoringAgent: {e}")
        try:
            self.twilio = TwilioMCP()
        except Exception as e:
            warnings.warn(f"[TextAgent] TwilioMCP: {e}")
        try:
            from self_evolution_agent import SelfEvolutionAgent
            self._evolution = SelfEvolutionAgent()
        except Exception as e:
            warnings.warn(f"[TextAgent] SelfEvolutionAgent: {e}")
        try:
            from advanced_browser_agent import AdvancedBrowserAgent
            self._advanced_browser = AdvancedBrowserAgent()
        except Exception as e:
            warnings.warn(f"[TextAgent] AdvancedBrowserAgent: {e}")
            self._advanced_browser = None

    def _get_client() -> genai.Client:
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

        # ── TWILIO ───────────────────────────────────────────────────────────
        elif name == "twilio_send_sms" and self.twilio:
            return await asyncio.to_thread(self.twilio.send_sms, args["to"], args["body"])

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

        # ── WIKIPEDIA ────────────────────────────────────────────────────────
        elif name == "wikipedia_search" and self._wiki:
            return await asyncio.to_thread(self._wiki.search, args["query"])

        # ── ARXIV ────────────────────────────────────────────────────────────
        elif name == "arxiv_search" and self._arxiv:
            return await asyncio.to_thread(self._arxiv.search, args["query"], args.get("max_results", 5))

        # ── GOOGLE MAPS ──────────────────────────────────────────────────────
        elif name == "maps_directions" and self._maps:
            return await asyncio.to_thread(self._maps.get_directions, args["origin"], args["destination"], args.get("mode", "driving"))

        # ── APPLE HEALTH ─────────────────────────────────────────────────────
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

        # ── SELF-EVOLUTION ─────────────────────────────────────────────────────
        elif name == "self_evolve" and self._evolution:
            return await self._evolution.evolve(
                goal=args.get("goal", ""),
                failed_context=args.get("failed_context", ""),
            )

        # ── CAMÉRA TUYA PTZ ───────────────────────────────────────────────────
        elif name == "camera_switch":
            source = args.get("source", "none")
            return f"Changement de source vidéo vers '{source}' — disponible uniquement en mode voix (Ada doit être active)."

        elif name == "camera_ptz_move" and self._tuya_camera:
            return await self._tuya_camera.ptz_move(args.get("direction", ""), int(args.get("duration_ms", 600)))

        elif name == "camera_goto_preset" and self._tuya_camera:
            return await self._tuya_camera.ptz_preset(int(args.get("preset", 1)))

        elif name == "camera_look" and self._tuya_camera:
            _payload = await self._tuya_camera.take_snapshot()
            if not _payload:
                return "Impossible de capturer une image depuis la caméra Tuya (vérifier connexion réseau)."
            _q = args.get("question", "Décris précisément et en détail ce que tu vois sur cette image.")
            import base64 as _b64
            from google.genai import types as _gtypes
            _img_part = _gtypes.Part.from_bytes(
                data=_b64.b64decode(_payload["data"]),
                mime_type="image/jpeg",
            )
            _resp = self._get_client().models.generate_content(
                model=TEXT_MODEL,
                contents=[_img_part, _q],
            )
            return _resp.text or "Aucune réponse de vision."

        elif name == "camera_tracking" and self._tuya_camera:
            return await self._tuya_camera.set_tracking(bool(args.get("enabled", True)))

        elif name == "camera_motion_detect" and self._tuya_camera:
            return await self._tuya_camera.set_motion_detect(
                bool(args.get("enabled", True)), args.get("sensitivity", "medium")
            )

        elif name == "camera_watch" and self._tuya_camera:
            _enabled = bool(args.get("enabled", True))
            if not _enabled:
                self._tuya_camera.stop_motion_watch()
                return "Surveillance mouvement arrêtée."
            _with_snap = bool(args.get("with_snapshot", True))
            _tg = self._telegram  # capture pour la closure
            async def _on_motion_bridge(_snap):
                import base64 as _b64b
                await _send_text("telegram", TELEGRAM_CHAT_ID, "⚠️ Mouvement détecté par la caméra !")
                if _snap and _tg:
                    import tempfile as _tf
                    _tmp = _tf.NamedTemporaryFile(suffix=".jpg", delete=False)
                    _tmp.write(_b64b.b64decode(_snap["data"]))
                    _tmp.close()
                    await asyncio.to_thread(_tg.send_photo, f"file://{_tmp.name}", "📸 Mouvement détecté")
            asyncio.create_task(
                self._tuya_camera.start_motion_watch(_on_motion_bridge, with_snapshot=_with_snap)
            )
            return "Surveillance active — alerte Telegram + photo à chaque mouvement détecté."

        # ── RAPPELS ───────────────────────────────────────────────────────────
        elif name == "reminder_set" and self._reminder:
            return self._reminder.set(args["message"], args["datetime_iso"])
        elif name == "reminder_list" and self._reminder:
            return self._reminder.list_reminders()
        elif name == "reminder_delete" and self._reminder:
            return self._reminder.delete(args["reminder_id"])

        # ── CHROMECAST ────────────────────────────────────────────────────────
        elif name == "get_chromecast_status" and self._cast:
            if not self._cast._initialized:
                await self._cast.initialize()
            return await self._cast.get_status()
        elif name == "control_chromecast" and self._cast:
            if not self._cast._initialized:
                await self._cast.initialize()
            action = args.get("action", "").lower()
            volume = args.get("volume")
            if volume is not None:
                return await self._cast.set_volume(float(volume))
            if action == "play":
                return await self._cast.play()
            elif action == "pause":
                return await self._cast.pause()
            elif action == "stop":
                return await self._cast.stop()
            return f"Action Chromecast inconnue: {action}"
        elif name == "play_youtube_on_chromecast" and self._cast:
            if not self._cast._initialized:
                await self._cast.initialize()
            return await self._cast.play_youtube(args.get("video_url", ""))
        elif name == "play_media_on_chromecast" and self._cast:
            if not self._cast._initialized:
                await self._cast.initialize()
            return await self._cast.play_media(
                args.get("url", ""),
                args.get("media_type", "video/mp4")
            )

        # ── DOMOTIQUE (Tuya) ──────────────────────────────────────────────────
        elif name == "refresh_tuya_devices" and self._tuya:
            return await self._tuya.refresh_devices()
        elif name == "list_smart_devices" and self._tuya:
            if not self._tuya.devices:
                await self._tuya.initialize()
            summaries = []
            for ip, d in self._tuya.devices.items():
                dev_type = "ampoule" if d.is_bulb else "prise" if d.is_plug else "inconnu"
                state = "ON" if d.is_on else "OFF"
                summaries.append(f"{d.alias} ({dev_type}) [{state}]")
            return "\n".join(summaries) if summaries else "Aucun appareil trouvé."

        elif name == "control_light" and self._tuya:
            if not self._tuya.devices:
                await self._tuya.initialize()
            target = args.get("target", "")
            action = args.get("action", "")
            brightness = args.get("brightness")
            color = args.get("color")
            if action == "turn_on":
                success = await self._tuya.turn_on(target)
                result = f"'{target}' allumé." if success else f"Échec allumage '{target}'.'"
            elif action == "turn_off":
                success = await self._tuya.turn_off(target)
                result = f"'{target}' éteint." if success else f"Échec extinction '{target}'.'"
            elif action == "set":
                success = True
                result = f"'{target}' mis à jour."
            else:
                return f"Action inconnue: {action}"
            if success:
                if brightness is not None:
                    await self._tuya.set_brightness(target, brightness)
                    result += f" Luminosité: {brightness}%."
                if color is not None:
                    await self._tuya.set_color(target, color)
                    result += f" Couleur: {color}."
            return result

        # ── SUB-AGENTS ────────────────────────────────────────────────────────
        elif name == "run_research" and self._research:
            return await self._research.run(args.get("query", ""))
        elif name == "run_task" and self._task:
            return await self._task.run(args.get("objective", ""))
        elif name == "advanced_web_navigation":
            if not self._advanced_browser:
                return "AdvancedBrowserAgent non disponible (vérifier les dépendances)."
            try:
                return await asyncio.wait_for(
                    self._advanced_browser.run(args.get("mission", "")),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                return "Navigation avancée : timeout dépassé (5 min). Mission trop longue ou bloquée."
            except Exception as e:
                return f"Navigation avancée erreur : {e}"
        elif name == "anticipate" and self._anticipation:
            return await self._anticipation.run(args.get("context", ""))
        elif name == "start_monitoring" and self._monitoring:
            return await self._monitoring.run(args.get("watch_config", ""))
        elif name == "stop_monitoring" and self._monitoring:
            return "Monitoring arrêté."

        # ── RECHERCHE (compléments) ───────────────────────────────────────────
        elif name == "wikipedia_article" and self._wiki:
            return await asyncio.to_thread(self._wiki.get_article, args.get("title", ""), args.get("lang", "fr"))
        elif name == "arxiv_paper" and self._arxiv:
            return await asyncio.to_thread(self._arxiv.get_paper, args.get("arxiv_id", ""))
        elif name == "youtube_video_info" and self._yt:
            return await asyncio.to_thread(self._yt.get_video_info, args.get("video", ""))
        elif name == "youtube_transcript" and self._yt:
            return await asyncio.to_thread(self._yt.get_transcript, args.get("video", ""))

        # ── SPOTIFY (compléments) ─────────────────────────────────────────────
        elif name == "spotify_playlists" and self._spotify:
            return await asyncio.to_thread(self._spotify.get_playlists)

        # ── MAPS (compléments) ────────────────────────────────────────────────
        elif name == "maps_search_places" and self._maps:
            return await asyncio.to_thread(self._maps.search_places, args.get("query", ""), args.get("location", ""), args.get("radius", 5000))
        elif name == "maps_travel_time" and self._maps:
            return await asyncio.to_thread(self._maps.get_travel_time, args.get("origin", ""), args.get("destination", ""), args.get("mode", "driving"))
        elif name == "maps_geocode" and self._maps:
            return await asyncio.to_thread(self._maps.geocode, args.get("address", ""))

        # ── SANTÉ (compléments) ───────────────────────────────────────────────
        elif name == "health_activity" and self._health:
            return await asyncio.to_thread(self._health.get_activity_summary, args.get("days", 7))
        elif name == "health_heart_rate" and self._health:
            return await asyncio.to_thread(self._health.get_heart_rate, args.get("days", 7))

        # ── CRÉATION (compléments) ────────────────────────────────────────────
        elif name == "canva_list_designs" and self._canva:
            return await asyncio.to_thread(self._canva.list_designs, args.get("limit", 20))
        elif name == "canva_get_design" and self._canva:
            return await asyncio.to_thread(self._canva.get_design, args.get("design_id", ""))
        elif name == "canva_export_design" and self._canva:
            return await asyncio.to_thread(self._canva.export_design, args.get("design_id", ""), args.get("format", "png"))
        elif name == "figma_list_files" and self._figma:
            return await asyncio.to_thread(self._figma.list_files, args.get("team_id", ""), args.get("project_id", ""))
        elif name == "figma_get_file" and self._figma:
            return await asyncio.to_thread(self._figma.get_file, args.get("file_key", ""))
        elif name == "figma_export_node" and self._figma:
            return await asyncio.to_thread(self._figma.export_node, args.get("file_key", ""), args.get("node_id", ""), args.get("format", "png"))
        elif name == "replicate_generate_image" and self._replicate:
            return await asyncio.to_thread(self._replicate.generate_image, args.get("prompt", ""), args.get("model", "stability-ai/sdxl"), args.get("width", 1024), args.get("height", 1024))
        elif name == "replicate_run_model" and self._replicate:
            return await asyncio.to_thread(self._replicate.run_model, args.get("model_version", ""), args.get("input_json", ""))

        # ── FICHIERS ──────────────────────────────────────────────────────────
        elif name == "read_file":
            try:
                with open(args.get("path", ""), "r") as f:
                    return f.read()[:5000]
            except Exception as e:
                return f"Erreur lecture: {e}"
        elif name == "read_directory":
            import os as _os
            try:
                return "\n".join(_os.listdir(args.get("path", ".")))
            except Exception as e:
                return f"Erreur listdir: {e}"
        elif name == "write_file":
            try:
                with open(args.get("path", ""), "w") as f:
                    f.write(args.get("content", ""))
                return "Fichier écrit."
            except Exception as e:
                return f"Erreur écriture: {e}"

        # ── USER PROFILE MANAGER ────────────────────────────────────────────
        elif name == "remember_for_user":
            uid = args.get("user_id", "")
            mtype = args.get("memory_type", "preference")
            content = args.get("content", "")
            if mtype == "preference":
                return _upm.save_preference(uid, content)
            elif mtype == "fact":
                return _upm.save_fact(uid, content)
            elif mtype == "habit":
                profile = _upm.get_profile(uid)
                if profile:
                    profile.setdefault("habits", []).append(content)
                    _upm.save_profile(profile)
                    return f"Habitude enregistrée pour {profile['name']}."
                return f"Profil inconnu : {uid}"
            return "Type de mémoire inconnu."
        elif name == "who_is_speaking":
            return "Mode Telegram — identification vocale non disponible. Utilisateur : Bryan."
        elif name == "enroll_voice":
            return "Enrollment vocal non disponible via Telegram. Lance depuis l'interface voix."

        # Outil déclaré mais agent None (variable d'env manquante ou init échouée)
        prefix = name.split("_")[0]
        env_var = _ENV_FOR_TOOL.get(prefix)
        if env_var and not os.getenv(env_var):
            return (f"CONFIGURATION MANQUANTE — '{name}' nécessite la variable {env_var} "
                    f"qui n'est pas définie. Informer Monsieur de la configurer dans .env.")
        return f"Outil '{name}' non disponible (agent non initialisé — vérifier les imports au démarrage)."

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

        bryan_ctx = _upm.get_active_context([{"user": "bryan", "source": "telegram"}])
        user_block = f"\n\n{bryan_ctx}" if bryan_ctx else ""
        system = ADA_SYSTEM_PROMPT + memory_block + user_block
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
                try:
                    result = await self._execute_tool(fc.function_call.name, dict(fc.function_call.args))
                except Exception as _e:
                    result = _format_tool_error(fc.function_call.name, _e)
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
