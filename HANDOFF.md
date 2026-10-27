# Ada / Jarvis — Passation (handoff)

> Rédigé le 2026-10-27. Branche de travail : **`integration/widget-pc-control`** (poussée sur `16ze/jarvis`). Dernier commit : `2da2758`.
> Repo sur la machine de Bryan : `/Volumes/disque dev/archives-mars-avril-2026/jarvis` (disque externe).

---

## 1. Comment démarrer / arrêter

```bash
cd "/Volumes/disque dev/archives-mars-avril-2026/jarvis"
git checkout integration/widget-pc-control && git pull
lsof -ti:8000 | xargs kill -9 2>/dev/null   # tue un backend fantôme (bug récurrent)
bash start_ada.sh                            # backend (port 8000) + frontend (Vite+Electron)
# arrêt :
bash stop_ada.sh
```
- Vérifier d'être sur **`integration/widget-pc-control`** (`git branch --show-current`). Se tromper de branche a plusieurs fois fait croire à des bugs.
- Attendre `✅ Backend prêt` dans l'onglet backend. Au démarrage on doit voir aussi :
  `[SERVER] ada_affect broadcaster enregistré` et `[SERVER] ada_speaking broadcaster enregistré`.

---

## 2. À FAIRE / à vérifier (le plus important)

### 2.1 Vérifier que la vignette/visage est bien connectée (en cours)
- Dernière correction poussée : Electron injecte le token socket (`ADA_API_TOKEN` de `backend/.env`) dans toutes les fenêtres. **À confirmer au prochain démarrage.**
- **Point témoin** en bas de la vignette : 🔴 refusé/déconnecté · 🔵 connecté mais 0 donnée · 🟢 données reçues. Objectif = **vert**.
- Si 🔴 : `ADA_API_TOKEN` n'est pas dans `backend/.env` (le chercher ailleurs : `.env` racine ? variable d'env shell ?). Aligner la source lue par `electron/main.js:readAdaToken()`.

### 2.2 Clé Gemini / facturation (bloquant pour la VOIX)
- La voix passe **uniquement** par Gemini Native Audio (non négociable). Erreur rencontrée : `1011 ... prepayment credits are depleted`.
- L'API **Live (native audio) exige un projet avec facturation activée** (le free tier ne suffit pas). Vérifier le crédit/billing du projet de la clé.
- Clé dans `backend/.env` → `GEMINI_API_KEY`. (Ne jamais coller la clé dans un chat.)

### 2.3 Tailscale (accès distant sécurisé/anonyme) — NON FAIT
- Objectif : accéder à Ada à distance de façon privée (VPN mesh WireGuard, HTTPS via `tailscale serve`), recommandé plutôt qu'un VPS exposé.
- **Nécessite les mains + login de Bryan sur chaque appareil** (ne peut pas se faire à distance) :
  - Mac (le serveur Ada) : installer Tailscale, se connecter, puis `tailscale serve` pour exposer le port 8000 en HTTPS privé. À faire quand Bryan est chez lui.
  - Téléphone : app Tailscale + login (faisable n'importe où).
- Une fois en place : pointer `VITE_BACKEND_URL` du mobile vers l'URL Tailscale du Mac.

### 2.4 Tester le stack de bout en bout (runtime)
- Rien n'a encore été confirmé **en exécution** complète par Bryan (compile/build OK, mais pas le run complet voix+visage+outils).
- Tester : voix (Gemini OK), chat texte, pilotage PC, et les 3 visages (bureau / vignette / mobile).

### 2.5 Cerveau Claude gratuit (optionnel)
- `llm_router` sait utiliser Claude Code CLI (`claude -p`) → raisonnement/codage **gratuit** via l'abonnement, sans clé API. La voix reste Gemini.
- Activer : `JARVIS_BRAIN=claudecli` dans `.env` (ou laisser `hybrid` avec `ANTHROPIC_API_KEY` vide + `claude` installé).

---

## 3. Chantiers discutés, non faits (features)

- **VR / casque (WebXR)** : intégrer le visage dans la scène XR. Reporté : la page XR est en Three.js pur (pas React), rendu différent, et pas de casque pour tester. Fusionner aussi la caméra (couche B) dans la page XR.
- **App mobile native** : la PWA mobile existe ; version native plus tard.
- **Shell natif pour tuer le lag Electron** : gros chantier (Swift), non commencé. Alternative discutée à la place d'Electron.
- **Repli chat → cerveau Claude** : quand la session Live est indisponible, faire répondre le chat texte via `claudecli` au lieu d'afficher « pas prête ». Proposé, **non implémenté** (en attente d'accord de Bryan).
- **Réglage fin des expressions** par émotion : le moteur est continu/variable ; ajuster les signatures (colère plus marquée, etc.) selon le ressenti de Bryan (capture d'écran utile).
- **Humeur « écoute »** à étendre au mobile / XR.

---

## 4. Ce qui a été construit cette session (état)

Visage vivant d'Ada :
- `src/widget/Face.jsx` — visage SVG « écran » (EMO-like), **moteur d'expression continu** piloté par les hormones du brain (valence/éveil/fatigue) + signatures d'émotion dosées + micro-variations (jamais figé). Clignement, saccades, suivi curseur, larme/sueur/tremblement.
- Tailles **S/M/L/XL + plein écran** (vignette). `electron/main.js` redimensionne la fenêtre (fix `setResizable` car `resizable:false` ignore `setBounds` sur macOS).
- Présent sur **3 surfaces** : vignette flottante (`Widget.jsx`), HUD de l'UI principale (`App.jsx`, suit le curseur + micro), mobile (`MobileApp.jsx`).

Signaux temps réel (sockets) :
- `ada_affect` — humeur du brain, diffusée en continu par `server.py` (`get_affect_snapshot()`).
- `ada_speaking` — « Ada parle », basé sur la **durée audio réelle** (`ada.py:_speaking_until`), diffusé à toutes les fenêtres → la bouche suit **toute la phrase** (fini le cut au milieu).
- `pc_control_state` — pilotage PC (visage ambré/focalisé).
- Token socket auto-injecté par Electron (`src/adaToken.js`).

Rappel des briques des sessions précédentes (déjà en place) : contrôle PC animé façon Claude, cerveau hybride (`llm_router`), agent de code autonome (`dev_agent`), gate de sécurité (`security_gate`), reprompting (`reprompt`), client MCP générique (`external_mcp`), PWA, couches WebXR + caméra, passe perf (electron-performance).

---

## 5. Contraintes & règles (à respecter par le relais)

- **Voix = Gemini Native Audio uniquement.** Jamais ElevenLabs. Jamais changer la voix (Kore) sans validation.
- **Autonome total**, mais garder le filet anti-catastrophe (`safe_exec` HARD_BLOCK : `rm -rf /`, fork bomb, wipe disque).
- **Jamais** committer de secrets. `.env`, `backend/mcp_servers.json`, tokens → gitignored.
- **Jamais LangGraph / framework agent lourd** — asyncio pur. Jamais localtuya (tinytuya).
- Confirmations avant actions irréversibles (email, suppression) — sauf réglage autonome explicite.
- Attribution des commits (voir CLAUDE.md du repo / la session).
- Push via l'email noreply si GitHub bloque l'email privé : `git config user.email "16ze@users.noreply.github.com"`.

---

## 6. Pièges récurrents rencontrés

- **Port 8000 fantôme** : `address already in use` → `lsof -ti:8000 | xargs kill -9` avant de relancer.
- **Mauvaise branche** : toujours vérifier `integration/widget-pc-control`.
- **Chemin du repo** : sur disque externe (`/Volumes/disque dev/...`), pas dans `~`. Le trouver : `find /Volumes ~ -maxdepth 5 -name start_ada.sh`.
- **Code Electron (`main.js`)** : ne se recharge pas à chaud → vrai redémarrage requis.
- **Un « crash » d'Ada** a été signalé sans traceback — si ça revient, garder l'onglet backend ouvert et récupérer le `Traceback`.
