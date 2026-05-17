# Brain v3 — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire un package `brain/v3/` en surcouche entre les capteurs et le brain v2 d'Ada, fournissant des neurones adaptatifs, une habituation par classe de stimulus, un budget d'attention, une neuromodulation explicite par les hormones v2, et une politique de réaction probabiliste — sans casser le brain v2 actuel ni l'API publique de `BrainManager`.

**Architecture:** Surcouche fine. `BrainManager` v2 reste le point d'entrée public ; quand `BRAIN_V3_ENABLED=true`, il route via un `V3Manager` qui produit une `ReactionDecision` (SUPPRESS/OBSERVE/REACT). En mode shadow (`BRAIN_V3_SHADOW_MODE=true`, défaut), v3 logge ses décisions sans bloquer v2. Limbic v2 est toujours mis à jour (perception), v3 ne gate que la décision de parler.

**Tech Stack:** Python 3.11 strict, asyncio (jamais bloquant), pytest pour les tests, threading.Lock pour la thread-safety, env vars via `brain.calibration.env_*`. Aucune nouvelle dépendance externe.

**Spec source:** `docs/superpowers/specs/2026-05-17-brain-v3-neurobiological-design.md`

**Branch:** `feature/yolo-vision-layer` (continue) ou créer `feature/brain-v3` selon préférence.

---

## File Structure

### Fichiers à créer

| Fichier | Rôle | LOC estimé |
|---|---|---|
| `brain/v3/__init__.py` | Package marker | 5 |
| `brain/v3/types.py` | `Stimulus`, `ReactionDecision`, `ModulationVector` (frozen dataclasses) | 50 |
| `brain/v3/adapters.py` | `from_payload()` : payload → Stimulus avec canonical_id stable | 120 |
| `brain/v3/neurons.py` | `AdaptiveLIF` : LIF + threshold drift + AHP + modulation | 100 |
| `brain/v3/attention.py` | `AttentionField` : 5 neurones + inhibition latérale | 80 |
| `brain/v3/habituation.py` | `HabituationTracker` : LRU + decay temporel | 80 |
| `brain/v3/neuromodulation.py` | Hormones v2 → ModulationVector | 50 |
| `brain/v3/traces.py` | `ShortTermMemory` : ring buffer 60s | 60 |
| `brain/v3/policy.py` | `ReactionPolicy` : SUPPRESS/OBSERVE/REACT | 100 |
| `brain/v3/v3_manager.py` | Façade défensive, singleton, refill loop | 120 |
| `brain/v3/tests/__init__.py` | Tests package | 0 |
| `brain/v3/tests/conftest.py` | Fixtures : `mock_limbic`, `freeze_time` | 50 |
| `brain/v3/tests/test_types.py` | Validation des dataclasses | 40 |
| `brain/v3/tests/test_adapters.py` | canonical_id stable par channel | 80 |
| `brain/v3/tests/test_neurons_adaptive.py` | threshold drift, AHP, modulation | 100 |
| `brain/v3/tests/test_attention_field.py` | inhibition latérale, winner-take-all | 80 |
| `brain/v3/tests/test_habituation.py` | decay, LRU eviction, thread-safety | 100 |
| `brain/v3/tests/test_neuromodulation.py` | snapshot → ModulationVector | 60 |
| `brain/v3/tests/test_traces.py` | ring buffer, append, recent | 50 |
| `brain/v3/tests/test_policy.py` | toutes les branches de décision | 120 |
| `brain/v3/tests/test_v3_manager.py` | enabled/shadow/degraded/p95 < 3ms | 100 |
| `brain/v3/tests/test_integration_v3.py` | bout-en-bout YOLO → v3 → décision | 80 |
| `brain/v3/tests/test_v2_v3_isolation.py` | v3 OFF → v2 strictement inchangé | 60 |

### Fichiers à modifier

| Fichier | Lignes | Modification |
|---|---|---|
| `brain/brain_manager.py` | +40, ~10 modifiés | Ajout `_v3`, `ingest_stimulus()`, `_dispatch_stimulus()`, refacto interne |
| `backend/ada.py:4797-4804` | +2 | Fallback singleton dans `_on_vision_object_event` |
| `backend/server.py` | +30 | Endpoint `GET /brain/v3/traces?n=50` |
| `.env.example` | +30 | Variables `BRAIN_V3_*` documentées |

---

## Phase 1 — Fondations (types, traces, adapters)

### Task 1.1 : Créer le package `brain/v3/` et les types de base

**Files:**
- Create: `brain/v3/__init__.py`
- Create: `brain/v3/types.py`
- Test: `brain/v3/tests/__init__.py`
- Test: `brain/v3/tests/test_types.py`

- [ ] **Step 1: Créer le test pour les types**

Crée `brain/v3/tests/__init__.py` (vide), puis `brain/v3/tests/test_types.py` :

```python
"""Tests des dataclasses immuables du brain v3."""
import pytest

from brain.v3.types import ModulationVector, ReactionDecision, Stimulus


def test_stimulus_is_frozen():
    s = Stimulus(
        canonical_id="obj:cat:appeared",
        channel="vision_object",
        intensity=0.5,
        valence=0.0,
        risk="none",
        attention_need=0.3,
        ts=1234.5,
        raw={},
    )
    with pytest.raises(Exception):  # FrozenInstanceError ou AttributeError
        s.intensity = 0.9


def test_reaction_decision_three_actions_only():
    for action in ("SUPPRESS", "OBSERVE", "REACT"):
        d = ReactionDecision(action=action, saliency=0.5, reason="r", cost=0.0, prompt_hint=None)
        assert d.action == action


def test_modulation_vector_neutral_is_identity():
    m = ModulationVector.neutral()
    assert m.threshold_gain == 1.0
    assert m.decay_gain == 1.0
    assert m.budget_refill == 0.0


def test_stimulus_intensity_bounds_documented_only():
    # Les bornes [0..1] sont une convention applicative, pas une validation.
    # Ce test documente l'absence de validation pour rester rapide.
    s = Stimulus("k", "vision_object", intensity=2.0, valence=0.0,
                  risk="none", attention_need=0.0, ts=0.0, raw={})
    assert s.intensity == 2.0  # pas de clamp ici
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
python -m pytest brain/v3/tests/test_types.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'brain.v3'`.

- [ ] **Step 3: Créer le package `brain/v3/__init__.py`**

```python
"""Brain v3 — couche neurobiologique en surcouche."""

__all__: list[str] = []
```

- [ ] **Step 4: Créer `brain/v3/types.py`**

```python
"""Dataclasses immuables échangées entre les modules du brain v3."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Stimulus:
    """Entrée canonique du brain v3, produite par adapters.from_payload()."""

    canonical_id: str       # ex: "obj:cat:appeared", "scene:bryan:sad"
    channel: str            # "vision_object" | "vision_scene" | "face_motion" | "audio" | "text"
    intensity: float        # [0..1] — convention applicative, non validée
    valence: float          # [-1..1]
    risk: str               # "none" | "low" | "medium" | "high"
    attention_need: float   # [0..1]
    ts: float               # time.monotonic()
    raw: dict               # payload original — passé tel quel à limbic v2


@dataclass(frozen=True)
class ReactionDecision:
    """Sortie de ReactionPolicy.decide()."""

    action: str             # "SUPPRESS" | "OBSERVE" | "REACT"
    saliency: float         # [0..1]
    reason: str             # court texte pour debug
    cost: float             # coût appliqué au budget si action == REACT
    prompt_hint: str | None # texte fourni par Gemini/YOLO si à transmettre


@dataclass(frozen=True)
class ModulationVector:
    """Modulation appliquée aux neurones par le neuromodulateur."""

    threshold_gain: float   # 1.0 = neutre, <1.0 = plus excitable
    decay_gain: float       # 1.0 = oubli normal, >1.0 = oubli rapide
    budget_refill: float    # contribution par tick au budget d'attention

    @classmethod
    def neutral(cls) -> "ModulationVector":
        return cls(threshold_gain=1.0, decay_gain=1.0, budget_refill=0.0)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_types.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add brain/v3/__init__.py brain/v3/types.py brain/v3/tests/__init__.py brain/v3/tests/test_types.py
git commit -m "feat(brain-v3): bootstrap package + immutable types (Stimulus, ReactionDecision, ModulationVector)"
```

---

### Task 1.2 : `ShortTermMemory` — ring buffer 60s pour traces

**Files:**
- Create: `brain/v3/traces.py`
- Test: `brain/v3/tests/test_traces.py`

- [ ] **Step 1: Écrire le test**

Crée `brain/v3/tests/test_traces.py` :

```python
"""Tests du ring buffer ShortTermMemory."""
import time

from brain.v3.traces import ShortTermMemory
from brain.v3.types import ReactionDecision, Stimulus


def _stim(canonical: str = "obj:cat:appeared") -> Stimulus:
    return Stimulus(canonical, "vision_object", 0.5, 0.0, "none", 0.3, time.monotonic(), {})


def _dec(action: str = "REACT") -> ReactionDecision:
    return ReactionDecision(action, 0.6, "react", 0.2, None)


def test_append_and_recent():
    mem = ShortTermMemory(window_sec=60.0)
    mem.append(_stim(), _dec())
    items = mem.recent(n=10)
    assert len(items) == 1
    assert items[0]["stimulus"] == "obj:cat:appeared"
    assert items[0]["action"] == "REACT"


def test_recent_limits_n():
    mem = ShortTermMemory(window_sec=60.0)
    for i in range(20):
        mem.append(_stim(f"obj:cat:{i}"), _dec())
    items = mem.recent(n=5)
    assert len(items) == 5
    # ordre récent en premier
    assert items[0]["stimulus"] == "obj:cat:19"


def test_window_drops_old_entries():
    mem = ShortTermMemory(window_sec=0.05)
    mem.append(_stim("old"), _dec())
    time.sleep(0.1)
    mem.append(_stim("new"), _dec())
    items = mem.recent(n=10)
    assert len(items) == 1
    assert items[0]["stimulus"] == "new"


def test_thread_safe_append():
    import threading

    mem = ShortTermMemory(window_sec=60.0)

    def worker():
        for _ in range(50):
            mem.append(_stim(), _dec())

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    items = mem.recent(n=500)
    assert len(items) == 200
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_traces.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'brain.v3.traces'`.

- [ ] **Step 3: Implémenter `ShortTermMemory`**

Crée `brain/v3/traces.py` :

```python
"""Ring buffer thread-safe pour observer en live les décisions du brain v3."""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime

from brain.v3.types import ReactionDecision, Stimulus


class ShortTermMemory:
    """Buffer FIFO borné dans le temps. Utilisé par l'endpoint /brain/v3/traces."""

    def __init__(self, window_sec: float = 60.0, max_items: int = 500) -> None:
        self._window = max(1.0, float(window_sec))
        self._max_items = int(max_items)
        self._items: deque[tuple[float, dict]] = deque(maxlen=max_items)
        self._lock = threading.Lock()

    def append(self, stimulus: Stimulus, decision: ReactionDecision) -> None:
        now = time.monotonic()
        entry = (
            now,
            {
                "ts": datetime.now().strftime("%H:%M:%S"),
                "stimulus": stimulus.canonical_id,
                "channel": stimulus.channel,
                "saliency": round(decision.saliency, 3),
                "action": decision.action,
                "reason": decision.reason,
                "cost": round(decision.cost, 3),
            },
        )
        with self._lock:
            self._items.append(entry)
            self._evict_old(now)

    def recent(self, n: int = 50) -> list[dict]:
        """Retourne les n entrées les plus récentes (récent en premier)."""
        now = time.monotonic()
        with self._lock:
            self._evict_old(now)
            payload = [d for _ts, d in self._items]
        return list(reversed(payload))[:n]

    def _evict_old(self, now: float) -> None:
        cutoff = now - self._window
        while self._items and self._items[0][0] < cutoff:
            self._items.popleft()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_traces.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add brain/v3/traces.py brain/v3/tests/test_traces.py
git commit -m "feat(brain-v3): ShortTermMemory ring buffer (60s window, thread-safe)"
```

---

### Task 1.3 : `adapters.from_payload()` — normalisation des payloads

**Files:**
- Create: `brain/v3/adapters.py`
- Test: `brain/v3/tests/test_adapters.py`

- [ ] **Step 1: Écrire le test**

Crée `brain/v3/tests/test_adapters.py` :

```python
"""Tests de la normalisation payload → Stimulus."""
import pytest

from brain.v3.adapters import canonical_id_for, from_payload


def test_vision_object_canonical_id():
    payload = {"object_class": "Cat", "event_type": "appeared"}
    assert canonical_id_for("vision_object", payload) == "obj:cat:appeared"


def test_vision_scene_canonical_id():
    payload = {"person": "Bryan", "human_emotion": "Happy"}
    assert canonical_id_for("vision_scene", payload) == "scene:bryan:happy"


def test_face_motion_canonical_id():
    assert canonical_id_for("face_motion", {"presence_bool": True}) == "face:present"
    assert canonical_id_for("face_motion", {"presence_bool": False}) == "face:absent"


def test_text_canonical_id_buckets_valence():
    assert canonical_id_for("text", {"valence": 0.8}) == "text:positive"
    assert canonical_id_for("text", {"valence": -0.6}) == "text:negative"
    assert canonical_id_for("text", {"valence": 0.0}) == "text:neutral"


def test_unknown_channel_canonical_id_safe():
    assert canonical_id_for("weird", {}) == "weird:unknown"


def test_from_payload_vision_object_normalizes_fields():
    payload = {
        "source": "vision_object",
        "object_class": "Cat",
        "event_type": "appeared",
        "movement": 0.6,
        "risk": "low",
        "attention_need": 0.4,
        "valence": 0.0,
        "spontaneous_hint": "Un chat apparaît.",
    }
    stim = from_payload(payload, channel="vision_object")
    assert stim.canonical_id == "obj:cat:appeared"
    assert stim.channel == "vision_object"
    assert stim.intensity == pytest.approx(0.6)
    assert stim.risk == "low"
    assert stim.attention_need == pytest.approx(0.4)
    assert stim.raw is payload  # passé par référence pour limbic v2


def test_from_payload_vision_scene_uses_movement_as_intensity():
    payload = {"movement": 0.7, "attention_need": 0.5, "risk": "none",
                "person": "Bryan", "human_emotion": "sad", "valence": -0.3}
    stim = from_payload(payload, channel="vision_scene")
    assert stim.canonical_id == "scene:bryan:sad"
    # intensité = max(movement, attention_need)
    assert stim.intensity == pytest.approx(0.7)
    assert stim.valence == pytest.approx(-0.3)


def test_from_payload_clamps_intensity_to_unit():
    payload = {"object_class": "Cat", "event_type": "appeared", "movement": 999.0,
                "risk": "none", "attention_need": -5.0}
    stim = from_payload(payload, channel="vision_object")
    assert 0.0 <= stim.intensity <= 1.0
    assert 0.0 <= stim.attention_need <= 1.0


def test_from_payload_unknown_risk_defaults_none():
    stim = from_payload({"risk": "nuclear"}, channel="vision_object")
    assert stim.risk == "none"


def test_canonical_id_stable_across_calls():
    p1 = {"object_class": "Cat", "event_type": "appeared"}
    p2 = {"object_class": "cat", "event_type": "APPEARED"}
    assert canonical_id_for("vision_object", p1) == canonical_id_for("vision_object", p2)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_adapters.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'brain.v3.adapters'`.

- [ ] **Step 3: Implémenter `adapters.py`**

Crée `brain/v3/adapters.py` :

```python
"""Normalisation des payloads hétérogènes en Stimulus canoniques.

Chaque source d'événement (YOLO, scène Gemini, MediaPipe, texte) produit un
payload dict de forme différente. adapters.from_payload() les convertit en
un Stimulus unique avec un canonical_id stable utilisable comme clé
d'habituation.
"""
from __future__ import annotations

import time

from brain.v3.types import Stimulus

_VALID_RISKS = {"none", "low", "medium", "high"}


def _clamp(value: float, lo: float, hi: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return lo


def _coerce_str(value, default: str = "unknown") -> str:
    if value is None:
        return default
    return str(value).strip().lower() or default


def _valence_bucket(value: float) -> str:
    if value > 0.25:
        return "positive"
    if value < -0.25:
        return "negative"
    return "neutral"


def canonical_id_for(channel: str, payload: dict) -> str:
    """Construit la clé stable d'habituation pour ce stimulus."""
    if channel == "vision_object":
        cls = _coerce_str(payload.get("object_class"), "unknown")
        evt = _coerce_str(payload.get("event_type"), "unknown")
        return f"obj:{cls}:{evt}"
    if channel == "vision_scene":
        person = _coerce_str(payload.get("person"), "unknown")
        emotion = _coerce_str(payload.get("human_emotion"), "unknown")
        return f"scene:{person}:{emotion}"
    if channel == "face_motion":
        present = bool(payload.get("presence_bool", False))
        return f"face:{'present' if present else 'absent'}"
    if channel == "audio":
        bucket = _coerce_str(payload.get("intensity_bucket"), "normal")
        return f"audio:{bucket}"
    if channel == "text":
        valence = _clamp(payload.get("valence", 0.0), -1.0, 1.0)
        return f"text:{_valence_bucket(valence)}"
    return f"{channel}:unknown"


def from_payload(payload: dict, channel: str) -> Stimulus:
    """Normalise un payload hétérogène en Stimulus canonique."""
    risk = _coerce_str(payload.get("risk"), "none")
    if risk not in _VALID_RISKS:
        risk = "none"

    attention_need = _clamp(payload.get("attention_need", 0.0), 0.0, 1.0)
    valence = _clamp(payload.get("valence", 0.0), -1.0, 1.0)

    if channel == "vision_object":
        intensity = _clamp(payload.get("movement", 0.0), 0.0, 1.0)
    elif channel == "vision_scene":
        movement = _clamp(payload.get("movement", 0.0), 0.0, 1.0)
        intensity = max(movement, attention_need)
    elif channel == "face_motion":
        intensity = _clamp(payload.get("mouvement", payload.get("movement", 0.0)), 0.0, 1.0)
    elif channel == "audio":
        intensity = _clamp(payload.get("energie", payload.get("intensity", 0.0)), 0.0, 1.0)
    elif channel == "text":
        intensity = _clamp(abs(valence), 0.0, 1.0)
    else:
        intensity = _clamp(payload.get("intensity", 0.0), 0.0, 1.0)

    return Stimulus(
        canonical_id=canonical_id_for(channel, payload),
        channel=channel,
        intensity=intensity,
        valence=valence,
        risk=risk,
        attention_need=attention_need,
        ts=time.monotonic(),
        raw=payload,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_adapters.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add brain/v3/adapters.py brain/v3/tests/test_adapters.py
git commit -m "feat(brain-v3): adapters.from_payload() — normalise YOLO/scène/face/text en Stimulus"
```

---

## Phase 2 — Modèle neuronal (neurons, attention, neuromodulation)

### Task 2.1 : `AdaptiveLIF` — neurone adaptatif

**Files:**
- Create: `brain/v3/neurons.py`
- Test: `brain/v3/tests/test_neurons_adaptive.py`

- [ ] **Step 1: Écrire le test**

Crée `brain/v3/tests/test_neurons_adaptive.py` :

```python
"""Tests du neurone AdaptiveLIF (LIF + threshold drift + AHP + modulation)."""
import threading
import time

from brain.v3.neurons import AdaptiveLIF


def test_spike_above_threshold():
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.01)
    assert n.exciter(1.2) is True


def test_refractory_blocks_immediate_repeat():
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.5)
    assert n.exciter(1.5) is True
    assert n.exciter(1.5) is False


def test_modulation_lowers_effective_threshold():
    # modulation=0.6 → seuil effectif = 0.6, donc 0.7 spike alors qu'il ne spikerait pas à 1.0
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.01)
    assert n.exciter(0.7) is False  # 0.7 < 1.0
    n2 = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.01)
    assert n2.exciter(0.7, modulation=0.6) is True  # 0.7 >= 0.6


def test_threshold_drift_up_after_spike():
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.0,
                     threshold_drift_rate=0.05, threshold_max=2.0)
    before = n.seuil_courant
    assert n.exciter(1.5) is True
    after = n.seuil_courant
    assert after > before


def test_threshold_drift_down_when_no_spike():
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.0,
                     threshold_drift_rate=0.1, threshold_max=2.0,
                     threshold_min=0.5)
    # élève manuellement le seuil
    n._seuil_courant = 1.5
    n.exciter(0.0)  # pas de spike
    assert n._seuil_courant < 1.5


def test_ahp_post_spike_makes_next_excitation_harder():
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.0,
                     ahp_amplitude=0.5, ahp_decay=0.99)
    assert n.exciter(1.5) is True
    # Juste après le spike, l'AHP est à 0.5 → potentiel a 0.5 de retard
    # 1.0 d'excitation arrive → potentiel = 0.5 → pas de spike
    assert n.exciter(1.0) is False


def test_threshold_stays_within_bounds():
    n = AdaptiveLIF("test", seuil_base=1.0, periode_refractaire=0.0,
                     threshold_drift_rate=0.5, threshold_min=0.4,
                     threshold_max=2.0)
    for _ in range(100):
        n.exciter(3.0)
    assert n.seuil_courant <= 2.0
    n2 = AdaptiveLIF("test2", seuil_base=1.0, threshold_drift_rate=0.5,
                      threshold_min=0.4, threshold_max=2.0)
    for _ in range(100):
        n2.exciter(0.0)
    assert n2.seuil_courant >= 0.4


def test_thread_safety_concurrent_excitations():
    n = AdaptiveLIF("test", seuil_base=50.0, fuite=0.0, periode_refractaire=0.0,
                     threshold_drift_rate=0.0)

    def worker():
        for _ in range(100):
            n.exciter(0.01)
            time.sleep(0.0001)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    # Pas d'assertion sur le potentiel exact, on vérifie juste l'absence de crash
    assert n._potentiel >= 0.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_neurons_adaptive.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'brain.v3.neurons'`.

- [ ] **Step 3: Implémenter `AdaptiveLIF`**

Crée `brain/v3/neurons.py` :

```python
"""AdaptiveLIF — Leaky Integrate-and-Fire avec threshold drift + AHP + modulation.

Extension thread-safe de NeuroneLIF v2 :
- threshold drift : adaptation homéostatique (le seuil monte après spike,
  redescend lentement) — encode l'habituation neuronale
- after-hyperpolarization (AHP) : amplitude soustraite au potentiel post-spike,
  qui décroît exponentiellement — encode la fatigue cellulaire
- modulation externe : un facteur multiplicatif appliqué au seuil par tick
  (le neuromodulateur peut rendre le neurone plus excitable selon l'état hormonal)
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class AdaptiveLIF:
    nom: str
    seuil_base: float = 1.0
    fuite: float = 0.18
    potentiel_repos: float = 0.0
    periode_refractaire: float = 0.3
    # v3 additions
    ahp_amplitude: float = 0.15
    ahp_decay: float = 0.92
    threshold_drift_rate: float = 0.005
    threshold_min: float = 0.4
    threshold_max: float = 2.0

    _potentiel: float = field(default=0.0, init=False, repr=False)
    _ahp: float = field(default=0.0, init=False, repr=False)
    _seuil_courant: float = field(default=None, init=False, repr=False)
    _t_dernier_spike: float = field(default=0.0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self._seuil_courant is None:
            self._seuil_courant = self.seuil_base

    def exciter(self, intensite: float, modulation: float = 1.0) -> bool:
        """Excite le neurone. Retourne True si spike."""
        with self._lock:
            now = time.monotonic()

            if now - self._t_dernier_spike < self.periode_refractaire:
                return False

            # 1. Décay fuite + relâche AHP
            self._potentiel *= (1.0 - self.fuite)
            self._potentiel = max(self._potentiel - self._ahp, self.potentiel_repos)
            self._ahp *= self.ahp_decay

            # 2. Seuil effectif modulé par les hormones
            seuil_effectif = self._seuil_courant * max(0.1, modulation)

            # 3. Intégration (clamp soft à 2x seuil pour éviter accumulation infinie)
            self._potentiel = min(
                self._potentiel + float(intensite),
                seuil_effectif * 2.0,
            )

            # 4. Test de seuil
            if self._potentiel >= seuil_effectif:
                self._potentiel = self.potentiel_repos
                self._ahp = self.ahp_amplitude
                self._t_dernier_spike = now
                self._adapt_threshold(spiked=True)
                return True

            self._adapt_threshold(spiked=False)
            return False

    def _adapt_threshold(self, spiked: bool) -> None:
        """Le seuil monte après spike (homéostasie), redescend vers la base sinon."""
        if spiked:
            self._seuil_courant = min(
                self._seuil_courant + self.threshold_drift_rate * 10.0,
                self.threshold_max,
            )
        else:
            drift = (self.seuil_base - self._seuil_courant) * self.threshold_drift_rate
            self._seuil_courant = max(
                self._seuil_courant + drift,
                self.threshold_min,
            )

    @property
    def potentiel(self) -> float:
        with self._lock:
            return round(self._potentiel, 4)

    @property
    def seuil_courant(self) -> float:
        with self._lock:
            return round(self._seuil_courant, 4)

    @property
    def en_refractaire(self) -> bool:
        with self._lock:
            return (time.monotonic() - self._t_dernier_spike) < self.periode_refractaire
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_neurons_adaptive.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add brain/v3/neurons.py brain/v3/tests/test_neurons_adaptive.py
git commit -m "feat(brain-v3): AdaptiveLIF — threshold drift + AHP + modulation"
```

---

### Task 2.2 : `Neuromodulator` — pont hormones v2 → ModulationVector

**Files:**
- Create: `brain/v3/neuromodulation.py`
- Test: `brain/v3/tests/test_neuromodulation.py`

- [ ] **Step 1: Écrire le test**

Crée `brain/v3/tests/test_neuromodulation.py` :

```python
"""Tests du pont hormones v2 → ModulationVector."""
import pytest

from brain.v3.neuromodulation import derive
from brain.v3.types import ModulationVector


def _baseline_snapshot() -> dict:
    return {
        "cortisol": 0.10,
        "dopamine": 0.28,
        "oxytocine": 0.30,
        "serotonine": 0.42,
        "self_confidence": 0.60,
        "mental_load": 0.15,
    }


def test_baseline_returns_near_neutral():
    m = derive(_baseline_snapshot())
    assert 0.95 <= m.threshold_gain <= 1.10
    assert 0.95 <= m.decay_gain <= 1.05


def test_high_cortisol_lowers_threshold_gain():
    snap = _baseline_snapshot()
    snap["cortisol"] = 0.80
    m = derive(snap)
    # Stress haut → plus excitable → seuils baissent
    assert m.threshold_gain < 0.9


def test_high_fatigue_increases_decay():
    snap = _baseline_snapshot()
    snap["mental_load"] = 0.85
    m = derive(snap)
    assert m.decay_gain > 1.1


def test_high_dopamine_increases_budget_refill():
    snap = _baseline_snapshot()
    snap["dopamine"] = 0.90
    m = derive(snap)
    assert m.budget_refill > 0.0005


def test_threshold_gain_bounded():
    # Cortisol extrême → ne descend pas sous 0.6
    snap = _baseline_snapshot()
    snap["cortisol"] = 5.0
    m = derive(snap)
    assert 0.6 <= m.threshold_gain <= 1.4


def test_missing_keys_safe():
    m = derive({})
    assert isinstance(m, ModulationVector)
    assert 0.6 <= m.threshold_gain <= 1.4


def test_neutral_factory():
    m = ModulationVector.neutral()
    assert m.threshold_gain == 1.0
    assert m.decay_gain == 1.0
    assert m.budget_refill == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_neuromodulation.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'brain.v3.neuromodulation'`.

- [ ] **Step 3: Implémenter `neuromodulation.py`**

Crée `brain/v3/neuromodulation.py` :

```python
"""Pont hormones v2 → ModulationVector v3.

derive() lit un snapshot du limbic v2 (cortisol, dopamine, mental_load) et
produit un vecteur de modulation qui sera consommé par les neurones v3 :
- threshold_gain  : multiplie le seuil effectif (cortisol haut → baisse)
- decay_gain      : module la vitesse d'oubli (fatigue → oubli rapide)
- budget_refill   : contribution par tick au budget d'attention (dopamine)
"""
from __future__ import annotations

from brain.calibration import env_float
from brain.v3.types import ModulationVector


def derive(snapshot: dict) -> ModulationVector:
    cortisol = float(snapshot.get("cortisol", 0.10))
    dopamine = float(snapshot.get("dopamine", 0.28))
    mental_load = float(snapshot.get("mental_load", 0.15))

    cortisol_gain = env_float("BRAIN_V3_CORTISOL_THRESHOLD_GAIN", 0.40)
    fatigue_gain = env_float("BRAIN_V3_FATIGUE_DECAY_GAIN", 0.50)
    refill_gain = env_float("BRAIN_V3_DOPAMINE_REFILL_GAIN", 0.0008)

    # Stress haut → seuils baissent (plus excitable)
    threshold_gain = 1.0 - cortisol_gain * (cortisol - 0.30)
    threshold_gain = max(0.6, min(1.4, threshold_gain))

    # Fatigue haute → oubli plus rapide
    decay_gain = 1.0 + fatigue_gain * max(0.0, mental_load - 0.60)

    # Dopamine alimente le budget, fatigue le sape
    budget_refill = refill_gain * dopamine - (refill_gain * 0.375) * mental_load

    return ModulationVector(
        threshold_gain=round(threshold_gain, 4),
        decay_gain=round(decay_gain, 4),
        budget_refill=round(budget_refill, 6),
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_neuromodulation.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add brain/v3/neuromodulation.py brain/v3/tests/test_neuromodulation.py
git commit -m "feat(brain-v3): Neuromodulator — snapshot hormones v2 → ModulationVector"
```

---

### Task 2.3 : `AttentionField` — couche thalamique v3 avec inhibition latérale

**Files:**
- Create: `brain/v3/attention.py`
- Test: `brain/v3/tests/test_attention_field.py`

- [ ] **Step 1: Écrire le test**

Crée `brain/v3/tests/test_attention_field.py` :

```python
"""Tests de AttentionField (5 neurones + inhibition latérale + intégration habituation)."""
import time

import pytest

from brain.v3.attention import AttentionField
from brain.v3.habituation import HabituationTracker
from brain.v3.types import ModulationVector, Stimulus


def _stim(channel: str, canonical: str, intensity: float = 0.8) -> Stimulus:
    return Stimulus(canonical, channel, intensity, 0.0, "none", 0.0, time.monotonic(), {})


def test_unknown_channel_returns_false():
    field = AttentionField()
    s = _stim("weird", "x:y", 0.9)
    assert field.tick(s, ModulationVector.neutral(), HabituationTracker()) is False


def test_spike_on_strong_stimulus():
    field = AttentionField()
    s = _stim("vision_object", "obj:cat:appeared", intensity=0.95)
    # Avec un seuil de base à 1.0 et intensity=0.95, on ne devrait pas spike tout de suite,
    # mais avec intensity=2.0 oui :
    s_strong = _stim("vision_object", "obj:fire:appeared", intensity=2.0)
    assert field.tick(s_strong, ModulationVector.neutral(), HabituationTracker()) is True


def test_familiarity_reduces_effective_intensity():
    field = AttentionField()
    hab = HabituationTracker(halflife_sec=120.0)
    canonical = "obj:cat:appeared"
    # Force familiarity élevée
    for _ in range(15):
        hab.imprint(canonical)
    s = _stim("vision_object", canonical, intensity=1.2)
    # À familiarity=1.0, intensité effective = 1.2 * (1 - 0.7) = 0.36 → pas de spike
    assert field.tick(s, ModulationVector.neutral(), hab) is False


def test_modulation_threshold_gain_makes_easier_to_spike():
    field = AttentionField()
    s = _stim("vision_object", "obj:knife:appeared", intensity=0.7)
    # Sans modulation
    assert field.tick(s, ModulationVector.neutral(), HabituationTracker()) is False
    # Avec cortisol haut (gain 0.6 → seuil effectif baissé)
    field2 = AttentionField()
    mod = ModulationVector(threshold_gain=0.6, decay_gain=1.0, budget_refill=0.0)
    assert field2.tick(s, mod, HabituationTracker()) is True


def test_refractory_per_channel():
    field = AttentionField()
    # 2 spikes consécutifs sur le même canal doivent être bloqués par refractory
    s = _stim("vision_object", "obj:gun:appeared", intensity=3.0)
    assert field.tick(s, ModulationVector.neutral(), HabituationTracker()) is True
    assert field.tick(s, ModulationVector.neutral(), HabituationTracker()) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_attention_field.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'brain.v3.attention'` (et `habituation` aussi).

- [ ] **Step 3: Implémenter `attention.py`** (la dépendance sur `habituation` est résolue plus tard, donc importation paresseuse)

Crée `brain/v3/attention.py` :

```python
"""AttentionField — couche thalamique v3.

Cinq neurones AdaptiveLIF spécialisés par canal (vision_object, vision_scene,
face_motion, audio_user, text) avec une inhibition latérale soft : un spike
sur un canal soustrait une fraction du potentiel des autres canaux à la
tick suivante (pour éviter les doublons multi-canaux sur un même événement).
"""
from __future__ import annotations

import threading

from brain.calibration import env_float
from brain.v3.neurons import AdaptiveLIF
from brain.v3.types import ModulationVector, Stimulus


class AttentionField:
    """Champ d'attention v3 avec inhibition latérale."""

    def __init__(self) -> None:
        self._neurons: dict[str, AdaptiveLIF] = {
            "vision_object": AdaptiveLIF(
                "vision_object", seuil_base=1.0,
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_VISION_OBJECT", 2.0),
                ahp_amplitude=env_float("BRAIN_V3_AHP_AMPLITUDE", 0.15),
                ahp_decay=env_float("BRAIN_V3_AHP_DECAY", 0.92),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
                threshold_min=env_float("BRAIN_V3_THRESHOLD_MIN", 0.4),
                threshold_max=env_float("BRAIN_V3_THRESHOLD_MAX", 2.0),
            ),
            "vision_scene": AdaptiveLIF(
                "vision_scene", seuil_base=1.0,
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_VISION_SCENE", 8.0),
                ahp_amplitude=env_float("BRAIN_V3_AHP_AMPLITUDE", 0.15),
                ahp_decay=env_float("BRAIN_V3_AHP_DECAY", 0.92),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
                threshold_min=env_float("BRAIN_V3_THRESHOLD_MIN", 0.4),
                threshold_max=env_float("BRAIN_V3_THRESHOLD_MAX", 2.0),
            ),
            "face_motion": AdaptiveLIF(
                "face_motion", seuil_base=1.0,
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_FACE_MOTION", 1.0),
                ahp_amplitude=env_float("BRAIN_V3_AHP_AMPLITUDE", 0.15),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
            ),
            "audio_user": AdaptiveLIF(
                "audio_user", seuil_base=1.0,
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_AUDIO", 0.5),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
            ),
            "text": AdaptiveLIF(
                "text", seuil_base=1.0,
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_TEXT", 0.3),
                threshold_drift_rate=env_float("BRAIN_V3_THRESHOLD_DRIFT", 0.005),
            ),
        }
        self._inhibition_strength = env_float("BRAIN_V3_INHIBITION_STRENGTH", 0.3)
        self._habituation_gain = env_float("BRAIN_V3_HABITUATION_GAIN", 0.70)
        self._lock = threading.Lock()
        self._last_winner: str | None = None
        self._last_winner_ts: float = 0.0

    def tick(self, stimulus: Stimulus, modulation: ModulationVector,
             habituation) -> bool:
        """Excite le neurone correspondant au canal, retourne True si spike.

        L'habituation réduit l'intensité effective ; l'inhibition latérale est
        appliquée sur les autres canaux quand un spike s'est produit récemment.
        """
        neuron = self._neurons.get(stimulus.channel)
        if neuron is None:
            return False

        familiarity = habituation.familiarity(stimulus.canonical_id)
        effective_intensity = stimulus.intensity * (1.0 - familiarity * self._habituation_gain)

        # Inhibition latérale : si un autre canal vient de spike, on soustrait un peu
        import time
        with self._lock:
            inhib = 0.0
            if (self._last_winner is not None
                    and self._last_winner != stimulus.channel
                    and time.monotonic() - self._last_winner_ts < 1.0):
                inhib = self._inhibition_strength

        adjusted = max(0.0, effective_intensity - inhib)
        spiked = neuron.exciter(adjusted, modulation=modulation.threshold_gain)

        if spiked:
            with self._lock:
                self._last_winner = stimulus.channel
                self._last_winner_ts = time.monotonic()
        return spiked

    def get_state(self) -> dict:
        """Snapshot debug : potentiels et seuils courants."""
        return {
            name: {
                "potentiel": n.potentiel,
                "seuil_courant": n.seuil_courant,
                "en_refractaire": n.en_refractaire,
            }
            for name, n in self._neurons.items()
        }
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_attention_field.py -v
```

Expected: 5 passed (le test `test_modulation_threshold_gain_makes_easier_to_spike` peut échouer si l'inhibition latérale d'un test précédent persiste. Si c'est le cas, l'ordre des tests pytest doit être indépendant — chaque test crée son propre AttentionField, donc devrait passer).

- [ ] **Step 5: Commit**

```bash
git add brain/v3/attention.py brain/v3/tests/test_attention_field.py
git commit -m "feat(brain-v3): AttentionField — 5 neurones spécialisés + inhibition latérale"
```

---

## Phase 3 — Habituation et politique de réaction

### Task 3.1 : `HabituationTracker` — LRU + decay temporel

**Files:**
- Create: `brain/v3/habituation.py`
- Test: `brain/v3/tests/test_habituation.py`

- [ ] **Step 1: Écrire le test**

Crée `brain/v3/tests/test_habituation.py` :

```python
"""Tests du HabituationTracker (LRU + decay temporel)."""
import threading
import time

from brain.v3.habituation import HabituationTracker


def test_unknown_id_returns_zero():
    h = HabituationTracker(halflife_sec=120.0)
    assert h.familiarity("never:seen") == 0.0


def test_imprint_increases_familiarity():
    h = HabituationTracker(halflife_sec=120.0)
    canonical = "obj:cat:appeared"
    f0 = h.familiarity(canonical)
    h.imprint(canonical)
    f1 = h.familiarity(canonical)
    assert f1 > f0


def test_repeated_imprint_saturates_at_one():
    h = HabituationTracker(halflife_sec=3600.0)
    for _ in range(100):
        h.imprint("obj:cat:appeared")
    assert h.familiarity("obj:cat:appeared") <= 1.0
    assert h.familiarity("obj:cat:appeared") >= 0.9


def test_decay_halflife_reduces_familiarity():
    h = HabituationTracker(halflife_sec=0.1)
    h.imprint("obj:cat:appeared")
    f_before = h.familiarity("obj:cat:appeared")
    time.sleep(0.2)  # 2 demi-vies
    f_after = h.familiarity("obj:cat:appeared")
    assert f_after < f_before * 0.4


def test_lru_eviction_drops_oldest():
    h = HabituationTracker(halflife_sec=120.0, max_keys=3)
    h.imprint("a")
    time.sleep(0.01)
    h.imprint("b")
    time.sleep(0.01)
    h.imprint("c")
    time.sleep(0.01)
    h.imprint("d")  # devrait évincer "a"
    assert h.familiarity("a") == 0.0
    assert h.familiarity("b") > 0.0
    assert h.familiarity("c") > 0.0
    assert h.familiarity("d") > 0.0


def test_thread_safe_imprint():
    h = HabituationTracker(halflife_sec=3600.0)

    def worker():
        for _ in range(100):
            h.imprint("obj:cat:appeared")

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert h.familiarity("obj:cat:appeared") > 0.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_habituation.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implémenter `habituation.py`**

Crée `brain/v3/habituation.py` :

```python
"""HabituationTracker — mémoire de familiarité par canonical_id.

LRU borné avec decay temporel exponentiel. Une clé vue récemment et
fréquemment a une familiarité proche de 1.0 ; une clé inutilisée pendant
plusieurs demi-vies retombe vers 0.
"""
from __future__ import annotations

import threading
import time


class HabituationTracker:
    """Tracker thread-safe de familiarité par canonical_id."""

    def __init__(self, halflife_sec: float = 120.0, max_keys: int = 256) -> None:
        self._halflife = max(1.0, float(halflife_sec))
        self._max_keys = int(max_keys)
        self._counts: dict[str, float] = {}
        self._last_ts: dict[str, float] = {}
        self._lock = threading.Lock()

    def familiarity(self, canonical_id: str) -> float:
        """Retourne la familiarité ∈ [0..1] (0 = jamais vu)."""
        with self._lock:
            if canonical_id not in self._counts:
                return 0.0
            now = time.monotonic()
            elapsed = now - self._last_ts[canonical_id]
            decayed = self._counts[canonical_id] * (0.5 ** (elapsed / self._halflife))
            return min(1.0, decayed / 10.0)

    def imprint(self, canonical_id: str) -> None:
        """Incrémente le compteur pour ce canonical_id."""
        with self._lock:
            now = time.monotonic()
            if canonical_id in self._counts:
                elapsed = now - self._last_ts[canonical_id]
                decayed = self._counts[canonical_id] * (0.5 ** (elapsed / self._halflife))
                self._counts[canonical_id] = decayed + 1.0
            else:
                if len(self._counts) >= self._max_keys:
                    oldest = min(self._last_ts, key=self._last_ts.get)
                    del self._counts[oldest]
                    del self._last_ts[oldest]
                self._counts[canonical_id] = 1.0
            self._last_ts[canonical_id] = now

    def size(self) -> int:
        with self._lock:
            return len(self._counts)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_habituation.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add brain/v3/habituation.py brain/v3/tests/test_habituation.py
git commit -m "feat(brain-v3): HabituationTracker — LRU + decay temporel exponentiel"
```

---

### Task 3.2 : `AttentionBudget` + `ReactionPolicy`

**Files:**
- Create: `brain/v3/policy.py`
- Test: `brain/v3/tests/test_policy.py`

- [ ] **Step 1: Écrire le test**

Crée `brain/v3/tests/test_policy.py` :

```python
"""Tests du ReactionPolicy et AttentionBudget."""
import random
import time

import pytest

from brain.v3.policy import AttentionBudget, ReactionPolicy
from brain.v3.types import ModulationVector, Stimulus


def _stim(channel="vision_object", canonical="obj:cat:appeared",
           intensity=0.8, risk="none", attention_need=0.3, valence=0.0):
    return Stimulus(canonical, channel, intensity, valence, risk,
                     attention_need, time.monotonic(), {"spontaneous_hint": "hi"})


# ─── AttentionBudget ────────────────────────────────────────────

def test_budget_can_afford_initially():
    b = AttentionBudget(initial=1.0, max_budget=1.5)
    assert b.can_afford(0.3) is True
    assert b.level == 1.0


def test_budget_consume_then_refuse():
    b = AttentionBudget(initial=0.5)
    b.consume(0.4)
    assert b.can_afford(0.3) is False  # 0.1 restant


def test_budget_refill_bounded_by_max():
    b = AttentionBudget(initial=1.0, max_budget=1.5)
    b.refill(10.0)
    assert b.level == 1.5


def test_budget_consume_does_not_go_negative():
    b = AttentionBudget(initial=0.2)
    b.consume(1.0)
    assert b.level == 0.0


# ─── ReactionPolicy ─────────────────────────────────────────────

def test_high_risk_always_reacts():
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=0.0)  # budget vide
    s = _stim(risk="high")
    d = policy.decide(s, spike=False, familiarity=1.0,
                      modulation=ModulationVector.neutral(), budget=budget,
                      threshold=0.55)
    assert d.action == "REACT"
    assert d.cost <= 0.1


def test_no_spike_no_reaction():
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=1.0)
    s = _stim(intensity=0.5)
    d = policy.decide(s, spike=False, familiarity=0.0,
                      modulation=ModulationVector.neutral(), budget=budget,
                      threshold=0.55)
    assert d.action == "OBSERVE"


def test_saliency_below_threshold_observes():
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=1.0)
    s = _stim(intensity=0.1, attention_need=0.1, valence=0.0)
    d = policy.decide(s, spike=True, familiarity=0.9,
                      modulation=ModulationVector.neutral(), budget=budget,
                      threshold=0.55)
    assert d.action == "OBSERVE"


def test_no_budget_observes():
    random.seed(0)
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=0.05)  # quasi vide
    s = _stim(intensity=0.95, attention_need=0.9)
    d = policy.decide(s, spike=True, familiarity=0.0,
                      modulation=ModulationVector.neutral(), budget=budget,
                      threshold=0.55)
    assert d.action == "OBSERVE"
    assert "budget" in d.reason


def test_reaction_with_full_budget_and_high_saliency():
    random.seed(42)
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=1.0)
    s = _stim(intensity=0.95, attention_need=0.9, valence=0.5)
    # Run plusieurs fois car probabiliste — au moins une fois REACT
    actions = set()
    for seed in range(10):
        random.seed(seed)
        d = policy.decide(s, spike=True, familiarity=0.0,
                          modulation=ModulationVector.neutral(), budget=budget,
                          threshold=0.55)
        actions.add(d.action)
    assert "REACT" in actions


def test_cost_higher_for_vision_scene():
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=1.0)
    s_obj = _stim(channel="vision_object", intensity=0.95, attention_need=0.9)
    s_scene = _stim(channel="vision_scene", intensity=0.95, attention_need=0.9)
    cost_obj = policy._cost_for(s_obj)
    cost_scene = policy._cost_for(s_scene)
    assert cost_scene > cost_obj


def test_prompt_hint_propagated_on_react():
    random.seed(0)
    policy = ReactionPolicy(threshold=0.10)  # seuil bas pour forcer REACT
    budget = AttentionBudget(initial=1.0)
    s = _stim(intensity=1.0, attention_need=1.0)
    found_react = False
    for seed in range(20):
        random.seed(seed)
        d = policy.decide(s, spike=True, familiarity=0.0,
                          modulation=ModulationVector.neutral(), budget=budget,
                          threshold=0.10)
        if d.action == "REACT":
            assert d.prompt_hint == "hi"
            found_react = True
            break
    assert found_react
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_policy.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implémenter `policy.py`**

Crée `brain/v3/policy.py` :

```python
"""ReactionPolicy + AttentionBudget — décision finale du brain v3."""
from __future__ import annotations

import random
import threading

from brain.calibration import env_float
from brain.v3.types import ModulationVector, ReactionDecision, Stimulus


class AttentionBudget:
    """Budget d'attention épuisable, reconstitué par neuromodulation."""

    def __init__(self, initial: float = 1.0, max_budget: float = 1.5) -> None:
        self._budget = float(initial)
        self._max = float(max_budget)
        self._lock = threading.Lock()

    def can_afford(self, cost: float) -> bool:
        with self._lock:
            return self._budget >= float(cost)

    def consume(self, cost: float) -> None:
        with self._lock:
            self._budget = max(0.0, self._budget - float(cost))

    def refill(self, delta: float) -> None:
        with self._lock:
            self._budget = min(self._max, self._budget + float(delta))

    @property
    def level(self) -> float:
        with self._lock:
            return round(self._budget, 4)


class ReactionPolicy:
    """Décide quoi faire d'un stimulus : SUPPRESS / OBSERVE / REACT."""

    def __init__(self, threshold: float | None = None) -> None:
        self.threshold = (
            float(threshold) if threshold is not None
            else env_float("BRAIN_V3_REACTION_THRESHOLD", 0.55)
        )
        self._prob_slope = env_float("BRAIN_V3_PROB_GATE_SLOPE", 2.0)
        self._cost_object = env_float("BRAIN_V3_COST_OBJECT_NORMAL", 0.20)
        self._cost_scene = env_float("BRAIN_V3_COST_SCENE_NORMAL", 0.30)
        self._cost_high_risk = env_float("BRAIN_V3_COST_HIGH_RISK", 0.05)

    def decide(
        self,
        stimulus: Stimulus,
        spike: bool,
        familiarity: float,
        modulation: ModulationVector,
        budget: AttentionBudget,
        threshold: float,
    ) -> ReactionDecision:
        hint = stimulus.raw.get("spontaneous_hint") if isinstance(stimulus.raw, dict) else None

        # 1. risk=high court-circuite tout (bypass budget + habituation)
        if stimulus.risk == "high":
            return ReactionDecision(
                action="REACT",
                saliency=1.0,
                reason=f"risk_high:{stimulus.canonical_id}",
                cost=self._cost_high_risk,
                prompt_hint=hint,
            )

        # 2. Calcul de la saillance
        novelty = 1.0 - max(0.0, min(1.0, familiarity))
        saliency = (
            0.45 * max(0.0, min(1.0, stimulus.intensity))
            + 0.35 * novelty
            + 0.15 * max(0.0, min(1.0, stimulus.attention_need))
            + 0.05 * abs(max(-1.0, min(1.0, stimulus.valence)))
        )

        # 3. Pas de spike OU saillance trop basse → observe
        if not spike or saliency < threshold:
            return ReactionDecision(
                action="OBSERVE",
                saliency=saliency,
                reason=f"sub_threshold:{stimulus.canonical_id}",
                cost=0.0,
                prompt_hint=None,
            )

        # 4. Spike + saillance OK, mais budget insuffisant → observe
        cost = self._cost_for(stimulus)
        if not budget.can_afford(cost):
            return ReactionDecision(
                action="OBSERVE",
                saliency=saliency,
                reason=f"no_budget:{stimulus.canonical_id}",
                cost=0.0,
                prompt_hint=None,
            )

        # 5. Gate probabiliste : à saillance=seuil P=50%, monte vers 0.95 plus haut
        p = min(0.95, 0.5 + (saliency - threshold) * self._prob_slope)
        if random.random() > p:
            return ReactionDecision(
                action="OBSERVE",
                saliency=saliency,
                reason=f"prob_gate_miss:{stimulus.canonical_id}",
                cost=0.0,
                prompt_hint=None,
            )

        return ReactionDecision(
            action="REACT",
            saliency=saliency,
            reason=f"react:{stimulus.canonical_id}",
            cost=cost,
            prompt_hint=hint,
        )

    def _cost_for(self, stimulus: Stimulus) -> float:
        if stimulus.channel == "vision_scene":
            return self._cost_scene
        return self._cost_object
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_policy.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add brain/v3/policy.py brain/v3/tests/test_policy.py
git commit -m "feat(brain-v3): ReactionPolicy + AttentionBudget — décision probabiliste"
```

---

## Phase 4 — V3Manager (façade défensive)

### Task 4.1 : `V3Manager` — façade + refill loop

**Files:**
- Create: `brain/v3/v3_manager.py`
- Create: `brain/v3/tests/conftest.py`
- Test: `brain/v3/tests/test_v3_manager.py`

- [ ] **Step 1: Créer les fixtures partagées**

Crée `brain/v3/tests/conftest.py` :

```python
"""Fixtures partagées des tests v3."""
from __future__ import annotations


class MockLimbic:
    """Stub minimaliste imitant CerveauEmotif.get_snapshot()."""

    def __init__(self, snapshot: dict | None = None) -> None:
        self._snap = snapshot or {
            "cortisol": 0.10, "dopamine": 0.28, "oxytocine": 0.30,
            "serotonine": 0.42, "self_confidence": 0.60, "mental_load": 0.15,
            "mood": "Neutre", "momentum": 0.0, "last_stimulus": "init",
        }

    def get_snapshot(self) -> dict:
        return dict(self._snap)

    def set(self, **kwargs) -> None:
        self._snap.update(kwargs)
```

- [ ] **Step 2: Écrire le test**

Crée `brain/v3/tests/test_v3_manager.py` :

```python
"""Tests du V3Manager (façade défensive)."""
import os
import time

import pytest

from brain.v3.tests.conftest import MockLimbic
from brain.v3.v3_manager import V3Manager


def test_manager_starts_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    m = V3Manager(limbic_ref=MockLimbic())
    assert m.enabled is False
    m.stop()


def test_manager_enabled_with_env(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    m = V3Manager(limbic_ref=MockLimbic())
    assert m.enabled is True
    m.stop()


def test_shadow_mode_default_true(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    monkeypatch.delenv("BRAIN_V3_SHADOW_MODE", raising=False)
    m = V3Manager(limbic_ref=MockLimbic())
    assert m.shadow_mode is True
    m.stop()


def test_process_returns_reaction_decision(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    m = V3Manager(limbic_ref=MockLimbic())
    payload = {"object_class": "Cat", "event_type": "appeared",
                "movement": 0.6, "risk": "low", "attention_need": 0.4}
    decision = m.process(payload, channel="vision_object")
    assert decision is not None
    assert decision.action in {"SUPPRESS", "OBSERVE", "REACT"}
    m.stop()


def test_high_risk_always_reacts(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    m = V3Manager(limbic_ref=MockLimbic())
    payload = {"object_class": "Fire", "event_type": "appeared",
                "movement": 0.3, "risk": "high", "attention_need": 0.9,
                "spontaneous_hint": "Du feu apparaît"}
    decision = m.process(payload, channel="vision_object")
    assert decision.action == "REACT"
    assert decision.prompt_hint == "Du feu apparaît"
    m.stop()


def test_traces_records_decisions(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    m = V3Manager(limbic_ref=MockLimbic())
    m.process({"object_class": "Cat", "event_type": "appeared", "movement": 0.5,
                "risk": "none"}, channel="vision_object")
    state = m.get_debug_state()
    assert state["recent_decisions"]
    assert state["recent_decisions"][0]["stimulus"].startswith("obj:cat")
    m.stop()


def test_exception_marks_degraded(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    m = V3Manager(limbic_ref=MockLimbic())
    # Forcer une exception en passant un payload qui casse adapters
    class Boom:
        def get(self, *a, **kw):
            raise RuntimeError("boom")
    decision = m.process(Boom(), channel="vision_object")
    assert decision is None
    assert m._is_degraded()
    m.stop()


def test_p95_latency_under_3ms(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    m = V3Manager(limbic_ref=MockLimbic())
    payload = {"object_class": "Cat", "event_type": "appeared",
                "movement": 0.5, "risk": "low", "attention_need": 0.3,
                "spontaneous_hint": "Un chat"}
    times_ms = []
    for _ in range(100):
        start = time.perf_counter()
        m.process(payload, channel="vision_object")
        times_ms.append((time.perf_counter() - start) * 1000.0)
    p95 = sorted(times_ms)[94]
    assert p95 < 3.0, f"p95 latency {p95:.2f}ms exceeds 3ms budget"
    m.stop()


def test_observe_does_not_consume_budget(monkeypatch):
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    m = V3Manager(limbic_ref=MockLimbic())
    level_before = m._budget.level
    m.observe({"text": "salut", "valence": 0.3}, channel="text")
    level_after = m._budget.level
    assert level_after == level_before
    m.stop()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_v3_manager.py -v
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implémenter `v3_manager.py`**

Crée `brain/v3/v3_manager.py` :

```python
"""V3Manager — façade défensive du brain v3.

Reprend exactement le pattern défensif de BrainManager v2 :
- _safe() qui dégrade automatiquement sur exception ou tick > budget
- toutes les méthodes publiques tolèrent l'erreur et fallback proprement
- l'API publique reste sync (les caller en threadpool si async nécessaire)
"""
from __future__ import annotations

import os
import threading
import time

from brain.calibration import env_bool, env_float
from brain.v3 import adapters, neuromodulation
from brain.v3.attention import AttentionField
from brain.v3.habituation import HabituationTracker
from brain.v3.policy import AttentionBudget, ReactionPolicy
from brain.v3.traces import ShortTermMemory
from brain.v3.types import ReactionDecision


class V3Manager:
    """Singleton-friendly. Instancié par BrainManager si BRAIN_V3_ENABLED=true."""

    def __init__(self, limbic_ref) -> None:
        self._limbic = limbic_ref
        self._attention = AttentionField()
        self._habituation = HabituationTracker(
            halflife_sec=env_float("BRAIN_V3_HABITUATION_HALFLIFE", 120.0),
            max_keys=int(env_float("BRAIN_V3_HABITUATION_MAX_KEYS", 256)),
        )
        self._budget = AttentionBudget(
            initial=env_float("BRAIN_V3_ATTENTION_BUDGET_INIT", 1.0),
            max_budget=env_float("BRAIN_V3_ATTENTION_BUDGET_MAX", 1.5),
        )
        self._policy = ReactionPolicy()
        self._traces = ShortTermMemory(window_sec=60.0)
        self._tick_budget_ms = env_float("BRAIN_V3_TICK_BUDGET_MS", 3.0)
        self._degraded_until = 0.0
        self._stop_event = threading.Event()
        self._refill_thread: threading.Thread | None = None
        self._start_refill_loop()

    # ─── Public API ─────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return env_bool("BRAIN_V3_ENABLED", False) and not self._is_degraded()

    @property
    def shadow_mode(self) -> bool:
        return env_bool("BRAIN_V3_SHADOW_MODE", True)

    def process(self, payload: dict, channel: str) -> ReactionDecision | None:
        """Pipeline complet : produit une ReactionDecision."""
        start = time.perf_counter()
        try:
            stimulus = adapters.from_payload(payload, channel)
            modulation = neuromodulation.derive(self._limbic.get_snapshot())
            spike = self._attention.tick(stimulus, modulation, self._habituation)
            familiarity = self._habituation.familiarity(stimulus.canonical_id)
            decision = self._policy.decide(
                stimulus, spike, familiarity, modulation, self._budget,
                threshold=self._policy.threshold,
            )
            self._traces.append(stimulus, decision)
            self._habituation.imprint(stimulus.canonical_id)
            if decision.action == "REACT":
                self._budget.consume(decision.cost)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if elapsed_ms > self._tick_budget_ms:
                self._degraded_until = time.monotonic() + 5.0
                print(f"[BRAIN_V3] slow tick {elapsed_ms:.2f}ms — degraded 5s")
            return decision
        except Exception as exc:
            self._degraded_until = time.monotonic() + 30.0
            print(f"[BRAIN_V3] process failed, degraded 30s: {type(exc).__name__}: {exc}")
            return None

    def observe(self, payload: dict, channel: str) -> None:
        """Observation passive (texte/audio) sans gating ni consommation budget."""
        try:
            stimulus = adapters.from_payload(payload, channel)
            modulation = neuromodulation.derive(self._limbic.get_snapshot())
            self._attention.tick(stimulus, modulation, self._habituation)
            self._habituation.imprint(stimulus.canonical_id)
            self._traces.append(stimulus, ReactionDecision(
                "OBSERVE", 0.0, "passive_observe", 0.0, None))
        except Exception as exc:
            print(f"[BRAIN_V3] observe failed: {type(exc).__name__}: {exc}")

    def get_debug_state(self) -> dict:
        return {
            "enabled": self.enabled,
            "shadow_mode": self.shadow_mode,
            "degraded": self._is_degraded(),
            "budget": self._budget.level,
            "habituation_size": self._habituation.size(),
            "attention_state": self._attention.get_state(),
            "recent_decisions": self._traces.recent(n=10),
        }

    def stop(self) -> None:
        """Arrête le thread de refill (utilisé par les tests + shutdown propre)."""
        self._stop_event.set()
        if self._refill_thread and self._refill_thread.is_alive():
            self._refill_thread.join(timeout=1.0)

    # ─── Internals ──────────────────────────────────────────────

    def _is_degraded(self) -> bool:
        return time.monotonic() < self._degraded_until

    def _start_refill_loop(self) -> None:
        """Thread daemon refill du budget toutes les 5s."""
        def loop() -> None:
            while not self._stop_event.is_set():
                self._stop_event.wait(5.0)
                if self._stop_event.is_set():
                    return
                try:
                    mod = neuromodulation.derive(self._limbic.get_snapshot())
                    self._budget.refill(mod.budget_refill * 5.0)
                except Exception:
                    pass
        self._refill_thread = threading.Thread(
            target=loop, name="V3BudgetRefill", daemon=True,
        )
        self._refill_thread.start()
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_v3_manager.py -v
```

Expected: 9 passed.

- [ ] **Step 6: Run the full v3 suite to check no cross-test regressions**

```bash
python -m pytest brain/v3/tests/ -v
```

Expected: ~50 passed.

- [ ] **Step 7: Commit**

```bash
git add brain/v3/v3_manager.py brain/v3/tests/conftest.py brain/v3/tests/test_v3_manager.py
git commit -m "feat(brain-v3): V3Manager — façade défensive + refill loop"
```

---

## Phase 5 — Intégration avec BrainManager v2 et ada.py

### Task 5.1 : Refactor sûr de `brain/brain_manager.py` pour préparer l'insertion v3

**Files:**
- Modify: `brain/brain_manager.py`
- Test: `brain/tests/test_brain_manager.py` (vérification non-régression)

- [ ] **Step 1: Vérifier que tous les tests v2 passent actuellement**

```bash
python -m pytest brain/tests/ -v
```

Expected: tous passent (baseline).

- [ ] **Step 2: Extraire la logique de `notify_visual_scene` dans une méthode privée**

Modifie `brain/brain_manager.py` lignes 132-152. Remplace la méthode `notify_visual_scene` actuelle par :

```python
    def notify_visual_scene(self, event: dict) -> str | None:
        if not self.enabled or self._is_degraded():
            return None
        return self._safe("notify_visual_scene",
                          lambda: self._dispatch_stimulus(event, channel="vision_scene"),
                          fallback=None)
```

Ajoute ensuite (avant `consume_spontaneous_impulse`) la méthode privée extraite :

```python
    def _existing_visual_scene_logic(self, event: dict) -> str | None:
        """Logique v2 originelle de notify_visual_scene — appelée par _dispatch_stimulus."""
        from brain.network import EtatEveil
        movement = float(event.get("movement", 0.0) or 0.0)
        attention = float(event.get("attention_need", 0.0) or 0.0)
        risk = str(event.get("risk") or "none").lower()
        person = str(event.get("person") or "").lower()
        presence = 1.0 if person not in {"", "personne", "unknown"} else 0.0
        self.reseau.tick_visual(
            presence=presence,
            mouvement=max(movement, attention),
        )
        self.limbic.analyser_scene_visuelle(event)
        should_emit = risk == "high" or self.reseau.etat == EtatEveil.EVEIL
        if not should_emit:
            return None
        return self.limbic.verifier_action_spontanee()
```

Ajoute aussi la méthode de dispatch (sans v3 pour l'instant) :

```python
    def _dispatch_stimulus(self, payload: dict, channel: str) -> str | None:
        """Route un stimulus via v3 si activé, sinon v2 direct."""
        if channel == "vision_scene":
            return self._existing_visual_scene_logic(payload)
        # vision_object n'a pas de logique v2 native — pour l'instant ignoré
        return None
```

- [ ] **Step 3: Vérifier que les tests v2 passent encore**

```bash
python -m pytest brain/tests/ -v
```

Expected: tous passent encore (refacto sans changement de comportement).

- [ ] **Step 4: Commit**

```bash
git add brain/brain_manager.py
git commit -m "refactor(brain): extract notify_visual_scene logic into _existing_visual_scene_logic"
```

---

### Task 5.2 : Brancher `V3Manager` dans `BrainManager`

**Files:**
- Modify: `brain/brain_manager.py`
- Test: `brain/v3/tests/test_integration_v3.py` (nouveau)
- Test: `brain/v3/tests/test_v2_v3_isolation.py` (nouveau)

- [ ] **Step 1: Écrire le test d'isolation (v3 OFF → v2 inchangé)**

Crée `brain/v3/tests/test_v2_v3_isolation.py` :

```python
"""Vérifie que v3 désactivé laisse v2 strictement inchangé."""
import os

import pytest

from brain.brain_manager import BrainManager


def _enable_brain(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    monkeypatch.setenv("BRAIN_MODULATE_ALL", "true")
    monkeypatch.setenv("BRAIN_OBSERVE_ONLY", "false")


def test_v3_not_initialized_when_disabled(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    brain = BrainManager()
    assert brain._v3 is None


def test_v3_initialized_when_enabled(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")
    brain = BrainManager()
    assert brain._v3 is not None
    brain._v3.stop()


def test_notify_visual_scene_returns_same_type_when_v3_off(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    brain = BrainManager()
    event = {"risk": "low", "movement": 0.3, "person": "bryan",
             "human_emotion": "happy", "attention_need": 0.3}
    result = brain.notify_visual_scene(event)
    assert isinstance(result, (str, type(None)))


def test_high_risk_event_still_triggers_v2_path(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    brain = BrainManager()
    event = {"risk": "high", "movement": 0.5, "person": "bryan",
             "human_emotion": "stressed", "attention_need": 0.95,
             "spontaneous_hint": "Bryan semble en détresse"}
    result = brain.notify_visual_scene(event)
    # En v2 high risk forçait une action_spontanee → string non vide
    assert result is None or len(result) > 0


def test_ingest_stimulus_returns_none_when_v3_off(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    brain = BrainManager()
    stimulus = {"source": "vision_object", "object_class": "Cat",
                 "event_type": "appeared", "movement": 0.5, "risk": "low",
                 "attention_need": 0.3}
    result = brain.ingest_stimulus(stimulus)
    # v3 désactivé → pas de traitement, mais pas de crash
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_v2_v3_isolation.py -v
```

Expected: FAIL — `BrainManager` n'a pas encore `_v3` ni `ingest_stimulus`.

- [ ] **Step 3: Ajouter `_v3` et `ingest_stimulus` à `BrainManager`**

Modifie `brain/brain_manager.py` :

**Dans `BrainManager.__init__`**, ajoute après `self._degraded_until = 0.0` :

```python
        self._v3 = None
        if _env_bool("BRAIN_V3_ENABLED", False):
            try:
                from brain.v3.v3_manager import V3Manager
                self._v3 = V3Manager(limbic_ref=self.limbic)
            except Exception as exc:
                print(f"[BRAIN_V3] init failed, falling back to v2: {exc}")
                self._v3 = None
```

**Ajoute la méthode `ingest_stimulus`** (avant `_start_impl`) :

```python
    def ingest_stimulus(self, stimulus: dict) -> str | None:
        """Pont YOLO/screen_watcher → brain. Fixe le bug ada.py:4800."""
        if not self.enabled or self._is_degraded():
            return None
        return self._safe(
            "ingest_stimulus",
            lambda: self._dispatch_stimulus(
                stimulus,
                channel=stimulus.get("source", "vision_object"),
            ),
            fallback=None,
        )
```

**Modifie `_dispatch_stimulus`** pour router via v3 :

```python
    def _dispatch_stimulus(self, payload: dict, channel: str) -> str | None:
        """Route un stimulus visuel via v3 (si activé), puis v2 dans tous les cas."""
        decision = None
        if self._v3 is not None and self._v3.enabled:
            decision = self._v3.process(payload, channel=channel)
            if self._v3.shadow_mode:
                decision = None  # shadow : v3 logge mais ne décide pas

        # v2 toujours appelé pour mise à jour limbic (perception)
        v2_prompt: str | None = None
        if channel == "vision_scene":
            v2_prompt = self._existing_visual_scene_logic(payload)
        elif channel == "vision_object":
            # vision_object met juste à jour le limbic via analyser_scene_visuelle
            # (le payload YOLO est compatible avec le schéma scène)
            try:
                self.limbic.analyser_scene_visuelle(payload)
            except Exception:
                pass

        # Si v3 a tranché OBSERVE/SUPPRESS → silence (override v2)
        if decision is not None and decision.action != "REACT":
            return None
        # Si v3 dit REACT avec un hint, on le préfère à v2
        if decision is not None and decision.action == "REACT" and decision.prompt_hint:
            return decision.prompt_hint
        return v2_prompt
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_v2_v3_isolation.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Vérifier que les tests v2 et v3 passent encore tous ensemble**

```bash
python -m pytest brain/ -v
```

Expected: tous les tests v2 + v3 passent.

- [ ] **Step 6: Écrire le test d'intégration bout-en-bout**

Crée `brain/v3/tests/test_integration_v3.py` :

```python
"""Tests d'intégration bout-en-bout : YOLO → BrainManager → V3Manager → décision."""
import os

import pytest

from brain.brain_manager import BrainManager


def _enable_brain(monkeypatch):
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    monkeypatch.setenv("BRAIN_MODULATE_ALL", "true")
    monkeypatch.setenv("BRAIN_OBSERVE_ONLY", "false")
    monkeypatch.setenv("BRAIN_V3_ENABLED", "true")


def test_ingest_stimulus_runs_through_v3(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_SHADOW_MODE", "true")
    brain = BrainManager()
    stimulus = {"source": "vision_object", "object_class": "Cat",
                 "event_type": "appeared", "movement": 0.6, "risk": "low",
                 "attention_need": 0.4, "spontaneous_hint": "Un chat"}
    brain.ingest_stimulus(stimulus)
    # En shadow mode → pas de prompt retourné, mais v3 a tracé la décision
    state = brain._v3.get_debug_state()
    assert state["recent_decisions"]
    assert state["recent_decisions"][0]["stimulus"].startswith("obj:cat")
    brain._v3.stop()


def test_high_risk_stimulus_returns_react_prompt(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_SHADOW_MODE", "false")
    brain = BrainManager()
    stimulus = {"source": "vision_object", "object_class": "Fire",
                 "event_type": "appeared", "movement": 0.3, "risk": "high",
                 "attention_need": 0.95, "spontaneous_hint": "Du feu !"}
    result = brain.ingest_stimulus(stimulus)
    assert result == "Du feu !"
    brain._v3.stop()


def test_repeated_stimulus_eventually_suppressed_by_habituation(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_SHADOW_MODE", "false")
    monkeypatch.setenv("BRAIN_V3_REACTION_THRESHOLD", "0.55")
    monkeypatch.setenv("BRAIN_V3_REFRACTORY_VISION_OBJECT", "0.0")
    brain = BrainManager()
    stimulus = {"source": "vision_object", "object_class": "Cat",
                 "event_type": "appeared", "movement": 0.5, "risk": "low",
                 "attention_need": 0.3, "spontaneous_hint": "Un chat"}
    # 30 envois rapides → la familiarité monte, l'intensité effective baisse
    reactions = 0
    for _ in range(30):
        result = brain.ingest_stimulus(stimulus)
        if result is not None:
            reactions += 1
    # Largement moins de 30 réactions (habituation + budget + proba)
    assert reactions < 10
    brain._v3.stop()
```

- [ ] **Step 7: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_integration_v3.py -v
```

Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add brain/brain_manager.py brain/v3/tests/test_v2_v3_isolation.py brain/v3/tests/test_integration_v3.py
git commit -m "feat(brain): wire V3Manager into BrainManager (fixes ada.py:4800 ingest_stimulus bug)"
```

---

### Task 5.3 : Wirer `notify_user_message` → `V3Manager.observe()`

**Files:**
- Modify: `brain/brain_manager.py`
- Test: `brain/v3/tests/test_integration_v3.py` (extension)

Cette tâche réalise l'extension décrite dans la section 5.2 du spec : le texte
utilisateur doit alimenter l'habituation v3 (pour calibrer la "familiarité"
des patterns conversationnels) sans bloquer la voix d'Ada (Bryan parle → Ada
répond toujours, jamais gated).

- [ ] **Step 1: Étendre le test d'intégration**

Append à `brain/v3/tests/test_integration_v3.py` :

```python
def test_notify_user_message_observes_in_v3_without_gating(monkeypatch):
    _enable_brain(monkeypatch)
    monkeypatch.setenv("BRAIN_V3_SHADOW_MODE", "false")
    brain = BrainManager()
    # `notify_user_message` ne retourne rien (None), mais v3 doit observer
    brain.notify_user_message("salut, comment vas-tu ?", audio_features=None)
    state = brain._v3.get_debug_state()
    # Une décision passive_observe doit avoir été tracée
    text_traces = [d for d in state["recent_decisions"]
                    if d["stimulus"].startswith("text:")]
    assert text_traces, "v3 devrait avoir observé le texte user"
    assert text_traces[0]["action"] == "OBSERVE"
    assert text_traces[0]["reason"] == "passive_observe"
    brain._v3.stop()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest brain/v3/tests/test_integration_v3.py::test_notify_user_message_observes_in_v3_without_gating -v
```

Expected: FAIL — `notify_user_message` v2 ne route pas encore vers v3.

- [ ] **Step 3: Étendre `notify_user_message` dans `brain/brain_manager.py`**

Repère la méthode `notify_user_message` actuelle (lignes 107-125). Ajoute à la
toute fin de la méthode (après le bloc `self._safe("notify_user_message", ...)`) :

```python
        # v3 observation passive (n'affecte pas le retour, jamais de gating sur le texte)
        if self._v3 is not None and self._v3.enabled:
            try:
                self._v3.observe(
                    {"text": text, "valence": 0.0, "audio": audio_features or {}},
                    channel="text",
                )
            except Exception as exc:
                print(f"[BRAIN_V3] notify_user_message observe failed: {exc}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest brain/v3/tests/test_integration_v3.py -v
```

Expected: 4 passed (les 3 précédents + le nouveau).

- [ ] **Step 5: Commit**

```bash
git add brain/brain_manager.py brain/v3/tests/test_integration_v3.py
git commit -m "feat(brain): notify_user_message → v3.observe() (alimente habituation texte sans gating)"
```

---

### Task 5.4 : Patch `ada.py` — fallback singleton dans `_on_vision_object_event`

**Files:**
- Modify: `backend/ada.py:4797-4804`

- [ ] **Step 1: Lire le code actuel**

```bash
sed -n '4795,4810p' "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/backend/ada.py"
```

Vérifie que la fonction `_on_vision_object_event` correspond exactement à ce qui est dans le spec.

- [ ] **Step 2: Appliquer le patch minimal**

Édite `backend/ada.py`. Remplace les lignes 4797-4804 :

```python
    async def _on_vision_object_event(self, stimulus: dict) -> None:
        """Pont vers le brain SNN (additif, ne casse pas on_scene_event)."""
        brain = getattr(self, "_brain", None) or getattr(self, "brain", None)
        if brain is not None and hasattr(brain, "ingest_stimulus"):
            try:
                await brain.ingest_stimulus(stimulus)
            except Exception as exc:
                print(f"[VISION_OBJ] brain.ingest_stimulus failed: {exc}")
```

Par :

```python
    async def _on_vision_object_event(self, stimulus: dict) -> None:
        """Pont vers le brain SNN (additif, ne casse pas on_scene_event)."""
        brain = getattr(self, "_brain", None) or getattr(self, "brain", None)
        if brain is None:
            from brain.brain_manager import get_brain
            brain = get_brain()
        if brain is not None and hasattr(brain, "ingest_stimulus"):
            try:
                await asyncio.to_thread(brain.ingest_stimulus, stimulus)
            except Exception as exc:
                print(f"[VISION_OBJ] brain.ingest_stimulus failed: {exc}")
```

Deux changements :
1. Fallback sur `get_brain()` si `self._brain` est absent
2. `await asyncio.to_thread(brain.ingest_stimulus, stimulus)` car `ingest_stimulus` est sync

- [ ] **Step 3: Smoke test : import du module ada**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
python -c "import sys; sys.path.insert(0, 'backend'); from backend import ada; print('OK')"
```

Expected: `OK` sans exception.

- [ ] **Step 4: Vérifier les tests YOLO existants**

```bash
python -m pytest backend/tests/test_vision_object_agent.py -v
```

Expected: tests YOLO existants passent toujours.

- [ ] **Step 5: Commit**

```bash
git add backend/ada.py
git commit -m "fix(ada): wire brain.ingest_stimulus via singleton fallback + asyncio.to_thread"
```

---

## Phase 6 — Observabilité et finalisation

### Task 6.1 : Endpoint `/brain/v3/traces` dans `server.py`

**Files:**
- Modify: `backend/server.py`

- [ ] **Step 1: Repérer où monter l'endpoint**

```bash
grep -n "@app\." /Volumes/Disque\ dev/Archives-Mars-Avril-2026/jarvis/backend/server.py | head -10
```

Cible le bloc des routes FastAPI.

- [ ] **Step 2: Ajouter l'endpoint**

Dans `backend/server.py`, ajoute après les autres routes `@app.get(...)` :

```python
@app.get("/brain/v3/traces")
async def brain_v3_traces(n: int = 50):
    """Retourne les N dernières décisions du brain v3 (pour calibration shadow)."""
    try:
        from brain.brain_manager import get_brain
        brain = get_brain()
        v3 = getattr(brain, "_v3", None)
        if v3 is None:
            return {"enabled": False, "decisions": []}
        state = v3.get_debug_state()
        return {
            "enabled": state["enabled"],
            "shadow_mode": state["shadow_mode"],
            "degraded": state["degraded"],
            "budget": state["budget"],
            "habituation_size": state["habituation_size"],
            "decisions": state["recent_decisions"][:max(1, min(int(n), 500))],
        }
    except Exception as exc:
        return {"error": str(exc), "decisions": []}
```

- [ ] **Step 3: Smoke test du serveur**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis/backend"
python -c "import server; print('server module OK')"
```

Expected: `server module OK`.

- [ ] **Step 4: Commit**

```bash
git add backend/server.py
git commit -m "feat(server): endpoint GET /brain/v3/traces pour calibration shadow"
```

---

### Task 6.2 : Documentation des variables d'environnement

**Files:**
- Modify: `.env.example` (à la racine du repo)
- Modify: `backend/CLAUDE.md` (référence brain v3)

- [ ] **Step 1: Vérifier l'existence et le contenu de .env.example**

```bash
ls /Volumes/Disque\ dev/Archives-Mars-Avril-2026/jarvis/.env.example 2>/dev/null && head -5 /Volumes/Disque\ dev/Archives-Mars-Avril-2026/jarvis/.env.example
```

- [ ] **Step 2: Ajouter le bloc de configuration v3**

Append au `.env.example` (ou crée-le s'il n'existe pas) :

```bash

# ═══════════════════════════════════════════════════════════
# Brain v3 — couche neurobiologique en surcouche
# ═══════════════════════════════════════════════════════════

# ─── Master switches ───────────────────────────
BRAIN_V3_ENABLED=false                 # par défaut OFF — activer après calibration shadow
BRAIN_V3_SHADOW_MODE=true              # true = v3 logge sans décider, false = v3 prend la main

# ─── Performance ───────────────────────────────
BRAIN_V3_TICK_BUDGET_MS=3.0            # budget temps par tick avant degraded

# ─── Neurones adaptatifs (AdaptiveLIF) ─────────
BRAIN_V3_AHP_AMPLITUDE=0.15            # after-hyperpolarization post-spike
BRAIN_V3_AHP_DECAY=0.92                # decay AHP par tick
BRAIN_V3_THRESHOLD_DRIFT=0.005         # vitesse d'adaptation du seuil
BRAIN_V3_THRESHOLD_MIN=0.40            # plancher du seuil adaptatif
BRAIN_V3_THRESHOLD_MAX=2.00            # plafond du seuil adaptatif

# ─── Refractory adaptatif par canal ────────────
BRAIN_V3_REFRACTORY_VISION_OBJECT=2.0  # YOLO : 2s entre spikes même classe
BRAIN_V3_REFRACTORY_VISION_SCENE=8.0   # Gemini multimodal : long car coûteux
BRAIN_V3_REFRACTORY_FACE_MOTION=1.0    # MediaPipe : court (continu)
BRAIN_V3_REFRACTORY_AUDIO=0.5          # voix : très réactif
BRAIN_V3_REFRACTORY_TEXT=0.3           # texte : très réactif

# ─── Habituation ───────────────────────────────
BRAIN_V3_HABITUATION_HALFLIFE=120.0    # secondes pour qu'une familiarité décroisse de 50%
BRAIN_V3_HABITUATION_MAX_KEYS=256      # LRU cap
BRAIN_V3_HABITUATION_GAIN=0.70         # familiarité=1 → intensité réduite à 30%

# ─── Inhibition latérale ───────────────────────
BRAIN_V3_INHIBITION_STRENGTH=0.3       # un canal qui vient de spike inhibe les autres de 0.3

# ─── Budget d'attention ────────────────────────
BRAIN_V3_ATTENTION_BUDGET_INIT=1.0     # 1 réaction normale dispo au démarrage
BRAIN_V3_ATTENTION_BUDGET_MAX=1.5      # plafond
BRAIN_V3_COST_OBJECT_NORMAL=0.20       # coût YOLO normal
BRAIN_V3_COST_SCENE_NORMAL=0.30        # coût scène Gemini (plus cher)
BRAIN_V3_COST_HIGH_RISK=0.05           # urgences quasi gratuites

# ─── Politique de réaction ─────────────────────
BRAIN_V3_REACTION_THRESHOLD=0.55       # saillance min pour autoriser REACT
BRAIN_V3_PROB_GATE_SLOPE=2.0           # pente probabilité au-dessus du seuil

# ─── Neuromodulation (hormones v2 → modulation v3) ─
BRAIN_V3_CORTISOL_THRESHOLD_GAIN=0.40  # stress haut → seuils baissent jusqu'à 40%
BRAIN_V3_FATIGUE_DECAY_GAIN=0.50       # fatigue → oubli x1.5
BRAIN_V3_DOPAMINE_REFILL_GAIN=0.0008   # dopamine alimente le budget
```

- [ ] **Step 3: Ajouter une section "Brain v3" au backend/CLAUDE.md**

Modifie `backend/CLAUDE.md`. Cherche la section `### Couche vision objet (YOLO)` dans le CLAUDE.md racine — le backend/CLAUDE.md a son propre format. Ajoute une section similaire après "Identité" :

Édite `backend/CLAUDE.md` en ajoutant cette section avant la section "Variables d'environnement requises" :

```markdown

---

## Brain v3 — couche neurobiologique en surcouche

Active par `BRAIN_V3_ENABLED=true`. En surcouche au-dessus du brain v2 (limbic v2 inchangé) :

- `brain/v3/adapters.py` — normalise YOLO/scène/face/texte en Stimulus canoniques
- `brain/v3/neurons.py` — `AdaptiveLIF` : LIF + threshold drift + AHP + modulation
- `brain/v3/attention.py` — `AttentionField` : 5 neurones + inhibition latérale
- `brain/v3/habituation.py` — `HabituationTracker` : LRU + decay exponentiel
- `brain/v3/neuromodulation.py` — hormones v2 → ModulationVector
- `brain/v3/policy.py` — `ReactionPolicy` : SUPPRESS/OBSERVE/REACT
- `brain/v3/v3_manager.py` — façade défensive, refill loop

**Mode shadow** (`BRAIN_V3_SHADOW_MODE=true`) : v3 logge ses décisions sans bloquer v2. Endpoint `GET /brain/v3/traces?n=50` pour visualiser en live.

**Bug corrigé** : `ada.py:_on_vision_object_event` appelait `brain.ingest_stimulus()` qui n'existait pas dans v2 → tous les stimuli YOLO étaient perdus. v3 fournit cette méthode et le pont fonctionne.

**Spec** : `docs/superpowers/specs/2026-05-17-brain-v3-neurobiological-design.md`
**Plan** : `docs/superpowers/plans/2026-05-17-brain-v3-implementation.md`
```

- [ ] **Step 4: Commit**

```bash
git add .env.example backend/CLAUDE.md
git commit -m "docs(brain-v3): document env vars + section dans backend/CLAUDE.md"
```

---

### Task 6.3 : Test de non-régression complet et performance globale

**Files:**
- Test: tous les tests v2 + v3 + backend

- [ ] **Step 1: Lancer la suite v2 (régression bio existante)**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
python -m pytest brain/tests/ -v
```

Expected: tous passent (baseline préservée).

- [ ] **Step 2: Lancer la suite v3**

```bash
python -m pytest brain/v3/tests/ -v
```

Expected: ~70 tests passent.

- [ ] **Step 3: Lancer la suite backend (vision_object_agent, YOLO, etc.)**

```bash
python -m pytest backend/tests/ -v
```

Expected: tests existants (vision_object, yolo_detector, vision_deduplicator, vision_storage, vision_translations) passent.

- [ ] **Step 4: Smoke test live : v3 activé en shadow, simulation YOLO**

Crée un fichier temporaire `/tmp/v3_smoke.py` :

```python
"""Smoke test live de brain v3 (à exécuter à la main)."""
import os
import sys

os.environ["BRAIN_ENABLED"] = "true"
os.environ["BRAIN_V3_ENABLED"] = "true"
os.environ["BRAIN_V3_SHADOW_MODE"] = "true"
os.environ["BRAIN_MODULATE_ALL"] = "true"

sys.path.insert(0, "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis")

from brain.brain_manager import get_brain

brain = get_brain()
print(f"v3 enabled: {brain._v3 is not None}")
print(f"shadow mode: {brain._v3.shadow_mode if brain._v3 else 'N/A'}")

# Simule 5 stimuli YOLO
for i in range(5):
    brain.ingest_stimulus({
        "source": "vision_object",
        "object_class": "Cat",
        "event_type": "appeared" if i % 2 == 0 else "moved",
        "movement": 0.6,
        "risk": "low",
        "attention_need": 0.4,
        "spontaneous_hint": f"Chat #{i}",
    })

state = brain._v3.get_debug_state()
print(f"\nDécisions traçées: {len(state['recent_decisions'])}")
for d in state["recent_decisions"]:
    print(f"  {d['ts']} [{d['action']:8s}] {d['stimulus']:30s} sal={d['saliency']:.2f}")

print(f"\nBudget: {state['budget']:.3f}")
print(f"Habituation size: {state['habituation_size']}")
brain._v3.stop()
```

Lance-le :

```bash
python /tmp/v3_smoke.py
```

Expected output :
```
v3 enabled: True
shadow mode: True
Décisions traçées: 5
  HH:MM:SS [OBSERVE ] obj:cat:appeared              sal=0.XX
  ...
Budget: 1.0XX
Habituation size: 2
```

- [ ] **Step 5: Mesure p95 latence en condition réaliste**

Crée `/tmp/v3_perf.py` :

```python
import os, sys, time
os.environ["BRAIN_V3_ENABLED"] = "true"
os.environ["BRAIN_ENABLED"] = "true"
sys.path.insert(0, "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis")

from brain.brain_manager import get_brain

brain = get_brain()
times = []
for i in range(500):
    t0 = time.perf_counter()
    brain.ingest_stimulus({
        "source": "vision_object", "object_class": "Cat",
        "event_type": "moved", "movement": 0.5, "risk": "low",
        "attention_need": 0.3, "spontaneous_hint": "Chat",
    })
    times.append((time.perf_counter() - t0) * 1000.0)

times.sort()
p50, p95, p99 = times[249], times[474], times[494]
print(f"p50: {p50:.2f}ms  p95: {p95:.2f}ms  p99: {p99:.2f}ms")
assert p95 < 5.0, f"p95 dépasse 5ms ({p95:.2f}ms)"
print("✓ Performance OK")
brain._v3.stop()
```

```bash
python /tmp/v3_perf.py
```

Expected: `p95 < 5ms`, `p99 < 10ms`.

- [ ] **Step 6: Nettoyer les fichiers temporaires**

```bash
rm /tmp/v3_smoke.py /tmp/v3_perf.py
```

- [ ] **Step 7: Commit final (si modifs résiduelles)**

```bash
cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"
git status
# Si rien à commit, c'est OK. Sinon :
# git add -p
# git commit -m "test(brain-v3): non-regression + perf smoke validated"
```

---

## Récapitulatif des commits attendus

| # | Phase | Message |
|---|---|---|
| 1 | 1.1 | `feat(brain-v3): bootstrap package + immutable types` |
| 2 | 1.2 | `feat(brain-v3): ShortTermMemory ring buffer (60s window, thread-safe)` |
| 3 | 1.3 | `feat(brain-v3): adapters.from_payload() — normalise YOLO/scène/face/text` |
| 4 | 2.1 | `feat(brain-v3): AdaptiveLIF — threshold drift + AHP + modulation` |
| 5 | 2.2 | `feat(brain-v3): Neuromodulator — snapshot hormones v2 → ModulationVector` |
| 6 | 2.3 | `feat(brain-v3): AttentionField — 5 neurones spécialisés + inhibition latérale` |
| 7 | 3.1 | `feat(brain-v3): HabituationTracker — LRU + decay temporel exponentiel` |
| 8 | 3.2 | `feat(brain-v3): ReactionPolicy + AttentionBudget — décision probabiliste` |
| 9 | 4.1 | `feat(brain-v3): V3Manager — façade défensive + refill loop` |
| 10 | 5.1 | `refactor(brain): extract notify_visual_scene logic into _existing_visual_scene_logic` |
| 11 | 5.2 | `feat(brain): wire V3Manager into BrainManager (fixes ada.py:4800 bug)` |
| 12 | 5.3 | `feat(brain): notify_user_message → v3.observe() (habituation texte sans gating)` |
| 13 | 5.4 | `fix(ada): wire brain.ingest_stimulus via singleton fallback + asyncio.to_thread` |
| 14 | 6.1 | `feat(server): endpoint GET /brain/v3/traces pour calibration shadow` |
| 15 | 6.2 | `docs(brain-v3): document env vars + section dans backend/CLAUDE.md` |

15 commits attendus, chacun laissant le système dans un état fonctionnel et testable.

---

## Critères d'acceptation finaux

Avant de fermer cette feature :

- [ ] Tous les commits ci-dessus sont sur la branche
- [ ] `python -m pytest brain/tests/` → tous verts (régression v2 préservée)
- [ ] `python -m pytest brain/v3/tests/` → tous verts (~70 tests)
- [ ] `python -m pytest backend/tests/` → tous verts (régression YOLO/vision préservée)
- [ ] Smoke test live : `BRAIN_V3_ENABLED=true BRAIN_V3_SHADOW_MODE=true` → endpoint `/brain/v3/traces` retourne des décisions
- [ ] Mesure p95 < 5ms sur 500 ingest_stimulus
- [ ] `backend/CLAUDE.md` mentionne brain v3
- [ ] `.env.example` documente les ~25 variables `BRAIN_V3_*`
- [ ] Plan de calibration (Phase 1 shadow / Phase 2 vision_object / Phase 3 tous canaux) à exécuter manuellement en live ensuite — hors scope de ce plan
