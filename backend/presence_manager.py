import asyncio
import os
from typing import Optional, Callable, Awaitable
from voice_recognizer import VoiceRecognizer
from user_profile_manager import UserProfileManager


class PresenceManager:
    def __init__(
        self,
        voice_recognizer: Optional[VoiceRecognizer] = None,
        profile_manager: Optional[UserProfileManager] = None,
    ):
        self.voice_recognizer = voice_recognizer if voice_recognizer is not None else VoiceRecognizer()
        self.profile_manager = profile_manager if profile_manager is not None else UserProfileManager()
        self._active_speakers: list[dict] = []
        self._audio_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._on_unknown_voice: Optional[Callable[[], Awaitable[None]]] = None

    @property
    def active_speakers(self) -> list[dict]:
        return list(self._active_speakers)

    def feed_audio_chunk(self, pcm_bytes: bytes) -> None:
        try:
            self._audio_queue.put_nowait(pcm_bytes)
        except asyncio.QueueFull:
            pass

    def update_face_detection(self, detections: list[dict]) -> None:
        voice_users = {s["user"] for s in self._active_speakers if s.get("source") == "voice"}
        face_only = [
            {**d, "source": "face"}
            for d in detections
            if d["user"] not in voice_users
        ]
        voice_speakers = [s for s in self._active_speakers if s.get("source") == "voice"]
        self._active_speakers = voice_speakers + face_only

    def get_context_block(self) -> str:
        return self.profile_manager.get_active_context(self._active_speakers)

    def set_unknown_voice_callback(self, callback: Callable[[], Awaitable[None]]) -> None:
        self._on_unknown_voice = callback

    async def run(self) -> None:
        while True:
            try:
                pcm_bytes = await asyncio.wait_for(self._audio_queue.get(), timeout=1.0)
                result = self.voice_recognizer.feed_chunk(pcm_bytes)
                if result:
                    await self._handle_voice_identification(result)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                raise
            except Exception as e:
                print(f"[PRESENCE] Erreur: {e}")

    async def _handle_voice_identification(self, result: dict) -> None:
        user_id = result["user"]
        profile = self.profile_manager.get_profile(user_id)

        if profile is None:
            if self._on_unknown_voice:
                asyncio.create_task(self._on_unknown_voice())
            return

        existing = next((s for s in self._active_speakers if s["user"] == user_id), None)
        if existing:
            existing["confidence"] = result["confidence"]
            existing["source"] = "voice"
        else:
            self._active_speakers.append({
                "user": user_id,
                "source": "voice",
                "confidence": result["confidence"],
                "location": None,
            })
