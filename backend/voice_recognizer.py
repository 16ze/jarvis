import os
import threading
import numpy as np
from pathlib import Path
from typing import Optional
from resemblyzer import VoiceEncoder, preprocess_wav

JARVIS_ROOT = os.getenv("JARVIS_ROOT", "/Users/bryandev/jarvis")
VOICE_PRINTS_DIR = os.path.join(JARVIS_ROOT, "backend", "memory", "voice_prints")
GUESTS_VOICE_DIR = os.path.join(VOICE_PRINTS_DIR, "guests")
OWNER_IDS = {"bryan", "rose"}

CONFIDENCE_THRESHOLD = 0.75
SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # int16
ACCUMULATION_BYTES = SAMPLE_RATE * BYTES_PER_SAMPLE * 2  # 2s = 64000 bytes


class VoiceRecognizer:
    def __init__(self):
        os.makedirs(VOICE_PRINTS_DIR, exist_ok=True)
        os.makedirs(GUESTS_VOICE_DIR, exist_ok=True)
        self.encoder = VoiceEncoder()
        self._embeddings: dict[str, np.ndarray] = {}
        self._audio_buffer = bytearray()
        self._lock = threading.Lock()
        self._load_all_embeddings()

    def _print_path(self, user_id: str) -> str:
        if user_id in OWNER_IDS:
            return os.path.join(VOICE_PRINTS_DIR, f"{user_id}.npy")
        return os.path.join(GUESTS_VOICE_DIR, f"{user_id}.npy")

    def _load_all_embeddings(self) -> None:
        for path in Path(VOICE_PRINTS_DIR).glob("*.npy"):
            self._embeddings[path.stem] = np.load(str(path))
        for path in Path(GUESTS_VOICE_DIR).glob("*.npy"):
            self._embeddings[path.stem] = np.load(str(path))

    def enroll(self, user_id: str, audio_path: str) -> str:
        wav = preprocess_wav(Path(audio_path))
        embedding = self.encoder.embed_utterance(wav)
        np.save(self._print_path(user_id), embedding)
        self._embeddings[user_id] = embedding
        return f"Empreinte vocale enregistrée pour {user_id}."

    def enroll_from_array(self, user_id: str, audio_array: np.ndarray) -> str:
        wav = preprocess_wav(audio_array, source_sr=SAMPLE_RATE)
        embedding = self.encoder.embed_utterance(wav)
        np.save(self._print_path(user_id), embedding)
        self._embeddings[user_id] = embedding
        return f"Empreinte vocale enregistrée pour {user_id}."

    def identify(self, audio_array: np.ndarray) -> Optional[dict]:
        if not self._embeddings:
            return None
        if np.abs(audio_array).mean() < 0.01:
            return None
        try:
            wav = preprocess_wav(audio_array, source_sr=SAMPLE_RATE)
            embedding = self.encoder.embed_utterance(wav)
        except Exception:
            return None
        best_user, best_score = None, -1.0
        for user_id, ref in self._embeddings.items():
            score = float(np.inner(embedding, ref))
            if score > best_score:
                best_score, best_user = score, user_id
        if best_score >= CONFIDENCE_THRESHOLD:
            return {"user": best_user, "confidence": best_score}
        return None

    def feed_chunk(self, pcm_bytes: bytes) -> Optional[dict]:
        with self._lock:
            self._audio_buffer.extend(pcm_bytes)
            if len(self._audio_buffer) < ACCUMULATION_BYTES:
                return None
            chunk = bytes(self._audio_buffer[:ACCUMULATION_BYTES])
            self._audio_buffer = self._audio_buffer[ACCUMULATION_BYTES:]
        audio_array = (
            np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
        )
        return self.identify(audio_array)

    def reload_embeddings(self) -> None:
        self._embeddings.clear()
        self._load_all_embeddings()
