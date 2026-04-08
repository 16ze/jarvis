# Jarvis / Ada — Contexte projet complet

## Vue d'ensemble
Assistant personnel IA basé sur **Google Gemini 2.5 Flash Native Audio** (voix Kore).
Mode voix via Live API + mode texte via Telegram/WhatsApp (external_bridge).
Propriétaire : Bryan Hilaire / Kairo Digital — repo : github.com/16ze/jarvis

---

## Architecture générale

```
┌─────────────────────────────────────────────────────────┐
│                      ada.py                             │
│          AudioLoop — orchestrateur principal            │
│   Gemini 2.5 Flash Native Audio (models/gemini-2.5-     │
│   flash-native-audio-preview-12-2025), voix Kore        │
│   Écoute micro → envoie audio → reçoit audio+texte      │
└────────────────────┬────────────────────────────────────┘
                     │ tool_calls
        ┌────────────┼─────────────────────────┐
        │            │                         │
   Agents locaux   MCP tools            Agents asyncio
   (tools.py)   (mcp_tools_          (research_agent.py,
                declarations.py)      task_agent.py,
                                      anticipation_agent.py,
                                      monitoring_agent.py)
        │
  ┌─────┴──────┐
  │server.py   │  FastAPI + Socket.IO — UI web + remote control
  └────────────┘

external_bridge.py → TextAgent → Telegram / WhatsApp (Evolution API)
self_correction_agent.py → Claude Opus 4.6 — auto-correction des erreurs
```

---

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `backend/ada.py` | AudioLoop principal, Live API Gemini, wiring de tous les tools |
| `backend/external_bridge.py` | TextAgent pour Telegram + WhatsApp, seuil TEXT_VOICE_THRESHOLD |
| `backend/server.py` | FastAPI + Socket.IO, endpoints REST, WebSocket UI |
| `backend/self_correction_agent.py` | Agent Claude Opus 4.6, auto-correction sur erreur outil |
| `backend/mcp_tools_declarations.py` | Déclarations Gemini (format OBJECT) de tous les outils MCP |
| `backend/tools.py` | tools_list — outils locaux non-MCP déclarés pour Gemini |
| `backend/memory_manager.py` | ChromaDB — mémoire vectorielle RAG persistante |
| `backend/authenticator.py` | MediaPipe face recognition — authentification visage |
| `backend/reminder_manager.py` | Gestionnaire de rappels persistants |

### Agents spécialisés

| Agent | Fichier | Pattern |
|---|---|---|
| Web | `web_agent.py` | Playwright async |
| CAD | `cad_agent.py` | build123d + OrcaSlicer |
| Imprimante 3D | `printer_agent.py` | Moonraker API |
| Smart home | `tuya_agent.py` | tinytuya async (remplace kasa_agent.py) |
| Google (Gmail/Cal/Drive) | `google_agent.py` | OAuth2 google_token.json |
| Projets | `project_manager.py` | Gestion dossiers locaux |
| Recherche | `research_agent.py` | asyncio/Gemini pur |
| Tâches | `task_agent.py` | asyncio/Gemini pur |
| Anticipation | `anticipation_agent.py` | asyncio/Gemini pur |
| Monitoring | `monitoring_agent.py` | asyncio/Gemini pur |

### Connecteurs MCP (`backend/mcps/`)

GitHub, Telegram, Slack, WhatsApp, Spotify, Google Maps, Drive, YouTube,
Notion, Linear, Canva, Figma, Stripe, Supabase, Vercel, Docker, Arxiv,
Wikipedia, Replicate, Qonto, Apple Health, Home Assistant

---

## Flux de données — ajouter un nouvel agent

**Checklist obligatoire (dans cet ordre) :**

1. Créer `backend/<nom>_agent.py` — classe async avec méthode principale `async def run(self, prompt: str) -> str`
2. Déclarer le tool dans `backend/mcp_tools_declarations.py` — format `{"name": "...", "description": "...", "parameters": {"type": "OBJECT", ...}}`
3. Wirer dans `backend/ada.py` — ajouter dans `_execute_text_tool()` ET dans la liste `tools` du config Gemini
4. Wirer dans `backend/external_bridge.py` — ajouter dans `TextAgent._execute_tool()`
5. Ajouter les env vars nécessaires dans `.env.example`
6. Tester en isolation avant d'intégrer

---

## Conventions absolues

- Tous les outils retournent une `str` — jamais d'exceptions non catchées
- Outils `jarvis_*` : path toujours validé contre `JARVIS_ROOT` avant toute opération
- Backup git automatique avant toute `jarvis_write_file`
- Pattern tool call : `async def _execute_tool(name, args) -> str` — switch/case sur le nom
- `TEXT_VOICE_THRESHOLD` dans external_bridge.py — sous le seuil = texte, au-dessus = OGG voice note

---

## Variables d'environnement requises

```bash
# IA
GEMINI_API_KEY=
ANTHROPIC_API_KEY=

# Messaging
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
WHATSAPP_EVOLUTION_API_URL=
WHATSAPP_EVOLUTION_API_KEY=
WHATSAPP_INSTANCE=

# GitHub
GITHUB_TOKEN=
GITHUB_DEFAULT_REPO=16ze/jarvis

# Smart home
TUYA_API_KEY=
TUYA_API_SECRET=
TUYA_API_REGION=eu

# Google OAuth2
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
# token stocké dans backend/google_token.json (compte adaai.bryan@gmail.com)

# Spotify
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=

# Chromecast
CHROMECAST_HOST=  # IP du Chromecast local

# Infra
JARVIS_ROOT=/Users/bryandev/jarvis
```

---

## Règles absolues — voir `.claude/rules/`

- **Jamais LangGraph** ni framework agent lourd — asyncio pur uniquement
- **Jamais ElevenLabs** — Gemini Native Audio uniquement pour la voix
- **Jamais localtuya** — tinytuya uniquement pour le smart home
- Tout agent suit le pattern asyncio/Gemini existant
- Confirmations obligatoires avant actions irréversibles (email envoyé, suppression)
- Credentials dans `.env` uniquement — jamais dans le code

---

## Infra cible

- **Hetzner VPS** — Ubuntu 22.04
- **PM2** — process manager, auto-restart, logs
- **Cloudflare Tunnel** — exposition HTTPS sans port ouvert (même config que n8n)
- **Conda** — environnement `ada_v2` (Python 3.11)
