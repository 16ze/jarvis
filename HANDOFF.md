# HANDOFF — Jarvis / Ada  (reprise par Cursor)

> Mis à jour le 2026-10-30. Rédigé pour que **Cursor reprenne le chantier sans se tromper**.
> Lis ce fichier EN ENTIER avant de coder. Il fait autorité sur l'état réel du projet.

---

## MISSION (objectif prioritaire)

**Amener Ada à une maturité équivalente à ChatGPT / Codex — UX/UI ET moteur. Objectif : 100 %.**
- Style **Apple-clean** (sobre), pas cyberpunk/néon.
- Multi-device : desktop (Electron) + mobile + tablette, la même Ada partout.
- **Aucune régression, aucun conflit, aucun bug.** Toujours vérifier (build + tests + smoke) avant de pousser/déployer.
- Autonomie max : lancer, intégrer, builder, pousser, déployer, montrer.

**Maturité estimée actuelle : ~82 %** (voir §3 pour le détail).

---

## 0. État exact du dépôt (au moment du handoff)

- **Repo** : github.com/16ze/jarvis
- **Branche de travail** : `integration/widget-pc-control`
- **HEAD poussé sur origin** : `383067b` — arbre propre, rien en attente.
- **CI** : verte (backend pytest + frontend vitest/build + **smoke de rendu**). Voir §6.
- **Mac de Bryan** : repo sur `/Volumes/Disque dev/Archives-Mars-Avril-2026/jarvis`,
  conda env `ada_v2` (Python 3.11), node 22.
- **Déploiement sur le Mac** : double-clic `~/Desktop/Relancer-Ada.command`
  = `git pull origin integration/widget-pc-control` + `npm install` + arrêt propre + `bash start_ada.sh`.
  (Alternative manuelle : `bash start_ada.sh` depuis la racine.)
- **Ports** : backend FastAPI+Socket.IO = `8000`, vite dev = `5173`.

**Avant de coder** : `git fetch origin && git reset --hard origin/integration/widget-pc-control`.

---

## 1. ⚠️ VÉRIFICATION EN ATTENTE (à faire en premier)

Le fix « backend unique » (#1, commit `e1c758e`) a été **déployé** mais **pas encore confirmé
visuellement** (le contrôle d'écran distant était bloqué par le Centre de notifications).
→ **À faire** : relancer `Relancer-Ada.command`, puis dans la fenêtre Terminal « esbuild • npm run dev »
(lignes préfixées `[1]`), vérifier qu'on voit bien :
`[Backend] ADA_BACKEND_EXTERNAL=1 — backend géré par start_ada.sh, aucun spawn Electron`
et **AUCUN** `[Errno 48] address already in use`. Si `[Errno 48]` apparaît encore, voir §5 (pièges).

---

## 2. Ce qui a été livré cette session (déjà poussé, CI verte)

Commits (plus récent → ancien) :
- `383067b` `7445c9b` `2115e17` `e8da9c5` — **#2 Smoke-test de rendu en CI** (anti écran blanc).
- `e1c758e` — **#1 Fiabilité : backend unique déterministe** (`ADA_BACKEND_EXTERNAL`).
- `0e34d99` — **Pièces jointes image sur mobile/tablette**.
- `fb335d9` — **Fix écran blanc** (TDZ `adaSpeaking`).
- `dd57f5c` — **Pièces jointes image desktop**.
- `ee84430` — **Sécurité** : `npm audit fix` (26 → 7 vulns, non-breaking).
- `5ee89f8` `4646a87` — **CI GitHub Actions** (pytest + vitest + build).

Détail fonctionnel :
1. **Streaming token-par-token** : CONFIRMÉ fait des deux côtés — voix (`ada.py` calcule les deltas
   des transcriptions cumulatives Gemini Live, ~l.2852-2908) et texte (`backend/text_streaming.py`
   `collect_gemini_stream`). Contrat socket `transcription {sender,text}` = deltas, append par sender.
2. **Historique multi-conversations + sync** : `backend/conversation_store.py` (SQLite, merge
   Last-Write-Wins, tombstones), route `POST /api/conversations/sync`, client `src/lib/conversationSync.js`
   (Bearer token), câblé dans `App.jsx` (`syncConversationsNow`). Statut « Synchronisé sur vos appareils »
   affiché. Édition de message avec branche (`EditableUserMessage.jsx`), régénération sans doublon,
   recherche dans l'historique, suppression avec confirmation (`ConfirmDialog.jsx`), drawer mobile
   (`MobileConversationDrawer.jsx`). Stop = vraie annulation asyncio (`generation_registry.py`, par `requestId`).
3. **Pièces jointes image** (desktop + mobile) : passe par le canal multimodal **existant**
   `image_payload {mime_type, data}` consommé par `process_text_message` → Ada voit l'image via Gemini.
   - Backend : `backend/chat_attachments.py` (`normalize_image_attachment` : valide MIME jpeg/png/webp/gif,
     décode base64, plafond 6 Mo, ne lève jamais) + branchement dans `server.py::_handle_user_input`
     (`data['image']` prioritaire, sinon frame caméra). Tests : `backend/tests/test_chat_attachments.py`.
   - Frontend : `ChatComposer` (bouton trombone + aperçu, props `attachment/onPickImage/onClearAttachment`),
     `App.jsx` (`pendingAttachment`, FileReader base64, vignette dans la bulle), idem `MobileApp.jsx`.
     Tests : `src/components/chat/__tests__/ChatComposer.attachments.test.jsx`.
4. **Fix écran blanc (TDZ)** : l'effet autoscroll de `App.jsx` dépendait de la const dérivée
   `adaSpeaking` (déclarée plus bas) → ReferenceError au render → `#root` vide. Corrigé en dépendant des
   states bruts `adaVoiceSpeaking, adaTextSpeaking, requestPending`. **Ce bug rendait l'app non affichable.**
5. **#1 Fiabilité** : `start_ada.sh` exporte `ADA_BACKEND_EXTERNAL=1` dans l'onglet frontend ; `electron/main.js`
   ne spawne alors JAMAIS de backend (le poll de port ~3 s reste le fallback standalone). Fin du double-backend.
6. **#2 CI smoke** : `scripts/smoke-render.cjs` charge l'app (vite) en Chromium headless desktop+mobile,
   échoue si erreur de page au render (TDZ…) ou `#root` vide. Dans la CI : `--host 127.0.0.1`,
   `playwright install --with-deps chromium`, `--no-sandbox`, annotations `::error::`.
7. **Sécurité** : 19 vulns transitives corrigées (shell-quote critique, ws, axios, socket.io-parser…).

Tests actuels : **114 backend (pytest) + 66 frontend (vitest)**, build OK, smoke OK. Tous verts en CI.

---

## 3. Maturité par dimension (honnête)

- Expérience conversation : ~92 % (streaming, édition/branche, régénération, recherche, mobile, pièces jointes).
- Fiabilité : ~85 % (annulation réelle, backend unique, `/health/errors`, CI + smoke).
- Multi-device : ~75-80 % (sync bâtie + câblée + Bearer + tests ; reste test terrain 2 appareils réels).
- Ce qui DÉPASSE ChatGPT/Codex : voix native, vision caméra/YOLO, pilotage PC, domotique (19 devices Tuya),
  3D/CAD, mémoire persistante, brain neurobiologique. (~130 %.)

---

## 4. SUITE À FAIRE (backlog priorisé)

1. **Confirmer l'absence de `[Errno 48]`** après redéploiement (cf. §1).
2. **Test terrain de la sync multi-device** : ouvrir Ada sur 2 appareils réels (desktop + téléphone via
   Tailscale `https://macbook-pro.tailb0eecd.ts.net`) et vérifier que l'historique converge (créer une conv
   sur l'un, la voir sur l'autre). Durcir si besoin (le statut par défaut est `local`, se désactive sur erreur).
3. **Les 7 vulns npm restantes** = bumps majeurs (`vite@8`, `vitest@5`, `electron@45`, `esbuild`). Migration
   PRUDENTE, une par une, avec test sur appareil. **Ne PAS faire `npm audit fix --force`** à l'aveugle.
4. **Pièces jointes v2** (optionnel) : fichiers non-image, multi-fichiers, drag-&-drop.
5. **CI** : monter les actions en Node 24 (couper les warnings de dépréciation) ; éventuellement un cache
   des browsers Playwright pour accélérer le job frontend.
6. **Cosmétique** : router les logs `terminal_output` `[PLAN]/[PENSÉE]/[DIAG]` hors du fil (panneau latéral).

---

## 5. ⚠️ PIÈGES CONNUS (lis avant de toucher quoi que ce soit)

- **Écran blanc = crash de render** : le build ET les tests unitaires ne rendent PAS `<App/>` en entier.
  Pour vérifier un rendu : `npm run build` NE SUFFIT PAS. Lance le **smoke** (`npm run smoke`, voir §6) ou
  charge l'app et regarde la console (ReferenceError/TDZ). La CI le fait maintenant automatiquement.
- **TDZ / ordre de déclaration dans `App.jsx`** : `App.jsx` est énorme (~2900 l.). Beaucoup de consts dérivées
  sont déclarées TARD (ex. `adaSpeaking = adaVoiceSpeaking || adaTextSpeaking` ~l.2131, `isGenerating` ~l.2132).
  Ne JAMAIS référencer ces consts dans un `useEffect`/handler situé plus HAUT → ReferenceError au render.
  Utilise les states bruts (`adaVoiceSpeaking`, `adaTextSpeaking`, `requestPending`) déclarés en amont.
- **Double-backend / `[Errno 48]`** : `start_ada.sh` lance le backend PUIS `npm run dev` (→ Electron) dans un
  onglet Terminal **séparé** (osascript, env NON hérité). Le fix pose `ADA_BACKEND_EXTERNAL=1` dans l'onglet
  frontend ; Electron le lit et ne spawne pas. Si tu touches `start_ada.sh` ou `electron/main.js`, préserve
  ce flag des deux côtés.
- **CI — logs bruts bloqués** : dans certains environnements, `gh run view --log-failed` est refusé (proxy).
  → le smoke émet des annotations `::error::` (visibles via `gh api repos/16ze/jarvis/check-runs/<job-id>/annotations`).
- **CI — IPv4/IPv6** : vite dev bind `localhost` (souvent `::1` en CI) → wait-on/smoke en `127.0.0.1` ne le
  voient pas. D'où `npm run web -- --host 127.0.0.1` dans le step CI. Garde ça.
- **CI — deps backend** : le job n'installe que `pytest pytest-asyncio fastapi numpy` (les tests n'utilisent ni
  clé ni réseau ; les modules lourds sont importés paresseusement). Si tu ajoutes un test qui importe autre
  chose au chargement, ajoute la dep au step CI `backend`.
- **Playwright** : épinglé `1.48.2` (devDep). Le browser se télécharge via `npx playwright install chromium`
  (fait en CI). En local derrière proxy, le download peut échouer — sans impact sur la CI.
- **Déploiement sur le Mac** : si Electron tourne déjà, le **verrou d'instance unique** empêche le nouveau de
  démarrer → quitter l'ancien Electron AVANT (menu « Electron » → « Quit ada-v2 »). Le `.command` fait un
  stop propre, mais l'overlay widget peut bloquer le Bureau — ouvrir le Bureau via Finder (menu Aller → Bureau)
  pour double-cliquer le script. (Le volume externe + SSH = accès shell distant capricieux.)

---

## 6. Commandes utiles

```bash
# Backend (sans clé ni réseau)
python -m pytest backend/tests -q               # 114 verts

# Frontend
npm run test                                     # vitest, 66 verts
npm run build                                    # build prod
npm run smoke                                    # smoke de rendu (voir ci-dessous)

# Smoke en local (vite doit tourner) :
npm run web -- --host 127.0.0.1 &                # sert l'app sur 5173
npx wait-on http://127.0.0.1:5173/
SMOKE_URL=http://127.0.0.1:5173/ npm run smoke   # desktop + mobile, 0 erreur attendu

# Démarrage / arrêt (Mac)
bash start_ada.sh        # backend + vite + electron (pose ADA_BACKEND_EXTERNAL=1)
bash stop_ada.sh

# Santé runtime
curl -s http://127.0.0.1:8000/health/errors      # stats d'erreurs (monitoring)
```

---

## 7. Contrats & conventions À NE PAS CASSER

**Socket.IO** : `transcription {sender,text}` (deltas, append par sender), `user_input {text, requestId, image?}`
(`image = {mime_type, data(base64)}`), `ada_affect`, `ada_speaking {on, mode?, requestId?}`,
`pc_control_state {active}`, `clear_audio`, `tool_confirmation_request`/`confirm_tool {id,confirmed}`,
`terminal_output {command,output}`, `generation_finished {requestId,status}`.

**Modèle messages (front)** : `messages = [{ sender, text, time, edited?, image? }]`.
`sender==='Bryan'` = user ; `==='System'` = notice ; sinon = Ada. `image` = URL d'aperçu (session, non persistée dans la sync).

**Composants chat (API figée — tests en dépendent)** :
- `MarkdownMessage({ text, className })`
- `MessageActions({ onCopy, onRegenerate, canRegenerate })`
- `TypingIndicator()`
- `ChatComposer({ value, onChange(str), onSend(), onStop(), isGenerating, disabled, placeholder, attachment, onPickImage(file), onClearAttachment() })`
- `EditableUserMessage({ text, edited, disabled, alwaysShowActions?, onCopy, onSave(nextText) })`

**Règles projet ABSOLUES** :
- Voix = **Gemini Native Audio only** (voix Kore). Jamais ElevenLabs.
- **asyncio pur** partout. Jamais LangGraph. Jamais localtuya (tinytuya only).
- Tous les outils backend retournent une **`str`** (jamais d'exception non catchée).
- Secrets dans `.env` uniquement — jamais commités, jamais en clair.
- Nouvel outil = 3 points de câblage : `mcp_tools_declarations.py` + `ada.py::_execute_text_tool()`
  + `external_bridge.py::TextAgent._execute_tool()`.
- Confirmations avant actions irréversibles (envoi email, suppression).
- `mobile_setup.sh` (non suivi) : NE PAS le committer.

**Attribution des commits** : Cursor met évidemment sa propre attribution (ne pas réutiliser celle de Claude).

---

## 8. Fichiers chauds (attention aux conflits / à la taille)

- `src/App.jsx` (~2900 l.) : le hub. Socket, état conversation, rendu desktop + branche mobile, modular mode.
  `isModularMode` sépare l'ancien OS déplaçable (visage flottant, visualiseur hero, fenêtres outils) du
  nouveau shell conversation. Ne pas mélanger les deux.
- `electron/main.js`, `start_ada.sh`, `stop_ada.sh` : démarrage/fiabilité (cf. §5).
- `backend/server.py` : routes + handlers socket + wiring AudioLoop.
- `src/components/chat/ChatComposer.jsx`, `src/components/MobileApp.jsx`, `src/components/ConversationSidebar.jsx`.
