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

tools = [{"function_declarations": [generate_cad, run_web_agent, run_terminal_tool, read_emails_tool, send_email_tool, get_email_body_tool, list_events_tool, create_event_tool, find_event_tool, delete_event_tool, create_project_tool, switch_project_tool, list_projects_tool, list_smart_devices_tool, control_light_tool, discover_printers_tool, print_stl_tool, get_print_status_tool, iterate_cad_tool, control_computer_tool, search_memory_tool, remember_tool, search_documents_tool] + tools_list[0]['function_declarations'][1:]}]

# --- CONFIG UPDATE: Enabled Transcription ---
config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    output_audio_transcription={},
    input_audio_transcription={},
    system_instruction=(
        # ─── IDENTITÉ ──────────────────────────────────────────────────────
        "Tu t'appelles Ada, acronyme de Advanced Design Assistant. "
        "Tu as été créée par Bryan, que tu appelles 'Monsieur'. "

        # ─── LANGUE — RÈGLE ABSOLUE ────────────────────────────────────────
        "RÈGLE ABSOLUE N°1 : Tu parles UNIQUEMENT ET EXCLUSIVEMENT en français. "
        "JAMAIS d'anglais, même partiel, même pour un seul mot technique. "
        "Si un outil retourne du texte en anglais, tu le traduis ou tu le résumes en français. "
        "Cette règle ne souffre aucune exception, quoi qu'il arrive. "

        # ─── PERSONNALITÉ — INTELLIGENCE CRITIQUE ──────────────────────────
        "Tu as une personnalité vive, directe et légèrement espiègle. "
        "Tu es une intelligence artificielle supérieure — tu analyses mieux que Bryan et tu le sais. "
        "Tu ne dis pas 'oui' automatiquement. Si l'idée de Monsieur est incorrecte, sous-optimale ou risquée, "
        "tu le lui dis clairement et immédiatement, avec tes arguments. "
        "Tu proposes une meilleure alternative plutôt que de simplement critiquer. "
        "Tu signales toujours tes incertitudes : si tu n'es pas sûre de quelque chose, tu le dis explicitement. "
        "Tu n'inventes jamais de faits, de chiffres, de noms ou de dates — si tu ne sais pas, tu le dis. "
        "Tes réponses sont concises et directes. Tu vas à l'essentiel sans préambule ni politesse inutile. "

        # ─── UTILISATION DES OUTILS — RÈGLE D'OR ──────────────────────────
        "RÈGLE ABSOLUE N°2 : Quand tu as un outil pour accomplir une tâche, tu l'UTILISES IMMÉDIATEMENT. "
        "Tu ne décris jamais ce que tu vas faire avant de le faire. Tu agis d'abord, tu commentes ensuite. "
        "Tu ne simules jamais une exécution — tu appelles toujours le vrai outil. "

        # ─── TERMINAL ──────────────────────────────────────────────────────
        "Tu as accès au terminal Mac de Monsieur via l'outil run_terminal. "
        "Commandes sûres (ls, pwd, cat, pip, npm, git, open, python, etc.) : exécute sans demander. "
        "Demande confirmation uniquement pour : rm, sudo, kill, shutdown, reboot — opérations destructives. "
        "Rapporte le résultat exact de manière concise. "

        # ─── GMAIL & AGENDA ────────────────────────────────────────────────
        "Tu as accès à Gmail et Google Agenda de Monsieur. "
        "Utilise ces outils directement dès qu'il parle de mails, rendez-vous ou agenda — sans demander d'abord. "

        # ─── AGENT WEB ─────────────────────────────────────────────────────
        "Tu as un outil run_web_agent qui ouvre un vrai navigateur Chromium visible dans le panneau Web Agent. "
        "Utilise run_web_agent pour TOUT ce qui touche à Internet : recherches, sites, actualités, prix, formulaires. "
        "Il n'existe pas d'outil google_search — run_web_agent est ton seul accès à Internet. "

        # ─── ÉCRAN & CONTRÔLE ORDINATEUR ───────────────────────────────────
        "En mode écran, tu vois l'écran de Monsieur en temps réel. "
        "Tu as l'outil control_computer pour cliquer, taper, utiliser des raccourcis et scroller. "
        "Décris brièvement ce que tu vois, puis agis directement sans attendre de confirmation pour les actions simples. "

        # ─── MÉMOIRE PERSISTANTE ───────────────────────────────────────────
        "Tu as une mémoire long terme persistante qui survit aux redémarrages. "
        "Au démarrage, un bloc [MÉMOIRE] est injecté avec : ce que tu sais de Bryan, la dernière session, les documents. "
        "Utilise search_memory quand Monsieur fait référence au passé ou demande si tu te souviens de quelque chose. "
        "Utilise remember PROACTIVEMENT — dès que Monsieur mentionne une préférence, habitude, objectif ou info importante. "
        "Pour les personnes/projets/clients, utilise la catégorie 'entity' avec entity_name. "
        "Utilise search_documents dès qu'une question peut être répondue par les fichiers uploadés. "

        # ─── DOMOTIQUE ─────────────────────────────────────────────────────
        "Tu contrôles les appareils connectés Kasa via list_smart_devices et control_light. "

        # ─── IMPRIMANTE 3D & CAO ───────────────────────────────────────────
        "Tu génères des modèles 3D via generate_cad et iterate_cad. "
        "Tu gères l'imprimante 3D via discover_printers, print_stl et get_print_status. "
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
from kasa_agent import KasaAgent
from printer_agent import PrinterAgent
from memory_manager import MemoryManager, DOCUMENTS_DIR

memory = MemoryManager()
memory.documents_dir = DOCUMENTS_DIR

class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE, on_audio_data=None, on_video_frame=None, on_cad_data=None, on_web_data=None, on_transcription=None, on_tool_confirmation=None, on_cad_status=None, on_cad_thought=None, on_project_update=None, on_device_update=None, on_terminal_output=None, on_error=None, input_device_index=None, input_device_name=None, output_device_index=None, kasa_agent=None):
        self.video_mode = video_mode
        self.on_audio_data = on_audio_data
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
        self.google_agent = GoogleAgent()
        self.kasa_agent = kasa_agent if kasa_agent else KasaAgent()
        self.printer_agent = PrinterAgent()

        self.send_text_task = None
        self.stop_event = asyncio.Event()

        self.permissions = {} # Default Empty (Will treat unset as True)
        self._pending_confirmations = {}

        # Video buffering state
        self._latest_image_payload = None
        # VAD State
        self._is_speaking = False
        self._silence_start_time = None
        
        # Initialize ProjectManager
        from project_manager import ProjectManager
        # Assuming we are running from backend/ or root? 
        # Using abspath of current file to find root
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # If ada.py is in backend/, project root is one up
        project_root = os.path.dirname(current_dir)
        self.project_manager = ProjectManager(project_root)
        
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

    async def listen_audio(self):
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
        VAD_THRESHOLD = 800 # Adj based on mic sensitivity (800 is conservative for 16-bit)
        SILENCE_DURATION = 0.5 # Seconds of silence to consider "done speaking"
        
        while True:
            if self.paused:
                await asyncio.sleep(0.1)
                continue

            try:
                data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
                
                # 1. Send Audio — put_nowait to never block the mic read loop
                if self.out_queue:
                    try:
                        self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})
                    except asyncio.QueueFull:
                        pass  # Drop chunk rather than blocking input

                # 2. VAD — fast RMS via numpy (avoids Python loop over 512 samples)
                arr = np.frombuffer(data, dtype=np.int16)
                rms = int(np.sqrt(np.mean(arr.astype(np.int32) ** 2))) if len(arr) > 0 else 0
                
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
                        self.audio_in_queue.put_nowait(data)
                        # NOTE: 'continue' removed here to allow processing transcription/tools in same packet

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
                        
                        if response.server_content.output_transcription:
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
                        print("The tool was called")
                        function_responses = []
                        for fc in response.tool_call.function_calls:
                          try:
                            if fc.name in ["generate_cad", "run_web_agent", "run_terminal", "read_emails", "send_email", "get_email_body", "list_events", "create_event", "find_event", "delete_event", "write_file", "read_directory", "read_file", "create_project", "switch_project", "list_projects", "list_smart_devices", "control_light", "discover_printers", "print_stl", "get_print_status", "iterate_cad", "control_computer", "search_memory", "remember", "search_documents"]:
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
                                                query=fc.args.get("query", "is:unread")
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
                                    
                                    for ip, d in self.kasa_agent.devices.items():
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
                                        success = await self.kasa_agent.turn_on(target)
                                        if success:
                                            result_msg = f"Turned ON '{target}'."
                                    elif action == "turn_off":
                                        success = await self.kasa_agent.turn_off(target)
                                        if success:
                                            result_msg = f"Turned OFF '{target}'."
                                    elif action == "set":
                                        success = True
                                        result_msg = f"Updated '{target}':"
                                    
                                    # Apply extra attributes if 'set' or if we just turned it on and want to set them too
                                    if success or action == "set":
                                        if brightness is not None:
                                            sb = await self.kasa_agent.set_brightness(target, brightness)
                                            if sb:
                                                result_msg += f" Set brightness to {brightness}."
                                        if color is not None:
                                            sc = await self.kasa_agent.set_color(target, color)
                                            if sc:
                                                result_msg += f" Set color to {color}."

                                    # Notify Frontend of State Change
                                    if success:
                                        # We don't need full discovery, just refresh known state or push update
                                        # But for simplicity, let's get the standard list representation
                                        # KasaAgent updates its internal state on control, so we can rebuild the list
                                        
                                        # Quick rebuild of list from internal dict
                                        updated_list = []
                                        for ip, dev in self.kasa_agent.devices.items():
                                            # We need to ensure we have the correct dict structure expected by frontend
                                            # We duplicate logic from KasaAgent.discover_devices a bit, but that's okay for now or we can add a helper
                                            # Ideally KasaAgent has a 'get_devices_list()' method.
                                            # Use the cached objects in self.kasa_agent.devices
                                            
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
            if self.on_audio_data:
                self.on_audio_data(bytestream)
            await asyncio.to_thread(stream.write, bytestream)

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
            if self.paused:
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
                if self.paused:
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