# Audit complet — Jarvis / A.D.A V2

> Audit réalisé le 2026-07-05 sur `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis`
> Objectif : évaluer l'état réel du projet et tracer la route vers un « OS IA » complet, stable et sécurisé.

---

## 1. Verdict global

Jarvis est un projet **ambitieux et déjà très substantiel** : ~23 400 lignes de Python backend, ~8 000 lignes de frontend React/Electron, 124 fichiers Python, un système cognitif biomimétique (brain SNN + système limbique simulé), une vingtaine d'agents spécialisés (web, CAD, impression 3D, domotique, vision YOLO, Google, etc.), et une couche de connecteurs MCP.

Ce n'est **pas** une simple IA conversationnelle — la fondation d'un assistant-exécuteur existe déjà. Mais dans son état actuel, ce n'est pas encore un système *fiable*, *sécurisé* ni *évolutif* au sens où tu le vises. Trois catégories de problèmes le bloquent :

1. **Sécurité** — plusieurs vecteurs d'exécution de commandes arbitraires insuffisamment protégés, et une couche temps réel non authentifiée.
2. **Robustesse** — un fichier monstre (`ada.py`, 6 551 lignes), 342 blocs `except` dont des `except:` nus qui masquent les erreurs, pas de CI/tests exécutés.
3. **Sauvegarde** — 18 commits + du travail non commité qui n'existent que sur ce disque externe (voir §7).

Aucun de ces points n'est rédhibitoire. Ils sont la liste de travaux à faire **avant** d'empiler de nouvelles fonctionnalités.

---

## 2. Sécurité — À corriger en priorité

### 2.1 🔴 CRITIQUE — Couche Socket.IO non authentifiée
- `backend/server.py:74` et le serveur Socket.IO sont configurés en `cors_allowed_origins='*'` / `allow_origins=["*"]`.
- Le handler `connect` (`server.py:485`) **ne vérifie aucun token**. Seuls 3 endpoints HTTP (`/documents/*`) passent par `require_token`.
- Or l'événement `user_input` (`server.py:945`) route vers `os_agent.run()`, qui peut exécuter des commandes shell (`os_control_agent.py:1020`, `run_shell`).
- **Conséquence** : le serveur écoute sur `127.0.0.1:8000`, mais avec CORS `*`, **n'importe quelle page web ouverte dans ton navigateur peut ouvrir une socket vers localhost:8000 et piloter le PC** (exécution de commandes, contrôle OS). C'est une faille de type CSRF/DNS-rebinding sur une surface d'exécution de code.
- **Correctif** : exiger un token partagé sur `connect` (via `auth` handshake Socket.IO), restreindre `cors_allowed_origins` à l'origine réelle de l'UI (`app://` Electron / `http://localhost:5173`), refuser toute origine inconnue.

### 2.2 🔴 CRITIQUE — Blocklist de commandes contournable
- `ada.py:509` `DANGEROUS_COMMANDS` est une liste de sous-chaînes (`"rm "`, `"sudo "`, …) testée par `if dangerous in command`.
- Une blocklist par sous-chaîne se contourne trivialement : `/bin/rm`, `r""m`, `$(echo cm0K | base64 -d)`, `find … -delete`, un script intermédiaire, etc. Et elle ne couvre ni `curl … | sh`, ni l'exfiltration, ni l'écriture dans des fichiers système.
- Le même `subprocess.run(..., shell=True)` existe à **4 endroits au moins** (`ada.py:2302`, `os_control_agent.py:962/1020`, `task_agent.py:111`) — dont certains **sans aucun filtre**.
- **Correctif** : passer d'une blocklist à un modèle d'**autorisation explicite** (allowlist de commandes + confirmation utilisateur obligatoire pour tout le reste, cf. §5 le « mode sécurité »). Idéalement, supprimer `shell=True` au profit de `shlex.split` + argv, et router toute exécution par un point unique (`safe_exec()`).

### 2.3 🟠 Secrets versionnés dans git
- Trackés dans le repo (donc sur GitHub `16ze/jarvis`) : `backend/.spotify_token` (**access token Spotify réel**), `devices.json`, `tinytuya.json`, `tuya-raw.json` + `.bak` (clés locales domotique Tuya).
- **Correctif** : `git rm --cached` ces fichiers, les ajouter au `.gitignore`, **révoquer/régénérer** le token Spotify et les clés Tuya, et purger l'historique si le repo est public (`git filter-repo`).

### 2.4 🟠 `self_evolution_agent.py` — l'IA modifie son propre code
- L'agent écrit des fichiers dans `JARVIS_ROOT` et commit automatiquement (`self_evolution_agent.py:75`). La validation de chemin (`_validate_path`) est bonne, mais il n'y a pas de garde-fou humain systématique ni de sandbox.
- **Recommandation** : garder cet agent **désactivé par défaut**, exiger une revue/confirmation avant tout `git commit`, et l'exécuter sur une branche dédiée jamais sur `main`.

---

## 3. Robustesse & qualité de code

| Problème | Détail | Impact |
|---|---|---|
| **Fichier monolithe** | `ada.py` = 6 551 lignes, mêle orchestration, config Gemini, dispatch d'outils, terminal, brain, heartbeat | Illisible, difficile à tester, source de régressions |
| **`except:` nus** | `ada.py:5218`, `printer_agent.py:457/494`, `server.py:87` + 342 `except` au total | Masquent les vraies erreurs, rendent le debug impossible |
| **Duplication du dispatch** | Chaque outil doit être wiré à 4 endroits (`ada.py` ×2 + `external_bridge.py` + déclarations) — cf. CLAUDE.md | Oublis fréquents, incohérences voix/texte |
| **Pas de CI / tests non lancés** | 13 fichiers de tests présents mais aucune trace d'exécution automatisée | Régressions non détectées |
| **Incohérence dépendances** | `langchain-google-genai` dans `requirements.txt` alors que la règle absolue dit « Jamais LangGraph/framework lourd » | Dette et confusion |
| **Fichiers `.bak` partout** | `devices.json.bak`, `devices.json.bak2`, `.env.bak.*` dans le repo | Bruit, risque de fuite |

**Priorités robustesse :**
1. Remplacer tous les `except:` nus par `except Exception as e:` avec log structuré.
2. Découper `ada.py` : extraire `tool_dispatch.py`, `voice_config.py`, `terminal.py`, `heartbeat.py`.
3. Centraliser le registre d'outils dans **une seule** structure (un dict `TOOLS = {name: (declaration, handler)}`) consommée à la fois par la voix, le texte et les déclarations Gemini — élimine la quadruple duplication.
4. Ajouter un `pytest` en pre-commit + un workflow GitHub Actions minimal.

---

## 4. Système cognitif (brain SNN + limbique)

**C'est la partie la plus originale du projet et la mieux structurée.** `brain/brain_manager.py` est une façade singleton défensive (aucune exception ne remonte), avec un réseau d'attention, un système limbique (`limbic.py`, 486 lignes : dopamine, cortisol, oxytocine, sérotonine…), des humeurs, et une injection du « mood block » dans le `system_instruction` de Gemini (`ada.py:905`).

**Constats :**
- ✅ Architecture propre, feature-flaggée (`BRAIN_ENABLED`, `BRAIN_OBSERVE_ONLY`, `BRAIN_MODULATE_ALL`, `BRAIN_V3_ENABLED`), fallback v2/v3 géré.
- ⚠️ **Désactivé par défaut** (`BRAIN_ENABLED=false`) — donc aujourd'hui le comportement « profondément réfléchi » que tu vises n'est pas actif.
- ⚠️ Le brain **module la prosodie/le ton** (via mood block), mais n'influence pas encore la **prise de décision** ni la **planification** des actions. C'est un système émotionnel, pas encore un système de raisonnement.
- ⚠️ Le `mood_block.py` pousse une « identité affective » très forte (colère, insultes autorisées, attachement amoureux). Cohérent avec un compagnon, mais à **découpler** du mode « exécuteur de tâches » : quand Jarvis réserve un vol ou exécute une action système, tu veux de la rigueur, pas de l'humeur.

**Recommandation pour « raisonnement proche de l'humain » :** ajouter par-dessus le brain émotionnel une **couche de raisonnement délibératif** (planification explicite : intention → décomposition → plan → validation → exécution → vérification), séparée de la couche affective. Le brain règle *le ton* ; le planner règle *les actes*.

---

## 5. Capacités « OS IA » — écart avec la cible

Ta vision : un OS IA multi-écrans, où Jarvis peut lui-même naviguer et automatiser toute action PC.

**État actuel du frontend :**
- L'UI n'a **pas de vrai routeur multi-écrans**. `App.jsx` (2 391 lignes) gère les fenêtres via **8 booléens** `showKasaWindow`, `showPrinterWindow`, `showCadWindow`… (toggles de modales), pas des « écrans » navigables.
- Il n'y a donc pas encore le « menu hamburger → écrans dédiés » que tu décris : c'est un bureau à fenêtres flottantes, pas un OS à modules.

**Ce qu'il faut construire :**
1. **Un vrai shell d'OS** : sidebar/menu hamburger + routeur (React Router ou état `activeModule`) → écrans plein cadre : *Dashboard, Agents, Automatisations, Vision, Domotique, Fichiers/Projets, Terminal, Mémoire, Paramètres, Sécurité/Logs*.
2. **Un bus d'actions unifié** : un registre d'outils unique (§3.3) que **l'UI ET Jarvis** consomment, pour que Jarvis puisse « ouvrir un écran » et « exécuter une capacité » exactement comme l'utilisateur.
3. **Un moteur de planification** (le cœur « exécuteur ») : décompose une demande floue (« réserve-moi un vol ») en étapes vérifiables, avec points de confirmation avant chaque action irréversible (paiement, envoi, suppression).
4. **Une couche d'observabilité** (à la Palantir dans l'esprit) : un écran unique qui agrège les logs, l'état des agents, les stimuli du brain, l'historique des actions, et permet de rejouer/auditer chaque décision. Tu as déjà les briques (`monitoring_agent`, `screen_watcher`, vision storage SQLite+Chroma) — il manque la vue unifiée.

---

## 6. Feuille de route proposée (par phases)

**Phase 0 — Sécuriser & sauvegarder (immédiat, bloquant) — ✅ TERMINÉE (2026-07-05)**
- ✅ Sauvegarde : tout poussé sur GitHub (`main` 159 commits + `codex/restore-voice-pipeline`
  + toutes les branches). Le disque externe s'est déconnecté en pleine session — rien perdu,
  car déjà poussé. Preuve en direct de la fragilité signalée au §7.
- ✅ Secrets : sortis du suivi git (`git rm --cached`), copiés dans le coffre
  `~/.jarvis/secrets-vault` (conservés, non révoqués), gitignorés. **Token Notion réel
  découvert dans l'historique et purgé de toutes les branches** (`git filter-repo`).
- ✅ Socket.IO/CORS : origines restreintes + auth token optionnelle sur le handshake
  (`server.py`, `App.jsx`). Faille CSRF/DNS-rebinding fermée.
- ✅ Exécution shell : politique robuste `backend/safe_exec.py` (blocage dur non
  contournable via shlex) câblée dans `handle_terminal_request`, `os_control_agent`,
  `task_agent`. Mode `ADA_SHELL_STRICT`. 22 tests unitaires verts.
- ✅ Bonus robustesse : 4 `except:` nus corrigés.

**Phase 1 — Stabiliser le socle**
- Découper `ada.py`, centraliser le registre d'outils, nettoyer les `except:` nus.
- Mettre en place pytest + CI GitHub Actions.
- Créer un point d'exécution unique `safe_exec()` (fin des `shell=True` dispersés).

**Phase 2 — Le shell OS IA**
- Routeur multi-écrans + menu hamburger, écrans dédiés par capacité.
- Bus d'actions partagé UI/Jarvis.
- Écran d'observabilité (logs, agents, décisions, brain).

**Phase 3 — Le cerveau exécuteur**
- Moteur de planification délibérative (intention → plan → confirmation → exécution → vérification).
- Découplage couche affective (ton) / couche raisonnement (actes).
- Activation progressive du brain (`BRAIN_ENABLED=true` en `OBSERVE_ONLY` d'abord).

**Phase 4 — Capacités avancées**
- Élargir les agents (voyage/réservation, finance, veille, etc.) sur le socle sécurisé.
- Mémoire long-terme enrichie, anticipation proactive encadrée.

---

## 7. Sauvegarde — risque immédiat de perte

- `main` local est **18 commits en avance** sur `origin/main` (travail brain SNN, vision YOLO, gesture controller non poussé).
- **642 lignes modifiées non commitées** + 12 fichiers non trackés (dont `backend/brave_search_agent.py`).
- Dernier commit il y a 6 semaines. **Tout ceci n'existe que sur ce disque externe.** Si le disque tombe, c'est perdu.
- **Action n°1, avant tout le reste** : committer/pusher toutes les branches sur GitHub.

---

## 8. Ce qui est déjà bien (à préserver)

- Architecture d'agents cohérente et documentée (`CLAUDE.md` excellent, checklist d'ajout d'agent claire).
- Le brain biomimétique : conception soignée, défensive, feature-flaggée.
- Convention « tout outil retourne une `str`, jamais d'exception non catchée ».
- Validation de chemin contre `JARVIS_ROOT` pour les opérations fichiers.
- Master switches d'activation partout (vision, brain, face auth) — bonne discipline.
- Auth par visage (MediaPipe) et confirmations avant actions irréversibles : les bons réflexes de sécurité sont là, il faut les généraliser.
