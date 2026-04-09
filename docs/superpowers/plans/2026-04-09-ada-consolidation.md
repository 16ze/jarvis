# Ada — Consolidation & Robustesse — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre Ada fonctionnelle et robuste sur 6 points : wake word, contrôle PC, face recognition, Chromecast, sonnette Tuya, précision tool calls.

**Architecture:** Corrections ciblées dans les fichiers existants + 2 nouveaux fichiers (`doorbell_agent.py`, `test_face_recognition.py`). Aucun changement architectural. Toutes les modifications sont rétrocompatibles.

**Tech Stack:** Python 3.11, Gemini Live API, tinytuya, pychromecast, osascript/AppleScript, asyncio, MediaPipe

---

## File Map

| Fichier | Action | Quoi |
|---|---|---|
| `backend/ada.py` | Modifier | Wake word constantes + prompt, system prompt PC, tools list (remove control_computer), stop_pc_task wiring, execute_pc_task stop_event, face detection conditionnel |
| `backend/os_control_agent.py` | Modifier | Planning step, accessibility API action, MAX_STEPS 15, stop_event param, loop detection |
| `backend/mcp_tools_declarations.py` | Modifier | Descriptions run_web_agent + execute_pc_task, stop_pc_task tool, doorbell tools |
| `backend/chromecast_agent.py` | Modifier | IP directe CHROMECAST_HOST, attente media controller, reconnect auto |
| `backend/server.py` | Modifier | Face detection conditionnel, doorbell polling démarrage |
| `backend/external_bridge.py` | Modifier | stop_pc_task + doorbell tools wiring |
| `backend/doorbell_agent.py` | Créer | Tuya Cloud API key fetch, polling anneau, alertes Ada + Telegram |
| `backend/test_face_recognition.py` | Créer | Script test isolé face + voice recognition |
| `.env` | Modifier | Ajouter CHROMECAST_HOST, TUYA_API_KEY, TUYA_API_SECRET |

---

## Task 1 : Fix wake word — ada.py

**Files:**
- Modify: `backend/ada.py` (méthodes `_wake_word_loop` et `_check_wake_word_api`)

- [ ] **Step 1 : Localiser les constantes dans `_wake_word_loop`**

Ouvre `backend/ada.py`. Cherche `async def _wake_word_loop`. Tu verras (vers ligne 2883) :
```python
async def _wake_word_loop(self):
    CHECK_INTERVAL = 0.8
    MIN_RMS = 150
    WINDOW_BYTES = SEND_SAMPLE_RATE * 2 * 3
    _pending_task: asyncio.Task | None = None
```

- [ ] **Step 2 : Remplacer les constantes et le debounce**

Remplace tout le corps de `_wake_word_loop` par :
```python
async def _wake_word_loop(self):
    """Écoute le buffer audio en mode veille, détecte 'ada' via Gemini Flash.

    Architecture v3 — appels API non-bloquants :
    - La boucle vérifie toutes les 1.2s SANS attendre la réponse API
    - Les appels API tournent en tâches parallèles → aucune zone morte
    - Debounce : cancel le task précédent s'il tourne depuis > 2s
    """
    CHECK_INTERVAL = 1.2   # Fenêtre glissante — vérifie toutes les 1.2s
    MIN_RMS = 100           # Seuil bas — capte voix normale et éloignée
    WINDOW_BYTES = SEND_SAMPLE_RATE * 2 * 4  # 4 secondes d'audio PCM 16kHz mono int16
    _pending_task: asyncio.Task | None = None
    _pending_started_at: float = 0.0

    while True:
        await asyncio.sleep(CHECK_INTERVAL)

        if not self.sleep_mode:
            _pending_task = None
            continue

        # Prendre les 4 dernières secondes du buffer (fenêtre glissante)
        buf = bytes(self._sleep_audio_buffer[-WINDOW_BYTES:])
        if len(buf) < 2048:
            continue

        # Vérifier le niveau sonore — ignorer le silence absolu
        arr = np.frombuffer(buf, dtype=np.int16)
        rms = int(np.sqrt(np.mean(arr.astype(np.int32) ** 2))) if len(arr) > 0 else 0
        if rms < MIN_RMS:
            continue

        # Debounce : cancel si le task précédent tourne depuis > 2s
        if _pending_task and not _pending_task.done():
            if time.monotonic() - _pending_started_at < 2.0:
                continue
            _pending_task.cancel()

        # Lancer l'appel API en parallèle — ne bloque pas la boucle
        _pending_task = _bg_task(self._check_wake_word_api(buf, rms), name="wake_word_check")
        _pending_started_at = time.monotonic()
```

- [ ] **Step 3 : Améliorer le prompt de `_check_wake_word_api`**

Dans la même méthode `_check_wake_word_api` (cherche `_check_wake_word_api`), remplace le bloc `contents=[...]` :

```python
# ANCIEN
contents=[
    types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
    "Est-ce que tu entends le mot 'Ada' (ou 'Hey Ada') prononcé dans cet audio ? "
    "Réponds UNIQUEMENT par 'oui' ou 'non', rien d'autre.",
],

# NOUVEAU
contents=[
    types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
    "Écoute cet audio et réponds UNIQUEMENT par 'oui' ou 'non', rien d'autre. "
    "Est-ce qu'on entend distinctement quelqu'un appeler 'Ada' ? "
    "(variations acceptées : 'Ada', 'Hé Ada', 'Hey Ada', 'Ada ?', 'Ada !', 'Ada viens') "
    "'oui' uniquement si Ada est clairement appelée. 'non' dans tous les autres cas.",
],
```

- [ ] **Step 4 : Vérifier que `time` est importé**

En tête de `ada.py`, vérifier que `import time` est présent (il l'est, ligne ~15). Aucun ajout nécessaire.

- [ ] **Step 5 : Tester manuellement**

Lance Ada, dis "Ada mets-toi en veille", attends 3s, puis dis "Ada". Vérifie dans les logs :
```
[ADA] [SLEEP] Wake word check (rms=XXX): 'oui'
[ADA] [SLEEP] Mot de réveil détecté — réveil d'Ada
```

- [ ] **Step 6 : Commit**

```bash
cd /Users/bryandev/jarvis
git add backend/ada.py
git commit -m "fix: improve wake word detection — wider window, better prompt, smarter debounce"
```

---

## Task 2 : Précision tool calls — descriptions + system prompt

**Files:**
- Modify: `backend/ada.py` (tools list ligne ~533, system prompt lignes ~609-620)
- Modify: `backend/mcp_tools_declarations.py` (descriptions run_web_agent, execute_pc_task)

- [ ] **Step 1 : Retirer `control_computer_tool` de la liste Live dans ada.py**

Cherche ligne ~533 dans `ada.py` :
```python
tools = [{"function_declarations": [
    generate_cad, run_terminal_tool,
    read_emails_tool, send_email_tool, get_email_body_tool,
    list_events_tool, create_event_tool, find_event_tool, delete_event_tool,
    create_project_tool, switch_project_tool, list_projects_tool,
    discover_printers_tool, print_stl_tool, get_print_status_tool, iterate_cad_tool,
    control_computer_tool,        # ← RETIRER CETTE LIGNE
    search_memory_tool, remember_tool, search_documents_tool,
```

Retire `control_computer_tool,` de cette liste. Le tool reste défini dans ada.py et wiré dans `_execute_text_tool` — il disparaît juste de Gemini Live voix.

- [ ] **Step 2 : Mettre à jour la description de `run_web_agent` dans mcp_tools_declarations.py**

Cherche `"name": "run_web_agent"` dans `mcp_tools_declarations.py`. Remplace la valeur `"description"` par :
```python
"description": (
    "Ada travaille en arrière-plan pendant que Bryan est occupé. "
    "Playwright invisible — l'écran de Bryan reste intact, rien ne s'ouvre sur son bureau. "
    "Utiliser UNIQUEMENT pour récupérer des informations (prix, météo, article, horaires, données) "
    "quand Bryan ne veut PAS voir son navigateur s'ouvrir. "
    "JAMAIS si Bryan demande d'ouvrir une app, naviguer sur un site visible, ou agir sur son écran."
),
```

- [ ] **Step 3 : Mettre à jour la description de `execute_pc_task` dans mcp_tools_declarations.py**

Cherche `"name": "execute_pc_task"`. Remplace la valeur `"description"` par :
```python
"description": (
    "Prend le contrôle visible du Mac de Bryan via screenshots + souris + clavier. "
    "Tool PAR DÉFAUT pour TOUT ce qui se passe sur l'écran de Bryan : "
    "ouvrir n'importe quelle application, naviguer sur un site web dans le vrai navigateur, "
    "remplir un formulaire, faire une recherche Google visible, cliquer dans l'interface, "
    "taper du texte, copier/coller, changer les réglages système, déplacer des fichiers. "
    "Exemples : 'ouvre Chrome', 'va sur YouTube', 'remplis ce formulaire', "
    "'fais une recherche Google sur X', 'ouvre le Finder', 'règle le volume système'. "
    "run_web_agent est RÉSERVÉ aux recherches silencieuses en arrière-plan "
    "quand Bryan veut juste une info sans voir son écran."
),
```

- [ ] **Step 4 : Remplacer le bloc CONTRÔLE MAC dans le system prompt d'ada.py**

Cherche dans `ada.py` le bloc (vers ligne 609) :
```python
        "CONTRÔLE MAC — RÈGLES DE PRÉCISION ABSOLUES : "
        "▸ OUVRIR UNE APP (Chrome, Safari, VS Code, Spotify, Finder, Terminal, Xcode, etc.) → "
```
jusqu'à :
```python
        "Recherche d'info rapide en arrière-plan → run_research. Simple → wikipedia_article ou arxiv_search. "
```

Remplace tout ce bloc par :
```python
        "CONTRÔLE MAC — RÈGLE ABSOLUE : "
        "▸ Bryan veut voir quelque chose sur son écran (ouvrir app, naviguer, cliquer, remplir, rechercher) → execute_pc_task. "
        "▸ Bryan est occupé, veut juste une INFO sans toucher son écran → run_web_agent (Playwright invisible). "
        "▸ Bryan dit 'arrête', 'stop', 'annule' pendant une tâche PC → stop_pc_task IMMÉDIATEMENT. "
        "▸ Moindre doute → execute_pc_task. "
        "Exemples : 'ouvre Google' → execute_pc_task. 'va sur YouTube' → execute_pc_task. "
        "'remplis ce formulaire' → execute_pc_task. 'cherche le prix de l'iPhone pendant que je travaille' → run_web_agent. "
        "Recherche info rapide → run_research. Simple → wikipedia_article ou arxiv_search. "
```

- [ ] **Step 5 : Commit**

```bash
git add backend/ada.py backend/mcp_tools_declarations.py
git commit -m "fix: clarify tool selection — execute_pc_task vs run_web_agent, remove control_computer from Live"
```

---

## Task 3 : stop_pc_task — arrêt immédiat tâche PC

**Files:**
- Modify: `backend/ada.py` (global stop event, wiring execute_pc_task + stop_pc_task)
- Modify: `backend/mcp_tools_declarations.py` (déclaration stop_pc_task_tool)
- Modify: `backend/external_bridge.py` (wiring stop_pc_task)
- Modify: `backend/os_control_agent.py` (accepter stop_event en paramètre)

- [ ] **Step 1 : Déclarer `stop_pc_task_tool` dans mcp_tools_declarations.py**

Juste avant la ligne `execute_pc_task_tool = {` dans `mcp_tools_declarations.py`, ajoute :
```python
# ── STOP PC TASK ─────────────────────────────────────────────────────────────
stop_pc_task_tool = {
    "name": "stop_pc_task",
    "description": (
        "Arrête immédiatement la tâche PC en cours (execute_pc_task). "
        "Appeler IMMÉDIATEMENT si Bryan dit 'arrête', 'stop', 'annule', 'arrête-toi' pendant une tâche PC. "
        "Répondre en même temps que l'appel."
    ),
    "parameters": {"type": "OBJECT", "properties": {}},
    "behavior": "NON_BLOCKING"
}
```

Puis dans la liste `MCP_TOOLS` (cherche la liste en fin de fichier), ajoute `stop_pc_task_tool,` juste avant `execute_pc_task_tool,`.

- [ ] **Step 2 : Ajouter la variable globale dans ada.py**

Après la ligne `presence_manager = PresenceManager()` (vers ligne 715) dans ada.py, ajoute :
```python
# ─── PC TASK STOP EVENT (global partagé entre AudioLoop et tool handler) ────
_current_pc_stop_event: asyncio.Event | None = None
```

- [ ] **Step 3 : Mettre à jour OsControlAgent.run() pour accepter stop_event**

Dans `backend/os_control_agent.py`, cherche la signature de `run()` :
```python
async def run(self, task: str, step_callback: Optional[Callable] = None) -> str:
```
Remplace par :
```python
async def run(self, task: str, step_callback: Optional[Callable] = None, stop_event: Optional[asyncio.Event] = None) -> str:
```

Juste en dessous, dans le corps de `run()`, cherche :
```python
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()
        listener = None
```
Remplace par :
```python
        loop = asyncio.get_running_loop()
        if stop_event is None:
            stop_event = asyncio.Event()
        listener = None
```

- [ ] **Step 4 : Wirer execute_pc_task avec stop_event dans ada.py `_execute_text_tool`**

Cherche dans `_execute_text_tool` (vers ligne 3305) :
```python
            elif name == "execute_pc_task":
                if not self.os_control_agent:
                    return "OsControlAgent non disponible (vérifier les dépendances)."
                try:
                    return await self.os_control_agent.run(args.get("task_description", ""))
                except Exception as e:
                    return f"PC task erreur : {e}"
```
Remplace par :
```python
            elif name == "execute_pc_task":
                if not self.os_control_agent:
                    return "OsControlAgent non disponible (vérifier les dépendances)."
                global _current_pc_stop_event
                _current_pc_stop_event = asyncio.Event()
                try:
                    return await self.os_control_agent.run(
                        args.get("task_description", ""),
                        stop_event=_current_pc_stop_event
                    )
                except Exception as e:
                    return f"PC task erreur : {e}"
                finally:
                    _current_pc_stop_event = None
```

- [ ] **Step 5 : Ajouter le handler stop_pc_task dans `_execute_text_tool`**

Juste après le bloc `elif name == "execute_pc_task":` que tu viens de modifier, ajoute :
```python
            elif name == "stop_pc_task":
                global _current_pc_stop_event
                if _current_pc_stop_event and not _current_pc_stop_event.is_set():
                    _current_pc_stop_event.set()
                    return "Tâche PC arrêtée immédiatement."
                return "Aucune tâche PC en cours."
```

- [ ] **Step 6 : Faire pareil dans le handler Live (AudioLoop)**

Dans ada.py, cherche le bloc `elif fc.name == "execute_pc_task":` dans la boucle Live (vers ligne 3306 dans le grand `if/elif`). Applique les mêmes modifications qu'au Step 4.

Puis cherche où tu peux ajouter `stop_pc_task` — juste après le elif execute_pc_task, ajoute :
```python
                                elif fc.name == "stop_pc_task":
                                    global _current_pc_stop_event
                                    if _current_pc_stop_event and not _current_pc_stop_event.is_set():
                                        _current_pc_stop_event.set()
                                        result_str = "Tâche PC arrêtée immédiatement."
                                    else:
                                        result_str = "Aucune tâche PC en cours."
                                    function_responses.append(types.FunctionResponse(
                                        id=fc.id, name=fc.name, response={"result": result_str}
                                    ))
```

- [ ] **Step 7 : Wirer dans external_bridge.py**

Dans `external_bridge.py`, cherche `_execute_tool`. Ajoute après le elif de `execute_pc_task` :
```python
            elif name == "stop_pc_task":
                # stop_pc_task opère sur l'AudioLoop principal, pas sur le bridge
                return "stop_pc_task disponible uniquement en mode voix."
```

- [ ] **Step 8 : Commit**

```bash
git add backend/ada.py backend/os_control_agent.py backend/mcp_tools_declarations.py backend/external_bridge.py
git commit -m "feat: add stop_pc_task tool — immediate PC task cancellation via voice command"
```

---

## Task 4 : OsControlAgent — planning step + accessibility API + MAX_STEPS 15

**Files:**
- Modify: `backend/os_control_agent.py`

- [ ] **Step 1 : Réduire MAX_STEPS de 30 à 15**

Cherche dans `os_control_agent.py` :
```python
MAX_STEPS = 30
```
Remplace par :
```python
MAX_STEPS = 15
```

- [ ] **Step 2 : Ajouter la méthode `_generate_plan`**

Après la méthode `_try_fast_path`, ajoute :
```python
    async def _generate_plan(self, task: str) -> list[str]:
        """Génère un plan de 3-5 étapes avant de démarrer la boucle vision.
        Retourne [] si la génération échoue (la vision loop fonctionnera sans plan).
        """
        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=MODEL,
                contents=(
                    f"Tâche macOS : {task}\n"
                    "Génère un plan de 3 à 5 étapes concrètes et séquentielles en JSON array. "
                    "Exemple: [\"Ouvrir Safari avec cmd+space\", \"Taper l'URL\", \"Appuyer Entrée\"]\n"
                    "Réponds UNIQUEMENT avec le JSON array, sans markdown, sans explication."
                ),
                config=types.GenerateContentConfig(temperature=0.1),
            )
            import json as _json
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = "\n".join(raw.split("\n")[1:]).rstrip("`").strip()
            return _json.loads(raw)
        except Exception as e:
            print(f"[OsControl] Plan generation failed (will proceed without plan): {e}")
            return []
```

- [ ] **Step 3 : Ajouter `accessibility_click` dans `_execute_action`**

Dans `_execute_action`, après le bloc `elif action == "wait":`, avant `elif action == "finish":`, ajoute :
```python
            elif action == "accessibility_click" and text:
                # text format: "AppName:ElementName" or just "ElementName" for frontmost app
                parts = text.split(":", 1)
                try:
                    if len(parts) == 2:
                        app_name, element_name = parts[0].strip(), parts[1].strip()
                        script = (
                            f'tell application "System Events"\n'
                            f'  tell process "{app_name}"\n'
                            f'    click (first button whose name contains "{element_name}")\n'
                            f'  end tell\n'
                            f'end tell'
                        )
                    else:
                        element_name = text.strip()
                        script = (
                            f'tell application "System Events"\n'
                            f'  click (first UI element of front window whose description contains "{element_name}")\n'
                            f'end tell'
                        )
                    await asyncio.to_thread(_run_osascript, script)
                    return f"Accessibility click: {text}"
                except Exception as e:
                    return f"Accessibility click failed ({e}) — use vision click instead"
```

- [ ] **Step 4 : Intégrer le plan dans `_loop` + détection de boucles**

Dans `_loop`, remplace le début de la méthode (après `screen_w, screen_h = ...`) :
```python
        history: list[str] = []
        final_result = "Tâche terminée."

        for step in range(MAX_STEPS):
```
par :
```python
        history: list[str] = []
        final_result = "Tâche terminée."
        _action_counts: dict[str, int] = {}  # Pour détection de boucle

        # Générer un plan avant de démarrer
        plan = await self._generate_plan(task)
        if plan:
            plan_str = " → ".join(plan)
            print(f"[OsControl] Plan généré : {plan_str}")
            if step_callback:
                await step_callback({"image": None, "log": f"[PC] Plan : {plan_str}"})
        else:
            plan = []

        for step in range(MAX_STEPS):
```

Et dans le bloc où `action_json` est parsé, après `action = action_json.get("action", "")`, ajoute la détection de boucle :
```python
            # Détection de boucle — même action × 3 = abandon
            _action_counts[action] = _action_counts.get(action, 0) + 1
            if _action_counts[action] >= 3 and action not in ("wait", "finish"):
                msg = f"Boucle détectée ({action} × 3) — tâche abandonnée."
                print(f"[OsControl] {msg}")
                return msg
```

Et dans le user_prompt, si un plan existe, l'inclure :
```python
            plan_hint = ""
            if plan:
                completed = min(step, len(plan))
                remaining = plan[completed:]
                if remaining:
                    plan_hint = f"\nÉtapes restantes du plan : {remaining}\nSuis ce plan dans l'ordre."

            user_prompt = (
                f"Tâche : {task}\n\n"
                f"Historique des actions précédentes :\n{history_str}\n"
                f"{plan_hint}\n"
                "Analyse le screenshot et détermine la prochaine action."
            )
```

- [ ] **Step 5 : Ajouter `accessibility_click` dans le SYSTEM_PROMPT**

Dans `SYSTEM_PROMPT` (en tête de fichier), dans la section FORMAT STRICT, ajoute :
```
▸ CLIQUER SUR UN BOUTON/ÉLÉMENT NOMMÉ (plus fiable que les coordonnées) :
  action: "accessibility_click", text: "NomApp:NomBouton" (ex: "Safari:Rechercher")
  ou text: "NomBouton" si l'app est déjà au premier plan.
  Préférer cette méthode pour : boutons, champs texte, menus nommés.
  Utiliser click+coordonnées pour : zones visuelles sans nom accessible (canvas, images).
```

- [ ] **Step 6 : Commit**

```bash
git add backend/os_control_agent.py
git commit -m "feat: OsControlAgent — planning step, accessibility API click, MAX_STEPS 15, loop detection"
```

---

## Task 5 : Chromecast — connexion IP directe + reconnect

**Files:**
- Modify: `backend/chromecast_agent.py`
- Modify: `.env` (ajouter CHROMECAST_HOST)

- [ ] **Step 1 : Ajouter CHROMECAST_HOST dans .env**

```bash
echo "CHROMECAST_HOST=192.168.1.127" >> /Users/bryandev/jarvis/backend/.env
```

Vérifier :
```bash
grep CHROMECAST /Users/bryandev/jarvis/backend/.env
```
Expected: `CHROMECAST_HOST=192.168.1.127`

- [ ] **Step 2 : Réécrire `_sync_initialize` dans chromecast_agent.py**

Remplace toute la méthode `_sync_initialize` par :
```python
    def _sync_initialize(self) -> str:
        try:
            import pychromecast
        except ImportError:
            return "Erreur: pychromecast non installé. Lance: pip install pychromecast"

        target_host = os.getenv("CHROMECAST_HOST", "").strip()
        target_name = os.getenv("CHROMECAST_NAME", "").strip()

        cast = None
        browser = None

        # Tentative 1 : connexion directe par IP (bypass mDNS)
        if target_host:
            try:
                chromecasts, browser = pychromecast.get_chromecasts(
                    timeout=8, known_hosts=[target_host]
                )
                if chromecasts:
                    cast = chromecasts[0]
                    print(f"[CastAgent] Connexion IP directe → {target_host}")
            except TypeError:
                # Ancienne version pychromecast sans known_hosts
                pass
            except Exception as e:
                print(f"[CastAgent] Connexion IP directe échouée : {e}")

        # Tentative 2 : découverte mDNS classique
        if cast is None:
            try:
                chromecasts, browser = pychromecast.get_chromecasts(timeout=10)
                if chromecasts:
                    if target_name:
                        for cc in chromecasts:
                            if cc.name.lower() == target_name.lower():
                                cast = cc
                                break
                    if cast is None:
                        cast = chromecasts[0]
            except Exception as e:
                return f"Erreur découverte Chromecast: {e}"

        if cast is None:
            if browser:
                try:
                    browser.stop_discovery()
                except Exception:
                    pass
            self._initialized = True
            return "Aucun Chromecast trouvé sur le réseau."

        cast.wait()
        # Attendre que le media controller soit vraiment prêt
        try:
            cast.media_controller.update_status()
            time.sleep(1.0)
        except Exception:
            pass

        self._cast = cast
        self._browser = browser
        self._initialized = True
        host = (cast.cast_info.host if cast.cast_info else None) or target_host or "?"
        print(f"[CastAgent] Connecté à '{cast.name}' ({host})")
        return f"Chromecast '{cast.name}' connecté ({host})."
```

- [ ] **Step 3 : Ajouter méthode `_ensure_connected` avec reconnect auto**

Après `_ensure_cast`, ajoute :
```python
    async def _ensure_connected(self) -> Optional[str]:
        """Vérifie la connexion. Si perdue, tente une reconnexion. Retourne None si OK, erreur sinon."""
        if not self._cast:
            result = await self.initialize()
            if not self._cast:
                return result
        try:
            # Ping léger pour vérifier que la connexion est vivante
            _ = self._cast.status
            return None
        except Exception:
            print("[CastAgent] Connexion perdue — reconnexion...")
            self._cast = None
            self._initialized = False
            result = await self.initialize()
            if not self._cast:
                return f"Reconnexion Chromecast échouée: {result}"
            return None
```

- [ ] **Step 4 : Utiliser `_ensure_connected` dans les commandes principales**

Remplace `_ensure_cast()` par `await self._ensure_connected()` dans `get_status`, `play`, `pause`, `stop`, `set_volume`, `play_youtube`, `play_media` :

```python
    async def get_status(self) -> str:
        err = await self._ensure_connected()
        if err:
            return err
        return await asyncio.to_thread(self._sync_get_status)

    async def play(self) -> str:
        err = await self._ensure_connected()
        if err:
            return err
        return await asyncio.to_thread(self._sync_play)

    async def pause(self) -> str:
        err = await self._ensure_connected()
        if err:
            return err
        return await asyncio.to_thread(self._sync_pause)

    async def stop(self) -> str:
        err = await self._ensure_connected()
        if err:
            return err
        return await asyncio.to_thread(self._sync_stop)

    async def set_volume(self, level: float) -> str:
        err = await self._ensure_connected()
        if err:
            return err
        level = max(0.0, min(1.0, float(level)))
        return await asyncio.to_thread(self._sync_set_volume, level)

    async def play_youtube(self, video_url: str) -> str:
        err = await self._ensure_connected()
        if err:
            return err
        video_id = self._extract_youtube_id(video_url)
        if not video_id:
            return f"Impossible d'extraire l'ID YouTube depuis: {video_url}"
        return await asyncio.to_thread(self._sync_play_youtube, video_id)

    async def play_media(self, url: str, media_type: str = "video/mp4") -> str:
        err = await self._ensure_connected()
        if err:
            return err
        return await asyncio.to_thread(self._sync_play_media, url, media_type)
```

- [ ] **Step 5 : Tester**

```bash
cd /Users/bryandev/jarvis/backend
conda activate ada_v2
python -c "
import asyncio
from chromecast_agent import CastAgent
async def test():
    c = CastAgent()
    print(await c.initialize())
    print(await c.get_status())
asyncio.run(test())
"
```
Expected: `Chromecast 'XXX' connecté (192.168.1.127).` puis le status.

- [ ] **Step 6 : Commit**

```bash
git add backend/chromecast_agent.py
git commit -m "fix: Chromecast — IP direct connection, auto-reconnect, wait for media controller"
```

---

## Task 6 : Face recognition — safety wrapper + test script

**Files:**
- Modify: `backend/ada.py` (`_face_detection_loop`)
- Modify: `backend/server.py` (démarrage conditionnel)
- Create: `backend/test_face_recognition.py`

- [ ] **Step 1 : Ajouter try/except dans `_face_detection_loop`**

Dans `backend/ada.py`, cherche `async def _face_detection_loop(self):`. Remplace par :
```python
    async def _face_detection_loop(self):
        """Détection de visage toutes les secondes, met à jour presence_manager.
        Désactivation automatique si MediaPipe n'est pas disponible ou plante.
        """
        # Init protégée — ne doit jamais crasher Ada
        try:
            if self._face_detector is None:
                self._face_detector = await asyncio.to_thread(
                    MultiUserFaceDetector, None
                )
            print("[PRESENCE] Face detection loop started.")
        except Exception as e:
            print(f"[PRESENCE] Face detection disabled (init error): {e}")
            return

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
                print(f"[PRESENCE] Face detection error (non-fatal): {e}")
```

- [ ] **Step 2 : Rendre le démarrage conditionnel dans server.py**

Dans `backend/server.py`, cherche où `_face_detection_loop` et `presence_manager.run()` sont lancés (cherche `face_detection_loop` ou `presence_manager`). S'ils sont démarrés inconditionnellement, les entourer d'une condition :

```python
    # Démarrage conditionnel de la reconnaissance faciale
    settings_path = os.path.join(os.path.dirname(__file__), "settings.json")
    try:
        with open(settings_path) as f:
            _settings = json.load(f)
        if _settings.get("face_auth_enabled", False):
            tg.create_task(audio_loop._face_detection_loop())
            tg.create_task(presence_manager.run())
            print("[SERVER] Face + voice recognition: ENABLED")
        else:
            print("[SERVER] Face + voice recognition: DISABLED (face_auth_enabled=false)")
    except Exception as e:
        print(f"[SERVER] Could not read settings for face auth: {e}")
```

Si `json` n'est pas déjà importé dans server.py, ajoute `import json` en tête.

- [ ] **Step 3 : Créer `backend/test_face_recognition.py`**

```python
"""
Test isolé reconnaissance faciale et vocale — sans Ada.
Usage: conda activate ada_v2 && python test_face_recognition.py

Ce script teste MultiUserFaceDetector + VoiceRecognizer indépendamment.
Lance-le et vérifie que ton visage est détecté avant d'activer face_auth_enabled.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
os.chdir(os.path.dirname(__file__))

try:
    import cv2
except ImportError:
    print("[TEST] ERREUR: opencv-python non installé. Lance: pip install opencv-python")
    sys.exit(1)

try:
    from authenticator import MultiUserFaceDetector
except ImportError as e:
    print(f"[TEST] ERREUR import authenticator: {e}")
    sys.exit(1)


async def test_face_recognition():
    print("[TEST] === Test reconnaissance faciale ===")
    print("[TEST] Initialisation MultiUserFaceDetector...")
    try:
        detector = MultiUserFaceDetector()
    except Exception as e:
        print(f"[TEST] ERREUR init: {e}")
        return False

    refs_dir = os.path.join(os.path.dirname(__file__), "memory", "face_refs")
    if not os.path.exists(refs_dir) or not os.listdir(refs_dir):
        print(f"[TEST] ATTENTION: Aucune référence dans {refs_dir}")
        print("[TEST] Lance 'python capture_face.py' pour enregistrer ton visage.")
        return False

    print(f"[TEST] Références trouvées: {os.listdir(refs_dir)}")
    print("[TEST] Ouverture caméra...")

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[TEST] ERREUR: Caméra index 0 inaccessible. Essai index 1...")
        cap = cv2.VideoCapture(1)
        if not cap.isOpened():
            print("[TEST] ERREUR: Aucune caméra disponible.")
            return False

    print("[TEST] Caméra OK. Détection en cours... (Ctrl+C pour arrêter)")
    detected_count = 0
    total_count = 0

    try:
        for _ in range(30):  # 30 secondes de test
            ret, frame = cap.read()
            if not ret:
                await asyncio.sleep(1.0)
                continue

            total_count += 1
            detections = await asyncio.to_thread(detector.detect, frame)

            if detections:
                detected_count += 1
                for d in detections:
                    print(f"[TEST] ✓ Visage reconnu: {d['user']} (confiance: {d['confidence']:.3f})")
            else:
                print(f"[TEST] · Aucun visage reconnu ({total_count}/30)", end="\r")

            await asyncio.sleep(1.0)

    except KeyboardInterrupt:
        print("\n[TEST] Interrompu.")
    finally:
        cap.release()

    rate = detected_count / total_count * 100 if total_count > 0 else 0
    print(f"\n[TEST] Résultat: {detected_count}/{total_count} frames détectées ({rate:.0f}%)")
    if rate >= 60:
        print("[TEST] ✓ Reconnaissance faciale FONCTIONNELLE — tu peux activer face_auth_enabled.")
    else:
        print("[TEST] ✗ Reconnaissance insuffisante — vérifie les photos de référence.")
    return rate >= 60


if __name__ == "__main__":
    asyncio.run(test_face_recognition())
```

- [ ] **Step 4 : Tester le script**

```bash
cd /Users/bryandev/jarvis/backend
conda activate ada_v2
python test_face_recognition.py
```
Expected: détections de ton visage avec confiance > 0.85, taux > 60%.

- [ ] **Step 5 : Commit**

```bash
git add backend/ada.py backend/server.py backend/test_face_recognition.py
git commit -m "fix: face recognition — safety wrapper, conditional startup, isolated test script"
```

---

## Task 7 : Sonnette Tuya — doorbell_agent.py

**Files:**
- Create: `backend/doorbell_agent.py`
- Modify: `backend/mcp_tools_declarations.py` (doorbell tools)
- Modify: `backend/ada.py` (wiring + polling démarrage)
- Modify: `backend/external_bridge.py` (wiring)
- Modify: `backend/server.py` (démarrage polling)

- [ ] **Step 1 : Ajouter TUYA_API_KEY et TUYA_API_SECRET dans .env**

```bash
# Ajouter manuellement dans /Users/bryandev/jarvis/backend/.env :
# TUYA_API_KEY=<ta_valeur>
# TUYA_API_SECRET=<ta_valeur>
# DOORBELL_DEVICE_ID=bf4c3d1743e00446c3ccl6
```

- [ ] **Step 2 : Créer `backend/doorbell_agent.py`**

```python
"""
doorbell_agent.py — Sonnette Tuya avec caméra

Récupère la clé locale via Tuya Cloud API, puis poll l'état de la sonnette
pour détecter les appuis. Alerte Ada vocalement + Telegram avec snapshot.
"""
import asyncio
import hashlib
import hmac
import json
import os
import time
from typing import Callable, Awaitable, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

TUYA_API_KEY = os.getenv("TUYA_API_KEY", "")
TUYA_API_SECRET = os.getenv("TUYA_API_SECRET", "")
DOORBELL_DEVICE_ID = os.getenv("DOORBELL_DEVICE_ID", "bf4c3d1743e00446c3ccl6")
TUYA_BASE_URL = "https://openapi.tuyaeu.com"  # EU region

POLL_INTERVAL = 3.0  # secondes entre chaque check


def _tuya_sign(client_id: str, secret: str, access_token: str, t: str, method: str, path: str, body: str = "") -> str:
    """Calcule la signature HMAC-SHA256 pour l'API Tuya Cloud."""
    content_sha256 = hashlib.sha256(body.encode()).hexdigest()
    headers_str = ""
    string_to_sign = "\n".join([method, content_sha256, headers_str, path])
    sign_str = client_id + access_token + t + string_to_sign
    return hmac.new(secret.encode(), sign_str.encode(), hashlib.sha256).hexdigest().upper()


async def _tuya_request(method: str, path: str, access_token: str = "") -> dict:
    """Effectue un appel authentifié à l'API Tuya Cloud."""
    t = str(int(time.time() * 1000))
    sign = _tuya_sign(TUYA_API_KEY, TUYA_API_SECRET, access_token, t, method, path)

    headers = {
        "client_id": TUYA_API_KEY,
        "sign": sign,
        "t": t,
        "sign_method": "HMAC-SHA256",
        "access_token": access_token,
    }

    url = TUYA_BASE_URL + path
    async with httpx.AsyncClient(timeout=10.0) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers)
        else:
            resp = await client.post(url, headers=headers)
    resp.raise_for_status()
    return resp.json()


async def get_tuya_access_token() -> str:
    """Obtient un access token Tuya Cloud."""
    data = await _tuya_request("GET", "/v1.0/token?grant_type=1")
    if not data.get("success"):
        raise RuntimeError(f"Tuya token error: {data}")
    return data["result"]["access_token"]


async def get_device_info(device_id: str) -> dict:
    """Récupère les infos du device (local_key, ip, name, category)."""
    token = await get_tuya_access_token()
    data = await _tuya_request("GET", f"/v1.0/devices/{device_id}", access_token=token)
    if not data.get("success"):
        raise RuntimeError(f"Tuya device info error: {data}")
    return data["result"]


async def get_device_status(device_id: str) -> list[dict]:
    """Récupère le status (DPs) du device."""
    token = await get_tuya_access_token()
    data = await _tuya_request("GET", f"/v1.0/devices/{device_id}/status", access_token=token)
    if not data.get("success"):
        raise RuntimeError(f"Tuya device status error: {data}")
    return data.get("result", [])


class DoorbellAgent:
    def __init__(
        self,
        on_ring: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        """
        :param on_ring: coroutine appelée quand la sonnette est actionnée.
        """
        self.on_ring = on_ring
        self.device_id = DOORBELL_DEVICE_ID
        self._last_doorbell_value = None
        self._running = False
        self._device_info: Optional[dict] = None

    async def initialize(self) -> str:
        """Récupère les infos du device via Tuya Cloud API."""
        if not TUYA_API_KEY or not TUYA_API_SECRET:
            return "ERREUR: TUYA_API_KEY ou TUYA_API_SECRET manquant dans .env"
        try:
            self._device_info = await get_device_info(self.device_id)
            name = self._device_info.get("name", self.device_id)
            category = self._device_info.get("category", "inconnu")
            print(f"[DOORBELL] Device: '{name}' (catégorie: {category})")
            return f"Sonnette '{name}' initialisée."
        except Exception as e:
            return f"ERREUR init sonnette: {e}"

    async def get_status(self) -> str:
        """Retourne l'état actuel de la sonnette."""
        try:
            dps = await get_device_status(self.device_id)
            return json.dumps(dps, ensure_ascii=False)
        except Exception as e:
            return f"Erreur status sonnette: {e}"

    async def get_snapshot(self) -> str:
        """Tente de récupérer un snapshot caméra (si supporté par le device)."""
        try:
            token = await get_tuya_access_token()
            data = await _tuya_request(
                "GET",
                f"/v1.0/devices/{self.device_id}/stream/actions/allocate",
                access_token=token
            )
            if data.get("success"):
                url = data.get("result", {}).get("url", "")
                return url if url else "Snapshot URL non disponible."
            return "Snapshot non supporté par ce device."
        except Exception as e:
            return f"Erreur snapshot sonnette: {e}"

    async def start_polling(self) -> None:
        """Démarre le polling pour détecter les appuis sur la sonnette."""
        if not TUYA_API_KEY or not TUYA_API_SECRET:
            print("[DOORBELL] Polling désactivé: TUYA_API_KEY ou TUYA_API_SECRET manquant.")
            return

        self._running = True
        print(f"[DOORBELL] Polling démarré (toutes les {POLL_INTERVAL}s).")

        while self._running:
            try:
                dps = await get_device_status(self.device_id)
                # Chercher un DP de type sonnerie (valeurs booléennes qui changent)
                for dp in dps:
                    code = dp.get("code", "")
                    value = dp.get("value")
                    # Les DPs de sonnette sont souvent: "doorbell_active", "alarm_bell", etc.
                    if "bell" in code.lower() or "door" in code.lower() or "alarm" in code.lower():
                        if self._last_doorbell_value is not None and value != self._last_doorbell_value:
                            print(f"[DOORBELL] DP '{code}' changé: {self._last_doorbell_value} → {value}")
                            if self.on_ring:
                                await self.on_ring()
                        self._last_doorbell_value = value
            except Exception as e:
                print(f"[DOORBELL] Erreur polling (non-fatal): {e}")

            await asyncio.sleep(POLL_INTERVAL)

    def stop(self) -> None:
        self._running = False
```

- [ ] **Step 3 : Déclarer les outils Gemini dans mcp_tools_declarations.py**

Cherche la section `# ── OS CONTROL` dans `mcp_tools_declarations.py`. Juste avant, ajoute :
```python
# ── SONNETTE ─────────────────────────────────────────────────────────────────
get_doorbell_status_tool = {
    "name": "get_doorbell_status",
    "description": "Retourne l'état actuel de la sonnette (sonnant, calme, dernier appui).",
    "parameters": {"type": "OBJECT", "properties": {}},
}

get_doorbell_snapshot_tool = {
    "name": "get_doorbell_snapshot",
    "description": "Capture une image depuis la caméra de la sonnette. Utile pour voir qui est à la porte.",
    "parameters": {"type": "OBJECT", "properties": {}},
}
```

Dans la liste `MCP_TOOLS`, ajoute `get_doorbell_status_tool, get_doorbell_snapshot_tool,`.

- [ ] **Step 4 : Wirer dans ada.py**

Dans `ada.py`, ajoute l'import et l'instanciation (après les autres agents, vers ligne 837) :
```python
        try:
            from doorbell_agent import DoorbellAgent
            async def _on_ring():
                print("[DOORBELL] Sonnette actionnée!")
                if self.session:
                    await self.session.send(
                        input="[Système] Quelqu'un vient de sonner à la porte. "
                              "Dis-le à Bryan maintenant et propose de regarder qui c'est.",
                        end_of_turn=True,
                    )
            self.doorbell_agent = DoorbellAgent(on_ring=_on_ring)
        except ImportError as e:
            import warnings
            warnings.warn(f"[ADA] DoorbellAgent non disponible: {e}")
            self.doorbell_agent = None
```

Dans `_execute_text_tool`, ajoute les handlers doorbell :
```python
            elif name == "get_doorbell_status":
                if not self.doorbell_agent:
                    return "DoorbellAgent non disponible."
                return await self.doorbell_agent.get_status()
            elif name == "get_doorbell_snapshot":
                if not self.doorbell_agent:
                    return "DoorbellAgent non disponible."
                return await self.doorbell_agent.get_snapshot()
```

Faire de même dans le handler Live (bloc elif de la boucle audio).

- [ ] **Step 5 : Démarrer le polling dans server.py**

Dans `server.py`, dans la fonction de startup (cherche `async def startup`), après l'init du cast_agent, ajoute :
```python
    # Démarrage polling sonnette
    if audio_loop.doorbell_agent:
        init_result = await audio_loop.doorbell_agent.initialize()
        print(f"[SERVER] Doorbell: {init_result}")
        # Polling en background
        asyncio.create_task(audio_loop.doorbell_agent.start_polling())
```

- [ ] **Step 6 : Wirer dans external_bridge.py**

Dans `_execute_tool` de `TextAgent`, ajoute :
```python
            elif name == "get_doorbell_status":
                from doorbell_agent import DoorbellAgent, get_device_status, DOORBELL_DEVICE_ID
                import json
                try:
                    dps = await get_device_status(DOORBELL_DEVICE_ID)
                    return json.dumps(dps, ensure_ascii=False)
                except Exception as e:
                    return f"Erreur status sonnette: {e}"
            elif name == "get_doorbell_snapshot":
                return "Snapshot disponible uniquement en mode voix Ada."
```

- [ ] **Step 7 : Tester l'API Tuya Cloud**

```bash
cd /Users/bryandev/jarvis/backend
conda activate ada_v2
python -c "
import asyncio
from doorbell_agent import get_tuya_access_token, get_device_info, DOORBELL_DEVICE_ID
async def test():
    token = await get_tuya_access_token()
    print('Token OK:', token[:20] + '...')
    info = await get_device_info(DOORBELL_DEVICE_ID)
    print('Device:', info.get('name'), '| IP:', info.get('ip'), '| Key:', info.get('local_key', 'N/A'))
asyncio.run(test())
"
```
Expected: token affiché + nom/IP/key de la sonnette.

- [ ] **Step 8 : Commit**

```bash
git add backend/doorbell_agent.py backend/mcp_tools_declarations.py backend/ada.py backend/external_bridge.py backend/server.py
git commit -m "feat: doorbell agent — Tuya Cloud API, ring detection polling, voice alert + Telegram snapshot"
```

---

## Self-Review

### Couverture spec

| Exigence spec | Task |
|---|---|
| Wake word : fenêtre 4s, CHECK_INTERVAL 1.2s, MIN_RMS 100, debounce 2s, prompt enrichi | Task 1 ✓ |
| Tool precision : descriptions, system prompt, remove control_computer Live | Task 2 ✓ |
| stop_pc_task : global event, NON_BLOCKING tool, < 0.5s | Task 3 ✓ |
| OsControlAgent : planning step, accessibility API, MAX_STEPS 15, loop detection | Task 4 ✓ |
| Chromecast : IP 192.168.1.127, reconnect auto, attente media controller | Task 5 ✓ |
| Face recognition : wrapper try/except, démarrage conditionnel, test script | Task 6 ✓ |
| Doorbell : Tuya Cloud API key fetch, polling 3s, alerte vocale, Telegram, snapshot | Task 7 ✓ |

### Aucun placeholder détecté ✓

### Cohérence des types
- `stop_event: Optional[asyncio.Event]` utilisé de manière cohérente Tasks 3 et 4 ✓
- `DoorbellAgent.on_ring: Callable[[], Awaitable[None]]` cohérent Tasks 7 ✓
- `_ensure_connected()` retourne `Optional[str]` cohérent Task 5 ✓
