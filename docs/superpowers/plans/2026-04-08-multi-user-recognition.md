# Multi-User Recognition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ada identifie qui lui parle (voix via resemblyzer) et qui elle voit (visage via MediaPipe), charge les préférences personnalisées de Bryan / Rose / invités, et adapte ses réponses en conséquence.

**Architecture:** `voice_recognizer.py` accumule les chunks PCM du micro et identifie les locuteurs toutes les 2s. `MultiUserFaceDetector` (ajouté dans `authenticator.py`) tourne en parallèle dans `ada.py`. `presence_manager.py` fusionne les deux sources et maintient `active_speakers[]`. `user_profile_manager.py` gère les profils JSON persistants. Le bloc [UTILISATEURS ACTIFS] est injecté dans Gemini Live via `session.send()` au démarrage.

**Tech Stack:** resemblyzer (voice embeddings), MediaPipe (face landmarks), pyaudio (PCM 16kHz int16), asyncio, JSON profiles.

---

## File Map

| Action | Fichier | Responsabilité |
|---|---|---|
| Create | `backend/voice_recognizer.py` | Enrollment + identification voix (resemblyzer) |
| Create | `backend/presence_manager.py` | Fusion voix + visage → active_speakers[] |
| Create | `backend/user_profile_manager.py` | CRUD profils utilisateurs JSON |
| Create | `backend/enroll.py` | CLI one-shot d'enrollment (voix + photo) |
| Create | `backend/migrate_profiles.py` | Migration one-shot procedural.json → users/ |
| Modify | `backend/authenticator.py` | Ajouter MultiUserFaceDetector (ne pas toucher FaceAuthenticator) |
| Modify | `backend/capture_face.py` | Ajouter --user argument, sauver dans face_refs/ |
| Modify | `backend/ada.py` | Wire presence_manager + injection contexte |
| Modify | `backend/external_bridge.py` | Injection profil Bryan pour Telegram/WhatsApp |
| Modify | `backend/mcp_tools_declarations.py` | 3 nouveaux outils |
| Modify | `backend/settings.json` | Ajout cameras[] |
| Modify | `requirements.txt` | Ajouter resemblyzer |
| Create | `tests/test_user_profile_manager.py` | Tests CRUD profils |
| Create | `tests/test_voice_recognizer.py` | Tests similarity + feed_chunk |
| Create | `tests/test_presence_manager.py` | Tests fusion + contexte |

---

## Task 1: Dépendances + structure répertoires + settings.json

**Files:**
- Modify: `requirements.txt`
- Modify: `backend/settings.json`

- [ ] **Step 1: Ajouter resemblyzer dans requirements.txt**

Ajouter après la ligne `numpy` :
```
resemblyzer
```

- [ ] **Step 2: Créer la structure de répertoires**

```bash
mkdir -p backend/memory/users/guests
mkdir -p backend/memory/voice_prints/guests
mkdir -p backend/memory/face_refs
```

- [ ] **Step 3: Ajouter la config cameras dans settings.json**

Ajouter avant la dernière accolade `}` :
```json
    "cameras": [
        {"id": 0, "type": "webcam", "label": "bureau"}
    ]
```
(settings.json doit se terminer par `"timezone": "Europe/Paris",\n    "cameras": [...]`)

- [ ] **Step 4: Installer resemblyzer**

```bash
conda run -n ada_v2 pip install resemblyzer
```
Expected: Successfully installed resemblyzer

- [ ] **Step 5: Commit**

```bash
git add requirements.txt backend/settings.json
git commit -m "chore: add resemblyzer dep + user recognition directory structure"
```

---

## Task 2: user_profile_manager.py

**Files:**
- Create: `backend/user_profile_manager.py`
- Create: `tests/test_user_profile_manager.py`

- [ ] **Step 1: Écrire le test en premier**

```python
# tests/test_user_profile_manager.py
import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

def test_get_nonexistent_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    assert mgr.get_profile("nobody") is None

def test_save_and_get_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    mgr.save_profile({"id": "bryan", "name": "Bryan", "role": "owner",
                      "preferences": [], "habits": [], "goals": [], "facts": [],
                      "created_at": "2026-01-01"})
    profile = mgr.get_profile("bryan")
    assert profile["name"] == "Bryan"

def test_save_preference_appends(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    mgr.save_profile({"id": "bryan", "name": "Bryan", "role": "owner",
                      "preferences": [], "habits": [], "goals": [], "facts": [],
                      "created_at": "2026-01-01"})
    mgr.save_preference("bryan", "Aime le café")
    assert "Aime le café" in mgr.get_profile("bryan")["preferences"]

def test_save_preference_no_duplicate(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    mgr.save_profile({"id": "bryan", "name": "Bryan", "role": "owner",
                      "preferences": ["Aime le café"], "habits": [], "goals": [], "facts": [],
                      "created_at": "2026-01-01"})
    mgr.save_preference("bryan", "Aime le café")
    assert mgr.get_profile("bryan")["preferences"].count("Aime le café") == 1

def test_create_guest_persistent(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    guest = mgr.create_guest("Marco")
    assert guest["id"] == "marco"
    assert guest["role"] == "guest"
    guest2 = mgr.create_guest("Marco")
    assert guest2["id"] == "marco"  # retourne le profil existant

def test_get_active_context_single(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    mgr.save_profile({"id": "bryan", "name": "Bryan", "role": "owner",
                      "preferences": ["Aime coder le matin"], "habits": [], "goals": [], "facts": [],
                      "created_at": "2026-01-01"})
    ctx = mgr.get_active_context([{"user": "bryan", "source": "voice", "confidence": 0.92}])
    assert "Bryan" in ctx
    assert "Aime coder le matin" in ctx

def test_get_active_context_dual_has_explicit_reply_instruction(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    for uid, name in [("bryan", "Bryan"), ("rose", "Rose")]:
        mgr.save_profile({"id": uid, "name": name, "role": "owner",
                          "preferences": [], "habits": [], "goals": [], "facts": [],
                          "created_at": "2026-01-01"})
    ctx = mgr.get_active_context([
        {"user": "bryan", "source": "voice", "confidence": 0.9},
        {"user": "rose",  "source": "face",  "confidence": 0.85},
    ])
    assert "réponds à chacun explicitement" in ctx

def test_get_active_context_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, user_profile_manager
    importlib.reload(user_profile_manager)
    from user_profile_manager import UserProfileManager
    mgr = UserProfileManager()
    assert mgr.get_active_context([]) == ""
```

- [ ] **Step 2: Vérifier que les tests échouent**

```bash
cd /Users/bryandev/jarvis && conda run -n ada_v2 pytest tests/test_user_profile_manager.py -v 2>&1 | head -20
```
Expected: ERROR — ModuleNotFoundError: No module named 'user_profile_manager'

- [ ] **Step 3: Implémenter user_profile_manager.py**

```python
# backend/user_profile_manager.py
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
```

- [ ] **Step 4: Vérifier que les tests passent**

```bash
cd /Users/bryandev/jarvis && conda run -n ada_v2 pytest tests/test_user_profile_manager.py -v
```
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add backend/user_profile_manager.py tests/test_user_profile_manager.py
git commit -m "feat: add UserProfileManager with CRUD and active context builder"
```

---

## Task 3: Migration des profils

**Files:**
- Create: `backend/migrate_profiles.py`
- Create: `backend/memory/users/bryan.json`
- Create: `backend/memory/users/rose.json`

- [ ] **Step 1: Créer le script de migration**

```python
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
```

- [ ] **Step 2: Exécuter la migration**

```bash
cd /Users/bryandev/jarvis && conda run -n ada_v2 python backend/migrate_profiles.py
```
Expected: Créé backend/memory/users/bryan.json + backend/memory/users/rose.json

- [ ] **Step 3: Vérifier les fichiers créés**

```bash
cat backend/memory/users/bryan.json
cat backend/memory/users/rose.json
```
Expected: JSON valides avec `"id": "bryan"` / `"id": "rose"`

- [ ] **Step 4: Commit**

```bash
git add backend/migrate_profiles.py backend/memory/users/bryan.json backend/memory/users/rose.json
git commit -m "feat: migrate procedural.json to multi-user profiles (bryan + rose)"
```

---

## Task 4: capture_face.py — support multi-utilisateur

**Files:**
- Modify: `backend/capture_face.py`

- [ ] **Step 1: Remplacer capture_face.py**

```python
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
```

- [ ] **Step 2: Vérifier la syntaxe**

```bash
conda run -n ada_v2 python -c "import ast; ast.parse(open('backend/capture_face.py').read()); print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add backend/capture_face.py
git commit -m "feat: extend capture_face.py for multi-user (--user argument)"
```

---

## Task 5: authenticator.py — MultiUserFaceDetector

**Files:**
- Modify: `backend/authenticator.py`

- [ ] **Step 1: Ajouter MultiUserFaceDetector à la fin de authenticator.py**

Lire authenticator.py puis ajouter après la dernière ligne :

```python


# ─── MULTI-USER FACE DETECTOR ───────────────────────────────────────────────

class MultiUserFaceDetector:
    """
    Détecte et identifie plusieurs utilisateurs dans un frame.
    Charge les photos de référence depuis memory/face_refs/.
    Retourne une liste de {"user": str, "confidence": float, "location": Optional[str]}.
    """

    CONFIDENCE_THRESHOLD = 0.85

    def __init__(self, camera_label: str = None):
        self.camera_label = camera_label
        self._reference_landmarks: dict[str, np.ndarray] = {}
        self.landmarker = None
        self._faces_dir = os.path.join(
            os.getenv("JARVIS_ROOT", "/Users/bryandev/jarvis"),
            "backend", "memory", "face_refs"
        )
        self._ensure_model()
        self._init_landmarker()
        self._load_all_references()

    def _ensure_model(self):
        if not os.path.exists(FaceAuthenticator.MODEL_PATH):
            print("[MFACE] Downloading Face Landmarker model...")
            try:
                urllib.request.urlretrieve(FaceAuthenticator.MODEL_URL, FaceAuthenticator.MODEL_PATH)
            except Exception as e:
                print(f"[MFACE] Download failed: {e}")

    def _init_landmarker(self):
        if not os.path.exists(FaceAuthenticator.MODEL_PATH):
            return
        try:
            base_options = mp_python.BaseOptions(model_asset_path=FaceAuthenticator.MODEL_PATH)
            options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
                num_faces=4,
            )
            self.landmarker = vision.FaceLandmarker.create_from_options(options)
        except Exception as e:
            print(f"[MFACE] Init failed: {e}")

    def _extract_landmarks(self, image_rgb: np.ndarray) -> list[np.ndarray]:
        if self.landmarker is None:
            return []
        try:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
            result = self.landmarker.detect(mp_image)
            return [
                np.array([[lm.x, lm.y, lm.z] for lm in face], dtype=np.float32).flatten()
                for face in result.face_landmarks
            ]
        except Exception:
            return []

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def _load_all_references(self):
        if not os.path.exists(self._faces_dir):
            return
        for fname in os.listdir(self._faces_dir):
            if not fname.endswith(".jpg"):
                continue
            user_id = fname[:-4]
            img_bgr = cv2.imread(os.path.join(self._faces_dir, fname))
            if img_bgr is None:
                continue
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            landmarks = self._extract_landmarks(img_rgb)
            if landmarks:
                self._reference_landmarks[user_id] = landmarks[0]
                print(f"[MFACE] Référence chargée : {user_id}")

    def reload_references(self):
        self._reference_landmarks.clear()
        self._load_all_references()

    def detect(self, frame_bgr: np.ndarray) -> list[dict]:
        """
        Analyse un frame BGR. Retourne une liste de détections :
        [{"user": str, "confidence": float, "location": Optional[str]}]
        """
        if not self._reference_landmarks:
            return []
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        detected_landmarks = self._extract_landmarks(frame_rgb)
        results = []
        for face_lm in detected_landmarks:
            best_user = None
            best_score = -1.0
            for user_id, ref_lm in self._reference_landmarks.items():
                score = self._cosine_similarity(face_lm, ref_lm)
                if score > best_score:
                    best_score = score
                    best_user = user_id
            if best_score >= self.CONFIDENCE_THRESHOLD and best_user:
                results.append({
                    "user": best_user,
                    "confidence": best_score,
                    "location": self.camera_label,
                })
        return results
```

- [ ] **Step 2: Vérifier la syntaxe**

```bash
conda run -n ada_v2 python -c "import ast; ast.parse(open('backend/authenticator.py').read()); print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add backend/authenticator.py
git commit -m "feat: add MultiUserFaceDetector to authenticator.py (multi-user, camera_label)"
```

---

## Task 6: voice_recognizer.py

**Files:**
- Create: `backend/voice_recognizer.py`
- Create: `tests/test_voice_recognizer.py`

- [ ] **Step 1: Écrire les tests**

```python
# tests/test_voice_recognizer.py
import pytest
import sys
import numpy as np
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

def test_identify_returns_none_when_no_embeddings(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    audio = np.zeros(32000, dtype=np.float32)
    # No embeddings enrolled → should return None without crashing
    result = vr.identify(audio)
    assert result is None

def test_enroll_from_array_creates_npy(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    # 5 seconds of silence — enough for resemblyzer to create an embedding
    audio = np.zeros(16000 * 5, dtype=np.float32)
    vr.enroll_from_array("testuser", audio)
    npy_path = tmp_path / "backend" / "memory" / "voice_prints" / "guests" / "testuser.npy"
    assert npy_path.exists()

def test_identify_known_user_above_threshold(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    # Enroll with a sine wave
    t = np.linspace(0, 5, 16000 * 5, dtype=np.float32)
    audio = np.sin(2 * np.pi * 440 * t) * 0.5
    vr.enroll_from_array("bryan", audio)
    # Identify with same audio → should match (same signal)
    result = vr.identify(audio[:32000])
    # resemblyzer on identical signals should score high
    assert result is not None
    assert result["user"] == "bryan"
    assert result["confidence"] >= 0.75

def test_feed_chunk_accumulates_before_identifying(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    t = np.linspace(0, 5, 16000 * 5, dtype=np.float32)
    audio = np.sin(2 * np.pi * 440 * t) * 0.5
    vr.enroll_from_array("bryan", audio)
    # Feed less than 2s → no result yet
    chunk = (audio[:1024] * 32767).astype(np.int16).tobytes()
    result = vr.feed_chunk(chunk)
    assert result is None  # Not enough audio yet

def test_feed_chunk_returns_result_after_2s(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib, voice_recognizer
    importlib.reload(voice_recognizer)
    from voice_recognizer import VoiceRecognizer
    vr = VoiceRecognizer()
    t = np.linspace(0, 5, 16000 * 5, dtype=np.float32)
    audio = np.sin(2 * np.pi * 440 * t) * 0.5
    vr.enroll_from_array("bryan", audio)
    # Feed 2 full seconds (32000 samples * 2 bytes = 64000 bytes)
    audio_2s = audio[:32000]
    pcm_bytes = (audio_2s * 32767).astype(np.int16).tobytes()
    result = vr.feed_chunk(pcm_bytes)
    assert result is not None
```

- [ ] **Step 2: Vérifier que les tests échouent**

```bash
cd /Users/bryandev/jarvis && conda run -n ada_v2 pytest tests/test_voice_recognizer.py -v 2>&1 | head -10
```
Expected: ModuleNotFoundError: No module named 'voice_recognizer'

- [ ] **Step 3: Implémenter voice_recognizer.py**

```python
# backend/voice_recognizer.py
import os
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
ACCUMULATION_BYTES = SAMPLE_RATE * BYTES_PER_SAMPLE * 2  # 2 secondes = 64000 bytes


class VoiceRecognizer:
    def __init__(self):
        os.makedirs(VOICE_PRINTS_DIR, exist_ok=True)
        os.makedirs(GUESTS_VOICE_DIR, exist_ok=True)
        self.encoder = VoiceEncoder()
        self._embeddings: dict[str, np.ndarray] = {}
        self._audio_buffer = bytearray()
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
```

- [ ] **Step 4: Lancer les tests**

```bash
cd /Users/bryandev/jarvis && conda run -n ada_v2 pytest tests/test_voice_recognizer.py -v
```
Expected: 5 passed (le test `test_identify_known_user_above_threshold` peut être lent ~3s — normal)

- [ ] **Step 5: Commit**

```bash
git add backend/voice_recognizer.py tests/test_voice_recognizer.py
git commit -m "feat: add VoiceRecognizer with resemblyzer embeddings + feed_chunk accumulation"
```

---

## Task 7: enroll.py — script d'enrollment one-shot

**Files:**
- Create: `backend/enroll.py`

- [ ] **Step 1: Créer enroll.py**

```python
# backend/enroll.py
"""
Script one-shot d'enrollment vocal + photo pour un utilisateur.
Usage:
  conda run -n ada_v2 python backend/enroll.py --user bryan
  conda run -n ada_v2 python backend/enroll.py --user rose
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
```

- [ ] **Step 2: Vérifier la syntaxe**

```bash
conda run -n ada_v2 python -c "import ast; ast.parse(open('backend/enroll.py').read()); print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add backend/enroll.py
git commit -m "feat: add enroll.py CLI script for one-shot voice + face enrollment"
```

---

## Task 8: presence_manager.py

**Files:**
- Create: `backend/presence_manager.py`
- Create: `tests/test_presence_manager.py`

- [ ] **Step 1: Écrire les tests**

```python
# tests/test_presence_manager.py
import pytest
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

def test_update_face_detection_adds_face_speaker(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    import importlib
    for mod in ["user_profile_manager", "voice_recognizer", "presence_manager"]:
        if mod in sys.modules:
            del sys.modules[mod]
    from presence_manager import PresenceManager
    pm = PresenceManager()
    pm.update_face_detection([{"user": "rose", "confidence": 0.9, "location": "bureau"}])
    assert any(s["user"] == "rose" for s in pm.active_speakers)

def test_voice_does_not_duplicate_face(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    for mod in ["user_profile_manager", "voice_recognizer", "presence_manager"]:
        if mod in sys.modules:
            del sys.modules[mod]
    from presence_manager import PresenceManager
    pm = PresenceManager()
    pm._active_speakers = [{"user": "bryan", "source": "voice", "confidence": 0.92}]
    pm.update_face_detection([{"user": "bryan", "confidence": 0.95, "location": "bureau"}])
    bryan_entries = [s for s in pm.active_speakers if s["user"] == "bryan"]
    assert len(bryan_entries) == 1  # pas de doublon
    assert bryan_entries[0]["source"] == "voice"  # voice a priorité

def test_get_context_block_empty_when_no_speakers(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    for mod in ["user_profile_manager", "voice_recognizer", "presence_manager"]:
        if mod in sys.modules:
            del sys.modules[mod]
    from presence_manager import PresenceManager
    pm = PresenceManager()
    assert pm.get_context_block() == ""

def test_get_context_block_with_known_user(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    for mod in ["user_profile_manager", "voice_recognizer", "presence_manager"]:
        if mod in sys.modules:
            del sys.modules[mod]
    import json, os
    users_dir = tmp_path / "backend" / "memory" / "users"
    users_dir.mkdir(parents=True)
    (users_dir / "bryan.json").write_text(json.dumps({
        "id": "bryan", "name": "Bryan", "role": "owner",
        "preferences": ["Aime le café"], "habits": [], "goals": [], "facts": [],
        "created_at": "2026-01-01"
    }))
    from presence_manager import PresenceManager
    pm = PresenceManager()
    pm._active_speakers = [{"user": "bryan", "source": "voice", "confidence": 0.92}]
    ctx = pm.get_context_block()
    assert "Bryan" in ctx
    assert "Aime le café" in ctx

@pytest.mark.asyncio
async def test_run_handles_empty_queue_gracefully(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_ROOT", str(tmp_path))
    for mod in ["user_profile_manager", "voice_recognizer", "presence_manager"]:
        if mod in sys.modules:
            del sys.modules[mod]
    from presence_manager import PresenceManager
    pm = PresenceManager()
    # Run for 0.2s then cancel — should not raise
    task = asyncio.create_task(pm.run())
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
```

- [ ] **Step 2: Vérifier que les tests échouent**

```bash
cd /Users/bryandev/jarvis && conda run -n ada_v2 pytest tests/test_presence_manager.py -v 2>&1 | head -10
```
Expected: ModuleNotFoundError: No module named 'presence_manager'

- [ ] **Step 3: Implémenter presence_manager.py**

```python
# backend/presence_manager.py
import asyncio
import os
from typing import Optional, Callable, Awaitable
from voice_recognizer import VoiceRecognizer
from user_profile_manager import UserProfileManager


class PresenceManager:
    def __init__(self):
        self.voice_recognizer = VoiceRecognizer()
        self.profile_manager = UserProfileManager()
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
                await self._on_unknown_voice()
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
```

- [ ] **Step 4: Lancer les tests**

```bash
cd /Users/bryandev/jarvis && conda run -n ada_v2 pip install pytest-asyncio -q && conda run -n ada_v2 pytest tests/test_presence_manager.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add backend/presence_manager.py tests/test_presence_manager.py
git commit -m "feat: add PresenceManager fusing voice + face detections into active_speakers"
```

---

## Task 9: Nouvelles déclarations d'outils dans mcp_tools_declarations.py

**Files:**
- Modify: `backend/mcp_tools_declarations.py`

- [ ] **Step 1: Lire mcp_tools_declarations.py pour trouver la fin de la liste MCP_TOOLS**

Chercher la ligne `MCP_TOOLS = [` et la ligne `]` finale. Les 3 nouveaux outils vont être insérés avant le `]` final.

- [ ] **Step 2: Ajouter les 3 nouveaux outils avant le `]` fermant de MCP_TOOLS**

```python
    {
        "name": "remember_for_user",
        "description": (
            "Enregistre une préférence, une habitude ou un fait pour l'utilisateur actuellement identifié. "
            "Utilise ce tool dès qu'un utilisateur mentionne une préférence, une habitude ou une information "
            "personnelle (ex: 'j'aime le café', 'je travaille le matin', 'j'ai deux enfants'). "
            "Ne l'utilise pas pour Bryan si ce n'est pas Bryan qui parle."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {
                    "type": "STRING",
                    "description": "ID de l'utilisateur : 'bryan', 'rose', ou le prénom en minuscules d'un invité."
                },
                "memory_type": {
                    "type": "STRING",
                    "description": "Type de mémoire : 'preference', 'habit', ou 'fact'."
                },
                "content": {
                    "type": "STRING",
                    "description": "La préférence, habitude ou fait à enregistrer."
                }
            },
            "required": ["user_id", "memory_type", "content"]
        }
    },
    {
        "name": "enroll_voice",
        "description": (
            "Lance l'enrollment vocal pour un utilisateur. À utiliser quand Bryan demande à Ada "
            "d'enregistrer la voix de quelqu'un (ex: 'Ada, enregistre la voix de Rose'). "
            "L'enrollment dure 25 secondes — prévenir l'utilisateur de parler normalement."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "user_id": {
                    "type": "STRING",
                    "description": "ID de l'utilisateur à enregistrer : 'bryan', 'rose', ou prénom invité."
                }
            },
            "required": ["user_id"]
        }
    },
    {
        "name": "who_is_speaking",
        "description": (
            "Retourne la liste des utilisateurs actuellement identifiés (voix + visage). "
            "Utilise ce tool quand Ada n'est pas sûre de qui lui parle ou quand Bryan demande "
            "'qui est là ?' / 'tu reconnais qui ?'."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
```

- [ ] **Step 3: Vérifier la syntaxe**

```bash
conda run -n ada_v2 python -c "import ast; ast.parse(open('backend/mcp_tools_declarations.py').read()); print('OK')"
```
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add backend/mcp_tools_declarations.py
git commit -m "feat: add remember_for_user, enroll_voice, who_is_speaking tool declarations"
```

---

## Task 10: Wire dans ada.py

**Files:**
- Modify: `backend/ada.py`

- [ ] **Step 1: Ajouter l'import de presence_manager en tête des imports locaux (autour de la ligne 670)**

Après la ligne `from reminder_manager import ReminderManager`, ajouter :
```python
from presence_manager import PresenceManager
from user_profile_manager import UserProfileManager
from authenticator import MultiUserFaceDetector
```

- [ ] **Step 2: Créer les instances module-level juste après les imports (autour de la ligne 710, après les imports locaux)**

Après la ligne `from mcps.twilio_mcp import TwilioMCP` (ou le dernier import), ajouter :
```python
# ─── PRÉSENCE & PROFILS ──────────────────────────────────────────────────────
presence_manager = PresenceManager()
user_profile_manager = UserProfileManager()
```

- [ ] **Step 3: Ajouter `_last_raw_frame` et `_face_detector` dans `AudioLoop.__init__`**

Dans la méthode `__init__` de AudioLoop (autour de la ligne 850), ajouter avant `self.permissions = {}` :
```python
        self._last_raw_frame = None  # dernier frame BGR brut pour la détection de visage
        self._face_detector = MultiUserFaceDetector(camera_label=None)
        self._guest_detection_pending = False
```

- [ ] **Step 4: Stocker le frame brut dans `_get_frame` (ligne 2751)**

Dans `_get_frame`, après `ret, frame = cap.read()` et avant `frame_rgb = cv2.cvtColor(...)`, ajouter :
```python
        self._last_raw_frame = frame  # pour la détection de visage en parallèle
```

- [ ] **Step 5: Ajouter `_face_detection_loop` comme méthode de AudioLoop**

Ajouter après la méthode `get_frames()` (autour de la ligne 2748) :
```python
    async def _face_detection_loop(self):
        """Lit _last_raw_frame toutes les secondes et met à jour presence_manager."""
        while True:
            await asyncio.sleep(1.0)
            if self._last_raw_frame is None:
                continue
            try:
                frame = self._last_raw_frame
                detections = await asyncio.to_thread(self._face_detector.detect, frame)
                if detections:
                    presence_manager.update_face_detection(detections)
            except Exception as e:
                print(f"[PRESENCE] Face detection error: {e}")
```

- [ ] **Step 6: Alimenter presence_manager en audio dans `listen_audio` (autour de la ligne 1106)**

Dans `listen_audio()`, après `self.out_queue.put_nowait({"data": data, "mime_type": "audio/pcm"})`, ajouter :
```python
                    presence_manager.feed_audio_chunk(data)
```

- [ ] **Step 7: Démarrer presence_manager et face_detection_loop dans `run()` (autour de la ligne 2895)**

Dans la méthode `run()`, après `tg.create_task(self.play_audio())`, ajouter :
```python
                    tg.create_task(presence_manager.run())
                    tg.create_task(self._face_detection_loop())
```

- [ ] **Step 8: Injecter le contexte utilisateur au démarrage (autour de la ligne 2905)**

Dans `run()`, après le bloc d'injection mémoire (après `await self.session.send(input=mem_ctx, end_of_turn=False)`), ajouter :
```python
                        # Injecter le contexte utilisateurs actifs
                        user_ctx = presence_manager.get_context_block()
                        if user_ctx:
                            await self.session.send(input=user_ctx, end_of_turn=False)
```

- [ ] **Step 9: Ajouter le callback pour voix inconnue (dans `__init__` de AudioLoop, après `self._guest_detection_pending = False`)**

```python
        async def _on_unknown_voice():
            if self._guest_detection_pending:
                return
            self._guest_detection_pending = True
            if self.session:
                try:
                    await self.session.send(
                        input="[SYSTÈME] Voix inconnue détectée. Demande à cette personne son prénom de manière naturelle, puis appelle create_guest avec ce prénom.",
                        end_of_turn=True
                    )
                except Exception as e:
                    print(f"[PRESENCE] guest callback error: {e}")
            await asyncio.sleep(30)  # anti-spam : 30s avant de re-demander
            self._guest_detection_pending = False
        presence_manager.set_unknown_voice_callback(_on_unknown_voice)
```

- [ ] **Step 10: Wirer les 3 nouveaux outils dans `_execute_text_tool`**

Chercher le bloc `elif n == "reminder_delete":` (ou un outil proche dans `_execute_text_tool`) et ajouter après :
```python
            elif n == "remember_for_user":
                uid = args.get("user_id", "")
                mtype = args.get("memory_type", "preference")
                content = args.get("content", "")
                if mtype == "preference":
                    return user_profile_manager.save_preference(uid, content)
                elif mtype == "fact":
                    return user_profile_manager.save_fact(uid, content)
                elif mtype == "habit":
                    profile = user_profile_manager.get_profile(uid)
                    if profile:
                        profile.setdefault("habits", []).append(content)
                        user_profile_manager.save_profile(profile)
                        return f"Habitude enregistrée pour {profile['name']}."
                    return f"Profil inconnu : {uid}"
                return "Type inconnu."
            elif n == "enroll_voice":
                uid = args.get("user_id", "")
                import subprocess
                subprocess.Popen(
                    ["conda", "run", "-n", "ada_v2", "python", "backend/enroll.py",
                     "--user", uid, "--voice-only"],
                    cwd=os.getenv("JARVIS_ROOT", "/Users/bryandev/jarvis")
                )
                return f"Enrollment vocal lancé pour '{uid}'. Parle normalement pendant 25 secondes."
            elif n == "who_is_speaking":
                speakers = presence_manager.active_speakers
                if not speakers:
                    return "Aucun utilisateur identifié pour le moment."
                lines = [f"- {s['user']} ({s.get('source','?')}, confiance {int(s.get('confidence',0)*100)}%)" for s in speakers]
                return "Utilisateurs détectés :\n" + "\n".join(lines)
            elif n == "create_guest":
                name = args.get("name", "Inconnu")
                profile = user_profile_manager.create_guest(name)
                presence_manager.voice_recognizer.reload_embeddings()
                presence_manager._guest_detection_pending = False
                return f"Profil créé pour {profile['name']}. Bienvenue !"
```

- [ ] **Step 11: Vérifier la syntaxe**

```bash
conda run -n ada_v2 python -c "import ast; ast.parse(open('backend/ada.py').read()); print('OK')"
```
Expected: OK

- [ ] **Step 12: Commit**

```bash
git add backend/ada.py
git commit -m "feat: wire presence_manager into ada.py (voice feed, face loop, user context injection)"
```

---

## Task 11: Wire dans external_bridge.py

**Files:**
- Modify: `backend/external_bridge.py`

- [ ] **Step 1: Ajouter les imports en haut de external_bridge.py**

Après les imports existants, ajouter :
```python
from user_profile_manager import UserProfileManager
_upm = UserProfileManager()
```

- [ ] **Step 2: Injecter le profil Bryan dans le system block de TextAgent**

Dans la méthode `_handle_text` (ou la méthode qui construit le `system` pour `generate_content`), trouver la ligne :
```python
        system = _si_text + date_block + memory_block
```
Et la remplacer par :
```python
        bryan_ctx = _upm.get_active_context([{"user": "bryan", "source": "telegram"}])
        user_block = f"\n\n{bryan_ctx}" if bryan_ctx else ""
        system = _si_text + date_block + memory_block + user_block
```

- [ ] **Step 3: Wirer les 3 nouveaux outils dans `TextAgent._execute_tool`**

Chercher le bloc de wiring des outils dans `_execute_tool` de TextAgent et ajouter :
```python
            elif name == "remember_for_user":
                uid = args.get("user_id", "")
                mtype = args.get("memory_type", "preference")
                content = args.get("content", "")
                if mtype == "preference":
                    return _upm.save_preference(uid, content)
                elif mtype == "fact":
                    return _upm.save_fact(uid, content)
                elif mtype == "habit":
                    profile = _upm.get_profile(uid)
                    if profile:
                        profile.setdefault("habits", []).append(content)
                        _upm.save_profile(profile)
                        return f"Habitude enregistrée pour {profile['name']}."
                    return f"Profil inconnu : {uid}"
                return "Type inconnu."
            elif name == "who_is_speaking":
                return "Mode Telegram — identification vocale non disponible. Utilisateur : Bryan."
            elif name == "enroll_voice":
                return "Enrollment vocal non disponible via Telegram. Lance depuis l'interface voix."
```

- [ ] **Step 4: Vérifier la syntaxe**

```bash
conda run -n ada_v2 python -c "import ast; ast.parse(open('backend/external_bridge.py').read()); print('OK')"
```
Expected: OK

- [ ] **Step 5: Commit final**

```bash
git add backend/external_bridge.py
git commit -m "feat: inject Bryan profile context in external_bridge TextAgent"
```

---

## Procédure d'enrollment après implémentation

Une fois tout déployé, lancer dans cet ordre :

```bash
# 1. Bryan
conda run -n ada_v2 python backend/enroll.py --user bryan
# (parler 25s + photo)

# 2. Rose
conda run -n ada_v2 python backend/enroll.py --user rose
# (parler 25s + photo)

# 3. Redémarrer Ada
bash start_ada.sh
```

---

## Self-Review

**Spec coverage :**
- ✅ Identification vocale (VoiceRecognizer + feed_chunk dans ada.py)
- ✅ Identification faciale + localisation caméra (MultiUserFaceDetector + _face_detection_loop)
- ✅ Profils Bryan / Rose avec migration procedural.json
- ✅ Invité : Ada demande le prénom, profil persistant créé
- ✅ Multi-speaker : get_active_context() génère l'instruction "réponds à chacun explicitement"
- ✅ Enrollment one-shot (enroll.py)
- ✅ Extension caméras futures (camera_label dans settings.json + MultiUserFaceDetector)
- ✅ Wire Telegram (external_bridge)
- ✅ 3 nouveaux outils Ada

**Pas de placeholders ni TBD.**

**Cohérence des types :**
- `VoiceRecognizer.feed_chunk(bytes) → Optional[dict]`
- `MultiUserFaceDetector.detect(np.ndarray) → list[dict]`
- `PresenceManager.active_speakers → list[dict]`
- `UserProfileManager.get_active_context(list[dict]) → str`
- Tous utilisés de façon cohérente dans ada.py et external_bridge.py.
