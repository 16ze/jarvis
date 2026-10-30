# HANDOFF — Jarvis / Ada  (pour Codex)

> Rédigé le 2026-10-29 par Claude. But : permettre à Codex de reprendre le chantier
> « maturité » sans perte de contexte. Lis ce fichier en entier avant de coder.

---

## MISSION (objectif prioritaire)

**Amener Ada à un niveau de maturité équivalent à ChatGPT et Codex — côté UX/UI
ET côté moteur. Objectif : 100 %.**

- Style visé : propre et mature façon **Apple** (sobre), **pas** cyberpunk/néon.
- Disponible sur **plusieurs devices** : desktop (Electron), mobile et tablette,
  la même Ada partout.
- Exigence absolue de Bryan : **aucune régression, aucun conflit, aucun bug.**
  Déléguer à plusieurs agents en périmètres disjoints quand c'est pertinent, et
  toujours vérifier (build + tests) avant de pousser/déployer.
- Mode de travail attendu : **autonomie maximale** — lancer, intégrer, builder,
  pousser, déployer sur le Mac et montrer le résultat ; ne demander que si réellement bloqué.

État d'avancement estimé au handoff : **~78–82 %** de la maturité « produit grand
public » façon ChatGPT (voir §1 pour le détail livré, §2–§3 pour ce qui reste).

---

## 0. État du dépôt (vérité au moment du handoff)

- **Repo** : github.com/16ze/jarvis
- **Branche de travail** : `integration/widget-pc-control`
- **HEAD fonctionnel du lot** : `a98cc97` (« fix(security): retirer le jeton des arguments Electron »),
  après `ee74206` (synchronisation multi-device) et `4dd8701` (auth Bearer HTTP)
- **Mac (machine de Bryan)** : repo sur `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis`,
  conda env `ada_v2` (Python 3.11), node 22.
- **Déploiement sur le Mac** : double-clic `~/Desktop/Relancer-Ada.command`
  (= `git pull origin integration/widget-pc-control` + `npm install` + arrêt propre + `bash start_ada.sh`).
  Alternative manuelle : `bash start_ada.sh` depuis la racine.
- **Ports** : backend FastAPI+Socket.IO sur `8000`, vite dev sur `5173`.

Avant de commencer : `git fetch origin && git reset --hard origin/integration/widget-pc-control`.

---

## 1. Ce qui a été livré cette session (déjà poussé)

1. **Refonte UI Apple-clean** (tokens CSS clair/sombre, system font, `rounded-ada*`, `shadow-ada*`).
2. **Shell centré conversation** (mode normal) façon ChatGPT/Claude, **mode modulaire préservé** derrière `isModularMode`.
3. **Fiabilité** : instance Electron unique (`requestSingleInstanceLock`), anti-race port 8000
   (`pollBackendPortTaken` ~3 s), arrêt sélectif, `start_ada.sh` idempotent. Fin du `[Errno 48]`.
4. **Robustesse moteur** (`backend/llm_router.py`) : retries+backoff (erreurs transitoires only),
   timeouts `asyncio.wait_for`, repli propre (messages FR par cause), masquage des clés. API publique inchangée.
5. **Historique conversations** : `src/components/ConversationSidebar.jsx` + état dans `App.jsx`
   (new/switch/rename/delete, persistance localStorage `ada-conversations` / `ada-active-conv`).
6. **Composants chat** : `src/components/chat/{MarkdownMessage,MessageActions,TypingIndicator,ChatComposer}.jsx`.
7. **Streaming visuel** : caret clignotant sur le dernier message Ada pendant `isGenerating` (= `adaSpeaking`).
8. **Fix** : la fenêtre flottante TERMINAL ne s'auto-ouvre plus en mode normal (réservée au modulaire).
9. **Tests** : `backend/tests/*` → `python -m pytest backend/tests -q` = **104 verts** ;
   `npm run test` (vitest) = **60 verts**.
10. **Monitoring** : `backend/monitoring.py` (`log_exception`, `@guard`, `get_error_stats`),
    handler d'exception global + endpoint `GET /health/errors` dans `server.py`.
11. **Code-split** : `vite.config.js` `manualChunks` → `vendor-three` / `vendor-markdown` ;
    chunk applicatif ~446 ko (< 500 ko).
12. **Historique mature** : recherche accent-insensible dans les titres et messages, extraits de
    contexte, édition d'un message Bryan avec création d'une nouvelle branche, régénération sans doublon.
13. **Parité mobile/tablette** : tiroir d'historique, recherche, nouvelle conversation, suppression
    confirmée, édition tactile et compositeur partagé avec le desktop.
14. **Annulation réelle** : chaque tour texte possède un `requestId`; le bouton Stop annule la tâche
    `asyncio` correspondante côté serveur et attend `generation_finished` avant de libérer l'UI.
15. **Synchronisation multi-device réelle** : cache `localStorage` offline-first + stockage SQLite
    canonique authentifié, fusion LWW déterministe, tombstones anti-résurrection, notifications Socket.IO
    et statut de synchronisation visible sur desktop/mobile/tablette.
16. **Durcissement du secret Electron** : `ADA_API_TOKEN` ne transite plus dans `process.argv` ;
    le main process le fournit aux renderers locaux via IPC, y compris pour la base de documents.

---

## 2. LIVRÉ : vrai streaming token-par-token

Livré dans `f7501e4`. Les réponses tapées utilisent désormais
`generate_content_stream` et émettent chaque delta Socket.IO dès son arrivée.

**Contrats validés** :
- `App.jsx` handler `socket.on('transcription', (data) => …)` : **append par expéditeur**
  sans réémission finale du texte complet ;
- `ada_speaking {on:true}` précède les deltas texte et `{on:false}` clôt le tour ;
- la voix Gemini Live conserve son streaming existant, sans modification ;
- le contexte caméra/écran et les function calls restent disponibles en mode texte ;
- test runtime Socket.IO : 4 chunks reçus dans l'ordre, réponse reconstruite sans doublon.

**Validation** : 104 tests backend, 60 tests front, build Vite réussi, `/health/errors` à zéro.

---

## 3. Backlog restant pour viser 100 %

1. **Panneau santé** branché sur `GET /health/errors` (monitoring déjà prêt côté backend).
2. **CI** : lancer `pytest backend/tests` + `npm run test` à chaque push (GitHub Actions).
3. **npm audit** : 26 vulnérabilités (3 critiques) préexistantes remontées à l'install — à traiter.
4. **Conflits avancés** : le LWW actuel est adapté à Ada mono-propriétaire ; conserver une branche
   secondaire si deux appareils modifient hors ligne le même fil au même moment.
5. Cosmétique : router les logs `terminal_output` `[PLAN]/[PENSÉE]/[DIAG]` ailleurs que dans le fil
   (ou dans un panneau latéral discret), pour ne pas polluer la conversation.

---

## 4. Contrats & conventions À NE PAS CASSER

**Socket.IO** (events) :
- `transcription {sender, text, requestId?}` (append par sender), `user_input {text, requestId}`
  (envoi depuis le front), `generation_finished {requestId, status}`, `cancel_generation {requestId}`,
  `conversations_changed {revision, deviceId, sourceId}` (signal de resynchronisation, sans contenu),
  `ada_affect` (humeur brain, ~1.5 s), `ada_speaking {on, mode?, requestId?}` (vérité « Ada parle »),
  `pc_control_state {active}`, `clear_audio`, `tool_confirmation_request` / `confirm_tool {id, confirmed}`,
  `terminal_output {command, output}`, `status {msg}`, `audio_pcm`, `audio_data {data}`.

**Modèle de messages (front)** : `messages = [{ sender, text, time }]`.
`sender === 'Bryan'` = utilisateur ; `=== 'System'` = notice ; sinon = Ada.

**Composants chat (API figée — les tests en dépendent)** :
- `MarkdownMessage({ text, className })`
- `MessageActions({ onCopy, onRegenerate, canRegenerate })`
- `TypingIndicator()`
- `ChatComposer({ value, onChange(str), onSend(), onStop(), isGenerating, disabled, placeholder })`

**Règles projet absolues** :
- Voix = **Gemini Native Audio uniquement** (voix Kore). Jamais ElevenLabs.
- **asyncio pur** partout. Jamais LangGraph ni framework agent lourd. Jamais localtuya (tinytuya only).
- Tous les outils backend retournent une **`str`** (jamais d'exception non catchée).
- Secrets dans `.env` uniquement — **jamais** commités, jamais collés en clair.
- Nouvel outil = 3 points de câblage : `mcp_tools_declarations.py` + `ada.py::_execute_text_tool()`
  + `external_bridge.py::TextAgent._execute_tool()`.
- Confirmations avant actions irréversibles (envoi email, suppression).

**Attribution des commits** (obligatoire, fin de message de commit) :
```
Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01GgB2RcfHN2UPAwpdFC58ue
```
(Codex remplacera évidemment par sa propre attribution.)

---

## 5. Commandes utiles

```bash
# Tests backend (sans clé ni réseau)
python -m pytest backend/tests -q           # 104 verts attendus

# Tests + build front
npm run test                                # vitest, 60 verts
npm run build                               # chunk applicatif < 500 ko

# Démarrage complet (Mac)
bash start_ada.sh                           # backend + vite + electron
bash stop_ada.sh                            # arrêt propre (ports 8000/5173)

# Santé runtime
curl -s http://127.0.0.1:8000/health/errors # stats d'erreurs (monitoring)
```

---

## 6. Pièges connus

- **Double backend** : `start_ada.sh` lance un backend ET Electron peut en lancer un ;
  le fix (`electron/main.js`) fait qu'Electron **poll le port 8000 ~3 s** et s'attache si pris
  (message front « A.D.A Already Running »). Ne pas « corriger » en supprimant un des deux sans comprendre ce poll.
- **Worktrees d'agents** : si tu délègues, repars toujours de `origin/integration/widget-pc-control`
  (les worktrees ont démarré sur un mauvais commit par le passé).
- **Volume externe + SSH** : le repo est sur `/Volumes/Disque dev/...` ; certains accès shell distants
  échouent (Full Disk Access). Le `.command` du Bureau contourne en s'exécutant localement.
- **Mode modulaire** vs **mode normal** : `isModularMode` sépare l'ancien OS déplaçable (visage flottant,
  visualiseur hero, chat flottant, fenêtres outils) du nouveau shell conversation. Ne pas mélanger.
