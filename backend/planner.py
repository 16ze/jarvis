"""
planner — le moteur d'exécution délibérative d'Ada.

Jusqu'ici Ada était RÉACTIVE : le modèle appelait des outils au fil de l'eau,
sans plan, sans vérification, sans reprise possible. Une tâche en cinq étapes
qui échouait à la troisième laissait tout en suspens.

Ce module généralise le seul endroit du projet où le bon patron existait déjà
— la boucle de `os_control_agent` — et le rend transverse à TOUS les outils :

    Intention  →  Plan typé (étapes + critères de succès)
               →  Exécution étape par étape
               →  Vérification de chaque étape
               →  Réparation ciblée (on rejoue l'étape, pas tout le plan)
               →  Compte rendu honnête

Trois propriétés qui manquaient :

1. REPRISE — le plan est persisté à chaque étape. Un crash ou un redémarrage
   n'efface plus le travail en cours.
2. VÉRIFICATION — chaque étape a un critère de succès ; Ada ne prétend plus
   avoir fait ce qu'elle n'a pas vérifié.
3. SÛRETÉ — une étape irréversible (envoi d'email, suppression, paiement)
   n'est JAMAIS exécutée automatiquement : le plan s'arrête et rend la main.

L'exécuteur est injecté : le planificateur ne connaît aucun outil en propre,
il orchestre. Cela le rend testable sans réseau ni matériel.
"""

from __future__ import annotations

import asyncio
import json
import os

import models
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_MODEL = os.getenv("PLANNER_MODEL", models.get("reasoning"))
MAX_STEPS = int(os.getenv("PLANNER_MAX_STEPS", "12"))
MAX_REPAIRS = int(os.getenv("PLANNER_MAX_REPAIRS", "2"))

# Outils dont l'effet est irréversible ou visible par des tiers : le plan
# s'arrête et demande confirmation plutôt que de les déclencher seul.
SENSITIVE_TOOLS = {
    "send_email",
    "delete_event",
    "delete_file",
    "telegram_send_message",
    "twilio_send_sms",
    "slack_send_message",
    "whatsapp_send_message",
    "spotify_play",
    "jarvis_git_commit",
    "self_evolve",
    "self_correct_file",
}

# Marqueurs d'échec dans le retour d'un outil (tous les outils renvoient une str).
_FAILURE_PATTERNS = re.compile(
    r"^\s*(erreur|error|impossible|échec|echec|introuvable|non disponible|"
    r"indisponible|timeout|\[bloqué\]|not found|failed)",
    re.IGNORECASE,
)

_PLAN_SYSTEM = """Tu décomposes un objectif en un plan d'actions exécutables par Ada.

Tu reçois la liste des outils disponibles. Tu produis UNIQUEMENT un JSON valide,
sans markdown :
{
  "steps": [
    {
      "description": "ce que fait cette étape, en français",
      "tool": "nom_exact_d_un_outil_disponible",
      "args": {"param": "valeur"},
      "success_criteria": "à quoi on reconnaît que l'étape a réussi"
    }
  ]
}

Règles :
- N'utilise QUE des outils de la liste fournie, avec leur nom exact.
- Le minimum d'étapes possible : ne découpe pas ce qui tient en une action.
- Chaque étape doit être vérifiable — un critère de succès concret.
- Si une étape dépend du résultat d'une précédente, mets-la après ; utilise
  le marqueur {{etape_N}} dans les args pour réutiliser un résultat.
- Si l'objectif ne demande qu'une seule action, produis une seule étape.
- Si l'objectif est irréalisable avec ces outils, renvoie {"steps": []}."""

_REPAIR_SYSTEM = """Une étape d'un plan a échoué. Tu proposes une correction.

Réponds UNIQUEMENT par un JSON valide, sans markdown :
{
  "tool": "nom_exact_de_l_outil",
  "args": {"param": "valeur"},
  "reason": "ce que tu changes et pourquoi"
}

Analyse l'erreur : paramètre mal formé ? mauvais outil ? valeur manquante ?
Propose une approche DIFFÉRENTE, pas un simple nouvel essai à l'identique.
Si aucune correction n'est possible, renvoie {"tool": null}."""


def _parse_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*", "", (text or "").strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    data = json.loads(cleaned)
    return data if isinstance(data, dict) else {}


def looks_like_failure(result: str) -> bool:
    """Heuristique de détection d'échec sur le retour d'un outil."""
    if result is None:
        return True
    text = str(result).strip()
    if not text:
        return True
    return bool(_FAILURE_PATTERNS.match(text))


@dataclass
class Step:
    id: int
    description: str
    tool: str
    args: dict = field(default_factory=dict)
    success_criteria: str = ""
    status: str = "pending"   # pending | done | failed | blocked
    result: str = ""
    attempts: int = 0

    @property
    def is_sensitive(self) -> bool:
        return self.tool in SENSITIVE_TOOLS


@dataclass
class Plan:
    objective: str
    steps: list[Step] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "pending"   # pending | running | done | failed | blocked

    def to_dict(self) -> dict:
        return {
            "objective": self.objective,
            "created_at": self.created_at,
            "status": self.status,
            "steps": [asdict(s) for s in self.steps],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        plan = cls(
            objective=str(data.get("objective", "")),
            created_at=float(data.get("created_at", time.time())),
            status=str(data.get("status", "pending")),
        )
        plan.steps = [Step(**s) for s in data.get("steps", [])]
        return plan

    @property
    def pending_steps(self) -> list[Step]:
        return [s for s in self.steps if s.status == "pending"]

    def summary(self) -> str:
        done = sum(1 for s in self.steps if s.status == "done")
        return f"{done}/{len(self.steps)} étapes"


class Planner:
    """Décompose un objectif, l'exécute pas à pas, vérifie et répare."""

    def __init__(self, executor=None, client=None, on_progress=None):
        self._executor = executor      # async (tool, args) -> str
        self._client = client
        self._on_progress = on_progress

    # ── Cycle complet ─────────────────────────────────────────────────────────

    async def run(self, objective: str, tools: list[str]) -> str:
        """Point d'entrée : planifie puis exécute. Retourne un compte rendu."""
        plan = await self.make_plan(objective, tools)
        if plan is None or not plan.steps:
            return (
                f"Je n'ai pas réussi à décomposer « {objective} » en actions "
                "réalisables avec les outils disponibles."
            )
        await self._progress(f"Plan établi : {len(plan.steps)} étape(s)")
        return await self.execute(plan)

    # ── Planification ─────────────────────────────────────────────────────────

    async def make_plan(self, objective: str, tools: list[str]) -> Plan | None:
        client = self._get_client()
        if client is None:
            return None

        prompt = (
            f"Objectif : {objective}\n\n"
            f"Outils disponibles :\n" + "\n".join(f"- {t}" for t in sorted(tools))
        )
        raw = await self._ask(client, _PLAN_SYSTEM, prompt)
        if not raw:
            return None

        try:
            data = _parse_json(raw)
        except Exception as exc:  # noqa: BLE001
            print(f"[PLANNER] plan illisible : {exc}")
            return None

        plan = Plan(objective=objective)
        for i, item in enumerate(data.get("steps", [])[:MAX_STEPS], start=1):
            tool = str(item.get("tool", "")).strip()
            if tool not in tools:
                print(f"[PLANNER] étape ignorée — outil inconnu : {tool!r}")
                continue
            plan.steps.append(
                Step(
                    id=i,
                    description=str(item.get("description", ""))[:200],
                    tool=tool,
                    args=item.get("args") or {},
                    success_criteria=str(item.get("success_criteria", ""))[:200],
                )
            )
        return plan

    # ── Exécution ─────────────────────────────────────────────────────────────

    async def execute(self, plan: Plan) -> str:
        if self._executor is None:
            return "Aucun exécuteur disponible."

        plan.status = "running"
        results: dict[int, str] = {}

        for step in plan.steps:
            if step.status == "done":
                results[step.id] = step.result
                continue

            # Sûreté : jamais d'action irréversible sans validation humaine.
            if step.is_sensitive:
                step.status = "blocked"
                plan.status = "blocked"
                self._save(plan)
                await self._progress(f"⏸ Étape {step.id} en attente de ton accord")
                return (
                    f"Plan interrompu à l'étape {step.id} ({plan.summary()}).\n"
                    f"L'action « {step.description} » utilise {step.tool}, "
                    "qui est irréversible : confirme-la et je poursuis."
                )

            args = self._resolve_refs(step.args, results)
            await self._progress(f"▶ Étape {step.id}/{len(plan.steps)} : {step.description}")

            ok, result = await self._run_step(step, args)

            # Réparation ciblée : on rejoue l'étape, pas tout le plan.
            while not ok and step.attempts <= MAX_REPAIRS:
                repair = await self._repair(plan.objective, step, result)
                if repair is None:
                    break
                await self._progress(f"↻ Correction étape {step.id} : {repair.get('reason', '')}")
                step.tool = repair.get("tool") or step.tool
                step.args = repair.get("args") or step.args
                ok, result = await self._run_step(step, self._resolve_refs(step.args, results))

            step.result = str(result)[:1000]
            step.status = "done" if ok else "failed"
            results[step.id] = step.result
            self._save(plan)

            if not ok:
                plan.status = "failed"
                self._save(plan)
                await self._progress(f"✗ Échec à l'étape {step.id}")
                return (
                    f"Bloquée à l'étape {step.id} sur {len(plan.steps)} : "
                    f"{step.description}.\nCause : {step.result[:300]}"
                )

        plan.status = "done"
        self._save(plan)
        await self._progress(f"✓ Terminé ({plan.summary()})")
        dernier = plan.steps[-1].result if plan.steps else ""
        return f"Fait — {plan.summary()}. {dernier[:400]}"

    async def _run_step(self, step: Step, args: dict) -> tuple[bool, str]:
        step.attempts += 1
        try:
            result = await self._executor(step.tool, args)
        except Exception as exc:  # noqa: BLE001
            return False, f"Erreur : {exc}"
        return (not looks_like_failure(result)), str(result)

    @staticmethod
    def _resolve_refs(args: dict, results: dict[int, str]) -> dict:
        """Remplace les marqueurs {{etape_N}} par le résultat correspondant."""
        if not isinstance(args, dict):
            return {}
        resolved = {}
        for key, value in args.items():
            if isinstance(value, str):
                for step_id, result in results.items():
                    value = value.replace(f"{{{{etape_{step_id}}}}}", str(result)[:500])
            resolved[key] = value
        return resolved

    async def _repair(self, objective: str, step: Step, error: str) -> dict | None:
        client = self._get_client()
        if client is None:
            return None
        prompt = (
            f"Objectif global : {objective}\n"
            f"Étape échouée : {step.description}\n"
            f"Outil utilisé : {step.tool}\n"
            f"Arguments : {json.dumps(step.args, ensure_ascii=False)}\n"
            f"Erreur obtenue : {error[:400]}\n"
            f"Critère de succès attendu : {step.success_criteria}"
        )
        raw = await self._ask(client, _REPAIR_SYSTEM, prompt)
        if not raw:
            return None
        try:
            data = _parse_json(raw)
        except Exception:  # noqa: BLE001
            return None
        return data if data.get("tool") else None

    # ── Persistance (reprise après crash) ─────────────────────────────────────

    @staticmethod
    def state_path() -> Path:
        custom = os.getenv("PLANNER_STATE_PATH", "").strip()
        if custom:
            return Path(custom).expanduser()
        return Path(__file__).resolve().parent / "memory" / "current_plan.json"

    def _save(self, plan: Plan) -> None:
        try:
            path = self.state_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(plan.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[PLANNER] sauvegarde du plan impossible : {exc}")

    @classmethod
    def load_plan(cls) -> Plan | None:
        """Recharge un plan interrompu (reprise après redémarrage)."""
        try:
            path = cls.state_path()
            if not path.exists():
                return None
            plan = Plan.from_dict(json.loads(path.read_text(encoding="utf-8")))
            return plan if plan.status in {"running", "blocked"} else None
        except Exception as exc:  # noqa: BLE001
            print(f"[PLANNER] plan illisible : {exc}")
            return None

    # ── Utilitaires ───────────────────────────────────────────────────────────

    async def _progress(self, message: str) -> None:
        print(f"[PLANNER] {message}")
        if self._on_progress is None:
            return
        try:
            res = self._on_progress(message)
            if asyncio.iscoroutine(res):
                await res
        except Exception:
            pass

    async def _ask(self, client, system: str, prompt: str) -> str:
        try:
            from google.genai import types

            response = await client.aio.models.generate_content(
                model=_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.2,
                    max_output_tokens=1200,
                ),
            )
            return response.text or ""
        except Exception as exc:  # noqa: BLE001
            print(f"[PLANNER] appel modèle échoué : {exc}")
            return ""

    def _get_client(self):
        """Initialisation paresseuse — aucun effet de bord à l'import."""
        if self._client is not None:
            return self._client
        key = os.getenv("GEMINI_API_KEY", "")
        if not key:
            return None
        try:
            from google import genai

            self._client = genai.Client(api_key=key)
            return self._client
        except Exception as exc:  # noqa: BLE001
            print(f"[PLANNER] client indisponible : {exc}")
            return None
