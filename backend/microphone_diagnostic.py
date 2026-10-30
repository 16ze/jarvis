"""Diagnostic local du micro utilisé par Ada, sans envoyer ni conserver l'audio."""

from __future__ import annotations

import argparse
from array import array
import json
import math
import os
import sys
import time
from typing import Iterable


SAMPLE_RATE = 16_000
CHUNK_SIZE = 1_024


def pcm16_level(data: bytes) -> tuple[int, int]:
    """Retourne (RMS, pic) pour un bloc PCM16 mono little-endian."""
    usable = len(data) - (len(data) % 2)
    if usable <= 0:
        return 0, 0
    samples = array("h")
    samples.frombytes(data[:usable])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return 0, 0
    squares = sum(int(sample) * int(sample) for sample in samples)
    rms = int(math.sqrt(squares / len(samples)))
    peak = max(abs(int(sample)) for sample in samples)
    return rms, peak


def summarize_levels(
    rms_levels: Iterable[int],
    peaks: Iterable[int],
    vad_threshold: int,
) -> dict:
    """Évalue si le niveau capté franchit suffisamment le seuil local d'Ada."""
    levels = [max(0, int(level)) for level in rms_levels]
    peak_values = [max(0, int(peak)) for peak in peaks]
    threshold = max(1, int(vad_threshold))
    if not levels:
        return {
            "status": "no_audio",
            "message": "Aucun échantillon audio reçu.",
            "vad_threshold": threshold,
        }

    sorted_levels = sorted(levels)
    p95_index = min(len(sorted_levels) - 1, int(len(sorted_levels) * 0.95))
    active_chunks = sum(level >= threshold for level in levels)
    active_ratio = active_chunks / len(levels)
    max_peak = max(peak_values, default=0)
    p95_rms = sorted_levels[p95_index]

    if max_peak < 100:
        status = "silent"
        message = "Signal presque silencieux : vérifier le micro et son autorisation macOS."
    elif active_chunks == 0:
        status = "too_low"
        message = (
            "La voix ne franchit jamais le seuil VAD local. Choisir le bon micro "
            "ou réduire ADA_VAD_RMS_THRESHOLD."
        )
    elif active_ratio < 0.05:
        status = "intermittent"
        message = "Signal détecté mais trop intermittent pour une transcription fiable."
    else:
        status = "ok"
        message = "Niveau micro compatible avec le seuil auxiliaire d'Ada."

    return {
        "status": status,
        "message": message,
        "vad_threshold": threshold,
        "chunks": len(levels),
        "active_ratio": round(active_ratio, 3),
        "p95_rms": p95_rms,
        "max_rms": max(levels),
        "max_peak": max_peak,
        "clipping": max_peak >= 32_000,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mesure le micro Ada pendant quelques secondes sans sauvegarder l'audio."
    )
    parser.add_argument("--seconds", type=float, default=6.0)
    parser.add_argument("--device", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        import pyaudio
    except ImportError:
        print("PyAudio est absent. Active d'abord l'environnement conda ada_v2.")
        return 1

    threshold = max(1, int(os.getenv("ADA_VAD_RMS_THRESHOLD", "800")))
    audio = pyaudio.PyAudio()
    stream = None
    try:
        info = (
            audio.get_device_info_by_index(args.device)
            if args.device is not None
            else audio.get_default_input_device_info()
        )
        device_index = int(info["index"])
        print(f"Micro testé : {info.get('name', 'inconnu')} (index {device_index})")
        print("Parle normalement pendant le test : « Ada, peux-tu me comprendre ? »")
        stream = audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK_SIZE,
        )
        deadline = time.monotonic() + max(1.0, args.seconds)
        rms_levels = []
        peaks = []
        while time.monotonic() < deadline:
            block = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            rms, peak = pcm16_level(block)
            rms_levels.append(rms)
            peaks.append(peak)

        summary = summarize_levels(rms_levels, peaks, threshold)
        summary["device"] = info.get("name", "inconnu")
        summary["device_index"] = device_index
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["status"] == "ok" else 2
    except Exception as exc:
        print(f"Diagnostic micro impossible : {exc}")
        return 1
    finally:
        if stream is not None:
            stream.stop_stream()
            stream.close()
        audio.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
