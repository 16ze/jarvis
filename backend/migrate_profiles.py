# backend/migrate_profiles.py
"""
Script one-shot : migre procedural.json vers memory/users/
Crée bryan.json (avec préférences existantes) + rose.json (vide).
Lance avec : conda run -n ada_v2 python backend/migrate_profiles.py
"""
import json
import os
from datetime import datetime

JARVIS_ROOT = os.getenv("JARVIS_ROOT", "/Users/bryandev/jarvis")
BACKEND = os.path.join(JARVIS_ROOT, "backend")
PROCEDURAL = os.path.join(BACKEND, "memory", "procedural.json")
USERS_DIR = os.path.join(BACKEND, "memory", "users")

def migrate():
    os.makedirs(USERS_DIR, exist_ok=True)
    os.makedirs(os.path.join(USERS_DIR, "guests"), exist_ok=True)

    procedural = {}
    if os.path.exists(PROCEDURAL):
        with open(PROCEDURAL, "r", encoding="utf-8") as f:
            procedural = json.load(f)
        print(f"[MIGRATE] procedural.json chargé : {procedural}")
    else:
        print("[MIGRATE] procedural.json introuvable — Bryan créé avec profil vide.")

    bryan = {
        "id": "bryan",
        "name": "Bryan",
        "role": "owner",
        "preferences": procedural.get("preferences", []),
        "habits": procedural.get("habits", []),
        "goals": procedural.get("goals", []),
        "facts": [f for f in procedural.get("facts", [])
                  if "Bryan" in f or "Kairo" in f or "Ada" in f],
        "created_at": "2026-01-01T00:00:00",
    }
    rose = {
        "id": "rose",
        "name": "Rose",
        "role": "owner",
        "preferences": [],
        "habits": [],
        "goals": [],
        "facts": [],
        "created_at": datetime.utcnow().isoformat(),
    }

    for profile in [bryan, rose]:
        path = os.path.join(USERS_DIR, f"{profile['id']}.json")
        if os.path.exists(path):
            print(f"[MIGRATE] {path} existe déjà — ignoré.")
            continue
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"[MIGRATE] Créé : {path}")

    print("[MIGRATE] Terminé.")

if __name__ == "__main__":
    migrate()
