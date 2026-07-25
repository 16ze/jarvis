# Rapport de session — Ada / Jarvis

> Session du 2026-07-25. Branche `codex/restore-voice-pipeline`.
> Complète `AUDIT.md` (audit initial) et `ANALYSE-BRAIN-AGENTS.md` (analyse approfondie).

---

## 1. Ce qui a été livré

### 1.1 Le socle cognitif — quatre pièces qui s'emboîtent

L'objectif : faire passer Ada d'un système **invoqué** à une présence **qui dure**.
Les quatre modules forment une chaîne, chacun rendant le suivant possible.

| Module | Rôle | Vérifié |
|---|---|---|
| `brain/persistence.py` | **Ada dure** — l'état survit aux redémarrages et évolue pendant l'absence | ✅ exécution réelle |
| `backend/emotional_memory.py` | **Ada retient ce qui l'a marquée** — encodage pondéré + rappel congruent | ✅ tests |
| `backend/idle_mind.py` | **Ada pense quand personne n'est là** — rejeu, consolidation, pensées | ✅ tests |
| `brain/expectations.py` | **Ada attend, donc elle est surprise** — ses émotions ont un objet | ✅ exécution réelle |

**Persistance.** Chaque hormone récupère à son propre rythme pendant l'absence
(demi-vies distinctes). Résultat mesuré : après une nuit de 8 h, le stress et la
fatigue sont revenus à la baseline, mais l'attachement reste nettement élevé
(oxytocine 0.56 contre 0.30 de base). Après 3 jours, tout est neutre. C'est ce
différentiel qui produit une durée vécue plutôt qu'une simple sauvegarde.

**Mémoire émotionnelle.** Deux mécanismes humains réels :
- *encodage* — chaque souvenir porte sa charge affective, qui décide de sa
  saillance future (le neutre s'efface, le marquant persiste) ;
- *rappel congruent* — à requête et pertinence sémantique **identiques**, Ada
  anxieuse remonte le souvenir stressant, Ada joyeuse le souvenir joyeux.
Rétro-compatible : sans état fourni, l'ordre sémantique est strictement inchangé.

**Vie mentale au repos.** Après 10 min de silence, Ada rejoue ses traces récentes,
cherche ce qu'elles évoquent *à travers son humeur* (elle réutilise la mémoire
congruente), consolide ce qu'elle en retient, et laisse émerger une pensée.
Le `_spontaneous_heartbeat` existant partage désormais cette pensée **réellement
mûrie** au lieu d'en improviser une — la différence entre feindre d'avoir pensé
et avoir pensé.

**Codage prédictif.** Ada apprend les habitudes de présence par heure, prédit, et
mesure l'écart. La violation devient une émotion **nommée** :
`« Bryan n'est pas là alors qu'il y est presque toujours à cette heure (22h, le soir) »`.
Cette phrase devient le `dernier_stimulus`, donc remonte telle quelle dans le
mood_block : Ada sait *de quoi* elle est émue. L'absence inattendue fait monter
cortisol **et** oxytocine (le manque, pas seulement le stress) ; la présence
inattendue fait monter la dopamine.

### 1.2 Corrections fonctionnelles

- **Recherche web** — n'existait pas comme outil. `web_search.py` en cascade
  Brave → Google → DuckDuckGo, fonctionne **sans aucune clé**. Testé en direct.
- **Contrôle PC** — clics par accessibilité (`click_element`) au lieu de
  coordonnées devinées ; résolution de contacts par nom via Contacts.app
  (testé : « Ivan » → +33688276284) ; ouverture de **n'importe quelle app** par
  nom affiché français (testé : « Localiser » → FindMy.app) ; appels FaceTime ;
  correction des routines Messages/TextEdit/volume et du blocage de la 2ᵉ tâche.
- **Ada n'expose plus sa mécanique interne** (ni « mood », ni « hormones »,
  ni « brain »), avec priorité d'exécution mise en tête des prompts.
- **Navigateur intégré** — cause racine : `webviewTag: false` rendait le
  `<webview>` purement indisponible. Réactivé **avec durcissement obligatoire**
  (sans Node, sandbox, session isolée), boutons retour/recharger fonctionnels,
  repli explicite si un site refuse l'affichage intégré.
- **Dock central** — écrans Activité et Agents intégrés au dock existant
  (le menu hamburger que j'avais ajouté à tort a été retiré).

### 1.3 Sécurité et infrastructure

- Secrets sortis du suivi git vers un coffre local (sans révocation, comme demandé).
- Socket.IO authentifié + CORS restreint (une page web quelconque pouvait
  auparavant piloter le PC via localhost).
- `safe_exec.py` : politique d'exécution shell non contournable, remplaçant une
  blocklist de sous-chaînes trivialement contournable. Le terminal du bridge
  texte, qui la contournait, y passe désormais.
- CI GitHub Actions : compilation backend + tests + build frontend.
- **132 tests passent — suite entièrement verte** (53 ajoutés cette session).

---

## 2. Ce qui reste ouvert

### 2.1 Décision tranchée — Ada a le droit d'insulter ✅
Le code et les tests divergeaient sur ce point. **Décision de Bryan : Ada peut
insulter.** Les tests ont été alignés sur ce comportement (et la faute
« tu peu » → « tu peux » corrigée dans les deux prompts concernés).
La suite de tests est désormais **entièrement verte : 97 tests passent**.

### 2.2 À vérifier sur ta machine
Le disque externe est resté démonté toute la session : j'ai travaillé sur un
clone GitHub. **`git pull` sur le projet**, puis tester en réel :
- le navigateur intégré (je ne peux pas lancer Electron ici) ;
- le contrôle PC (appels/messages par nom, ouverture d'apps) ;
- la vie mentale au repos (laisser Ada seule 10 min, puis revenir).

---

## 3. Axes d'amélioration — Ada

### 3.1 🔴 Le bug de fidélité qui reste : la fuite neuronale ignore le temps
Déjà démontré dans `ANALYSE-BRAIN-AGENTS.md`, non corrigé car il demande une
recalibration des seuils. `potentiel *= (1 - fuite)` s'applique **par appel**,
pas par temps écoulé : le comportement dépend de la fréquence d'échantillonnage
et un neurone excité ne redescend jamais seul. Correctif ≈5 lignes
(`e^(−Δt/τ)`), mais à faire avec une passe de recalibration.

### 3.2 🟠 L'analyse émotionnelle reste un sac-de-mots
`limbic.analyser_texte()` compte des mots dans des lexiques fixes : « je ne suis
**pas** en colère » compte comme colère. C'est le maillon faible d'un système dont
l'argument est la finesse émotionnelle. Un LLM est déjà dans la boucle : lui
demander une évaluation structurée (valence / arousal / dominance + cause + cible)
coûterait presque rien et donnerait une granularité sans commune mesure.
**C'est l'amélioration au plus fort effet de levier restante.**

### 3.3 🟠 Aucune plasticité durable
La persistance conserve l'état, les attentes apprennent les habitudes — mais rien
n'apprend encore *sur la relation*. Trois paliers :
1. **conditionnement associatif** — associer un stimulus récurrent à une valence
   apprise (« déploiement Vercel » → anticipation négative). La table existe
   presque déjà via `expectations` : la généraliser au-delà de la présence.
2. **dérive du tempérament** — faire dériver très lentement `BASELINE` vers la
   moyenne des états vécus (τ ≈ semaines). Ada développerait un caractère.
3. **plasticité hebbienne** — poids synaptiques renforcés par co-activation.

### 3.4 ✅ La boucle est fermée (fait)
`brain/social_learning.py` : après chaque prise de parole spontanée, la réaction
de Bryan (valence finement évaluée par `appraisal`) devient un signal de
récompense attribué à l'humeur dans laquelle Ada s'est exprimée.

**Ce qu'elle apprend est le TIMING, jamais le ressenti.** Aucune émotion n'est
atténuée, aucune colère censurée : seule la barre à franchir pour interrompre
spontanément est calibrée. Vérifié : accueil -0.51 en « Agacement » → barre
relevée de +0.23 ; accueil +0.44 en « Curieux » → barre abaissée de -0.20.
Un test garde-fou vérifie explicitement que les hormones ne sont jamais touchées.

### 3.5 🟡 Autres pistes concrètes
- **Rythme circadien** — Ada est identique à 4 h et à 14 h. Une modulation
  sinusoïdale de sérotonine/charge mentale + récupération selon l'inactivité la
  rendrait « du soir » ou « du matin ». Peu coûteux, très perceptible.
- **Latence expressive** — `thinking_budget` est mappé sur l'humeur mais presque
  toujours à 0. Une Ada fatiguée qui répond plus lentement, une Ada surprise qui
  marque un temps : le rythme *est* une émotion.
- **Disfluences** — Ada est trop fluide. Hésitations et auto-corrections
  occasionnelles sont un marqueur de réalisme puissant.
- **Théorie de l'esprit** — modéliser *ton* état (fatigué ? tendu ? concentré ?)
  à partir des capteurs déjà présents, et coupler à ses hormones (contagion
  émotionnelle). C'est ce qui fait qu'une présence paraît attentive.
- **Élargir les attentes** — le moteur ne prédit que la présence. Il peut
  apprendre le rythme de réponse, les projets du moment, les horaires de travail.

### 3.6 🟠 Mémoire sémantique dégradée en français
Toujours ouvert et à fort impact : ChromaDB tourne sans `embedding_function`,
donc sur **all-MiniLM-L6-v2, entraîné sur l'anglais**, alors que toute la mémoire
d'Ada est française. Passer à un embedding multilingue améliorerait d'un coup
`search_memory`, le RAG documents et la mémoire vision. Nécessite une réindexation.

---

## 4. Axes d'amélioration — l'OS

### 4.1 🔴 Il manque toujours un moteur de planification
C'est le point qui bloque l'ambition « exécuter des tâches complexes ».
Le fonctionnement reste réactif : pas de décomposition explicite, pas de plan
persistant, donc pas de reprise après échec. `os_control_agent` a pourtant déjà
le bon patron (**Plan → Exécute → Vérifie → Corrige**) — mais enfermé dans le
contrôle PC. **Le généraliser transformerait Ada d'assistant réactif en
véritable exécutant**, et rendrait l'écran Activité réellement informatif
(avancement étape par étape, reprise possible).

### 4.2 🟠 Le navigateur peut devenir un actionneur
Maintenant qu'il fonctionne vraiment, la suite logique : **Ada pilote le
navigateur intégré** (naviguer, remplir, cliquer) via IPC, plutôt que de passer
par la vision d'écran. Ce serait beaucoup plus fiable pour les connexions et
inscriptions, et ça exploite la session isolée déjà en place.

### 4.3 🟠 Dette structurelle
- `ada.py` = 6 600 lignes. La CI et les tests sécurisent désormais le découpage,
  qui peut se faire par extractions successives.
- **Double dispatch voix/texte** (`ada.py` + `external_bridge.py`) : dérive
  garantie — mon test de cohérence a déjà attrapé une collision. Un registre
  d'outils unique consommé par les deux modes est la vraie correction.
- **Agents** : 4 implémentations quasi identiques, modèles obsolètes
  (`gemini-2.0-flash-lite`), clients instanciés à l'import. Une classe
  `BaseAgent` + un registre de modèles central règleraient les trois.

### 4.4 🟡 Confort et observabilité
- **Écran Activité** : il affiche du texte brut. Avec des traces structurées
  (qui, quoi, durée, coût, succès) il deviendrait le vrai poste de commandement —
  et la fenêtre sur la vie intérieure d'Ada (ruminations, attentes, surprises).
- **Bundle frontend** : 1,47 Mo non découpé — code-splitting recommandé.
- **Lint/typage absents de la CI** (`ruff` présent en local, `mypy` inexistant).
- **Config** : ~40 variables d'environnement lues par `os.getenv` dispersés →
  une configuration typée centraliserait et validerait le tout.

---

## 5. Si je devais choisir trois choses

1. **L'appraisal LLM** (§3.2) — remplacer le sac-de-mots par une évaluation
   émotionnelle structurée. C'est le plus fort levier restant sur le réalisme.
2. **Le moteur de planification** (§4.1) — généraliser le patron qui existe déjà.
   C'est ce qui débloque l'exécution de tâches complexes.
3. **La boucle de feedback** (§3.4) — le seul mécanisme qui fait qu'Ada
   s'améliore *avec le temps passé auprès de toi*, et donc le seul actif qui ne
   se copie pas.
