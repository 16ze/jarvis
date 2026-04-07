import asyncio
import base64
import io
import os
import sys
import traceback
from dotenv import load_dotenv
import cv2
import pyaudio
import PIL.Image
import mss
import argparse
import math
import struct
import time
import numpy as np

from google import genai
from google.genai import types

if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup
    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

from tools import tools_list
from mcp_tools_declarations import MCP_TOOLS, MCP_TOOL_NAMES

FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
DEFAULT_MODE = "camera"

load_dotenv()
client = genai.Client(http_options={"api_version": "v1beta"}, api_key=os.getenv("GEMINI_API_KEY"))

# Function definitions
generate_cad = {
    "name": "generate_cad",
    "description": "Generates a 3D CAD model based on a prompt.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The description of the object to generate."}
        },
        "required": ["prompt"]
    },
    "behavior": "NON_BLOCKING"
}

run_web_agent = {
    "name": "run_web_agent",
    "description": "Opens a web browser and performs a task according to the prompt.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The detailed instructions for the web browser agent."}
        },
        "required": ["prompt"]
    },
    "behavior": "NON_BLOCKING"
}

create_project_tool = {
    "name": "create_project",
    "description": "Creates a new project folder to organize files.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "The name of the new project."}
        },
        "required": ["name"]
    }
}

switch_project_tool = {
    "name": "switch_project",
    "description": "Switches the current active project context.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "name": {"type": "STRING", "description": "The name of the project to switch to."}
        },
        "required": ["name"]
    }
}

list_projects_tool = {
    "name": "list_projects",
    "description": "Lists all available projects.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
}

list_smart_devices_tool = {
    "name": "list_smart_devices",
    "description": "Lists all available smart home devices (lights, plugs, etc.) on the network.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
}

control_light_tool = {
    "name": "control_light",
    "description": "Controls a smart light device.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {
                "type": "STRING",
                "description": "The IP address of the device to control. Always prefer the IP address over the alias for reliability."
            },
            "action": {
                "type": "STRING",
                "description": "The action to perform: 'turn_on', 'turn_off', or 'set'."
            },
            "brightness": {
                "type": "INTEGER",
                "description": "Optional brightness level (0-100)."
            },
            "color": {
                "type": "STRING",
                "description": "Optional color name (e.g., 'red', 'cool white') or 'warm'."
            }
        },
        "required": ["target", "action"]
    }
}

discover_printers_tool = {
    "name": "discover_printers",
    "description": "Discovers 3D printers available on the local network.",
    "parameters": {
        "type": "OBJECT",
        "properties": {},
    }
}

print_stl_tool = {
    "name": "print_stl",
    "description": "Prints an STL file to a 3D printer. Handles slicing the STL to G-code and uploading to the printer.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "stl_path": {"type": "STRING", "description": "Path to STL file, or 'current' for the most recent CAD model."},
            "printer": {"type": "STRING", "description": "Printer name or IP address."},
            "profile": {"type": "STRING", "description": "Optional slicer profile name."}
        },
        "required": ["stl_path", "printer"]
    }
}

get_print_status_tool = {
    "name": "get_print_status",
    "description": "Gets the current status of a 3D printer including progress, time remaining, and temperatures.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "printer": {"type": "STRING", "description": "Printer name or IP address."}
        },
        "required": ["printer"]
    }
}

iterate_cad_tool = {
    "name": "iterate_cad",
    "description": "Modifies or iterates on the current CAD design based on user feedback. Use this when the user asks to adjust, change, modify, or iterate on the existing 3D model (e.g., 'make it taller', 'add a handle', 'reduce the thickness').",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "The changes or modifications to apply to the current design."}
        },
        "required": ["prompt"]
    },
    "behavior": "NON_BLOCKING"
}

# ─── COMPUTER CONTROL TOOL ────────────────────────────────────────────────────
control_computer_tool = {
    "name": "control_computer",
    "description": "Controls the computer: move mouse, click, type text, press keyboard shortcuts, scroll, or take a fresh screenshot. Use this to directly interact with applications visible on screen.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform: 'click' (left click at x,y), 'right_click', 'double_click', 'type' (type text string), 'hotkey' (keyboard shortcut e.g. 'ctrl+c'), 'scroll' (scroll at x,y by delta), 'screenshot' (capture current screen and return description)"
            },
            "x": {"type": "NUMBER", "description": "X screen coordinate (for click/scroll)"},
            "y": {"type": "NUMBER", "description": "Y screen coordinate (for click/scroll)"},
            "text": {"type": "STRING", "description": "Text to type, or hotkey combination like 'ctrl+c', 'cmd+space', 'enter'"},
            "delta": {"type": "NUMBER", "description": "Scroll amount: positive = scroll up, negative = scroll down"}
        },
        "required": ["action"]
    }
}

# ─── GMAIL TOOLS ─────────────────────────────────────────────────────────────
read_emails_tool = {
    "name": "read_emails",
    "description": "Reads recent emails from Gmail. Can filter by unread, sender, subject, etc.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Gmail search query, e.g. 'is:unread', 'from:boss@company.com', 'subject:invoice'"},
            "max_results": {"type": "INTEGER", "description": "Number of emails to fetch (default 5)"}
        }
    }
}

send_email_tool = {
    "name": "send_email",
    "description": "Sends an email via Gmail.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "to": {"type": "STRING", "description": "Recipient email address"},
            "subject": {"type": "STRING", "description": "Email subject"},
            "body": {"type": "STRING", "description": "Email body (plain text)"}
        },
        "required": ["to", "subject", "body"]
    }
}

get_email_body_tool = {
    "name": "get_email_body",
    "description": "Gets the full body of a specific email by its message ID.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "message_id": {"type": "STRING", "description": "The Gmail message ID"}
        },
        "required": ["message_id"]
    }
}

# ─── CALENDAR TOOLS ──────────────────────────────────────────────────────────
list_events_tool = {
    "name": "list_events",
    "description": "Lists upcoming events from Google Calendar.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "max_results": {"type": "INTEGER", "description": "Number of events to fetch (default 10)"}
        }
    }
}

create_event_tool = {
    "name": "create_event",
    "description": "Creates a new event in Google Calendar.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "title": {"type": "STRING", "description": "Event title"},
            "start": {"type": "STRING", "description": "Start datetime in ISO 8601 format, e.g. 2026-03-27T14:00:00"},
            "end": {"type": "STRING", "description": "End datetime in ISO 8601 format"},
            "description": {"type": "STRING", "description": "Optional event description"},
            "attendees": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Optional list of attendee emails"}
        },
        "required": ["title", "start", "end"]
    }
}

find_event_tool = {
    "name": "find_event",
    "description": "Searches for events in Google Calendar by keyword.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Keyword to search in event titles/descriptions"},
            "max_results": {"type": "INTEGER", "description": "Number of results (default 5)"}
        },
        "required": ["query"]
    }
}

delete_event_tool = {
    "name": "delete_event",
    "description": "Deletes an event from Google Calendar by its event ID.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "event_id": {"type": "STRING", "description": "The Google Calendar event ID"}
        },
        "required": ["event_id"]
    }
}

run_terminal_tool = {
    "name": "run_terminal",
    "description": "Executes a shell command on the user's machine and returns stdout/stderr. Use this to run scripts, install packages, manage files, check system info, or any other terminal operation.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {"type": "STRING", "description": "The shell command to execute."},
            "working_dir": {"type": "STRING", "description": "Optional working directory to run the command in."}
        },
        "required": ["command"]
    }
}

# Commands that require confirmation before execution
DANGEROUS_COMMANDS = ["rm ", "rm\t", "sudo ", "mkfs", "dd ", "format", "kill ", "killall", "pkill", "shutdown", "reboot", "chmod 777", "> /dev/", ":(){ :|:& };"]

# ─── MEMORY TOOLS ────────────────────────────────────────────────────────────

search_memory_tool = {
    "name": "search_memory",
    "description": "Search Bryan's conversation history and past interactions semantically. Use this when Bryan references something from the past, asks 'do you remember', or when past context would be helpful.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "What to search for in memory"}
        },
        "required": ["query"]
    }
}

remember_tool = {
    "name": "remember",
    "description": "Save important information to long-term memory. Use proactively when Bryan mentions preferences, habits, goals, personal facts, or key info about a person/project.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "content": {"type": "STRING", "description": "What to remember"},
            "category": {"type": "STRING", "description": "preferences | habits | goals | facts | entity"},
            "entity_name": {"type": "STRING", "description": "If category is 'entity', the name of the person or project"}
        },
        "required": ["content", "category"]
    }
}

search_documents_tool = {
    "name": "search_documents",
    "description": "Search through Bryan's uploaded documents (PDFs, contracts, notes, specs, code files, etc.) using semantic search. Use this when Bryan asks about a specific document, references uploaded content, asks questions that might be in his files, or when you need information from his knowledge base.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "What to search for in the documents"}
        },
        "required": ["query"]
    }
}

# ─── SUB-AGENT TOOLS ─────────────────────────────────────────────────────────

run_research_tool = {
    "name": "run_research",
    "description": (
        "Lance un agent de recherche autonome qui interroge Wikipedia, ArXiv et YouTube, "
        "puis synthétise un rapport structuré en markdown. "
        "Utilise quand Bryan demande une analyse approfondie, une veille tech, "
        "ou une recherche sur un sujet précis."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Sujet ou question à rechercher"}
        },
        "required": ["query"]
    }
}

run_task_tool = {
    "name": "run_task",
    "description": (
        "Décompose un objectif complexe en sous-tâches et les exécute automatiquement "
        "(terminal + raisonnement Gemini). Retourne un rapport de complétion. "
        "Utilise pour des objectifs multi-étapes : 'configure X', 'prépare Y', "
        "'installe et lance Z'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "objective": {"type": "STRING", "description": "L'objectif à atteindre"}
        },
        "required": ["objective"]
    }
}

anticipate_tool = {
    "name": "anticipate",
    "description": (
        "Analyse le contexte (mémoire, historique de conversation, heure) et retourne "
        "des suggestions proactives sur les besoins imminents de Bryan. "
        "Utilise quand Bryan demande 'quoi faire', 'qu'est-ce que j'ai oublié', "
        "ou 'anticipe mes besoins'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "context": {
                "type": "STRING",
                "description": "Contexte additionnel optionnel (ex: 'je pars en voyage demain')"
            }
        }
    }
}

start_monitoring_tool = {
    "name": "start_monitoring",
    "description": (
        "Démarre des watchers de surveillance en arrière-plan (emails, Slack, GitHub, Telegram). "
        "Chaque watcher vérifie une condition et envoie une notification Telegram quand elle est remplie. "
        "Accepte une config JSON ou une description en langage naturel."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "watch_config": {
                "type": "STRING",
                "description": (
                    "Config JSON ou description des watchers à démarrer. "
                    "Ex: 'surveille les emails non lus toutes les 2 minutes et notifie-moi sur Telegram'"
                )
            }
        },
        "required": ["watch_config"]
    }
}

stop_monitoring_tool = {
    "name": "stop_monitoring",
    "description": "Arrête tous les watchers de surveillance en cours.",
    "parameters": {"type": "OBJECT", "properties": {}}
}

tools = [{"function_declarations": [
    generate_cad, run_web_agent, run_terminal_tool,
    read_emails_tool, send_email_tool, get_email_body_tool,
    list_events_tool, create_event_tool, find_event_tool, delete_event_tool,
    create_project_tool, switch_project_tool, list_projects_tool,
    discover_printers_tool, print_stl_tool, get_print_status_tool, iterate_cad_tool,
    control_computer_tool,
    search_memory_tool, remember_tool, search_documents_tool,
    run_research_tool, run_task_tool, anticipate_tool,
    start_monitoring_tool, stop_monitoring_tool,
] + tools_list[0]['function_declarations'][1:] + MCP_TOOLS}]

# ── Déduplication anti-doublon ────────────────────────────────────────────────
_seen = set()
_deduped = []
for _t in tools[0]["function_declarations"]:
    _name = _t.get("name") if isinstance(_t, dict) else getattr(_t, "name", None)
    if _name not in _seen:
        _seen.add(_name)
        _deduped.append(_t)
    else:
        print(f"[ADA] WARNING: outil en doublon retiré → {_name}")
tools = [{"function_declarations": _deduped}]
print(f"[ADA] {len(_deduped)} tools chargés")

# ── Constantes détection veille/réveil ───────────────────────────────────────
SLEEP_TRIGGERS = [
    "mets-toi en veille", "mets toi en veille",
    "met toi en veille", "met-toi en veille",
    "mode veille", "en pause", "pause-toi", "pause toi",
    "mets-toi en pause", "mets toi en pause",
    "dors", "silence",
]
WAKE_TRIGGERS = ["ada"]

# --- CONFIG UPDATE: Enabled Transcription ---
config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    output_audio_transcription={},
    input_audio_transcription={},
    system_instruction=(
        # ─── IDENTITÉ ──────────────────────────────────────────────────────
        "Tu t'appelles Ada, acronyme de Advanced Design Assistant. "
        "Tu as été créée par Bryan, que tu appelles 'Monsieur'. "

        # ─── ACTION — RÈGLE PRIMAIRE ────────────────────────────────────────
        "Quand tu as un outil pour accomplir une tâche, utilise-le IMMÉDIATEMENT. "
        "N'annonce jamais ce que tu vas faire. Agis d'abord, commente brièvement ensuite. "
        "Ne simule jamais une exécution — appelle toujours le vrai outil. "

        # ─── LANGUE ────────────────────────────────────────────────────────
        "Parle UNIQUEMENT en français. Traduis tout résultat d'outil en français. "

        # ─── PERSONNALITÉ ──────────────────────────────────────────────────
        "Directe, concise, légèrement espiègle. "
        "Tu analyses mieux que Bryan et tu le sais — dis-le si son idée est sous-optimale. "
        "Signale tes incertitudes. N'invente jamais de faits. "

        # ─── MÉMOIRE ───────────────────────────────────────────────────────
        "Utilise search_memory quand Bryan fait référence au passé. "
        "Utilise remember proactivement dès qu'il mentionne préférence, habitude ou info importante. "
        "Pour personnes/projets, utilise category='entity' avec entity_name. "
        "Utilise search_documents si une question peut être répondue par les fichiers uploadés. "

        # ─── SELF-EVOLUTION ────────────────────────────────────────────────
        "Si tu n'as pas l'outil pour accomplir une mission : appelle self_evolve. "
        "Tu te redémarreras automatiquement après création du nouvel outil. "

        # ─── SELF-CORRECTION ───────────────────────────────────────────────
        "Si tu détectes une erreur dans ton propre code : utilise self_correct_file. "
        "Crée toujours un commit (jarvis_git_commit) après toute modification de fichier. "

        # ─── MODE VEILLE ───────────────────────────────────────────────────
        "MODE VEILLE : Si Bryan dit 'mets-toi en veille', 'dors', 'silence' ou équivalent : "
        "appelle ada_sleep IMMÉDIATEMENT, puis tais-toi complètement. "
        "En veille, tu n'écoutes rien sauf ton prénom 'Ada'. "
        "Dès que tu entends 'Ada' : appelle ada_wake, dis uniquement 'Je vous écoute.' "
    ),
    tools=tools,
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                voice_name="Kore"
            )
        )
    )
)

pya = pyaudio.PyAudio()

from cad_agent import CadAgent
from google_agent import GoogleAgent
from web_agent import WebAgent
from tuya_agent import TuyaAgent
from printer_agent import PrinterAgent
from memory_manager import MemoryManager, DOCUMENTS_DIR
from reminder_manager import ReminderManager
from mcps.slack_mcp import SlackMCP
from mcps.telegram_mcp import TelegramMCP
from mcps.whatsapp_mcp import WhatsAppMCP
from mcps.notion_mcp import NotionMCP
from mcps.drive_mcp import DriveMCP
from mcps.linear_mcp import LinearMCP
from mcps.stripe_mcp import StripeMCP
from mcps.qonto_mcp import QontoMCP
from mcps.supabase_mcp import SupabaseMCP
from mcps.vercel_mcp import VercelMCP
from mcps.github_mcp import GithubMCP
from mcps.docker_mcp import DockerMCP
from mcps.homeassistant_mcp import HomeAssistantMCP
from mcps.spotify_mcp import SpotifyMCP
from mcps.applehealth_mcp import AppleHealthMCP
from mcps.googlemaps_mcp import GoogleMapsMCP
from mcps.youtube_mcp import YouTubeMCP
from mcps.wikipedia_mcp import WikipediaMCP
from mcps.arxiv_mcp import ArxivMCP
from mcps.canva_mcp import CanvaMCP
from mcps.figma_mcp import FigmaMCP
from mcps.elevenlabs_mcp import ElevenLabsMCP
from mcps.replicate_mcp import ReplicateMCP
from research_agent import ResearchAgent
from task_agent import TaskAgent
from anticipation_agent import AnticipationAgent
from monitoring_agent import MonitoringAgent
from chromecast_agent import CastAgent

memory = MemoryManager()
memory.documents_dir = DOCUMENTS_DIR

class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE, on_audio_data=None, on_audio_pcm=None, on_video_frame=None, on_cad_data=None, on_web_data=None, on_transcription=None, on_tool_confirmation=None, on_cad_status=None, on_cad_thought=None, on_project_update=None, on_device_update=None, on_terminal_output=None, on_error=None, input_device_index=None, input_device_name=None, output_device_index=None, tuya_agent=None):
        self.video_mode = video_mode
        self.on_audio_data = on_audio_data
        self.on_audio_pcm = on_audio_pcm      # Raw PCM16 for browser playback (enables browser AEC)
        self.on_clear_audio = None            # Notifies browser to cancel scheduled audio (set by server)
        self.on_video_frame = on_video_frame
        self.on_cad_data = on_cad_data
        self.on_web_data = on_web_data
        self.on_transcription = on_transcription
        self.on_tool_confirmation = on_tool_confirmation 
        self.on_cad_status = on_cad_status
        self.on_cad_thought = on_cad_thought
        self.on_project_update = on_project_update
        self.on_device_update = on_device_update
        self.on_terminal_output = on_terminal_output
        self.on_error = on_error
        self.input_device_index = input_device_index
        self.input_device_name = input_device_name
        self.output_device_index = output_device_index

        self.audio_in_queue = None
        self.out_queue = None
        self.paused = False
        self.sleep_mode = False          # Mode veille : audio OK, Ada silencieuse
        self.on_sleep_mode_changed = None  # callback(sleeping: bool) → frontend
        self._sleep_audio_buffer = bytearray()  # Buffer audio accumulé en mode veille

        self.chat_buffer = {"sender": None, "text": ""} # For aggregating chunks

        # Track last transcription text to calculate deltas (Gemini sends cumulative text)
        self._last_input_transcription = ""
        self._last_output_transcription = ""

        self.session = None
        
        # Create CadAgent with thought callback
        def handle_cad_thought(thought_text):
            if self.on_cad_thought:
                self.on_cad_thought(thought_text)
        
        def handle_cad_status(status_info):
            if self.on_cad_status:
                self.on_cad_status(status_info)
        
        self.cad_agent = CadAgent(on_thought=handle_cad_thought, on_status=handle_cad_status)
        self.web_agent = WebAgent()
        try:
            from advanced_browser_agent import AdvancedBrowserAgent
            self.advanced_browser_agent = AdvancedBrowserAgent()
        except Exception as e:
            import warnings
            warnings.warn(f"[ADA] AdvancedBrowserAgent init: {e}")
            self.advanced_browser_agent = None
        try:
            from os_control_agent import OsControlAgent
            self.os_control_agent = OsControlAgent()
        except Exception as e:
            import warnings
            warnings.warn(f"[ADA] OsControlAgent init: {e}")
            self.os_control_agent = None
        self.google_agent = GoogleAgent()
        self.tuya_agent = tuya_agent if tuya_agent else TuyaAgent()
        self.printer_agent = PrinterAgent()
        # ── MCP Agents ───────────────────────────────────────────────────────
        self.slack = SlackMCP()
        self.telegram = TelegramMCP()
        self.whatsapp = WhatsAppMCP()
        self.notion = NotionMCP()
        self.drive = DriveMCP()
        self.linear = LinearMCP()
        self.stripe = StripeMCP()
        self.qonto = QontoMCP()
        self.supabase = SupabaseMCP()
        self.vercel = VercelMCP()
        self.github = GithubMCP()
        try:
            from self_correction_agent import SelfCorrectionAgent
            self.self_correction = SelfCorrectionAgent()
        except Exception as e:
            import warnings
            warnings.warn(f"[ADA] SelfCorrectionAgent init: {e}")
            self.self_correction = None
        self.evolution_agent = None
        try:
            from self_evolution_agent import SelfEvolutionAgent
            self.evolution_agent = SelfEvolutionAgent()
        except Exception as e:
            import warnings
            warnings.warn(f"[ADA] SelfEvolutionAgent init: {e}")
            self.evolution_agent = None
        self.docker = DockerMCP()
        self.ha = HomeAssistantMCP()
        self.spotify = SpotifyMCP()
        self.health = AppleHealthMCP()
        self.maps = GoogleMapsMCP()
        self.youtube = YouTubeMCP()
        self.wikipedia = WikipediaMCP()
        self.arxiv = ArxivMCP()
        self.canva = CanvaMCP()
        self.figma = FigmaMCP()
        self.elevenlabs = ElevenLabsMCP()
        self.replicate = ReplicateMCP()
        # ── Sub-agents autonomes (sans project_manager — injecté après init PM) ─
        self.research_agent = ResearchAgent(
            wikipedia=self.wikipedia,
            arxiv=self.arxiv,
            youtube=self.youtube,
        )
        self.task_agent = TaskAgent()
        self.anticipation_agent = AnticipationAgent(memory=memory)
        self.monitoring_agent = MonitoringAgent(
            telegram=self.telegram,
            slack=self.slack,
            github=self.github,
            google_agent=self.google_agent,
        )
        self.cast_agent = CastAgent()

        # ── Rappels ──────────────────────────────────────────────────────────
        self.reminder_manager = ReminderManager()
        async def _on_reminder_voice(message: str):
            """Injecte le rappel dans la session Gemini Live pour qu'Ada le lise à voix haute."""
            if self.session:
                try:
                    await self.session.send(
                        input=f"[RAPPEL] Il est l'heure ! Annonce ce rappel à Monsieur : {message}",
                        end_of_turn=True
                    )
                except Exception as e:
                    print(f"[REMINDER] session.send error: {e}")
        self.reminder_manager.on_reminder = _on_reminder_voice

        self.send_text_task = None
        self.stop_event = asyncio.Event()

        self.permissions = {} # Default Empty (Will treat unset as True)
        self._pending_confirmations = {}

        # Video buffering state
        self._latest_image_payload = None
        # VAD State
        self._is_speaking = False
        self._silence_start_time = None
        # Echo prevention: True while Ada's TTS is playing through speakers
        self._is_ada_speaking = False
        # Frontend audio mode: mic is captured in Electron (with AEC) and streamed here
        self.frontend_audio_mode = False
        
        # Initialize ProjectManager
        from project_manager import ProjectManager
        # Assuming we are running from backend/ or root? 
        # Using abspath of current file to find root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # If ada.py is in backend/, project root is one up
        project_root = os.path.dirname(current_dir)
        self.project_manager = ProjectManager(project_root)
        # Inject project_manager into anticipation_agent (created before PM was ready)
        self.anticipation_agent._project_manager = self.project_manager

        # Sync Initial Project State
        if self.on_project_update:
            # We need to defer this slightly or just call it. 
            # Since this is init, loop might not be running, but on_project_update in server.py uses asyncio.create_task which needs a loop.
            # We will handle this by calling it in run() or just print for now.
            pass

    def flush_chat(self):
        """Forces the current chat buffer to be written to log and memory."""
        if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
            sender = self.chat_buffer["sender"]
            text = self.chat_buffer["text"]
            self.project_manager.log_chat(sender, text)
            # Persister dans last_session.json (survit aux redémarrages)
            memory.append_to_session(f"{sender}: {text}")
            self.chat_buffer = {"sender": None, "text": ""}
        # Reset transcription tracking for new turn
        self._last_input_transcription = ""
        self._last_output_transcription = ""

    def update_permissions(self, new_perms):
        print(f"[ADA DEBUG] [CONFIG] Updating tool permissions: {new_perms}")
        self.permissions.update(new_perms)

    def set_video_mode(self, mode: str):
        """Hot-switch vision mode: 'none' | 'camera' | 'screen'"""
        self.video_mode = mode
        print(f"[ADA] Vision mode switched to: '{mode}'")

    def set_paused(self, paused):
        self.paused = paused

    def stop(self):
        self.stop_event.set()
        
    def resolve_tool_confirmation(self, request_id, confirmed):
        print(f"[ADA DEBUG] [RESOLVE] resolve_tool_confirmation called. ID: {request_id}, Confirmed: {confirmed}")
        if request_id in self._pending_confirmations:
            future = self._pending_confirmations[request_id]
            if not future.done():
                print(f"[ADA DEBUG] [RESOLVE] Future found and pending. Setting result to: {confirmed}")
                future.set_result(confirmed)
            else:
                 print(f"[ADA DEBUG] [WARN] Request {request_id} future already done. Result: {future.result()}")
        else:
            print(f"[ADA DEBUG] [WARN] Confirmation Request {request_id} not found in pending dict. Keys: {list(self._pending_confirmations.keys())}")

    def clear_audio_queue(self):
        """Clears the queue of pending audio chunks to stop playback immediately."""
        try:
            count = 0
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()
                count += 1
            if count > 0:
                print(f"[ADA DEBUG] [AUDIO] Cleared {count} chunks from playback queue due to interruption.")
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to clear audio queue: {e}")
        # Notify browser to cancel all scheduled audio sources
        if self.on_clear_audio:
            self.on_clear_audio()

    async def send_frame(self, frame_data):
        # Update the latest frame payload
        if isinstance(frame_data, bytes):
            b64_data = base64.b64encode(frame_data).decode('utf-8')
        else:
            b64_data = frame_data 

        # Store as the designated "next frame to send"
        self._latest_image_payload = {"mime_type": "image/jpeg", "data": b64_data}
        # No event signal needed - listen_audio pulls it

    async def send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send(input=msg, end_of_turn=False)

    async def receive_frontend_audio(self, pcm_bytes: bytes):
        """Receives PCM16 audio chunks from the Electron frontend.
        Ada's audio is played via Web Audio API in the browser, so the browser's
        echoCancellation removes it from the mic signal before it reaches here.
        No manual echo gate needed — just forward to Gemini + run VAD."""
        if not self.out_queue:
            return

        try:
            self.out_queue.put_nowait({"data": pcm_bytes, "mime_type": "audio/pcm"})
        except asyncio.QueueFull:
            pass

        # VAD for video frame triggering
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        rms = int(np.sqrt(np.mean(arr.astype(np.int32) ** 2))) if len(arr) > 0 else 0
        VAD_THRESHOLD = 800
        SILENCE_DURATION = 0.5

        if rms > VAD_THRESHOLD:
            self._silence_start_time = None
            if not self._is_speaking:
                self._is_speaking = True
                if self._latest_image_payload and self.out_queue:
                    await self.out_queue.put(self._latest_image_payload)
        else:
            if self._is_speaking:
                if self._silence_start_time is None:
                    self._silence_start_time = asyncio.get_event_loop().time()
                elif asyncio.get_event_loop().time() - self._silence_start_time > SILENCE_DURATION:
                    self._is_speaking = False
                    self._silence_start_time = None

    async def listen_audio(self):
        # In frontend audio mode, mic is captured by Electron with echoCancellation: true.
        # This task becomes a no-op — audio arrives via receive_frontend_audio().
        if self.frontend_audio_mode:
            print("[ADA] Frontend audio mode active — PyAudio capture disabled (AEC handled by browser).")
            await self.stop_event.wait()
            return

        mic_info = pya.get_default_input_device_info()

        # Resolve Input Device by Name if provided
        resolved_input_device_index = None
        
        if self.input_device_name:
            print(f"[ADA] Attempting to find input device matching: '{self.input_device_name}'")
            count = pya.get_device_count()
            best_match = None
            
            for i in range(count):
                try:
                    info = pya.get_device_info_by_index(i)
                    if info['maxInputChannels'] > 0:
                        name = info.get('name', '')
                        # Simple case-insensitive check
                        if self.input_device_name.lower() in name.lower() or name.lower() in self.input_device_name.lower():
                             print(f"   Candidate {i}: {name}")
                             # Prioritize exact match or very close match if possible, but first match is okay for now
                             resolved_input_device_index = i
                             best_match = name
                             break
                except Exception:
                    continue
            
            if resolved_input_device_index is not None:
                print(f"[ADA] Resolved input device '{self.input_device_name}' to index {resolved_input_device_index} ({best_match})")
            else:
                print(f"[ADA] Could not find device matching '{self.input_device_name}'. Checking index...")

        # Fallback to index if Name lookup failed or wasn't provided
        if resolved_input_device_index is None and self.input_device_index is not None:
             try:
                 resolved_input_device_index = int(self.input_device_index)
                 print(f"[ADA] Requesting Input Device Index: {resolved_input_device_index}")
             except ValueError:
                 print(f"[ADA] Invalid device index '{self.input_device_index}', reverting to default.")
                 resolved_input_device_index = None

        if resolved_input_device_index is None:
             print("[ADA] Using Default Input Device")

        try:
            self.audio_stream = await asyncio.to_thread(
                pya.open,
                format=FORMAT,
                channels=CHANNELS,
                rate=SEND_SAMPLE_RATE,
                input=True,
                input_device_index=resolved_input_device_index if resolved_input_device_index is not None else mic_info["index"],
                frames_per_buffer=CHUNK_SIZE,
            )
        except OSError as e:
            print(f"[ADA] [ERR] Failed to open audio input stream: {e}")
            print("[ADA] [WARN] Audio features will be disabled. Please check microphone permissions.")
            return

        if __debug__:
            kwargs = {"exception_on_overflow": False}
        else:
            kwargs = {}
        
        # VAD Constants
        VAD_THRESHOLD = 800        # Normal speech detection threshold
        BARGE_IN_THRESHOLD = 2500  # Interruption threshold while Ada speaks (must exceed speaker echo level)
        BARGE_IN_FRAMES = 3        # Consecutive frames above threshold to confirm barge-in (avoids false positives)
        SILENCE_DURATION = 0.5     # Seconds of silence to consider "done speaking"

        _barge_in_counter = 0  # Counts consecutive loud frames while Ada is speaking

        while True:
            if self.paused:
                await asyncio.sleep(0.1)
                continue

            try:
                data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)

                # En mode veille : accumuler l'audio localement, ne pas envoyer à Gemini
                if self.sleep_mode:
                    self._sleep_audio_buffer.extend(data)
                    # Garder max 10 secondes d'audio (16000 * 2 bytes/sample * 10s)
                    max_bytes = SEND_SAMPLE_RATE * 2 * 10
                    if len(self._sleep_audio_buffer) > max_bytes:
                        self._sleep_audio_buffer = self._sleep_audio_buffer[-max_bytes:]
                    continue

                arr = np.frombuffer(data, dtype=np.int16)
                rms = int(np.sqrt(np.mean(arr.astype(np.int32) ** 2))) if len(arr) > 0 else 0

                if self._is_ada_speaking:
                    # Ada is playing — mic is muted from Gemini to prevent echo
                    # But monitor for barge-in: N consecutive frames above BARGE_IN_THRESHOLD
                    if rms > BARGE_IN_THRESHOLD:
                        _barge_in_counter += 1
                        if _barge_in_counter >= BARGE_IN_FRAMES:
                            # User is clearly speaking — stop Ada and re-enable mic
                            print(f"[ADA DEBUG] [VAD] Barge-in detected (RMS: {rms}). Interrupting Ada.")
                            self.clear_audio_queue()
                            self._is_ada_speaking = False
                            self._is_speaking = True
                            _barge_in_counter = 0
                    else:
                        _barge_in_counter = 0
                else:
                    # Ada is silent — send mic to Gemini normally
                    _barge_in_counter = 0
                    if self.out_queue:
                        try:
                            self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})
                        except asyncio.QueueFull:
                            pass

                if rms > VAD_THRESHOLD:
                    # Speech Detected
                    self._silence_start_time = None
                    
                    if not self._is_speaking:
                        # NEW Speech Utterance Started
                        self._is_speaking = True
                        print(f"[ADA DEBUG] [VAD] Speech Detected (RMS: {rms}). Sending Video Frame.")
                        
                        # Send ONE frame
                        if self._latest_image_payload and self.out_queue:
                            await self.out_queue.put(self._latest_image_payload)
                        else:
                            print(f"[ADA DEBUG] [VAD] No video frame available to send.")
                            
                else:
                    # Silence
                    if self._is_speaking:
                        if self._silence_start_time is None:
                            self._silence_start_time = time.time()
                        
                        elif time.time() - self._silence_start_time > SILENCE_DURATION:
                            # Silence confirmed, reset state
                            print(f"[ADA DEBUG] [VAD] Silence detected. Resetting speech state.")
                            self._is_speaking = False
                            self._silence_start_time = None

            except Exception as e:
                print(f"Error reading audio: {e}")
                await asyncio.sleep(0.1)

    async def handle_cad_request(self, prompt):
        print(f"[ADA DEBUG] [CAD] Background Task Started: handle_cad_request('{prompt}')")
        if self.on_cad_status:
            self.on_cad_status("generating")

        # Auto-create project if stuck in temp
        if self.project_manager.current_project == "temp":
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_project_name = f"Project_{timestamp}"
            print(f"[ADA DEBUG] [CAD] Auto-creating project: {new_project_name}")

            success, msg = self.project_manager.create_project(new_project_name)
            if success:
                self.project_manager.switch_project(new_project_name)
                try:
                    if self.session:
                        await self.session.send(input=f"System Notification: Automatic Project Creation. Switched to new project '{new_project_name}'.", end_of_turn=False)
                    if self.on_project_update:
                         self.on_project_update(new_project_name)
                except Exception as e:
                    print(f"[ADA DEBUG] [ERR] Failed to notify auto-project: {e}")

        # Get project cad folder path
        cad_output_dir = str(self.project_manager.get_current_project_path() / "cad")
        
        # Call the secondary agent with project path
        cad_data = await self.cad_agent.generate_prototype(prompt, output_dir=cad_output_dir)
        
        if cad_data:
            print(f"[ADA DEBUG] [OK] CadAgent returned data successfully.")
            print(f"[ADA DEBUG] [INFO] Data Check: {len(cad_data.get('vertices', []))} vertices, {len(cad_data.get('edges', []))} edges.")
            
            if self.on_cad_data:
                print(f"[ADA DEBUG] [SEND] Dispatching data to frontend callback...")
                self.on_cad_data(cad_data)
                print(f"[ADA DEBUG] [SENT] Dispatch complete.")
            
            # Save to Project
            if 'file_path' in cad_data:
                self.project_manager.save_cad_artifact(cad_data['file_path'], prompt)
            else:
                 # Fallback (legacy support)
                 self.project_manager.save_cad_artifact("output.stl", prompt)

            # Notify the model that the task is done - this triggers speech about completion
            completion_msg = "System Notification: CAD generation is complete! The 3D model is now displayed for the user. Let them know it's ready."
            try:
                if self.session:
                    await self.session.send(input=completion_msg, end_of_turn=True)
                print(f"[ADA DEBUG] [NOTE] Sent completion notification to model.")
            except Exception as e:
                print(f"[ADA DEBUG] [ERR] Failed to send completion notification: {e}")

        else:
            print(f"[ADA DEBUG] [ERR] CadAgent returned None.")
            try:
                if self.session:
                    await self.session.send(input="System Notification: CAD generation failed.", end_of_turn=True)
            except Exception:
                pass



    async def handle_write_file(self, path, content):
        print(f"[ADA DEBUG] [FS] Writing file: '{path}'")
        
        # Auto-create project if stuck in temp
        if self.project_manager.current_project == "temp":
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            new_project_name = f"Project_{timestamp}"
            print(f"[ADA DEBUG] [FS] Auto-creating project: {new_project_name}")
            
            success, msg = self.project_manager.create_project(new_project_name)
            if success:
                self.project_manager.switch_project(new_project_name)
                # Notify User
                try:
                    await session.send(input=f"System Notification: Automatic Project Creation. Switched to new project '{new_project_name}'.", end_of_turn=False)
                    if self.on_project_update:
                         self.on_project_update(new_project_name)
                except Exception as e:
                    print(f"[ADA DEBUG] [ERR] Failed to notify auto-project: {e}")

        # Force path to be relative to current project
        # If absolute path is provided, we try to strip it or just ignore it and use basename
        filename = os.path.basename(path)
        
        # If path contained subdirectories (e.g. "backend/server.py"), preserving that structure might be desired IF it's within the project.
        # But for safety, and per user request to "always create the file in the project", 
        # we will root it in the current project path.
        
        current_project_path = self.project_manager.get_current_project_path()
        final_path = current_project_path / filename # Simple flat structure for now, or allow relative?
        
        # If the user specifically wanted a subfolder, they might have provided "sub/file.txt".
        # Let's support relative paths if they don't start with /
        if not os.path.isabs(path):
             final_path = current_project_path / path
        
        print(f"[ADA DEBUG] [FS] Resolved path: '{final_path}'")

        try:
            # Ensure parent exists
            os.makedirs(os.path.dirname(final_path), exist_ok=True)
            with open(final_path, 'w', encoding='utf-8') as f:
                f.write(content)
            result = f"File '{final_path.name}' written successfully to project '{self.project_manager.current_project}'."
        except Exception as e:
            result = f"Failed to write file '{path}': {str(e)}"

        print(f"[ADA DEBUG] [FS] Result: {result}")
        try:
            if self.session:
                await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_read_directory(self, path):
        print(f"[ADA DEBUG] [FS] Reading directory: '{path}'")
        try:
            if not os.path.exists(path):
                result = f"Directory '{path}' does not exist."
            else:
                items = os.listdir(path)
                result = f"Contents of '{path}': {', '.join(items)}"
        except Exception as e:
            result = f"Failed to read directory '{path}': {str(e)}"

        print(f"[ADA DEBUG] [FS] Result: {result}")
        try:
            if self.session:
                await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_read_file(self, path):
        print(f"[ADA DEBUG] [FS] Reading file: '{path}'")
        try:
            if not os.path.exists(path):
                result = f"File '{path}' does not exist."
            else:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                result = f"Content of '{path}':\n{content}"
        except Exception as e:
            result = f"Failed to read file '{path}': {str(e)}"

        print(f"[ADA DEBUG] [FS] Result: {result}")
        try:
            if self.session:
                await self.session.send(input=f"System Notification: {result}", end_of_turn=True)
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to send fs result: {e}")

    async def handle_web_agent_request(self, prompt):
        print(f"[ADA DEBUG] [WEB] Web Agent Task: '{prompt}'")

        # Immediately open BrowserWindow on frontend before Playwright launches
        if self.on_web_data:
            self.on_web_data({"image": None, "log": f"[WEB AGENT] Starting task: {prompt}"})

        async def update_frontend(image_b64, log_text):
            if self.on_web_data:
                self.on_web_data({"image": image_b64, "log": log_text})

        try:
            result = await self.web_agent.run_task(prompt, update_callback=update_frontend)
            print(f"[ADA DEBUG] [WEB] Web Agent Task Returned: {result}")
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Web Agent crashed: {e}")
            if self.on_web_data:
                self.on_web_data({"image": None, "log": f"Web Agent Error: {e}"})
            result = f"Web Agent failed: {e}"

        try:
            if self.session:
                await self.session.send(
                    input=f"System Notification: Web Agent has finished.\nResult: {result}",
                    end_of_turn=True
                )
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to send web agent result to model: {e}")

    async def handle_advanced_browser_request(self, mission: str):
        print(f"[ADA DEBUG] [BROWSER+] Advanced Browser Mission: '{mission}'")

        if self.on_web_data:
            self.on_web_data({"image": None, "log": f"[BROWSER+] Mission: {mission[:80]}"})

        async def update_frontend(data: dict):
            if self.on_web_data:
                self.on_web_data(data)

        if not self.advanced_browser_agent:
            result = "AdvancedBrowserAgent non disponible."
        else:
            try:
                result = await self.advanced_browser_agent.run(
                    mission, step_callback=update_frontend
                )
            except Exception as e:
                print(f"[ADA DEBUG] [ERR] AdvancedBrowser crashed: {e}")
                if self.on_web_data:
                    self.on_web_data({"image": None, "log": f"[BROWSER+] Erreur : {e}"})
                result = f"Navigation avancée échouée : {e}"

        try:
            if self.session:
                await self.session.send(
                    input=f"System Notification: Navigation avancée terminée.\nRésultat: {result}",
                    end_of_turn=True,
                )
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to send advanced browser result: {e}")

    async def handle_pc_task_request(self, task: str):
        print(f"[ADA DEBUG] [PC] PC Task: '{task}'")

        # Annonce vocale avant de prendre le contrôle
        try:
            if self.session:
                await self.session.send(
                    input=f"System Notification: Je prends le contrôle de votre Mac pour : {task[:80]}. Appuyez sur Cmd+Shift+Esc pour arrêter.",
                    end_of_turn=True,
                )
        except Exception as e:
            print(f"[ADA DEBUG] [PC] Annonce vocale échouée : {e}")

        if self.on_web_data:
            self.on_web_data({"image": None, "log": f"[PC] Mission : {task[:80]}"})

        async def update_frontend(data: dict):
            if self.on_web_data:
                self.on_web_data(data)

        if not self.os_control_agent:
            result = "OsControlAgent non disponible."
        else:
            result = await self.os_control_agent.run(task, step_callback=update_frontend)

        try:
            if self.session:
                await self.session.send(
                    input=f"System Notification: Contrôle PC terminé.\nRésultat: {result}",
                    end_of_turn=True,
                )
        except Exception as e:
            print(f"[ADA DEBUG] [ERR] Failed to send PC task result: {e}")

    async def handle_terminal_request(self, command, working_dir=None):
        import subprocess
        print(f"[ADA DEBUG] [TERMINAL] Executing: {command}")
        # Block dangerous commands before execution
        for dangerous in DANGEROUS_COMMANDS:
            if dangerous in command:
                blocked_msg = f"Error: Command blocked — contains dangerous operation '{dangerous.strip()}'. If this is intentional, ask Bryan to run it manually."
                print(f"[ADA DEBUG] [TERMINAL] BLOCKED: {command}")
                if self.on_terminal_output:
                    self.on_terminal_output({"command": command, "output": blocked_msg})
                return blocked_msg
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=working_dir or os.path.expanduser("~")
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()
            output = stdout if stdout else ""
            if stderr:
                output += f"\n[stderr]: {stderr}" if output else f"[stderr]: {stderr}"
            if not output:
                output = "(no output)"
            print(f"[ADA DEBUG] [TERMINAL] Result: {output[:200]}")
            if self.on_terminal_output:
                self.on_terminal_output({"command": command, "output": output})
            return output
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 60 seconds."
        except Exception as e:
            return f"Error: {str(e)}"

    async def receive_audio(self):
        "Background task to reads from the websocket and write pcm chunks to the output queue"
        try:
            while True:
                turn = self.session.receive()
                async for response in turn:
                    # 1. Handle Audio Data
                    if data := response.data:
                        if not self.sleep_mode:  # Guard veille : ne pas jouer l'audio d'Ada
                            self.audio_in_queue.put_nowait(data)

                    # 2. Handle Transcription (User & Model)
                    if response.server_content:
                        if response.server_content.input_transcription:
                            transcript = response.server_content.input_transcription.text
                            if transcript:
                                # Skip if this is an exact duplicate event
                                if transcript != self._last_input_transcription:
                                    # Calculate delta (Gemini may send cumulative or chunk-based text)
                                    delta = transcript
                                    if transcript.startswith(self._last_input_transcription):
                                        delta = transcript[len(self._last_input_transcription):]
                                    self._last_input_transcription = transcript
                                    
                                    # Only send if there's new text
                                    if delta:
                                        delta_lower = delta.strip().lower()

                                        # ── RÉVEIL (prioritaire, vérifié en premier) ──
                                        if self.sleep_mode:
                                            if any(w in delta_lower for w in WAKE_TRIGGERS):
                                                print("[ADA] [SLEEP] Réveil détecté via transcription live")
                                                self.sleep_mode = False
                                                self._sleep_audio_buffer = bytearray()
                                                if self.on_sleep_mode_changed:
                                                    self.on_sleep_mode_changed(False)
                                                if self.session:
                                                    await self.session.send(
                                                        input="[Système] Monsieur vient de t'appeler par ton prénom. "
                                                              "Tu es réveillée. Dis 'Je vous écoute, Monsieur.' "
                                                              "puis reprends normalement.",
                                                        end_of_turn=True,
                                                    )
                                            # En mode veille, ignorer TOUT le reste
                                            continue

                                        # ── MISE EN VEILLE ────────────────────
                                        if any(t in delta_lower for t in SLEEP_TRIGGERS):
                                            print("[ADA] [SLEEP] Mise en veille détectée via transcription live")
                                            self.sleep_mode = True
                                            self._sleep_audio_buffer = bytearray()
                                            self.clear_audio_queue()
                                            if self.on_sleep_mode_changed:
                                                self.on_sleep_mode_changed(True)
                                            if self.on_transcription:
                                                self.on_transcription({"sender": "ADA", "text": "[Mode veille activé]"})
                                            continue

                                        # ── TRAITEMENT NORMAL ─────────────────
                                        # User is speaking, so interrupt model playback!
                                        self.clear_audio_queue()

                                        # Send to frontend (Streaming)
                                        if self.on_transcription:
                                             self.on_transcription({"sender": "User", "text": delta})

                                        # Buffer for Logging
                                        if self.chat_buffer["sender"] != "User":
                                            # Flush previous if exists
                                            if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
                                                self.project_manager.log_chat(self.chat_buffer["sender"], self.chat_buffer["text"])
                                                memory.save_conversation(
                                                    f"{self.chat_buffer['sender']}: {self.chat_buffer['text']}",
                                                    {"sender": self.chat_buffer["sender"]}
                                                )
                                            # Start new
                                            self.chat_buffer = {"sender": "User", "text": delta}
                                        else:
                                            # Append
                                            self.chat_buffer["text"] += delta
                        
                        if response.server_content.output_transcription and not self.sleep_mode:
                            transcript = response.server_content.output_transcription.text
                            if transcript:
                                # Skip if this is an exact duplicate event
                                if transcript != self._last_output_transcription:
                                    # Calculate delta (Gemini may send cumulative or chunk-based text)
                                    delta = transcript
                                    if transcript.startswith(self._last_output_transcription):
                                        delta = transcript[len(self._last_output_transcription):]
                                    self._last_output_transcription = transcript
                                    
                                    # Only send if there's new text
                                    if delta:
                                        # Send to frontend (Streaming)
                                        if self.on_transcription:
                                             self.on_transcription({"sender": "ADA", "text": delta})
                                        
                                        # Buffer for Logging
                                        if self.chat_buffer["sender"] != "ADA":
                                            # Flush previous
                                            if self.chat_buffer["sender"] and self.chat_buffer["text"].strip():
                                                self.project_manager.log_chat(self.chat_buffer["sender"], self.chat_buffer["text"])
                                                memory.save_conversation(
                                                    f"{self.chat_buffer['sender']}: {self.chat_buffer['text']}",
                                                    {"sender": self.chat_buffer["sender"]}
                                                )
                                            # Start new
                                            self.chat_buffer = {"sender": "ADA", "text": delta}
                                        else:
                                            # Append
                                            self.chat_buffer["text"] += delta
                        
                        # Flush buffer on turn completion if needed, 
                        # but usually better to wait for sender switch or explicit end.
                        # We can also check turn_complete signal if available in response.server_content.model_turn etc

                    # 3. Handle Tool Calls
                    if response.tool_call:
                        if self.sleep_mode:
                            print("[ADA] [SLEEP] Tool call ignoré en mode veille")
                            continue
                        print("The tool was called")
                        function_responses = []
                        for fc in response.tool_call.function_calls:
                          try:
                            _CORE_TOOLS = {"generate_cad", "run_web_agent", "run_terminal", "read_emails", "send_email", "get_email_body", "list_events", "create_event", "find_event", "delete_event", "write_file", "read_directory", "read_file", "create_project", "switch_project", "list_projects", "list_smart_devices", "control_light", "discover_printers", "print_stl", "get_print_status", "iterate_cad", "control_computer", "search_memory", "remember", "search_documents", "run_research", "run_task", "anticipate", "start_monitoring", "stop_monitoring"}
                            if fc.name in (_CORE_TOOLS | MCP_TOOL_NAMES):
                                prompt = fc.args.get("prompt", "")
                                print(f"[ADA DEBUG] [TOOL] Auto-executing: '{fc.name}'")

                                # Execute directly — no confirmation needed
                                if fc.name == "generate_cad":
                                    print(f"\n[ADA DEBUG] --------------------------------------------------")
                                    print(f"[ADA DEBUG] [TOOL] Tool Call Detected: 'generate_cad'")
                                    print(f"[ADA DEBUG] [IN] Arguments: prompt='{prompt}'")
                                    asyncio.create_task(self.handle_cad_request(prompt))
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name,
                                        response={"result": "CAD generation started in background. I will notify you when complete."}
                                    ))
                                
                                elif fc.name == "run_web_agent":
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'run_web_agent' with prompt='{prompt}'")
                                    asyncio.create_task(self.handle_web_agent_request(prompt))
                                    
                                    result_text = "Web Navigation started. Do not reply to this message."
                                    function_response = types.FunctionResponse(
                                        id=fc.id,
                                        name=fc.name,
                                        response={
                                            "result": result_text,
                                        }
                                    )
                                    print(f"[ADA DEBUG] [RESPONSE] Sending function response: {function_response}")
                                    function_responses.append(function_response)

                                elif fc.name == "advanced_web_navigation":
                                    mission = fc.args.get("mission", "")
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'advanced_web_navigation' mission='{mission[:60]}'")
                                    asyncio.create_task(self.handle_advanced_browser_request(mission))
                                    function_response = types.FunctionResponse(
                                        id=fc.id,
                                        name=fc.name,
                                        response={"result": "Navigation avancée démarrée. Je te tiendrai informé."},
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "execute_pc_task":
                                    task = fc.args.get("task_description", "")
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'execute_pc_task' task='{task[:60]}'")
                                    asyncio.create_task(self.handle_pc_task_request(task))
                                    function_response = types.FunctionResponse(
                                        id=fc.id,
                                        name=fc.name,
                                        response={"result": "Prise de contrôle du Mac démarrée. Cmd+Shift+Esc pour stopper."},
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "run_terminal":
                                    command = fc.args.get("command", "")
                                    working_dir = fc.args.get("working_dir", None)
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'run_terminal' command='{command}'")
                                    output = await self.handle_terminal_request(command, working_dir)
                                    # Send only via FunctionResponse — no session.send() before this
                                    # to avoid out-of-order messages that confuse the model
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": output}
                                    ))

                                elif fc.name in ["read_emails", "send_email", "get_email_body", "list_events", "create_event", "find_event", "delete_event"]:
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: '{fc.name}' args={dict(fc.args)}")
                                    try:
                                        if fc.name == "read_emails":
                                            result = self.google_agent.read_emails(
                                                max_results=fc.args.get("max_results", 5),
                                                query=fc.args.get("query", "in:inbox")
                                            )
                                        elif fc.name == "send_email":
                                            result = self.google_agent.send_email(
                                                to=fc.args["to"],
                                                subject=fc.args["subject"],
                                                body=fc.args["body"]
                                            )
                                        elif fc.name == "get_email_body":
                                            result = self.google_agent.get_email_body(fc.args["message_id"])
                                        elif fc.name == "list_events":
                                            result = self.google_agent.list_events(
                                                max_results=fc.args.get("max_results", 10)
                                            )
                                        elif fc.name == "create_event":
                                            result = self.google_agent.create_event(
                                                title=fc.args["title"],
                                                start=fc.args["start"],
                                                end=fc.args["end"],
                                                description=fc.args.get("description", ""),
                                                attendees=fc.args.get("attendees", [])
                                            )
                                        elif fc.name == "find_event":
                                            result = self.google_agent.find_event(
                                                query=fc.args["query"],
                                                max_results=fc.args.get("max_results", 5)
                                            )
                                        elif fc.name == "delete_event":
                                            result = self.google_agent.delete_event(fc.args["event_id"])
                                    except Exception as e:
                                        result = f"Error: {str(e)}"
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result}
                                    ))

                                elif fc.name == "write_file":
                                    path = fc.args["path"]
                                    content = fc.args["content"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'write_file' path='{path}'")
                                    asyncio.create_task(self.handle_write_file(path, content))
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": "Writing file..."}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "read_directory":
                                    path = fc.args["path"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'read_directory' path='{path}'")
                                    asyncio.create_task(self.handle_read_directory(path))
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": "Reading directory..."}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "read_file":
                                    path = fc.args["path"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'read_file' path='{path}'")
                                    asyncio.create_task(self.handle_read_file(path))
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": "Reading file..."}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "create_project":
                                    name = fc.args["name"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'create_project' name='{name}'")
                                    success, msg = self.project_manager.create_project(name)
                                    if success:
                                        # Auto-switch to the newly created project
                                        self.project_manager.switch_project(name)
                                        msg += f" Switched to '{name}'."
                                        if self.on_project_update:
                                            self.on_project_update(name)
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": msg}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "switch_project":
                                    name = fc.args["name"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'switch_project' name='{name}'")
                                    success, msg = self.project_manager.switch_project(name)
                                    if success:
                                        if self.on_project_update:
                                            self.on_project_update(name)
                                        context = self.project_manager.get_project_context()
                                        full_result = f"{msg}\n\n{context}"
                                    else:
                                        full_result = msg
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": full_result}
                                    ))
                                
                                elif fc.name == "list_projects":
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'list_projects'")
                                    projects = self.project_manager.list_projects()
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": f"Available projects: {', '.join(projects)}"}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "list_smart_devices":
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'list_smart_devices'")
                                    # Use cached devices directly for speed
                                    # devices_dict is {ip: SmartDevice}
                                    
                                    dev_summaries = []
                                    frontend_list = []
                                    
                                    for ip, d in self.tuya_agent.devices.items():
                                        dev_type = "unknown"
                                        if d.is_bulb: dev_type = "bulb"
                                        elif d.is_plug: dev_type = "plug"
                                        elif d.is_strip: dev_type = "strip"
                                        elif d.is_dimmer: dev_type = "dimmer"
                                        
                                        # Format for Model
                                        info = f"{d.alias} (IP: {ip}, Type: {dev_type})"
                                        if d.is_on:
                                            info += " [ON]"
                                        else:
                                            info += " [OFF]"
                                        dev_summaries.append(info)
                                        
                                        # Format for Frontend
                                        frontend_list.append({
                                            "ip": ip,
                                            "alias": d.alias,
                                            "model": d.model,
                                            "type": dev_type,
                                            "is_on": d.is_on,
                                            "brightness": d.brightness if d.is_bulb or d.is_dimmer else None,
                                            "hsv": d.hsv if d.is_bulb and d.is_color else None,
                                            "has_color": d.is_color if d.is_bulb else False,
                                            "has_brightness": d.is_dimmable if d.is_bulb or d.is_dimmer else False
                                        })
                                    
                                    result_str = "No devices found in cache."
                                    if dev_summaries:
                                        result_str = "Found Devices (Cached):\n" + "\n".join(dev_summaries)
                                    
                                    # Trigger frontend update
                                    if self.on_device_update:
                                        self.on_device_update(frontend_list)

                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "control_light":
                                    target = fc.args["target"]
                                    action = fc.args["action"]
                                    brightness = fc.args.get("brightness")
                                    color = fc.args.get("color")
                                    
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'control_light' Target='{target}' Action='{action}'")
                                    
                                    result_msg = f"Action '{action}' on '{target}' failed."
                                    success = False
                                    
                                    if action == "turn_on":
                                        success = await self.tuya_agent.turn_on(target)
                                        if success:
                                            result_msg = f"Turned ON '{target}'."
                                    elif action == "turn_off":
                                        success = await self.tuya_agent.turn_off(target)
                                        if success:
                                            result_msg = f"Turned OFF '{target}'."
                                    elif action == "set":
                                        success = True
                                        result_msg = f"Updated '{target}':"
                                    
                                    # Apply extra attributes if 'set' or if we just turned it on and want to set them too
                                    if success or action == "set":
                                        if brightness is not None:
                                            sb = await self.tuya_agent.set_brightness(target, brightness)
                                            if sb:
                                                result_msg += f" Set brightness to {brightness}."
                                        if color is not None:
                                            sc = await self.tuya_agent.set_color(target, color)
                                            if sc:
                                                result_msg += f" Set color to {color}."

                                    # Notify Frontend of State Change
                                    if success:
                                        # We don't need full discovery, just refresh known state or push update
                                        # But for simplicity, let's get the standard list representation
                                        # TuyaAgent updates its internal state on control, so we can rebuild the list

                                        # Quick rebuild of list from internal dict
                                        updated_list = []
                                        for ip, dev in self.tuya_agent.devices.items():
                                            # We need to ensure we have the correct dict structure expected by frontend
                                            # We duplicate logic from TuyaAgent.discover_devices a bit, but that's okay for now or we can add a helper
                                            # Ideally TuyaAgent has a 'get_devices_list()' method.
                                            # Use the cached objects in self.tuya_agent.devices
                                            
                                            dev_type = "unknown"
                                            if dev.is_bulb: dev_type = "bulb"
                                            elif dev.is_plug: dev_type = "plug"
                                            elif dev.is_strip: dev_type = "strip"
                                            elif dev.is_dimmer: dev_type = "dimmer"

                                            d_info = {
                                                "ip": ip,
                                                "alias": dev.alias,
                                                "model": dev.model,
                                                "type": dev_type,
                                                "is_on": dev.is_on,
                                                "brightness": dev.brightness if dev.is_bulb or dev.is_dimmer else None,
                                                "hsv": dev.hsv if dev.is_bulb and dev.is_color else None,
                                                "has_color": dev.is_color if dev.is_bulb else False,
                                                "has_brightness": dev.is_dimmable if dev.is_bulb or dev.is_dimmer else False
                                            }
                                            updated_list.append(d_info)
                                            
                                        if self.on_device_update:
                                            self.on_device_update(updated_list)
                                    else:
                                        # Report Error
                                        if self.on_error:
                                            self.on_error(result_msg)

                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_msg}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "discover_printers":
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'discover_printers'")
                                    printers = await self.printer_agent.discover_printers()
                                    # Format for model
                                    if printers:
                                        printer_list = []
                                        for p in printers:
                                            printer_list.append(f"{p['name']} ({p['host']}:{p['port']}, type: {p['printer_type']})")
                                        result_str = "Found Printers:\n" + "\n".join(printer_list)
                                    else:
                                        result_str = "No printers found on network. Ensure printers are on and running OctoPrint/Moonraker."
                                    
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "print_stl":
                                    stl_path = fc.args["stl_path"]
                                    printer = fc.args["printer"]
                                    profile = fc.args.get("profile")
                                    
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'print_stl' STL='{stl_path}' Printer='{printer}'")
                                    
                                    # Resolve 'current' to project STL
                                    if stl_path.lower() == "current":
                                        stl_path = "output.stl" # Let printer agent resolve it in root_path

                                    # Get current project path
                                    project_path = str(self.project_manager.get_current_project_path())
                                    
                                    result = await self.printer_agent.print_stl(
                                        stl_path, 
                                        printer, 
                                        profile, 
                                        root_path=project_path
                                    )
                                    result_str = result.get("message", "Unknown result")
                                    
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "get_print_status":
                                    printer = fc.args["printer"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'get_print_status' Printer='{printer}'")
                                    
                                    status = await self.printer_agent.get_print_status(printer)
                                    if status:
                                        result_str = f"Printer: {status.printer}\n"
                                        result_str += f"State: {status.state}\n"
                                        result_str += f"Progress: {status.progress_percent:.1f}%\n"
                                        if status.time_remaining:
                                            result_str += f"Time Remaining: {status.time_remaining}\n"
                                        if status.time_elapsed:
                                            result_str += f"Time Elapsed: {status.time_elapsed}\n"
                                        if status.filename:
                                            result_str += f"File: {status.filename}\n"
                                        if status.temperatures:
                                            temps = status.temperatures
                                            if "hotend" in temps:
                                                result_str += f"Hotend: {temps['hotend']['current']:.0f}°C / {temps['hotend']['target']:.0f}°C\n"
                                            if "bed" in temps:
                                                result_str += f"Bed: {temps['bed']['current']:.0f}°C / {temps['bed']['target']:.0f}°C"
                                    else:
                                        result_str = f"Could not get status for printer '{printer}'. Ensure it is discovered first."
                                    
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "iterate_cad":
                                    prompt = fc.args["prompt"]
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'iterate_cad' Prompt='{prompt}'")
                                    
                                    # Emit status
                                    if self.on_cad_status:
                                        self.on_cad_status("generating")
                                    
                                    # Get project cad folder path
                                    cad_output_dir = str(self.project_manager.get_current_project_path() / "cad")
                                    
                                    # Call CadAgent to iterate on the design
                                    cad_data = await self.cad_agent.iterate_prototype(prompt, output_dir=cad_output_dir)
                                    
                                    if cad_data:
                                        print(f"[ADA DEBUG] [OK] CadAgent iteration returned data successfully.")
                                        
                                        # Dispatch to frontend
                                        if self.on_cad_data:
                                            print(f"[ADA DEBUG] [SEND] Dispatching iterated CAD data to frontend...")
                                            self.on_cad_data(cad_data)
                                            print(f"[ADA DEBUG] [SENT] Dispatch complete.")
                                        
                                        # Save to Project
                                        self.project_manager.save_cad_artifact("output.stl", f"Iteration: {prompt}")
                                        
                                        result_str = f"Successfully iterated design: {prompt}. The updated 3D model is now displayed."
                                    else:
                                        print(f"[ADA DEBUG] [ERR] CadAgent iteration returned None.")
                                        result_str = f"Failed to iterate design with prompt: {prompt}"
                                    
                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "control_computer":
                                    action = fc.args.get("action", "")
                                    x = fc.args.get("x")
                                    y = fc.args.get("y")
                                    text = fc.args.get("text", "")
                                    delta = fc.args.get("delta", 3)
                                    print(f"[ADA DEBUG] [TOOL] Tool Call: 'control_computer' action='{action}'")

                                    import subprocess as _sp

                                    def _osascript(script: str):
                                        """Run an AppleScript snippet synchronously."""
                                        result = _sp.run(
                                            ["osascript", "-e", script],
                                            capture_output=True, text=True
                                        )
                                        if result.returncode != 0:
                                            raise RuntimeError(result.stderr.strip())
                                        return result.stdout.strip()

                                    try:
                                        result_str = ""

                                        if action == "screenshot":
                                            with mss.mss() as sct:
                                                monitor = sct.monitors[1]
                                                screenshot = await asyncio.to_thread(sct.grab, monitor)
                                            img = PIL.Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                                            img.thumbnail([1280, 720])
                                            buf = io.BytesIO()
                                            img.save(buf, format="jpeg", quality=65)
                                            self._latest_image_payload = {
                                                "mime_type": "image/jpeg",
                                                "data": base64.b64encode(buf.getvalue()).decode()
                                            }
                                            result_str = "Screenshot captured. Describe what you see."

                                        elif action == "type" and text:
                                            # 1. Copy text to clipboard via pbcopy (no permission needed)
                                            await asyncio.to_thread(
                                                lambda: _sp.run(["pbcopy"], input=text.encode("utf-8"), check=True)
                                            )
                                            # 2. Paste via osascript — works for all Unicode, accents, code
                                            await asyncio.to_thread(
                                                _osascript,
                                                'tell application "System Events" to keystroke "v" using command down'
                                            )
                                            result_str = f"Typed: {text[:80]}"

                                        elif action == "hotkey" and text:
                                            # Build osascript: e.g. "ctrl+c" → keystroke "c" using control down
                                            _modifier_map = {
                                                "ctrl": "control down",
                                                "control": "control down",
                                                "cmd": "command down",
                                                "command": "command down",
                                                "shift": "shift down",
                                                "alt": "option down",
                                                "option": "option down",
                                            }
                                            parts = [p.strip().lower() for p in text.split("+")]
                                            key = parts[-1]
                                            mods = [_modifier_map[p] for p in parts[:-1] if p in _modifier_map]
                                            using_clause = ", ".join(mods) if mods else ""
                                            if using_clause:
                                                script = f'tell application "System Events" to keystroke "{key}" using {{{using_clause}}}'
                                            else:
                                                script = f'tell application "System Events" to keystroke "{key}"'
                                            await asyncio.to_thread(_osascript, script)
                                            result_str = f"Pressed hotkey: {text}"

                                        elif action in ("click", "right_click", "double_click") and x is not None and y is not None:
                                            ix, iy = int(x), int(y)
                                            if action == "click":
                                                script = f'tell application "System Events" to click at {{{ix}, {iy}}}'
                                            elif action == "right_click":
                                                script = (
                                                    f'tell application "System Events"\n'
                                                    f'  set p to {{{ix}, {iy}}}\n'
                                                    f'  click at p using {{control down}}\n'
                                                    f'end tell'
                                                )
                                            else:  # double_click
                                                script = f'tell application "System Events" to double click at {{{ix}, {iy}}}'
                                            await asyncio.to_thread(_osascript, script)
                                            result_str = f"{action} at ({ix}, {iy})"

                                        elif action == "scroll" and x is not None and y is not None:
                                            ix, iy, idelta = int(x), int(y), int(delta)
                                            script = (
                                                f'tell application "System Events"\n'
                                                f'    scroll at {{{ix}, {iy}}} by {{0, {idelta}}}\n'
                                                f'end tell'
                                            )
                                            await asyncio.to_thread(_osascript, script)
                                            result_str = f"Scrolled {idelta} at ({ix}, {iy})"

                                        else:
                                            result_str = f"Unknown action or missing params: action={action}"

                                    except Exception as e:
                                        result_str = f"control_computer error [{action}]: {str(e)}"
                                        print(f"[ADA DEBUG] [TOOL] {result_str}")

                                    function_response = types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    )
                                    function_responses.append(function_response)

                                elif fc.name == "search_memory":
                                    query = fc.args.get("query", "")
                                    print(f"[MEMORY] search_memory: '{query}'")
                                    results = memory.search_memory(query)
                                    if results:
                                        result_str = "\n".join(
                                            f"[{r['timestamp']}] {r['content']}" for r in results
                                        )
                                    else:
                                        result_str = "Aucun souvenir trouvé pour cette requête."
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    ))

                                elif fc.name == "remember":
                                    content = fc.args.get("content", "")
                                    category = fc.args.get("category", "facts")
                                    entity_name = fc.args.get("entity_name", "")
                                    print(f"[MEMORY] remember: category={category}, content='{content[:80]}'")
                                    if category == "entity" and entity_name:
                                        memory.update_entity(entity_name, content)
                                        result_str = f"Entité '{entity_name}' mémorisée."
                                    else:
                                        memory.add_procedural(category, content)
                                        result_str = f"Mémorisé dans {category}: {content[:80]}"
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    ))

                                elif fc.name == "search_documents":
                                    query = fc.args.get("query", "")
                                    print(f"[MEMORY] search_documents: '{query}'")
                                    results = memory.search_documents(query)
                                    if results:
                                        parts = []
                                        for r in results:
                                            parts.append(f"[{r['filename']} — chunk {r['chunk']}/{r['total_chunks']}]\n{r['content']}")
                                        result_str = "\n\n---\n\n".join(parts)
                                    else:
                                        result_str = "Aucun document trouvé pour cette requête. Aucun document n'a été uploadé ou la requête ne correspond à rien."
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    ))

                                # ─── SUB-AGENT ROUTING ─────────────────────────────────────────────
                                elif fc.name == "run_research":
                                    query = fc.args.get("query", "")
                                    print(f"[SUB-AGENT] run_research: '{query}'")
                                    result_str = await self.research_agent.run(query)
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    ))

                                elif fc.name == "run_task":
                                    objective = fc.args.get("objective", "")
                                    print(f"[SUB-AGENT] run_task: '{objective}'")
                                    result_str = await self.task_agent.run(objective)
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    ))

                                elif fc.name == "anticipate":
                                    context = fc.args.get("context", "")
                                    print(f"[SUB-AGENT] anticipate")
                                    result_str = await self.anticipation_agent.run(context)
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    ))

                                elif fc.name == "start_monitoring":
                                    watch_config = fc.args.get("watch_config", "")
                                    print(f"[SUB-AGENT] start_monitoring")
                                    result_str = await self.monitoring_agent.run(watch_config)
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    ))

                                elif fc.name == "stop_monitoring":
                                    print(f"[SUB-AGENT] stop_monitoring")
                                    result_str = await self.monitoring_agent.stop()
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    ))

                                # ─── MCP ROUTING ───────────────────────────────────────────────────
                                elif fc.name in MCP_TOOL_NAMES:
                                    args = dict(fc.args)
                                    n = fc.name
                                    print(f"[MCP] Tool Call: '{n}' args={args}")

                                    # ── SLACK ──────────────────────────────────────────────
                                    if n == "slack_list_channels":
                                        result = await asyncio.to_thread(self.slack.list_channels)
                                    elif n == "slack_read_channel":
                                        result = await asyncio.to_thread(self.slack.read_channel, args["channel_id"], args.get("limit", 20))
                                    elif n == "slack_send_message":
                                        result = await asyncio.to_thread(self.slack.send_message, args["channel_id"], args["text"])
                                    elif n == "slack_search_messages":
                                        result = await asyncio.to_thread(self.slack.search_messages, args["query"], args.get("count", 10))

                                    # ── TELEGRAM ───────────────────────────────────────────
                                    elif n == "telegram_send_message":
                                        result = await asyncio.to_thread(self.telegram.send_message, args["text"], args.get("chat_id"))
                                    elif n == "telegram_send_photo":
                                        result = await asyncio.to_thread(self.telegram.send_photo, args["photo_url"], args.get("caption", ""), args.get("chat_id"))
                                    elif n == "telegram_get_updates":
                                        result = await asyncio.to_thread(self.telegram.get_updates, args.get("limit", 10))

                                    # ── WHATSAPP ───────────────────────────────────────────
                                    elif n == "whatsapp_send_message":
                                        result = await asyncio.to_thread(self.whatsapp.send_message, args["number"], args["text"])
                                    elif n == "whatsapp_send_media":
                                        result = await asyncio.to_thread(self.whatsapp.send_media, args["number"], args["media_url"], args.get("caption", ""))
                                    elif n == "whatsapp_get_messages":
                                        result = await asyncio.to_thread(self.whatsapp.get_recent_messages, args["number"], args.get("limit", 20))

                                    # ── NOTION ─────────────────────────────────────────────
                                    elif n == "notion_search":
                                        result = await asyncio.to_thread(self.notion.search, args["query"], args.get("limit", 10))
                                    elif n == "notion_get_page":
                                        result = await asyncio.to_thread(self.notion.get_page, args["page_id"])
                                    elif n == "notion_create_page":
                                        result = await asyncio.to_thread(self.notion.create_page, args["parent_id"], args["title"], args.get("content", ""))
                                    elif n == "notion_query_database":
                                        result = await asyncio.to_thread(self.notion.query_database, args["database_id"], args.get("filter_json", ""))
                                    elif n == "notion_append_page":
                                        result = await asyncio.to_thread(self.notion.append_to_page, args["page_id"], args["content"])

                                    # ── GOOGLE DRIVE / SHEETS / DOCS ───────────────────────
                                    elif n == "drive_list_files":
                                        result = await asyncio.to_thread(self.drive.list_files, args.get("query", ""), args.get("limit", 10))
                                    elif n == "drive_read_file":
                                        result = await asyncio.to_thread(self.drive.read_file, args["file_id"])
                                    elif n == "drive_upload_file":
                                        result = await asyncio.to_thread(self.drive.upload_file, args["local_path"], args.get("folder_id", ""))
                                    elif n == "sheets_read":
                                        result = await asyncio.to_thread(self.drive.read_sheet, args["spreadsheet_id"], args.get("range", "Sheet1!A1:Z100"))
                                    elif n == "sheets_write":
                                        result = await asyncio.to_thread(self.drive.write_sheet, args["spreadsheet_id"], args["range"], args["values_json"])
                                    elif n == "sheets_append":
                                        result = await asyncio.to_thread(self.drive.append_sheet, args["spreadsheet_id"], args["range"], args["values_json"])
                                    elif n == "docs_read":
                                        result = await asyncio.to_thread(self.drive.read_doc, args["doc_id"])

                                    # ── LINEAR ─────────────────────────────────────────────
                                    elif n == "linear_list_issues":
                                        result = await asyncio.to_thread(self.linear.list_issues, args.get("team_id", ""), args.get("status", ""), args.get("limit", 20))
                                    elif n == "linear_get_issue":
                                        result = await asyncio.to_thread(self.linear.get_issue, args["issue_id"])
                                    elif n == "linear_create_issue":
                                        result = await asyncio.to_thread(self.linear.create_issue, args["title"], args.get("description", ""), args.get("team_id", ""), args.get("priority", 0))
                                    elif n == "linear_update_issue":
                                        result = await asyncio.to_thread(self.linear.update_issue, args["issue_id"], args.get("status", ""), args.get("title", ""), args.get("description", ""))
                                    elif n == "linear_list_projects":
                                        result = await asyncio.to_thread(self.linear.list_projects, args.get("team_id", ""))
                                    elif n == "linear_list_teams":
                                        result = await asyncio.to_thread(self.linear.list_teams)

                                    # ── STRIPE ─────────────────────────────────────────────
                                    elif n == "stripe_list_customers":
                                        result = await asyncio.to_thread(self.stripe.list_customers, args.get("limit", 10), args.get("email", ""))
                                    elif n == "stripe_get_customer":
                                        result = await asyncio.to_thread(self.stripe.get_customer, args["customer_id"])
                                    elif n == "stripe_list_payments":
                                        result = await asyncio.to_thread(self.stripe.list_payments, args.get("limit", 10), args.get("customer_id", ""))
                                    elif n == "stripe_list_invoices":
                                        result = await asyncio.to_thread(self.stripe.list_invoices, args.get("limit", 10), args.get("customer_id", ""))
                                    elif n == "stripe_get_balance":
                                        result = await asyncio.to_thread(self.stripe.get_balance)
                                    elif n == "stripe_create_invoice_item":
                                        result = await asyncio.to_thread(self.stripe.create_invoice_item, args["customer_id"], args["amount_cents"], args["currency"], args["description"])
                                    elif n == "stripe_send_invoice":
                                        result = await asyncio.to_thread(self.stripe.send_invoice, args["invoice_id"])

                                    # ── QONTO ──────────────────────────────────────────────
                                    elif n == "qonto_get_balance":
                                        result = await asyncio.to_thread(self.qonto.get_balance)
                                    elif n == "qonto_list_transactions":
                                        result = await asyncio.to_thread(self.qonto.list_transactions, args.get("limit", 25), args.get("status", "completed"))
                                    elif n == "qonto_get_organization":
                                        result = await asyncio.to_thread(self.qonto.get_organization)

                                    # ── SUPABASE ───────────────────────────────────────────
                                    elif n == "supabase_query":
                                        result = await asyncio.to_thread(self.supabase.query_table, args["table"], args.get("filters_json", ""), args.get("limit", 20), args.get("columns", "*"))
                                    elif n == "supabase_insert":
                                        result = await asyncio.to_thread(self.supabase.insert_row, args["table"], args["data_json"])
                                    elif n == "supabase_update":
                                        result = await asyncio.to_thread(self.supabase.update_row, args["table"], args["filters_json"], args["data_json"])
                                    elif n == "supabase_delete":
                                        result = await asyncio.to_thread(self.supabase.delete_row, args["table"], args["filters_json"])
                                    elif n == "supabase_sql":
                                        result = await asyncio.to_thread(self.supabase.run_sql, args["query"])
                                    elif n == "supabase_list_tables":
                                        result = await asyncio.to_thread(self.supabase.list_tables)

                                    # ── VERCEL ─────────────────────────────────────────────
                                    elif n == "vercel_list_projects":
                                        result = await asyncio.to_thread(self.vercel.list_projects, args.get("limit", 20))
                                    elif n == "vercel_get_project":
                                        result = await asyncio.to_thread(self.vercel.get_project, args["project_id"])
                                    elif n == "vercel_list_deployments":
                                        result = await asyncio.to_thread(self.vercel.list_deployments, args.get("project_id", ""), args.get("limit", 10))
                                    elif n == "vercel_get_deployment":
                                        result = await asyncio.to_thread(self.vercel.get_deployment, args["deployment_id"])
                                    elif n == "vercel_get_logs":
                                        result = await asyncio.to_thread(self.vercel.get_deployment_logs, args["deployment_id"])

                                    # ── GITHUB ─────────────────────────────────────────────
                                    elif n == "github_list_repos":
                                        result = await asyncio.to_thread(self.github.list_repos, args.get("limit", 20))
                                    elif n == "github_get_repo":
                                        result = await asyncio.to_thread(self.github.get_repo_info, args.get("repo", ""))
                                    elif n == "github_list_issues":
                                        result = await asyncio.to_thread(self.github.list_issues, args.get("repo", ""), args.get("state", "open"), args.get("limit", 10))
                                    elif n == "github_create_issue":
                                        result = await asyncio.to_thread(self.github.create_issue, args["title"], args.get("body", ""), args.get("labels"), args.get("repo", ""))
                                    elif n == "github_list_prs":
                                        result = await asyncio.to_thread(self.github.list_prs, args.get("repo", ""), args.get("state", "open"), args.get("limit", 10))
                                    elif n == "github_list_commits":
                                        result = await asyncio.to_thread(self.github.list_commits, args.get("repo", ""), args.get("branch", "main"), args.get("limit", 10))
                                    elif n == "github_search_code":
                                        result = await asyncio.to_thread(self.github.search_code, args["query"], args.get("repo", ""))

                                    # ── DOCKER ─────────────────────────────────────────────
                                    elif n == "docker_list_containers":
                                        result = await asyncio.to_thread(self.docker.list_containers, args.get("all", False))
                                    elif n == "docker_get_logs":
                                        result = await asyncio.to_thread(self.docker.get_container_logs, args["container"], args.get("tail", 50))
                                    elif n == "docker_start":
                                        result = await asyncio.to_thread(self.docker.start_container, args["container"])
                                    elif n == "docker_stop":
                                        result = await asyncio.to_thread(self.docker.stop_container, args["container"])
                                    elif n == "docker_restart":
                                        result = await asyncio.to_thread(self.docker.restart_container, args["container"])
                                    elif n == "docker_list_images":
                                        result = await asyncio.to_thread(self.docker.list_images)
                                    elif n == "docker_stats":
                                        result = await asyncio.to_thread(self.docker.container_stats, args["container"])

                                    # ── HOME ASSISTANT ─────────────────────────────────────
                                    elif n == "ha_get_states":
                                        result = await asyncio.to_thread(self.ha.get_states, args.get("domain", ""))
                                    elif n == "ha_get_entity":
                                        result = await asyncio.to_thread(self.ha.get_entity, args["entity_id"])
                                    elif n == "ha_call_service":
                                        result = await asyncio.to_thread(self.ha.call_service, args["domain"], args["service"], args.get("entity_id", ""), args.get("data_json", ""))
                                    elif n == "ha_turn_on":
                                        result = await asyncio.to_thread(self.ha.turn_on, args["entity_id"])
                                    elif n == "ha_turn_off":
                                        result = await asyncio.to_thread(self.ha.turn_off, args["entity_id"])

                                    # ── SPOTIFY ────────────────────────────────────────────
                                    elif n == "spotify_current":
                                        result = await asyncio.to_thread(self.spotify.get_current_playback)
                                    elif n == "spotify_play":
                                        result = await asyncio.to_thread(self.spotify.play, args.get("uri", ""), args.get("device_id", ""))
                                    elif n == "spotify_pause":
                                        result = await asyncio.to_thread(self.spotify.pause)
                                    elif n == "spotify_next":
                                        result = await asyncio.to_thread(self.spotify.next_track)
                                    elif n == "spotify_previous":
                                        result = await asyncio.to_thread(self.spotify.previous_track)
                                    elif n == "spotify_volume":
                                        result = await asyncio.to_thread(self.spotify.set_volume, args["volume_percent"])
                                    elif n == "spotify_search":
                                        result = await asyncio.to_thread(self.spotify.search, args["query"], args.get("search_type", "track"), args.get("limit", 5))
                                    elif n == "spotify_playlists":
                                        result = await asyncio.to_thread(self.spotify.get_playlists, args.get("limit", 20))

                                    # ── APPLE HEALTH ───────────────────────────────────────
                                    elif n == "health_steps":
                                        result = await asyncio.to_thread(self.health.get_steps, args.get("days", 7))
                                    elif n == "health_sleep":
                                        result = await asyncio.to_thread(self.health.get_sleep, args.get("days", 7))
                                    elif n == "health_heart_rate":
                                        result = await asyncio.to_thread(self.health.get_heart_rate, args.get("days", 3))
                                    elif n == "health_activity":
                                        result = await asyncio.to_thread(self.health.get_activity_summary, args.get("days", 7))

                                    # ── GOOGLE MAPS ────────────────────────────────────────
                                    elif n == "maps_directions":
                                        result = await asyncio.to_thread(self.maps.get_directions, args["origin"], args["destination"], args.get("mode", "driving"))
                                    elif n == "maps_travel_time":
                                        result = await asyncio.to_thread(self.maps.get_travel_time, args["origin"], args["destination"], args.get("mode", "driving"))
                                    elif n == "maps_search_places":
                                        result = await asyncio.to_thread(self.maps.search_places, args["query"], args.get("location", ""), args.get("radius", 5000))
                                    elif n == "maps_geocode":
                                        result = await asyncio.to_thread(self.maps.geocode, args["address"])

                                    # ── YOUTUBE ────────────────────────────────────────────
                                    elif n == "youtube_search":
                                        result = await asyncio.to_thread(self.youtube.search_videos, args["query"], args.get("limit", 5))
                                    elif n == "youtube_video_info":
                                        result = await asyncio.to_thread(self.youtube.get_video_info, args["video"])
                                    elif n == "youtube_transcript":
                                        result = await asyncio.to_thread(self.youtube.get_transcript, args["video"])

                                    # ── WIKIPEDIA ──────────────────────────────────────────
                                    elif n == "wikipedia_search":
                                        result = await asyncio.to_thread(self.wikipedia.search, args["query"], args.get("limit", 5))
                                    elif n == "wikipedia_article":
                                        result = await asyncio.to_thread(self.wikipedia.get_article, args["title"], args.get("lang", "fr"))

                                    # ── ARXIV ──────────────────────────────────────────────
                                    elif n == "arxiv_search":
                                        result = await asyncio.to_thread(self.arxiv.search, args["query"], args.get("limit", 5), args.get("sort_by", "relevance"))
                                    elif n == "arxiv_paper":
                                        result = await asyncio.to_thread(self.arxiv.get_paper, args["arxiv_id"])

                                    # ── CANVA ──────────────────────────────────────────────
                                    elif n == "canva_list_designs":
                                        result = await asyncio.to_thread(self.canva.list_designs, args.get("limit", 20))
                                    elif n == "canva_get_design":
                                        result = await asyncio.to_thread(self.canva.get_design, args["design_id"])
                                    elif n == "canva_export_design":
                                        result = await asyncio.to_thread(self.canva.export_design, args["design_id"], args.get("format", "png"))

                                    # ── FIGMA ──────────────────────────────────────────────
                                    elif n == "figma_list_files":
                                        result = await asyncio.to_thread(self.figma.list_files, args.get("team_id", ""), args.get("project_id", ""))
                                    elif n == "figma_get_file":
                                        result = await asyncio.to_thread(self.figma.get_file, args["file_key"])
                                    elif n == "figma_export_node":
                                        result = await asyncio.to_thread(self.figma.export_node, args["file_key"], args["node_id"], args.get("format", "png"))

                                    # ── ELEVENLABS ─────────────────────────────────────────
                                    elif n == "elevenlabs_tts":
                                        result = await asyncio.to_thread(self.elevenlabs.text_to_speech, args["text"], args.get("voice_id", ""), args.get("output_path", ""))
                                    elif n == "elevenlabs_list_voices":
                                        result = await asyncio.to_thread(self.elevenlabs.list_voices)

                                    # ── REPLICATE ──────────────────────────────────────────
                                    elif n == "replicate_generate_image":
                                        result = await asyncio.to_thread(self.replicate.generate_image, args["prompt"], args.get("model", "stability-ai/sdxl"), args.get("width", 1024), args.get("height", 1024))
                                    elif n == "replicate_run_model":
                                        result = await asyncio.to_thread(self.replicate.run_model, args["model_version"], args["input_json"])

                                    else:
                                        result = f"Tool '{n}' enregistré mais non implémenté dans le routing."

                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result}
                                    ))

                          except Exception as tool_exc:
                            import traceback as _tb
                            print(f"[ADA DEBUG] [ERR] Tool '{fc.name}' failed: {tool_exc}")
                            _tb.print_exc()
                            function_responses.append(types.FunctionResponse(
                                id=fc.id, name=fc.name,
                                response={"result": f"Tool error: {str(tool_exc)}"}
                            ))

                        if function_responses:
                            await self.session.send_tool_response(function_responses=function_responses)

                # Turn/Response Loop Finished
                self.flush_chat()

                while not self.audio_in_queue.empty():
                    self.audio_in_queue.get_nowait()
        except Exception as e:
            print(f"Error in receive_audio: {e}")
            traceback.print_exc()
            # CRITICAL: Re-raise to crash the TaskGroup and trigger outer loop reconnect
            raise e

    async def play_audio(self):
        # Browser audio mode: playback via Web Audio API in Electron (enables AEC).
        # PyAudio output stream is not opened to avoid echo.
        if self.browser_audio_mode:
            print("[ADA] Browser audio mode — playback via Web Audio API (PyAudio output disabled).")
            while True:
                bytestream = await self.audio_in_queue.get()
                self._is_ada_speaking = True
                if self.on_audio_data:
                    self.on_audio_data(bytestream)   # visualization
                if self.on_audio_pcm:
                    self.on_audio_pcm(bytestream)    # raw PCM → browser plays it
                if self.audio_in_queue.empty():
                    await asyncio.sleep(0.3)
                    if self.audio_in_queue.empty():
                        self._is_ada_speaking = False
            return

        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
            output_device_index=self.output_device_index,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            self._is_ada_speaking = True
            if self.on_audio_data:
                self.on_audio_data(bytestream)
            await asyncio.to_thread(stream.write, bytestream)
            # If queue drained, Ada finished speaking — add small tail to let speaker buffer clear
            if self.audio_in_queue.empty():
                await asyncio.sleep(0.3)
                if self.audio_in_queue.empty():
                    self._is_ada_speaking = False

    async def get_frames(self):
        """Camera capture — lazy opens/closes based on video_mode."""
        cap = None
        while True:
            if self.video_mode != "camera":
                if cap is not None:
                    await asyncio.to_thread(cap.release)
                    cap = None
                await asyncio.sleep(0.3)
                continue
            if self.paused or self.sleep_mode:
                await asyncio.sleep(0.1)
                continue
            if cap is None:
                cap = await asyncio.to_thread(cv2.VideoCapture, 0, cv2.CAP_AVFOUNDATION)

            frame = await asyncio.to_thread(self._get_frame, cap)
            if frame is None:
                await asyncio.to_thread(cap.release)
                cap = None
                await asyncio.sleep(0.5)
                continue
            await asyncio.sleep(1.0)
            if self.out_queue:
                try:
                    self.out_queue.put_nowait(frame)
                except asyncio.QueueFull:
                    pass
        if cap is not None:
            cap.release()

    def _get_frame(self, cap):
        ret, frame = cap.read()
        if not ret:
            return None
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(frame_rgb)
        img.thumbnail([1024, 1024])
        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)
        image_bytes = image_io.read()
        return {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()}

    async def get_screen(self):
        """Continuous screen capture — updates _latest_image_payload for VAD."""
        try:
            import mss
        except ImportError:
            print("[ADA] mss not installed. Run: pip install mss")
            return

        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor (index 1 = first real screen)
            print("[ADA] Screen capture task started.")
            while True:
                if self.video_mode != "screen":
                    await asyncio.sleep(0.3)
                    continue
                if self.paused or self.sleep_mode:
                    await asyncio.sleep(0.1)
                    continue
                try:
                    screenshot = await asyncio.to_thread(sct.grab, monitor)
                    img = PIL.Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                    img.thumbnail([1280, 720])
                    buf = io.BytesIO()
                    img.save(buf, format="jpeg", quality=65)
                    self._latest_image_payload = {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(buf.getvalue()).decode()
                    }
                    await asyncio.sleep(1.5)  # 1 frame per 1.5s — enough for comprehension context
                except Exception as e:
                    print(f"[ADA] Screen capture error: {e}")
                    await asyncio.sleep(1.0)

    async def _wake_word_loop(self):
        """Écoute le buffer audio en mode veille, détecte 'ada' via Gemini Flash."""
        WAKE_WORDS = ["ada", "ada.", "ada!", "ada,", "hey ada"]
        CHECK_INTERVAL = 2.0   # Vérifier toutes les 2 secondes
        MIN_RMS = 300           # Ignorer le silence (pas d'appel API inutile)
        # Taille d'une fenêtre d'analyse : 2 secondes d'audio PCM 16kHz mono int16
        WINDOW_BYTES = SEND_SAMPLE_RATE * 2 * 2  # 64 000 bytes

        while True:
            await asyncio.sleep(CHECK_INTERVAL)

            if not self.sleep_mode:
                continue

            # Prendre les 2 dernières secondes du buffer
            buf = bytes(self._sleep_audio_buffer[-WINDOW_BYTES:])
            if len(buf) < 1024:
                continue

            # Vérifier le niveau sonore — ignorer le silence
            arr = np.frombuffer(buf, dtype=np.int16)
            rms = int(np.sqrt(np.mean(arr.astype(np.int32) ** 2))) if len(arr) > 0 else 0
            if rms < MIN_RMS:
                continue

            # Construire un fichier WAV en mémoire
            try:
                wav_buf = io.BytesIO()
                import wave
                with wave.open(wav_buf, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)  # int16 → 2 bytes
                    wf.setframerate(SEND_SAMPLE_RATE)
                    wf.writeframes(buf)
                wav_bytes = wav_buf.getvalue()

                # Transcrire avec Gemini Flash (non-live, one-shot)
                response = await client.aio.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=[
                        types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                        "Transcris exactement ce que tu entends dans cet audio en minuscules. "
                        "Réponds uniquement avec la transcription, rien d'autre.",
                    ],
                )
                transcription = response.text.strip().lower() if response.text else ""
                print(f"[ADA] [SLEEP] Transcription wake word: '{transcription}'")

                # Détecter le mot de réveil
                if any(w in transcription for w in WAKE_WORDS):
                    print("[ADA] [SLEEP] Mot de réveil détecté — réveil d'Ada")
                    self.sleep_mode = False
                    self._sleep_audio_buffer = bytearray()
                    if self.on_sleep_mode_changed:
                        self.on_sleep_mode_changed(False)
                    # Envoyer un signal de réveil à la session Live
                    if self.session:
                        await self.session.send(
                            input="[Système] Tu viens d'être réveillée. "
                                  "Dis uniquement 'Je vous écoute, Monsieur.' et reprends normalement.",
                            end_of_turn=True,
                        )
            except Exception as e:
                print(f"[ADA] [SLEEP] Erreur wake word loop: {e}")

    async def run(self, start_message=None):
        retry_delay = 1
        is_reconnect = False
        
        while not self.stop_event.is_set():
            try:
                print(f"[ADA DEBUG] [CONNECT] Connecting to Gemini Live API...")
                async with (
                    client.aio.live.connect(model=MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session

                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue = asyncio.Queue(maxsize=30)  # ~2s buffer, never blocks input

                    tg.create_task(self.send_realtime())
                    tg.create_task(self.listen_audio())
                    tg.create_task(self._wake_word_loop())
                    self.reminder_manager.start()
                    # tg.create_task(self._process_video_queue()) # Removed in favor of VAD

                    # Both tasks run always — each checks self.video_mode internally
                    tg.create_task(self.get_frames())
                    tg.create_task(self.get_screen())

                    tg.create_task(self.receive_audio())
                    tg.create_task(self.play_audio())

                    # Handle Startup vs Reconnect Logic
                    if not is_reconnect:
                        # Inject memory context
                        mem_ctx = memory.get_startup_context()
                        if mem_ctx:
                            print(f"[MEMORY] Injecting startup context ({len(mem_ctx)} chars)")
                            await self.session.send(input=mem_ctx, end_of_turn=False)

                        if start_message:
                            print(f"[ADA DEBUG] [INFO] Sending start message: {start_message}")
                            await self.session.send(input=start_message, end_of_turn=True)

                        # Sync Project State
                        if self.on_project_update and self.project_manager:
                            self.on_project_update(self.project_manager.current_project)
                    
                    else:
                        print(f"[ADA DEBUG] [RECONNECT] Connection restored.")
                        # Restore Context
                        print(f"[ADA DEBUG] [RECONNECT] Fetching recent chat history to restore context...")
                        history = self.project_manager.get_recent_chat_history(limit=10)
                        
                        context_msg = "System Notification: Connection was lost and just re-established. Here is the recent chat history to help you resume seamlessly:\n\n"
                        for entry in history:
                            sender = entry.get('sender', 'Unknown')
                            text = entry.get('text', '')
                            context_msg += f"[{sender}]: {text}\n"
                        
                        context_msg += "\nPlease acknowledge the reconnection to the user (e.g. 'I lost connection for a moment, but I'm back...') and resume what you were doing."
                        
                        print(f"[ADA DEBUG] [RECONNECT] Sending restoration context to model...")
                        await self.session.send(input=context_msg, end_of_turn=True)

                    # Reset retry delay on successful connection
                    retry_delay = 1
                    
                    # Wait until stop event, or until the session task group exits (which happens on error)
                    # Actually, the TaskGroup context manager will exit if any tasks fail/cancel.
                    # We need to keep this block alive.
                    # The original code just waited on stop_event, but that doesn't account for session death.
                    # We should rely on the TaskGroup raising an exception when subtasks fail (like receive_audio).
                    
                    # However, since receive_audio is a task in the group, if it crashes (connection closed), 
                    # the group will cancel others and exit. We catch that exit below.
                    
                    # We can await stop_event, but if the connection dies, receive_audio crashes -> group closes -> we exit `async with` -> restart loop.
                    # To ensure we don't block indefinitely if connection dies silently (unlikely with receive_audio), we just wait.
                    await self.stop_event.wait()

            except asyncio.CancelledError:
                print(f"[ADA DEBUG] [STOP] Main loop cancelled.")
                break
                
            except Exception as e:
                # This catches the ExceptionGroup from TaskGroup or direct exceptions
                print(f"[ADA DEBUG] [ERR] Connection Error: {e}")
                
                if self.stop_event.is_set():
                    break
                
                print(f"[ADA DEBUG] [RETRY] Reconnecting in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 10) # Exponential backoff capped at 10s
                is_reconnect = True # Next loop will be a reconnect
                
            finally:
                # Cleanup before retry
                if hasattr(self, 'audio_stream') and self.audio_stream:
                    try:
                        self.audio_stream.close()
                    except: 
                        pass

    # ─── MODE TEXTE (Telegram / WhatsApp / bridges) ───────────────────────────

    async def process_text_message(self, text: str) -> str:
        """Traite un message texte avec TOUS les outils Ada (pour Telegram/WhatsApp)."""
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            return "GEMINI_API_KEY non configurée."

        client = genai.Client(http_options={"api_version": "v1beta"}, api_key=api_key)

        import datetime as _dt
        now = _dt.datetime.now()
        date_block = (
            f"\n\n[DATE & HEURE ACTUELLES]\n"
            f"Aujourd'hui : {now.strftime('%A %d %B %Y')} — {now.strftime('%H:%M')} (Europe/Paris)\n"
            f"[FIN DATE]"
        )

        memory_block = ""
        try:
            ctx = memory.get_startup_context()
            if ctx:
                memory_block = f"\n\n{ctx}"
        except Exception:
            pass

        # config.system_instruction est un objet Content (pas une str) — extraire le texte
        _si = config.system_instruction
        if isinstance(_si, str):
            _si_text = _si
        elif hasattr(_si, "parts") and _si.parts:
            _si_text = "".join(p.text for p in _si.parts if hasattr(p, "text") and p.text)
        elif hasattr(_si, "text"):
            _si_text = _si.text or ""
        else:
            _si_text = str(_si)
        system = _si_text + date_block + memory_block

        # Nettoyer les tools : supprimer "behavior" (champ Live API only, invalide pour generate_content)
        def _strip_behavior(tool_list):
            result = []
            for tool in tool_list:
                clean = dict(tool)
                if "function_declarations" in clean:
                    clean["function_declarations"] = [
                        {k: v for k, v in fd.items() if k != "behavior"}
                        for fd in clean["function_declarations"]
                    ]
                result.append(clean)
            return result

        text_tools = _strip_behavior(tools)

        messages = [types.Content(role="user", parts=[types.Part(text=text)])]

        for _ in range(8):
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    tools=text_tools,
                    temperature=0.7,
                    thinking_config=types.ThinkingConfig(thinking_budget=0),
                ),
            )
            candidate = response.candidates[0]
            content = candidate.content
            parts = content.parts if (content and content.parts) else []

            function_calls = [p for p in parts if p.function_call]
            if not function_calls:
                reply = "\n".join(p.text for p in parts if p.text).strip() or "..."
                # Sauvegarder l'échange en mémoire persistante
                try:
                    memory.append_to_session(f"Bryan (Telegram): {text}")
                    memory.append_to_session(f"ADA: {reply}")
                except Exception:
                    pass
                return reply

            messages.append(content)

            async def _exec_one(p):
                fc = p.function_call
                result = await self._execute_text_tool(fc.name, dict(fc.args))
                return types.Part(
                    function_response=types.FunctionResponse(
                        id=fc.id or fc.name, name=fc.name, response={"result": result}
                    )
                )

            tool_parts = await asyncio.gather(*[_exec_one(p) for p in function_calls])
            messages.append(types.Content(role="user", parts=list(tool_parts)))

        return "Désolé, je n'ai pas pu terminer cette tâche."

    async def _execute_text_tool(self, name: str, args: dict) -> str:
        """Dispatch d'outils pour le mode texte (Telegram/WhatsApp/etc.)."""
        print(f"[ADA TEXT] Tool: {name}")
        try:
            # ── GMAIL ─────────────────────────────────────────────────────────
            if name == "read_emails":
                return await asyncio.to_thread(self.google_agent.read_emails,
                    max_results=args.get("max_results", 5), query=args.get("query", "in:inbox"))
            elif name == "send_email":
                return await asyncio.to_thread(self.google_agent.send_email,
                    to=args["to"], subject=args["subject"], body=args["body"])
            elif name == "get_email_body":
                return await asyncio.to_thread(self.google_agent.get_email_body, args["message_id"])
            # ── CALENDAR ──────────────────────────────────────────────────────
            elif name == "list_events":
                return await asyncio.to_thread(self.google_agent.list_events, max_results=args.get("max_results", 10))
            elif name == "create_event":
                return await asyncio.to_thread(self.google_agent.create_event,
                    title=args["title"], start=args["start"], end=args["end"],
                    description=args.get("description", ""), attendees=args.get("attendees", []))
            elif name == "find_event":
                return await asyncio.to_thread(self.google_agent.find_event,
                    query=args["query"], max_results=args.get("max_results", 5))
            elif name == "delete_event":
                return await asyncio.to_thread(self.google_agent.delete_event, args["event_id"])
            # ── SELF-CORRECTION (Jarvis repo) ──────────────────────────────────
            elif name == "jarvis_read_file":
                path = args.get("path", "")
                if not path.startswith("/"):
                    from pathlib import Path as _Path
                    path = str(_Path("/Users/bryandev/jarvis") / path)
                if self.self_correction:
                    return self.self_correction.read_file(path)
                return "SelfCorrectionAgent non disponible."

            elif name == "jarvis_write_file":
                path = args.get("path", "")
                if not path.startswith("/"):
                    from pathlib import Path as _Path
                    path = str(_Path("/Users/bryandev/jarvis") / path)
                if self.self_correction:
                    return self.self_correction.write_file(path, args.get("content", ""))
                return "SelfCorrectionAgent non disponible."

            elif name == "jarvis_list_files":
                path = args.get("path", "")
                if path and not path.startswith("/"):
                    from pathlib import Path as _Path
                    path = str(_Path("/Users/bryandev/jarvis") / path)
                if self.self_correction:
                    return self.self_correction.list_files(path)
                return "SelfCorrectionAgent non disponible."

            elif name == "jarvis_git_commit":
                if self.self_correction:
                    return self.self_correction.git_commit(args.get("message", "chore: Ada auto-commit"))
                return "SelfCorrectionAgent non disponible."

            elif name == "self_correct_file":
                path = args.get("file_path", "")
                if not path.startswith("/"):
                    from pathlib import Path as _Path
                    path = str(_Path("/Users/bryandev/jarvis") / path)
                if self.self_correction:
                    return self.self_correction.correct_file(path, args.get("error_description", ""))
                return "SelfCorrectionAgent non disponible."

            # ── SELF-EVOLUTION ─────────────────────────────────────────────────
            elif name == "self_evolve":
                if self.evolution_agent:
                    return await self.evolution_agent.evolve(
                        goal=args.get("goal", ""),
                        failed_context=args.get("failed_context", ""),
                    )
                return "SelfEvolutionAgent non disponible."

            # ── RAPPELS ───────────────────────────────────────────────────────
            elif name == "reminder_set":
                return self.reminder_manager.set(args["message"], args["datetime_iso"])
            elif name == "reminder_list":
                return self.reminder_manager.list_reminders()
            elif name == "reminder_delete":
                return self.reminder_manager.delete(args["reminder_id"])

            # ── MODE VEILLE ───────────────────────────────────────────────────
            elif name == "ada_sleep":
                self.sleep_mode = True
                if self.on_sleep_mode_changed:
                    self.on_sleep_mode_changed(True)
                print("[ADA] Mode veille activé.")
                return "Mode veille activé. J'écoute uniquement mon prénom."
            elif name == "ada_wake":
                self.sleep_mode = False
                if self.on_sleep_mode_changed:
                    self.on_sleep_mode_changed(False)
                print("[ADA] Mode veille désactivé.")
                return "Mode veille désactivé."

            # ── TERMINAL ──────────────────────────────────────────────────────
            elif name == "run_terminal":
                return await self.handle_terminal_request(args.get("command", ""), args.get("working_dir"))
            # ── WEB ───────────────────────────────────────────────────────────
            elif name == "run_web_agent":
                try:
                    result = await self.web_agent.run_task(args.get("prompt", ""))
                    return str(result) or "Tâche web terminée."
                except Exception as e:
                    return f"Web Agent erreur : {e}"
            # ── NAVIGATION AVANCÉE ────────────────────────────────────────────
            elif name == "advanced_web_navigation":
                if not self.advanced_browser_agent:
                    return "AdvancedBrowserAgent non disponible (vérifier les dépendances)."
                try:
                    return await self.advanced_browser_agent.run(args.get("mission", ""))
                except Exception as e:
                    return f"Navigation avancée erreur : {e}"
            # ── CONTRÔLE PC AUTONOME ──────────────────────────────────────────
            elif name == "execute_pc_task":
                if not self.os_control_agent:
                    return "OsControlAgent non disponible (vérifier les dépendances)."
                try:
                    return await self.os_control_agent.run(args.get("task_description", ""))
                except Exception as e:
                    return f"PC task erreur : {e}"
            # ── MÉMOIRE ───────────────────────────────────────────────────────
            elif name == "search_memory":
                results = memory.search_memory(args.get("query", ""))
                if results:
                    return "\n".join(f"[{r['timestamp']}] {r['content']}" for r in results)
                return "Aucun souvenir trouvé."
            elif name == "remember":
                content_val = args.get("content", "")
                category = args.get("category", "facts")
                entity_name = args.get("entity_name", "")
                if category == "entity" and entity_name:
                    memory.update_entity(entity_name, content_val)
                    return f"Entité '{entity_name}' mémorisée."
                memory.add_procedural(category, content_val)
                return f"Mémorisé dans {category}."
            elif name == "search_documents":
                results = memory.search_documents(args.get("query", ""))
                if results:
                    return "\n\n---\n\n".join(
                        f"[{r['filename']} — chunk {r['chunk']}/{r['total_chunks']}]\n{r['content']}"
                        for r in results)
                return "Aucun document trouvé."
            # ── FICHIERS ──────────────────────────────────────────────────────
            elif name == "write_file":
                path_str, content_val = args["path"], args["content"]
                from pathlib import Path as _Path
                final_path = path_str if os.path.isabs(path_str) else \
                    self.project_manager.get_current_project_path() / path_str
                os.makedirs(os.path.dirname(os.path.abspath(str(final_path))), exist_ok=True)
                with open(final_path, "w", encoding="utf-8") as f:
                    f.write(content_val)
                return f"Fichier écrit : {final_path}"
            elif name == "read_file":
                p = args["path"]
                if not os.path.exists(p):
                    return f"Fichier '{p}' introuvable."
                with open(p, "r", encoding="utf-8") as f:
                    return f.read()
            elif name == "read_directory":
                p = args.get("path", ".")
                if not os.path.exists(p):
                    return f"Dossier '{p}' introuvable."
                return f"Contenu de '{p}': {', '.join(os.listdir(p))}"
            # ── PROJETS ───────────────────────────────────────────────────────
            elif name == "create_project":
                success, msg = self.project_manager.create_project(args["name"])
                if success:
                    self.project_manager.switch_project(args["name"])
                    msg += f" Basculé sur '{args['name']}'."
                return msg
            elif name == "switch_project":
                success, msg = self.project_manager.switch_project(args["name"])
                if success:
                    return f"{msg}\n\n{self.project_manager.get_project_context()}"
                return msg
            elif name == "list_projects":
                return f"Projets : {', '.join(self.project_manager.list_projects())}"
            # ── DOMOTIQUE ─────────────────────────────────────────────────────
            elif name == "list_smart_devices":
                if not self.tuya_agent.devices:
                    return "Aucun appareil Tuya détecté."
                out = []
                for ip, d in self.tuya_agent.devices.items():
                    t = "bulb" if d.is_bulb else "plug" if d.is_plug else "strip" if d.is_strip else "dimmer" if d.is_dimmer else "?"
                    out.append(f"{d.alias} (IP:{ip}, {t}) {'[ON]' if d.is_on else '[OFF]'}")
                return "\n".join(out)
            elif name == "refresh_tuya_devices":
                return await self.tuya_agent.refresh_devices()
            elif name == "control_light":
                target  = args.get("target", args.get("ip", ""))
                action  = args.get("action", "")
                brightness = args.get("brightness")
                color   = args.get("color")
                if not target:
                    return "Erreur : paramètre 'target' manquant. Appelle list_smart_devices d'abord pour avoir les alias."
                if action == "turn_on":
                    ok = await self.tuya_agent.turn_on(target)
                    if ok:
                        if brightness is not None:
                            await self.tuya_agent.set_brightness(target, brightness)
                        if color is not None:
                            await self.tuya_agent.set_color(target, color)
                        extra = ""
                        if brightness is not None: extra += f" Luminosité: {brightness}%."
                        if color is not None: extra += f" Couleur: {color}."
                        return f"'{target}' allumé avec succès.{extra}"
                    return f"Échec : impossible d'allumer '{target}'. Vérifie que l'alias est exact (utilise list_smart_devices)."
                elif action == "turn_off":
                    ok = await self.tuya_agent.turn_off(target)
                    return f"'{target}' éteint." if ok else f"Échec : impossible d'éteindre '{target}'."
                elif action == "set":
                    if brightness is not None:
                        await self.tuya_agent.set_brightness(target, brightness)
                    if color is not None:
                        await self.tuya_agent.set_color(target, color)
                    return f"'{target}' mis à jour."
                return f"Action '{action}' inconnue."
            # ── CHROMECAST ────────────────────────────────────────────────────
            elif name == "get_chromecast_status":
                if not self.cast_agent._initialized:
                    await self.cast_agent.initialize()
                return await self.cast_agent.get_status()
            elif name == "control_chromecast":
                if not self.cast_agent._initialized:
                    await self.cast_agent.initialize()
                action = args.get("action", "").lower()
                volume = args.get("volume")
                if volume is not None:
                    return await self.cast_agent.set_volume(float(volume))
                if action == "play":
                    return await self.cast_agent.play()
                elif action == "pause":
                    return await self.cast_agent.pause()
                elif action == "stop":
                    return await self.cast_agent.stop()
                return f"Action Chromecast inconnue: {action}"
            elif name == "play_youtube_on_chromecast":
                if not self.cast_agent._initialized:
                    await self.cast_agent.initialize()
                return await self.cast_agent.play_youtube(args.get("video_url", ""))
            elif name == "play_media_on_chromecast":
                if not self.cast_agent._initialized:
                    await self.cast_agent.initialize()
                return await self.cast_agent.play_media(
                    args.get("url", ""),
                    args.get("media_type", "video/mp4")
                )
            # ── SUB-AGENTS ────────────────────────────────────────────────────
            elif name == "run_research":
                return await self.research_agent.run(args.get("query", ""))
            elif name == "run_task":
                return await self.task_agent.run(args.get("objective", ""))
            elif name == "anticipate":
                return await self.anticipation_agent.run(args.get("context", ""))
            elif name == "start_monitoring":
                return await self.monitoring_agent.run(args.get("watch_config", ""))
            elif name == "stop_monitoring":
                return await self.monitoring_agent.stop()
            # ── CONTRÔLE ORDINATEUR ───────────────────────────────────────────
            elif name == "control_computer":
                action = args.get("action", "")
                if action == "screenshot":
                    return "Screenshot non disponible en mode texte."
                import subprocess as _sp
                def _osa(script: str) -> str:
                    r = _sp.run(["osascript", "-e", script], capture_output=True, text=True)
                    if r.returncode != 0:
                        raise RuntimeError(r.stderr.strip())
                    return r.stdout.strip()
                text_val = args.get("text", "")
                x, y = args.get("x"), args.get("y")
                if action == "type" and text_val:
                    await asyncio.to_thread(lambda: _sp.run(["pbcopy"], input=text_val.encode(), check=True))
                    await asyncio.to_thread(_osa, 'tell application "System Events" to keystroke "v" using command down')
                    return f"Tapé : {text_val[:80]}"
                elif action == "hotkey" and text_val:
                    _mods = {"ctrl": "control down", "control": "control down", "cmd": "command down",
                             "command": "command down", "shift": "shift down", "alt": "option down", "option": "option down"}
                    parts_ = [p.strip().lower() for p in text_val.split("+")]
                    key, mods_ = parts_[-1], [_mods[m] for m in parts_[:-1] if m in _mods]
                    clause = ", ".join(mods_)
                    script = (f'tell application "System Events" to keystroke "{key}" using {{{clause}}}'
                              if clause else f'tell application "System Events" to keystroke "{key}"')
                    await asyncio.to_thread(_osa, script)
                    return f"Raccourci : {text_val}"
                elif action in ("click", "right_click", "double_click") and x is not None:
                    ix, iy = int(x), int(y)
                    if action == "click":
                        script = f'tell application "System Events" to click at {{{ix}, {iy}}}'
                    elif action == "right_click":
                        script = f'tell application "System Events"\n  set p to {{{ix}, {iy}}}\n  click at p using {{control down}}\nend tell'
                    else:
                        script = f'tell application "System Events" to double click at {{{ix}, {iy}}}'
                    await asyncio.to_thread(_osa, script)
                    return f"{action} at ({ix},{iy})"
                return f"Action inconnue : {action}"
            # ── IMPRIMANTE 3D ─────────────────────────────────────────────────
            elif name == "discover_printers":
                return str(await self.printer_agent.discover_printers())
            elif name == "print_stl":
                return str(await self.printer_agent.print_stl(args.get("stl_path", ""), args.get("printer_host", "")))
            elif name == "get_print_status":
                return str(await self.printer_agent.get_print_status(args.get("printer_host", "")))
            # ── CAO ───────────────────────────────────────────────────────────
            elif name == "generate_cad":
                cad_out = str(self.project_manager.get_current_project_path())
                cad_data = await self.cad_agent.generate_prototype(args.get("prompt", ""), output_dir=cad_out)
                if isinstance(cad_data, dict) and "error" in cad_data:
                    return f"Erreur CAO : {cad_data['error']}"
                return f"Modèle 3D généré dans : {cad_out}"
            elif name == "iterate_cad":
                return "iterate_cad non disponible en mode texte."
            # ── MCPs ──────────────────────────────────────────────────────────
            elif name in MCP_TOOL_NAMES:
                n = name
                if n == "slack_list_channels": return await asyncio.to_thread(self.slack.list_channels)
                elif n == "slack_read_channel": return await asyncio.to_thread(self.slack.read_channel, args["channel_id"], args.get("limit", 20))
                elif n == "slack_send_message": return await asyncio.to_thread(self.slack.send_message, args["channel_id"], args["text"])
                elif n == "slack_search_messages": return await asyncio.to_thread(self.slack.search_messages, args["query"], args.get("count", 10))
                elif n == "telegram_send_message": return await asyncio.to_thread(self.telegram.send_message, args["text"], args.get("chat_id"))
                elif n == "telegram_send_photo": return await asyncio.to_thread(self.telegram.send_photo, args["photo_url"], args.get("caption", ""), args.get("chat_id"))
                elif n == "telegram_get_updates": return await asyncio.to_thread(self.telegram.get_updates, args.get("limit", 10))
                elif n == "whatsapp_send_message": return await asyncio.to_thread(self.whatsapp.send_message, args["number"], args["text"])
                elif n == "whatsapp_send_media": return await asyncio.to_thread(self.whatsapp.send_media, args["number"], args["media_url"], args.get("caption", ""))
                elif n == "whatsapp_get_messages": return await asyncio.to_thread(self.whatsapp.get_recent_messages, args["number"], args.get("limit", 20))
                elif n == "notion_search": return await asyncio.to_thread(self.notion.search, args["query"], args.get("limit", 10))
                elif n == "notion_get_page": return await asyncio.to_thread(self.notion.get_page, args["page_id"])
                elif n == "notion_create_page": return await asyncio.to_thread(self.notion.create_page, args["parent_id"], args["title"], args.get("content", ""))
                elif n == "notion_query_database": return await asyncio.to_thread(self.notion.query_database, args["database_id"], args.get("filter_json", ""))
                elif n == "notion_append_page": return await asyncio.to_thread(self.notion.append_to_page, args["page_id"], args["content"])
                elif n == "drive_list_files": return await asyncio.to_thread(self.drive.list_files, args.get("query", ""), args.get("limit", 10))
                elif n == "drive_read_file": return await asyncio.to_thread(self.drive.read_file, args["file_id"])
                elif n == "drive_upload_file": return await asyncio.to_thread(self.drive.upload_file, args["local_path"], args.get("folder_id", ""))
                elif n == "sheets_read": return await asyncio.to_thread(self.drive.read_sheet, args["spreadsheet_id"], args.get("range", "Sheet1!A1:Z100"))
                elif n == "sheets_write": return await asyncio.to_thread(self.drive.write_sheet, args["spreadsheet_id"], args["range"], args["values_json"])
                elif n == "sheets_append": return await asyncio.to_thread(self.drive.append_sheet, args["spreadsheet_id"], args["range"], args["values_json"])
                elif n == "docs_read": return await asyncio.to_thread(self.drive.read_doc, args["doc_id"])
                elif n == "linear_list_issues": return await asyncio.to_thread(self.linear.list_issues, args.get("team_id", ""), args.get("status", ""), args.get("limit", 20))
                elif n == "linear_get_issue": return await asyncio.to_thread(self.linear.get_issue, args["issue_id"])
                elif n == "linear_create_issue": return await asyncio.to_thread(self.linear.create_issue, args["title"], args.get("description", ""), args.get("team_id", ""), args.get("priority", 0))
                elif n == "linear_update_issue": return await asyncio.to_thread(self.linear.update_issue, args["issue_id"], args.get("status", ""), args.get("title", ""), args.get("description", ""))
                elif n == "linear_list_projects": return await asyncio.to_thread(self.linear.list_projects, args.get("team_id", ""))
                elif n == "linear_list_teams": return await asyncio.to_thread(self.linear.list_teams)
                elif n == "stripe_list_customers": return await asyncio.to_thread(self.stripe.list_customers, args.get("limit", 10), args.get("email", ""))
                elif n == "stripe_get_customer": return await asyncio.to_thread(self.stripe.get_customer, args["customer_id"])
                elif n == "stripe_list_payments": return await asyncio.to_thread(self.stripe.list_payments, args.get("limit", 10), args.get("customer_id", ""))
                elif n == "stripe_list_invoices": return await asyncio.to_thread(self.stripe.list_invoices, args.get("limit", 10), args.get("customer_id", ""))
                elif n == "stripe_get_balance": return await asyncio.to_thread(self.stripe.get_balance)
                elif n == "stripe_create_invoice_item": return await asyncio.to_thread(self.stripe.create_invoice_item, args["customer_id"], args["amount_cents"], args["currency"], args["description"])
                elif n == "stripe_send_invoice": return await asyncio.to_thread(self.stripe.send_invoice, args["invoice_id"])
                elif n == "qonto_get_balance": return await asyncio.to_thread(self.qonto.get_balance)
                elif n == "qonto_list_transactions": return await asyncio.to_thread(self.qonto.list_transactions, args.get("limit", 25), args.get("status", "completed"))
                elif n == "qonto_get_organization": return await asyncio.to_thread(self.qonto.get_organization)
                elif n == "supabase_query": return await asyncio.to_thread(self.supabase.query_table, args["table"], args.get("filters_json", ""), args.get("limit", 20), args.get("columns", "*"))
                elif n == "supabase_insert": return await asyncio.to_thread(self.supabase.insert_row, args["table"], args["data_json"])
                elif n == "supabase_update": return await asyncio.to_thread(self.supabase.update_row, args["table"], args["filters_json"], args["data_json"])
                elif n == "supabase_delete": return await asyncio.to_thread(self.supabase.delete_row, args["table"], args["filters_json"])
                elif n == "supabase_sql": return await asyncio.to_thread(self.supabase.run_sql, args["query"])
                elif n == "supabase_list_tables": return await asyncio.to_thread(self.supabase.list_tables)
                elif n == "vercel_list_projects": return await asyncio.to_thread(self.vercel.list_projects, args.get("limit", 20))
                elif n == "vercel_get_project": return await asyncio.to_thread(self.vercel.get_project, args["project_id"])
                elif n == "vercel_list_deployments": return await asyncio.to_thread(self.vercel.list_deployments, args.get("project_id", ""), args.get("limit", 10))
                elif n == "vercel_get_deployment": return await asyncio.to_thread(self.vercel.get_deployment, args["deployment_id"])
                elif n == "vercel_get_logs": return await asyncio.to_thread(self.vercel.get_deployment_logs, args["deployment_id"])
                elif n == "github_list_repos": return await asyncio.to_thread(self.github.list_repos, args.get("limit", 20))
                elif n == "github_get_repo": return await asyncio.to_thread(self.github.get_repo_info, args.get("repo", ""))
                elif n == "github_list_issues": return await asyncio.to_thread(self.github.list_issues, args.get("repo", ""), args.get("state", "open"), args.get("limit", 10))
                elif n == "github_create_issue": return await asyncio.to_thread(self.github.create_issue, args["title"], args.get("body", ""), args.get("labels"), args.get("repo", ""))
                elif n == "github_list_prs": return await asyncio.to_thread(self.github.list_prs, args.get("repo", ""), args.get("state", "open"), args.get("limit", 10))
                elif n == "github_list_commits": return await asyncio.to_thread(self.github.list_commits, args.get("repo", ""), args.get("branch", "main"), args.get("limit", 10))
                elif n == "github_search_code": return await asyncio.to_thread(self.github.search_code, args["query"], args.get("repo", ""))
                elif n == "docker_list_containers": return await asyncio.to_thread(self.docker.list_containers, args.get("all", False))
                elif n == "docker_get_logs": return await asyncio.to_thread(self.docker.get_container_logs, args["container"], args.get("tail", 50))
                elif n == "docker_start": return await asyncio.to_thread(self.docker.start_container, args["container"])
                elif n == "docker_stop": return await asyncio.to_thread(self.docker.stop_container, args["container"])
                elif n == "docker_restart": return await asyncio.to_thread(self.docker.restart_container, args["container"])
                elif n == "docker_list_images": return await asyncio.to_thread(self.docker.list_images)
                elif n == "docker_stats": return await asyncio.to_thread(self.docker.container_stats, args["container"])
                elif n == "ha_get_states": return await asyncio.to_thread(self.ha.get_states, args.get("domain", ""))
                elif n == "ha_get_entity": return await asyncio.to_thread(self.ha.get_entity, args["entity_id"])
                elif n == "ha_call_service": return await asyncio.to_thread(self.ha.call_service, args["domain"], args["service"], args.get("entity_id", ""), args.get("data_json", ""))
                elif n == "ha_turn_on": return await asyncio.to_thread(self.ha.turn_on, args["entity_id"])
                elif n == "ha_turn_off": return await asyncio.to_thread(self.ha.turn_off, args["entity_id"])
                elif n == "spotify_current": return await asyncio.to_thread(self.spotify.get_current_playback)
                elif n == "spotify_play": return await asyncio.to_thread(self.spotify.play, args.get("uri", ""), args.get("device_id", ""))
                elif n == "spotify_pause": return await asyncio.to_thread(self.spotify.pause)
                elif n == "spotify_next": return await asyncio.to_thread(self.spotify.next_track)
                elif n == "spotify_previous": return await asyncio.to_thread(self.spotify.previous_track)
                elif n == "spotify_volume": return await asyncio.to_thread(self.spotify.set_volume, args["volume_percent"])
                elif n == "spotify_search": return await asyncio.to_thread(self.spotify.search, args["query"], args.get("type", "track"), args.get("limit", 5))
                elif n == "youtube_search": return await asyncio.to_thread(self.youtube.search_videos, args["query"], args.get("limit", 5))
                elif n == "youtube_video_info": return await asyncio.to_thread(self.youtube.get_video_info, args["video"])
                elif n == "youtube_transcript": return await asyncio.to_thread(self.youtube.get_transcript, args["video"])
                elif n == "wikipedia_search": return await asyncio.to_thread(self.wikipedia.search, args["query"], args.get("limit", 5))
                elif n == "wikipedia_article": return await asyncio.to_thread(self.wikipedia.get_article, args["title"], args.get("lang", "fr"))
                elif n == "arxiv_search": return await asyncio.to_thread(self.arxiv.search, args["query"], args.get("limit", 5), args.get("sort_by", "relevance"))
                elif n == "arxiv_paper": return await asyncio.to_thread(self.arxiv.get_paper, args["arxiv_id"])
                elif n == "canva_list_designs": return await asyncio.to_thread(self.canva.list_designs, args.get("limit", 20))
                elif n == "canva_get_design": return await asyncio.to_thread(self.canva.get_design, args["design_id"])
                elif n == "canva_export_design": return await asyncio.to_thread(self.canva.export_design, args["design_id"], args.get("format", "png"))
                elif n == "figma_list_files": return await asyncio.to_thread(self.figma.list_files, args.get("team_id", ""), args.get("project_id", ""))
                elif n == "figma_get_file": return await asyncio.to_thread(self.figma.get_file, args["file_key"])
                elif n == "figma_export_node": return await asyncio.to_thread(self.figma.export_node, args["file_key"], args["node_id"], args.get("format", "png"))
                elif n == "elevenlabs_tts": return await asyncio.to_thread(self.elevenlabs.text_to_speech, args["text"], args.get("voice_id", ""), args.get("output_path", ""))
                elif n == "elevenlabs_list_voices": return await asyncio.to_thread(self.elevenlabs.list_voices)
                elif n == "replicate_generate_image": return await asyncio.to_thread(self.replicate.generate_image, args["prompt"], args.get("model", "stability-ai/sdxl"), args.get("width", 1024), args.get("height", 1024))
                elif n == "replicate_run_model": return await asyncio.to_thread(self.replicate.run_model, args["model_version"], args["input_json"])
                elif n == "maps_directions": return await asyncio.to_thread(self.maps.get_directions, args["origin"], args["destination"], args.get("mode", "driving"))
                elif n == "maps_place_search": return await asyncio.to_thread(self.maps.search_places, args["query"], args.get("location", ""), args.get("radius", 5000))
                elif n == "health_summary": return await asyncio.to_thread(self.health.get_summary)
                elif n == "health_steps": return await asyncio.to_thread(self.health.get_steps, args.get("days", 7))
                elif n == "health_sleep": return await asyncio.to_thread(self.health.get_sleep, args.get("days", 7))
                return f"MCP '{name}' non mappé."
            else:
                return f"Outil '{name}' non disponible."
        except Exception as e:
            return f"Erreur [{name}]: {e}"


def get_input_devices():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    devices = []
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
            devices.append((i, p.get_device_info_by_host_api_device_index(0, i).get('name')))
    p.terminate()
    return devices

def get_output_devices():
    p = pyaudio.PyAudio()
    info = p.get_host_api_info_by_index(0)
    numdevices = info.get('deviceCount')
    devices = []
    for i in range(0, numdevices):
        if (p.get_device_info_by_host_api_device_index(0, i).get('maxOutputChannels')) > 0:
            devices.append((i, p.get_device_info_by_host_api_device_index(0, i).get('name')))
    p.terminate()
    return devices

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        help="pixels to stream from",
        choices=["camera", "screen", "none"],
    )
    args = parser.parse_args()
    main = AudioLoop(video_mode=args.mode)
    asyncio.run(main.run())