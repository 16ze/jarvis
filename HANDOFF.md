# HANDOFF — Reprise du projet Jarvis / Ada

> Lis ce fichier en premier. Il donne tout le contexte pour continuer sans
> explorer tout l'ordinateur.

## Où est le projet
- **Chemin** : `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis` (disque externe « Disque dev »)
- **Git** : `github.com:16ze/jarvis` — branche de travail **`codex/restore-voice-pipeline`** (tout est poussé)
- **Env Python** : conda `ada_v2` (Python 3.11)

## Démarrer une session de reprise
1. Ouvrir la nouvelle conversation **dans ce dossier** (`cd "/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis"`).
2. `CLAUDE.md` (architecture) et ce `HANDOFF.md` sont lus automatiquement / en premier.
3. `git status` + `git log --oneline -15` pour voir l'état.

## Lancer l'app
```bash
conda activate ada_v2
cd backend && python server.py      # backend (port 8000)
# autre terminal :
npm run web                          # front web (5173) — ou npm start (Electron)
```

## Ce qui a été fait (voir AUDIT.md pour le détail complet)
- **Sécurité (Phase 0)** : secrets sortis du git → coffre `~/.jarvis/secrets-vault` (non révoqués) ;
  token Notion purgé de l'historique ; Socket.IO/CORS durcis ; `safe_exec.py` (blocage shell robuste).
- **Phase 1** : `prompts.py` (personnalité centralisée voix+texte) ; CI GitHub Actions ;
  tests de cohérence des outils ; `except:` nus corrigés.
- **Phase 2** : shell OS via le **dock central** (`ToolsModule.jsx`) — écrans Activité (observabilité)
  + Agents (`OsShell.jsx`). Navigation pilotée par Ada via l'outil `open_screen`.
- **Recherche web** : `web_search.py` (Brave → Google → DuckDuckGo, marche sans clé).
- **Ada** : n'expose plus son état interne (brain/humeur) — `prompts.py` + `brain/mood_block.py`.
- **Contrôle PC** (`backend/os_control_agent.py`) :
  - clics par accessibilité (`click_element`) au lieu de coordonnées ;
  - routines locales corrigées (Messages, TextEdit, volume, concurrence 2e tâche) ;
  - **résolution de contacts par nom** via Contacts.app (`_resolve_contact`) → messages + appels ;
  - **ouverture de toute app** (`_open_app_local` + action vision `open_app`, ex. « Localiser » → FindMy) ;
  - capacité **login/inscription web** (autofill Safari, sinon demande les identifiants).

## Ce qui reste / à valider (priorité contrôle PC)
- **Tester en réel sur le Mac** toutes les corrections contrôle PC (je ne peux pas piloter l'écran) :
  appel/message par nom, ouverture d'apps, login web. Garder l'écran **Activité** ouvert pour voir
  les actions (`open_app`, `click_element`).
- Découpage complet de `ada.py` (6500+ lignes) — reste à faire, sécurisé par la CI.
- 2 tests obsolètes échouent (`test_run_web_agent`, `test_kasa_agent`) : features supprimées, à nettoyer.

## Convention de travail
- Tout commit/push sur `codex/restore-voice-pipeline`.
- Tests : `conda activate ada_v2 && python -m pytest tests/test_safe_exec.py tests/test_tool_consistency.py -q`
- Front : `npm run build` pour vérifier.
- Fin de message de commit : `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
