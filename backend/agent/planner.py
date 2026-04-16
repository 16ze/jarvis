"""
planner.py — Décompose une tâche en langage naturel en liste d'étapes JSON.

Utilise Gemini 2.5 Flash pour la décomposition multi-steps.
Les tâches simples (sans mots de séquence) retournent 1 step sans appel API.
"""

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = "gemini-2.5-flash"

# Mots déclenchant une décomposition multi-steps
_SEQUENCE_WORDS = re.compile(
    r"\b(puis|ensuite|après|apres|et\s+(?:ensuite|après|apres|puis)|alors|finalement|"
    r"d'abord|premièrement|deuxièmement|enfin|avant\s+de|puis\s+que|"
    r"first|then|after\s+that|next|finally|afterwards)\b",
    re.IGNORECASE,
)

# Outils disponibles pour Ada
_KNOWN_TOOLS = [
    "execute_pc_task",
    "run_terminal",
    "run_web_agent",
    "search_memory",
    "remember",
]

_SYSTEM_PROMPT = """Tu es un planificateur de tâches pour Ada, assistant IA personnel.
Tu reçois une description de tâche en langage naturel et tu la décomposes en étapes atomiques.

Réponds UNIQUEMENT avec un tableau JSON valide (sans markdown, sans explication).
Chaque élément du tableau doit avoir exactement ces clés :
- "step_num" : entier commençant à 1
- "description" : description courte de l'étape en français
- "tool" : l'outil à utiliser parmi """ + str(_KNOWN_TOOLS) + """
- "args" : objet JSON avec les arguments spécifiques à l'outil

Règles de mapping des outils :
- execute_pc_task → args: {"task_description": "..."}  (actions visibles sur l'écran Mac)
- run_terminal → args: {"command": "...", "working_dir": "..."}  (commandes shell)
- run_web_agent → args: {"mission": "..."}  (recherche silencieuse en arrière-plan)
- search_memory → args: {"query": "..."}  (chercher dans la mémoire Ada)
- remember → args: {"information": "..."}  (mémoriser une information)

Exemple pour "ouvre Chrome puis va sur YouTube" :
[
  {"step_num": 1, "description": "Ouvrir Chrome", "tool": "execute_pc_task", "args": {"task_description": "Ouvrir Chrome"}},
  {"step_num": 2, "description": "Naviguer vers YouTube", "tool": "execute_pc_task", "args": {"task_description": "Dans Chrome, aller sur youtube.com"}}
]"""


class TaskPlanner:
    """Décompose une tâche en langage naturel en liste d'étapes structurées."""

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY non configurée.")
        self._client = genai.Client(api_key=api_key)

    def _is_simple_task(self, task: str) -> bool:
        """Retourne True si la tâche ne contient pas de mots de séquence."""
        return _SEQUENCE_WORDS.search(task) is None

    def _build_single_step(self, task: str) -> list[dict[str, Any]]:
        """Construit un step unique sans appeler Gemini."""
        return [
            {
                "step_num": 1,
                "description": task,
                "tool": "execute_pc_task",
                "args": {"task_description": task},
            }
        ]

    async def plan(self, task: str) -> list[dict[str, Any]]:
        """
        Décompose la tâche en étapes JSON.

        Args:
            task: Description de la tâche en langage naturel.

        Returns:
            Liste de steps avec keys step_num, description, tool, args.
            Retourne toujours au moins 1 step, jamais d'exception.
        """
        if not task.strip():
            return self._build_single_step("Tâche vide.")

        # Heuristique : tâche simple → 1 step sans Gemini
        if self._is_simple_task(task):
            return self._build_single_step(task)

        # Tâche complexe → décomposition via Gemini
        try:
            import asyncio

            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=MODEL,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part(text=f"Tâche à décomposer : {task}")],
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    temperature=0.1,
                ),
            )

            raw = response.text.strip()

            # Nettoyer les balises markdown éventuelles
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:]).rstrip("`").strip()

            steps: list[dict[str, Any]] = json.loads(raw)

            # Validation minimale de la structure
            validated: list[dict[str, Any]] = []
            for i, step in enumerate(steps, start=1):
                if not isinstance(step, dict):
                    continue
                validated.append(
                    {
                        "step_num": step.get("step_num", i),
                        "description": str(step.get("description", "")),
                        "tool": str(step.get("tool", "execute_pc_task")),
                        "args": step.get("args", {"task_description": str(step.get("description", task))}),
                    }
                )

            if not validated:
                return self._build_single_step(task)

            return validated

        except json.JSONDecodeError as e:
            print(f"[TaskPlanner] JSON invalide : {e}")
            return self._build_single_step(task)

        except Exception as e:
            print(f"[TaskPlanner] Erreur Gemini : {e}")
            return self._build_single_step(task)
