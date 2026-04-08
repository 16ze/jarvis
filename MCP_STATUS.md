# MCP Status — Ada / Jarvis

> Mis à jour: 2026-04-02

## Légende
- ✅ Prêt — code implémenté, config dans `.env`
- ⚙️ Config manuelle requise — API key ou OAuth à configurer
- 📦 Dépendance à installer — `pip install <package>`

---

## COMMUNICATION

| MCP | Fichier | Variables requises | Dépendances | Statut |
|-----|---------|-------------------|-------------|--------|
| Slack | `mcps/slack_mcp.py` | `SLACK_BOT_TOKEN` | `slack_sdk` | ⚙️ 📦 |
| Telegram | `mcps/telegram_mcp.py` | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | `httpx` | ⚙️ |
| WhatsApp | `mcps/whatsapp_mcp.py` | `WHATSAPP_API_URL`, `WHATSAPP_API_KEY`, `WHATSAPP_INSTANCE` | `httpx` + Evolution API | ⚙️ |

### Notes Communication
- **Slack** : Créer une app sur api.slack.com, activer les scopes `channels:read`, `chat:write`, `search:read`
- **Telegram** : Créer un bot via @BotFather, récupérer ton `TELEGRAM_CHAT_ID` via @userinfobot
- **WhatsApp** : Requiert Evolution API auto-hébergé ou un service tiers. Docker: `docker run -p 8080:8080 atendai/evolution-api`

---

## PRODUCTIVITÉ

| MCP | Fichier | Variables requises | Dépendances | Statut |
|-----|---------|-------------------|-------------|--------|
| Gmail | `google_agent.py` | `google_credentials.json` | `google-api-python-client` | ✅ |
| Google Calendar | `google_agent.py` | `google_credentials.json` | `google-api-python-client` | ✅ |
| Notion | `mcps/notion_mcp.py` | `NOTION_TOKEN` | `notion-client` | ⚙️ 📦 |
| Google Drive | `mcps/drive_mcp.py` | `google_credentials.json` | `google-api-python-client` | ⚙️ |
| Google Sheets | `mcps/drive_mcp.py` | `google_credentials.json`, `BUDGET_SHEET_ID` | `google-api-python-client` | ⚙️ |
| Google Docs | `mcps/drive_mcp.py` | `google_credentials.json` | `google-api-python-client` | ⚙️ |
| Linear | `mcps/linear_mcp.py` | `LINEAR_API_KEY` | `httpx` | ⚙️ |
| Stripe | `mcps/stripe_mcp.py` | `STRIPE_SECRET_KEY` | `stripe` | ⚙️ 📦 |
| Qonto | `mcps/qonto_mcp.py` | `QONTO_LOGIN`, `QONTO_SECRET_KEY`, `QONTO_ORGANIZATION_SLUG` | `httpx` | ⚙️ |

### Notes Productivité
- **Drive/Sheets/Docs** : Ajouter les scopes Drive dans `google_credentials.json` et re-générer `google_token.json`
- **Notion** : Créer une intégration sur notion.so/my-integrations et partager les pages avec elle

---

## DEV & INFRA

| MCP | Fichier | Variables requises | Dépendances | Statut |
|-----|---------|-------------------|-------------|--------|
| Supabase | `mcps/supabase_mcp.py` | `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | `supabase` | ⚙️ 📦 |
| Vercel | `mcps/vercel_mcp.py` | `VERCEL_TOKEN` | `httpx` | ⚙️ |
| GitHub | `mcps/github_mcp.py` | `GITHUB_TOKEN`, `GITHUB_DEFAULT_REPO` | `PyGithub` | ⚙️ 📦 |
| Docker | `mcps/docker_mcp.py` | — (socket local) | `docker` | 📦 |

---

## SMART HOME & PERSO

| MCP | Fichier | Variables requises | Dépendances | Statut |
|-----|---------|-------------------|-------------|--------|
| Kasa (existant) | `kasa_agent.py` | — | `python-kasa` | ✅ |
| Home Assistant | `mcps/homeassistant_mcp.py` | `HOMEASSISTANT_URL`, `HOMEASSISTANT_TOKEN` | `httpx` | ⚙️ |
| Spotify | `mcps/spotify_mcp.py` | `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_USERNAME` | `spotipy` | ⚙️ 📦 |
| Apple Health | `mcps/applehealth_mcp.py` | `APPLE_HEALTH_EXPORT_PATH` | — | ⚙️ |
| Google Maps | `mcps/googlemaps_mcp.py` | `GOOGLE_MAPS_API_KEY` | `googlemaps` | ⚙️ 📦 |

### Notes Smart Home
- **Home Assistant** : Générer un token depuis HA > Profil > Sécurité > Jetons d'accès longue durée
- **Spotify** : Lancer `python mcps/spotify_mcp.py` une fois pour le flow OAuth initial
- **Apple Health** : Exporter depuis iPhone > Health app > Profil > Exporter les données de santé, copier `export.xml` dans le chemin configuré

---

## RECHERCHE & INTELLIGENCE

| MCP | Fichier | Variables requises | Dépendances | Statut |
|-----|---------|-------------------|-------------|--------|
| YouTube | `mcps/youtube_mcp.py` | `YOUTUBE_API_KEY` | `google-api-python-client`, `youtube-transcript-api` | ⚙️ 📦 |
| Wikipedia | `mcps/wikipedia_mcp.py` | — | `wikipediaapi` | 📦 |
| ArXiv | `mcps/arxiv_mcp.py` | — | `arxiv` | 📦 |

---

## FINANCE & ADMIN

| MCP | Fichier | Variables requises | Dépendances | Statut |
|-----|---------|-------------------|-------------|--------|
| Budget Sheets | `mcps/drive_mcp.py` | `BUDGET_SHEET_ID` | _(voir Drive)_ | ⚙️ |
| Qonto | `mcps/qonto_mcp.py` | `QONTO_*` | `httpx` | ⚙️ |

---

## CRÉATION & MÉDIAS

| MCP | Fichier | Variables requises | Dépendances | Statut |
|-----|---------|-------------------|-------------|--------|
| Canva | `mcps/canva_mcp.py` | `CANVA_ACCESS_TOKEN` | `httpx` | ⚙️ |
| Figma | `mcps/figma_mcp.py` | `FIGMA_ACCESS_TOKEN` | `httpx` | ⚙️ |
| ElevenLabs | `mcps/elevenlabs_mcp.py` | `ELEVENLABS_API_KEY` | `elevenlabs` | ⚙️ 📦 |
| Replicate | `mcps/replicate_mcp.py` | `REPLICATE_API_TOKEN` | `replicate` | ⚙️ 📦 |

---

## Installation des dépendances

```bash
pip install slack_sdk notion-client stripe supabase PyGithub docker \
            spotipy googlemaps youtube-transcript-api wikipediaapi \
            arxiv elevenlabs replicate httpx
```

## Vérification rapide

```bash
# Depuis backend/
python -c "
from mcps.slack_mcp import SlackMCP
from mcps.telegram_mcp import TelegramMCP
from mcps.notion_mcp import NotionMCP
from mcps.stripe_mcp import StripeMCP
from mcps.github_mcp import GithubMCP
print('Tous les imports OK')
"
```
