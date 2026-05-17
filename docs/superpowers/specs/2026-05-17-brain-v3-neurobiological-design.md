# Brain v3 — couche neurobiologique en surcouche

> Spec créée le 2026-05-17 — propriétaire : Bryan Hilaire / Kairo Digital.
> Status : design validé, prêt pour writing-plans.

---

## 1. Objectif et contexte

### 1.1 Problème

Le brain v2 actuel (`brain/`) fournit :
- 5 neurones LIF simples (vision, mouvement, audition, textuel, thalamus)
- Un limbic à 6 hormones avec décay et momentum de valence
- Un mood mapping → temperature Gemini + bloc texte injecté

Limitations identifiées en lecture de code (1415 LOC v2) :
- **Pas d'adaptation neuronale** — seuils LIF fixes
- **Pas de plasticité locale** — aucun apprentissage en ligne
- **Mémoire temporelle limitée** — buffer de 6 valences lexicales uniquement
- **Pas d'inhibition latérale** — les canaux LIF n'interagissent pas
- **Neuromodulation implicite** — les hormones existent mais ne modulent pas les seuils SNN
- **Pas de saillance / habituation** — un stimulus répété produit toujours le même spike
- **Bug pont YOLO** — `ada.py:4800` appelle `brain.ingest_stimulus()` qui n'existe pas → tous les stimuli YOLO sont perdus silencieusement
- **Pas de séparation perception / attention / décision** — limbic mélange ces rôles

Le comportement final attendu d'Ada : percevoir beaucoup, réagir peu, ne pas commenter chaque frame, rester silencieuse par défaut, ne réagir que sur saillance réelle.

### 1.2 Décision retenue

Construire un package `brain/v3/` **en surcouche** entre les capteurs et le brain v2 actuel. Le v3 fait perception+attention+décision ; le v2 garde son rôle de limbic+mood. Activé par feature flag `BRAIN_V3_ENABLED`.

**Choix de cohabitation** : surcouche fine (v3 entre capteurs et v2, fallback vers v2 si v3 KO).
**Modèle de saillance** : habituation par classe + budget d'attention épuisable (pas de modèle prédictif).

---

## 2. Architecture

### 2.1 Structure du package

```
brain/
├── (v2 existant — INCHANGÉ)
│   neurons.py, network.py, limbic.py, mood.py,
│   modulators.py, mood_block.py, sensors_adapter.py,
│   brain_manager.py, lexicons.py, calibration.py
│
└── v3/
    ├── __init__.py
    ├── types.py            # Stimulus, ReactionDecision, ModulationVector (frozen dataclasses)
    ├── adapters.py         # normalise les payloads → Stimulus avec canonical_id
    ├── neurons.py          # AdaptiveLIF (threshold drift + AHP + modulation)
    ├── attention.py        # AttentionField (inhibition latérale, winner-take-all soft)
    ├── habituation.py      # HabituationTracker (LRU par canonical_id, decay temporel)
    ├── neuromodulation.py  # snapshot limbic.hormones → ModulationVector
    ├── traces.py           # ShortTermMemory (ring buffer 60s, pour debug + endpoint)
    ├── policy.py           # ReactionPolicy (SUPPRESS|OBSERVE|REACT)
    ├── v3_manager.py       # façade défensive (singleton, équivalent v3 de brain_manager)
    └── tests/
        ├── __init__.py, conftest.py
        ├── test_adapters.py
        ├── test_neurons_adaptive.py
        ├── test_attention_field.py
        ├── test_habituation.py
        ├── test_neuromodulation.py
        ├── test_policy.py
        ├── test_traces.py
        ├── test_v3_manager.py
        ├── test_integration_v3.py
        ├── test_v2_v3_isolation.py
        └── test_no_regression_v3.py
```

### 2.2 Flux d'intégration

```
┌─────────────────────────────────────────────────────────────┐
│  ada.py / external_bridge.py / vision_object_agent.py       │
└──────────────┬──────────────┬──────────────┬────────────────┘
               │              │              │
   notify_user_message    notify_visual    ingest_stimulus
   (text, audio_feat)     _scene(event)    (yolo_payload)
               │              │              │
               ▼              ▼              ▼
        ┌─────────────────────────────────────┐
        │      BrainManager (dispatcher v2)   │
        │   - lit BRAIN_V3_ENABLED            │
        │   - si v3 OFF: chemin v2 classique  │
        │   - si v3 ON: passe par V3Manager   │
        └──────────────┬──────────────────────┘
                       │ if v3.enabled:
                       ▼
        ┌─────────────────────────────────────┐
        │           V3Manager                 │
        │  1. adapters.from_payload(...)      │
        │  2. neuromodulation.derive(limbic)  │
        │  3. attention.tick(stim, modulation)│
        │  4. policy.decide(...)              │
        │  5. traces.append(decision)         │
        │  6. budget.consume() si REACT       │
        │  7. habituation.imprint(canonical)  │
        └──────────────┬──────────────────────┘
                       │ ReactionDecision
                       ▼
        ┌─────────────────────────────────────┐
        │       v2 chemin existant            │
        │   - limbic.analyser_scene_visuelle  │
        │     (TOUJOURS exécuté pour percep.) │
        │   - action_spontanee GATED par      │
        │     decision.action == REACT        │
        └─────────────────────────────────────┘
```

**Invariant** : limbic v2 est **toujours mis à jour** (perception). v3 ne gate que la **décision de parler**.

### 2.3 API publique inchangée

`BrainManager` conserve strictement les mêmes signatures :
- `notify_user_message(text, audio_features=None)`
- `notify_visual_scene(event)`
- `notify_llm_response()`
- `get_mood_block()` / `get_runtime_mood_update()` / `get_gemini_params()`
- `consume_spontaneous_impulse()`
- `get_debug_state()`

**Nouvelle méthode ajoutée pour fixer le bug YOLO** :
- `ingest_stimulus(stimulus: dict) -> str | None`

ada.py et external_bridge.py ne sont pas touchés (sauf 2 lignes dans `_on_vision_object_event` pour le fallback singleton).

---

## 3. Modèle neuronal v3

### 3.1 AdaptiveLIF

Extension de `NeuroneLIF` v2 avec trois mécanismes biologiques supplémentaires.

```python
@dataclass
class AdaptiveLIF:
    nom: str
    seuil_base: float = 1.0
    fuite: float = 0.18
    periode_refractaire: float = 0.3
    # v3 additions
    ahp_amplitude: float = 0.15        # after-hyperpolarization post-spike
    ahp_decay: float = 0.92            # AHP decay par tick
    threshold_drift_rate: float = 0.005
    threshold_min: float = 0.4
    threshold_max: float = 2.0
```

**Boucle d'excitation** :

1. Si refractory → return False
2. Décroissance fuite + relâche AHP : `potentiel -= ahp_courant`
3. AHP decay : `ahp_courant *= ahp_decay`
4. Intégration avec modulation externe : `seuil_eff = seuil_courant * modulation`
5. Si `potentiel >= seuil_eff` : spike, reset, AHP active à `ahp_amplitude`, threshold drift +10×rate
6. Sinon : threshold drift vers seuil_base (taux `threshold_drift_rate`)

**Bénéfices bio** : un neurone qui spike souvent devient progressivement moins excitable (homéostasie). Un neurone non sollicité revient lentement à son excitabilité de base.

### 3.2 AttentionField

Remplace conceptuellement le `n_thalamus` unique de v2 par un champ de neurones spécialisés par canal :

```python
class AttentionField:
    """Champ thalamique v3 avec inhibition latérale."""
    
    def __init__(self):
        self._neurons = {
            "vision_object": AdaptiveLIF("vision_object",
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_VISION_OBJECT", 2.0)),
            "vision_scene": AdaptiveLIF("vision_scene",
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_VISION_SCENE", 8.0)),
            "face_motion": AdaptiveLIF("face_motion",
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_FACE_MOTION", 1.0)),
            "audio_user": AdaptiveLIF("audio_user",
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_AUDIO", 0.5)),
            "text": AdaptiveLIF("text",
                periode_refractaire=env_float("BRAIN_V3_REFRACTORY_TEXT", 0.3)),
        }
        self._inhibition_w = self._build_inhibition_matrix()
    
    def tick(self, stimulus: Stimulus, modulation: ModulationVector,
             habituation: HabituationTracker) -> bool:
        """Retourne True si le stimulus a produit un spike sur son canal."""
        neuron = self._neurons.get(stimulus.channel)
        if neuron is None:
            return False
        familiarity = habituation.familiarity(stimulus.canonical_id)
        effective = stimulus.intensity * (1.0 - familiarity * 0.7)
        return neuron.exciter(effective, modulation=modulation.threshold_gain)
```

L'inhibition latérale est implémentée comme un coupling négatif entre canaux : un spike sur un canal soustrait une fraction de son potentiel aux voisins, évitant les doublons.

### 3.3 Neuromodulator

Pont entre hormones v2 et seuils v3 :

```python
@dataclass(frozen=True)
class ModulationVector:
    threshold_gain: float   # 1.0 = neutre, <1.0 = plus excitable
    decay_gain: float       # 1.0 = oubli normal, >1.0 = oubli rapide
    budget_refill: float    # contribution au budget par tick

def derive(snapshot: dict) -> ModulationVector:
    cortisol = snapshot.get("cortisol", 0.10)
    dopamine = snapshot.get("dopamine", 0.28)
    mental_load = snapshot.get("mental_load", 0.15)
    
    threshold_gain = 1.0 - 0.4 * (cortisol - 0.30)
    threshold_gain = max(0.6, min(1.4, threshold_gain))
    
    decay_gain = 1.0 + 0.5 * max(0, mental_load - 0.60)
    budget_refill = 0.0008 * dopamine - 0.0003 * mental_load
    
    return ModulationVector(threshold_gain, decay_gain, budget_refill)
```

C'est ici que **les hormones de v2 modulent réellement les neurones de v3**.

---

## 4. Politique de réaction

### 4.1 Stimulus canonique

Tous les flux sont normalisés vers une dataclass immuable :

```python
@dataclass(frozen=True)
class Stimulus:
    canonical_id: str        # ex: "obj:cat:appeared", "scene:bryan:sad"
    channel: str             # "vision_object"|"vision_scene"|"face_motion"|"audio"|"text"
    intensity: float         # [0..1]
    valence: float           # [-1..1]
    risk: str                # "none"|"low"|"medium"|"high"
    attention_need: float    # [0..1]
    ts: float                # time.monotonic()
    raw: dict                # payload original (passé à limbic v2)
```

### 4.2 HabituationTracker

LRU par `canonical_id` avec decay temporel (demi-vie configurable).

```python
def familiarity(self, canonical_id: str) -> float:
    """Retourne ∈ [0..1]. 0 = jamais vu, 1 = très familier."""
    if canonical_id not in self._counts:
        return 0.0
    elapsed = now - self._last_ts[canonical_id]
    decayed = self._counts[canonical_id] * (0.5 ** (elapsed / self._halflife))
    return min(1.0, decayed / 10.0)
```

10 occurrences récentes → familiarité ≈ 1. Après 2 demi-vies sans répétition, retombe à 25%.

### 4.3 AttentionBudget

Budget [0..1.5] qui se consomme à chaque réaction et se reconstitue lentement par dopamine.

```python
class AttentionBudget:
    def can_afford(self, cost: float) -> bool
    def consume(self, cost: float) -> None
    def refill(self, delta: float) -> None
```

Coûts par canal :
- `vision_object` normal : 0.20
- `vision_scene` normal : 0.30 (Gemini multimodal plus coûteux)
- `risk=high` : 0.05 (urgences peu taxées)

Refill : `0.0008 × dopamine` par tick (~3 min pour récupérer une réaction normale à dopamine baseline).

### 4.4 ReactionPolicy

```python
class ReactionPolicy:
    def decide(self, stimulus, spike, familiarity, modulation, budget, threshold):
        # 1. risk=high court-circuite tout
        if stimulus.risk == "high":
            return ReactionDecision("REACT", 1.0, "risk=high", 0.05, hint)
        
        # 2. saillance combinée
        novelty = 1.0 - familiarity
        saliency = (0.45 * stimulus.intensity
                   + 0.35 * novelty
                   + 0.15 * stimulus.attention_need
                   + 0.05 * abs(stimulus.valence))
        
        # 3. pas de spike ou sub-threshold → silence
        if not spike or saliency < threshold:
            return ReactionDecision("OBSERVE", saliency, "sub_threshold", 0.0, None)
        
        # 4. budget insuffisant → silence
        cost = self._cost_for(stimulus)
        if not budget.can_afford(cost):
            return ReactionDecision("OBSERVE", saliency, "no_budget", 0.0, None)
        
        # 5. gate probabiliste (non-mécanique)
        p = min(0.95, 0.5 + (saliency - threshold) * 2.0)
        if random.random() > p:
            return ReactionDecision("OBSERVE", saliency, "prob_gate_miss", 0.0, None)
        
        return ReactionDecision("REACT", saliency, "react", cost, hint)
```

**Trois actions** :
- `SUPPRESS` : flood / flux à couper avant limbic (réservé aux abus)
- `OBSERVE` : limbic v2 mis à jour, **pas de spontanéité**
- `REACT` : limbic v2 mis à jour ET spontanéité autorisée

---

## 5. V3Manager et wiring

### 5.1 V3Manager

Façade défensive, même pattern que `BrainManager` v2 (`_safe()`, `_is_degraded()`, fallback) :

```python
class V3Manager:
    def __init__(self, limbic_ref): ...
    
    @property
    def enabled(self) -> bool:
        return env_bool("BRAIN_V3_ENABLED", False) and not self._is_degraded()
    
    @property
    def shadow_mode(self) -> bool:
        return env_bool("BRAIN_V3_SHADOW_MODE", True)
    
    def process(self, payload: dict, channel: str) -> ReactionDecision | None:
        """Route principale : produit une ReactionDecision pour les flux visuels."""
        start = time.perf_counter()
        try:
            stimulus = adapters.from_payload(payload, channel)
            modulation = neuromodulation.derive(self._limbic.get_snapshot())
            spike = self._attention.tick(stimulus, modulation, self._habituation)
            familiarity = self._habituation.familiarity(stimulus.canonical_id)
            decision = self._policy.decide(stimulus, spike, familiarity,
                                            modulation, self._budget,
                                            threshold=self._policy.threshold)
            self._traces.append(stimulus, decision)
            self._habituation.imprint(stimulus.canonical_id)
            if decision.action == "REACT":
                self._budget.consume(decision.cost)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if elapsed_ms > self._tick_budget_ms:
                self._degraded_until = time.monotonic() + 5.0
            return decision
        except Exception as exc:
            self._degraded_until = time.monotonic() + 30.0
            print(f"[BRAIN_V3] process failed, degraded 30s: {exc}")
            return None
    
    def observe(self, payload: dict, channel: str) -> None:
        """Observation passive (texte, audio) : alimente AttentionField + habituation
        SANS produire de ReactionDecision. Le texte user passe toujours sur v2 ;
        v3 l'observe juste pour calibrer son budget et son habituation."""
        try:
            stimulus = adapters.from_payload(payload, channel)
            modulation = neuromodulation.derive(self._limbic.get_snapshot())
            self._attention.tick(stimulus, modulation, self._habituation)
            self._habituation.imprint(stimulus.canonical_id)
            self._traces.append(stimulus, ReactionDecision(
                "OBSERVE", 0.0, "passive_observe", 0.0, None))
        except Exception as exc:
            print(f"[BRAIN_V3] observe failed: {exc}")
    
    def get_debug_state(self) -> dict: ...
```

Thread daemon dédié au refill du budget toutes les 5s, lit `limbic.get_snapshot()` et alimente le budget proportionnellement à dopamine.

### 5.2 Patch chirurgical de brain_manager.py

3 modifications, ~40 LOC ajoutées :

```python
class BrainManager:
    def __init__(self) -> None:
        # ... code existant ...
        self._v3: V3Manager | None = None
        if _env_bool("BRAIN_V3_ENABLED", False):
            try:
                from brain.v3.v3_manager import V3Manager
                self._v3 = V3Manager(limbic_ref=self.limbic)
            except Exception as exc:
                print(f"[BRAIN_V3] init failed, falling back to v2: {exc}")
                self._v3 = None
    
    def ingest_stimulus(self, stimulus: dict) -> str | None:
        """Pont YOLO/screen_watcher → brain. Fixe le bug ada.py:4800."""
        if not self.enabled or self._is_degraded():
            return None
        return self._safe("ingest_stimulus",
                          lambda: self._dispatch_stimulus(
                              stimulus,
                              channel=stimulus.get("source", "vision_object")),
                          fallback=None)
    
    def notify_visual_scene(self, event: dict) -> str | None:
        if not self.enabled or self._is_degraded():
            return None
        return self._safe("notify_visual_scene",
                          lambda: self._dispatch_stimulus(event, channel="vision_scene"),
                          fallback=None)
    
    def notify_user_message(self, text: str, audio_features: dict | None = None) -> None:
        """Étendu en v3 : si v3 actif, route le texte aussi pour observabilité.
        Pas de gating sur le texte (le texte user n'est jamais "spam" : Ada doit
        toujours répondre quand Bryan parle). v3 met juste à jour son AttentionField
        et son AttentionBudget."""
        if not self.enabled or self._is_degraded():
            return
        # Comportement v2 inchangé (limbic.analyser_texte etc.)
        self._existing_notify_user_message(text, audio_features)
        # v3 en plus : observation pour habituation et budget (pas de gating)
        if self._v3 is not None:
            self._safe("v3_observe_text",
                       lambda: self._v3.observe(
                           {"text": text, "audio": audio_features or {}},
                           channel="text"),
                       fallback=None)
    
    def _dispatch_stimulus(self, payload: dict, channel: str) -> str | None:
        """Route un stimulus visuel via v3 (si activé), puis v2 dans tous les cas."""
        decision = None
        if self._v3 is not None:
            decision = self._v3.process(payload, channel=channel)
            if self._v3.shadow_mode:
                decision = None  # shadow : ignore la décision v3
        # v2 toujours appelé pour mise à jour des hormones (perception)
        v2_prompt = self._existing_v2_logic(payload, channel)
        if decision is not None and decision.action != "REACT":
            return None  # v3 a tranché : silence
        if decision is not None and decision.action == "REACT" and decision.prompt_hint:
            return decision.prompt_hint
        return v2_prompt
```

**Note implémentation** : `_existing_v2_logic` et `_existing_notify_user_message` sont des refactorisations privées
extraites du code actuel de `notify_visual_scene` et `notify_user_message` v2 (lignes 107-152 de `brain_manager.py`).
Pas de nouvelle logique métier : juste un déplacement local pour permettre l'insertion v3 au-dessus.

### 5.3 Patch ada.py (2 lignes)

```python
# ada.py:4797 — modification minimale
async def _on_vision_object_event(self, stimulus: dict) -> None:
    brain = getattr(self, "_brain", None) or getattr(self, "brain", None)
    if brain is None:
        from brain.brain_manager import get_brain  # +1 ligne
        brain = get_brain()                         # +1 ligne
    if brain is not None and hasattr(brain, "ingest_stimulus"):
        try:
            await asyncio.to_thread(brain.ingest_stimulus, stimulus)
        except Exception as exc:
            print(f"[VISION_OBJ] brain.ingest_stimulus failed: {exc}")
```

### 5.4 Endpoint d'observabilité

`server.py` expose `GET /brain/v3/traces?n=50` qui retourne les N dernières décisions au format JSON, utile pour calibration empirique :

```json
[
  {"ts": "20:54:01", "stimulus": "obj:cat:appeared", "saliency": 0.62, "action": "REACT", "reason": "react", "budget": 0.80},
  {"ts": "20:54:03", "stimulus": "obj:cat:moved", "saliency": 0.31, "action": "OBSERVE", "reason": "sub_threshold", "budget": 0.80}
]
```

---

## 6. Variables d'environnement (calibration initiale)

```bash
# ─── Master switches ───────────────────────────
BRAIN_V3_ENABLED=false                 # par défaut OFF
BRAIN_V3_SHADOW_MODE=true              # log only au départ

# ─── Performance ───────────────────────────────
BRAIN_V3_TICK_BUDGET_MS=3.0            # 5ms total v2+v3 ; v3 ≤ 3ms

# ─── Neurones adaptatifs ───────────────────────
BRAIN_V3_AHP_AMPLITUDE=0.15
BRAIN_V3_AHP_DECAY=0.92
BRAIN_V3_THRESHOLD_DRIFT=0.005
BRAIN_V3_THRESHOLD_MIN=0.40
BRAIN_V3_THRESHOLD_MAX=2.00

# ─── Refractory par canal ──────────────────────
BRAIN_V3_REFRACTORY_VISION_OBJECT=2.0
BRAIN_V3_REFRACTORY_VISION_SCENE=8.0
BRAIN_V3_REFRACTORY_FACE_MOTION=1.0
BRAIN_V3_REFRACTORY_AUDIO=0.5
BRAIN_V3_REFRACTORY_TEXT=0.3

# ─── Habituation ───────────────────────────────
BRAIN_V3_HABITUATION_HALFLIFE=120.0
BRAIN_V3_HABITUATION_MAX_KEYS=256
BRAIN_V3_HABITUATION_GAIN=0.70

# ─── Budget d'attention ────────────────────────
BRAIN_V3_ATTENTION_BUDGET_INIT=1.0
BRAIN_V3_ATTENTION_BUDGET_MAX=1.5
BRAIN_V3_COST_OBJECT_NORMAL=0.20
BRAIN_V3_COST_SCENE_NORMAL=0.30
BRAIN_V3_COST_HIGH_RISK=0.05

# ─── Politique de réaction ─────────────────────
BRAIN_V3_REACTION_THRESHOLD=0.55
BRAIN_V3_PROB_GATE_SLOPE=2.0

# ─── Neuromodulation ───────────────────────────
BRAIN_V3_CORTISOL_THRESHOLD_GAIN=0.40
BRAIN_V3_FATIGUE_DECAY_GAIN=0.50
BRAIN_V3_DOPAMINE_REFILL_GAIN=0.0008
```

**Justifications biologiques** :
- `HABITUATION_HALFLIFE=120s` : ordre de grandeur de l'habituation neuronale courte (cortex humain)
- `THRESHOLD_DRIFT=0.005` : ~50 ticks pour qu'un seuil revienne au repos après un spike (~5-10s)
- `REACTION_THRESHOLD=0.55` : empiriquement, ~30% des stimuli passeront le seuil au départ
- `PROB_GATE_SLOPE=2.0` : à saillance=0.55 → P=50%, à saillance=0.80 → P=100% (courbe douce, non-mécanique)

---

## 7. Tests

### 7.1 Couverture cible

| Fichier de test | Cible |
|---|---|
| `test_adapters.py` | canonical_id stable et déterministe par channel |
| `test_neurons_adaptive.py` | threshold drift, AHP, modulation, refractory |
| `test_attention_field.py` | inhibition latérale, winner-take-all, multi-canal |
| `test_habituation.py` | familiarity decay 0.5 par halflife, LRU eviction |
| `test_neuromodulation.py` | snapshot → ModulationVector cohérent (cortisol haut → seuils bas) |
| `test_policy.py` | SUPPRESS/OBSERVE/REACT selon contexte, risk=high bypass |
| `test_traces.py` | ring buffer 60s, append/recent thread-safe |
| `test_v3_manager.py` | enabled/shadow/degraded, process p95 < 3ms |
| `test_integration_v3.py` | bout-en-bout YOLO → v3 → décision |
| `test_v2_v3_isolation.py` | **v3 OFF → comportement v2 strictement identique** |
| `test_no_regression_v3.py` | ré-exécute brain/tests/test_no_regression.py |

### 7.2 Tests critiques

**Invariance v2 quand v3 OFF** — le test le plus important :

```python
def test_v2_behavior_unchanged_when_v3_disabled(monkeypatch):
    monkeypatch.delenv("BRAIN_V3_ENABLED", raising=False)
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    monkeypatch.setenv("BRAIN_MODULATE_ALL", "true")
    brain = BrainManager()
    event = {"risk": "low", "movement": 0.5, "person": "bryan",
             "human_emotion": "happy", "attention_need": 0.8}
    result = brain.notify_visual_scene(event)
    assert brain._v3 is None
    assert isinstance(result, (str, type(None)))
```

**Habituation : stimulus répété perd en saillance** :

```python
def test_habituation_reduces_saliency(freeze_time):
    tracker = HabituationTracker(halflife_sec=120.0)
    canonical = "obj:cat:appeared"
    assert tracker.familiarity(canonical) == 0.0
    for _ in range(5):
        tracker.imprint(canonical)
    fam_high = tracker.familiarity(canonical)
    assert fam_high > 0.4
    freeze_time.tick(240.0)  # 2 demi-vies
    assert tracker.familiarity(canonical) < fam_high * 0.3
```

**Budget épuisable** :

```python
def test_budget_exhausts_after_repeated_reactions():
    budget = AttentionBudget(initial=1.0)
    for _ in range(3):
        assert budget.can_afford(0.30)
        budget.consume(0.30)
    assert not budget.can_afford(0.30)
    budget.refill(0.5)
    assert budget.can_afford(0.30)
```

**Risk=high court-circuite tout** :

```python
def test_high_risk_bypasses_budget_and_habituation():
    policy = ReactionPolicy(threshold=0.55)
    budget = AttentionBudget(initial=0.0)  # budget vide
    stimulus = Stimulus("obj:fire:appeared", "vision_object",
                         intensity=0.5, valence=0.0, risk="high",
                         attention_need=0.9, ts=time.monotonic(), raw={})
    decision = policy.decide(stimulus, spike=False, familiarity=1.0,
                              modulation=ModulationVector.neutral(),
                              budget=budget, threshold=0.55)
    assert decision.action == "REACT"
    assert decision.cost <= 0.05
```

**Performance** :

```python
def test_v3_process_under_budget():
    manager = V3Manager(limbic_ref=MockLimbic())
    payload = {"object_class": "Cat", "event_type": "appeared",
                "movement": 0.5, "risk": "low", "attention_need": 0.3}
    times = []
    for _ in range(100):
        start = time.perf_counter()
        manager.process(payload, channel="vision_object")
        times.append((time.perf_counter() - start) * 1000.0)
    p95 = sorted(times)[94]
    assert p95 < 3.0
```

---

## 8. Plan de calibration

### Phase 1 — Shadow live (3-7 jours)
- `BRAIN_V3_ENABLED=true`, `BRAIN_V3_SHADOW_MODE=true`
- v3 logge toutes ses décisions ; v2 reste maître
- Observer `/brain/v3/traces` pendant usage normal d'Ada
- Ajuster `REACTION_THRESHOLD`, `HABITUATION_HALFLIFE`, `COST_*` selon écarts au comportement souhaité

### Phase 2 — Active sur canal unique (3-5 jours)
- `BRAIN_V3_SHADOW_MODE=false` mais seulement pour `vision_object` (le pont YOLO, le moins risqué)
- Les autres canaux continuent sur v2 pur
- Si comportement OK → étendre

### Phase 3 — Active sur tous canaux
- v3 gate toutes les décisions de spontanéité
- v2 reste l'oracle pour hormones et mood

---

## 9. Risques résiduels et mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| AdaptiveLIF mal calibré → Ada complètement muette | Élevé | Mode shadow + observabilité traces avant activation |
| Budget se vide trop vite → fenêtres de silence trop longues | Moyen | `BUDGET_MAX=1.5` plafond + refill par dopamine |
| Habituation LRU évince un stimulus important | Faible | LRU 256 entrées ; risk=high bypass habituation |
| Latence > 5ms cumulée v2+v3 | Moyen | Budget v3 à 3ms + degraded 30s sur exception |
| Threading entre refill loop et tick principal | Faible | Tous les accès protégés par Lock |
| Bug dans canonical_id → habituation foireuse | Moyen | Tests unitaires sur stabilité des id par channel |

---

## 10. Critères d'acceptation

- ✅ Tous les tests v2 existants (`brain/tests/`) passent inchangés
- ✅ p95 latence `V3Manager.process()` < 3ms
- ✅ v3 désactivé → comportement strictement v2 (test d'isolation)
- ✅ Pont YOLO fonctionnel (fix du bug `ingest_stimulus` ada.py:4800)
- ✅ Ada ne spam pas en démo live (vérifié manuellement en shadow)
- ✅ `risk=high` passe toujours, même budget vide / familiarité max
- ✅ Mode degraded propre si tick > budget ou exception (pas de crash)
- ✅ La vision en temps réel continue de fonctionner (hand tracking, vision écran, voice pipeline intacts)
- ✅ YOLO reste une couche supplémentaire, pas remplacée
- ✅ Voix Kore inchangée (aucune modification de `modulators.py`)

---

## 11. Estimation et structure d'implémentation

| Module | LOC estimé | Tests | Risque |
|---|---|---|---|
| `brain/v3/types.py` | ~50 | inclus | Faible |
| `brain/v3/adapters.py` | ~120 | `test_adapters.py` | Moyen |
| `brain/v3/neurons.py` | ~100 | `test_neurons_adaptive.py` | Faible |
| `brain/v3/attention.py` | ~80 | `test_attention_field.py` | Moyen |
| `brain/v3/habituation.py` | ~80 | `test_habituation.py` | Faible |
| `brain/v3/neuromodulation.py` | ~50 | `test_neuromodulation.py` | Faible |
| `brain/v3/traces.py` | ~50 | `test_traces.py` | Faible |
| `brain/v3/policy.py` | ~100 | `test_policy.py` | Élevé (cœur métier) |
| `brain/v3/v3_manager.py` | ~120 | `test_v3_manager.py` | Moyen |
| Patch `brain/brain_manager.py` | +40 | tests v2 + isolation | Moyen |
| Patch `backend/ada.py` (2 lignes) | +2 | `test_integration_v3.py` | Faible |
| Endpoint `server.py:/brain/v3/traces` | ~30 | manuel | Faible |
| **Total** | **~820 LOC** | **~11 fichiers tests** | |

L'implémentation se découpe naturellement en **6 étapes** (à détailler dans le plan d'implémentation) :

1. **Fondations** : `types.py`, `adapters.py`, `traces.py` + tests
2. **Modèle neuronal** : `neurons.py`, `attention.py`, `neuromodulation.py` + tests
3. **Décision** : `habituation.py`, `policy.py` + tests
4. **Façade** : `v3_manager.py` + tests (manager isolé)
5. **Intégration** : patch `brain_manager.py` + patch `ada.py` + tests d'isolation et bout-en-bout
6. **Observabilité** : endpoint REST `/brain/v3/traces` + calibration shadow

Chaque étape est commitable indépendamment et laisse le système fonctionnel.
