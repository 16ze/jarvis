# Analyse approfondie — Simulation biologique, Agents, Architecture

> Audit technique du 2026-07-06 — complément à `AUDIT.md`.
> Focus : fidélité biologique du brain, architecture d'agents, dette de code.

---

## PARTIE 1 — La simulation biologique

### 1.1 Ce qui est réellement bien conçu

Il faut le dire d'emblée : le brain d'Ada n'est pas de la décoration. Plusieurs choix sont
justes sur le plan des neurosciences computationnelles :

| Élément | Pourquoi c'est bon |
|---|---|
| **Neurones LIF** (`neurons.py`) | Vrai modèle *leaky integrate-and-fire* avec période réfractaire — le standard des SNN |
| **AHP + seuil adaptatif** (`v3/neurons.py`) | L'after-hyperpolarization et l'adaptation de seuil sont de vrais mécanismes d'accommodation neuronale |
| **Neuromodulation** (`v3/neuromodulation.py`) | Les hormones modulent l'excitabilité neuronale — exactement le rôle des neuromodulateurs (DA/NA/5-HT) |
| **Habituation temporelle** (`v3/habituation.py`) | Décroissance exponentielle correcte `0.5^(Δt/T½)` + éviction LRU |
| **Budget d'attention** (`v3/policy.py`) | Modèle métabolique : réagir coûte, se recharge dans le temps. Très juste conceptuellement |
| **Porte probabiliste** | Le tir stochastique reflète la variabilité neuronale réelle |
| **Architecture défensive** | Feature flags, mode dégradé, aucune exception ne remonte vers Ada |

La couche v3 est clairement d'un niveau au-dessus de la v2.

---

### 1.2 🔴 Le défaut fondamental : la fuite membranaire ignore le temps

**C'est le bug de fidélité le plus important du système.** Il touche v2 ET v3.

```python
# brain/neurons.py:37  et  brain/v3/neurons.py:44
self._potentiel *= (1.0 - self.fuite)   # ← appliqué PAR APPEL, pas par temps écoulé
```

En biologie, le potentiel membranaire décroît **continûment dans le temps** :
`V(t) = V_repos + (V₀ - V_repos)·e^(−Δt/τ)`.

Ici, la fuite s'applique une fois par appel à `exciter()`, quel que soit le temps écoulé.

**Démonstration exécutée sur le code réel :**

```
10 excitations de 0.09 (rapides) → potentiel = 0.431
1  excitation  de 0.90            → potentiel = 0.900   ← même charge, résultat 2× différent
après 0.5, puis 1 seconde d'attente SANS appel → potentiel = 0.5 (INCHANGÉ)
```

**Conséquences concrètes :**
1. Le comportement du brain dépend de la **fréquence d'échantillonnage** (`poll_hz=2.0`), pas du temps réel. Changer le poll rate casse toute la calibration.
2. Un neurone **garde son potentiel indéfiniment** en l'absence de stimulus — l'excitation ne retombe jamais toute seule. Biologiquement faux, et cela fausse l'état d'éveil (`_calculer_etat` lit `potentiel/seuil`).
3. Les seuils (`BRAIN_*_THRESHOLD`) ont été calibrés empiriquement **autour de ce bug** — les corriger demandera de recalibrer.

**Correctif (≈5 lignes, à appliquer aux deux versions) :**

```python
# Ajouter tau (constante de temps, en secondes) et mémoriser le dernier update
def exciter(self, intensite: float) -> bool:
    with self._lock:
        now = time.monotonic()
        if now - self._t_dernier_spike < self.periode_refractaire:
            return False
        # Fuite exponentielle réelle, fonction du temps écoulé
        dt = max(0.0, now - self._t_last_update)
        self._t_last_update = now
        self._potentiel = self.potentiel_repos + (
            (self._potentiel - self.potentiel_repos) * math.exp(-dt / self.tau)
        )
        ...
```
Avec `tau ≈ -Δt_nominal / ln(1 - fuite)` pour retrouver le comportement actuel au poll rate courant
(≈ 2.5 s pour fuite=0.18 à 2 Hz), la migration se fait sans casser la calibration existante.

---

### 1.3 🟠 L'analyse émotionnelle est un sac-de-mots

`limbic.analyser_texte()` (`limbic.py:140`) calcule la valence par **comptage de mots** dans des
lexiques fixes (`INSULTES`, `POSITIFS`, `TRISTES`…).

C'est le maillon faible d'un système dont l'argument central est la finesse émotionnelle :

- **Aucune gestion de la négation** : « je ne suis *pas* en colère » compte comme colère.
- **Aucune ironie / second degré** : « super, encore un bug… » compte comme positif.
- **Aucun contexte multi-tour** : l'intensité d'une remarque dépend de ce qui précède.
- **Aucune intentionnalité** : on sait *combien* c'est négatif, jamais *pourquoi* ni *envers quoi*.

**L'ironie de la situation** : un LLM multimodal de pointe est **déjà dans la boucle**. Il pourrait
produire une évaluation affective structurée quasi gratuitement.

**Axe recommandé — passer à un modèle d'*appraisal* (théorie de l'évaluation cognitive) :**

```python
# Sortie structurée demandée au LLM en parallèle de la réponse (coût ~0)
{
  "valence": -0.6,        # négatif ↔ positif
  "arousal": 0.8,         # calme ↔ activé
  "dominance": 0.3,       # subi ↔ maîtrisé
  "cause": "correction_technique",
  "target": "soi",        # l'émotion porte SUR quoi
  "certainty": 0.7
}
```
Le modèle VAD (valence-arousal-dominance) + attribution est le standard en informatique affective.
Il alimenterait les hormones bien plus finement que le comptage de mots, **et** donnerait à Ada des
émotions *dirigées* (fier **de**, inquiet **pour**) au lieu d'une simple intensité.

Le lexique reste utile en **repli** hors ligne / quand le LLM est indisponible.

---

### 1.4 🔴 Aucune persistance : Ada renaît amnésique à chaque redémarrage

Vérifié : **aucun** `save`/`load`/`json.dump` dans tout `brain/`.

À chaque redémarrage du backend :
- les 6 hormones repartent à `BASELINE`,
- l'habituation est vidée (tout redevient « nouveau »),
- les traces courtes et le budget d'attention sont réinitialisés.

**C'est incohérent avec la proposition de valeur.** Un compagnon dont l'état affectif et la
familiarité se réinitialisent à chaque reboot ne construit aucune continuité relationnelle — alors
que c'est précisément ce que le `mood_block` prétend incarner.

**Axe — persistance avec « sommeil » :**
```python
# À l'arrêt : snapshot JSON {hormones, habituation, timestamp}
# Au démarrage : recharger PUIS appliquer la décroissance du temps écoulé
elapsed = now - snapshot["timestamp"]
for h, v in hormones.items():
    # retour progressif vers la baseline pendant l'absence
    hormones[h] = baseline[h] + (v - baseline[h]) * exp(-elapsed / TAU_SOMMEIL[h])
```
Ada « se réveille » alors dans un état cohérent : une dispute d'il y a 10 minutes est encore
présente, celle d'il y a 3 jours s'est estompée. C'est **le gain de réalisme le plus fort pour le
moins d'effort** de toute cette analyse.

---

### 1.5 🟠 Aucune plasticité : le cerveau ne fait que réagir, il n'apprend jamais

Vérifié : aucun poids synaptique, aucun mécanisme hebbien/STDP, aucune dérive de tempérament.
Les seuils v3 s'adaptent (accommodation), mais **rien n'est conservé** ni appris durablement.

Le brain est aujourd'hui un **système dynamique à paramètres fixes** : il oscille autour de sa
baseline, sans jamais se transformer. C'est l'écart le plus large avec la biologie.

**Trois axes, par difficulté croissante :**

1. **Conditionnement associatif** (simple, fort impact) — associer un `canonical_id` de stimulus à
   une valence apprise. Si « déploiement Vercel » a été suivi 5 fois de frustration, le seul mot
   déclenche une légère anticipation négative. Une table `{stimulus → valence_moyenne}` persistée suffit.
2. **Dérive lente du tempérament** — faire dériver `BASELINE` très lentement vers la moyenne
   glissante des états vécus (τ ≈ semaines). Ada développerait un caractère façonné par la relation :
   plus confiante si le vécu est positif, plus prudente sinon.
3. **Plasticité hebbienne réelle** — poids entre neurones sensoriels et thalamus renforcés par
   co-activation (`w += η·pre·post`, avec normalisation). C'est le seul vrai SNN apprenant, mais
   c'est aussi le plus délicat à stabiliser.

---

### 1.6 🟡 Absence de rythme circadien et d'homéostasie

`mental_load` monte avec l'usage et redescend par décroissance, mais :
- pas de cycle jour/nuit (Ada est identique à 4 h et à 14 h),
- pas de récupération liée au sommeil,
- pas de variation d'énergie selon l'heure.

Ajout peu coûteux et très perceptible : moduler `serotonine`/`mental_load` par une sinusoïde
circadienne + un bonus de récupération selon la durée d'inactivité. Ada devient « du soir » ou
« du matin ».

---

### 1.7 🟡 Boucle ouverte : aucun retour sur l'effet produit

Le brain module le ton (température, `mood_block`) mais **ne reçoit jamais de signal sur l'effet**
de ce ton. Si une réponse sèche provoque un retour négatif de Bryan, rien ne l'enregistre.

C'est une boucle ouverte là où la régulation émotionnelle humaine est fermée. Un simple signal de
récompense sociale (valence du tour suivant) suffirait à alimenter le point 1.5.

---

### 1.8 Dette : v2 et v3 coexistent

`v3` est meilleur (AHP, habituation correcte, budget, politique), mais reste **désactivé par défaut**
(`BRAIN_V3_ENABLED=false`) et `v3/neuromodulation.derive()` **lit l'état de v2** — les deux versions
sont couplées, pas alternatives. Il faut trancher : migrer vers v3 comme chemin unique, en gardant
le limbique v2 comme couche hormonale (ce qu'il est déjà de fait).

**Détail** : `policy.py:107` utilise `random.random()` non seedé → tests non reproductibles.
Injecter un `random.Random(seed)` rendrait la politique testable de façon déterministe.

---

## PARTIE 2 — L'architecture d'agents

### 2.1 🔴 Absence d'abstraction commune (duplication 4×)

`research_agent`, `task_agent`, `anticipation_agent`, `monitoring_agent` répliquent chacun :
client `genai`, constante `SUB_MODEL`, boucle de tool-calling, parsing, retry.

Ajouter un agent = copier ~100 lignes. Corriger un bug de retry = le corriger 4 fois.

**Axe** : une classe `BaseAgent` (client injecté, boucle d'outils, retry, budget, traces) — chaque
agent ne définit alors que son prompt, ses outils et son modèle.

### 2.2 🟠 Modèles obsolètes et incohérents

```
12× "gemini-2.5-flash"        3× "gemini-2.0-flash-lite"   ← ancien
 1× "gemini-3-pro-preview"    1× "gemini-2.0-flash"
```
Trois agents tournent sur `gemini-2.0-flash-lite`, nettement dépassé pour du raisonnement.
Aucune stratégie de sélection.

**Axe** : un `models.py` central avec des rôles — `FAST`, `REASONING`, `VISION`, `CHEAP` — et un seul
endroit à modifier lors d'une montée de version.

### 2.3 🟠 Effets de bord à l'import

```python
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))   # niveau module, ×4
```
Conséquences : coût/latence à l'import, échec si la clé manque, impossible à mocker proprement
(c'est une des raisons pour lesquelles la suite de tests est fragile). → *lazy init* dans le constructeur.

### 2.4 🔴 Le manque le plus structurant : il n'existe pas de vrai planificateur

C'est **le** point qui bloque l'ambition « exécuter des tâches complexes ».

Aujourd'hui, le fonctionnement est **réactif** : Gemini reçoit une demande et appelle des outils
au fil de l'eau. Il n'y a pas :
- de décomposition explicite en sous-tâches,
- de plan persistant (donc pas de reprise après interruption),
- de vérification systématique de chaque étape,
- de réparation ciblée en cas d'échec partiel.

L'exception notable : `os_control_agent._plan_execute_verify()` implémente un vrai cycle
**Plan → Exécute → Vérifie → Corrige** (3 tentatives). C'est le bon patron… mais il est enfermé
dans le contrôle PC.

**Axe — généraliser ce patron en un moteur de planification transverse :**
```
Intention → Plan typé (étapes + critères de succès + dépendances)
          → Exécution (outil par étape, état persisté)
          → Vérification par étape
          → Réparation ciblée (rejouer l'étape, pas tout le plan)
```
C'est exactement la « Phase 3 » de la roadmap, et c'est ce qui transformerait Ada d'un assistant
réactif en véritable exécutant. Le plan persisté permet en prime de reprendre après un crash et
d'afficher l'avancement dans l'écran Activité.

### 2.5 🟠 Autres manques de la couche agents

- **Pas de mémoire de travail partagée** : chaque agent est un one-shot isolé. Pas de tableau noir
  (*blackboard*) permettant à `research_agent` de transmettre à `task_agent`.
- **Pas de traces structurées** : impossible de savoir qui a appelé quoi, à quel coût, en combien de
  temps. L'écran Activité montre du texte, pas des *spans*. → traces typées (durée, coût, succès).
- **Pas de budget tokens/coût**, pas de cache de résultats, pas de parallélisme contrôlé
  (`asyncio.gather` + sémaphore).
- **Double dispatch voix/texte** (`ada.py` + `external_bridge.py`) : dérive garantie entre les deux
  modes — mon test de cohérence a déjà attrapé la collision `control_light`/MCP. Un registre d'outils
  unique consommé par les deux est la vraie correction.

---

## PARTIE 3 — Le projet dans son ensemble

### 3.1 🔴 Mémoire sémantique dégradée en français

```python
self.conversations = self.client.get_or_create_collection("conversations")  # ← aucun embedding_function
```
Sans `embedding_function`, ChromaDB utilise **all-MiniLM-L6-v2**, un modèle **entraîné sur l'anglais**.
Or toute la mémoire d'Ada est en français : la recherche sémantique (`search_memory`, RAG documents,
mémoire vision) fonctionne donc **très en dessous de son potentiel**.

**Correctif à fort impact et faible effort** : passer à un embedding multilingue
(`intfloat/multilingual-e5-base`, `paraphrase-multilingual-MiniLM`, ou l'API d'embeddings Gemini).
⚠️ Nécessite de réindexer les collections existantes.

### 3.2 🟠 `ada.py` reste un monolithe de 6 574 lignes

Le point noir de maintenabilité. La CI et les tests posés en Phase 1 sécurisent désormais le
découpage — il peut se faire par extractions successives (dispatch, config voix, terminal, heartbeat).

### 3.3 🟡 Qualité et outillage

- Pas de **lint en CI** (`ruff` est présent en local mais absent du workflow) ni de typage vérifié (`mypy`).
- Configuration par `os.getenv` disséminé → une config typée (`pydantic-settings`) centraliserait
  et validerait les ~40 variables d'environnement.
- 2 tests obsolètes (`test_run_web_agent`, `test_kasa_agent`) testent des fonctionnalités supprimées.
- Frontend : `App.jsx` ≈ 2 400 lignes, bundle **1,47 Mo** non découpé (code-splitting recommandé).

### 3.4 🟠 `self_evolution_agent` : l'IA modifie et commit son propre code

Le garde-fou de chemin (`_validate_path`) est bon, mais l'agent peut écrire **et committer** sans
revue humaine systématique. À conserver désactivé par défaut, sur branche dédiée, avec confirmation
explicite avant tout commit.

---

## Priorisation recommandée

| # | Action | Effort | Impact |
|---|---|---|---|
| 1 | **Persistance de l'état du brain** (+ décroissance de sommeil) | Faible | ⭐⭐⭐⭐⭐ |
| 2 | **Embeddings multilingues** pour ChromaDB | Faible | ⭐⭐⭐⭐⭐ |
| 3 | **Fuite membranaire fonction du temps** (v2+v3) | Faible | ⭐⭐⭐⭐ |
| 4 | **Registre de modèles central** + sortir les clients de l'import | Faible | ⭐⭐⭐ |
| 5 | **Appraisal LLM** (VAD + attribution) en remplacement du sac-de-mots | Moyen | ⭐⭐⭐⭐⭐ |
| 6 | **Moteur de planification** généralisé (Phase 3) | Élevé | ⭐⭐⭐⭐⭐ |
| 7 | **BaseAgent** + registre d'outils unique (fin du double dispatch) | Moyen | ⭐⭐⭐⭐ |
| 8 | **Conditionnement associatif** (première vraie plasticité) | Moyen | ⭐⭐⭐⭐ |
| 9 | Découpage de `ada.py` | Élevé | ⭐⭐⭐ |
| 10 | Traces structurées + budget de coût | Moyen | ⭐⭐⭐ |

Les points 1, 2 et 3 sont des gains rapides à effet immédiatement perceptible.
Les points 5 et 6 sont les deux transformations qui changeraient la nature du système.
