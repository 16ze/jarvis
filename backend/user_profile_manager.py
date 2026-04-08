import json
import os
from datetime import datetime
from typing import Optional

JARVIS_ROOT = os.getenv("JARVIS_ROOT", "/Users/bryandev/jarvis")
USERS_DIR = os.path.join(JARVIS_ROOT, "backend", "memory", "users")
GUESTS_DIR = os.path.join(USERS_DIR, "guests")
OWNER_IDS = {"bryan", "rose"}


class UserProfileManager:
    def __init__(self):
        os.makedirs(USERS_DIR, exist_ok=True)
        os.makedirs(GUESTS_DIR, exist_ok=True)

    def _profile_path(self, user_id: str) -> str:
        if user_id in OWNER_IDS:
            return os.path.join(USERS_DIR, f"{user_id}.json")
        return os.path.join(GUESTS_DIR, f"{user_id}.json")

    def get_profile(self, user_id: str) -> Optional[dict]:
        path = self._profile_path(user_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_profile(self, profile: dict) -> None:
        path = self._profile_path(profile["id"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

    def save_preference(self, user_id: str, preference: str) -> str:
        profile = self.get_profile(user_id)
        if profile is None:
            return f"Profil inconnu : {user_id}"
        prefs = profile.setdefault("preferences", [])
        if preference not in prefs:
            prefs.append(preference)
            self.save_profile(profile)
        return f"Préférence enregistrée pour {profile['name']}."

    def save_fact(self, user_id: str, fact: str) -> str:
        profile = self.get_profile(user_id)
        if profile is None:
            return f"Profil inconnu : {user_id}"
        facts = profile.setdefault("facts", [])
        if fact not in facts:
            facts.append(fact)
            self.save_profile(profile)
        return f"Fait enregistré pour {profile['name']}."

    def create_guest(self, name: str) -> dict:
        guest_id = name.lower().strip()
        existing = self.get_profile(guest_id)
        if existing:
            existing["last_seen"] = datetime.utcnow().isoformat()
            self.save_profile(existing)
            return existing
        profile = {
            "id": guest_id,
            "name": name,
            "role": "guest",
            "preferences": [],
            "habits": [],
            "facts": [],
            "created_at": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
        }
        self.save_profile(profile)
        return profile

    def get_active_context(self, speakers: list[dict]) -> str:
        if not speakers:
            return ""
        lines = ["[UTILISATEURS ACTIFS]"]
        for s in speakers:
            profile = self.get_profile(s["user"])
            if not profile:
                continue
            source = s.get("source", "inconnu")
            confidence = s.get("confidence")
            location = s.get("location")
            prefs = ", ".join(profile.get("preferences", [])) or "aucune préférence enregistrée"
            desc = f"- {profile['name']} ({source}"
            if confidence:
                desc += f", confiance {int(confidence * 100)}%"
            if location:
                desc += f", vu en {location}"
            desc += f") — préférences : {prefs}"
            lines.append(desc)
        if len(speakers) >= 2:
            lines.append("→ Si les deux parlent en même temps : réponds à chacun explicitement.")
        return "\n".join(lines)
