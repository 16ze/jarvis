# Couche YOLO Vision — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter une couche YOLO (Open Images V7, 600 classes) à la vision d'Ada — en complément de MediaPipe (visages/gestes) et Gemini multimodal (scène sémantique) — sans rien retirer ni modifier le brain SNN.

**Architecture:** Agent asyncio `VisionObjectAgent` qui orchestre un wrapper stateless `YoloDetector`, un déduplicateur IoU avec tracking ByteTrack, et un stockage dual SQLite (factuel) + ChromaDB (sémantique). Trois tools Gemini exposés (`detect_objects`, `query_seen_objects`, `count_objects_seen`) wirés en mode PULL voix + texte. Deux boucles PUSH (caméra 10 fps continu, écran 15 s greffé sur `screen_watcher`) propagent des stimuli au brain SNN avec le **même schéma que `visual_scene_observer`** (source `"vision_object"`).

**Tech Stack:** Python 3.11, asyncio pur, `ultralytics==8.3.x` (YOLOv8 + ByteTrack), `torch>=2.2` (MPS Mac / CPU Hetzner), `sqlite3` stdlib, ChromaDB existant, pytest pour les tests. Aucune dépendance lourde nouvelle (pas de LangChain, pas de SQLAlchemy).

**Référence spec:** `docs/superpowers/specs/2026-05-17-yolo-vision-layer-design.md`

---

## Vue d'ensemble des fichiers

### Création

| Fichier | Responsabilité unique |
|---|---|
| `backend/yolo_detector.py` | Wrapper YOLO stateless : charger modèle, exécuter inférence, normaliser `Detection` |
| `backend/vision_translations.py` | Mapping statique OIV7 EN → FR (top 80 classes courantes) |
| `backend/vision_deduplicator.py` | `_DetectionDeduplicator` : matching IoU + ByteTrack → events |
| `backend/vision_storage.py` | `_VisionStorage` : persistance SQLite + ChromaDB transactionnelle |
| `backend/vision_object_agent.py` | `VisionObjectAgent` : orchestration boucles + mode PULL + singleton |
| `backend/memory/` | Dossier de persistance (créé au boot) |
| `backend/tests/__init__.py` | Marqueur package tests |
| `backend/tests/conftest.py` | Fixtures pytest (frames mock, db temp) |
| `backend/tests/fixtures/.gitkeep` | Placeholder dossier fixtures images |
| `backend/tests/test_yolo_detector.py` | Tests unitaires YoloDetector (mock model) |
| `backend/tests/test_vision_translations.py` | Tests du mapping FR |
| `backend/tests/test_vision_deduplicator.py` | Tests dédup |
| `backend/tests/test_vision_storage.py` | Tests SQLite + Chroma (tempdir) |
| `backend/tests/test_vision_object_agent.py` | Tests agent (PULL + PUSH + throttling + cleanup) |
| `pytest.ini` | Config asyncio_mode=auto + testpaths |

### Modification

| Fichier | Nature de la modification |
|---|---|
| `backend/authenticator.py` | Ajout `get_last_frame()` sur `MultiUserFaceDetector` (~6 lignes) |
| `backend/mcp_tools_declarations.py` | Ajout 3 déclarations de tools Gemini |
| `backend/ada.py` | Instanciation lazy agent + 3 branches `_execute_text_tool` |
| `backend/external_bridge.py` | 3 branches `_execute_tool` + accès au singleton |
| `backend/server.py` | Lifecycle FastAPI startup/shutdown |
| `backend/memory_manager.py` | Ajout collection ChromaDB `vision_objects` |
| `backend/screen_watcher.py` | Greffon fire-and-forget vers agent |
| `requirements.txt` | Ajout `ultralytics` + `torch` + `pytest-asyncio` |
| `.env.example` | Ajout 11 variables d'env |
| `.gitignore` | Exclusion `*.pt` + `backend/memory/vision_timeline.db*` |
| `CLAUDE.md` | Section "Vision objet (YOLO)" |

---

## Conventions du plan

- **TDD strict** : test rouge → implémentation minimale → test vert → commit.
- **Tous les outils retournent `str`** — jamais raise (règle absolue projet).
- **Commits fréquents** : 1 commit par étape « verte » (test + code minimal).
- **Format commit** : `feat(vision): ...`, `test(vision): ...`, `chore(vision): ...`, `docs(vision): ...`.
- **Environnement** : conda env `ada_v2`, lancé depuis racine repo.
- **Test runner** : `pytest backend/tests/ -v` depuis racine.

---

## Tâches

### Task 1 : Setup dépendances et environnement

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `backend/memory/.gitkeep`

- [ ] **Step 1 : Ajouter les dépendances dans `requirements.txt`**

Ajouter à la fin du fichier (après la dernière ligne `browser-use>=0.1.0`) :

```txt
# Vision objet (YOLO + Open Images V7)
ultralytics==8.3.40
torch>=2.2.0
torchvision>=0.17.0
pytest-asyncio>=0.23
```

- [ ] **Step 2 : Installer les dépendances**

Run : `pip install ultralytics==8.3.40 "torch>=2.2.0" "torchvision>=0.17.0" "pytest-asyncio>=0.23"`
Expected : installation OK, `python -c "import ultralytics; print(ultralytics.__version__)"` renvoie `8.3.40`

- [ ] **Step 3 : Ajouter les 11 variables d'env dans `.env.example`**

Ajouter à la fin du fichier :

```bash
# ──── Vision objet (YOLO) ────────────────────────────────────────
# Master switch : false = aucun import, zéro impact
VISION_OBJECT_ENABLED=false

# Modèle YOLO (téléchargé automatiquement au premier boot par ultralytics)
VISION_OBJECT_MODEL=yolov8m-oiv7.pt

# Device : 'mps' (Mac M-series), 'cuda' (Hetzner GPU), 'cpu' (fallback)
VISION_OBJECT_DEVICE=mps

# Tempo de la boucle caméra (frames/sec)
VISION_OBJECT_FPS=10

# Confidence minimale pour considérer une détection
VISION_OBJECT_CONFIDENCE=0.45

# Throttling brain : intervalle min entre 2 events de la même classe
VISION_OBJECT_BRAIN_THROTTLE_SEC=1.0

# Cap maximal d'events brain envoyés par seconde
VISION_OBJECT_MAX_EVENTS_PER_SEC=10

# Retention SQLite + ChromaDB (jours)
VISION_OBJECT_RETENTION_DAYS=30

# Heure du cleanup nocturne (HH:MM)
VISION_OBJECT_CLEANUP_TIME=04:00

# Boucle caméra activée (false = mode PULL seul)
VISION_OBJECT_CAMERA_LOOP=true

# Boucle écran activée (greffée sur screen_watcher)
VISION_OBJECT_SCREEN_LOOP=true
```

- [ ] **Step 4 : Ajouter les exclusions dans `.gitignore`**

Ajouter à la fin du fichier :

```gitignore
# Vision objet (YOLO)
*.pt
backend/memory/vision_timeline.db
backend/memory/vision_timeline.db-journal
backend/memory/vision_timeline.db-wal
backend/memory/vision_timeline.db-shm
```

- [ ] **Step 5 : Créer le dossier de persistance**

Run : `mkdir -p "backend/memory" && touch "backend/memory/.gitkeep"`
Expected : dossier créé, `.gitkeep` présent

- [ ] **Step 6 : Commit**

```bash
git add requirements.txt .env.example .gitignore backend/memory/.gitkeep
git commit -m "chore(vision): setup deps + env vars + storage dir for YOLO layer"
```

---

### Task 2 : Setup infrastructure de tests

**Files:**
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/fixtures/.gitkeep`
- Create: `pytest.ini`

- [ ] **Step 1 : Créer le package tests**

Créer `backend/tests/__init__.py` (vide).

- [ ] **Step 2 : Créer `pytest.ini` à la racine**

Créer `pytest.ini` :

```ini
[pytest]
asyncio_mode = auto
testpaths = backend/tests
python_files = test_*.py
```

- [ ] **Step 3 : Créer `conftest.py` avec fixtures réutilisables**

Créer `backend/tests/conftest.py` :

```python
"""Fixtures pytest partagées pour les tests de la couche vision YOLO."""
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest


@pytest.fixture
def fake_frame_bgr() -> np.ndarray:
    """Frame BGR 480x640 noire (placeholder)."""
    return np.zeros((480, 640, 3), dtype=np.uint8)


@pytest.fixture
def fake_frame_bgr_with_pattern() -> np.ndarray:
    """Frame BGR 480x640 avec un carré blanc au centre (debug visuel)."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[200:280, 280:360] = 255
    return frame


@pytest.fixture
def temp_db_path(tmp_path: Path) -> str:
    """Chemin vers une SQLite temporaire, supprimée à la fin du test."""
    return str(tmp_path / "test_vision.db")


@pytest.fixture
def mock_memory_manager() -> MagicMock:
    """MemoryManager mocké avec une collection vision_objects no-op."""
    mock = MagicMock()
    mock.vision_collection = MagicMock()
    mock.vision_collection.add = MagicMock(return_value=None)
    mock.vision_collection.query = MagicMock(
        return_value={"ids": [[]], "documents": [[]], "metadatas": [[]]}
    )
    return mock


@pytest.fixture
def fixtures_dir() -> Path:
    """Chemin vers le dossier de fixtures images."""
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 4 : Créer le dossier fixtures**

Créer `backend/tests/fixtures/.gitkeep` (vide).

- [ ] **Step 5 : Vérifier que pytest découvre le package**

Run : `pytest backend/tests/ --collect-only -q`
Expected : `no tests ran` (aucun test encore, mais 0 erreur de collection)

- [ ] **Step 6 : Commit**

```bash
git add pytest.ini backend/tests/__init__.py backend/tests/conftest.py backend/tests/fixtures/.gitkeep
git commit -m "test(vision): scaffold pytest infra + shared fixtures"
```

---

### Task 3 : Translations OIV7 FR (mapping statique)

**Files:**
- Create: `backend/vision_translations.py`
- Create: `backend/tests/test_vision_translations.py`

- [ ] **Step 1 : Écrire le test d'abord**

Créer `backend/tests/test_vision_translations.py` :

```python
"""Tests du mapping OIV7 EN → FR."""
from backend.vision_translations import translate_class, OIV7_FR_TRANSLATIONS


def test_translate_known_class_returns_french():
    assert translate_class("Mobile phone") == "téléphone"
    assert translate_class("Cat") == "chat"
    assert translate_class("Person") == "personne"


def test_translate_unknown_class_returns_lowercase_english():
    assert translate_class("UnknownThingy") == "unknownthingy"


def test_translate_handles_empty_string():
    assert translate_class("") == ""


def test_translations_dict_has_minimum_coverage():
    # Au moins 30 classes courantes couvertes
    assert len(OIV7_FR_TRANSLATIONS) >= 30


def test_translations_keys_are_capitalized_english():
    # Convention ultralytics : "Mobile phone", "Coffee cup"
    for key in OIV7_FR_TRANSLATIONS.keys():
        assert key[0].isupper(), f"Clé non capitalisée: {key}"
```

- [ ] **Step 2 : Lancer le test → échec attendu**

Run : `pytest backend/tests/test_vision_translations.py -v`
Expected : FAIL avec `ModuleNotFoundError: No module named 'backend.vision_translations'`

- [ ] **Step 3 : Implémentation minimale**

Créer `backend/vision_translations.py` :

```python
"""Mapping statique OIV7 (Open Images V7) EN → FR.

Couvre les ~80 classes les plus courantes au foyer / bureau.
Pour les classes non mappées, on renvoie la version lowercase EN
(meilleur que rien pour l'affichage et la recherche).
"""

OIV7_FR_TRANSLATIONS: dict[str, str] = {
    # Personnes & animaux
    "Person": "personne",
    "Man": "homme",
    "Woman": "femme",
    "Boy": "garçon",
    "Girl": "fille",
    "Cat": "chat",
    "Dog": "chien",
    "Bird": "oiseau",
    "Horse": "cheval",
    # Électronique
    "Mobile phone": "téléphone",
    "Telephone": "téléphone",
    "Laptop": "ordinateur portable",
    "Computer monitor": "écran",
    "Computer keyboard": "clavier",
    "Computer mouse": "souris",
    "Tablet computer": "tablette",
    "Television": "télévision",
    "Remote control": "télécommande",
    "Headphones": "casque audio",
    "Camera": "caméra",
    "Microphone": "micro",
    "Printer": "imprimante",
    # Mobilier
    "Chair": "chaise",
    "Couch": "canapé",
    "Sofa bed": "canapé-lit",
    "Bed": "lit",
    "Table": "table",
    "Desk": "bureau",
    "Bookcase": "bibliothèque",
    "Cabinetry": "meuble de rangement",
    "Shelf": "étagère",
    # Cuisine & alimentation
    "Cup": "tasse",
    "Mug": "mug",
    "Coffee cup": "tasse de café",
    "Bottle": "bouteille",
    "Wine glass": "verre à vin",
    "Plate": "assiette",
    "Bowl": "bol",
    "Fork": "fourchette",
    "Knife": "couteau",
    "Spoon": "cuillère",
    "Banana": "banane",
    "Apple": "pomme",
    "Orange": "orange",
    "Sandwich": "sandwich",
    "Pizza": "pizza",
    "Cake": "gâteau",
    # Sac & accessoires
    "Backpack": "sac à dos",
    "Handbag": "sac à main",
    "Suitcase": "valise",
    "Wallet": "portefeuille",
    "Watch": "montre",
    "Glasses": "lunettes",
    "Sunglasses": "lunettes de soleil",
    "Hat": "chapeau",
    # Livres & papier
    "Book": "livre",
    "Magazine": "magazine",
    "Newspaper": "journal",
    "Pen": "stylo",
    "Pencil": "crayon",
    # Véhicules
    "Car": "voiture",
    "Bicycle": "vélo",
    "Motorcycle": "moto",
    "Truck": "camion",
    "Bus": "bus",
    # Risque & sécurité
    "Fire": "feu",
    "Gun": "arme",
    "Pistol": "pistolet",
    # Maison
    "Clock": "horloge",
    "Lamp": "lampe",
    "Flower": "fleur",
    "Plant": "plante",
    "Houseplant": "plante d'intérieur",
    "Mirror": "miroir",
    "Toilet": "toilettes",
    "Sink": "évier",
    # Sport
    "Ball": "balle",
    "Sports equipment": "équipement de sport",
    "Skateboard": "skateboard",
    # Divers utiles
    "Box": "boîte",
    "Bag": "sac",
    "Toy": "jouet",
    "Tool": "outil",
    "Scissors": "ciseaux",
    "Umbrella": "parapluie",
}


def translate_class(class_name_en: str) -> str:
    """Traduit une classe OIV7 EN vers FR.

    Renvoie la valeur du dict si trouvée, sinon le `class_name_en.lower()`
    pour rester utilisable même hors mapping.
    """
    if not class_name_en:
        return ""
    return OIV7_FR_TRANSLATIONS.get(class_name_en, class_name_en.lower())
```

- [ ] **Step 4 : Relancer le test → succès attendu**

Run : `pytest backend/tests/test_vision_translations.py -v`
Expected : 5 passed

- [ ] **Step 5 : Commit**

```bash
git add backend/vision_translations.py backend/tests/test_vision_translations.py
git commit -m "feat(vision): add OIV7 EN→FR class name mapping (80+ classes)"
```

---

### Task 4 : `Detection` dataclass + `YoloDetector` wrapper

**Files:**
- Create: `backend/yolo_detector.py`
- Create: `backend/tests/test_yolo_detector.py`

- [ ] **Step 1 : Écrire les tests d'abord (avec mock du modèle ultralytics)**

Créer `backend/tests/test_yolo_detector.py` :

```python
"""Tests unitaires YoloDetector (modèle ultralytics mocké)."""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.yolo_detector import Detection, YoloDetector


def _make_fake_ultralytics_result(detections: list[tuple]):
    """Construit un faux objet Results compatible avec l'API ultralytics.

    `detections` est une liste de tuples
    (cls_id, conf, x_center, y_center, w, h, track_id).
    Toutes les valeurs bbox sont normalisées [0,1].
    """
    fake_result = MagicMock()
    if not detections:
        fake_result.boxes = None
        fake_result.names = {}
        return [fake_result]

    cls_ids = np.array([d[0] for d in detections])
    confs = np.array([d[1] for d in detections])
    xywhn = np.array([[d[2], d[3], d[4], d[5]] for d in detections])
    has_track = detections[0][6] is not None
    track_ids = np.array([d[6] for d in detections]) if has_track else None

    fake_result.boxes = MagicMock()
    fake_result.boxes.cls = MagicMock(
        cpu=lambda: MagicMock(numpy=lambda: cls_ids)
    )
    fake_result.boxes.conf = MagicMock(
        cpu=lambda: MagicMock(numpy=lambda: confs)
    )
    fake_result.boxes.xywhn = MagicMock(
        cpu=lambda: MagicMock(numpy=lambda: xywhn)
    )
    if track_ids is not None:
        fake_result.boxes.id = MagicMock(
            cpu=lambda: MagicMock(numpy=lambda: track_ids)
        )
    else:
        fake_result.boxes.id = None
    fake_result.names = {0: "Mobile phone", 1: "Cat", 2: "Person"}
    return [fake_result]


def test_detection_dataclass_is_frozen():
    d = Detection(
        class_id=0, class_name="Mobile phone", class_fr="téléphone",
        confidence=0.9, bbox=(0.5, 0.5, 0.1, 0.2), track_id=1,
    )
    with pytest.raises(Exception):
        d.confidence = 0.5  # type: ignore[misc]


@patch("backend.yolo_detector.YOLO")
def test_detector_loads_model_with_configured_device(mock_yolo_cls):
    YoloDetector(model_path="yolov8m-oiv7.pt", device="mps", confidence_min=0.45)
    mock_yolo_cls.assert_called_once_with("yolov8m-oiv7.pt")


@patch("backend.yolo_detector.YOLO")
def test_detect_returns_empty_list_for_no_detections(mock_yolo_cls, fake_frame_bgr):
    mock_model = MagicMock()
    mock_model.track = MagicMock(return_value=_make_fake_ultralytics_result([]))
    mock_yolo_cls.return_value = mock_model

    detector = YoloDetector(model_path="yolov8m-oiv7.pt", device="cpu", confidence_min=0.45)
    detections = detector.detect(fake_frame_bgr)

    assert detections == []


@patch("backend.yolo_detector.YOLO")
def test_detect_returns_detections_with_french_translation(mock_yolo_cls, fake_frame_bgr):
    mock_model = MagicMock()
    mock_model.track = MagicMock(return_value=_make_fake_ultralytics_result([
        (0, 0.91, 0.5, 0.5, 0.1, 0.2, 7),
        (1, 0.78, 0.3, 0.4, 0.15, 0.25, 12),
    ]))
    mock_yolo_cls.return_value = mock_model

    detector = YoloDetector(model_path="yolov8m-oiv7.pt", device="cpu", confidence_min=0.45)
    detections = detector.detect(fake_frame_bgr)

    assert len(detections) == 2
    assert detections[0].class_name == "Mobile phone"
    assert detections[0].class_fr == "téléphone"
    assert detections[0].confidence == pytest.approx(0.91)
    assert detections[0].track_id == 7
    assert detections[1].class_fr == "chat"


@patch("backend.yolo_detector.YOLO")
def test_detect_filters_by_confidence_threshold(mock_yolo_cls, fake_frame_bgr):
    mock_model = MagicMock()
    mock_model.track = MagicMock(return_value=_make_fake_ultralytics_result([
        (0, 0.91, 0.5, 0.5, 0.1, 0.2, 7),    # garde
        (1, 0.30, 0.3, 0.4, 0.15, 0.25, 12), # drop (< 0.45)
    ]))
    mock_yolo_cls.return_value = mock_model

    detector = YoloDetector(model_path="yolov8m-oiv7.pt", device="cpu", confidence_min=0.45)
    detections = detector.detect(fake_frame_bgr)

    assert len(detections) == 1
    assert detections[0].class_fr == "téléphone"


@patch("backend.yolo_detector.YOLO")
def test_detect_returns_empty_list_on_exception(mock_yolo_cls, fake_frame_bgr):
    mock_model = MagicMock()
    mock_model.track = MagicMock(side_effect=RuntimeError("CUDA OOM"))
    mock_yolo_cls.return_value = mock_model

    detector = YoloDetector(model_path="yolov8m-oiv7.pt", device="cpu", confidence_min=0.45)
    detections = detector.detect(fake_frame_bgr)

    # Pas de raise, juste []
    assert detections == []
```

- [ ] **Step 2 : Lancer les tests → échec attendu**

Run : `pytest backend/tests/test_yolo_detector.py -v`
Expected : FAIL `ModuleNotFoundError: No module named 'backend.yolo_detector'`

- [ ] **Step 3 : Implémentation**

Créer `backend/yolo_detector.py` :

```python
"""Wrapper stateless YOLO (ultralytics + ByteTrack) pour la couche vision objet.

Renvoie une liste de `Detection` normalisées (bbox [0,1], translation FR).
Ne maintient aucun état entre frames — c'est le rôle du `_DetectionDeduplicator`.
ByteTrack est utilisé via `model.track()` pour des track_id stables inter-frames.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

from backend.vision_translations import translate_class

_LOG = logging.getLogger("vision_object")


@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str          # nom EN OIV7 brut
    class_fr: str            # traduit FR (ou lowercase EN si absent du mapping)
    confidence: float        # 0.0 - 1.0
    bbox: tuple[float, float, float, float]   # (x_center, y_center, w, h) normalisés
    track_id: int | None     # ID stable ByteTrack (None si non-tracké)


class YoloDetector:
    """Wrapper stateless YOLO. Une instance = un modèle chargé en RAM."""

    def __init__(
        self,
        model_path: str = "yolov8m-oiv7.pt",
        device: str = "mps",
        confidence_min: float = 0.45,
    ) -> None:
        self._device = device
        self._confidence_min = confidence_min
        # Téléchargement automatique du modèle si absent (~52 MB pour yolov8m-oiv7)
        self._model = YOLO(model_path)
        _LOG.info(
            "[VISION_OBJ] Model loaded: %s on device=%s confidence_min=%.2f",
            model_path, device, confidence_min,
        )

    def detect(self, frame_bgr: np.ndarray) -> list[Detection]:
        """Inférence + tracking ByteTrack sur une frame BGR.

        Renvoie toujours une liste (vide si erreur ou aucune détection).
        Ne raise jamais — politique fault-tolerance du projet.
        """
        try:
            results = self._model.track(
                source=frame_bgr,
                device=self._device,
                conf=self._confidence_min,
                persist=True,        # tracking inter-appels
                verbose=False,
            )
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] Inference failed: %s", exc)
            return []

        if not results:
            return []

        result = results[0]
        if result.boxes is None:
            return []

        try:
            cls_ids = result.boxes.cls.cpu().numpy().astype(int)
            confs = result.boxes.conf.cpu().numpy().astype(float)
            xywhn = result.boxes.xywhn.cpu().numpy().astype(float)
            track_ids: list[int | None]
            if result.boxes.id is not None:
                track_ids = [int(t) for t in result.boxes.id.cpu().numpy()]
            else:
                track_ids = [None] * len(cls_ids)
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] Result parsing failed: %s", exc)
            return []

        names: dict[int, str] = result.names or {}
        detections: list[Detection] = []
        for idx, (cls_id, conf) in enumerate(zip(cls_ids, confs)):
            if conf < self._confidence_min:
                continue
            class_name = names.get(int(cls_id), f"class_{cls_id}")
            xc, yc, w, h = xywhn[idx]
            detections.append(Detection(
                class_id=int(cls_id),
                class_name=class_name,
                class_fr=translate_class(class_name),
                confidence=float(conf),
                bbox=(float(xc), float(yc), float(w), float(h)),
                track_id=track_ids[idx],
            ))
        return detections
```

- [ ] **Step 4 : Relancer les tests → succès attendu**

Run : `pytest backend/tests/test_yolo_detector.py -v`
Expected : 6 passed

- [ ] **Step 5 : Commit**

```bash
git add backend/yolo_detector.py backend/tests/test_yolo_detector.py
git commit -m "feat(vision): add YoloDetector wrapper with ByteTrack and FR translation"
```

---

### Task 5 : Déduplicateur IoU avec génération d'events

**Files:**
- Create: `backend/vision_deduplicator.py`
- Create: `backend/tests/test_vision_deduplicator.py`

- [ ] **Step 1 : Écrire les tests d'abord**

Créer `backend/tests/test_vision_deduplicator.py` :

```python
"""Tests du déduplicateur de détections (IoU + ByteTrack)."""
from backend.yolo_detector import Detection
from backend.vision_deduplicator import (
    DedupConfig,
    EventType,
    _DetectionDeduplicator,
)


def _det(
    track_id: int, cls_fr: str = "téléphone",
    bbox=(0.5, 0.5, 0.1, 0.1), conf: float = 0.9,
) -> Detection:
    return Detection(
        class_id=0, class_name="Mobile phone", class_fr=cls_fr,
        confidence=conf, bbox=bbox, track_id=track_id,
    )


def test_first_frame_produces_appeared_events_for_all_detections():
    dedup = _DetectionDeduplicator(DedupConfig())
    events = dedup.diff([_det(1), _det(2, "chat")], source="camera", timestamp=100.0)
    assert len(events) == 2
    assert all(e.event_type == EventType.APPEARED for e in events)


def test_stable_scene_produces_no_events_on_second_frame():
    dedup = _DetectionDeduplicator(DedupConfig())
    dets = [_det(1)]
    dedup.diff(dets, source="camera", timestamp=100.0)
    events_2 = dedup.diff(dets, source="camera", timestamp=100.1)
    assert events_2 == []


def test_significant_bbox_change_produces_moved_event():
    dedup = _DetectionDeduplicator(DedupConfig(iou_moved_threshold=0.5))
    dedup.diff([_det(1, bbox=(0.5, 0.5, 0.1, 0.1))], source="camera", timestamp=100.0)
    # Bouge loin → IoU = 0
    events = dedup.diff([_det(1, bbox=(0.9, 0.9, 0.1, 0.1))], source="camera", timestamp=100.1)
    assert len(events) == 1
    assert events[0].event_type == EventType.MOVED


def test_occlusion_within_grace_period_does_not_trigger_disappeared():
    dedup = _DetectionDeduplicator(DedupConfig(disappear_grace_frames=5))
    dedup.diff([_det(1)], source="camera", timestamp=100.0)
    # 3 frames d'absence (< grace 5)
    for i in range(1, 4):
        events = dedup.diff([], source="camera", timestamp=100.0 + i * 0.1)
        assert events == []


def test_object_absent_for_grace_period_triggers_one_disappeared():
    dedup = _DetectionDeduplicator(DedupConfig(disappear_grace_frames=5))
    dedup.diff([_det(1)], source="camera", timestamp=100.0)
    events_final: list = []
    for i in range(1, 7):
        events_final = dedup.diff([], source="camera", timestamp=100.0 + i * 0.1)
    # Au tick 6, 5 absences consécutives → DISAPPEARED émis
    assert len(events_final) == 1
    assert events_final[0].event_type == EventType.DISAPPEARED


def test_confidence_jump_produces_updated_event():
    dedup = _DetectionDeduplicator(DedupConfig())
    dedup.diff([_det(1, conf=0.9)], source="camera", timestamp=100.0)
    events = dedup.diff([_det(1, conf=0.5)], source="camera", timestamp=100.1)
    types = [e.event_type for e in events]
    assert EventType.UPDATED in types


def test_max_tracked_objects_eviction_lru():
    cfg = DedupConfig(max_tracked_objects=3)
    dedup = _DetectionDeduplicator(cfg)
    dedup.diff([_det(1), _det(2), _det(3)], source="camera", timestamp=100.0)
    dedup.diff([_det(1), _det(2), _det(3), _det(4)], source="camera", timestamp=100.1)
    # Au moins un évincé pour respecter le cap
    assert len(dedup._tracked) <= 3


def test_different_sources_have_independent_tracking():
    dedup = _DetectionDeduplicator(DedupConfig())
    e1 = dedup.diff([_det(1)], source="camera", timestamp=100.0)
    e2 = dedup.diff([_det(1)], source="screen", timestamp=100.1)
    # Même track_id mais source différente → 2x APPEARED
    assert len(e1) == 1 and len(e2) == 1
    assert e1[0].event_type == EventType.APPEARED
    assert e2[0].event_type == EventType.APPEARED
```

- [ ] **Step 2 : Lancer les tests → échec attendu**

Run : `pytest backend/tests/test_vision_deduplicator.py -v`
Expected : FAIL `ModuleNotFoundError`

- [ ] **Step 3 : Implémentation**

Créer `backend/vision_deduplicator.py` :

```python
"""Déduplicateur IoU pour la couche vision objet.

Reçoit des `Detection` (sortie YOLO + ByteTrack) frame par frame,
maintient un état par (source, track_id), et émet des `ObjectEvent`
quand un objet apparaît / disparaît / se déplace significativement /
voit sa confidence varier fortement.
"""
from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum

from backend.yolo_detector import Detection


class EventType(str, Enum):
    APPEARED = "appeared"
    DISAPPEARED = "disappeared"
    MOVED = "moved"
    UPDATED = "updated"


@dataclass(frozen=True)
class ObjectEvent:
    event_id: str
    event_type: EventType
    source: str                 # "camera" | "screen"
    timestamp: float
    detection: Detection
    track_id: int | None
    location_hint: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class DedupConfig:
    iou_moved_threshold: float = 0.5
    disappear_grace_frames: int = 5
    confidence_update_threshold: float = 0.2
    max_tracked_objects: int = 100


@dataclass
class _TrackedObject:
    detection: Detection
    last_seen_ts: float
    consecutive_misses: int = 0


def _iou(
    b1: tuple[float, float, float, float],
    b2: tuple[float, float, float, float],
) -> float:
    """IoU entre deux bbox au format (x_center, y_center, w, h) normalisées."""
    def _to_corners(b):
        xc, yc, w, h = b
        return (xc - w / 2, yc - h / 2, xc + w / 2, yc + h / 2)

    ax1, ay1, ax2, ay2 = _to_corners(b1)
    bx1, by1, bx2, by2 = _to_corners(b2)
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def _make_event(
    event_type: EventType, source: str, timestamp: float, detection: Detection,
) -> ObjectEvent:
    return ObjectEvent(
        event_id=uuid.uuid4().hex[:12],
        event_type=event_type,
        source=source,
        timestamp=timestamp,
        detection=detection,
        track_id=detection.track_id,
    )


class _DetectionDeduplicator:
    """Maintient l'état des objets vus par (source, track_id) et émet des events."""

    def __init__(self, config: DedupConfig | None = None) -> None:
        self._config = config or DedupConfig()
        # OrderedDict pour éviction LRU naturelle
        self._tracked: OrderedDict[tuple[str, int], _TrackedObject] = OrderedDict()

    def diff(
        self,
        detections: list[Detection],
        source: str,
        timestamp: float | None = None,
    ) -> list[ObjectEvent]:
        """Compare le batch courant à l'état précédent, retourne les events."""
        ts = timestamp if timestamp is not None else time.time()
        events: list[ObjectEvent] = []
        seen_keys: set[tuple[str, int]] = set()

        for det in detections:
            if det.track_id is None:
                events.append(_make_event(EventType.APPEARED, source, ts, det))
                continue

            key = (source, det.track_id)
            seen_keys.add(key)

            if key not in self._tracked:
                events.append(_make_event(EventType.APPEARED, source, ts, det))
                self._tracked[key] = _TrackedObject(detection=det, last_seen_ts=ts)
            else:
                tracked = self._tracked[key]
                iou = _iou(tracked.detection.bbox, det.bbox)
                if iou < self._config.iou_moved_threshold:
                    events.append(_make_event(EventType.MOVED, source, ts, det))
                if abs(tracked.detection.confidence - det.confidence) > self._config.confidence_update_threshold:
                    events.append(_make_event(EventType.UPDATED, source, ts, det))
                tracked.detection = det
                tracked.last_seen_ts = ts
                tracked.consecutive_misses = 0
                self._tracked.move_to_end(key)

        # Détection des disparitions (objets pas vus dans ce batch, pour cette source)
        keys_to_delete: list[tuple[str, int]] = []
        for key, tracked in self._tracked.items():
            if key[0] != source:
                continue
            if key in seen_keys:
                continue
            tracked.consecutive_misses += 1
            if tracked.consecutive_misses >= self._config.disappear_grace_frames:
                events.append(_make_event(EventType.DISAPPEARED, source, ts, tracked.detection))
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._tracked[key]

        # Éviction LRU si on dépasse la limite
        while len(self._tracked) > self._config.max_tracked_objects:
            self._tracked.popitem(last=False)

        return events
```

- [ ] **Step 4 : Relancer les tests → succès attendu**

Run : `pytest backend/tests/test_vision_deduplicator.py -v`
Expected : 8 passed

- [ ] **Step 5 : Commit**

```bash
git add backend/vision_deduplicator.py backend/tests/test_vision_deduplicator.py
git commit -m "feat(vision): add IoU-based deduplicator emitting APPEARED/MOVED/DISAPPEARED/UPDATED"
```

---

### Task 6 : Stockage SQLite + ChromaDB (`_VisionStorage`)

**Files:**
- Create: `backend/vision_storage.py`
- Create: `backend/tests/test_vision_storage.py`

- [ ] **Step 1 : Écrire les tests d'abord (Chroma mocké via fixture)**

Créer `backend/tests/test_vision_storage.py` :

```python
"""Tests du stockage vision (SQLite + ChromaDB)."""
import sqlite3
import time

from backend.yolo_detector import Detection
from backend.vision_deduplicator import EventType, ObjectEvent
from backend.vision_storage import _VisionStorage


def _evt(
    event_type: EventType = EventType.APPEARED,
    track_id: int = 1,
    cls_fr: str = "téléphone",
    ts: float = 1000.0,
    source: str = "camera",
) -> ObjectEvent:
    det = Detection(
        class_id=0, class_name="Mobile phone", class_fr=cls_fr,
        confidence=0.9, bbox=(0.5, 0.5, 0.1, 0.1), track_id=track_id,
    )
    return ObjectEvent(
        event_id=f"evt_{track_id}_{event_type.value}_{int(ts)}",
        event_type=event_type, source=source, timestamp=ts,
        detection=det, track_id=track_id,
    )


def test_storage_creates_schema_on_init(temp_db_path, mock_memory_manager):
    _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    conn = sqlite3.connect(temp_db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "object_events" in tables
    assert "current_objects" in tables


def test_storage_persists_appeared_event(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([_evt(event_type=EventType.APPEARED, track_id=42, cls_fr="chat")])

    conn = sqlite3.connect(temp_db_path)
    rows = conn.execute(
        "SELECT event_type, class_fr, track_id FROM object_events"
    ).fetchall()
    assert rows == [("appeared", "chat", 42)]

    current = conn.execute(
        "SELECT track_id, class_fr, is_present FROM current_objects"
    ).fetchall()
    assert current == [(42, "chat", 1)]


def test_storage_marks_object_absent_on_disappeared(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([_evt(EventType.APPEARED, track_id=5)])
    storage.persist([_evt(EventType.DISAPPEARED, track_id=5, ts=1010.0)])

    conn = sqlite3.connect(temp_db_path)
    is_present = conn.execute(
        "SELECT is_present FROM current_objects WHERE track_id = 5"
    ).fetchone()[0]
    assert is_present == 0


def test_storage_indexes_only_appeared_and_moved_in_chroma(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([
        _evt(EventType.APPEARED, track_id=1),
        _evt(EventType.MOVED, track_id=2),
        _evt(EventType.DISAPPEARED, track_id=3),
        _evt(EventType.UPDATED, track_id=4),
    ])

    # Seuls APPEARED + MOVED indexés dans Chroma
    assert mock_memory_manager.vision_collection.add.call_count == 2


def test_query_recent_by_class(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([_evt(EventType.APPEARED, track_id=1, cls_fr="livre", ts=1000.0)])
    storage.persist([_evt(EventType.APPEARED, track_id=2, cls_fr="livre", ts=2000.0)])
    storage.persist([_evt(EventType.APPEARED, track_id=3, cls_fr="chat",  ts=1500.0)])

    results = storage.query_by_class("livre", since_ts=0.0, max_results=10)
    assert len(results) == 2
    assert results[0]["timestamp"] >= results[1]["timestamp"]  # ordre DESC


def test_count_distinct_track_ids(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    # Le même track_id réapparaît 3 fois → ne doit compter qu'1
    for ts in (1000.0, 1001.0, 1002.0):
        storage.persist([_evt(EventType.APPEARED, track_id=1, cls_fr="chat", ts=ts)])
    storage.persist([_evt(EventType.APPEARED, track_id=2, cls_fr="chat", ts=1100.0)])

    count = storage.count_distinct("chat", since_ts=0.0, until_ts=9999.0)
    assert count == 2


def test_get_current_objects_present(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([
        _evt(EventType.APPEARED, track_id=1, cls_fr="téléphone"),
        _evt(EventType.APPEARED, track_id=2, cls_fr="chat"),
    ])
    storage.persist([_evt(EventType.DISAPPEARED, track_id=2, cls_fr="chat", ts=1010.0)])

    current = storage.get_current_objects()
    classes = sorted([o["class_fr"] for o in current])
    assert classes == ["téléphone"]


def test_cleanup_removes_old_events(temp_db_path, mock_memory_manager):
    storage = _VisionStorage(db_path=temp_db_path, memory_manager=mock_memory_manager)
    storage.persist([_evt(EventType.APPEARED, track_id=1, ts=1.0)])
    storage.persist([_evt(EventType.APPEARED, track_id=2, ts=time.time())])

    deleted = storage.cleanup_older_than(retention_days=30)
    assert deleted == 1

    conn = sqlite3.connect(temp_db_path)
    remaining = conn.execute("SELECT COUNT(*) FROM object_events").fetchone()[0]
    assert remaining == 1
```

- [ ] **Step 2 : Lancer les tests → échec attendu**

Run : `pytest backend/tests/test_vision_storage.py -v`
Expected : FAIL `ModuleNotFoundError`

- [ ] **Step 3 : Implémentation**

Créer `backend/vision_storage.py` :

```python
"""Stockage transactionnel des events vision (SQLite + ChromaDB).

SQLite → factuel (compte, time-range, classe).
ChromaDB → sémantique (recherche floue : "où j'ai laissé un truc rouge").
Une seule méthode publique d'écriture (`persist`) pour garantir la cohérence.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from backend.vision_deduplicator import EventType, ObjectEvent

_LOG = logging.getLogger("vision_object")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS object_events (
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    source          TEXT NOT NULL,
    timestamp       REAL NOT NULL,
    timestamp_iso   TEXT NOT NULL,
    class_id        INTEGER NOT NULL,
    class_name      TEXT NOT NULL,
    class_fr        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    bbox_x          REAL NOT NULL,
    bbox_y          REAL NOT NULL,
    bbox_w          REAL NOT NULL,
    bbox_h          REAL NOT NULL,
    track_id        INTEGER,
    location_hint   TEXT,
    metadata_json   TEXT
);

CREATE TABLE IF NOT EXISTS current_objects (
    track_id        INTEGER PRIMARY KEY,
    class_name      TEXT NOT NULL,
    class_fr        TEXT NOT NULL,
    source          TEXT NOT NULL,
    last_seen       REAL NOT NULL,
    bbox_x          REAL NOT NULL,
    bbox_y          REAL NOT NULL,
    bbox_w          REAL NOT NULL,
    bbox_h          REAL NOT NULL,
    confidence      REAL NOT NULL,
    is_present      INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_events_class_time   ON object_events(class_fr, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_time         ON object_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_source_time  ON object_events(source, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_current_class       ON current_objects(class_fr);
"""


class _VisionStorage:
    """Stockage SQLite + ChromaDB. Tolère un memory_manager sans `vision_collection`."""

    def __init__(self, db_path: str, memory_manager: Any | None) -> None:
        self._db_path = db_path
        self._memory = memory_manager
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def persist(self, events: list[ObjectEvent]) -> None:
        """Persiste un batch d'events. Skip silencieusement si SQLite locked
        après 3 retries. Indexe Chroma uniquement pour APPEARED + MOVED."""
        if not events:
            return

        for attempt in range(3):
            try:
                with self._connect() as conn:
                    for evt in events:
                        self._insert_event(conn, evt)
                        self._upsert_current(conn, evt)
                break
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() and attempt < 2:
                    time.sleep(0.01 * (10 ** attempt))
                    continue
                _LOG.warning("[VISION_OBJ] SQLite persist failed: %s", exc)
                return

        # Indexation Chroma (best-effort, n'interrompt pas si échec)
        if self._memory is not None and getattr(self._memory, "vision_collection", None) is not None:
            for evt in events:
                if evt.event_type in (EventType.APPEARED, EventType.MOVED):
                    self._index_chroma(evt)

    def _insert_event(self, conn: sqlite3.Connection, evt: ObjectEvent) -> None:
        iso = datetime.fromtimestamp(evt.timestamp, tz=timezone.utc).isoformat()
        xc, yc, w, h = evt.detection.bbox
        conn.execute(
            """INSERT OR REPLACE INTO object_events (
                event_id, event_type, source, timestamp, timestamp_iso,
                class_id, class_name, class_fr, confidence,
                bbox_x, bbox_y, bbox_w, bbox_h,
                track_id, location_hint, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evt.event_id, evt.event_type.value, evt.source,
                evt.timestamp, iso,
                evt.detection.class_id, evt.detection.class_name, evt.detection.class_fr,
                evt.detection.confidence,
                xc, yc, w, h,
                evt.track_id, evt.location_hint, json.dumps(evt.metadata or {}),
            ),
        )

    def _upsert_current(self, conn: sqlite3.Connection, evt: ObjectEvent) -> None:
        if evt.track_id is None:
            return
        xc, yc, w, h = evt.detection.bbox
        if evt.event_type == EventType.DISAPPEARED:
            conn.execute(
                "UPDATE current_objects SET is_present = 0, last_seen = ? WHERE track_id = ?",
                (evt.timestamp, evt.track_id),
            )
            return
        conn.execute(
            """INSERT INTO current_objects (
                track_id, class_name, class_fr, source, last_seen,
                bbox_x, bbox_y, bbox_w, bbox_h, confidence, is_present
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(track_id) DO UPDATE SET
                class_name = excluded.class_name,
                class_fr = excluded.class_fr,
                source = excluded.source,
                last_seen = excluded.last_seen,
                bbox_x = excluded.bbox_x, bbox_y = excluded.bbox_y,
                bbox_w = excluded.bbox_w, bbox_h = excluded.bbox_h,
                confidence = excluded.confidence,
                is_present = 1""",
            (
                evt.track_id, evt.detection.class_name, evt.detection.class_fr,
                evt.source, evt.timestamp,
                xc, yc, w, h, evt.detection.confidence,
            ),
        )

    def _index_chroma(self, evt: ObjectEvent) -> None:
        try:
            xc, yc, w, h = evt.detection.bbox
            iso = datetime.fromtimestamp(evt.timestamp, tz=timezone.utc).isoformat()
            doc = (
                f"{evt.detection.class_fr} vu sur {evt.source} à {iso} "
                f"position ({xc:.2f}, {yc:.2f}) confiance {evt.detection.confidence:.2f}"
            )
            self._memory.vision_collection.add(
                ids=[evt.event_id],
                documents=[doc],
                metadatas=[{
                    "class_name": evt.detection.class_name,
                    "class_fr": evt.detection.class_fr,
                    "source": evt.source,
                    "timestamp": evt.timestamp,
                    "track_id": evt.track_id if evt.track_id is not None else -1,
                    "bbox": json.dumps([xc, yc, w, h]),
                }],
            )
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] Chroma index failed: %s", exc)

    def query_by_class(
        self, class_fr: str, since_ts: float, max_results: int = 10,
    ) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT event_id, event_type, source, timestamp, timestamp_iso,
                          class_fr, confidence, bbox_x, bbox_y, bbox_w, bbox_h,
                          track_id, location_hint
                   FROM object_events
                   WHERE class_fr LIKE ? AND timestamp >= ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (f"%{class_fr}%", since_ts, max_results),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_distinct(
        self, class_fr: str, since_ts: float, until_ts: float,
    ) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT COUNT(DISTINCT track_id) FROM object_events
                   WHERE class_fr LIKE ? AND event_type = 'appeared'
                     AND timestamp >= ? AND timestamp <= ?""",
                (f"%{class_fr}%", since_ts, until_ts),
            ).fetchone()
            return int(row[0]) if row else 0

    def get_current_objects(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT track_id, class_fr, source, last_seen,
                          bbox_x, bbox_y, bbox_w, bbox_h, confidence
                   FROM current_objects WHERE is_present = 1
                   ORDER BY last_seen DESC"""
            ).fetchall()
            return [dict(r) for r in rows]

    def cleanup_older_than(self, retention_days: int) -> int:
        cutoff = time.time() - retention_days * 86400.0
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM object_events WHERE timestamp < ?", (cutoff,))
            deleted = cur.rowcount
            conn.execute(
                "DELETE FROM current_objects WHERE is_present = 0 AND last_seen < ?",
                (cutoff,),
            )
            conn.execute("VACUUM")
            return deleted
```

- [ ] **Step 4 : Relancer les tests → succès attendu**

Run : `pytest backend/tests/test_vision_storage.py -v`
Expected : 8 passed

- [ ] **Step 5 : Commit**

```bash
git add backend/vision_storage.py backend/tests/test_vision_storage.py
git commit -m "feat(vision): add SQLite+Chroma storage with transactional persist + cleanup"
```

---

### Task 7 : Collection ChromaDB `vision_objects` dans `memory_manager.py`

**Files:**
- Modify: `backend/memory_manager.py`

- [ ] **Step 1 : Lire le code actuel de `memory_manager.py`**

Run : `grep -n "client.get_or_create_collection\|class MemoryManager\|def __init__" "backend/memory_manager.py" | head -20`
Identifier où sont créées les collections existantes (probablement dans `MemoryManager.__init__`).

- [ ] **Step 2 : Ajouter la collection `vision_objects` à l'init**

Localiser dans `MemoryManager.__init__()` (après création des collections existantes type `personal_memory`) et ajouter :

```python
        # Collection pour la couche vision objet (YOLO)
        # On ne plante PAS si l'init échoue : la couche vision sait fonctionner sans Chroma.
        try:
            self.vision_collection = self.client.get_or_create_collection(
                name="vision_objects",
                embedding_function=self._embedding_func,
            )
        except Exception as exc:
            print(f"[MEMORY] vision_objects collection init failed: {exc}")
            self.vision_collection = None
```

(Adapter `self._embedding_func` au vrai nom utilisé dans le fichier — peut être `self.embedding_function` ou similaire.)

- [ ] **Step 3 : Vérification manuelle**

Run : `python -c "from backend.memory_manager import MemoryManager; m = MemoryManager(); print(m.vision_collection)"`
Expected : Affichage de l'objet Collection (non None)

- [ ] **Step 4 : Commit**

```bash
git add backend/memory_manager.py
git commit -m "feat(memory): add vision_objects ChromaDB collection (tolerant to init failure)"
```

---

### Task 8 : `MultiUserFaceDetector.get_last_frame()` (micro-mod)

**Files:**
- Modify: `backend/authenticator.py`

- [ ] **Step 1 : Repérer la classe `MultiUserFaceDetector`**

Run : `grep -n "class MultiUserFaceDetector\|def detect\|def __init__" "backend/authenticator.py" | head`
Lire les 30 lignes suivantes pour identifier `__init__` et `detect()`.

- [ ] **Step 2 : Ajouter l'attribut `_last_frame` dans `__init__`**

Ajouter en fin de `__init__` de `MultiUserFaceDetector` :

```python
        # Frame BGR la plus récente, partagée avec la couche vision objet (YOLO)
        # pour éviter d'ouvrir une 2e capture webcam (incompatible macOS).
        self._last_frame = None  # type: np.ndarray | None
```

(S'assurer qu'`import numpy as np` est en haut du fichier — déjà présent côté MediaPipe normalement.)

- [ ] **Step 3 : Stocker la frame en première ligne de `detect()`**

Au début du corps de `detect(self, frame_bgr)` :

```python
        # Partagé avec VisionObjectAgent — pas de seconde capture webcam.
        try:
            self._last_frame = frame_bgr.copy() if frame_bgr is not None else None
        except Exception:
            self._last_frame = None
        # ... reste du corps existant inchangé
```

- [ ] **Step 4 : Ajouter la méthode `get_last_frame()`**

Ajouter à la fin de la classe `MultiUserFaceDetector` :

```python
    def get_last_frame(self):
        """Renvoie la dernière frame BGR capturée par MediaPipe (peut être None)."""
        return self._last_frame
```

- [ ] **Step 5 : Vérification — aucune régression**

Run : `python -c "from backend.authenticator import MultiUserFaceDetector; print(hasattr(MultiUserFaceDetector, 'get_last_frame'))"`
Expected : `True`

- [ ] **Step 6 : Commit**

```bash
git add backend/authenticator.py
git commit -m "feat(authenticator): expose get_last_frame() for YOLO frame sharing"
```

---

### Task 9 : `VisionObjectAgent` skeleton + singleton + mode PULL

**Files:**
- Create: `backend/vision_object_agent.py`
- Create: `backend/tests/test_vision_object_agent.py`

- [ ] **Step 1 : Écrire les tests d'abord**

Créer `backend/tests/test_vision_object_agent.py` :

```python
"""Tests du VisionObjectAgent (orchestration + mode PULL + throttling)."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from backend.yolo_detector import Detection
from backend.vision_object_agent import VisionObjectAgent, _classify_risk
from backend.vision_deduplicator import EventType, ObjectEvent


def _det(track_id=1, cls_fr="téléphone", conf=0.9, cls_name="Mobile phone"):
    return Detection(
        class_id=0, class_name=cls_name, class_fr=cls_fr,
        confidence=conf, bbox=(0.5, 0.5, 0.1, 0.1), track_id=track_id,
    )


def _evt(event_type=EventType.APPEARED, cls_fr="téléphone", cls_name="Mobile phone"):
    return ObjectEvent(
        event_id="x", event_type=event_type, source="camera", timestamp=1000.0,
        detection=_det(cls_fr=cls_fr, cls_name=cls_name),
        track_id=1,
    )


@pytest.fixture(autouse=True)
def _reset_singleton():
    VisionObjectAgent._singleton = None
    yield
    VisionObjectAgent._singleton = None


def test_singleton_returns_same_instance(mock_memory_manager, temp_db_path):
    with patch("backend.vision_object_agent.YoloDetector"):
        a1 = VisionObjectAgent.get_or_create_singleton(
            memory_manager=mock_memory_manager, db_path=temp_db_path,
        )
        a2 = VisionObjectAgent.get_or_create_singleton(
            memory_manager=mock_memory_manager, db_path=temp_db_path,
        )
    assert a1 is a2


async def test_detect_on_demand_returns_french_summary(mock_memory_manager, temp_db_path, fake_frame_bgr):
    with patch("backend.vision_object_agent.YoloDetector") as MockDetector:
        MockDetector.return_value.detect = MagicMock(return_value=[
            _det(track_id=1, cls_fr="téléphone", conf=0.91),
            _det(track_id=2, cls_fr="chat", cls_name="Cat", conf=0.85),
        ])
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=fake_frame_bgr)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.detect_on_demand(source="camera", filter_class=None, max_results=10)

    assert isinstance(result, str)
    assert "téléphone" in result
    assert "chat" in result


async def test_detect_on_demand_filters_by_class(mock_memory_manager, temp_db_path, fake_frame_bgr):
    with patch("backend.vision_object_agent.YoloDetector") as MockDetector:
        MockDetector.return_value.detect = MagicMock(return_value=[
            _det(track_id=1, cls_fr="téléphone"),
            _det(track_id=2, cls_fr="chat", cls_name="Cat"),
        ])
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=fake_frame_bgr)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.detect_on_demand(source="camera", filter_class="chat", max_results=10)

    assert "chat" in result
    assert "téléphone" not in result


async def test_detect_on_demand_returns_message_when_no_frame(mock_memory_manager, temp_db_path):
    with patch("backend.vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=None)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.detect_on_demand(source="camera", filter_class=None, max_results=10)

    assert isinstance(result, str)
    assert "pas" in result.lower() or "indispon" in result.lower()


async def test_throttling_per_class(mock_memory_manager, temp_db_path):
    """Même classe envoyée 5x rapidement → callback brain appelé 1 seule fois."""
    callback = MagicMock(return_value=asyncio.sleep(0))

    with patch("backend.vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
            on_object_event=callback,
            brain_throttle_sec=10.0,  # gros throttle pour le test
        )
        for _ in range(5):
            await agent._propagate_to_brain(_evt(EventType.APPEARED, cls_fr="livre"))

    assert callback.call_count == 1


async def test_high_priority_class_bypasses_throttling(mock_memory_manager, temp_db_path):
    """Person/Cat/Dog/Fire/Knife/Gun → toujours propagé."""
    callback = MagicMock(return_value=asyncio.sleep(0))

    with patch("backend.vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
            on_object_event=callback,
            brain_throttle_sec=10.0,
        )
        for _ in range(3):
            await agent._propagate_to_brain(_evt(EventType.APPEARED, cls_fr="chat", cls_name="Cat"))

    assert callback.call_count == 3


def test_classify_risk_fire_is_high():
    assert _classify_risk(_evt(cls_fr="feu", cls_name="Fire")) == "high"


def test_classify_risk_phone_is_none():
    assert _classify_risk(_evt(cls_fr="téléphone", cls_name="Mobile phone")) == "none"


async def test_query_history_returns_string(mock_memory_manager, temp_db_path):
    with patch("backend.vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.query_history(object_query="téléphone", since=None, max_results=5)
    assert isinstance(result, str)


async def test_count_seen_returns_string(mock_memory_manager, temp_db_path):
    with patch("backend.vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        result = await agent.count_seen(object_class="chat", period="today")
    assert isinstance(result, str)
```

- [ ] **Step 2 : Lancer les tests → échec attendu**

Run : `pytest backend/tests/test_vision_object_agent.py -v`
Expected : FAIL `ModuleNotFoundError: No module named 'backend.vision_object_agent'`

- [ ] **Step 3 : Implémentation**

Créer `backend/vision_object_agent.py` :

```python
"""Agent asyncio orchestrant la couche vision objet (YOLO).

Trois rôles :
  1. Mode PULL — tools Gemini one-shot (detect_objects / query / count)
  2. Mode PUSH — boucles caméra + écran qui propagent au brain SNN
  3. Singleton inter-modules — partagé entre ada.py (voix) et external_bridge.py (texte)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

import numpy as np

from backend.vision_deduplicator import (
    DedupConfig,
    EventType,
    ObjectEvent,
    _DetectionDeduplicator,
)
from backend.vision_storage import _VisionStorage
from backend.yolo_detector import YoloDetector

_LOG = logging.getLogger("vision_object")

HIGH_PRIORITY_CLASSES_EN: set[str] = {
    "Person", "Cat", "Dog", "Fire", "Knife", "Gun", "Pistol",
}
HIGH_RISK_CLASSES_EN: set[str] = {"Fire", "Knife", "Gun", "Pistol"}
DEFAULT_DB_PATH = "backend/memory/vision_timeline.db"


def _classify_risk(event: ObjectEvent) -> str:
    if event.detection.class_name in HIGH_RISK_CLASSES_EN:
        return "high"
    if event.detection.class_name in {"Person", "Cat", "Dog"} and event.event_type == EventType.APPEARED:
        return "low"
    return "none"


def _classify_attention(event: ObjectEvent) -> float:
    if event.detection.class_name in HIGH_RISK_CLASSES_EN:
        return 0.9
    if event.detection.class_name in HIGH_PRIORITY_CLASSES_EN:
        return 0.5
    if event.event_type == EventType.MOVED:
        return 0.3
    return 0.1


def _classify_movement(event: ObjectEvent) -> float:
    return 0.6 if event.event_type == EventType.MOVED else 0.2


def _hint_for(event: ObjectEvent) -> str:
    return f"{event.detection.class_fr} {event.event_type.value} sur {event.source}"


class VisionObjectAgent:
    """Singleton orchestrant les détections YOLO."""

    _singleton: "VisionObjectAgent | None" = None

    @classmethod
    def get_or_create_singleton(
        cls,
        memory_manager: Any | None = None,
        face_frame_source: Any | None = None,
        on_object_event: Callable[[dict], Awaitable[None]] | None = None,
        db_path: str | None = None,
    ) -> "VisionObjectAgent":
        if cls._singleton is None:
            cls._singleton = VisionObjectAgent(
                face_frame_source=face_frame_source,
                memory_manager=memory_manager,
                on_object_event=on_object_event,
                db_path=db_path or DEFAULT_DB_PATH,
            )
        else:
            # Met à jour les hooks si fournis tardivement (ordre AudioLoop/TextAgent variable)
            if face_frame_source is not None and cls._singleton._face_source is None:
                cls._singleton._face_source = face_frame_source
            if on_object_event is not None and cls._singleton._on_event is None:
                cls._singleton._on_event = on_object_event
        return cls._singleton

    @classmethod
    def peek_singleton(cls) -> "VisionObjectAgent | None":
        return cls._singleton

    def __init__(
        self,
        face_frame_source: Any | None,
        memory_manager: Any | None,
        on_object_event: Callable[[dict], Awaitable[None]] | None = None,
        db_path: str = DEFAULT_DB_PATH,
        brain_throttle_sec: float | None = None,
        max_events_per_sec: int | None = None,
    ) -> None:
        self._face_source = face_frame_source
        self._memory = memory_manager
        self._on_event = on_object_event

        self._detector = YoloDetector(
            model_path=os.getenv("VISION_OBJECT_MODEL", "yolov8m-oiv7.pt"),
            device=os.getenv("VISION_OBJECT_DEVICE", "mps"),
            confidence_min=float(os.getenv("VISION_OBJECT_CONFIDENCE", "0.45")),
        )
        self._dedup = _DetectionDeduplicator(DedupConfig())
        self._storage = _VisionStorage(db_path=db_path, memory_manager=memory_manager)

        self._brain_throttle_sec = (
            brain_throttle_sec if brain_throttle_sec is not None
            else float(os.getenv("VISION_OBJECT_BRAIN_THROTTLE_SEC", "1.0"))
        )
        self._max_events_per_sec = (
            max_events_per_sec if max_events_per_sec is not None
            else int(os.getenv("VISION_OBJECT_MAX_EVENTS_PER_SEC", "10"))
        )

        self._last_brain_push_by_class: dict[str, float] = {}
        self._recent_push_ts: deque[float] = deque(maxlen=self._max_events_per_sec)

        self._camera_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None
        self._stopping = False

    # ─────── Mode PULL ───────

    async def detect_on_demand(
        self, source: str = "camera", filter_class: str | None = None, max_results: int = 10,
    ) -> str:
        """One-shot : capture frame → YOLO → réponse FR. Bypass la dédup."""
        try:
            frame = await self._capture_frame(source)
            if frame is None:
                return f"Erreur: pas de frame disponible pour la source '{source}' (caméra ou écran indisponible)."

            detections = await asyncio.to_thread(self._detector.detect, frame)

            if filter_class:
                fc = filter_class.lower()
                detections = [d for d in detections if fc in d.class_fr.lower()]

            if not detections:
                if filter_class:
                    return f"Je ne vois pas de {filter_class} sur la {source}."
                return f"Je ne détecte rien sur la {source}."

            detections = detections[:max_results]
            lines = []
            for d in detections:
                pos = self._bbox_to_position_fr(d.bbox)
                lines.append(f"- {d.class_fr} {pos} (confiance {d.confidence:.2f})")
            header = f"J'identifie {len(detections)} objet(s) sur la {source} :"
            return header + "\n" + "\n".join(lines)

        except Exception as exc:
            _LOG.warning("[VISION_OBJ] detect_on_demand failed: %s", exc)
            return f"Erreur détection: {exc}"

    async def query_history(
        self, object_query: str, since: str | None = None, max_results: int = 5,
    ) -> str:
        try:
            since_ts = self._parse_since(since)
            rows = self._storage.query_by_class(
                class_fr=object_query, since_ts=since_ts, max_results=max_results,
            )
            if not rows:
                return f"Aucune trace de '{object_query}' depuis la période demandée."
            lines = [
                f"- {r['timestamp_iso']} sur {r['source']} (confiance {r['confidence']:.2f})"
                for r in rows
            ]
            return f"J'ai vu '{object_query}' {len(rows)} fois :\n" + "\n".join(lines)
        except Exception as exc:
            return f"Erreur recherche: {exc}"

    async def count_seen(self, object_class: str, period: str = "today") -> str:
        try:
            since_ts, until_ts = self._parse_period(period)
            count = self._storage.count_distinct(
                class_fr=object_class, since_ts=since_ts, until_ts=until_ts,
            )
            return f"J'ai vu {count} fois '{object_class}' sur la période '{period}'."
        except Exception as exc:
            return f"Erreur comptage: {exc}"

    # ─────── Mode PUSH ───────

    async def detect_on_frame_bytes(self, frame_bytes: bytes, source: str) -> None:
        """Greffon utilisé par screen_watcher (fire-and-forget)."""
        try:
            import cv2
            arr = np.frombuffer(frame_bytes, dtype=np.uint8)
            frame_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame_bgr is None:
                return
            await self._process_frame(frame_bgr, source)
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] detect_on_frame_bytes failed: %s", exc)

    async def _process_frame(self, frame_bgr: np.ndarray, source: str) -> None:
        detections = await asyncio.to_thread(self._detector.detect, frame_bgr)
        events = self._dedup.diff(detections, source=source, timestamp=time.time())
        if not events:
            return
        await asyncio.to_thread(self._storage.persist, events)
        for evt in events:
            await self._propagate_to_brain(evt)

    async def _propagate_to_brain(self, event: ObjectEvent) -> None:
        if self._on_event is None:
            return

        now = time.time()
        # Hard cap par seconde (sauf classe haute priorité)
        is_high_priority = event.detection.class_name in HIGH_PRIORITY_CLASSES_EN
        if not is_high_priority and len(self._recent_push_ts) == self._max_events_per_sec:
            oldest = self._recent_push_ts[0]
            if now - oldest < 1.0:
                return

        # Throttling par classe (sauf high-priority)
        if not is_high_priority:
            last = self._last_brain_push_by_class.get(event.detection.class_fr, 0.0)
            if now - last < self._brain_throttle_sec:
                return

        self._last_brain_push_by_class[event.detection.class_fr] = now
        self._recent_push_ts.append(now)

        stimulus = {
            "source": "vision_object",
            "description": f"{event.detection.class_fr} {event.event_type.value}",
            "object_class": event.detection.class_fr,
            "event_type": event.event_type.value,
            "movement": _classify_movement(event),
            "risk": _classify_risk(event),
            "attention_need": _classify_attention(event),
            "valence": 0.0,
            "spontaneous_hint": _hint_for(event),
        }
        try:
            await self._on_event(stimulus)
        except Exception as exc:
            _LOG.warning("[VISION_OBJ] Brain callback failed: %s", exc)

    # ─────── Helpers ───────

    async def _capture_frame(self, source: str) -> np.ndarray | None:
        if source == "camera":
            if self._face_source is None:
                return None
            return self._face_source.get_last_frame()
        if source == "screen":
            try:
                import mss
                import cv2
                with mss.mss() as sct:
                    img = np.array(sct.grab(sct.monitors[1]))
                    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            except Exception as exc:
                _LOG.warning("[VISION_OBJ] Screen capture failed: %s", exc)
                return None
        return None

    @staticmethod
    def _bbox_to_position_fr(bbox: tuple[float, float, float, float]) -> str:
        xc, yc, _, _ = bbox
        horiz = "à gauche" if xc < 0.33 else ("à droite" if xc > 0.66 else "au centre")
        vert = "en haut" if yc < 0.33 else ("en bas" if yc > 0.66 else "")
        return f"{vert} {horiz}".strip()

    @staticmethod
    def _parse_since(since: str | None) -> float:
        if not since:
            return time.time() - 86400.0
        s = since.lower().strip()
        now = time.time()
        if s in {"hier", "yesterday"}:
            return now - 2 * 86400.0
        if s in {"cette semaine", "this_week", "this week"}:
            return now - 7 * 86400.0
        if s in {"dernier mois", "last_month"}:
            return now - 30 * 86400.0
        try:
            return datetime.fromisoformat(since.replace("Z", "+00:00")).timestamp()
        except Exception:
            return now - 86400.0

    @staticmethod
    def _parse_period(period: str) -> tuple[float, float]:
        now = time.time()
        p = (period or "today").lower().strip()
        if p == "today":
            start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            return start.timestamp(), now
        if p == "yesterday":
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_start = today_start - timedelta(days=1)
            return yesterday_start.timestamp(), today_start.timestamp()
        if p == "this_week":
            return now - 7 * 86400.0, now
        if p == "last_24h":
            return now - 86400.0, now
        if p == "last_hour":
            return now - 3600.0, now
        return now - 86400.0, now

    # ─────── Lifecycle (boucles activées dans la Task 14) ───────

    async def start(self) -> None:
        _LOG.info("[VISION_OBJ] Agent started (singleton)")

    async def stop(self) -> None:
        self._stopping = True
        for task in (self._camera_task, self._cleanup_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        _LOG.info("[VISION_OBJ] Agent stopped")
```

- [ ] **Step 4 : Relancer les tests → succès attendu**

Run : `pytest backend/tests/test_vision_object_agent.py -v`
Expected : 10 passed

- [ ] **Step 5 : Commit**

```bash
git add backend/vision_object_agent.py backend/tests/test_vision_object_agent.py
git commit -m "feat(vision): add VisionObjectAgent skeleton with PULL mode + throttling + singleton"
```

---

### Task 10 : Déclarations Gemini des 3 tools

**Files:**
- Modify: `backend/mcp_tools_declarations.py`

- [ ] **Step 1 : Identifier la liste exportée**

Run : `grep -n "MCP_TOOLS\s*=\|tools_list\s*=\|TOOL_DECLS\s*=" "backend/mcp_tools_declarations.py" | head`
Identifier la variable qui agrège les tools (probablement `MCP_TOOLS` ou similaire).

- [ ] **Step 2 : Ajouter les 3 déclarations en haut du fichier (juste avant la liste agrégée)**

```python
# ───── Couche vision objet (YOLO) ────────────────────────────────
detect_objects_tool = {
    "name": "detect_objects",
    "description": (
        "Détecte les objets visibles via YOLO sur la caméra ou l'écran. "
        "Réponse immédiate, ne dépend pas du quota Gemini. "
        "Utilise quand l'utilisateur demande 'tu vois X ?', 'qu'est-ce qu'il y a sur mon bureau', "
        "'qu'est-ce que je tiens', ou pour vérifier la présence d'un objet précis."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "source": {
                "type": "STRING",
                "description": "'camera' (webcam) ou 'screen' (capture écran). Défaut: 'camera'.",
            },
            "filter": {
                "type": "STRING",
                "description": "Optionnel. Nom de classe FR à filtrer (ex: 'téléphone'). Vide = toutes classes.",
            },
            "max_results": {
                "type": "INTEGER",
                "description": "Nombre max de détections. Défaut: 10.",
            },
        },
        "required": [],
    },
}

query_seen_objects_tool = {
    "name": "query_seen_objects",
    "description": (
        "Recherche dans l'historique des objets vus (SQLite + ChromaDB). "
        "Utilise pour 'où j'ai laissé X', 'quand j'ai vu X pour la dernière fois'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "object": {"type": "STRING", "description": "Description FR de l'objet (peut être flou)."},
            "since": {"type": "STRING", "description": "Optionnel. ISO ou relatif ('hier', 'cette semaine'). Défaut: 24h."},
            "max_results": {"type": "INTEGER", "description": "Défaut: 5."},
        },
        "required": ["object"],
    },
}

count_objects_seen_tool = {
    "name": "count_objects_seen",
    "description": (
        "Compte le nombre de fois qu'un objet a été vu sur une période. "
        "Compte par track_id distinct (3 passages du chat = 3, pas 47 frames)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "object": {"type": "STRING", "description": "Classe FR à compter (ex: 'chat', 'téléphone')."},
            "period": {
                "type": "STRING",
                "description": "'today'|'yesterday'|'this_week'|'last_24h'|'last_hour'. Défaut: 'today'.",
            },
        },
        "required": ["object"],
    },
}
```

- [ ] **Step 3 : Ajouter les 3 tools à la liste agrégée**

Repérer la liste agrégée (ex: `MCP_TOOLS = [...]`) et y ajouter en fin :

```python
    detect_objects_tool,
    query_seen_objects_tool,
    count_objects_seen_tool,
```

- [ ] **Step 4 : Vérification — import sans erreur**

Run : `python -c "from backend.mcp_tools_declarations import detect_objects_tool, query_seen_objects_tool, count_objects_seen_tool; print('OK')"`
Expected : `OK`

- [ ] **Step 5 : Commit**

```bash
git add backend/mcp_tools_declarations.py
git commit -m "feat(tools): add Gemini declarations for detect_objects + query + count"
```

---

### Task 11 : Wiring des 3 tools dans `ada.py` (voix Live API)

**Files:**
- Modify: `backend/ada.py`

- [ ] **Step 1 : Repérer la classe `AudioLoop` et `_execute_text_tool`**

Run : `grep -n "class AudioLoop\|def _execute_text_tool\|def __init__" "backend/ada.py" | head -20`
Lire les 40 lignes autour de chaque hit.

- [ ] **Step 2 : Ajouter l'import + attribut dans `AudioLoop.__init__`**

En haut du fichier (avec les autres imports) :

```python
from backend.vision_object_agent import VisionObjectAgent
```

Dans `AudioLoop.__init__` (en fin) :

```python
        self._vision_agent: VisionObjectAgent | None = None
```

- [ ] **Step 3 : Ajouter le helper d'instanciation lazy**

Ajouter comme méthode de `AudioLoop` (juste avant `_execute_text_tool`) :

```python
    async def _ensure_vision_agent(self) -> VisionObjectAgent:
        """Lazy-init du singleton VisionObjectAgent (partage la frame avec MediaPipe)."""
        if self._vision_agent is None:
            face_source = getattr(self, "_face_detector", None)
            self._vision_agent = await asyncio.to_thread(
                VisionObjectAgent.get_or_create_singleton,
                memory_manager=self.memory,
                face_frame_source=face_source,
                on_object_event=self._on_vision_object_event,
            )
            await self._vision_agent.start()
        return self._vision_agent

    async def _on_vision_object_event(self, stimulus: dict) -> None:
        """Pont vers le brain SNN (additif, ne casse pas on_scene_event)."""
        brain = getattr(self, "_brain", None)
        if brain is not None and hasattr(brain, "ingest_stimulus"):
            try:
                await brain.ingest_stimulus(stimulus)
            except Exception as exc:
                print(f"[VISION_OBJ] brain.ingest_stimulus failed: {exc}")
```

- [ ] **Step 4 : Ajouter les 3 branches dans `_execute_text_tool`**

Localiser le `switch/case` de `_execute_text_tool` (chaînes `elif n == "..."`) et ajouter avant la branche `Outil inconnu` :

```python
        elif n == "detect_objects":
            agent = await self._ensure_vision_agent()
            return await agent.detect_on_demand(
                source=args.get("source", "camera"),
                filter_class=args.get("filter") or None,
                max_results=int(args.get("max_results", 10)),
            )
        elif n == "query_seen_objects":
            agent = await self._ensure_vision_agent()
            return await agent.query_history(
                object_query=args.get("object", ""),
                since=args.get("since"),
                max_results=int(args.get("max_results", 5)),
            )
        elif n == "count_objects_seen":
            agent = await self._ensure_vision_agent()
            return await agent.count_seen(
                object_class=args.get("object", ""),
                period=args.get("period", "today"),
            )
```

- [ ] **Step 5 : Vérification — import sans erreur**

Run : `python -c "import backend.ada; print('OK')"`
Expected : `OK` (peut afficher des warnings d'init Gemini sans clé, mais l'import doit passer)

- [ ] **Step 6 : Commit**

```bash
git add backend/ada.py
git commit -m "feat(ada): wire detect_objects/query_seen/count tools in voice Live API"
```

---

### Task 12 : Wiring des 3 tools dans `external_bridge.py` (Telegram/WhatsApp)

**Files:**
- Modify: `backend/external_bridge.py`

- [ ] **Step 1 : Repérer `TextAgent` et `_execute_tool`**

Run : `grep -n "class TextAgent\|def _execute_tool\|def __init__" "backend/external_bridge.py" | head -20`

- [ ] **Step 2 : Ajouter l'import + attribut dans `TextAgent.__init__`**

En haut du fichier (avec les autres imports) :

```python
from backend.vision_object_agent import VisionObjectAgent
```

Dans `TextAgent.__init__` (en fin) :

```python
        self._vision_agent: VisionObjectAgent | None = None
```

- [ ] **Step 3 : Ajouter le helper d'instanciation lazy (singleton inter-modules)**

Ajouter dans `TextAgent` juste avant `_execute_tool` :

```python
    async def _ensure_vision_agent(self) -> VisionObjectAgent:
        """Récupère le singleton VisionObjectAgent (partagé avec AudioLoop)."""
        if self._vision_agent is None:
            self._vision_agent = await asyncio.to_thread(
                VisionObjectAgent.get_or_create_singleton,
                memory_manager=getattr(self, "memory", None),
            )
        return self._vision_agent
```

- [ ] **Step 4 : Ajouter les 3 branches dans `_execute_tool`**

Insérer avant la branche `Outil inconnu` (les mêmes que dans `ada.py`) :

```python
        elif name == "detect_objects":
            agent = await self._ensure_vision_agent()
            return await agent.detect_on_demand(
                source=args.get("source", "camera"),
                filter_class=args.get("filter") or None,
                max_results=int(args.get("max_results", 10)),
            )
        elif name == "query_seen_objects":
            agent = await self._ensure_vision_agent()
            return await agent.query_history(
                object_query=args.get("object", ""),
                since=args.get("since"),
                max_results=int(args.get("max_results", 5)),
            )
        elif name == "count_objects_seen":
            agent = await self._ensure_vision_agent()
            return await agent.count_seen(
                object_class=args.get("object", ""),
                period=args.get("period", "today"),
            )
```

- [ ] **Step 5 : Vérification**

Run : `python -c "import backend.external_bridge; print('OK')"`
Expected : `OK`

- [ ] **Step 6 : Commit**

```bash
git add backend/external_bridge.py
git commit -m "feat(bridge): wire vision object tools in Telegram/WhatsApp TextAgent"
```

---

### Task 13 : Lifecycle FastAPI dans `server.py`

**Files:**
- Modify: `backend/server.py`

- [ ] **Step 1 : Repérer les hooks FastAPI existants**

Run : `grep -n "on_event\|@app.on\|lifespan" "backend/server.py" | head`
Identifier le pattern utilisé (startup/shutdown ou lifespan moderne).

- [ ] **Step 2 : Ajouter les hooks startup/shutdown**

Ajouter dans `backend/server.py` (à un endroit approprié, près des autres `@app.on_event`) :

```python
@app.on_event("startup")
async def _startup_vision_object_agent() -> None:
    if os.getenv("VISION_OBJECT_ENABLED", "false").lower() == "true":
        try:
            from backend.vision_object_agent import VisionObjectAgent
            VisionObjectAgent.get_or_create_singleton(memory_manager=memory)
            print("[SERVER] VisionObjectAgent singleton initialized")
        except Exception as exc:
            print(f"[SERVER] VisionObjectAgent init failed: {exc}")


@app.on_event("shutdown")
async def _shutdown_vision_object_agent() -> None:
    try:
        from backend.vision_object_agent import VisionObjectAgent
        agent = VisionObjectAgent.peek_singleton()
        if agent is not None:
            await agent.stop()
    except Exception as exc:
        print(f"[SERVER] VisionObjectAgent shutdown failed: {exc}")
```

S'assurer qu'`import os` est déjà présent en haut du fichier (sinon l'ajouter). Adapter `memory` au nom réel de l'instance MemoryManager dans `server.py`.

- [ ] **Step 3 : Vérification — démarrage avec switch=false**

Run : `VISION_OBJECT_ENABLED=false python -c "import backend.server; print('server import OK')"`
Expected : `server import OK` (aucun import de YoloDetector)

- [ ] **Step 4 : Commit**

```bash
git add backend/server.py
git commit -m "feat(server): add FastAPI lifecycle for VisionObjectAgent (env-gated)"
```

---

### Task 14 : Boucle PUSH caméra (10 fps continu)

**Files:**
- Modify: `backend/vision_object_agent.py`
- Modify: `backend/tests/test_vision_object_agent.py`

- [ ] **Step 1 : Écrire les tests d'abord**

Ajouter à la fin de `backend/tests/test_vision_object_agent.py` :

```python
async def test_camera_loop_calls_detector_when_frame_available(mock_memory_manager, temp_db_path, fake_frame_bgr):
    """Boucle camera : au moins 1 inférence si la frame est disponible."""
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[])

    with patch("backend.vision_object_agent.YoloDetector", return_value=detector):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=fake_frame_bgr)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )

        await agent.start_camera_loop(fps=20)
        await asyncio.sleep(0.2)
        await agent.stop()

    assert detector.detect.call_count >= 1


async def test_camera_loop_skips_when_frame_is_none(mock_memory_manager, temp_db_path):
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[])

    with patch("backend.vision_object_agent.YoloDetector", return_value=detector):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=None)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        await agent.start_camera_loop(fps=20)
        await asyncio.sleep(0.15)
        await agent.stop()

    # Aucune inférence car frame None
    assert detector.detect.call_count == 0


async def test_camera_loop_does_not_double_start(mock_memory_manager, temp_db_path, fake_frame_bgr):
    detector = MagicMock()
    detector.detect = MagicMock(return_value=[])

    with patch("backend.vision_object_agent.YoloDetector", return_value=detector):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(get_last_frame=MagicMock(return_value=fake_frame_bgr)),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        await agent.start_camera_loop(fps=10)
        first_task = agent._camera_task
        await agent.start_camera_loop(fps=10)
        assert agent._camera_task is first_task
        await agent.stop()
```

- [ ] **Step 2 : Lancer les tests → échec attendu**

Run : `pytest backend/tests/test_vision_object_agent.py::test_camera_loop_calls_detector_when_frame_available -v`
Expected : FAIL (`start_camera_loop` n'existe pas encore)

- [ ] **Step 3 : Implémenter `start_camera_loop` dans `VisionObjectAgent`**

Remplacer la section `# ─────── Lifecycle ───────` à la fin de `vision_object_agent.py` par :

```python
    # ─────── Lifecycle ───────

    async def start(self) -> None:
        _LOG.info("[VISION_OBJ] Agent started (singleton)")
        if os.getenv("VISION_OBJECT_CAMERA_LOOP", "true").lower() == "true":
            fps = int(os.getenv("VISION_OBJECT_FPS", "10"))
            await self.start_camera_loop(fps=fps)

    async def start_camera_loop(self, fps: int = 10) -> None:
        """Démarre la boucle continue sur la caméra (partagée avec MediaPipe)."""
        if self._camera_task is not None and not self._camera_task.done():
            return
        period = 1.0 / max(1, fps)
        self._stopping = False
        self._camera_task = asyncio.create_task(self._run_camera_loop(period))
        _LOG.info("[VISION_OBJ] Camera loop started (period=%.3fs, fps=%d)", period, fps)

    async def _run_camera_loop(self, period: float) -> None:
        while not self._stopping:
            tick_start = time.monotonic()
            try:
                frame = None
                if self._face_source is not None:
                    frame = self._face_source.get_last_frame()
                if frame is None:
                    await asyncio.sleep(period)
                    continue
                await self._process_frame(frame, source="camera")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning("[VISION_OBJ] Camera loop tick failed: %s", exc)
            elapsed = time.monotonic() - tick_start
            sleep_for = max(0.0, period - elapsed)
            await asyncio.sleep(sleep_for)

    async def stop(self) -> None:
        self._stopping = True
        for task in (self._camera_task, self._cleanup_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
        _LOG.info("[VISION_OBJ] Agent stopped")
```

(La politique "drop si inférence en retard" est implicite : `asyncio.to_thread` libère la boucle, mais le `tick_start` re-mesure à chaque itération — si l'inférence prend > period, on n'attend pas, on enchaîne immédiatement.)

- [ ] **Step 4 : Relancer les tests → succès attendu**

Run : `pytest backend/tests/test_vision_object_agent.py -v`
Expected : 13 passed

- [ ] **Step 5 : Commit**

```bash
git add backend/vision_object_agent.py backend/tests/test_vision_object_agent.py
git commit -m "feat(vision): add continuous camera loop with idempotent start"
```

---

### Task 15 : Greffon PUSH écran dans `screen_watcher.py`

**Files:**
- Modify: `backend/screen_watcher.py`

- [ ] **Step 1 : Repérer la méthode qui analyse une frame**

Run : `grep -n "def _analyze_frame\|analyze_visual_scene\|class ScreenWatcher\|frame_bytes" "backend/screen_watcher.py" | head`
Identifier où est l'appel Gemini après capture et le nom de la variable `frame_bytes`.

- [ ] **Step 2 : Ajouter le greffon fire-and-forget**

Après l'appel `analyze_visual_scene(...)` existant, ajouter (en gardant l'appel Gemini intact) :

```python
        # Greffon couche vision objet (YOLO) — fire-and-forget, n'interrompt pas Gemini
        if os.getenv("VISION_OBJECT_ENABLED", "false").lower() == "true" \
           and os.getenv("VISION_OBJECT_SCREEN_LOOP", "true").lower() == "true":
            try:
                from backend.vision_object_agent import VisionObjectAgent
                agent = VisionObjectAgent.peek_singleton()
                if agent is not None:
                    asyncio.create_task(
                        agent.detect_on_frame_bytes(frame_bytes, source="screen")
                    )
            except Exception as exc:
                print(f"[VISION_OBJ] screen greffon failed: {exc}")
```

Vérifier que `frame_bytes` est bien le nom de variable utilisé. Sinon, adapter à la variable réelle (ex: `jpeg_bytes`).
S'assurer qu'`import os` et `import asyncio` sont en haut du fichier.

- [ ] **Step 3 : Vérification — import sans erreur**

Run : `python -c "import backend.screen_watcher; print('OK')"`
Expected : `OK`

- [ ] **Step 4 : Commit**

```bash
git add backend/screen_watcher.py
git commit -m "feat(screen_watcher): add fire-and-forget YOLO graft alongside Gemini scene"
```

---

### Task 16 : Cleanup nocturne (boucle asyncio interne)

**Files:**
- Modify: `backend/vision_object_agent.py`
- Modify: `backend/tests/test_vision_object_agent.py`

- [ ] **Step 1 : Écrire le test d'abord**

Ajouter à la fin de `backend/tests/test_vision_object_agent.py` :

```python
async def test_cleanup_loop_triggers_storage_cleanup(mock_memory_manager, temp_db_path):
    with patch("backend.vision_object_agent.YoloDetector"):
        agent = VisionObjectAgent(
            face_frame_source=MagicMock(),
            memory_manager=mock_memory_manager,
            db_path=temp_db_path,
        )
        agent._storage = MagicMock()
        agent._storage.cleanup_older_than = MagicMock(return_value=42)

        # Force le déclenchement immédiat (sans attendre 4h du matin)
        await agent.start_cleanup_loop(interval_sec=0.05, retention_days=30)
        await asyncio.sleep(0.15)
        await agent.stop()

    assert agent._storage.cleanup_older_than.call_count >= 1
```

- [ ] **Step 2 : Lancer le test → échec attendu**

Run : `pytest backend/tests/test_vision_object_agent.py::test_cleanup_loop_triggers_storage_cleanup -v`
Expected : FAIL (`start_cleanup_loop` n'existe pas)

- [ ] **Step 3 : Implémenter la boucle cleanup**

Ajouter dans `VisionObjectAgent` (avant `stop()`) :

```python
    async def start_cleanup_loop(
        self, interval_sec: float = 86400.0, retention_days: int | None = None,
    ) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            return
        retention = (
            retention_days if retention_days is not None
            else int(os.getenv("VISION_OBJECT_RETENTION_DAYS", "30"))
        )
        self._stopping = False
        self._cleanup_task = asyncio.create_task(
            self._run_cleanup_loop(interval_sec=interval_sec, retention_days=retention)
        )

    async def _run_cleanup_loop(self, interval_sec: float, retention_days: int) -> None:
        while not self._stopping:
            try:
                deleted = await asyncio.to_thread(
                    self._storage.cleanup_older_than, retention_days
                )
                _LOG.info(
                    "[VISION_OBJ] Nightly cleanup: %d events purged (retention=%dd)",
                    deleted, retention_days,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _LOG.warning("[VISION_OBJ] Cleanup failed: %s", exc)
            await asyncio.sleep(interval_sec)
```

Modifier `start()` pour démarrer aussi la boucle cleanup :

```python
    async def start(self) -> None:
        _LOG.info("[VISION_OBJ] Agent started (singleton)")
        if os.getenv("VISION_OBJECT_CAMERA_LOOP", "true").lower() == "true":
            fps = int(os.getenv("VISION_OBJECT_FPS", "10"))
            await self.start_camera_loop(fps=fps)
        await self.start_cleanup_loop()
```

- [ ] **Step 4 : Relancer les tests → succès attendu**

Run : `pytest backend/tests/test_vision_object_agent.py -v`
Expected : 14 passed

- [ ] **Step 5 : Commit**

```bash
git add backend/vision_object_agent.py backend/tests/test_vision_object_agent.py
git commit -m "feat(vision): add nightly cleanup loop (retention-aware purge + VACUUM)"
```

---

### Task 17 : Suite complète + smoke test manuel local

**Files:**
- aucune création/modification

- [ ] **Step 1 : Lancer la suite pytest complète**

Run : `pytest backend/tests/ -v`
Expected : 41+ passed, 0 failed

- [ ] **Step 2 : Smoke test #1 — boot avec switch désactivé**

Activer `VISION_OBJECT_ENABLED=false` dans `.env`.

Run : `VISION_OBJECT_ENABLED=false bash start_ada.sh` (puis Ctrl+C après ~5s de boot)
Expected : Aucun log `[VISION_OBJ]`, Ada démarre normalement.

- [ ] **Step 3 : Smoke test #2 — boot avec switch activé (mode PULL seul)**

Activer dans `.env` :
```
VISION_OBJECT_ENABLED=true
VISION_OBJECT_CAMERA_LOOP=false
VISION_OBJECT_SCREEN_LOOP=false
```

Run : `bash start_ada.sh`
Expected logs (premier boot — téléchargement du modèle ~52 MB) :
```
[VISION_OBJ] Model loaded: yolov8m-oiv7.pt on device=mps ...
[SERVER] VisionObjectAgent singleton initialized
```

- [ ] **Step 4 : Smoke test #3 — tool PULL voix**

Une fois Ada démarré, dire à voix haute : « Tu vois mon téléphone ? »
Expected : Réponse FR contenant `téléphone` ou `pas de téléphone` (selon scène).

- [ ] **Step 5 : Smoke test #4 — tool PULL Telegram**

Envoyer dans le chat Telegram autorisé : `Qu'est-ce qu'il y a sur ma caméra ?`
Expected : Réponse texte similaire.

- [ ] **Step 6 : Activer la boucle caméra et observer 60s**

Modifier `.env` : `VISION_OBJECT_CAMERA_LOOP=true`
Redémarrer Ada.
Expected logs sur 1 minute :
```
[VISION_OBJ] Camera loop started (period=0.100s, fps=10)
[VISION_OBJ] Model loaded: ...
```
Plus des messages quand des objets apparaissent/bougent. Le brain SNN reçoit des stimuli `source=vision_object` (vérifiable côté logs brain si présents).

- [ ] **Step 7 : Vérifier MediaPipe non régressé**

Se placer devant la caméra. Vérifier qu'Ada t'identifie toujours (auth Bryan) et qu'aucune erreur n'apparaît sur la couche MediaPipe.

- [ ] **Step 8 : Vérifier la persistance SQLite**

Run : `sqlite3 "backend/memory/vision_timeline.db" "SELECT COUNT(*), MAX(timestamp_iso) FROM object_events;"`
Expected : un compte > 0 et un timestamp récent.

- [ ] **Step 9 : Si tout OK, commit checkpoint**

```bash
git commit --allow-empty -m "chore(vision): smoke tests #1-8 OK in local Mac dev"
```

---

### Task 18 : Documentation projet (`CLAUDE.md`)

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1 : Ajouter une section "Couche vision objet (YOLO)" à `CLAUDE.md`**

Insérer après la section "Agents spécialisés" du tableau des agents :

```markdown
### Couche vision objet (YOLO)

| Fichier | Rôle |
|---|---|
| `backend/yolo_detector.py` | Wrapper stateless YOLO + ByteTrack |
| `backend/vision_translations.py` | Mapping OIV7 EN → FR (80+ classes) |
| `backend/vision_deduplicator.py` | IoU matching → events APPEARED/MOVED/DISAPPEARED/UPDATED |
| `backend/vision_storage.py` | SQLite (factuel) + ChromaDB (sémantique) |
| `backend/vision_object_agent.py` | Singleton orchestrateur (mode PULL + boucles PUSH) |

**Master switch :** `VISION_OBJECT_ENABLED=false` désactive tout (aucun import).

**3 tools Gemini exposés (mode PULL) :**
- `detect_objects(source, filter?, max?)` — détection one-shot
- `query_seen_objects(object, since?, max_results?)` — recherche historique
- `count_objects_seen(object, period)` — comptage par track_id distinct

**Mode PUSH :**
- Boucle caméra 10 fps (partage la frame avec MediaPipe via `MultiUserFaceDetector.get_last_frame()`)
- Boucle écran 15 s (greffon `screen_watcher`)
- Stimuli propagés au brain SNN avec `source="vision_object"` (même schéma que `visual_scene_observer`)

**Spec de design :** `docs/superpowers/specs/2026-05-17-yolo-vision-layer-design.md`
**Plan d'implémentation :** `docs/superpowers/plans/2026-05-17-yolo-vision-layer-implementation.md`
```

- [ ] **Step 2 : Commit final**

```bash
git add CLAUDE.md
git commit -m "docs(vision): document YOLO layer in project CLAUDE.md"
```

---

## Récapitulatif post-implémentation

À la fin du plan :

- **5 nouveaux fichiers `backend/`** (`yolo_detector`, `vision_translations`, `vision_deduplicator`, `vision_storage`, `vision_object_agent`)
- **4 fichiers de tests unitaires + 1 conftest + 1 pytest.ini** (41+ tests, mock YOLO partout)
- **9 fichiers modifiés** (3 wirings obligatoires + 3 hooks lifecycle + 3 micro-mods)
- **0 modification du brain SNN** (pure addition par stimulus identique)
- **Kill-switch complet** via `VISION_OBJECT_ENABLED=false`

### Critères de "done"

- [ ] `pytest backend/tests/ -v` → tout vert (41+ tests)
- [ ] Boot `VISION_OBJECT_ENABLED=false` → Ada normal, aucun log `[VISION_OBJ]`
- [ ] Boot `VISION_OBJECT_ENABLED=true` + mode PULL → tool voix répond
- [ ] Boot avec boucle camera → events `appeared` visibles dans les logs
- [ ] MediaPipe (auth Bryan) fonctionne toujours en parallèle
- [ ] Cleanup nocturne loggé au moins une fois (en simulant avec interval court)
- [ ] SQLite `backend/memory/vision_timeline.db` créé et peuplé

### Hors scope (V2)

- Pas de fine-tuning custom (cf. §13 du design)
- Pas de segmentation pixel
- Pas de tracking 3D
- Pas de monitoring Prometheus/Sentry — logs PM2 suffisent
- Phase 3 Hetzner = plan distinct (déploiement, pas dev)
