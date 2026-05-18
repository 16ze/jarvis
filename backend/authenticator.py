"""
Authentification et détection faciale locales via MediaPipe.

Important:
- Ce pipeline local sert à reconnaître des visages et à mesurer un mouvement
  facial grossier entre frames.
- `FaceAuthenticator` reste volontairement centré sur l'identité faciale.
- `MultiUserFaceDetector` peut désormais extraire des face blendshapes pour
  dériver un signal local d'expression fine en temps réel.
"""

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import cv2
import asyncio
import os
import base64
import numpy as np
import urllib.request


def _blendshape_scores_to_dict(categories) -> dict[str, float]:
    """Normalise les catégories MediaPipe en dict simple."""
    scores: dict[str, float] = {}
    for category in categories or []:
        name = getattr(category, "category_name", None)
        score = getattr(category, "score", None)
        if not name:
            continue
        try:
            scores[str(name)] = float(score)
        except (TypeError, ValueError):
            continue
    return scores


def _infer_emotion_from_blendshapes(scores: dict[str, float]) -> tuple[str, float]:
    """
    Dérive une émotion locale simple à partir des blendshapes MediaPipe.

    Retourne `(human_emotion, confidence)`.
    """
    if not scores:
        return "unknown", 0.0

    smile = max(scores.get("mouthSmileLeft", 0.0), scores.get("mouthSmileRight", 0.0))
    frown = max(scores.get("mouthFrownLeft", 0.0), scores.get("mouthFrownRight", 0.0))
    brow_inner_up = scores.get("browInnerUp", 0.0)
    brow_outer_up = max(scores.get("browOuterUpLeft", 0.0), scores.get("browOuterUpRight", 0.0))
    brow_down = max(scores.get("browDownLeft", 0.0), scores.get("browDownRight", 0.0))
    eye_wide = max(scores.get("eyeWideLeft", 0.0), scores.get("eyeWideRight", 0.0))
    eye_squint = max(scores.get("eyeSquintLeft", 0.0), scores.get("eyeSquintRight", 0.0))
    blink = max(scores.get("eyeBlinkLeft", 0.0), scores.get("eyeBlinkRight", 0.0))
    eye_look_down = max(scores.get("eyeLookDownLeft", 0.0), scores.get("eyeLookDownRight", 0.0))
    jaw_open = scores.get("jawOpen", 0.0)
    mouth_open = scores.get("mouthOpen", 0.0)
    mouth_lower_down = max(
        scores.get("mouthLowerDownLeft", 0.0),
        scores.get("mouthLowerDownRight", 0.0),
    )
    mouth_press = max(scores.get("mouthPressLeft", 0.0), scores.get("mouthPressRight", 0.0))
    mouth_pucker = scores.get("mouthPucker", 0.0)

    candidates = {
        "happy": smile * 1.35 - frown * 0.35 - brow_down * 0.28 + eye_squint * 0.12,
        "sad": frown * 0.85 + brow_inner_up * 0.72 + brow_outer_up * 0.18 + mouth_lower_down * 0.08 - smile * 0.45 - mouth_pucker * 0.10,
        "angry": brow_down * 1.10 + mouth_press * 0.45 + eye_squint * 0.18 + jaw_open * 0.10 - smile * 0.55,
        "stressed": eye_wide * 0.60 + jaw_open * 0.34 + mouth_open * 0.22 + mouth_lower_down * 0.16 + brow_down * 0.20 - brow_inner_up * 0.12,
        "tired": blink * 0.42 + eye_look_down * 0.26 + brow_inner_up * 0.14 - eye_wide * 0.22,
        "intimate": mouth_pucker * 0.78 + eye_squint * 0.12 - jaw_open * 0.15 - brow_inner_up * 0.18 - brow_outer_up * 0.12,
    }
    if smile < 0.55:
        candidates["happy"] *= 0.45
    if jaw_open >= 0.68 and mouth_lower_down >= 0.72 and brow_inner_up <= 0.56:
        candidates["stressed"] += 0.10
    if mouth_pucker < 0.50:
        candidates["intimate"] = 0.0

    best_emotion, best_score = max(candidates.items(), key=lambda item: item[1])
    best_score = max(0.0, float(best_score))
    if best_score < 0.28:
        return "neutral", best_score
    return best_emotion, min(1.0, best_score)

class FaceAuthenticator:
    # MediaPipe Face Landmarker model URL
    MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
    MODEL_PATH = os.path.join(os.path.dirname(__file__), "face_landmarker.task")
    SUPPORTS_FINE_FACIAL_EXPRESSIONS = False
    
    def __init__(self, reference_image_path="reference.jpg", on_status_change=None, on_frame=None):
        """
        :param reference_image_path: Path to the user's reference photo.
        :param on_status_change: Async callback(is_authenticated: bool).
        :param on_frame: Async callback(frame_data_b64: str) to send frames to frontend.
        """
        self.reference_image_path = reference_image_path
        self.on_status_change = on_status_change
        self.on_frame = on_frame
        
        self.authenticated = False
        self.running = False
        self.reference_landmarks = None
        self.landmarker = None

        self._ensure_model()
        self._init_landmarker()
        self._load_reference()

    def _ensure_model(self):
        """Download the MediaPipe Face Landmarker model if not present."""
        if not os.path.exists(self.MODEL_PATH):
            print(f"[AUTH] Downloading Face Landmarker model...")
            try:
                urllib.request.urlretrieve(self.MODEL_URL, self.MODEL_PATH)
                print(f"[AUTH] [OK] Model downloaded to {self.MODEL_PATH}")
            except Exception as e:
                print(f"[AUTH] [ERR] Failed to download model: {e}")

    def _init_landmarker(self):
        """Initialize the MediaPipe Face Landmarker."""
        if not os.path.exists(self.MODEL_PATH):
            print("[AUTH] [ERR] Face Landmarker model not found. Cannot initialize.")
            return
        
        try:
            base_options = mp_python.BaseOptions(model_asset_path=self.MODEL_PATH)
            options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                # Blendshapes stay disabled here: this local authenticator only
                # handles identity / geometry, not fine-grained expressions.
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
                num_faces=1
            )
            self.landmarker = vision.FaceLandmarker.create_from_options(options)
            print("[AUTH] [OK] Face Landmarker initialized.")
        except Exception as e:
            print(f"[AUTH] [ERR] Failed to initialize Face Landmarker: {e}")

    def _extract_landmarks(self, image_rgb):
        """
        Extract normalized face landmarks from an RGB image.
        Returns a flattened numpy array of (x, y, z) coordinates, or None if no face found.
        """
        if self.landmarker is None:
            return None
        
        try:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
            result = self.landmarker.detect(mp_image)
            
            if result.face_landmarks and len(result.face_landmarks) > 0:
                landmarks = result.face_landmarks[0]
                # Convert to numpy array of (x, y, z) coordinates
                coords = np.array([[lm.x, lm.y, lm.z] for lm in landmarks], dtype=np.float32)
                return coords.flatten()
            return None
        except Exception as e:
            print(f"[AUTH] [ERR] Landmark extraction failed: {e}")
            return None

    def _compare_landmarks(self, landmarks1, landmarks2, threshold=0.15):
        """
        Compare two landmark vectors using cosine similarity.
        Returns True if similarity is above (1 - threshold).
        """
        if landmarks1 is None or landmarks2 is None:
            return False
        
        # Normalize vectors
        norm1 = np.linalg.norm(landmarks1)
        norm2 = np.linalg.norm(landmarks2)
        
        if norm1 == 0 or norm2 == 0:
            return False
        
        # Cosine similarity
        similarity = np.dot(landmarks1, landmarks2) / (norm1 * norm2)
        
        # Threshold check (similarity should be close to 1 for a match)
        is_match = similarity > (1 - threshold)
        if is_match:
            print(f"[AUTH] Face match! Similarity: {similarity:.4f}")
        return is_match

    def _load_reference(self):
        if not os.path.exists(self.reference_image_path):
            print(f"[AUTH] [WARN] Reference file not found at {self.reference_image_path}. Authentication will fail.")
            return

        try:
            print("[AUTH] Loading reference image...")
            img_bgr = cv2.imread(self.reference_image_path)
            if img_bgr is None:
                print(f"[AUTH] [ERR] Failed to read image file: {self.reference_image_path}")
                return
            
            # Convert to RGB
            image_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            
            self.reference_landmarks = self._extract_landmarks(image_rgb)
            
            if self.reference_landmarks is not None:
                print("[AUTH] [OK] Reference face landmarks extracted successfully.")
            else:
                print("[AUTH] [ERR] No face found in reference image.")
        except Exception as e:
            print(f"[AUTH] [ERR] Error loading reference: {e}")

    async def start_authentication_loop(self):
        if self.authenticated:
            print("[AUTH] Already authenticated.")
            if self.on_status_change:
                await self.on_status_change(True)
            return

        if self.reference_landmarks is None:
             print("[AUTH] [ERR] Cannot start auth loop: No reference landmarks.")
             return

        self.running = True
        print("[AUTH] Starting camera for authentication...")
        
        # Capture the current (main) event loop
        loop = asyncio.get_running_loop()
        
        # Use a separate thread for blocking camera/CV operations
        await asyncio.to_thread(self._run_cv_loop, loop)

        print("[AUTH] Authentication loop finished.")
    
    def stop(self):
        print("[AUTH] Stopping authentication loop...")
        self.running = False

    def _run_cv_loop(self, loop):
        def try_open_camera(index):
            print(f"[AUTH] Trying to open camera with index {index}...")
            cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
            if not cap.isOpened():
                print(f"[AUTH] [ERR] Could not open video device {index}.")
                return None
            
            ret, frame = cap.read()
            if not ret:
                 print(f"[AUTH] [ERR] Opened device {index} but failed to read first frame.")
                 cap.release()
                 return None
            
            print(f"[AUTH] [OK] Successfully opened and read from device {index}.")
            return cap

        video_capture = try_open_camera(0)
        
        if video_capture is None:
             print("[AUTH] Device 0 failed. Trying device 1...")
             video_capture = try_open_camera(1)

        if video_capture is None:
             print("[AUTH] [ERR] All camera attempts failed. Authentication cannot proceed.")
             self.running = False
             return

        process_this_frame = True
        
        while self.running and not self.authenticated:
            ret, frame = video_capture.read()
            if not ret:
                print("[AUTH] [ERR] Failed to read frame from camera loop.")
                break
            
            # Convert BGR to RGB
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            
            # Process every other frame for performance
            if process_this_frame:
                current_landmarks = self._extract_landmarks(rgb_frame)
                
                if self._compare_landmarks(self.reference_landmarks, current_landmarks):
                    self.authenticated = True
                    print("[AUTH] [OPEN] FACE RECOGNIZED! Access Granted.")
                    if self.on_status_change:
                        asyncio.run_coroutine_threadsafe(self.on_status_change(True), loop)
                    self.running = False
                    break

            process_this_frame = not process_this_frame

            # Send frame to frontend if callback exists
            if self.on_frame:
                small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                _, buffer = cv2.imencode('.jpg', small_frame)
                b64_str = base64.b64encode(buffer).decode('utf-8')
                
                asyncio.run_coroutine_threadsafe(self.on_frame(b64_str), loop)

        video_capture.release()


# ─── MULTI-USER FACE DETECTOR ───────────────────────────────────────────────

class MultiUserFaceDetector:
    """
    Détecte et identifie plusieurs utilisateurs dans un frame BGR.
    Charge les photos de référence depuis memory/face_refs/.
    Retourne une liste de {"user": str, "confidence": float, "location": Optional[str]}.

    Note:
    - Ce détecteur local expose le mouvement du visage via les landmarks.
    - Il dérive aussi un signal local d'expression faciale à partir des
      blendshapes MediaPipe pour les réactions fines temps réel.
    """

    CONFIDENCE_THRESHOLD = 0.85
    SUPPORTS_FINE_FACIAL_EXPRESSIONS = True

    def __init__(self, camera_label: str = None):
        self.camera_label = camera_label
        self._reference_landmarks: dict[str, np.ndarray] = {}
        # ═══ BRAIN INTEGRATION — début ═══
        self._last_landmarks: dict[str, np.ndarray] = {}
        self._last_motion: float = 0.0
        self._last_expression_scores: dict[str, float] = {}
        self._last_emotion: str = "unknown"
        self._last_emotion_confidence: float = 0.0
        # ═══ BRAIN INTEGRATION — fin ═══
        # ═══ VISION OBJECT (YOLO) — partage de frame webcam ═══
        # Évite d'ouvrir une 2e capture webcam (incompatible macOS).
        self._last_frame: "np.ndarray | None" = None
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
                output_face_blendshapes=True,
                output_facial_transformation_matrixes=False,
                num_faces=4,
            )
            self.landmarker = vision.FaceLandmarker.create_from_options(options)
        except Exception as e:
            print(f"[MFACE] Init failed: {e}")

    def _extract_faces(self, image_rgb: np.ndarray) -> list[dict]:
        if self.landmarker is None:
            return []
        try:
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image_rgb)
            result = self.landmarker.detect(mp_image)
            faces = []
            all_landmarks = result.face_landmarks or []
            all_blendshapes = result.face_blendshapes or []
            for index, face in enumerate(all_landmarks):
                landmarks = np.array(
                    [[lm.x, lm.y, lm.z] for lm in face],
                    dtype=np.float32,
                ).flatten()
                blendshape_scores = _blendshape_scores_to_dict(
                    all_blendshapes[index] if index < len(all_blendshapes) else []
                )
                emotion, emotion_confidence = _infer_emotion_from_blendshapes(
                    blendshape_scores
                )
                faces.append(
                    {
                        "landmarks": landmarks,
                        "blendshape_scores": blendshape_scores,
                        "human_emotion": emotion,
                        "emotion_confidence": emotion_confidence,
                    }
                )
            return faces
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
            faces = self._extract_faces(img_rgb)
            if faces:
                self._reference_landmarks[user_id] = faces[0]["landmarks"]
                print(f"[MFACE] Référence chargée : {user_id}")

    def reload_references(self):
        self._reference_landmarks.clear()
        self._load_all_references()

    def detect(self, frame_bgr: np.ndarray) -> list[dict]:
        """
        Analyse un frame BGR. Retourne une liste de détections :
        [{"user": str, "confidence": float, "location": Optional[str]}]
        Retourne [] si aucun visage reconnu ou si aucune référence chargée.
        """
        # Partagé avec VisionObjectAgent (YOLO) — pas de seconde capture webcam.
        try:
            self._last_frame = frame_bgr.copy() if frame_bgr is not None else None
        except Exception:
            self._last_frame = None
        if not self._reference_landmarks:
            return []
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        detected_faces = self._extract_faces(frame_rgb)
        results = []
        # ═══ BRAIN INTEGRATION — début ═══
        motion_values = []
        emotion_values = []
        for face_data in detected_faces:
            face_lm = face_data["landmarks"]
            best_user = None
            best_score = -1.0
            for user_id, ref_lm in self._reference_landmarks.items():
                score = self._cosine_similarity(face_lm, ref_lm)
                if score > best_score:
                    best_score = score
                    best_user = user_id
            if best_score >= self.CONFIDENCE_THRESHOLD and best_user:
                try:
                    motion_values.append(self._compute_motion(best_user, face_lm))
                except Exception:
                    pass
                emotion = str(face_data.get("human_emotion") or "unknown")
                emotion_confidence = float(face_data.get("emotion_confidence") or 0.0)
                blendshape_scores = dict(face_data.get("blendshape_scores") or {})
                emotion_values.append((emotion, emotion_confidence, blendshape_scores))
                results.append({
                    "user": best_user,
                    "confidence": best_score,
                    "location": self.camera_label,
                    "human_emotion": emotion,
                    "emotion_confidence": emotion_confidence,
                    "expression_scores": blendshape_scores,
                })
        if motion_values:
            self._last_motion = max(motion_values)
        else:
            self._last_motion = 0.0
        if emotion_values:
            self._last_emotion, self._last_emotion_confidence, self._last_expression_scores = max(
                emotion_values,
                key=lambda item: item[1],
            )
        else:
            self._last_emotion = "unknown"
            self._last_emotion_confidence = 0.0
            self._last_expression_scores = {}
        # ═══ BRAIN INTEGRATION — fin ═══
        return results

    # ═══ BRAIN INTEGRATION — début ═══
    def _compute_motion(self, user: str, current_landmarks) -> float:
        """
        Calcule la magnitude du mouvement entre deux frames consécutives
        pour le user donné. Utilisé par le brain SNN.
        """
        try:
            current = np.asarray(current_landmarks, dtype=np.float32).flatten()
        except Exception:
            return 0.0

        last = self._last_landmarks.get(user)
        self._last_landmarks[user] = current
        if last is None or last.shape != current.shape:
            return 0.0

        delta = float(np.linalg.norm(current - last))
        return min(1.0, delta / 50.0)

    @property
    def last_motion(self) -> float:
        """Magnitude du dernier mouvement détecté [0.0-1.0]. Lu par le brain."""
        return self._last_motion

    @property
    def last_emotion(self) -> str:
        """Dernière émotion locale inférée à partir des blendshapes."""
        return self._last_emotion

    @property
    def last_emotion_confidence(self) -> float:
        """Confiance de la dernière émotion locale inférée."""
        return self._last_emotion_confidence

    @property
    def last_expression_scores(self) -> dict[str, float]:
        """Scores blendshapes de la dernière émotion locale inférée."""
        return dict(self._last_expression_scores)
    # ═══ BRAIN INTEGRATION — fin ═══

    # ═══ VISION OBJECT (YOLO) — partage de frame webcam ═══
    def get_last_frame(self):
        """Renvoie la dernière frame BGR capturée par MediaPipe (peut être None).

        Utilisé par VisionObjectAgent pour exécuter YOLO sans ouvrir une seconde
        capture webcam (incompatible avec macOS qui n'autorise qu'un seul processus).
        """
        return self._last_frame
    # ═══ VISION OBJECT (YOLO) — fin ═══
