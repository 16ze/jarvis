# CLAUDE.local.md — Overrides locaux Bryan Hilaire
# NE PAS COMMITTER — contient des données personnelles

## Identité & comptes

- Propriétaire : Bryan Hilaire / Kairo Digital
- Compte Google Ada : adaai.bryan@gmail.com (OAuth2 — token dans backend/google_token.json)
- Timezone : Europe/Paris (UTC+2 en été, UTC+1 en hiver)
- Langue préférée : français

## Réseau local

- Réseau WiFi : Bbox-E5AB7C35
- IP décodeur Bbox TV : 192.168.1.86
- IP imprimante 3D (Moonraker) : vérifier dans backend/devices.json

## Devices Tuya/Smart home

- Devices LSC Connect configurés dans backend/tinytuya.json
- Config raw dans backend/tuya-raw.json
- Ne jamais écraser tinytuya.json sans backup

## Préférences de développement

- Conda env : ada_v2 (Python 3.11)
- Démarrage local : `bash start_ada.sh` depuis la racine
- Démarrage remote : `bash backend/start_remote.sh`
- Port backend : 8765 (WebSocket) + 8000 (FastAPI)

## Spotify

- Token stocké dans backend/.spotify_token
- Compte Spotify : compte personnel Bryan

## Comportement Ada attendu

- Voix Kore (Gemini Native Audio) — ne jamais changer la voix sans validation
- Mode caméra par défaut au lancement (`DEFAULT_MODE = "camera"`)
- Réponses vocales courtes et directes — pas de longs monologues
- Confirmations verbales avant envoi d'email ou suppression de fichier
