"""
dev_agent.py — Agent de codage autonome (niveau Claude Code / Codex).

Boucle observe→agis→ré-observe sur un dossier de projet : le modèle lit le code,
cherche, édite, lance des commandes/tests, lit la sortie et itère jusqu'à
l'objectif — comme le fait Claude Code. Pattern asyncio/Gemini d'Ada.

Sécurité : tout `run_shell` passe par security_gate (filet anti-catastrophe +
journal d'audit) ; les écritures sont confinées au dossier du projet (anti path
traversal) et sauvegardées (.bak) avant modification. Pas de confirmation à
cliquer (mode autonome).
"""

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional

from google import genai
from google.genai import types

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL = os.getenv("DEV_AGENT_MODEL", "gemini-2.5-flash")
MAX_STEPS = int(os.getenv("DEV_AGENT_MAX_STEPS", "40"))
MAX_READ_CHARS = 16000
MAX_OUTPUT_CHARS = 6000

_SYSTEM = """Tu es un agent de codage autonome expert (niveau Claude Code / Codex).
Tu travailles DANS un dossier de projet, une action à la fois. À chaque tour tu
reçois l'objectif, l'arborescence, et l'historique de tes actions + leurs
résultats. Tu renvoies UNE seule action JSON, puis tu observes avant la suivante.

Méthode : explore d'abord (list_dir / read_file / search) pour COMPRENDRE avant
d'éditer. Édite par petites touches sûres. Lance les tests/commandes pour
vérifier. N'invente jamais le contenu d'un fichier que tu n'as pas lu.

Actions possibles (UN seul objet JSON, rien d'autre) :
  {"action":"list_dir","path":"."}
  {"action":"read_file","path":"backend/x.py"}
  {"action":"search","pattern":"def foo","glob":"*.py"}
  {"action":"write_file","path":"backend/x.py","content":"<contenu COMPLET du fichier>"}
  {"action":"run_shell","command":"pytest -q"}
  {"action":"done","summary":"ce qui a été fait et vérifié"}

Règles :
- write_file écrit le fichier ENTIER (jamais un diff). Lis-le avant de le réécrire.
- Chemins relatifs au projet uniquement. Pas de sortie du dossier.
- Si une commande échoue, lis l'erreur et corrige — n'abandonne pas au premier échec.
- Termine par "done" dès que l'objectif est atteint et vérifié."""


class DevAgent:
    def __init__(self):
        self._client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

    # ── Confinement des chemins ──────────────────────────────────────────────
    @staticmethod
    def _safe(root: Path, rel: str) -> Optional[Path]:
        try:
            p = (root / rel).resolve()
            root_r = root.resolve()
            if p == root_r or root_r in p.parents:
                return p
        except Exception:
            pass
        return None

    # ── Primitives ───────────────────────────────────────────────────────────
    def _list_dir(self, root: Path, rel: str) -> str:
        p = self._safe(root, rel or ".")
        if not p or not p.exists():
            return f"(introuvable: {rel})"
        out = []
        for child in sorted(p.iterdir()):
            if child.name in {".git", "node_modules", "__pycache__", ".venv", "dist"}:
                out.append(f"{child.name}/  (ignoré)")
                continue
            out.append(f"{child.name}/" if child.is_dir() else child.name)
        return "\n".join(out) or "(vide)"

    def _read_file(self, root: Path, rel: str) -> str:
        p = self._safe(root, rel)
        if not p or not p.is_file():
            return f"(introuvable: {rel})"
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
            return txt[:MAX_READ_CHARS] + ("\n…(tronqué)" if len(txt) > MAX_READ_CHARS else "")
        except Exception as e:
            return f"(erreur lecture: {e})"

    def _search(self, root: Path, pattern: str, glob: str = "*") -> str:
        try:
            rx = re.compile(pattern)
        except re.error as e:
            return f"(regex invalide: {e})"
        hits = []
        for p in root.rglob(glob):
            if any(part in {".git", "node_modules", "__pycache__", ".venv", "dist"} for part in p.parts):
                continue
            if not p.is_file():
                continue
            try:
                for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                    if rx.search(line):
                        hits.append(f"{p.relative_to(root)}:{i}: {line.strip()[:160]}")
                        if len(hits) >= 60:
                            return "\n".join(hits) + "\n…(60+ résultats)"
            except Exception:
                continue
        return "\n".join(hits) or "(aucun résultat)"

    def _write_file(self, root: Path, rel: str, content: str) -> str:
        p = self._safe(root, rel)
        if not p:
            return f"(refusé: chemin hors projet: {rel})"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            if p.exists():
                try:
                    p.with_suffix(p.suffix + ".bak").write_text(
                        p.read_text(encoding="utf-8", errors="replace"), encoding="utf-8"
                    )
                except Exception:
                    pass
            p.write_text(content, encoding="utf-8")
            return f"écrit: {rel} ({len(content)} caractères)"
        except Exception as e:
            return f"(erreur écriture: {e})"

    async def _run_shell(self, root: Path, command: str) -> str:
        # Gate : filet anti-catastrophe + journal d'audit (mode autonome).
        try:
            import security_gate
            decision, reason = security_gate.check_shell(command, source="ai")
            if decision == security_gate.BLOCK:
                return f"[BLOQUÉ] {reason}"
        except Exception as e:
            print(f"[DevAgent] gate indisponible: {e}")

        def _exec():
            try:
                r = subprocess.run(
                    command, shell=True, cwd=str(root),
                    capture_output=True, text=True, timeout=180,
                )
                out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr else "")
                return f"(exit {r.returncode})\n{out}"
            except subprocess.TimeoutExpired:
                return "(timeout 180s)"
            except Exception as e:
                return f"(erreur: {e})"

        out = await asyncio.to_thread(_exec)
        return out[:MAX_OUTPUT_CHARS] + ("\n…(tronqué)" if len(out) > MAX_OUTPUT_CHARS else "")

    # ── Boucle principale ────────────────────────────────────────────────────
    async def run(self, objective: str, project_path: str = "",
                  step_callback: Optional[Callable] = None) -> str:
        if self._client is None:
            return "Erreur DevAgent : GEMINI_API_KEY non configurée."
        root = Path(project_path or os.getenv("JARVIS_ROOT") or os.getcwd()).expanduser()
        if not root.is_dir():
            return f"Erreur DevAgent : dossier projet introuvable : {root}"

        tree = self._list_dir(root, ".")
        history: list[str] = []

        for step in range(1, MAX_STEPS + 1):
            hist = "\n".join(history[-12:]) or "(aucune action encore)"
            prompt = (
                f"OBJECTIF: {objective}\n\n"
                f"PROJET: {root}\nARBORESCENCE (racine):\n{tree}\n\n"
                f"HISTORIQUE (actions → résultats):\n{hist}\n\n"
                "Donne la PROCHAINE action (un seul objet JSON)."
            )
            try:
                resp = await asyncio.to_thread(
                    self._client.models.generate_content,
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(system_instruction=_SYSTEM, temperature=0.1),
                )
                raw = (resp.text or "").strip()
                m = re.search(r"\{.*\}", raw, re.S)
                action = json.loads(m.group(0)) if m else None
            except Exception as e:
                return f"Erreur DevAgent (modèle) à l'étape {step}: {e}"

            if not isinstance(action, dict) or "action" not in action:
                history.append(f"[{step}] réponse illisible → arrêt")
                return "DevAgent : impossible de déterminer la prochaine action."

            act = action["action"]
            if act == "done":
                return f"✓ {action.get('summary', 'terminé')}"

            if step_callback:
                await step_callback({"log": f"[DEV] {step}. {act} {action.get('path', action.get('command', ''))}"[:120]})

            if act == "list_dir":
                res = self._list_dir(root, action.get("path", "."))
            elif act == "read_file":
                res = self._read_file(root, action.get("path", ""))
            elif act == "search":
                res = self._search(root, action.get("pattern", ""), action.get("glob", "*"))
            elif act == "write_file":
                res = self._write_file(root, action.get("path", ""), action.get("content", ""))
            elif act == "run_shell":
                res = await self._run_shell(root, action.get("command", ""))
            else:
                res = f"(action inconnue: {act})"

            history.append(f"[{step}] {act} {action.get('path', action.get('command', ''))}\n→ {res[:800]}")

        return f"DevAgent : objectif non atteint après {MAX_STEPS} étapes. Dernier état:\n" + "\n".join(history[-3:])
