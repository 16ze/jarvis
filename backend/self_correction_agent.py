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
