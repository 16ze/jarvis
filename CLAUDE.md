# Jarvis / Ada — Contexte projet

## Structure
- `backend/ada.py` — AudioLoop principal (mode voix, Live API Gemini)
- `backend/external_bridge.py` — TextAgent pour Telegram/WhatsApp
- `backend/server.py` — FastAPI + Socket.IO
- `backend/self_correction_agent.py` — Agent Claude Opus 4.6 auto-correction
- `backend/mcps/` — Connecteurs externes (GitHub, Telegram, Slack, etc.)
- `backend/mcp_tools_declarations.py` — Déclarations Gemini des outils MCP

## Conventions
- Tous les outils retournent une `str` (jamais d'exceptions non catchées)
- Nouveaux outils : déclarer dans `mcp_tools_declarations.py` ET wirer dans `_execute_text_tool` (ada.py) ET `TextAgent._execute_tool` (external_bridge.py)
- Outils jarvis_* : path toujours validé contre JARVIS_ROOT avant toute opération
- Backup git automatique avant toute `jarvis_write_file`

## Env vars requises
- GEMINI_API_KEY, ANTHROPIC_API_KEY
- TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- GITHUB_TOKEN, GITHUB_DEFAULT_REPO=16ze/jarvis
