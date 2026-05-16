"""
ScreenWatcher — Vision continue de l'écran en arrière-plan.

Fonctionnement :
  - Capture l'écran toutes les 2 secondes via screencapture (macOS native)
  - Analyse chaque frame avec Gemini Flash Lite (description courte)
  - Garde un buffer circulaire des 10 dernières descriptions
  - Répond INSTANTANÉMENT à "describe_screen" depuis le buffer
"""

import asyncio
import os
import subprocess
import tempfile
import time
from collections import deque
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"
INTERVAL_SEC = 2.0
BUFFER_SIZE = 10

_system_prompt = """Tu décris ce qui est visible à l'écran en FRANÇAIS.
Sois concis (1-2 phrases max).

Exemples :
- "Barre des tâches macOS, Finder ouvert avec le dossier Téléchargements"
- "Safari ouvert sur Google, barre de recherche visible, 3 onglets"
- "Terminal avec plusieurs onglets, curseur clignotant sur une commande"
- "Code VS avec fichier Python, panneau latéral Explorer ouvert"
- "Écran de connexion macOS, requête mot de passe"

Décris : les applications visibles, le contenu principal, l'état (actif, inactif)."""

_client = None
_tmp_file = "/tmp/ada_screen_watcher.jpg"


def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    return _client


def _capture_screen() -> Optional[bytes]:
    """Capture l'écran via screencapture macOS. Retourne les bytes JPEG ou None."""
    try:
        result = subprocess.run(
            ["screencapture", "-x", "-t", "jpg", _tmp_file],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0 and os.path.exists(_tmp_file):
            with open(_tmp_file, "rb") as f:
                return f.read()
    except Exception as e:
        print(f"[ScreenWatcher] Capture error: {e}")
    return None


class ScreenWatcher:
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._buffer: deque[str] = deque(maxlen=BUFFER_SIZE)
        self._last_frame: Optional[bytes] = None
        self._lock = asyncio.Lock()
        self._last_analysis: Optional[str] = None
        self._last_analysis_time: float = 0
        self._initialized = False

    async def start(self):
        """Démarre la capture d'écran en arrière-plan."""
        if self._running:
            return
        self._running = True
        self._initialized = True
        self._task = asyncio.create_task(self._capture_loop())
        print("[ScreenWatcher] Démarré — capture toutes les 2 secondes")

    async def stop(self):
        """Arrête la capture."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print("[ScreenWatcher] Arrêté")

    async def describe(self) -> str:
        """Retourne instantanément la description de l'écran actuel."""
        if not self._initialized:
            return "Vision continue non encore initialisée."

        if self._last_analysis and (time.time() - self._last_analysis_time) < 5:
            return self._last_analysis

        if self._buffer:
            return self._buffer[-1]

        if self._last_analysis:
            return self._last_analysis

        return "Je n'ai pas encore capturé d'image de l'écran."

    async def _capture_loop(self):
        """Boucle de capture — tourne en arrière-plan."""
        while self._running:
            try:
                jpeg_bytes = await asyncio.to_thread(_capture_screen)

                if jpeg_bytes:
                    async with self._lock:
                        self._last_frame = jpeg_bytes

                    asyncio.create_task(self._analyze_frame(jpeg_bytes))

            except Exception as e:
                print(f"[ScreenWatcher] Erreur capture : {e}")

            await asyncio.sleep(INTERVAL_SEC)

    async def _analyze_frame(self, frame_bytes: bytes):
        """Analyse un frame et met à jour le buffer."""
        try:
            client = _get_client()
            response = await client.aio.models.generate_content(
                model=MODEL,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_bytes(
                                data=frame_bytes, mime_type="image/jpeg"
                            )
                        ]
                    ),
                    _system_prompt,
                ],
            )
            desc = (response.text or "Écran visible.").strip()

            async with self._lock:
                self._buffer.append(desc)
                self._last_analysis = desc
                self._last_analysis_time = time.time()

        except Exception as e:
            print(f"[ScreenWatcher] Erreur analyse : {e}")

    @property
    def is_running(self) -> bool:
        return self._running
