# Design — ADA OS Environment

**Date :** 2026-05-21  
**Projet :** Jarvis / Ada  
**Statut :** Draft  

---

## Objectif

Créer un environnement totalement dans ADA où Bryan peut rechercher, naviguer, lire, écrire, organiser, automatiser et piloter son Mac sans quitter l'interface ADA.

ADA ne remplace pas macOS au niveau système : elle devient une couche d'exploitation cognitive au-dessus de macOS, capable d'observer le contexte, d'orchestrer les outils et de garder une mémoire continue du travail.

---

## Vision produit

L'expérience cible est simple :

```text
Bryan
  ↓ voix / texte / UI
ADA OS Environment
  ↓
Recherche web · Navigateur · Fichiers · Projets · Mémoire · Agents · Apps macOS · APIs
  ↓
macOS / Internet / services externes
```

Bryan reste dans ADA. ADA ouvre les pages, lit les sources, crée les notes, lance les agents, manipule les fichiers, demande confirmation si nécessaire, puis garde le contexte dans la mémoire et dans le projet actif.

---

## Périmètre V1

La V1 doit livrer un cockpit utile, pas un OS complet.

Fonctionnalités incluses :
- Recherche Internet profonde avec sources, synthèse et historique.
- Navigateur ADA contrôlé via Playwright/browser-use.
- Workspace projet avec notes, fichiers, captures, sources et livrables.
- Vue mémoire : souvenirs, documents indexés, décisions et préférences.
- Vue tâches : objectifs en cours, sous-tâches, statuts, résultats.
- Terminal/logs ADA pour voir les actions exécutées.
- Contrôle macOS via `execute_pc_task` pour les actions locales.
- Confirmations obligatoires pour toute action sensible.

Fonctionnalités exclues de la V1 :
- Remplacement du Finder complet.
- Gestion multi-utilisateur avancée.
- Virtualisation ou sandbox OS lourd.
- Actions irréversibles sans confirmation.
- Exécution Docker par défaut.

---

## Décisions d'architecture

| Question | Décision | Raison |
|---|---|---|
| Nature de l'OS | Surcouche ADA au-dessus de macOS | Cela donne l'expérience "sans quitter ADA" sans réécrire le système bas niveau. |
| Interface principale | Dashboard React existant dans `src/App.jsx` | Réutiliser l'UI actuelle réduit le risque et conserve la voix, les sockets et les modules déjà branchés. |
| Backend | FastAPI + Socket.IO existants dans `backend/server.py` | Le serveur a déjà les events temps réel nécessaires pour afficher actions, logs et confirmations. |
| Recherche web | Nouveau `workspace_research_agent.py` orchestrant agents existants | Un agent dédié évite de mélanger recherche, navigation et stockage dans `ada.py`. |
| Navigation | `advanced_browser_agent.py` pour missions complexes, `web_agent.py` pour captures simples si besoin | Les agents existants couvrent déjà les cas rapides et les sessions web persistantes. |
| Contrôle Mac | `os_control_agent.py` derrière permissions strictes | Le contrôle local est puissant mais doit rester encadré par timeout, stop et confirmations. |
| Stockage projet | `projects/<project>/workspace/` + SQLite manifest | Les fichiers restent lisibles localement et SQLite donne un index fiable sans service externe. |
| Mémoire | `memory_manager.py` pour connaissances longues, workspace DB pour état court terme | Séparer mémoire durable et état de session évite de polluer la mémoire globale. |
| Outils Gemini | Tools de haut niveau `workspace_*` | ADA doit raisonner sur des intentions métier plutôt que sur des opérations UI trop petites. |
| Sécurité | Policy centrale avant exécution | Un point unique de décision rend les confirmations cohérentes entre voix, texte et UI. |

---

## Modèle mental utilisateur

Exemples de commandes naturelles :

```text
ADA, crée un workspace sur "agents IA pour prospection B2B" et lance une recherche profonde.
ADA, ouvre les trois meilleures sources et fais-moi une synthèse avec liens.
ADA, garde cette page dans le projet et crée une note "idées produit".
ADA, compare ces deux outils et prépare un tableau.
ADA, ouvre Safari sur le site, connecte-toi si je valide, et récupère les informations utiles.
ADA, rappelle-moi demain de reprendre cette recherche.
```

ADA doit répondre en français, afficher les actions en cours dans l'UI, puis stocker les résultats dans le projet actif.

---

## Architecture cible

```text
src/App.jsx
  ├─ WorkspaceShell
  │   ├─ ResearchPanel
  │   ├─ BrowserPanel
  │   ├─ FilesPanel
  │   ├─ MemoryPanel
  │   ├─ TasksPanel
  │   └─ ActivityPanel
  ↓ Socket.IO
backend/server.py
  ├─ REST workspace endpoints
  ├─ socket events workspace_*
  └─ bridge AudioLoop callbacks
  ↓
backend/workspace_agent.py
  ├─ WorkspaceManager
  ├─ WorkspaceResearchAgent
  ├─ WorkspacePolicy
  └─ WorkspaceEventBus
  ↓
Agents existants
  ├─ advanced_browser_agent.py
  ├─ os_control_agent.py
  ├─ research_agent.py
  ├─ task_agent.py
  ├─ memory_manager.py
  └─ project_manager.py
```

---

## Nouveaux modules backend

### `backend/workspace_manager.py`

Responsabilité : gérer l'état du workspace ADA.

```python
class WorkspaceManager:
    def __init__(self, jarvis_root: Path):
        self.root = jarvis_root.resolve()
        self.projects_dir = self.root / "projects"

    def create_workspace(self, name: str) -> str: ...
    def switch_workspace(self, name: str) -> str: ...
    def get_active_workspace(self) -> dict: ...
    def add_source(self, url: str, title: str, summary: str) -> str: ...
    def add_note(self, title: str, content: str, tags: list[str] | None = None) -> str: ...
    def add_artifact(self, filename: str, content: str, kind: str) -> str: ...
    def list_items(self, kind: str | None = None) -> list[dict]: ...
```

Choix technique : `WorkspaceManager` isole les écritures fichier pour appliquer la validation `JARVIS_ROOT` partout au même endroit.

Structure disque :

```text
projects/<workspace>/
  workspace/
    manifest.sqlite
    notes/
    sources/
    artifacts/
    captures/
    exports/
  chat_history.jsonl
```

Tables SQLite :

```sql
workspace_items(
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  path TEXT,
  url TEXT,
  summary TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

workspace_events(
  id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
```

### `backend/workspace_research_agent.py`

Responsabilité : transformer une intention de recherche en dossier exploitable.

```python
class WorkspaceResearchAgent:
    async def run(
        self,
        query: str,
        depth: str = "standard",
        workspace: str | None = None,
        save_sources: bool = True,
    ) -> str: ...
```

Flow :
1. Planifier les angles de recherche.
2. Collecter sources via `research_agent.py`, MCPs et navigateur si nécessaire.
3. Évaluer la qualité des sources.
4. Sauvegarder liens, résumés et extraits courts dans le workspace.
5. Produire une synthèse markdown avec recommandations.

Choix technique : garder un agent recherche dédié permet d'améliorer la recherche web sans modifier le loop vocal principal.

### `backend/workspace_policy.py`

Responsabilité : décider si une action est autorisée, refusée ou nécessite confirmation.

```python
class WorkspacePolicy:
    def classify(self, action: dict) -> str:
        # returns: "allow" | "confirm" | "deny"
```

Actions `confirm` :
- envoyer email/message/publication ;
- achat, paiement, abonnement ;
- suppression ou écrasement de fichier ;
- modification credentials/env ;
- exécution shell destructive ;
- accès à compte connecté ou données sensibles ;
- contrôle Mac hors routine locale simple.

Choix technique : une policy centrale évite que chaque agent invente ses propres règles de sécurité.

### `backend/workspace_event_bus.py`

Responsabilité : normaliser les events envoyés à l'UI.

```python
class WorkspaceEventBus:
    async def emit_status(self, message: str, level: str = "info") -> None: ...
    async def emit_item_created(self, item: dict) -> None: ...
    async def emit_activity(self, activity: dict) -> None: ...
    async def emit_browser_frame(self, image: str | None, log: str) -> None: ...
```

Choix technique : un bus d'événements évite de disperser les noms d'events Socket.IO dans tous les agents.

---

## Nouveaux tools Gemini

À ajouter dans `backend/mcp_tools_declarations.py`, puis à wirer dans `backend/ada.py` et `backend/external_bridge.py`.

### `workspace_create`

Crée ou ouvre un environnement de travail ADA.

```python
{
  "name": "workspace_create",
  "description": "Crée ou ouvre un workspace ADA pour organiser recherches, notes, sources et livrables.",
  "parameters": {
    "type": "OBJECT",
    "properties": {
      "name": {"type": "STRING", "description": "Nom du workspace."},
      "goal": {"type": "STRING", "description": "Objectif principal du workspace."}
    },
    "required": ["name"]
  }
}
```

### `workspace_research`

Lance une recherche Internet sauvegardée dans le workspace.

```python
{
  "name": "workspace_research",
  "description": "Effectue une recherche Internet structurée, sauvegarde les sources et produit une synthèse.",
  "parameters": {
    "type": "OBJECT",
    "properties": {
      "query": {"type": "STRING", "description": "Sujet à rechercher."},
      "depth": {"type": "STRING", "enum": ["quick", "standard", "deep"], "description": "Profondeur de recherche."},
      "workspace": {"type": "STRING", "description": "Workspace cible optionnel."}
    },
    "required": ["query"]
  },
  "behavior": "NON_BLOCKING"
}
```

### `workspace_save_note`

Sauvegarde une note structurée.

```python
{
  "name": "workspace_save_note",
  "description": "Ajoute une note dans le workspace actif.",
  "parameters": {
    "type": "OBJECT",
    "properties": {
      "title": {"type": "STRING"},
      "content": {"type": "STRING"},
      "tags": {"type": "ARRAY", "items": {"type": "STRING"}}
    },
    "required": ["title", "content"]
  }
}
```

### `workspace_list`

Liste les éléments du workspace.

```python
{
  "name": "workspace_list",
  "description": "Liste notes, sources, livrables ou événements du workspace actif.",
  "parameters": {
    "type": "OBJECT",
    "properties": {
      "kind": {"type": "STRING", "description": "notes, sources, artifacts, captures ou all."}
    }
  }
}
```

### `workspace_open_browser`

Ouvre une mission navigateur dans le panneau ADA.

```python
{
  "name": "workspace_open_browser",
  "description": "Lance une mission navigateur contrôlée par ADA et affiche sa progression dans le workspace.",
  "parameters": {
    "type": "OBJECT",
    "properties": {
      "mission": {"type": "STRING", "description": "Mission web à accomplir."},
      "save_result": {"type": "BOOLEAN", "description": "Sauvegarder le résultat dans le workspace."}
    },
    "required": ["mission"]
  },
  "behavior": "NON_BLOCKING"
}
```

---

## Wiring backend

### `backend/server.py`

Ajouter :
- endpoints REST `GET /api/workspace`, `GET /api/workspace/items`, `POST /api/workspace/note` ;
- socket events `workspace_create`, `workspace_research`, `workspace_save_note`, `workspace_open_browser` ;
- émissions `workspace_status`, `workspace_item_created`, `workspace_activity`, `workspace_state`.

Choix technique : REST sert au chargement initial fiable, Socket.IO sert au temps réel.

### `backend/ada.py`

Ajouter dans `AudioLoop.__init__` :

```python
self.workspace_manager = WorkspaceManager(JARVIS_ROOT)
self.workspace_event_bus = WorkspaceEventBus(...)
self.workspace_policy = WorkspacePolicy()
self.workspace_research_agent = WorkspaceResearchAgent(...)
```

Ajouter dans `_execute_text_tool()` :

```python
elif name == "workspace_research":
    return await self.workspace_research_agent.run(
        query=args.get("query", ""),
        depth=args.get("depth", "standard"),
        workspace=args.get("workspace"),
    )
```

Pour les tools `NON_BLOCKING`, lancer via `_bg_task` et répondre immédiatement à Gemini.

Choix technique : les tâches longues ne doivent pas bloquer le flux audio Live API.

### `backend/external_bridge.py`

Autoriser :
- `workspace_create`
- `workspace_research`
- `workspace_save_note`
- `workspace_list`

Mettre `workspace_open_browser` en confirmation ou exclusion selon le contexte, car ouvrir un compte connecté à distance peut exposer des données sensibles.

Choix technique : Telegram/WhatsApp doivent pouvoir lancer une recherche, mais pas prendre le contrôle complet de la session locale sans garde-fou.

---

## UI V1

Créer ou refactorer dans `src/components/` :

| Composant | Rôle |
|---|---|
| `WorkspaceShell.jsx` | Layout principal du cockpit ADA OS |
| `ResearchPanel.jsx` | Recherche, synthèses, sources |
| `BrowserPanel.jsx` | Frame/logs navigateur ADA |
| `WorkspaceFilesPanel.jsx` | Notes, sources, livrables |
| `WorkspaceMemoryPanel.jsx` | Mémoire longue et documents |
| `WorkspaceTasksPanel.jsx` | Tâches autonomes et statuts |
| `WorkspaceActivityPanel.jsx` | Timeline d'actions ADA |

Layout recommandé :

```text
┌─────────────────────────────────────────────────────────────┐
│ TopAudioBar + état ADA                                      │
├───────────────┬─────────────────────────────┬───────────────┤
│ Navigation    │ Panneau principal           │ Activité      │
│ Workspaces    │ Recherche / Browser / Note  │ Logs / Tasks  │
│ Sources       │                             │ Confirmations │
└───────────────┴─────────────────────────────┴───────────────┘
```

Choix technique : une UI en panneaux permet de rester dans ADA tout en gardant assez de densité pour travailler réellement.

---

## Contrats Socket.IO

### Client → serveur

```typescript
socket.emit("workspace_create", { name: string, goal?: string })
socket.emit("workspace_research", { query: string, depth?: "quick" | "standard" | "deep" })
socket.emit("workspace_save_note", { title: string, content: string, tags?: string[] })
socket.emit("workspace_open_browser", { mission: string, save_result?: boolean })
socket.emit("workspace_list", { kind?: string })
```

### Serveur → client

```typescript
socket.on("workspace_state", (data: WorkspaceState) => {})
socket.on("workspace_status", (data: { message: string; level: string }) => {})
socket.on("workspace_activity", (data: WorkspaceActivity) => {})
socket.on("workspace_item_created", (data: WorkspaceItem) => {})
socket.on("workspace_research_result", (data: { workspace: string; markdown: string }) => {})
```

Types :

```typescript
type WorkspaceItemKind = "note" | "source" | "artifact" | "capture" | "task";

type WorkspaceItem = {
  id: string;
  kind: WorkspaceItemKind;
  title: string;
  path?: string;
  url?: string;
  summary?: string;
  tags: string[];
  createdAt: string;
  updatedAt: string;
};

type WorkspaceState = {
  activeWorkspace: string;
  goal?: string;
  items: WorkspaceItem[];
};
```

Choix technique : typer les contrats côté UI réduit les erreurs de payload sans introduire `any`.

---

## Sécurité

Règles obligatoires :
- Tout chemin doit être résolu et validé sous `JARVIS_ROOT`.
- Aucune clé API, token OAuth ou secret ne doit être écrit dans les notes/sources.
- Toute suppression, écrasement, envoi externe ou paiement nécessite confirmation.
- Les outils de contrôle Mac doivent garder `stop_pc_task` et timeout actif.
- Les actions lancées depuis Telegram/WhatsApp ont moins de permissions que la session locale.
- Le workspace doit journaliser les actions importantes dans `workspace_events`.

Confirmation UX :

```text
ADA veut envoyer un email à X avec le contenu Y.
Confirmer / Annuler
```

Choix technique : journaliser les décisions de sécurité facilite le debug et protège contre les actions ambiguës.

---

## Mémoire et contexte

Règles :
- Les notes et sources restent dans le workspace.
- Les préférences durables de Bryan vont dans `memory_manager.py`.
- Les décisions importantes peuvent être dupliquées : note projet + mémoire longue si ADA juge qu'elles seront utiles plus tard.
- Les recherches profondes doivent produire un artifact markdown dans `workspace/artifacts/`.

Choix technique : la séparation workspace/mémoire empêche une recherche temporaire de devenir une croyance permanente d'ADA.

---

## Critères d'acceptation V1

1. Bryan peut créer un workspace depuis l'UI ou la voix.
2. Bryan peut lancer une recherche Internet sans quitter ADA.
3. ADA affiche la progression de la recherche dans l'UI.
4. ADA sauvegarde au moins les sources, une synthèse et un artifact markdown.
5. Bryan peut ouvrir la synthèse depuis le panneau fichiers.
6. ADA peut lancer une mission navigateur et afficher les logs.
7. Les actions sensibles déclenchent une confirmation.
8. Les outils retournent toujours une `str` côté Gemini.
9. Les tests unitaires couvrent `WorkspaceManager` et `WorkspacePolicy`.
10. Un test manuel complet est documenté dans le plan d'implémentation.

---

## Plan d'implémentation recommandé

### Phase 1 — Fondations workspace

- Créer `workspace_manager.py`.
- Créer SQLite manifest.
- Ajouter tests unitaires path safety + CRUD items.
- Ajouter endpoints REST lecture/écriture.

### Phase 2 — UI cockpit

- Ajouter `WorkspaceShell`.
- Ajouter panneaux recherche, fichiers, activité.
- Brancher `workspace_state` et `workspace_item_created`.

### Phase 3 — Recherche Internet intégrée

- Créer `workspace_research_agent.py`.
- Brancher `research_agent.py` + sources web.
- Sauvegarder synthèses et sources.
- Ajouter tool `workspace_research`.

### Phase 4 — Browser dans ADA

- Brancher `workspace_open_browser` sur `advanced_browser_agent.py`.
- Afficher logs et résultats dans `BrowserPanel`.
- Sauvegarder résultat optionnel dans le workspace.

### Phase 5 — Policy sécurité

- Créer `workspace_policy.py`.
- Centraliser confirmations.
- Différencier permissions local UI vs bridge texte.

### Phase 6 — Polish OS feel

- Ajouter commandes rapides.
- Ajouter recherche dans workspace.
- Ajouter timeline claire.
- Ajouter export markdown.

---

## Tests

Tests unitaires :
- `tests/test_workspace_manager.py`
- `tests/test_workspace_policy.py`
- `tests/test_workspace_research_agent.py` avec mocks

Tests manuels :
- Créer workspace "test recherche".
- Lancer recherche quick.
- Vérifier sources + artifact.
- Lancer navigation simple.
- Vérifier logs UI.
- Tenter suppression ou envoi externe et vérifier confirmation.

Choix technique : les tests unitaires couvrent les garanties de sécurité, les tests manuels couvrent l'expérience temps réel.

---

## Risques

| Risque | Mitigation |
|---|---|
| ADA devient trop autonome | Policy centrale + confirmations strictes |
| UI trop chargée | Panneaux repliables et vues par onglets |
| Recherche web peu fiable | Sauvegarder sources + scores + dates |
| Sessions navigateur sensibles | Cookies dans `projects/browser_session`, confirmation avant comptes connectés |
| Pollution mémoire | Séparer workspace temporaire et mémoire longue |
| Latence des tâches longues | Tools `NON_BLOCKING` + events de progression |

---

## Definition of Done

La feature est considérée livrée quand Bryan peut rester dans ADA pour :

1. créer un workspace ;
2. chercher sur Internet ;
3. lire et comparer les sources ;
4. sauvegarder notes et synthèses ;
5. piloter une mission navigateur ;
6. retrouver les résultats plus tard ;
7. voir ce qu'ADA fait en temps réel ;
8. garder le contrôle sur les actions sensibles.

