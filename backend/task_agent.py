"""
TaskAgent — Sub-agent d'exécution d'objectifs complexes.

Flow :
  1. Decompose : Gemini transforme l'objectif en sous-tâches JSON ordonnées
  2. Execute   : boucle d'exécution — terminal ou Gemini, avec contexte cumulé
  3. Report    : Gemini produit un rapport de complétion

Types de sous-tâches :
  - "terminal"    : commande shell exécutée via asyncio.to_thread + subprocess
  - "gemini_only" : raisonnement / génération pure via Gemini

Usage depuis ada.py :
    result = await self.task_agent.run("Crée un fichier README pour le projet courant")
"""

import asyncio
import json
import os
import re
import subprocess

from google import genai

SUB_MODEL = "gemini-2.0-flash-lite"
_MAX_ITERATIONS = 10
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


class TaskAgent:
    def __init__(self):
        pass

    # ─── PUBLIC ──────────────────────────────────────────────────────────────

    async def run(self, objective: str) -> str:
        """Décompose et exécute `objective`. Retourne un rapport de complétion."""
        subtasks = await self._decompose(objective)
        if not subtasks:
            return f"Impossible de décomposer l'objectif : {objective}"
        results = await self._execute(subtasks)
        return await self._report(objective, results)

    # ─── PRIVATE ─────────────────────────────────────────────────────────────

    async def _decompose(self, objective: str) -> list[dict]:
        """Passe 1 : décomposition Gemini en sous-tâches."""
        response = await _client.aio.models.generate_content(
            model=SUB_MODEL,
            contents=(
                "Tu es un agent d'exécution. Décompose l'objectif suivant en sous-tâches "
                "ordonnées et concrètes.\n\n"
                f"Objectif : {objective}\n\n"
                "Réponds UNIQUEMENT avec un JSON valide :\n"
                '{"subtasks": ['
                '{"id": 1, "description": "...", "type": "terminal|gemini_only", '
                '"command": "..."}]}\n'
                'Le champ "command" est obligatoire uniquement si type=terminal.'
            ),
        )
        try:
            m = re.search(r"\{.*\}", response.text, re.DOTALL)
            plan = json.loads(m.group())
            return plan.get("subtasks", [])
        except Exception:
            return []

    async def _execute(self, subtasks: list[dict]) -> list[str]:
        """Passe 2 : exécute chaque sous-tâche séquentiellement."""
        results: list[str] = []

        for task in subtasks[:_MAX_ITERATIONS]:
            desc = task.get("description", "")
            task_type = task.get("type", "gemini_only")

            if task_type == "terminal":
                output = await self._run_terminal(task.get("command", ""))
                results.append(f"[terminal] {desc}\n→ {output[:500]}")

            else:
                context = "\n".join(results[-3:]) if results else ""
                response = await _client.aio.models.generate_content(
                    model=SUB_MODEL,
                    contents=(
                        f"Contexte des étapes précédentes :\n{context}\n\n"
                        f"Tâche : {desc}\n\n"
                        "Effectue cette tâche et fournis un résultat concis."
                    ),
                )
                results.append(f"[gemini] {desc}\n→ {response.text[:500]}")

        return results

    async def _run_terminal(self, command: str) -> str:
        """Exécute une commande shell, retourne stdout/stderr tronqué."""
        if not command:
            return "(commande vide)"
        try:
            proc = await asyncio.to_thread(
                subprocess.run,
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            out = proc.stdout.strip() or ""
            err = proc.stderr.strip() or ""
            return (out + ("\n[stderr]: " + err if err else "")).strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return "Erreur : commande expirée (>30s)."
        except Exception as e:
            return f"Erreur : {str(e)}"

    async def _report(self, objective: str, results: list[str]) -> str:
        """Passe 3 : rapport de complétion Gemini."""
        response = await _client.aio.models.generate_content(
            model=SUB_MODEL,
            contents=(
                f"Objectif initial : {objective}\n\n"
                "Actions effectuées :\n"
                + "\n".join(results)
                + "\n\nRédige un rapport de complétion concis en français : "
                "ce qui a été fait, ce qui a réussi, ce qui a échoué, "
                "et les prochaines étapes recommandées si nécessaire."
            ),
        )
        return response.text
