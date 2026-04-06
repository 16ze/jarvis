# Ada Self-Evolution Agent — Design Spec
**Date** : 2026-04-07  
**Statut** : Approuvé  
**Scope** : System prompt refactor + self_evolution_agent.py + restart automatique

---

## Contexte

Ada dispose d'un `self_correction_agent.py` qui corrige des bugs dans le code existant. Ce design étend Ada avec la capacité de **créer de nouveaux outils** quand elle détecte qu'un service lui manque, puis de **se redémarrer automatiquement** pour les activer.

---

## 1. System Prompt — Refactor

### Problème
Le prompt actuel (~560 lignes) contient des instructions redondantes par outil (terminal, Gmail, domotique…) qui dupliquent ce que les descriptions de tools décrivent déjà. Gemini "lit" trop avant d'agir, créant une latence perçue.

### Changements
- **Supprimer** : instructions par outil (terminal, Gmail, agenda, web agent, domotique, imprimante 3D, communication, productivité, dev/infra, musique/santé)
- **Garder** : identité Ada, règle de langue, personnalité, règle d'action immédiate, mémoire, self-correction
- **Reformuler** : règle d'action en une ligne en tête de prompt, sans numérotation "RÈGLE ABSOLUE"
- **Résultat visé** : ~40% plus court, appels d'outils immédiats sans hésitation

### Structure cible
```
[IDENTITÉ] Tu t'appelles Ada...
[LANGUE] Français exclusivement.
[ACTION] Quand tu as un outil pour une tâche → utilise-le immédiatement, sans annoncer ce que tu vas faire.
[PERSONNALITÉ] Directe, critique, concise.
[MÉMOIRE] Utilise search_memory / remember proactivement.
[SELF-EVOLUTION] Si tu n'as pas l'outil pour une mission → appelle self_evolve.
[SELF-CORRECTION] Si tu détectes une erreur dans ton code → self_correct_file.
```

---

## 2. Self-Evolution Agent

### Fichier
`backend/self_evolution_agent.py`

### Déclencheur
Ada essaie d'accomplir une tâche, échoue (outil manquant ou "non disponible"), puis appelle :
```
self_evolve(
    goal="ce que je voulais accomplir",
    failed_context="ce qui a échoué et pourquoi"
)
```

### Workflow (6 étapes)

#### Étape 1 — ANALYZE
Gemini 2.5 Flash reçoit `goal` + `failed_context` et retourne un JSON structuré :
```json
{
  "service_name": "stripe",
  "python_lib": "stripe",
  "pip_package": "stripe",
  "doc_urls": ["https://stripe.com/docs/api", "https://pypi.org/project/stripe/"],
  "tools_needed": ["stripe_create_payment", "stripe_list_subscriptions"],
  "file_name": "stripe_mcp.py"
}
```

#### Étape 2 — RESEARCH
Pour chaque `doc_url`, appelle `run_web_agent` pour scraper la documentation Python. Concatène les extraits pertinents (max 8000 tokens).

#### Étape 3 — GENERATE
Gemini 2.5 Flash reçoit en contexte :
- La doc scrapée
- Un exemple de MCP complet (`spotify_mcp.py` comme template)
- Un exemple de déclarations (`mcp_tools_declarations.py` — bloc spotify)
- Un exemple de dispatch (`ada.py` — bloc `elif n == "spotify_*"`)
- Les règles du projet : `async def method() -> str`, jamais d'exception non catchée, retour toujours `str`, imports lazy

Gemini génère **4 blocs délimités** :
```
===MCP_FILE===
<contenu complet de backend/mcps/{service}_mcp.py>
===DECLARATIONS===
<nouvelles déclarations + ajout dans MCP_TOOLS>
===DISPATCH===
<bloc elif à insérer dans _execute_text_tool de ada.py>
===INIT===
<ligne d'init à insérer dans _init_agents de external_bridge.py>
```

#### Étape 4 — VALIDATE (max 3 essais)
Pour chaque essai :
1. Écrit le MCP dans un fichier temporaire
2. Lance `python -c "import ast; ast.parse(open('tmp').read())"` (syntaxe)
3. Lance `python -c "import tmp_module"` (import réel en subprocess isolé)
4. Si échec → renvoie le code + l'erreur à Gemini pour correction
5. Si 3 échecs → escalade Telegram, aucun fichier déployé

#### Étape 5 — WRITE
Séquence atomique :
1. `_git_backup()` (pattern SelfCorrectionAgent)
2. Écriture `backend/mcps/{service}_mcp.py`
3. Injection dans `mcp_tools_declarations.py` (append déclarations + insert dans `MCP_TOOLS`)
4. Injection dans `ada.py` (insert dans le bloc dispatch `elif name in MCP_TOOL_NAMES`)
5. Injection dans `external_bridge.py` (insert dans `_init_agents`)
6. `git commit -m "feat: auto-evolution Ada — ajout {service}_mcp"`

#### Étape 6 — RESTART
```python
subprocess.Popen(
    ["bash", "/Users/bryandev/jarvis/backend/restart_ada.sh"],
    start_new_session=True  # détaché du process Ada
)
return f"Outil '{service}' créé et intégré. Je redémarre dans 3 secondes."
```

### restart_ada.sh
```bash
#!/bin/bash
sleep 3
pkill -f "python server.py" || true
sleep 2
cd /Users/bryandev/jarvis/backend
conda run -n ada_v2 --no-capture-output python server.py \
    > /tmp/ada_server.log 2>&1 &
```

---

## 3. Nouvel outil Gemini — `self_evolve`

### Déclaration (mcp_tools_declarations.py)
```python
self_evolve_tool = {
    "name": "self_evolve",
    "description": (
        "Crée automatiquement un nouveau connecteur MCP quand Ada n'a pas l'outil "
        "pour accomplir une mission. Appelle cet outil UNIQUEMENT après avoir constaté "
        "qu'aucun outil existant ne peut accomplir la tâche. Ada se redémarre "
        "automatiquement après création pour activer le nouvel outil."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {
                "type": "STRING",
                "description": "Ce que tu voulais accomplir (ex: 'envoyer un SMS via Twilio')"
            },
            "failed_context": {
                "type": "STRING", 
                "description": "Ce qui a échoué et pourquoi (outil manquant, erreur reçue)"
            }
        },
        "required": ["goal", "failed_context"]
    }
}
```

### Wiring
- `mcp_tools_declarations.py` : déclaration + ajout dans `MCP_TOOLS`
- `ada.py` : `elif name == "self_evolve": return await self.evolution_agent.evolve(args)`
- `external_bridge.py` : même dispatch dans `_execute_tool`
- `ada.py __init__` : `self.evolution_agent = SelfEvolutionAgent(run_web_agent_fn=...)`

---

## 4. Sécurité & Contraintes

| Contrainte | Implémentation |
|---|---|
| Path traversal | Toutes les écritures validées contre `JARVIS_ROOT` |
| Syntaxe invalide | `ast.parse()` avant tout déploiement |
| Import échoue | Subprocess isolé, max 3 essais avec correction Gemini |
| Déploiement raté × 3 | Escalade Telegram, aucun fichier modifié |
| Redémarrage | Script détaché (`start_new_session=True`), délai 3s |
| Git | Backup automatique avant chaque écriture |

---

## 5. Fichiers modifiés / créés

| Fichier | Action |
|---|---|
| `backend/self_evolution_agent.py` | Créer |
| `backend/restart_ada.sh` | Créer |
| `backend/mcp_tools_declarations.py` | Ajouter `self_evolve_tool` + dans `MCP_TOOLS` |
| `backend/ada.py` | System prompt refactor + wiring `self_evolve` + init |
| `backend/external_bridge.py` | Wiring `self_evolve` dans `_execute_tool` |

---

## 6. Hors scope

- Rechargement dynamique sans redémarrage (volontairement écarté)
- Tests automatisés du MCP généré au-delà de l'import test
- UI pour visualiser les MCPs générés
- Rollback automatique si le MCP généré casse le serveur au redémarrage
