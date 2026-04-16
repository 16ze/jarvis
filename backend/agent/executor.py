"""
executor.py — Exécute une liste d'étapes planifiées, avec replanification sur échec.

Pattern : reçoit les steps du TaskPlanner, appelle tool_fn pour chaque step.
En cas d'échec, demande à Gemini une action alternative (max 3 tentatives/step).
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

MODEL = "gemini-2.5-flash"
MAX_RETRIES = 3

# Signature du callable outil : async (tool_name, args) -> str
ToolFn = Callable[[str, dict[str, Any]], Coroutine[Any, Any, str]]


def _is_error(result: str) -> bool:
    """Retourne True si le résultat indique une erreur."""
    lowered = result.lower()
    return "erreur" in lowered or "error" in lowered or "failed" in lowered or "échec" in lowered


@dataclass
class ExecutionResult:
    """Résultat complet d'une exécution de plan."""

    success: bool
    results: list[str] = field(default_factory=list)
    final_message: str = ""


_REPLAN_SYSTEM = """Tu es un assistant de récupération d'erreur pour Ada.
Un step d'exécution a échoué. Propose UNE action alternative sous forme JSON :
{
  "description": "description courte de l'action alternative",
  "tool": "<outil parmi execute_pc_task|run_terminal|run_web_agent|search_memory|remember>",
  "args": {<arguments spécifiques à l'outil>}
}

Règles de mapping :
- execute_pc_task → args: {"task_description": "..."}
- run_terminal → args: {"command": "...", "working_dir": "..."}
- run_web_agent → args: {"mission": "..."}
- search_memory → args: {"query": "..."}
- remember → args: {"information": "..."}

Réponds UNIQUEMENT avec le JSON (sans markdown, sans explication)."""


class TaskExecutor:
    """Exécute une liste de steps avec gestion d'erreur et replanification."""

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY non configurée.")
        self._client = genai.Client(api_key=api_key)

    async def _replan_step(
        self,
        step: dict[str, Any],
        error_msg: str,
        attempt: int,
    ) -> dict[str, Any]:
        """
        Demande à Gemini une action alternative pour un step ayant échoué.

        Args:
            step: Le step original.
            error_msg: Le message d'erreur retourné.
            attempt: Numéro de la tentative courante.

        Returns:
            Nouveau step alternatif, ou le step original en cas d'échec de replanification.
        """
        prompt = (
            f"Step original : {json.dumps(step, ensure_ascii=False)}\n"
            f"Erreur reçue : {error_msg}\n"
            f"Tentative numéro {attempt}/{MAX_RETRIES}.\n"
            "Propose une action alternative."
        )

        try:
            response = await asyncio.to_thread(
                self._client.models.generate_content,
                model=MODEL,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part(text=prompt)],
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=_REPLAN_SYSTEM,
                    temperature=0.2,
                ),
            )

            raw = response.text.strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                raw = "\n".join(lines[1:]).rstrip("`").strip()

            alt: dict[str, Any] = json.loads(raw)
            return {
                "step_num": step.get("step_num", 0),
                "description": str(alt.get("description", step.get("description", ""))),
                "tool": str(alt.get("tool", step.get("tool", "execute_pc_task"))),
                "args": alt.get("args", step.get("args", {})),
            }

        except json.JSONDecodeError as e:
            print(f"[TaskExecutor] Replan JSON invalide : {e}")
            return step

        except Exception as e:
            print(f"[TaskExecutor] Erreur replan Gemini : {e}")
            return step

    async def execute(
        self,
        steps: list[dict[str, Any]],
        tool_fn: ToolFn,
    ) -> ExecutionResult:
        """
        Exécute chaque step via tool_fn avec gestion des échecs.

        Args:
            steps: Liste de steps produits par TaskPlanner.
            tool_fn: Callable async (tool_name, args) -> str.

        Returns:
            ExecutionResult avec success, results par step et final_message.
        """
        if not steps:
            return ExecutionResult(
                success=False,
                results=[],
                final_message="Aucun step à exécuter.",
            )

        results: list[str] = []
        all_success = True

        for step in steps:
            tool_name: str = step.get("tool", "execute_pc_task")
            args: dict[str, Any] = step.get("args", {})
            description: str = step.get("description", "")
            step_num: int = step.get("step_num", 0)

            print(f"[TaskExecutor] Step {step_num} — {description} (outil: {tool_name})")

            current_step = step
            result = ""
            step_success = False

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    result = await tool_fn(
                        current_step.get("tool", tool_name),
                        current_step.get("args", args),
                    )
                except Exception as e:
                    result = f"Erreur inattendue : {e}"

                if not _is_error(result):
                    step_success = True
                    print(f"[TaskExecutor] Step {step_num} — OK (tentative {attempt})")
                    break

                print(f"[TaskExecutor] Step {step_num} — Échec tentative {attempt} : {result[:120]}")

                if attempt < MAX_RETRIES:
                    current_step = await self._replan_step(current_step, result, attempt)

            results.append(result)

            if not step_success:
                all_success = False
                print(f"[TaskExecutor] Step {step_num} — Abandon après {MAX_RETRIES} tentatives.")

        # Construire le message final
        total = len(steps)
        succeeded = sum(1 for r in results if not _is_error(r))

        if all_success:
            final_message = f"Toutes les étapes accomplies ({total}/{total})."
        else:
            final_message = f"{succeeded}/{total} étapes réussies."

        return ExecutionResult(
            success=all_success,
            results=results,
            final_message=final_message,
        )
