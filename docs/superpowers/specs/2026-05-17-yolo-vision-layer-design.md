# Design — Couche YOLO complémentaire à MediaPipe pour la vision d'Ada

**Date :** 2026-05-17
**Auteur :** Bryan Hilaire (brainstorming avec Claude)
**Statut :** Design validé, prêt pour planification d'implémentation
**Projet :** jarvis / Ada — Assistant personnel IA
**Approche retenue :** C — Agent YOLO asyncio + tool Gemini

---

## TL;DR

Ajout d'une **couche YOLO** (Open Images V7, 600 classes) à la vision d'Ada,
**en complément** des couches MediaPipe (visages, gestes) et Gemini multimodal
(scène sémantique) existantes — **sans rien retirer ni modifier le brain SNN**.

- **Modèle :** `yolov8m-oiv7` (~52 MB, précision max raisonnable)
- **Hardware :** Mac M-series (MPS) en dev, Hetzner CPU en prod
- **Fréquence :** 10 fps continu sur caméra, 15 s sur écran
- **Sortie :** events `appeared`/`disappeared`/`moved`/`updated` propagés au brain SNN
  (même schéma que `visual_scene_observer`) + persistance SQLite + ChromaDB
- **Wiring :** pattern asyncio agent standard (comme `ResearchAgent`/`TaskAgent`),
  désactivable par env var `VISION_OBJECT_ENABLED=false`
- **Effort :** ~2-3 jours d'implémentation
- **Risque :** faible — aucune régression sur MediaPipe ni Gemini, kill-switch immédiat

---

## 1. Cadrage et objectifs

### 1.1 Pourquoi cette couche

La vision actuelle d'Ada a 3 couches bien séparées :

| Couche | Outil | Rôle |
|---|---|---|
| MediaPipe backend | `authenticator.py` | Identifie les personnes (Bryan, Rose) + calcule `last_motion` pour le brain SNN |
| MediaPipe frontend | `public/mediapipe/wasm/` + `hand_gesture_os_controller.py` | Détecte gestes des mains dans le navigateur → contrôle souris/clavier |
| Gemini 2.5 Flash | `visual_scene_observer.py` + `screen_watcher.py` | Compréhension sémantique haut-niveau (description, émotion, risque) toutes les 15 s |

**Le trou :** aucune des 3 couches ne détecte les **objets génériques de la scène**
(téléphone, livre, ordi, animal, voiture, bouteille…). C'est exactement ce que
YOLO comble, **localement, sans coût API et sans rate-limit Gemini**.

### 1.2 Cas d'usage cibles (les 4 retenus)

1. **Conscience d'objets en continu** — Ada sait en temps réel ce qui est dans
   la scène, enrichit le brain SNN et la spontanéité.
2. **Surveillance & sécurité** — détecte intrusions, animaux, objets à risque
   (feu, couteau) → déclenche alertes brain + notification Telegram.
3. **Interaction objets contextuelle** — Ada réagit à des objets précis
   ("tu prends ton téléphone → tu attends un appel ?").
4. **Tracking & mémoire spatiale** — Ada retient où sont les choses dans le
   temps ("où j'ai laissé mes clés", "combien de fois le chat est passé").

### 1.3 Sources vidéo couvertes

- **Caméra physique** (webcam macOS) — boucle 10 fps en arrière-plan
- **Capture d'écran** — branchée sur `screen_watcher.py` existant (15 s)
- **Tool à la demande** — n'importe quelle frame (caméra/écran/upload) via tool
  Gemini one-shot

### 1.4 Vocabulaire détecté

- **COCO + Open Images V7 (600 classes)** via les modèles `yolov8*-oiv7.pt`
  d'`ultralytics`. Plus de vocabulaire que les 80 classes COCO standard, légèrement
  moins précis par classe mais nettement plus large (clavier détaillé, outils,
  instruments, vêtements, etc.).
- **Pas de fine-tuning custom** dans cette V1. Architecture conçue pour
  l'accueillir plus tard (cf. § 13).

---

## 2. Architecture des composants

### 2.1 Nouveaux fichiers

```
backend/
├── yolo_detector.py              ← Core wrapper YOLO (stateless, réutilisable)
├── vision_object_agent.py        ← Agent asyncio (mode PUSH + mode PULL)
└── memory/
    └── vision_timeline.db        ← SQLite (créé au premier boot)
```

### 2.2 Fichiers modifiés (micro-touches, zéro régression)

```
backend/
├── authenticator.py              ← AJOUT get_last_frame() sur MultiUserFaceDetector (~6 lignes)
├── ada.py                        ← AJOUT instanciation agent + 3 wirings _execute_text_tool
├── external_bridge.py            ← AJOUT 3 wirings _execute_tool
├── mcp_tools_declarations.py     ← AJOUT 3 déclarations tools
├── server.py                     ← AJOUT lifecycle agent
├── memory_manager.py             ← AJOUT collection ChromaDB "vision_objects"
└── screen_watcher.py             ← AJOUT appel YOLO fire-and-forget en parallèle de Gemini

.env.example                      ← AJOUT 11 variables d'env
requirements.txt                  ← AJOUT ultralytics==8.3.x + torch>=2.2
.gitignore                        ← AJOUT *.pt + vision_timeline.db
```

### 2.3 Hiérarchie des responsabilités

| Composant | Responsabilité unique | Dépendances |
|---|---|---|
| `YoloDetector` | Charger le modèle, exécuter une inférence, normaliser les détections en `Detection` | `ultralytics` |
| `_DetectionDeduplicator` | IoU matching inter-frames → générer 4 types d'events (apparition/disparition/déplacement/update) | rien |
| `_VisionStorage` | Persister events dans SQLite + ChromaDB | `sqlite3` + `memory_manager` |
| `VisionObjectAgent` | Orchestrer : boucles caméra+écran, dédup, stockage, callbacks brain, expose mode PULL pour Gemini | `YoloDetector`, `MultiUserFaceDetector`, `memory_manager` |

### 2.4 Principe d'isolation

- `YoloDetector` testable seul (sans démarrer tout Ada)
- L'agent désactivable via `VISION_OBJECT_ENABLED=false` → aucun import, zéro impact
- Le brain SNN reçoit les events YOLO via **callback additif** (ne casse pas `on_scene_event`)
- SQLite strictement local à la couche vision

---

## 3. Flux de données

### 3.1 Mode PUSH — boucle caméra (10 fps continu)

```
MultiUserFaceDetector              VisionObjectAgent
    (boucle MediaPipe)              (boucle YOLO)
          │                              │
          │ get_last_frame() ────────────►│  ① frame BGR partagée (1 seule webcam macOS)
          │                              ▼
          │                     YoloDetector.detect(frame)
          │                              │  ② inférence 30-60ms (MPS)
          │                              ▼
          │                     _DetectionDeduplicator.diff(detections)
          │                              │  ③ matching IoU + ByteTrack
          │                              │     → appeared / disappeared / moved
          │                              ▼
          │                     IF empty diff → drop frame (économie brain)
          │                     ELSE :
          │                              ▼
          │                     _VisionStorage.persist(events)
          │                              │  ④ SQLite INSERT + ChromaDB add
          │                              ▼
          │                     brain.on_object_event(stimulus)
          │                              │  ⑤ stimule SNN (additif)
          │                              ▼
          │                     IF event.is_critical → telegram_alert()
          │                              ▼
          │                     sleep(100ms − inference_time) ; drop si retard
```

**Politique anti-backlog :** si l'inférence précédente n'est pas finie au tick
suivant, on **drop la frame courante** plutôt que d'accumuler. Tolérance de
chute de tempo (10 → 5 fps temporaire) si Mac chargé.

### 3.2 Mode PUSH — boucle écran (15 s, greffée sur screen_watcher)

```
_capture_screen() ──► jpeg_bytes
                          │
                          ├──► analyze_visual_scene(jpeg)         [Gemini, existant]
                          │       └──► on_scene_event(scene_event) [brain, existant]
                          │
                          └──► vision_object_agent.detect_on_frame_bytes(jpeg, source="screen")
                                    └──► dédup + persist + brain.on_object_event(stimulus)
```

Les deux pipelines (Gemini sémantique + YOLO objets) tournent **en parallèle**.
L'appel YOLO est `fire-and-forget` (`asyncio.create_task` sans await) pour ne
pas ralentir Gemini ni risquer de bloquer la boucle.

### 3.3 Mode PULL — appel à la demande (tool Gemini)

```
Bryan vocal : "Tu vois mon téléphone ?"
    └─► Gemini function_call : detect_objects(source="camera", filter="téléphone")
            └─► ada.py _execute_text_tool → agent.detect_on_demand(...)
                    └─► récupère frame → YOLO → filtre → format FR
                            └─► "Oui, je vois un téléphone à droite, confiance 0.87"
```

**3 tools Gemini exposés :**

| Tool | Signature | Cas d'usage |
|---|---|---|
| `detect_objects` | `(source: "camera"\|"screen"\|"upload", filter?: str, max?: int)` | "Tu vois X ?" / "Qu'est-ce qu'il y a sur mon bureau ?" |
| `query_seen_objects` | `(object: str, since?: str, max_results?: int)` | "Quand j'ai vu mon livre rouge pour la dernière fois ?" |
| `count_objects_seen` | `(object: str, period: str)` | "Combien de fois le chat est passé aujourd'hui ?" |

Le mode PULL bypass volontairement la dédup : si Bryan demande "tu vois mon
téléphone ?", il veut une réponse immédiate même si rien n'a bougé.

---

## 4. Contrats de données

### 4.1 `Detection` — sortie brute normalisée

```python
# yolo_detector.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Detection:
    class_id: int           # ID Open Images V7 (0-599)
    class_name: str         # ex: "Mobile phone", "Cat", "Coffee cup"
    class_fr: str           # ex: "téléphone", "chat", "tasse de café"
    confidence: float       # 0.0 - 1.0
    bbox: tuple[float, float, float, float]   # (x_center, y_center, w, h) normalisés [0,1]
    track_id: int | None    # ID stable inter-frames (ByteTrack)
```

- `bbox` normalisée [0,1] → indépendante de la résolution caméra/écran
- `class_fr` rempli via mapping statique `OIV7_FR_TRANSLATIONS` au top du module
- `track_id` via `ByteTrack` (intégré à `ultralytics`, gratuit) → permet le
  suivi inter-frames même si l'objet sort/rentre brièvement du cadre

### 4.2 `ObjectEvent` — ce qui est propagé au brain et persisté

```python
# vision_object_agent.py
from enum import Enum

class EventType(str, Enum):
    APPEARED = "appeared"       # nouvel objet
    DISAPPEARED = "disappeared" # objet précédemment vu, parti
    MOVED = "moved"             # déjà vu, déplacement > seuil
    UPDATED = "updated"         # changement de confidence/classe (rare)

@dataclass(frozen=True)
class ObjectEvent:
    event_id: str               # uuid4 court
    event_type: EventType
    source: str                 # "camera" | "screen"
    timestamp: float            # epoch
    detection: Detection
    track_id: int | None
    location_hint: str | None
    metadata: dict
```

### 4.3 Schéma SQLite — `backend/memory/vision_timeline.db`

```sql
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
CREATE INDEX IF NOT EXISTS idx_current_class       ON current_objects(class_fr) WHERE is_present = 1;
```

**Patterns de requêtes typiques** (utilisés par les 3 tools Gemini) :

```sql
-- count_objects_seen("chat", "today")
SELECT COUNT(DISTINCT track_id) FROM object_events
WHERE class_fr = 'chat' AND event_type = 'appeared'
  AND timestamp >= ? AND timestamp <= ?;

-- query_seen_objects("livre rouge", since="hier")
SELECT timestamp_iso, source, location_hint, bbox_x, bbox_y
FROM object_events
WHERE class_fr LIKE '%livre%' AND timestamp >= ?
ORDER BY timestamp DESC LIMIT 10;

-- "ce qui est dans la scène maintenant" (contexte brain)
SELECT class_fr, COUNT(*) FROM current_objects
WHERE is_present = 1 GROUP BY class_fr;
```

### 4.4 ChromaDB — collection `vision_objects`

```python
self.vision_collection = self.client.get_or_create_collection(
    name="vision_objects",
    embedding_function=self._embedding_func  # même qu'existant
)

# Indexe UNIQUEMENT APPEARED et MOVED (pas DISAPPEARED, pas UPDATED)
self.vision_collection.add(
    ids=[event.event_id],
    documents=[
        f"{event.detection.class_fr} vu sur {event.source} à {iso_time} "
        f"position ({bbox_x:.2f}, {bbox_y:.2f}) confiance {confidence:.2f}"
    ],
    metadatas=[{
        "class_name": event.detection.class_name,
        "class_fr": event.detection.class_fr,
        "source": event.source,
        "timestamp": event.timestamp,
        "track_id": event.track_id or -1,
        "bbox": json.dumps([bbox_x, bbox_y, bbox_w, bbox_h])
    }]
)
```

**Pourquoi SQLite + ChromaDB :**
- SQLite → questions **factuelles structurées** (combien, quand, entre quelle heure)
- ChromaDB → questions **floues sémantiques** ("où j'ai laissé un truc rouge")
- Écriture transactionnelle unique dans `_VisionStorage.persist()` → pas de désync

### 4.5 Format consommé par le brain SNN

Le brain reçoit `ObjectEvent` via `on_object_event(stimulus)`. Pour respecter
sa logique de stimulation bornée existante, l'agent **traduit** l'event en
stimulus au **même schéma que `normalize_scene_event()` de `visual_scene_observer`** :

```python
{
    "source": "vision_object",         # NOUVEAU type, additif à screen/camera
    "description": "téléphone appeared",
    "object_class": "téléphone",
    "event_type": "appeared",
    "movement": 0.6 if MOVED else 0.2,
    "risk": self._classify_risk(event),  # 'none'|'low'|'medium'|'high'
    "attention_need": self._classify_attention(event),
    "valence": 0.0,
    "spontaneous_hint": self._hint_for(event)
}
```

→ **Zéro changement dans le code du brain SNN.** C'est juste une nouvelle source
qui s'ajoute à `screen`/`camera`.

---

## 5. Wiring — les 3 endroits obligatoires + 3 additionnels

Conformément à la règle absolue de `backend/CLAUDE.md` : tout nouvel outil doit
être wiré dans `mcp_tools_declarations.py` + `ada.py:_execute_text_tool` +
`external_bridge.py:_execute_tool`.

### 5.1 `mcp_tools_declarations.py`

```python
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
            "source": {"type": "STRING", "description": "'camera' (webcam) ou 'screen' (capture écran). Défaut: 'camera'."},
            "filter": {"type": "STRING", "description": "Optionnel. Nom de classe FR à filtrer (ex: 'téléphone'). Vide = toutes classes."},
            "max_results": {"type": "INTEGER", "description": "Nombre max de détections. Défaut: 10."}
        },
        "required": []
    }
}

query_seen_objects_tool = {
    "name": "query_seen_objects",
    "description": (
        "Recherche dans l'historique des objets vus. Combine SQLite (temps) + ChromaDB (sémantique). "
        "Utilise pour 'où j'ai laissé X', 'quand j'ai vu X pour la dernière fois'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "object": {"type": "STRING", "description": "Description FR de l'objet (peut être flou)."},
            "since": {"type": "STRING", "description": "Optionnel. Date ISO ou relative ('hier', 'cette semaine'). Défaut: 24h."},
            "max_results": {"type": "INTEGER", "description": "Défaut: 5."}
        },
        "required": ["object"]
    }
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
            "period": {"type": "STRING", "description": "'today'|'yesterday'|'this_week'|'last_24h'|'last_hour'. Défaut: 'today'."}
        },
        "required": ["object"]
    }
}

MCP_TOOLS = [..., detect_objects_tool, query_seen_objects_tool, count_objects_seen_tool]
```

### 5.2 `ada.py` (voix Live API)

```python
from vision_object_agent import VisionObjectAgent

# Dans __init__ d'AudioLoop :
self._vision_agent: VisionObjectAgent | None = None

# Lazy-init pour partager la frame webcam avec MultiUserFaceDetector
async def _ensure_vision_agent(self) -> VisionObjectAgent:
    if self._vision_agent is None:
        face_detector = await self._ensure_face_detector()
        self._vision_agent = await asyncio.to_thread(
            VisionObjectAgent,
            face_frame_source=face_detector,
            memory_manager=self.memory,
            on_object_event=self._on_vision_object_event,
        )
        await self._vision_agent.start()
    return self._vision_agent

async def _on_vision_object_event(self, stimulus: dict) -> None:
    if self._brain is not None:
        await self._brain.ingest_stimulus(stimulus)

# Dans _execute_text_tool, 3 nouvelles branches :
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

### 5.3 `external_bridge.py` (Telegram/WhatsApp)

```python
from vision_object_agent import VisionObjectAgent

# Dans __init__ de TextAgent :
self._vision_agent: VisionObjectAgent | None = None

async def _ensure_vision_agent(self) -> VisionObjectAgent:
    if self._vision_agent is None:
        # Pattern singleton inter-modules : AudioLoop et TextAgent partagent l'instance
        self._vision_agent = await asyncio.to_thread(
            VisionObjectAgent.get_or_create_singleton,
            memory_manager=self.memory,
        )
    return self._vision_agent

# Dans _execute_tool, les 3 mêmes branches que ada.py
```

**Pattern singleton** : `VisionObjectAgent.get_or_create_singleton(...)` garantit
qu'un seul modèle YOLO est chargé en RAM (≈150 MB), partagé entre AudioLoop et
TextAgent.

### 5.4 `server.py` (lifecycle FastAPI)

```python
@app.on_event("startup")
async def startup_vision_agent():
    if os.getenv("VISION_OBJECT_ENABLED", "false").lower() == "true":
        from vision_object_agent import VisionObjectAgent
        VisionObjectAgent.get_or_create_singleton(memory_manager=memory)
        print("[SERVER] VisionObjectAgent initialisé (singleton)")

@app.on_event("shutdown")
async def shutdown_vision_agent():
    agent = VisionObjectAgent.peek_singleton()
    if agent:
        await agent.stop()
```

→ Si `VISION_OBJECT_ENABLED=false`, **aucun import**, aucun chargement modèle.
Kill-switch complet.

### 5.5 `authenticator.py` (micro-mod, 6 lignes)

```python
# Dans MultiUserFaceDetector :
self._last_frame: np.ndarray | None = None  # ajout

# Dans detect() — première ligne :
def detect(self, frame_bgr: np.ndarray) -> list[dict]:
    self._last_frame = frame_bgr.copy()  # ajout
    # ... reste inchangé

# Nouvelle méthode :
def get_last_frame(self) -> np.ndarray | None:
    """Renvoie la dernière frame BGR capturée."""
    return self._last_frame
```

**Aucun comportement modifié.** Juste exposition de la frame déjà capturée.

### 5.6 `screen_watcher.py` (ajout YOLO en parallèle de Gemini)

```python
# Dans _analyze_frame, après l'appel Gemini existant :
if self._vision_agent:
    asyncio.create_task(
        self._vision_agent.detect_on_frame_bytes(frame_bytes, source="screen")
    )
```

`fire-and-forget` : si YOLO crashe, Gemini continue. Si Gemini crashe
(rate-limit), YOLO continue.

---

## 6. Intégration brain SNN

Le brain ingère aujourd'hui deux types de stimuli :
- Events de `MultiUserFaceDetector` (motion, présence)
- Events de `visual_scene_observer` (sémantique Gemini)

YOLO ajoute un **troisième type** sans toucher au code du brain : `source="vision_object"`
avec le **même schéma de stimulus**.

**Pondération suggérée** (constante au top de `vision_object_agent.py`) :

| Cas | `attention_need` | `risk` |
|---|---|---|
| APPEARED objet connu fréquent (téléphone, ordi) | 0.1 | none |
| APPEARED objet rare (animal, personne inconnue, jamais vu) | 0.5 | low |
| APPEARED objet à risque (feu, couteau, fumée) | 0.9 | high |
| DISAPPEARED | 0.1 (sauf objet précieux configuré) | none |
| MOVED objet quelconque | 0.3 | none |

Table modifiable sans toucher au brain.

---

## 7. Algorithme de déduplication

```
détections = yolo.detect(frame)
events = []
seen_track_ids = set()

POUR chaque detection dans détections :
    seen_track_ids.add(detection.track_id)

    SI detection.track_id PAS dans _tracked_objects :
        events.append(APPEARED)
        _tracked_objects[detection.track_id] = TrackedObject(...)
    SINON :
        tracked = _tracked_objects[detection.track_id]
        iou = compute_iou(tracked.last_bbox, detection.bbox)
        SI iou < IOU_MOVED_THRESHOLD (0.5) :
            events.append(MOVED)
        SI abs(tracked.last_confidence - detection.confidence) > 0.2 :
            events.append(UPDATED)
        tracked.update(detection)
        tracked.consecutive_misses = 0

POUR chaque track_id dans _tracked_objects PAS dans seen_track_ids :
    _tracked_objects[track_id].consecutive_misses += 1
    SI consecutive_misses >= DISAPPEAR_GRACE_FRAMES (5) :
        events.append(DISAPPEARED)
        del _tracked_objects[track_id]

RETOURNER events
```

**Constantes (configurables via env) :**

| Constante | Défaut | Rôle |
|---|---|---|
| `IOU_MOVED_THRESHOLD` | 0.5 | En dessous = bougé significativement |
| `DISAPPEAR_GRACE_FRAMES` | 5 | Tolérance occlusions courtes (5 × 100ms = 0.5s) |
| `CONFIDENCE_MIN` | 0.45 | En dessous = ignoré (bruit) |
| `MAX_TRACKED_OBJECTS` | 100 | Cap mémoire — éviction LRU au-delà |

---

## 8. Gestion d'erreurs et garde-fous

### 8.1 Hiérarchie d'erreurs

| Erreur | Recovery | Impact Ada |
|---|---|---|
| Modèle YOLO introuvable | Téléchargement auto via ultralytics | Démarrage +20s, warning |
| MPS indisponible | Fallback CPU + tempo abaissé à 2 fps | Plus lent mais fonctionnel |
| OOM pendant inférence | Clear cache MPS + downgrade vers `yolov8n-oiv7` | Précision dégradée, Ada continue |
| Frame corrompue | Skip + log debug | Aucun |
| Inférence > 200ms répété (> 30% sur 1 min) | Tempo divisé par 2 (10→5→2 fps) | Réactivité réduite |
| SQLite locked | Retry × 3 avec backoff (10ms, 100ms, 1s) puis skip | Event perdu, warning |
| ChromaDB indisponible | Skip sémantique mais SQLite persisté | Recherche sémantique dégradée |
| Frame source vide (caméra coupée) | Skip cycle + retry. > 30s → warning + reset | Vision pause, repart auto |
| Crash thread d'inférence | Restart auto avec backoff (1s, 5s, 30s, 5min cap) | Quelques secondes coupure |

**Règle d'or :** aucune erreur YOLO ne fait planter Ada. Tous `try/except` →
retour `str` (cohérent `.claude/rules/code-style.md`).

### 8.2 Budget performance (Mac M-series récent)

| Ressource | Cible | Garde-fou |
|---|---|---|
| Latence inférence | < 80ms moyenne | Tempo /2 |
| CPU constant | < 25% | Tempo /2 |
| RAM modèle | < 200 MB | — (statique) |
| RAM tracking | < 50 MB | LRU eviction |
| SQLite size | < 500 MB | Cleanup nocturne |
| ChromaDB | < 50k vecteurs | Cleanup nocturne |
| Events brain | < 5/sec moyenne | Throttling + coalescing |

### 8.3 Throttling brain SNN (anti-spam)

```python
# 1. Throttling par classe : max 1 event/sec/classe envoyé au brain
HIGH_PRIORITY_CLASSES = {"Person", "Cat", "Dog", "Fire", "Knife", "Gun"}

def _should_propagate_to_brain(self, event: ObjectEvent) -> bool:
    if event.detection.class_fr in HIGH_PRIORITY_CLASSES:
        return True  # toujours propagé
    last = self._brain_throttle.get(event.detection.class_fr, 0)
    if time.time() - last < BRAIN_THROTTLE_SEC:
        return False
    self._brain_throttle[event.detection.class_fr] = time.time()
    return True

# 2. Coalescing : 5 APPEARED dans 200ms → 1 stimulus fusionné
# 3. Hard cap : max 10 stimuli brain/sec
```

### 8.4 Maintenance nocturne (cron interne)

Job asyncio léger qui tourne **une fois par jour à 4h** (configurable) :

1. SQLite : `DELETE` events older than `VISION_OBJECT_RETENTION_DAYS` (défaut 30)
2. SQLite : `VACUUM` pour récupérer l'espace
3. ChromaDB : remove embeddings older than retention
4. `_tracked_objects` : reset complet (oublie les fantômes)
5. Log résumé : "Cleanup: N events purged, db size X MB"

### 8.5 Observabilité

Logs structurés stdout avec préfixe `[VISION_OBJ]` :

```
[VISION_OBJ] Started — model=yolov8m-oiv7 device=mps fps_target=10
[VISION_OBJ] Frame inference: 42ms (objects=7, new_events=2)
[VISION_OBJ] Detected: chat APPEARED (conf=0.91, source=camera, track=12)
[VISION_OBJ] Throttled: téléphone MOVED (last brain push 0.3s ago)
[VISION_OBJ] Slow frame: 187ms (cumulative slow_frames=4/600)
[VISION_OBJ] Tempo degraded: 10fps → 5fps (32% slow frames last minute)
[VISION_OBJ] OOM detected → fallback yolov8n-oiv7
[VISION_OBJ] Nightly cleanup: 1247 events purged, sqlite=12.3MB chroma=8123 vecteurs
[VISION_OBJ] Stopped gracefully
```

Pas de Prometheus/Sentry pour le MVP. Logs PM2 suffisent.

---

## 9. Variables d'environnement

À ajouter dans `.env.example` :

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

---

## 10. Plan de tests

### 10.1 Tests unitaires (`backend/tests/test_vision_object.py`)

- `YoloDetector` — chargement + inférence sur fixture image
- `Detection` retourne bien `class_fr` (mapping FR)
- `_DetectionDeduplicator` :
  - première frame → toutes APPEARED
  - scène stable 2 frames → 0 event
  - bbox bouge → MOVED
  - grace period 3 frames d'occlusion → pas de DISAPPEARED
  - absent 5+ frames → un seul DISAPPEARED
- `_VisionStorage` :
  - persiste event (SQLite + Chroma)
  - `current_objects.is_present=0` après DISAPPEARED
  - query par classe + range temporel
- `VisionObjectAgent` :
  - mode PULL retourne réponse FR
  - callback `on_object_event` appelé
  - throttling brain (5 events même classe en 100ms → 1 callback)
- Resilience :
  - frame corrompue → `[]` pas d'exception
  - inférence en cours → skip frame

Fixtures images dans `backend/tests/fixtures/` (3-4 photos).

### 10.2 Smoke tests manuels (avant chaque déploiement)

| # | Test | Critère succès |
|---|---|---|
| 1 | Boot avec `VISION_OBJECT_ENABLED=false` | Ada démarre normalement, aucun log `[VISION_OBJ]` |
| 2 | Boot avec `VISION_OBJECT_ENABLED=true` | Log `Started — model=…`, modèle téléchargé si premier boot |
| 3 | Tool PULL via voix Gemini | "Tu vois mon téléphone ?" → réponse FR cohérente |
| 4 | Tool PULL via Telegram | Même type de réponse en texte |
| 5 | Brain stimulus PUSH | Objet bouge → log `MOVED` + `[BRAIN] Stimulus ingested (source=vision_object)` |
| 6 | Query historique | "Quand j'ai vu mon téléphone ?" → réponse temporelle |
| 7 | Count distinct | "Combien de fois le chat est passé ?" → comptage track_id |
| 8 | Coexistence MediaPipe | Bryan 5 min devant caméra avec objets → MediaPipe ID + YOLO objets en // |
| 9 | Coexistence Gemini screen | Logs Gemini scene + logs YOLO alternent toutes les 15s |
| 10 | Kill-switch en prod | `.env` `=false` + restart PM2 → Ada continue, zéro YOLO |

---

## 11. Plan de déploiement progressif

### Phase 1 — Local Mac, mode PULL seul (3-5 jours)
1. `VISION_OBJECT_ENABLED=true VISION_OBJECT_CAMERA_LOOP=false` → tools Gemini seuls
2. Smoke tests #1-7
3. Observer logs, latence, RAM
4. Si stable → activer la boucle caméra 10 fps

### Phase 2 — Local Mac avec boucle continue (1-2 semaines)
1. Tourner 24h+ avec les 2 boucles actives
2. Vérifier events `source=vision_object` reçus par le brain
3. Vérifier enrichissement spontanéité Ada
4. Mesurer croissance SQLite/Chroma + valider cleanup nocturne

### Phase 3 — Hetzner production
1. Push code + migration `requirements.txt`
2. Restart PM2 avec `VISION_OBJECT_ENABLED=false` (sécurité)
3. Vérifier démarrage normal
4. Activer `VISION_OBJECT_ENABLED=true VISION_OBJECT_CAMERA_LOOP=false VISION_OBJECT_DEVICE=cpu`
5. Si stable 24h → activer la boucle complète
6. Documenter dans `backend/CLAUDE.md` (rubrique "Problèmes connus & statut")

**Critère de rollback immédiat :** Ada perd la voix, ne répond plus, ou PM2
redémarre en boucle → `VISION_OBJECT_ENABLED=false` + restart.

---

## 12. Checklist avant merge

- [ ] Tests unitaires passent : `pytest backend/tests/test_vision_object.py`
- [ ] Smoke tests #1-10 passent en local Mac
- [ ] `.env.example` mis à jour avec les 11 nouvelles variables
- [ ] `requirements.txt` : `ultralytics==8.3.x` + `torch>=2.2` ajoutés
- [ ] `backend/CLAUDE.md` : section "Vision objet (YOLO)" ajoutée
- [ ] `.gitignore` : exclusion de `backend/memory/vision_timeline.db`
- [ ] `.gitignore` : exclusion de `yolov8*-oiv7.pt` (modèles téléchargés)
- [ ] Aucun secret ni token dans le code
- [ ] `MultiUserFaceDetector.get_last_frame()` ne casse pas la détection existante
- [ ] `FaceAuthenticator` de démarrage (`server.py:431`) toujours fonctionnel
- [ ] Brain SNN reçoit stimulus avec `source='vision_object'` (log présent)
- [ ] Mapping FR OIV7 couvre les 30-50 classes les plus communes
- [ ] Mode PULL fonctionne même si `VISION_OBJECT_CAMERA_LOOP=false`
- [ ] Kill-switch testé en prod-like (var=false → aucun import)
- [ ] Commit message : `feat(vision): couche YOLO complémentaire à MediaPipe (PUSH + PULL)`

---

## 13. Limites assumées du MVP (YAGNI)

**Pas dans cette V1**, à reconsidérer plus tard :

- ❌ Pas de fine-tuning custom (pas de "voiture de Bryan", "chat Rose nommé")
- ❌ Pas de segmentation (juste bbox, pas de masques pixel)
- ❌ Pas de pose estimation (MediaPipe le fait mieux pour les humains)
- ❌ Pas de tracking 3D (juste 2D normalisé)
- ❌ Pas de cross-camera matching (si un jour plusieurs webcams)
- ❌ Pas d'export Prometheus/Grafana — logs PM2 suffisent
- ❌ Pas d'UI frontend pour visualiser les détections temps-réel — V2 si besoin

Ces limites sont **explicites** pour éviter le scope-creep pendant l'implémentation.

---

## 14. Risques identifiés et mitigations

| Risque | Probabilité | Mitigation |
|---|---|---|
| Modèles OIV7 moins précis qu'attendu sur cas réels | Moyenne | Possible bascule vers COCO standard pour cas critiques |
| Conflit MediaPipe/YOLO sur la webcam | Faible | `get_last_frame()` partage la frame, pas de 2e capture |
| Croissance non bornée SQLite | Faible | Cleanup nocturne + retention par défaut 30j |
| Spam brain SNN | Moyenne | Throttling 1/sec/classe + coalescing + hard cap 10/sec |
| OOM Hetzner | Moyenne | Fallback auto yolov8m → yolov8n |
| Régression FaceAuthenticator (auth démarrage) | Faible | Test manuel obligatoire (item 10 checklist) |
| Casse silencieuse du brain SNN | Faible | Schéma stimulus identique à `visual_scene_observer` |

---

## 15. Estimation d'effort

- **Implémentation** : ~2-3 jours (1 dev focalisé)
- **Tests unitaires + fixtures** : ~0.5 jour
- **Phase 1 dev local** : 3-5 jours d'observation (passif)
- **Phase 2 boucle continue** : 1-2 semaines (passif)
- **Phase 3 prod Hetzner** : ~0.5 jour de déploiement + 24h d'observation

**Total avant prod stable :** ~3-4 semaines calendaires (dont la majorité en
observation passive).

---

## 16. Prochaine étape

→ Invoquer le skill `superpowers:writing-plans` pour générer un plan
d'implémentation détaillé tâche-par-tâche basé sur ce design.
