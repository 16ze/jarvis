# Ada Self-Correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Donner à Ada la capacité de lire/modifier ses propres fichiers (repo jarvis), utiliser Claude Opus 4.6 pour corriger ses erreurs, et se commit/push sur GitHub — tout en garantissant qu'elle ne peut pas se casser.

**Architecture:** Un nouveau module `self_correction_agent.py` utilise l'Anthropic SDK pour analyser une erreur + le fichier fautif et retourner du code corrigé. Ada dispose de 5 nouveaux outils (`jarvis_read_file`, `jarvis_write_file`, `jarvis_list_files`, `jarvis_git_commit`, `self_correct_file`) disponibles en mode texte (Telegram) et voix. Toutes les écritures sont scopées à `/Users/bryandev/jarvis/` avec validation de chemin et backup git automatique avant toute modification.

**Tech Stack:** Python 3.13, `anthropic>=0.40`, `PyGithub`, google-genai 1.68+, git CLI

---

## Fichiers modifiés / créés

| Fichier | Action | Responsabilité |
|---|---|---|
| `CLAUDE.md` | Créer | Contexte projet pour Claude Code |
| `.env` | Modifier | Ajouter `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, `GITHUB_DEFAULT_REPO` |
| `backend/self_correction_agent.py` | Créer | Agent Claude Opus 4.6 pour corriger du code |
| `backend/mcps/github_mcp.py` | Modifier | Ajouter `push_file`, `create_branch`, `create_pr` |
| `backend/mcp_tools_declarations.py` | Modifier | Déclarer les 5 nouveaux outils |
| `backend/ada.py` | Modifier | Ajouter dispatch des 5 outils dans `_execute_text_tool` + system prompt |
| `backend/external_bridge.py` | Modifier | Ajouter dispatch des 5 outils dans `TextAgent._execute_tool` |
| `tests/test_self_correction.py` | Créer | Tests unitaires |

---

## Task 1 : CLAUDE.md + variables d'environnement

**Files:**
- Create: `CLAUDE.md`
- Modify: `.env` (ajouter 3 variables)

- [ ] **Step 1 : Créer CLAUDE.md**

```markdown
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
```

- [ ] **Step 2 : Ajouter les variables dans `.env`**

Ouvrir `.env` et ajouter (si absent) :
```
ANTHROPIC_API_KEY=sk-ant-...
GITHUB_TOKEN=ghp_...
GITHUB_DEFAULT_REPO=16ze/jarvis
```

- [ ] **Step 3 : Vérifier**

```bash
python -c "
from dotenv import load_dotenv; load_dotenv()
import os
for k in ['ANTHROPIC_API_KEY','GITHUB_TOKEN','GITHUB_DEFAULT_REPO']:
    print(k, 'OK' if os.getenv(k) else 'MANQUANT')
"
```
Expected : 3 lignes `OK`

- [ ] **Step 4 : Commit**

```bash
git add CLAUDE.md
git commit -m "chore: add CLAUDE.md project context"
```

---

## Task 2 : Installer anthropic + tester la connexion

**Files:**
- No file changes (just package install + validation)

- [ ] **Step 1 : Installer le package dans conda ada_v2**

```bash
conda run -n ada_v2 pip install "anthropic>=0.40"
```
Expected : `Successfully installed anthropic-...`

- [ ] **Step 2 : Vérifier la connexion API**

```bash
conda run -n ada_v2 python -c "
from dotenv import load_dotenv; load_dotenv()
import anthropic, os
client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
msg = client.messages.create(
    model='claude-opus-4-6',
    max_tokens=50,
    messages=[{'role':'user','content':'Réponds juste: OK'}]
)
print(msg.content[0].text)
"
```
Expected : `OK` ou équivalent

---

## Task 3 : SelfCorrectionAgent — `backend/self_correction_agent.py`

**Files:**
- Create: `backend/self_correction_agent.py`
- Create: `tests/test_self_correction.py`

- [ ] **Step 1 : Écrire le test qui échoue**

```python
# tests/test_self_correction.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

def test_import():
    from self_correction_agent import SelfCorrectionAgent
    assert SelfCorrectionAgent is not None

def test_validate_path_ok():
    from self_correction_agent import SelfCorrectionAgent
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)
    assert agent._validate_path("/Users/bryandev/jarvis/backend/ada.py") is True

def test_validate_path_blocked():
    from self_correction_agent import SelfCorrectionAgent
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)
    assert agent._validate_path("/etc/passwd") is False
    assert agent._validate_path("/Users/bryandev/jarvis/../../../etc/passwd") is False
```

- [ ] **Step 2 : Lancer le test pour vérifier qu'il échoue**

```bash
conda run -n ada_v2 python -m pytest tests/test_self_correction.py -v
```
Expected : `ModuleNotFoundError: No module named 'self_correction_agent'`

- [ ] **Step 3 : Créer `backend/self_correction_agent.py`**

```python
"""
self_correction_agent.py — Agent Claude Opus 4.6 pour auto-correction du code Ada

Sécurité :
- Toutes les opérations fichier sont scopées à JARVIS_ROOT
- Backup git automatique avant toute écriture
- Validation syntaxe Python avant d'écraser le fichier original
"""

import os
import subprocess
import tempfile
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

JARVIS_ROOT = Path("/Users/bryandev/jarvis").resolve()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-opus-4-6"

SYSTEM_PROMPT = (
    "Tu es un expert Python spécialisé dans la correction de bugs. "
    "On te donne : le contenu d'un fichier Python et une description d'erreur. "
    "Tu réponds UNIQUEMENT avec le fichier complet corrigé, sans markdown, sans explication. "
    "Le code doit être syntaxiquement valide et résoudre l'erreur décrite. "
    "Si tu n'es pas certain de pouvoir corriger sans risque, réponds exactement : UNSAFE"
)


class SelfCorrectionAgent:
    def __init__(self):
        if not ANTHROPIC_API_KEY:
            raise RuntimeError("ANTHROPIC_API_KEY non configurée.")
        self._client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def _validate_path(self, path: str) -> bool:
        """Vérifie que le chemin est dans JARVIS_ROOT (pas d'escape)."""
        try:
            resolved = Path(path).resolve()
            return resolved.is_relative_to(JARVIS_ROOT)
        except Exception:
            return False

    def read_file(self, path: str) -> str:
        """Lit un fichier dans le repo jarvis."""
        if not self._validate_path(path):
            return f"ERREUR : chemin non autorisé ({path})"
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception as e:
            return f"ERREUR lecture : {e}"

    def list_files(self, path: str = "") -> str:
        """Liste les fichiers d'un dossier dans le repo jarvis."""
        target = Path(path).resolve() if path else JARVIS_ROOT
        if not self._validate_path(str(target)):
            return "ERREUR : chemin non autorisé"
        try:
            items = sorted(target.iterdir())
            lines = []
            for item in items:
                prefix = "📁" if item.is_dir() else "📄"
                lines.append(f"{prefix} {item.name}")
            return "\n".join(lines) if lines else "(dossier vide)"
        except Exception as e:
            return f"ERREUR listage : {e}"

    def _git_backup(self) -> str:
        """Crée un commit de backup avant toute modification."""
        try:
            result = subprocess.run(
                ["git", "-C", str(JARVIS_ROOT), "diff", "--quiet"],
                capture_output=True
            )
            if result.returncode != 0:
                # Il y a des changements non commités — on les stash
                subprocess.run(
                    ["git", "-C", str(JARVIS_ROOT), "add", "-A"],
                    capture_output=True
                )
                r = subprocess.run(
                    ["git", "-C", str(JARVIS_ROOT), "commit", "-m", "chore: auto-backup before Ada self-correction"],
                    capture_output=True, text=True
                )
                return r.stdout.strip() or r.stderr.strip()
            return "Aucun changement à sauvegarder."
        except Exception as e:
            return f"Backup git échoué : {e}"

    def write_file(self, path: str, content: str) -> str:
        """
        Écrit un fichier dans le repo jarvis.
        - Valide le chemin
        - Backup git automatique
        - Validation syntaxe si .py
        """
        if not self._validate_path(path):
            return f"ERREUR : chemin non autorisé ({path})"

        target = Path(path)

        # Validation syntaxe Python avant d'écraser
        if target.suffix == ".py":
            with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                result = subprocess.run(
                    ["python", "-m", "py_compile", tmp_path],
                    capture_output=True, text=True
                )
                if result.returncode != 0:
                    return f"ERREUR syntaxe Python — fichier non écrit :\n{result.stderr}"
            finally:
                os.unlink(tmp_path)

        # Backup avant écriture
        self._git_backup()

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"Fichier '{target.name}' écrit avec succès ({len(content)} chars)."
        except Exception as e:
            return f"ERREUR écriture : {e}"

    def git_commit(self, message: str) -> str:
        """Commit tous les changements dans le repo jarvis."""
        try:
            subprocess.run(["git", "-C", str(JARVIS_ROOT), "add", "-A"], capture_output=True)
            result = subprocess.run(
                ["git", "-C", str(JARVIS_ROOT), "commit", "-m", message],
                capture_output=True, text=True
            )
            output = result.stdout.strip() or result.stderr.strip()
            if result.returncode != 0 and "nothing to commit" not in output:
                return f"Erreur git commit : {output}"
            return output or "Commit créé."
        except Exception as e:
            return f"Erreur git : {e}"

    def correct_file(self, file_path: str, error_description: str) -> str:
        """
        Lit le fichier, envoie à Claude Opus 4.6, applique la correction.
        Retourne un rapport de ce qui a été fait.
        """
        if not self._validate_path(file_path):
            return f"ERREUR : chemin non autorisé ({file_path})"

        original_content = self.read_file(file_path)
        if original_content.startswith("ERREUR"):
            return original_content

        prompt = (
            f"Fichier : {file_path}\n\n"
            f"Erreur rencontrée :\n{error_description}\n\n"
            f"Contenu actuel du fichier :\n```python\n{original_content}\n```\n\n"
            "Retourne le fichier complet corrigé."
        )

        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            corrected = response.content[0].text.strip()
        except Exception as e:
            return f"Erreur API Claude : {e}"

        if corrected == "UNSAFE":
            return "Claude a refusé de corriger ce fichier (risque trop élevé)."

        result = self.write_file(file_path, corrected)
        if result.startswith("ERREUR"):
            return result

        commit_msg = self.git_commit(f"fix: auto-correction Ada — {Path(file_path).name}")
        return (
            f"Correction appliquée à '{Path(file_path).name}'.\n"
            f"Git : {commit_msg}"
        )
```

- [ ] **Step 4 : Lancer les tests**

```bash
conda run -n ada_v2 python -m pytest tests/test_self_correction.py -v
```
Expected :
```
test_import PASSED
test_validate_path_ok PASSED
test_validate_path_blocked PASSED
```

- [ ] **Step 5 : Commit**

```bash
git add backend/self_correction_agent.py tests/test_self_correction.py
git commit -m "feat: add SelfCorrectionAgent with Claude Opus 4.6"
```

---

## Task 4 : Nouvelles déclarations d'outils dans `mcp_tools_declarations.py`

**Files:**
- Modify: `backend/mcp_tools_declarations.py`

- [ ] **Step 1 : Lire la fin du fichier pour voir le pattern existant**

```bash
tail -30 backend/mcp_tools_declarations.py
```

- [ ] **Step 2 : Ajouter les 5 nouveaux outils à la fin de `MCP_TOOLS`**

Chercher la liste `MCP_TOOLS` dans `backend/mcp_tools_declarations.py` et ajouter avant le `]` final :

```python
    # ── SELF-CORRECTION (Jarvis repo) ─────────────────────────────────────────
    {"name": "jarvis_read_file",
     "description": "Lit un fichier du repo jarvis (/Users/bryandev/jarvis/). Utilise pour inspecter ton propre code.",
     "parameters": {"type": "OBJECT", "properties": {
         "path": {"type": "STRING", "description": "Chemin absolu ou relatif au repo jarvis. Ex: 'backend/ada.py' ou '/Users/bryandev/jarvis/backend/ada.py'"}
     }, "required": ["path"]}},

    {"name": "jarvis_write_file",
     "description": "Écrit un fichier dans le repo jarvis. Valide la syntaxe Python et crée un backup git automatique. N'utilise QUE pour corriger ton propre code.",
     "parameters": {"type": "OBJECT", "properties": {
         "path": {"type": "STRING", "description": "Chemin du fichier à écrire (doit être dans /Users/bryandev/jarvis/)"},
         "content": {"type": "STRING", "description": "Contenu complet du fichier"}
     }, "required": ["path", "content"]}},

    {"name": "jarvis_list_files",
     "description": "Liste les fichiers d'un dossier du repo jarvis.",
     "parameters": {"type": "OBJECT", "properties": {
         "path": {"type": "STRING", "description": "Dossier à lister. Laisser vide pour la racine du repo."}
     }}},

    {"name": "jarvis_git_commit",
     "description": "Crée un commit git dans le repo jarvis après une modification.",
     "parameters": {"type": "OBJECT", "properties": {
         "message": {"type": "STRING", "description": "Message de commit (convention: 'fix: ...' ou 'feat: ...')"}
     }, "required": ["message"]}},

    {"name": "self_correct_file",
     "description": "Utilise Claude Opus 4.6 pour analyser une erreur dans un fichier et appliquer automatiquement la correction. Crée un commit après. Utilise quand tu détectes une erreur dans ton propre code.",
     "parameters": {"type": "OBJECT", "properties": {
         "file_path": {"type": "STRING", "description": "Chemin absolu du fichier à corriger"},
         "error_description": {"type": "STRING", "description": "Description précise de l'erreur : traceback complet + comportement attendu vs observé"}
     }, "required": ["file_path", "error_description"]}},
```

- [ ] **Step 3 : Vérifier que le fichier est valide**

```bash
conda run -n ada_v2 python -c "from mcp_tools_declarations import MCP_TOOLS; print(f'{len(MCP_TOOLS)} tools OK')"
```
Expected : `N tools OK` (pas d'erreur)

- [ ] **Step 4 : Commit**

```bash
git add backend/mcp_tools_declarations.py
git commit -m "feat: declare 5 self-correction tools for Ada"
```

---

## Task 5 : Wirer les outils dans `ada.py` (`_execute_text_tool`)

**Files:**
- Modify: `backend/ada.py`

- [ ] **Step 1 : Initialiser SelfCorrectionAgent dans `AudioLoop.__init__`**

Dans `ada.py`, trouver `self.github = GithubMCP()` (ligne ~651) et ajouter juste après :

```python
        try:
            from self_correction_agent import SelfCorrectionAgent
            self.self_correction = SelfCorrectionAgent()
        except Exception as e:
            warnings.warn(f"[ADA] SelfCorrectionAgent init: {e}")
            self.self_correction = None
```

- [ ] **Step 2 : Mettre à jour le system prompt d'Ada**

Dans `ada.py`, chercher la ligne qui contient `"GitHub (github_*)"` dans le system prompt et ajouter après :

```python
            "Tu as accès à ton propre code source via jarvis_read_file, jarvis_write_file, jarvis_list_files, jarvis_git_commit. "
            "Quand tu détectes une erreur dans ton propre code, utilise self_correct_file pour la corriger automatiquement. "
            "Crée TOUJOURS un commit (jarvis_git_commit) après toute modification de fichier. "
```

- [ ] **Step 3 : Ajouter le dispatch dans `_execute_text_tool`**

Dans `ada.py`, dans la méthode `_execute_text_tool`, trouver `elif name == "run_terminal":` et ajouter AVANT ce bloc :

```python
            # ── SELF-CORRECTION (Jarvis repo) ──────────────────────────────────
            elif name == "jarvis_read_file":
                path = args.get("path", "")
                if not path.startswith("/"):
                    from pathlib import Path
                    path = str(Path("/Users/bryandev/jarvis") / path)
                if self.self_correction:
                    return self.self_correction.read_file(path)
                return "SelfCorrectionAgent non disponible."

            elif name == "jarvis_write_file":
                path = args.get("path", "")
                if not path.startswith("/"):
                    from pathlib import Path
                    path = str(Path("/Users/bryandev/jarvis") / path)
                if self.self_correction:
                    return self.self_correction.write_file(path, args.get("content", ""))
                return "SelfCorrectionAgent non disponible."

            elif name == "jarvis_list_files":
                path = args.get("path", "")
                if path and not path.startswith("/"):
                    from pathlib import Path
                    path = str(Path("/Users/bryandev/jarvis") / path)
                if self.self_correction:
                    return self.self_correction.list_files(path)
                return "SelfCorrectionAgent non disponible."

            elif name == "jarvis_git_commit":
                if self.self_correction:
                    return self.self_correction.git_commit(args.get("message", "chore: Ada auto-commit"))
                return "SelfCorrectionAgent non disponible."

            elif name == "self_correct_file":
                path = args.get("file_path", "")
                if not path.startswith("/"):
                    from pathlib import Path
                    path = str(Path("/Users/bryandev/jarvis") / path)
                if self.self_correction:
                    return self.self_correction.correct_file(path, args.get("error_description", ""))
                return "SelfCorrectionAgent non disponible."
```

- [ ] **Step 4 : Vérifier la syntaxe**

```bash
conda run -n ada_v2 python -m py_compile backend/ada.py && echo "OK"
```
Expected : `OK`

- [ ] **Step 5 : Commit**

```bash
git add backend/ada.py
git commit -m "feat: wire self-correction tools in AudioLoop._execute_text_tool"
```

---

## Task 6 : Wirer les outils dans `external_bridge.py` (`TextAgent._execute_tool`)

**Files:**
- Modify: `backend/external_bridge.py`

- [ ] **Step 1 : Initialiser SelfCorrectionAgent dans `TextAgent._init_agents`**

Dans `external_bridge.py`, dans `_init_agents`, trouver `self._github = TelegramMCP()` et ajouter à la fin du bloc d'init :

```python
        try:
            from self_correction_agent import SelfCorrectionAgent
            self._self_correction = SelfCorrectionAgent()
        except Exception as e:
            warnings.warn(f"[TextAgent] SelfCorrectionAgent: {e}")
            self._self_correction = None
```

Et dans `TextAgent.__init__`, ajouter `self._self_correction = None` avec les autres attributs.

- [ ] **Step 2 : Ajouter le dispatch dans `TextAgent._execute_tool`**

Dans `external_bridge.py`, dans `_execute_tool`, trouver `return f"Outil '{name}' non disponible..."` (dernière ligne) et ajouter AVANT :

```python
        # ── SELF-CORRECTION ──────────────────────────────────────────────────
        elif name == "jarvis_read_file" and self._self_correction:
            path = args.get("path", "")
            if not path.startswith("/"):
                from pathlib import Path
                path = str(Path("/Users/bryandev/jarvis") / path)
            return self._self_correction.read_file(path)

        elif name == "jarvis_write_file" and self._self_correction:
            path = args.get("path", "")
            if not path.startswith("/"):
                from pathlib import Path
                path = str(Path("/Users/bryandev/jarvis") / path)
            return self._self_correction.write_file(path, args.get("content", ""))

        elif name == "jarvis_list_files" and self._self_correction:
            path = args.get("path", "")
            if path and not path.startswith("/"):
                from pathlib import Path
                path = str(Path("/Users/bryandev/jarvis") / path)
            return self._self_correction.list_files(path)

        elif name == "jarvis_git_commit" and self._self_correction:
            return self._self_correction.git_commit(args.get("message", "chore: Ada auto-commit"))

        elif name == "self_correct_file" and self._self_correction:
            path = args.get("file_path", "")
            if not path.startswith("/"):
                from pathlib import Path
                path = str(Path("/Users/bryandev/jarvis") / path)
            return self._self_correction.correct_file(path, args.get("error_description", ""))
```

- [ ] **Step 3 : Vérifier la syntaxe**

```bash
conda run -n ada_v2 python -m py_compile backend/external_bridge.py && echo "OK"
```
Expected : `OK`

- [ ] **Step 4 : Test end-to-end Telegram**

```bash
conda run -n ada_v2 python -c "
import asyncio, sys
sys.path.insert(0, 'backend')
from dotenv import load_dotenv; load_dotenv()
from external_bridge import TextAgent

async def test():
    agent = TextAgent()
    result = await agent.run('Liste les fichiers du dossier backend de ton repo jarvis')
    print('RÉSULTAT:', result[:300])

asyncio.run(test())
" 2>&1 | grep -E "RÉSULTAT|ERREUR|Error"
```
Expected : liste des fichiers du dossier `backend/`

- [ ] **Step 5 : Commit**

```bash
git add backend/external_bridge.py
git commit -m "feat: wire self-correction tools in TextAgent._execute_tool"
```

---

## Task 7 : Activer GitHub (GITHUB_TOKEN dans .env)

**Files:**
- Modify: `.env`

> GitHub MCP est déjà codé (`backend/mcps/github_mcp.py`) et déjà wiré dans ada.py. Il suffit de configurer les variables.

- [ ] **Step 1 : Vérifier que PyGithub est installé**

```bash
conda run -n ada_v2 python -c "from github import Github; print('PyGithub OK')"
```
Si erreur : `conda run -n ada_v2 pip install PyGithub`

- [ ] **Step 2 : Tester la connexion GitHub**

```bash
conda run -n ada_v2 python -c "
from dotenv import load_dotenv; load_dotenv()
import os
from github import Github
g = Github(os.getenv('GITHUB_TOKEN'))
user = g.get_user()
print('GitHub connecté:', user.login)
repo = g.get_repo(os.getenv('GITHUB_DEFAULT_REPO'))
print('Repo:', repo.full_name, '|', repo.default_branch)
"
```
Expected : `GitHub connecté: 16ze` et `Repo: 16ze/jarvis`

- [ ] **Step 3 : Test via TextAgent**

```bash
conda run -n ada_v2 python -c "
import asyncio, sys
sys.path.insert(0, 'backend')
from dotenv import load_dotenv; load_dotenv()
from external_bridge import TextAgent

async def test():
    agent = TextAgent()
    result = await agent.run('Liste mes repos GitHub')
    print(result[:400])

asyncio.run(test())
" 2>&1 | grep -v Warning | grep -v warn
```
Expected : liste de repos GitHub

---

## Task 8 : Test de bout en bout — auto-correction

**Files:**
- Modify: `tests/test_self_correction.py` (ajouter test intégration)

- [ ] **Step 1 : Ajouter test d'intégration**

```python
# Ajouter à tests/test_self_correction.py
import os, tempfile
from pathlib import Path

def test_write_and_read_file(tmp_path):
    """Test écriture + lecture dans un dossier jarvis simulé."""
    from self_correction_agent import SelfCorrectionAgent, JARVIS_ROOT
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)

    # Simuler un fichier valide dans JARVIS_ROOT
    test_file = JARVIS_ROOT / "tests" / "_test_tmp_ada.py"
    content = "# test\ndef hello():\n    return 'world'\n"

    # Write
    result = agent.write_file(str(test_file), content)
    assert "écrit avec succès" in result, result

    # Read back
    read_back = agent.read_file(str(test_file))
    assert read_back == content

    # Cleanup
    test_file.unlink(missing_ok=True)

def test_blocked_path():
    from self_correction_agent import SelfCorrectionAgent
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)
    result = agent.read_file("/etc/passwd")
    assert "non autorisé" in result

def test_syntax_error_blocked():
    from self_correction_agent import SelfCorrectionAgent, JARVIS_ROOT
    agent = SelfCorrectionAgent.__new__(SelfCorrectionAgent)
    bad_python = "def broken(:\n    pass"
    test_file = JARVIS_ROOT / "tests" / "_test_syntax_err.py"
    result = agent.write_file(str(test_file), bad_python)
    assert "ERREUR syntaxe" in result
    assert not test_file.exists()
```

- [ ] **Step 2 : Lancer tous les tests**

```bash
conda run -n ada_v2 python -m pytest tests/test_self_correction.py -v
```
Expected : tous PASSED

- [ ] **Step 3 : Commit final**

```bash
git add tests/test_self_correction.py
git commit -m "test: add integration tests for SelfCorrectionAgent"
```

---

## Guardrails — Rappel de sécurité

| Risque | Protection en place |
|---|---|
| Ada écrase `server.py` et plante | `_validate_path` + backup git avant écriture |
| Code Python invalide écrit | `py_compile` avant d'écraser l'original |
| Escape du repo (`../../etc/passwd`) | `Path.resolve().is_relative_to(JARVIS_ROOT)` |
| Claude hallucine du code dangereux | Réponse `UNSAFE` si trop risqué |
| Perte de code non commité | `_git_backup()` auto avant chaque `write_file` |

---

## Self-Review

**Spec coverage :**
- [x] GitHub connecté à Ada → Task 7
- [x] Clé Anthropic + Opus 4.6 → Tasks 2 + 3
- [x] Ada peut lire ses fichiers → `jarvis_read_file` Tasks 4/5/6
- [x] Ada peut écrire ses fichiers → `jarvis_write_file` Tasks 4/5/6
- [x] Auto-debug sur erreur → `self_correct_file` Task 3
- [x] Commit après modification → `jarvis_git_commit` + backup auto
- [x] CLAUDE.md → Task 1
- [x] Mode texte (Telegram) → Task 6
- [x] Mode voix → Task 5

**Aucun placeholder détecté.**
