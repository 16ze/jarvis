"""
Calibration live des expressions faciales locales via MediaPipe blendshapes.

Usage:
    conda run -n ada_v2 python backend/calibrate_face_expressions.py
    conda run -n ada_v2 python backend/calibrate_face_expressions.py --seconds 30 --no-window

Touches:
    q / ESC : quitter
"""

from __future__ import annotations

import os
import sys
import time
import argparse
from typing import Iterable

import cv2


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from authenticator import MultiUserFaceDetector


TOP_BLENDSHAPES = 6


def _top_scores(scores: dict[str, float], limit: int = TOP_BLENDSHAPES) -> list[tuple[str, float]]:
    return sorted(
        ((name, float(score)) for name, score in (scores or {}).items()),
        key=lambda item: item[1],
        reverse=True,
    )[:limit]


def _format_top_scores(pairs: Iterable[tuple[str, float]]) -> str:
    return " | ".join(f"{name}:{score:.2f}" for name, score in pairs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=30.0, help="Durée max de capture.")
    parser.add_argument("--no-window", action="store_true", help="N'ouvre pas de fenêtre OpenCV.")
    args = parser.parse_args()

    detector = MultiUserFaceDetector(camera_label="calibration")

    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print("[CALIB] Impossible d'ouvrir la webcam.")
        return 1

    print("[CALIB] Webcam ouverte. Fais défiler happy / sad / angry / tired / stressed.")
    print("[CALIB] Observe les logs terminal et l'overlay vidéo. Quitter: q ou ESC.")
    started_at = time.monotonic()

    try:
        while True:
            if args.seconds > 0 and (time.monotonic() - started_at) >= args.seconds:
                print("[CALIB] Durée max atteinte.")
                break
            ret, frame = cap.read()
            if not ret:
                print("[CALIB] Frame non lue.")
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            faces = detector._extract_faces(frame_rgb)

            if faces:
                face = max(faces, key=lambda item: float(item.get("emotion_confidence") or 0.0))
                emotion = str(face.get("human_emotion") or "unknown")
                confidence = float(face.get("emotion_confidence") or 0.0)
                scores = dict(face.get("blendshape_scores") or {})
                top_scores = _top_scores(scores)

                overlay_1 = f"emotion={emotion} conf={confidence:.2f}"
                overlay_2 = _format_top_scores(top_scores)
                print(f"[CALIB] {overlay_1} :: {overlay_2}")

                cv2.putText(
                    frame,
                    overlay_1,
                    (20, 32),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.75,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    frame,
                    overlay_2[:140],
                    (20, 64),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )
            else:
                print("[CALIB] aucun visage detecte")
                if not args.no_window:
                    cv2.putText(
                        frame,
                        "aucun visage detecte",
                        (20, 32),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.75,
                        (0, 140, 255),
                        2,
                        cv2.LINE_AA,
                    )

            if not args.no_window:
                cv2.imshow("Ada Face Expression Calibration", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
    finally:
        cap.release()
        if not args.no_window:
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
