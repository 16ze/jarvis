import sys
import asyncio

# Fix for asyncio subprocess support on Windows
# MUST BE SET BEFORE OTHER IMPORTS
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import socketio
import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import asyncio
import threading
import sys
import os
import json
import numpy as np
from datetime import datetime
from pathlib import Path



# Ensure we can import ada
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import ada
import external_bridge
from dotenv import load_dotenv
load_dotenv()
from authenticator import FaceAuthenticator
from tuya_agent import TuyaAgent
from web_agent import WebAgent
from chromecast_agent import CastAgent

# ─── API AUTH ─────────────────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)
_ADA_TOKEN = os.getenv("ADA_API_TOKEN", "")

def require_token(creds: HTTPAuthorizationCredentials = Security(_bearer)):
    """Vérifie le Bearer token sur les endpoints HTTP sensibles."""
    if not _ADA_TOKEN:
        # Pas de token configuré → on bloque tout par sécurité
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "ADA_API_TOKEN non configuré")
    if not creds or creds.credentials != _ADA_TOKEN:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token invalide ou manquant")

# ─── SOCKETIO + APP ───────────────────────────────────────────────────────────
# Create a Socket.IO server
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app_socketio = socketio.ASGIApp(sio, app)

import signal

# --- SHUTDOWN HANDLER ---
def signal_handler(sig, frame):
    print(f"\n[SERVER] Caught signal {sig}. Exiting gracefully...")
    # Clean up audio loop
    if audio_loop:
        try:
            print("[SERVER] Stopping Audio Loop...")
            audio_loop.stop() 
        except:
            pass
    # Force kill
    print("[SERVER] Force exiting...")
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Global state
audio_loop = None
loop_task = None
authenticator = None
tuya_agent = TuyaAgent()
standalone_web_agent = WebAgent()
cast_agent = CastAgent()
SETTINGS_FILE = "settings.json"

DEFAULT_SETTINGS = {
    "face_auth_enabled": False, # Default OFF as requested
    "tool_permissions": {
        "generate_cad": True,
        "run_web_agent": True,
        "write_file": True,
        "read_directory": True,
        "read_file": True,
        "create_project": True,
        "switch_project": True,
        "list_projects": True
    },
    "printers": [], # List of {host, port, name, type}
    "tuya_devices": [], # List of {name, id, key, ip, type}
    "camera_flipped": False, # Invert cursor horizontal direction
    "timezone": "Europe/Paris" # IANA timezone for Google Calendar events
}

SETTINGS = DEFAULT_SETTINGS.copy()

def load_settings():
    global SETTINGS
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                loaded = json.load(f)
                # Merge with defaults to ensure new keys exist
                # Deep merge for tool_permissions would be better but shallow merge of top keys + tool_permissions check is okay for now
                for k, v in loaded.items():
                    if k == "tool_permissions" and isinstance(v, dict):
                         SETTINGS["tool_permissions"].update(v)
                    else:
                        SETTINGS[k] = v
            print(f"Loaded settings: {SETTINGS}")
        except Exception as e:
            print(f"Error loading settings: {e}")

def save_settings():
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(SETTINGS, f, indent=4)
        print("Settings saved.")
    except Exception as e:
        print(f"Error saving settings: {e}")

# Load on startup
load_settings()

authenticator = None
tuya_agent = TuyaAgent(known_devices=SETTINGS.get("tuya_devices"))
# tool_permissions is now SETTINGS["tool_permissions"]

# ─── HEALTH REPORT ───────────────────────────────────────────────────────────
_health_report: dict = {}

async def build_health_report() -> dict:
    """
    Vérifie l'état de chaque composant Ada.
    Retourne un rapport structuré {env_vars, files, agents, summary}.
    """
    from pathlib import Path as _Path
    _root = _Path(__file__).parent
    _ok, _warn, _ko = "✅", "⚠️", "❌"

    # ── Variables d'environnement ─────────────────────────────────────────────
    env_map = {
        "Gemini (voix/texte)":     "GEMINI_API_KEY",
        "Telegram bot token":      "TELEGRAM_BOT_TOKEN",
        "Telegram chat ID":        "TELEGRAM_CHAT_ID",
        "GitHub":                  "GITHUB_TOKEN",
        "Spotify":                 "SPOTIFY_CLIENT_ID",
        "Slack":                   "SLACK_BOT_TOKEN",
        "Notion":                  "NOTION_API_KEY",
        "Linear":                  "LINEAR_API_KEY",
        "Stripe":                  "STRIPE_SECRET_KEY",
        "Qonto":                   "QONTO_API_KEY",
        "Supabase":                "SUPABASE_URL",
        "Vercel":                  "VERCEL_TOKEN",
        "Google Maps":             "GOOGLE_MAPS_API_KEY",
        "ElevenLabs":              "ELEVENLABS_API_KEY",
        "Replicate":               "REPLICATE_API_TOKEN",
        "Home Assistant":          "HOME_ASSISTANT_URL",
        "WhatsApp":                "WHATSAPP_API_URL",
        "Tuya API key":            "TUYA_API_KEY",
        "Tuya Camera device ID":   "TUYA_CAMERA_DEVICE_ID",
        "Ada API token (sécurité)":"ADA_API_TOKEN",
    }
    env_results = {}
    for label, var in env_map.items():
        env_results[label] = _ok if os.getenv(var) else f"{_ko} {var} manquant"

    # ── Fichiers critiques ────────────────────────────────────────────────────
    files_map = {
        "google_token.json (OAuth2)": _root / "google_token.json",
        ".spotify_token":             _root / ".spotify_token",
        "tinytuya.json":              _root / "tinytuya.json",
        "devices.json":               _root / "devices.json",
        "memory/procedural.json":     _root / "memory" / "procedural.json",
    }
    file_results = {}
    for label, path in files_map.items():
        file_results[label] = _ok if path.exists() else f"{_warn} absent (optionnel)"

    # ── Agents runtime ────────────────────────────────────────────────────────
    agent_results = {}
    try:
        n_devices = len(tuya_agent.devices) if tuya_agent else 0
        agent_results["Tuya smart home"] = f"{_ok} {n_devices} device(s)" if n_devices > 0 else f"{_warn} 0 device (réseau Tuya inaccessible ?)"
    except Exception as e:
        agent_results["Tuya smart home"] = f"{_ko} {e}"
    try:
        agent_results["Chromecast"] = f"{_ok} connecté" if (cast_agent and getattr(cast_agent, '_initialized', False)) else f"{_warn} non connecté (TV éteinte ?)"
    except Exception as e:
        agent_results["Chromecast"] = f"{_ko} {e}"

    # AudioLoop
    agent_results["AudioLoop (voix)"] = f"{_ok} actif" if audio_loop else f"{_warn} non démarré"

    # Bridge Telegram
    agent_results["Bridge Telegram"] = _ok if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID") else f"{_ko} token/chat_id manquant"

    # Résumé
    all_vals = list(env_results.values()) + list(agent_results.values())
    n_ok   = sum(1 for v in all_vals if v.startswith(_ok))
    n_warn = sum(1 for v in all_vals if v.startswith(_warn))
    n_ko   = sum(1 for v in all_vals if v.startswith(_ko))

    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": f"{_ok} {n_ok} OK  {_warn} {n_warn} avertissements  {_ko} {n_ko} erreurs",
        "env_vars": env_results,
        "files": file_results,
        "agents": agent_results,
    }

    # Log console lisible
    sep = "─" * 60
    print(f"\n[HEALTH] {sep}")
    print(f"[HEALTH] Rapport Ada — {report['timestamp']}")
    print(f"[HEALTH] {report['summary']}")
    print(f"[HEALTH] {sep}")
    for section, items in [("Env vars", env_results), ("Fichiers", file_results), ("Agents", agent_results)]:
        print(f"[HEALTH] ── {section} ──")
        for k, v in items.items():
            print(f"[HEALTH]   {v}  {k}")
    print(f"[HEALTH] {sep}\n")

    return report


@app.on_event("startup")
async def startup_event():
    import sys
    print(f"[SERVER DEBUG] Startup Event Triggered")
    print(f"[SERVER DEBUG] Python Version: {sys.version}")
    try:
        loop = asyncio.get_running_loop()
        print(f"[SERVER DEBUG] Running Loop: {type(loop)}")
        policy = asyncio.get_event_loop_policy()
        print(f"[SERVER DEBUG] Current Policy: {type(policy)}")
    except Exception as e:
        print(f"[SERVER DEBUG] Error checking loop: {e}")

    print("[SERVER] Startup: Initializing Tuya Agent...")
    try:
        await asyncio.wait_for(tuya_agent.initialize(), timeout=15.0)
    except asyncio.TimeoutError:
        print("[SERVER] Tuya init timeout — devices chargés sans statut initial")

    print("[SERVER] Startup: Initializing Chromecast Agent...")
    result = await cast_agent.initialize()
    print(f"[SERVER] Chromecast: {result}")

    print("[SERVER] Startup: Démarrage du bridge Telegram/WhatsApp...")
    external_bridge.start_bridge()

    # ── Health report initial ─────────────────────────────────────────────────
    global _health_report
    _health_report = await build_health_report()
    await sio.emit("health_report", _health_report)


@app.get("/health")
async def health_endpoint():
    """Rapport de santé Ada — état de tous les agents et variables d'environnement."""
    global _health_report
    if not _health_report:
        _health_report = await build_health_report()
    return _health_report


@app.get("/status")
async def status():
    return {"status": "running", "service": "A.D.A Backend"}


# ─── SPOTIFY OAuth ────────────────────────────────────────────────────────────

@app.get("/spotify/auth")
async def spotify_auth():
    """Génère l'URL d'autorisation Spotify. Ouvre-la dans ton navigateur pour autoriser Ada."""
    from mcps.spotify_mcp import SpotifyMCP
    sp = SpotifyMCP()
    url = sp.get_auth_url()
    if url.startswith("SPOTIFY"):
        raise HTTPException(status_code=503, detail=url)
    return {"auth_url": url, "message": "Ouvre cette URL dans ton navigateur pour autoriser Spotify."}


@app.get("/spotify/callback")
async def spotify_callback(code: str = "", error: str = ""):
    """Callback OAuth Spotify — échange le code contre un token et le met en cache."""
    if error:
        raise HTTPException(status_code=400, detail=f"Spotify a refusé l'autorisation : {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Paramètre 'code' manquant.")
    from mcps.spotify_mcp import SpotifyMCP
    sp = SpotifyMCP()
    ok = sp.handle_callback(code)
    if not ok:
        raise HTTPException(status_code=500, detail="Échange du token Spotify échoué.")
    return {"status": "ok", "message": "Spotify autorisé. Ada peut maintenant contrôler la lecture."}


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx", ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".csv", ".html", ".css"}

def parse_file(filename: str, content: bytes) -> str:
    """Extrait le texte d'un fichier selon son type."""
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        import pypdf, io
        reader = pypdf.PdfReader(io.BytesIO(content))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    elif ext == ".docx":
        import docx, io
        doc = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    else:
        return content.decode("utf-8", errors="replace")


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...), _: None = Security(require_token)):
    # ── 1. Sanitize filename — strip all path components ──────────────────────
    safe_filename = os.path.basename(file.filename or "")
    if not safe_filename or safe_filename.startswith('.'):
        raise HTTPException(400, "Nom de fichier invalide")

    ext = Path(safe_filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Type non supporté: {ext}. Supportés: {', '.join(SUPPORTED_EXTENSIONS)}")

    content = await file.read()

    from ada import memory as ada_memory
    original_path = ada_memory.documents_dir / safe_filename

    # ── 2. Defense-in-depth: confirm path stays inside documents_dir ──────────
    if not original_path.resolve().is_relative_to(ada_memory.documents_dir.resolve()):
        raise HTTPException(400, "Chemin non autorisé")

    original_path.write_bytes(content)

    try:
        text = parse_file(safe_filename, content)
    except Exception as e:
        raise HTTPException(500, f"Erreur parsing: {e}")

    if not text.strip():
        raise HTTPException(400, "Le fichier est vide ou le texte n'a pas pu être extrait.")

    chunks = ada_memory.ingest_document(safe_filename, text)
    return {"filename": safe_filename, "chunks": chunks, "status": "ok", "chars": len(text)}


@app.get("/documents")
async def list_documents(_: None = Security(require_token)):
    from ada import memory as ada_memory
    return {"documents": ada_memory.list_documents()}


@app.delete("/documents/{filename}")
async def delete_document(filename: str, _: None = Security(require_token)):
    # ── Sanitize filename ─────────────────────────────────────────────────────
    safe_filename = os.path.basename(filename)
    if not safe_filename:
        raise HTTPException(400, "Nom de fichier invalide")

    from ada import memory as ada_memory
    original_path = ada_memory.documents_dir / safe_filename

    if not original_path.resolve().is_relative_to(ada_memory.documents_dir.resolve()):
        raise HTTPException(400, "Chemin non autorisé")

    ada_memory.delete_document(safe_filename)
    if original_path.exists():
        original_path.unlink()
    return {"status": "ok"}

@sio.on("get_chromecast_status")
async def on_get_chromecast_status(sid, data=None):
    """Retourne l'état du Chromecast au frontend."""
    if not cast_agent._initialized:
        await cast_agent.initialize()
    status = await cast_agent.get_status()
    await sio.emit("chromecast_status", {"status": status}, room=sid)

@sio.event
async def connect(sid, environ):
    print(f"Client connected: {sid}")
    await sio.emit('status', {'msg': 'Connected to A.D.A Backend'}, room=sid)
    # Ré-émettre le health report au nouveau client
    if _health_report:
        await sio.emit('health_report', _health_report, room=sid)

    global authenticator
    
    # Callback for Auth Status
    async def on_auth_status(is_auth):
        print(f"[SERVER] Auth status change: {is_auth}")
        await sio.emit('auth_status', {'authenticated': is_auth})

    # Callback for Auth Camera Frames
    async def on_auth_frame(frame_b64):
        await sio.emit('auth_frame', {'image': frame_b64})

    # Initialize Authenticator if not already done
    if authenticator is None:
        authenticator = FaceAuthenticator(
            reference_image_path="reference.jpg",
            on_status_change=on_auth_status,
            on_frame=on_auth_frame
        )
    
    # Check if already authenticated or needs to start
    if authenticator.authenticated:
        await sio.emit('auth_status', {'authenticated': True})
    else:
        # Check Settings for Auth
        if SETTINGS.get("face_auth_enabled", False):
            await sio.emit('auth_status', {'authenticated': False})
            # Start the auth loop in background
            asyncio.create_task(authenticator.start_authentication_loop())
        else:
            # Bypass Auth
            print("Face Auth Disabled. Auto-authenticating.")
            # We don't change authenticator state to true to avoid confusion if re-enabled? 
            # Or we should just tell client it's auth'd.
            await sio.emit('auth_status', {'authenticated': True})

@sio.event
async def disconnect(sid):
    print(f"Client disconnected: {sid}")

@sio.event
async def start_audio(sid, data=None):
    global audio_loop, loop_task
    
    # Optional: Block if not authenticated
    # Only block if auth is ENABLED and not authenticated
    if SETTINGS.get("face_auth_enabled", False):
        if authenticator and not authenticator.authenticated:
            print("Blocked start_audio: Not authenticated.")
            await sio.emit('error', {'msg': 'Authentication Required'})
            return

    print("Starting Audio Loop...")
    
    device_index = None
    device_name = None
    if data:
        if 'device_index' in data:
            device_index = data['device_index']
        if 'device_name' in data:
            device_name = data['device_name']
            
    print(f"Using input device: Name='{device_name}', Index={device_index}")
    
    if audio_loop:
        if loop_task and (loop_task.done() or loop_task.cancelled()):
             print("Audio loop task appeared finished/cancelled. Clearing and restarting...")
             audio_loop = None
             loop_task = None
        else:
             print("Audio loop already running. Re-connecting client to session.")
             await sio.emit('status', {'msg': 'A.D.A Already Running'})
             return


    # Callback to send audio data to frontend (visualizer only)
    # Throttled to ~10Hz and downsampled to 64 values to avoid hammering the event loop
    _viz_counter = [0]
    def on_audio_data(data_bytes):
        _viz_counter[0] += 1
        if _viz_counter[0] % 2 != 0:  # emit every 2nd chunk ≈ 11Hz
            return
        arr = np.frombuffer(data_bytes, dtype=np.int16).astype(np.int32)
        n = len(arr)
        if n < 64:
            return
        trimmed = arr[:n - n % 64]
        viz = (np.max(np.abs(trimmed.reshape(64, -1)), axis=1) >> 7).clip(0, 255).tolist()
        asyncio.create_task(sio.emit('audio_data', {'data': viz}))

    # Callback to send raw PCM to browser for playback via Web Audio API.
    # This lets the browser's echoCancellation know what's playing → proper AEC.
    def on_audio_pcm(data_bytes):
        asyncio.create_task(sio.emit('audio_pcm', data_bytes))

    # Callback to send CAL data to frontend
    def on_cad_data(data):
        info = f"{len(data.get('vertices', []))} vertices" if 'vertices' in data else f"{len(data.get('data', ''))} bytes (STL)"
        print(f"Sending CAD data to frontend: {info}")
        asyncio.create_task(sio.emit('cad_data', data))

    # Callback to send Browser data to frontend
    def on_web_data(data):
        print(f"Sending Browser data to frontend: {len(data.get('log', ''))} chars logs")
        asyncio.create_task(sio.emit('browser_frame', data))
        
    # Callback to send Transcription data to frontend
    def on_transcription(data):
        # data = {"sender": "User"|"ADA", "text": "..."}
        asyncio.create_task(sio.emit('transcription', data))

    # Callback to send Confirmation Request to frontend
    def on_tool_confirmation(data):
        # data = {"id": "uuid", "tool": "tool_name", "args": {...}}
        print(f"Requesting confirmation for tool: {data.get('tool')}")
        asyncio.create_task(sio.emit('tool_confirmation_request', data))

    # Callback to send CAD status to frontend
    def on_cad_status(status):
        # status can be: 
        # - a string like "generating" (from ada.py handle_cad_request)
        # - a dict with {status, attempt, max_attempts, error} (from CadAgent)
        if isinstance(status, dict):
            print(f"Sending CAD Status: {status.get('status')} (attempt {status.get('attempt')}/{status.get('max_attempts')})")
            asyncio.create_task(sio.emit('cad_status', status))
        else:
            # Legacy: simple string
            print(f"Sending CAD Status: {status}")
            asyncio.create_task(sio.emit('cad_status', {'status': status}))

    # Callback to send CAD thoughts to frontend (streaming)
    def on_cad_thought(thought_text):
        asyncio.create_task(sio.emit('cad_thought', {'text': thought_text}))

    # Callback to send Project Update to frontend
    def on_project_update(project_name):
        print(f"Sending Project Update: {project_name}")
        asyncio.create_task(sio.emit('project_update', {'project': project_name}))

    # Callback to send Device Update to frontend
    def on_device_update(devices):
        # devices is a list of dicts
        print(f"Sending Kasa Device Update: {len(devices)} devices")
        asyncio.create_task(sio.emit('kasa_devices', devices))

    # Callback to send Terminal output to frontend
    def on_terminal_output(data):
        # data = {"command": str, "output": str}
        asyncio.create_task(sio.emit('terminal_output', data))

    # Callback to send Error to frontend
    def on_error(msg):
        print(f"Sending Error to frontend: {msg}")
        asyncio.create_task(sio.emit('error', {'msg': msg}))

    # Initialize ADA
    try:
        print(f"Initializing AudioLoop with device_index={device_index}")
        audio_loop = ada.AudioLoop(
            video_mode="none",
            on_audio_data=on_audio_data,
            on_audio_pcm=on_audio_pcm,
            on_cad_data=on_cad_data,
            on_web_data=on_web_data,
            on_transcription=on_transcription,
            on_tool_confirmation=on_tool_confirmation,
            on_cad_status=on_cad_status,
            on_cad_thought=on_cad_thought,
            on_project_update=on_project_update,
            on_device_update=on_device_update,
            on_terminal_output=on_terminal_output,
            on_error=on_error,

            input_device_index=device_index,
            input_device_name=device_name,
            tuya_agent=tuya_agent
        )
        print("AudioLoop initialized successfully.")

        # Partager l'AudioLoop avec le bridge Telegram/WhatsApp (capacités complètes)
        external_bridge.set_ada_loop(audio_loop)

        # Full browser audio mode: mic captured + Ada played in Electron → browser AEC works
        audio_loop.frontend_audio_mode = True
        audio_loop.browser_audio_mode = True
        audio_loop.on_clear_audio = lambda: asyncio.create_task(sio.emit('clear_audio'))
        audio_loop.on_sleep_mode_changed = lambda sleeping: asyncio.create_task(sio.emit('sleep_mode', {'sleeping': sleeping}))
        print("[SERVER] Browser audio mode enabled (mic + playback via Web Audio API, AEC active).")

        # Apply current permissions
        audio_loop.update_permissions(SETTINGS["tool_permissions"])
        
        # Check initial mute state
        if data and data.get('muted', False):
            print("Starting with Audio Paused")
            audio_loop.set_paused(True)

        print("Creating asyncio task for AudioLoop.run()")
        loop_task = asyncio.create_task(audio_loop.run())
        
        # Add a done callback to catch silent failures in the loop
        def handle_loop_exit(task):
            try:
                task.result()
            except asyncio.CancelledError:
                print("Audio Loop Cancelled")
            except Exception as e:
                print(f"Audio Loop Crashed: {e}")
                # You could emit 'error' here if you have context
        
        loop_task.add_done_callback(handle_loop_exit)
        
        print("Emitting 'A.D.A Started'")
        await sio.emit('status', {'msg': 'A.D.A Started'})

        # Load saved printers
        saved_printers = SETTINGS.get("printers", [])
        if saved_printers and audio_loop.printer_agent:
            print(f"[SERVER] Loading {len(saved_printers)} saved printers...")
            for p in saved_printers:
                audio_loop.printer_agent.add_printer_manually(
                    name=p.get("name", p["host"]),
                    host=p["host"],
                    port=p.get("port", 80),
                    printer_type=p.get("type", "moonraker"),
                    camera_url=p.get("camera_url")
                )
        
        # Start Printer Monitor
        asyncio.create_task(monitor_printers_loop())
        
    except Exception as e:
        print(f"CRITICAL ERROR STARTING ADA: {e}")
        import traceback
        traceback.print_exc()
        await sio.emit('error', {'msg': f"Failed to start: {str(e)}"})
        audio_loop = None # Ensure we can try again


async def monitor_printers_loop():
    """Background task to query printer status periodically."""
    print("[SERVER] Starting Printer Monitor Loop")
    while audio_loop and audio_loop.printer_agent:
        try:
            agent = audio_loop.printer_agent
            if not agent.printers:
                await asyncio.sleep(5)
                continue
                
            tasks = []
            for host, printer in agent.printers.items():
                if printer.printer_type.value != "unknown":
                    tasks.append(agent.get_print_status(host))
            
            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Exception):
                        pass # Ignore errors for now
                    elif res:
                        # res is PrintStatus object
                        await sio.emit('print_status_update', res.to_dict())
                        
        except asyncio.CancelledError:
            print("[SERVER] Printer Monitor Cancelled")
            break
        except Exception as e:
            print(f"[SERVER] Monitor Loop Error: {e}")
            
        await asyncio.sleep(2) # Update every 2 seconds for responsiveness

@sio.event
async def mic_audio_chunk(sid, data):
    """Receives PCM16 audio chunk from Electron frontend (echoCancellation applied).
    Forwards to Gemini via AudioLoop."""
    if audio_loop and audio_loop.frontend_audio_mode:
        raw = data.get('data')
        if raw:
            await audio_loop.receive_frontend_audio(bytes(raw))

@sio.event
async def stop_audio(sid):
    global audio_loop
    if audio_loop:
        audio_loop.stop()
        print("Stopping Audio Loop")
        audio_loop = None
        await sio.emit('status', {'msg': 'A.D.A Stopped'})

@sio.event
async def pause_audio(sid):
    global audio_loop
    if audio_loop:
        audio_loop.set_paused(True)
        print("Pausing Audio")
        await sio.emit('status', {'msg': 'Audio Paused'})

@sio.event
async def resume_audio(sid):
    global audio_loop
    if audio_loop:
        audio_loop.set_paused(False)
        print("Resuming Audio")
        await sio.emit('status', {'msg': 'Audio Resumed'})

@sio.event
async def confirm_tool(sid, data):
    # data: { "id": "...", "confirmed": True/False }
    request_id = data.get('id')
    confirmed = data.get('confirmed', False)
    
    print(f"[SERVER DEBUG] Received confirmation response for {request_id}: {confirmed}")
    
    if audio_loop:
        audio_loop.resolve_tool_confirmation(request_id, confirmed)
    else:
        print("Audio loop not active, cannot resolve confirmation.")

@sio.event
async def shutdown(sid, data=None):
    """Gracefully shutdown the server when the application closes."""
    global audio_loop, loop_task, authenticator
    
    print("[SERVER] ========================================")
    print("[SERVER] SHUTDOWN SIGNAL RECEIVED FROM FRONTEND")
    print("[SERVER] ========================================")
    
    # Stop audio loop
    if audio_loop:
        print("[SERVER] Stopping Audio Loop...")
        audio_loop.stop()
        audio_loop = None
    
    # Cancel the loop task if running
    if loop_task and not loop_task.done():
        print("[SERVER] Cancelling loop task...")
        loop_task.cancel()
        loop_task = None
    
    # Stop authenticator if running
    if authenticator:
        print("[SERVER] Stopping Authenticator...")
        authenticator.stop()
    
    print("[SERVER] Graceful shutdown complete. Terminating process...")
    
    # Force exit immediately - os._exit bypasses cleanup but ensures termination
    os._exit(0)

@sio.event
async def user_input(sid, data):
    text = data.get('text')
    print(f"[SERVER DEBUG] User input received: '{text}'")
    
    if not audio_loop:
        print("[SERVER DEBUG] [Error] Audio loop is None. Cannot send text.")
        return

    if not audio_loop.session:
        print("[SERVER DEBUG] [Error] Session is None. Cannot send text.")
        return

    if text:
        print(f"[SERVER DEBUG] Sending message to model: '{text}'")
        
        # Log User Input to Project History
        if audio_loop and audio_loop.project_manager:
            audio_loop.project_manager.log_chat("User", text)
            
        # Use the same 'send' method that worked for audio, as 'send_realtime_input' and 'send_client_content' seem unstable in this env
        # INJECT VIDEO FRAME IF AVAILABLE (VAD-style logic for Text Input)
        if audio_loop and audio_loop._latest_image_payload:
            print(f"[SERVER DEBUG] Piggybacking video frame with text input.")
            try:
                # Send frame first
                await audio_loop.session.send(input=audio_loop._latest_image_payload, end_of_turn=False)
            except Exception as e:
                print(f"[SERVER DEBUG] Failed to send piggyback frame: {e}")
                
        await audio_loop.session.send(input=text, end_of_turn=True)
        print(f"[SERVER DEBUG] Message sent to model successfully.")

import json
from datetime import datetime
from pathlib import Path

# ... (imports)

@sio.event
async def video_frame(sid, data):
    # data should contain 'image' which is binary (blob) or base64 encoded
    image_data = data.get('image')
    if image_data and audio_loop:
        # We don't await this because we don't want to block the socket handler
        # But send_frame is async, so we create a task
        asyncio.create_task(audio_loop.send_frame(image_data))

@sio.event
async def save_memory(sid, data):
    try:
        messages = data.get('messages', [])
        if not messages:
            print("No messages to save.")
            return

        # Ensure directory exists
        memory_dir = Path("long_term_memory")
        memory_dir.mkdir(exist_ok=True)

        # Generate filename
        # Use provided filename if available, else timestamp
        provided_name = data.get('filename')
        
        if provided_name:
            # Simple sanitization
            if not provided_name.endswith('.txt'):
                provided_name += '.txt'
            # Prevent directory traversal
            filename = memory_dir / Path(provided_name).name 
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = memory_dir / f"memory_{timestamp}.txt"

        # Write to file
        with open(filename, 'w', encoding='utf-8') as f:
            for msg in messages:
                sender = msg.get('sender', 'Unknown')
                text = msg.get('text', '')
                f.write(f"{sender}: {text}\n")
        print(f"Conversation saved to {filename}")
        await sio.emit('status', {'msg': 'Memory Saved Successfully'})

    except Exception as e:
        print(f"Error saving memory: {e}")
        await sio.emit('error', {'msg': f"Failed to save memory: {str(e)}"})

@sio.event
async def upload_memory(sid, data):
    print(f"Received memory upload request")
    try:
        memory_text = data.get('memory', '')
        if not memory_text:
            print("No memory data provided.")
            return

        if not audio_loop:
             print("[SERVER DEBUG] [Error] Audio loop is None. Cannot load memory.")
             await sio.emit('error', {'msg': "System not ready (Audio Loop inactive)"})
             return
        
        if not audio_loop.session:
             print("[SERVER DEBUG] [Error] Session is None. Cannot load memory.")
             await sio.emit('error', {'msg': "System not ready (No active session)"})
             return

        # Send to model
        print("Sending memory context to model...")
        context_msg = f"System Notification: The user has uploaded a long-term memory file. Please load the following context into your understanding. The format is a text log of previous conversations:\n\n{memory_text}"
        
        await audio_loop.session.send(input=context_msg, end_of_turn=True)
        print("Memory context sent successfully.")
        await sio.emit('status', {'msg': 'Memory Loaded into Context'})

    except Exception as e:
        print(f"Error uploading memory: {e}")
        await sio.emit('error', {'msg': f"Failed to upload memory: {str(e)}"})

@sio.event
async def discover_kasa(sid):
    print(f"Received discover_kasa request")
    try:
        devices = await tuya_agent.discover_devices()
        await sio.emit('kasa_devices', devices)
        await sio.emit('status', {'msg': f"Found {len(devices)} Tuya devices"})

        # Save to settings
        saved_devices = []
        for d in devices:
            saved_devices.append({
                "ip": d["ip"],
                "alias": d["alias"],
                "model": d["model"]
            })

        SETTINGS["tuya_devices"] = saved_devices
        save_settings()
        print(f"[SERVER] Saved {len(saved_devices)} Tuya devices to settings.")

    except Exception as e:
        print(f"Error discovering Tuya devices: {e}")
        await sio.emit('error', {'msg': f"Tuya Discovery Failed: {str(e)}"})

@sio.event
async def iterate_cad(sid, data):
    # data: { prompt: "make it bigger" }
    prompt = data.get('prompt')
    print(f"Received iterate_cad request: '{prompt}'")
    
    if not audio_loop or not audio_loop.cad_agent:
        await sio.emit('error', {'msg': "CAD Agent not available"})
        return

    try:
        # Notify user work has started
        await sio.emit('status', {'msg': 'Iterating design...'})
        await sio.emit('cad_status', {'status': 'generating'})
        
        # Call the agent with project path
        cad_output_dir = str(audio_loop.project_manager.get_current_project_path() / "cad")
        result = await audio_loop.cad_agent.iterate_prototype(prompt, output_dir=cad_output_dir)
        
        if result:
            info = f"{len(result.get('data', ''))} bytes (STL)"
            print(f"Sending updated CAD data: {info}")
            await sio.emit('cad_data', result)
            # Save to Project
            if 'file_path' in result:
                saved_path = audio_loop.project_manager.save_cad_artifact(result['file_path'], prompt)
                if saved_path:
                    print(f"[SERVER] Saved iterated CAD to {saved_path}")

            await sio.emit('status', {'msg': 'Design updated'})
        else:
            await sio.emit('error', {'msg': 'Failed to update design'})
            
    except Exception as e:
        print(f"Error iterating CAD: {e}")
        await sio.emit('error', {'msg': f"Iteration Error: {str(e)}"})

@sio.event
async def generate_cad(sid, data):
    # data: { prompt: "make a cube" }
    prompt = data.get('prompt')
    print(f"Received generate_cad request: '{prompt}'")
    
    if not audio_loop or not audio_loop.cad_agent:
        await sio.emit('error', {'msg': "CAD Agent not available"})
        return

    try:
        await sio.emit('status', {'msg': 'Generating new design...'})
        await sio.emit('cad_status', {'status': 'generating'})
        
        # Use generate_prototype based on prompt with project path
        cad_output_dir = str(audio_loop.project_manager.get_current_project_path() / "cad")
        result = await audio_loop.cad_agent.generate_prototype(prompt, output_dir=cad_output_dir)
        
        if result:
            info = f"{len(result.get('data', ''))} bytes (STL)"
            print(f"Sending newly generated CAD data: {info}")
            await sio.emit('cad_data', result)


            # Save to Project
            if 'file_path' in result:
                saved_path = audio_loop.project_manager.save_cad_artifact(result['file_path'], prompt)
                if saved_path:
                    print(f"[SERVER] Saved generated CAD to {saved_path}")

            await sio.emit('status', {'msg': 'Design generated'})
        else:
            await sio.emit('error', {'msg': 'Failed to generate design'})
            
    except Exception as e:
        print(f"Error generating CAD: {e}")
        await sio.emit('error', {'msg': f"Generation Error: {str(e)}"})

@sio.event
async def prompt_web_agent(sid, data):
    prompt = data.get('prompt', '').strip()
    if not prompt:
        return
    print(f"[WEB AGENT] Received prompt: '{prompt}'")
    await sio.emit('status', {'msg': 'Web Agent running...'}, to=sid)

    async def update_callback(image_b64, log_text):
        payload = {'log': log_text}
        if image_b64:
            payload['image'] = image_b64
        await sio.emit('browser_frame', payload, to=sid)

    async def run():
        try:
            # Prefer audio_loop's agent if a session is active (shares context)
            agent = audio_loop.web_agent if (audio_loop and audio_loop.web_agent) else standalone_web_agent
            await agent.run_task(prompt, update_callback=update_callback)
        except Exception as e:
            print(f"[WEB AGENT] Error: {e}")
            await sio.emit('error', {'msg': f"Web Agent Error: {str(e)}"}, to=sid)

    asyncio.create_task(run())

@sio.event
async def discover_printers(sid):
    print("Received discover_printers request")
    
    # If audio_loop isn't ready yet, return saved printers from settings
    if not audio_loop or not audio_loop.printer_agent:
        saved_printers = SETTINGS.get("printers", [])
        if saved_printers:
            # Convert saved printers to the expected format
            printer_list = []
            for p in saved_printers:
                printer_list.append({
                    "name": p.get("name", p["host"]),
                    "host": p["host"],
                    "port": p.get("port", 80),
                    "printer_type": p.get("type", "unknown"),
                    "camera_url": p.get("camera_url")
                })
            print(f"[SERVER] Returning {len(printer_list)} saved printers (audio_loop not ready)")
            await sio.emit('printer_list', printer_list)
            return
        else:
            await sio.emit('printer_list', [])
            await sio.emit('status', {'msg': "Connect to A.D.A to enable printer discovery"})
            return
        
    try:
        printers = await audio_loop.printer_agent.discover_printers()
        await sio.emit('printer_list', printers)
        await sio.emit('status', {'msg': f"Found {len(printers)} printers"})
    except Exception as e:
        print(f"Error discovering printers: {e}")
        await sio.emit('error', {'msg': f"Printer Discovery Failed: {str(e)}"})

@sio.event
async def add_printer(sid, data):
    # data: { host: "192.168.1.50", name: "My Printer", type: "moonraker" }
    raw_host = data.get('host')
    name = data.get('name') or raw_host
    ptype = data.get('type', "moonraker")
    
    # Parse port if present
    if ":" in raw_host:
        host, port_str = raw_host.split(":")
        port = int(port_str)
    else:
        host = raw_host
        port = 80
    
    print(f"Received add_printer request: {host}:{port} ({ptype})")
    
    if not audio_loop or not audio_loop.printer_agent:
        await sio.emit('error', {'msg': "Printer Agent not available"})
        return
        
    try:
        # Add manually
        camera_url = data.get('camera_url')
        printer = audio_loop.printer_agent.add_printer_manually(name, host, port=port, printer_type=ptype, camera_url=camera_url)
        
        # Save to settings
        new_printer_config = {
            "name": name,
            "host": host,
            "port": port,
            "type": ptype,
            "camera_url": camera_url
        }
        
        # Check if already exists to avoid duplicates
        exists = False
        for p in SETTINGS.get("printers", []):
            if p["host"] == host and p["port"] == port:
                exists = True
                break
        
        if not exists:
            if "printers" not in SETTINGS:
                SETTINGS["printers"] = []
            SETTINGS["printers"].append(new_printer_config)
            save_settings()
            print(f"[SERVER] Saved printer {name} to settings.")
        
        # Probe to confirm/correct type
        print(f"Probing {host} to confirm type...")
        # Try port 7125 (Moonraker) and 4408 (Fluidd/K1) 
        ports_to_try = [80, 7125, 4408]
        
        actual_type = "unknown"
        for port in ports_to_try:
             found_type = await audio_loop.printer_agent._probe_printer_type(host, port)
             if found_type.value != "unknown":
                 actual_type = found_type
                 # Update port if different
                 if port != 80:
                     printer.port = port
                 break
        
        if actual_type != "unknown" and actual_type != printer.printer_type:
             printer.printer_type = actual_type
             print(f"Corrected type to {actual_type.value} on port {printer.port}")
             
        # Refresh list for everyone
        printers = [p.to_dict() for p in audio_loop.printer_agent.printers.values()]
        await sio.emit('printer_list', printers)
        await sio.emit('status', {'msg': f"Added printer: {name}"})
        
    except Exception as e:
        print(f"Error adding printer: {e}")
        await sio.emit('error', {'msg': f"Failed to add printer: {str(e)}"})

@sio.event
async def print_stl(sid, data):
    print(f"Received print_stl request: {data}")
    # data: { stl_path: "path/to.stl" | "current", printer: "name_or_ip", profile: "optional" }
    
    if not audio_loop or not audio_loop.printer_agent:
        await sio.emit('error', {'msg': "Printer Agent not available"})
        return
        
    try:
        stl_path = data.get('stl_path', 'current')
        printer_name = data.get('printer')
        profile = data.get('profile')
        
        if not printer_name:
             await sio.emit('error', {'msg': "No printer specified"})
             return
             
        await sio.emit('status', {'msg': f"Preparing print for {printer_name}..."})
        
        # Get current project path for resolution
        current_project_path = None
        if audio_loop and audio_loop.project_manager:
            current_project_path = str(audio_loop.project_manager.get_current_project_path())
            print(f"[SERVER DEBUG] Using project path: {current_project_path}")

        # Resolve STL path before slicing so we can preview it
        resolved_stl = audio_loop.printer_agent._resolve_file_path(stl_path, current_project_path)
        
        if resolved_stl and os.path.exists(resolved_stl):
            # Open the STL in the CAD module for preview
            try:
                import base64
                with open(resolved_stl, 'rb') as f:
                    stl_data = f.read()
                stl_b64 = base64.b64encode(stl_data).decode('utf-8')
                stl_filename = os.path.basename(resolved_stl)
                
                print(f"[SERVER] Opening STL in CAD module: {stl_filename}")
                await sio.emit('cad_data', {
                    'format': 'stl',
                    'data': stl_b64,
                    'filename': stl_filename
                })
            except Exception as e:
                print(f"[SERVER] Warning: Could not preview STL: {e}")
        
        # Progress Callback
        async def on_slicing_progress(percent, message):
            await sio.emit('slicing_progress', {
                'printer': printer_name,
                'percent': percent,
                'message': message
            })
            if percent < 100:
                 await sio.emit('status', {'msg': f"Slicing: {percent}%"})

        result = await audio_loop.printer_agent.print_stl(
            stl_path, 
            printer_name, 
            profile,
            progress_callback=on_slicing_progress,
            root_path=current_project_path
        )
        
        await sio.emit('print_result', result)
        await sio.emit('status', {'msg': f"Print Job: {result.get('status', 'unknown')}"})
        
    except Exception as e:
        print(f"Error printing STL: {e}")
        await sio.emit('error', {'msg': f"Print Failed: {str(e)}"})

@sio.event
async def get_slicer_profiles(sid):
    """Get available OrcaSlicer profiles for manual selection."""
    print("Received get_slicer_profiles request")
    if not audio_loop or not audio_loop.printer_agent:
        await sio.emit('error', {'msg': "Printer Agent not available"})
        return
    
    try:
        profiles = audio_loop.printer_agent.get_available_profiles()
        await sio.emit('slicer_profiles', profiles)
    except Exception as e:
        print(f"Error getting slicer profiles: {e}")
        await sio.emit('error', {'msg': f"Failed to get profiles: {str(e)}"})

@sio.event
async def control_kasa(sid, data):
    # data: { ip, action: "on"|"off"|"brightness"|"color", value: ... }
    ip = data.get('ip')
    action = data.get('action')
    print(f"Kasa Control: {ip} -> {action}")
    
    try:
        success = False
        if action == "on":
            success = await tuya_agent.turn_on(ip)
        elif action == "off":
            success = await tuya_agent.turn_off(ip)
        elif action == "brightness":
            val = data.get('value')
            success = await tuya_agent.set_brightness(ip, val)
        elif action == "color":
            # value is {h, s, v} - convert to tuple for set_color
            h = data.get('value', {}).get('h', 0)
            s = data.get('value', {}).get('s', 100)
            v = data.get('value', {}).get('v', 100)
            success = await tuya_agent.set_color(ip, (h, s, v))

        if success:
            await sio.emit('kasa_update', {
                'ip': ip,
                'is_on': True if action == "on" else (False if action == "off" else None),
                'brightness': data.get('value') if action == "brightness" else None,
            })

        else:
            await sio.emit('error', {'msg': f"Failed to control device {ip}"})

    except Exception as e:
        print(f"Error controlling Tuya device: {e}")
        await sio.emit('error', {'msg': f"Tuya Control Error: {str(e)}"})

@sio.event
async def get_settings(sid):
    await sio.emit('settings', SETTINGS)

@sio.event
async def update_settings(sid, data):
    # Generic update
    print(f"Updating settings: {data}")
    
    # Handle specific keys if needed
    if "tool_permissions" in data:
        SETTINGS["tool_permissions"].update(data["tool_permissions"])
        if audio_loop:
            audio_loop.update_permissions(SETTINGS["tool_permissions"])
            
    if "face_auth_enabled" in data:
        SETTINGS["face_auth_enabled"] = data["face_auth_enabled"]
        # If turned OFF, maybe emit auth status true?
        if not data["face_auth_enabled"]:
             await sio.emit('auth_status', {'authenticated': True})
             # Stop auth loop if running?
             if authenticator:
                 authenticator.stop() 

    if "camera_flipped" in data:
        SETTINGS["camera_flipped"] = data["camera_flipped"]
        print(f"[SERVER] Camera flip set to: {data['camera_flipped']}")

    # Generic fallback: persist any other scalar/string keys not handled above
    _handled = {"tool_permissions", "face_auth_enabled", "camera_flipped"}
    for key, value in data.items():
        if key not in _handled:
            SETTINGS[key] = value

    save_settings()
    # Broadcast new full settings
    await sio.emit('settings', SETTINGS)

@sio.event
async def set_vision_mode(sid, data):
    """Switch Ada's vision mode: 'none' | 'camera' | 'screen'"""
    mode = data.get("mode", "none")
    print(f"[SERVER] Vision mode change requested: '{mode}'")
    if audio_loop:
        audio_loop.set_video_mode(mode)
        await sio.emit('vision_mode', {'mode': mode})
    else:
        print("[SERVER] No audio_loop active — vision mode not changed.")


# Deprecated/Mapped for compatibility if frontend still uses specific events
@sio.event
async def get_tool_permissions(sid):
    await sio.emit('tool_permissions', SETTINGS["tool_permissions"])

@sio.event
async def update_tool_permissions(sid, data):
    print(f"Updating permissions (legacy event): {data}")
    SETTINGS["tool_permissions"].update(data)
    save_settings()
    
    if audio_loop:
        audio_loop.update_permissions(SETTINGS["tool_permissions"])
    # Broadcast update to all
    await sio.emit('tool_permissions', SETTINGS["tool_permissions"])

if __name__ == "__main__":
    uvicorn.run(
        "server:app_socketio", 
        host="127.0.0.1", 
        port=8000, 
        reload=False, # Reload enabled causes spawn of worker which might miss the event loop policy patch
        loop="asyncio",
        reload_excludes=["temp_cad_gen.py", "output.stl", "*.stl"]
    )
