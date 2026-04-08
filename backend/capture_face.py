# backend/capture_face.py
"""
Capture une photo de référence pour un utilisateur.
Usage: conda run -n ada_v2 python backend/capture_face.py --user bryan
       conda run -n ada_v2 python backend/capture_face.py --user rose
"""
import cv2
import os
import argparse

JARVIS_ROOT = os.getenv("JARVIS_ROOT", "/Users/bryandev/jarvis")
FACE_REFS_DIR = os.path.join(JARVIS_ROOT, "backend", "memory", "face_refs")


def capture_reference_face(user_id: str) -> None:
    os.makedirs(FACE_REFS_DIR, exist_ok=True)
    output_path = os.path.join(FACE_REFS_DIR, f"{user_id}.jpg")

    cap = cv2.VideoCapture(0, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print(f"[CAPTURE] Erreur : impossible d'ouvrir la webcam.")
        return

    print(f"[CAPTURE] Capture pour '{user_id}'. Appuie sur 's' ou ESPACE pour sauvegarder, 'q'/ESC pour annuler.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[CAPTURE] Erreur : frame non lue.")
            break
        cv2.imshow(f"Capture — {user_id}", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("s"), 32):
            cv2.imwrite(output_path, frame)
            print(f"[CAPTURE] Photo sauvegardée : {output_path}")
            break
        if key in (ord("q"), 27):
            print("[CAPTURE] Annulé.")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", required=True, help="ID utilisateur : bryan, rose, ou prénom invité")
    args = parser.parse_args()
    capture_reference_face(args.user)
