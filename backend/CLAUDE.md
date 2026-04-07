# Ada — Architecture & Guide de débogage rapide

> Ce fichier est lu par Ada elle-même (via `jarvis_read_file`) et par Claude Code pour tout debug ou évolution.
> **Règle absolue** : mettre à jour ce fichier après toute modification structurelle.

---

## Identité

- **Nom** : Ada — Advanced Design Assistant
- **Créée par** : Bryan Hilaire (Kairo Digital)
- **Modèle voix** : `gemini-2.5-flash-native-audio-preview-12-2025` (Live API Gemini)
- **Modèle texte (bridge)** : `gemini-2.5-flash`
- **Auto-correction** : Gemini 2.5 Flash (`self_correction_agent.py`) — gratuit, zéro coût Anthropic
- **Langue** : Français exclusivement — même les résultats d'outils en anglais sont traduits

---

## Architecture — vue d'ensemble

```
frontend/          ← Interface React (3D, visualisation)
backend/
  server.py        ← FastAPI + Socket.IO — point d'entrée principal
  ada.py           ← AudioLoop (mode voix Live API Gemini)
  external_bridge.py ← TextAgent Telegram/WhatsApp (long-polling)
  memory_manager.py  ← Mémoire persistante (ChromaDB + JSON)
  self_correction_agent.py ← Claude Opus 4.6, auto-correction code
  mcp_tools_declarations.py ← Déclarations Gemini de tous les outils MCP
  tools.py         ← Outils de base (terminal, fichiers, etc.)
  mcps/            ← Connecteurs externes (un fichier par service)
  memory/          ← ChromaDB + JSON (persisté sur disque)
    chroma/        ← Base vectorielle (conversations, entités, documents)
    procedural.json ← Profil de Bryan (préférences, habitudes, objectifs)
    last_session.json ← Ring buffer 30 échanges de la session courante
    documents/     ← Fichiers originaux ingérés en RAG
```

---

## Fichiers critiques — ce qu'ils font

| Fichier | Rôle |
|---|---|
| `server.py` | Lance FastAPI + Socket.IO, monte `ada.AudioLoop`, `external_bridge.TextAgent`, route les endpoints HTTP |
| `ada.py` | Classe `AudioLoop` — boucle principale voix (micro → Gemini Live → speaker), gère tous les function calls |
| `external_bridge.py` | Classe `TextAgent` — reçoit messages Telegram/WhatsApp, exécute les outils, répond en texte ou note vocale OGG |
| `memory_manager.py` | 4 types de mémoire : vectorielle (ChromaDB), entités (ChromaDB), procédurale (JSON), documents RAG (ChromaDB) |
| `mcp_tools_declarations.py` | Source de vérité des déclarations d'outils Gemini — **tout nouvel outil doit y être ajouté** |
| `self_correction_agent.py` | Gemini 2.5 Flash — lit/corrige/écrit des fichiers Python dans `JARVIS_ROOT` avec backup git automatique |

---

## Convention — ajouter un nouvel outil

**3 endroits obligatoires :**

1. `mcp_tools_declarations.py` — déclarer le schéma Gemini (nom, description, paramètres)
2. `ada.py` → `_execute_text_tool()` — wirer le `elif name == "mon_outil"`
3. `external_bridge.py` → `TextAgent._execute_tool()` — wirer pareil

Si l'outil est déclaré mais pas wiré dans l'un des deux agents → silencieusement ignoré.

---

## Outils disponibles — inventaire rapide

### Outils de base (tools.py + ada.py)
- `run_terminal` — shell Mac
- `run_web_agent` — navigateur Chromium visible
- `control_computer` — clic/frappe/scroll
- `read_emails`, `send_email`, `get_email_body`
- `list_events`, `create_event`, `find_event`, `delete_event`
- `generate_cad`, `iterate_cad`, `print_stl`, `discover_printers`, `get_print_status`
- `run_research`, `run_task`, `anticipate`, `start_monitoring`, `stop_monitoring`
- `create_project`, `switch_project`, `list_projects`
- `list_smart_devices`, `control_light`
- `search_memory`, `remember`, `search_documents`

### Outils mémoire & fichiers (self_correction_agent.py)
- `jarvis_read_file` — lit un fichier dans le repo (scopé à JARVIS_ROOT)
- `jarvis_write_file` — écrit avec backup git automatique avant
- `jarvis_list_files` — liste récursive
- `jarvis_git_commit` — commit git avec message
- `self_correct_file` — passe le fichier + description d'erreur à Claude Opus

### MCP — services externes (mcps/)
| Préfixe | Service | Fichier |
|---|---|---|
| `github_*` | GitHub API | `mcps/github_mcp.py` |
| `telegram_*` | Telegram Bot | `mcps/telegram_mcp.py` |
| `slack_*` | Slack | `mcps/slack_mcp.py` |
| `notion_*` | Notion | `mcps/notion_mcp.py` |
| `drive_*`, `sheets_*`, `docs_*` | Google Drive/Sheets/Docs | `mcps/drive_mcp.py` |
| `linear_*` | Linear | `mcps/linear_mcp.py` |
| `stripe_*` | Stripe | `mcps/stripe_mcp.py` |
| `qonto_*` | Qonto | `mcps/qonto_mcp.py` |
| `supabase_*` | Supabase | `mcps/supabase_mcp.py` |
| `vercel_*` | Vercel | `mcps/vercel_mcp.py` |
| `docker_*` | Docker | `mcps/docker_mcp.py` |
| `ha_*` | Home Assistant | `mcps/homeassistant_mcp.py` |
| `spotify_*` | Spotify | `mcps/spotify_mcp.py` |
| `youtube_*` | YouTube | `mcps/youtube_mcp.py` |
| `wikipedia_*` | Wikipedia | `mcps/wikipedia_mcp.py` |
| `arxiv_*` | ArXiv | `mcps/arxiv_mcp.py` |
| `maps_*` | Google Maps | `mcps/googlemaps_mcp.py` |
| `health_*` | Apple Health | `mcps/applehealth_mcp.py` |
| `canva_*` | Canva | `mcps/canva_mcp.py` |
| `figma_*` | Figma | `mcps/figma_mcp.py` |
| `elevenlabs_*` | ElevenLabs TTS | `mcps/elevenlabs_mcp.py` |
| `replicate_*` | Replicate (images) | `mcps/replicate_mcp.py` |
| `whatsapp_*` | WhatsApp (Evolution API) | `mcps/whatsapp_mcp.py` |

---

## Mémoire — comment ça marche

```
MemoryManager (memory_manager.py)
├── conversations  (ChromaDB) — recherche sémantique via search_memory
├── entities       (ChromaDB) — personnes/projets via search_entities / get_entity
├── documents      (ChromaDB) — RAG fichiers via search_documents
└── procedural.json           — profil Bryan (préférences, habitudes, objectifs, faits)

Démarrage : get_startup_context() génère un bloc [MÉMOIRE] injecté en tête de session
Session en cours : append_to_session() — ring buffer 30 échanges (last_session.json)
Fin de session : clear_session() — archive dans ChromaDB puis efface last_session.json
```

**Problème connu** : Ada ne sait pas automatiquement quels bugs ont été résolus dans les sessions précédentes. Pour le savoir, lire `../.claude/agent-memory/debugger/MEMORY.md`.

---

## Problèmes connus & statut

| Problème | Statut | Fichier concerné |
|---|---|---|
| Spotify — auth bloquante (`prompt_for_user_token` nécessite TTY interactif) | **Résolu** — SpotifyOAuth + endpoints `/spotify/auth` et `/spotify/callback` | `mcps/spotify_mcp.py`, `server.py` |
| Rappels/Reminders temporels | **Résolu** — `reminder_manager.py` + outils `reminder_set/list/delete` | `reminder_manager.py`, `ada.py`, `external_bridge.py` |
| Compréhension contextuelle fichiers (analyse sémantique, pas juste lecture brute) | **Partiel** — RAG documents OK, mais fichiers filesystem sans résumé | — |
| Double dispatch Spotify dans ada.py (lignes ~2030 et ~2742) | **À nettoyer** | `ada.py` |
| Mode veille (pause + wake word) | **Résolu** — `ada_sleep` / `ada_wake` tools + `sleep_mode` flag | `ada.py`, `mcp_tools_declarations.py`, `server.py` |

---

## Variables d'environnement requises

```bash
# IA
GEMINI_API_KEY=
ANTHROPIC_API_KEY=

# Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# GitHub
GITHUB_TOKEN=
GITHUB_DEFAULT_REPO=16ze/jarvis

# Sécurité API
ADA_API_TOKEN=

# Optionnels (MCP)
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
SPOTIFY_USERNAME=
SLACK_BOT_TOKEN=
NOTION_API_KEY=
LINEAR_API_KEY=
STRIPE_SECRET_KEY=
QONTO_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
VERCEL_TOKEN=
GOOGLE_MAPS_API_KEY=
ELEVENLABS_API_KEY=
REPLICATE_API_TOKEN=
HOME_ASSISTANT_URL=
HOME_ASSISTANT_TOKEN=
WHATSAPP_API_URL=
WHATSAPP_API_KEY=
WHATSAPP_INSTANCE=ada
```

---

## Débogage rapide — recettes

### Ada ne répond plus en voix
1. Vérifier que `GEMINI_API_KEY` est valide
2. Vérifier que le modèle `gemini-2.5-flash-native-audio-preview-12-2025` est accessible
3. Chercher `[ADA]` dans les logs — l'AudioLoop log toutes ses erreurs avec ce préfixe

### Un outil ne fonctionne pas
1. Vérifier qu'il est dans `mcp_tools_declarations.py` (liste `MCP_TOOLS`)
2. Vérifier qu'il est wiré dans `ada.py` → bloc `elif n == "nom_outil"`
3. Vérifier qu'il est wiré dans `external_bridge.py` → `TextAgent._execute_tool()`
4. Vérifier que la variable d'environnement correspondante est définie

### Mémoire vide au démarrage
1. Vérifier que `backend/memory/chroma/` existe et est non vide
2. Vérifier que `backend/memory/procedural.json` existe
3. Appeler `memory.get_startup_context()` manuellement en Python pour tester

### Spotify — "non autorisé" au premier lancement
1. Visiter `http://localhost:8000/spotify/auth` → récupérer l'URL
2. Ouvrir l'URL dans le navigateur → autoriser l'accès
3. Spotify redirige vers `http://localhost:8000/spotify/callback?code=...` → token mis en cache automatiquement
4. Le token est persisté dans `backend/.spotify_token` — l'autorisation survit aux redémarrages
5. Variables requises : `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI=http://localhost:8000/spotify/callback`

### Telegram ne répond plus
1. Vérifier `TELEGRAM_BOT_TOKEN` et `TELEGRAM_CHAT_ID`
2. Le TextAgent utilise le long-polling — s'il crashe, il ne redémarre pas automatiquement
3. Chercher `[BRIDGE]` dans les logs

### SelfCorrectionAgent échoue
1. Vérifier `GEMINI_API_KEY` — tester avec `python -c "from google import genai; print('ok')"`
2. Le chemin du fichier doit être absolu et sous `/Users/bryandev/jarvis`
3. Le backup git est automatique avant toute écriture — vérifier `git log` pour confirmer

---

## Démarrage du serveur

```bash
cd /Users/bryandev/jarvis/backend
python server.py
# ou
uvicorn server:app_socketio --host 0.0.0.0 --port 8000
```

Le serveur expose :
- `ws://` Socket.IO — communication temps réel avec le frontend
- `POST /upload` — ingestion de documents (RAG)
- `GET /memory/documents` — liste des documents
- `DELETE /memory/documents/{filename}` — suppression
- `POST /authenticate` — auth faciale
