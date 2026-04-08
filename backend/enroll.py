# backend/enroll.py
"""
Script one-shot d'enrollment vocal + photo pour un utilisateur.
Usage:
  conda run -n ada_v2 python backend/enroll.py --user bryan
  conda run -n ada_v2 python backend/enroll.py --user rose
  conda run -n ada_v2 python backend/enroll.py --user bryan --voice-only
  conda run -n ada_v2 python backend/enroll.py --user bryan --face-only
"""
import argparse
import os
import sys
import numpy as np
import pyaudio
import wave
import tempfile

JARVIS_ROOT = os.getenv("JARVIS_ROOT", "/Users/bryandev/jarvis")
BACKEND = os.path.join(JARVIS_ROOT, "backend")
sys.path.insert(0, BACKEND)

SAMPLE_RATE = 16000
DURATION_S = 25
CHUNK_SIZE = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1


def record_audio(user_id: str) -> str:
    print(f"\n[ENROLL] Enregistrement vocal pour '{user_id}'.")
    print(f"[ENROLL] Parle pendant {DURATION_S} secondes... (démarrage dans 2s)")
    import time
    time.sleep(2)
    print("[ENROLL] Enregistrement en cours...")

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=FORMAT, channels=CHANNELS, rate=SAMPLE_RATE,
        input=True, frames_per_buffer=CHUNK_SIZE
    )
    frames = []
    n_chunks = int(SAMPLE_RATE / CHUNK_SIZE * DURATION_S)
    for i in range(n_chunks):
        data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
        frames.append(data)
        if i % int(SAMPLE_RATE / CHUNK_SIZE) == 0:
            elapsed = i // int(SAMPLE_RATE / CHUNK_SIZE)
            print(f"  {elapsed}s / {DURATION_S}s...", end="\r")
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print(f"\n[ENROLL] Enregistrement terminé.")

    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(tmp.name, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pa.get_sample_size(FORMAT))
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(b"".join(frames))
    return tmp.name


def enroll_voice(user_id: str) -> None:
    from voice_recognizer import VoiceRecognizer
    audio_path = record_audio(user_id)
    vr = VoiceRecognizer()
    result = vr.enroll(user_id, audio_path)
    os.unlink(audio_path)
    print(f"[ENROLL] {result}")


def enroll_face(user_id: str) -> None:
    print(f"\n[ENROLL] Capture de la photo de référence pour '{user_id}'.")
    from capture_face import capture_reference_face
    capture_reference_face(user_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrollment vocal + photo pour Ada")
    parser.add_argument("--user", required=True, help="ID utilisateur : bryan ou rose")
    parser.add_argument("--voice-only", action="store_true")
    parser.add_argument("--face-only", action="store_true")
    args = parser.parse_args()

    if not args.face_only:
        enroll_voice(args.user)
    if not args.voice_only:
        enroll_face(args.user)
    print(f"\n[ENROLL] Enrollment terminé pour '{args.user}'.")
