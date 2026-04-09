# Ada — Consolidation & Robustesse — Design Spec
**Date :** 2026-04-09  
**Auteur :** Bryan Hilaire / Kairo Digital  
**Statut :** Approuvé — prêt pour implémentation

---

## Contexte

Sprint de consolidation pour rendre Ada fonctionnelle et robuste. Six problèmes identifiés après audit du code.

---

## Problème 1 — Wake word (Ada ne se réveille pas)

### Cause racine
En mode veille, `listen_audio` accumule l'audio dans `_sleep_audio_buffer` mais ne l'envoie plus à Gemini Live. Le seul mécanisme actif est `_wake_word_loop` → `_check_wake_word_api`. Ce mécanisme a 3 failles :
1. Debounce trop agressif — si l'appel API prend 2-3s, zone morte où "Ada" n'est pas détecté
2. Fenêtre audio trop courte (3s) — peut couper le mot en début de fenêtre
3. Prompt trop strict — ne couvre pas "Hé Ada", "Hey Ada", "Ada ?"

### Fix
- `WINDOW_BYTES` : 3s → **4s**
- `CHECK_INTERVAL` : 0.8s → **1.2s**
- `MIN_RMS` : 150 → **100**
- Debounce modifié : si task précédent > 2s en cours → cancel + relance
- Prompt : couvrir "Ada", "Hé Ada", "Hey Ada", "Ada ?", toute variation

**Fichier :** `backend/ada.py` — constantes `_wake_word_loop` + prompt `_check_wake_word_api`

---

## Problème 2 — Contrôle PC

### 2a. Mauvaise sélection d'outil
Ada appelle `run_web_agent` (Playwright visible) au lieu de `execute_pc_task` (contrôle Mac réel).

**Cause :** 3 tools aux descriptions qui se chevauchent.

**Fix :**
- Supprimer `control_computer` de la liste tools Live (voix) — le conserver dans `_execute_text_tool` (Telegram)
- `execute_pc_task` absorbe son rôle côté voix
- Réécriture des descriptions (voir section 6)

### 2b. OsControlAgent — précision + stop immédiat

**Problème précision :** vision loop estime les coordonnées via screenshot compressé → trop imprécis pour formulaires/petits éléments.

**Fix — deux modes combinés :**

**Mode 1 — Accessibility API (défaut)** : interroger l'arbre d'accessibilité macOS via osascript pour trouver les éléments par nom/rôle et cliquer précisément sans coordonnées.
```applescript
tell application "Safari"
  click button "Rechercher" of window 1
end tell
```
Gemini génère le nom de l'élément cible → osascript le trouve et clique. Zéro erreur de coordonnées.

**Mode 2 — Vision loop (fallback)** : uniquement si l'accessibility API ne trouve pas l'élément. Avec étape de planification obligatoire : Gemini génère un plan JSON de 3-5 étapes avant d'agir.

**Autres ajustements OsControlAgent :**
- `MAX_STEPS` : 30 → **15**
- Détection boucle : même action × 3 → `finish` avec échec explicite
- Ajout `return` et `escape` aux hotkeys fast-path

**Fix — stop immédiat :**
- `asyncio.Event` global `_current_pc_stop_event` créé au démarrage de chaque tâche PC
- Nouvel outil Gemini `stop_pc_task` (NON_BLOCKING) : set l'event → loop s'arrête en < 0.5s
- System prompt : *"Si Bryan dit 'arrête', 'stop', 'annule' → appelle stop_pc_task IMMÉDIATEMENT"*

**Fichiers :** `backend/os_control_agent.py`, `backend/ada.py`, `backend/mcp_tools_declarations.py`

---

## Problème 3 — Reconnaissance faciale & vocale

### État
Désactivée (`face_auth_enabled: false`). Infrastructure présente mais non testée depuis correction. État inconnu.

### Fix

**Étape 1 — Script de test isolé**
Créer `backend/test_face_recognition.py` : lance `MultiUserFaceDetector` + `VoiceRecognizer` indépendamment, affiche les détections. Bryan l'exécute pour valider sans risque pour Ada.

**Étape 2 — Wrapper de sécurité**
`_face_detection_loop` : try/except global avec fallback silencieux. Si MediaPipe plante → log `[PRESENCE] Face detection disabled: {e}`, Ada continue normalement. Si `face_refs/` vide → pas de détection, pas d'erreur.

**Étape 3 — Activation conditionnelle**
Dans `server.py` au démarrage :
```python
if settings.get("face_auth_enabled"):
    tg.create_task(audio_loop._face_detection_loop())
    tg.create_task(presence_manager.run())
```
Activation via `settings.json` uniquement. Zéro overhead si désactivé.

**Fichiers :** `backend/server.py`, `backend/ada.py`, nouveau `backend/test_face_recognition.py`

---

## Problème 4 — Chromecast (trouvé mais ne répond pas)

### Cause
`cast.wait()` établit le socket mais n'attend pas que le media controller soit prêt. Les commandes arrivent trop tôt et sont ignorées silencieusement.

### Fix

**Connexion IP directe (bypass mDNS) :**
```python
CHROMECAST_HOST = "192.168.1.127"  # dans .env
if host := os.getenv("CHROMECAST_HOST"):
    cast = pychromecast.get_chromecast_from_host((host, 8009, uuid, model, name))
else:
    chromecasts, browser = pychromecast.get_chromecasts(timeout=10)
    cast = chromecasts[0]
```

**Attente réelle du media controller :**
```python
cast.wait()
cast.media_controller.update_status()
time.sleep(1.0)
```

**Reconnexion automatique :** si commande échoue → reconnexion une fois avant erreur.

**Variable d'env à ajouter :** `CHROMECAST_HOST=192.168.1.127`

**Fichier :** `backend/chromecast_agent.py`

---

## Problème 5 — Sonnette Tuya avec caméra

### Device
- **ID :** `bf4c3d1743e00446c3ccl6`
- **Type :** sonnette avec caméra
- **Clé locale :** à récupérer via Tuya Cloud API (credentials disponibles)

### Architecture

**Récupération automatique de la clé locale :**
Appel `GET /v1.0/devices/{device_id}` à l'API Cloud Tuya avec `TUYA_API_KEY` + `TUYA_API_SECRET` pour récupérer `local_key` et `ip`. Stocké dans `devices.json`.

**`backend/doorbell_agent.py`** :
- Polling état toutes les **3s** via tinytuya
- Détection appui → alerte vocale Ada : *"Bryan, quelqu'un à la porte."*
- Notification Telegram + snapshot caméra si disponible
- Ada propose : *"Tu veux que je regarde qui c'est ?"*

**Outils Gemini :**
- `get_doorbell_status` — état actuel (sonnant / calme)
- `get_doorbell_snapshot` — capture image caméra

**Démarrage :** polling lancé automatiquement avec Ada dans `server.py`.

**Variables d'env à ajouter :**
```
TUYA_API_KEY=<valeur>
TUYA_API_SECRET=<valeur>
```

**Fichiers :** nouveau `backend/doorbell_agent.py`, `backend/ada.py`, `backend/external_bridge.py`, `backend/mcp_tools_declarations.py`, `backend/server.py`

---

## Problème 6 — Précision des tool calls

### Fix

**Suppression `control_computer` de la liste tools Live** (voix uniquement — conservé Telegram).

**Nouvelles descriptions :**

`run_web_agent` :
> *"Ada travaille en arrière-plan pendant que Bryan est occupé. Playwright invisible, écran de Bryan intact. Réservé à : récupérer une info (météo, prix, article, horaires) sans interrompre Bryan. JAMAIS si Bryan veut voir son navigateur ou agir sur son écran."*

`execute_pc_task` :
> *"Prend le contrôle visible du Mac de Bryan. Utilise ce tool pour TOUT ce qui nécessite d'agir sur l'écran : ouvrir une app, naviguer sur un site, remplir un formulaire, faire une recherche Google visible, cliquer, taper du texte, déplacer des fichiers. Tool par défaut dès que Bryan interagit avec son ordinateur."*

**Bloc décision dans le system prompt :**
```
RÈGLE SÉLECTION OUTIL PC (priorité absolue) :
→ Bryan est occupé, veut juste une INFO sans toucher son écran → run_web_agent
→ Bryan veut qu'Ada agisse sur son écran (ouvrir, naviguer, cliquer, remplir) → execute_pc_task
→ Bryan dit "arrête" pendant une tâche PC → stop_pc_task IMMÉDIATEMENT
→ Moindre doute → execute_pc_task

Exemples :
  "ouvre Google" → execute_pc_task
  "va sur YouTube" → execute_pc_task
  "remplis ce formulaire" → execute_pc_task
  "cherche le prix de l'iPhone pendant que je travaille" → run_web_agent
  "c'est quoi la météo demain" → run_web_agent
  "arrête" → stop_pc_task
```

**Fichiers :** `backend/mcp_tools_declarations.py`, `backend/ada.py` (system prompt + tools list)

---

## Récapitulatif des fichiers modifiés

| Fichier | Modifications |
|---|---|
| `backend/ada.py` | Wake word constantes + prompt, system prompt règles PC, tools list Live, stop_pc_task wiring, face detection conditionnel |
| `backend/os_control_agent.py` | Accessibility API mode 1, planning step, MAX_STEPS 15, stop_event global, loop detection |
| `backend/chromecast_agent.py` | IP directe, attente media controller, reconnect |
| `backend/mcp_tools_declarations.py` | Nouvelles descriptions, stop_pc_task tool, doorbell tools, suppression control_computer de Live |
| `backend/server.py` | Doorbell polling démarrage, face auth conditionnel |
| `backend/external_bridge.py` | Doorbell tools wiring, stop_pc_task wiring |
| `backend/doorbell_agent.py` | **Nouveau** — polling Tuya, alertes, snapshot |
| `backend/test_face_recognition.py` | **Nouveau** — script test isolé |

## Variables d'environnement à ajouter dans `.env`
```
CHROMECAST_HOST=192.168.1.127
TUYA_API_KEY=<valeur>
TUYA_API_SECRET=<valeur>
```
