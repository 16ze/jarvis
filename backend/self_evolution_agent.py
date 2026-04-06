"""
self_evolution_agent.py — Agent Gemini 2.5 Flash pour auto-évolution d'Ada

Workflow : analyze → research → generate → validate → write → restart
Sécurité : path validation, git backup, import test × 3 avant déploiement
"""
import ast
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

JARVIS_ROOT    = Path(os.getenv("JARVIS_ROOT", "/Users/bryandev/jarvis")).resolve()
BACKEND_DIR    = JARVIS_ROOT / "backend"
MCPS_DIR       = BACKEND_DIR / "mcps"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL          = "gemini-2.5-flash"
RESTART_SCRIPT = BACKEND_DIR / "restart_ada.sh"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT  = os.getenv("TELEGRAM_CHAT_ID", "")


class SelfEvolutionAgent:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY non configurée.")
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        # Templates lus une fois pour le prompt de génération
        self._template_mcp      = self._read_template(MCPS_DIR / "spotify_mcp.py")
        self._template_decl     = self._read_template_decl()
        self._template_dispatch = self._read_template_dispatch()

    # ── Sécurité ─────────────────────────────────────────────────────────────

    def _validate_path(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(JARVIS_ROOT)
        except Exception:
            return False

    def _git_backup(self) -> str:
        try:
            diff = subprocess.run(
                ["git", "-C", str(JARVIS_ROOT), "diff", "--quiet"],
                capture_output=True
            )
            if diff.returncode != 0:
                subprocess.run(
                    ["git", "-C", str(JARVIS_ROOT), "add", "-A"],
                    capture_output=True
                )
                r = subprocess.run(
                    ["git", "-C", str(JARVIS_ROOT), "commit", "-m",
                     "chore: auto-backup before Ada self-evolution"],
                    capture_output=True, text=True
                )
                return r.stdout.strip() or r.stderr.strip()
            return "Aucun changement à sauvegarder."
        except Exception as e:
            return f"Backup git échoué : {e}"

    def _git_commit(self, message: str) -> str:
        try:
            subprocess.run(["git", "-C", str(JARVIS_ROOT), "add", "-A"],
                           capture_output=True)
            r = subprocess.run(
                ["git", "-C", str(JARVIS_ROOT), "commit", "-m", message],
                capture_output=True, text=True
            )
            return r.stdout.strip() or r.stderr.strip()
        except Exception as e:
            return f"Git commit échoué : {e}"

    async def _notify_telegram(self, message: str) -> None:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                await c.post(url, json={"chat_id": TELEGRAM_CHAT, "text": message})
        except Exception:
            pass

    # ── Templates ─────────────────────────────────────────────────────────────

    def _read_template(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")[:3000]
        except Exception:
            return ""

    def _read_template_decl(self) -> str:
        """Extrait le bloc spotify de mcp_tools_declarations.py comme exemple."""
        decl_file = BACKEND_DIR / "mcp_tools_declarations.py"
        try:
            content = decl_file.read_text(encoding="utf-8")
            start = content.find("# ── SPOTIFY")
            end = content.find("# ── YOUTUBE")
            if start != -1 and end != -1:
                return content[start:end][:2000]
            return content[:2000]
        except Exception:
            return ""

    def _read_template_dispatch(self) -> str:
        """Extrait le bloc dispatch spotify d'ada.py comme exemple."""
        ada_file = BACKEND_DIR / "ada.py"
        try:
            content = ada_file.read_text(encoding="utf-8")
            start = content.find('elif n == "spotify_current"')
            end = content.find('elif n == "youtube_search"')
            if start != -1 and end != -1:
                return content[start:end][:2000]
            return ""
        except Exception:
            return ""

    # ── Étape 1 : Analyze ────────────────────────────────────────────────────

    async def _analyze(self, goal: str, failed_context: str) -> dict:
        """
        Retourne un dict avec service_name, python_lib, pip_package,
        doc_urls, tools_needed, file_name.
        """
        prompt = (
            f"Un assistant IA a échoué à accomplir cette mission :\n"
            f"GOAL: {goal}\n"
            f"ÉCHEC: {failed_context}\n\n"
            "Identifie le service externe Python nécessaire.\n"
            "Réponds UNIQUEMENT avec un JSON valide, sans markdown :\n"
            "{\n"
            '  "service_name": "nom_du_service",\n'
            '  "python_lib": "nom_du_package_pip",\n'
            '  "pip_package": "pip install ...",\n'
            '  "doc_urls": ["url1", "url2"],\n'
            '  "tools_needed": ["service_action1", "service_action2"],\n'
            '  "file_name": "service_mcp.py"\n'
            "}"
        )
        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.1),
        )
        raw = response.text.strip()
        # Nettoyer le markdown si présent
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            raw = raw.rstrip("`").strip()
        return json.loads(raw)

    # ── Étape 2 : Research ───────────────────────────────────────────────────

    async def _research(self, analysis: dict) -> str:
        """
        Fetche les URLs de documentation et retourne un extrait texte concaténé.
        Max 8000 chars pour rester dans le contexte Gemini.
        """
        MAX_CHARS = 8000
        parts = []

        lib = analysis.get("python_lib", "")
        urls = [f"https://pypi.org/pypi/{lib}/json"] + analysis.get("doc_urls", [])

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            for url in urls[:3]:  # max 3 URLs
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    text = resp.text
                    # Si PyPI JSON, extraire description + summary
                    if "pypi.org/pypi" in url and resp.headers.get("content-type", "").startswith("application/json"):
                        data = resp.json()
                        info = data.get("info", {})
                        text = (
                            f"Package: {info.get('name')}\n"
                            f"Summary: {info.get('summary')}\n"
                            f"Description:\n{info.get('description', '')[:3000]}"
                        )
                    elif "<html" in text.lower():
                        import re
                        text = re.sub(r"<[^>]+>", " ", text)
                        text = re.sub(r"\s+", " ", text)
                    parts.append(f"=== {url} ===\n{text[:MAX_CHARS // len(urls)]}")
                except Exception as e:
                    parts.append(f"=== {url} — ERREUR: {e} ===")

        return "\n\n".join(parts)[:MAX_CHARS]

    # ── Étape 3 : Generate ───────────────────────────────────────────────────

    async def _generate(self, analysis: dict, doc: str, previous_error: str = "") -> dict:
        """
        Génère 4 blocs de code délimités par des marqueurs.
        Retourne {"mcp_file": str, "declarations": str, "dispatch": str, "init": str}
        """
        service = analysis.get("service_name", "unknown")
        lib     = analysis.get("python_lib", service)
        tools   = analysis.get("tools_needed", [])

        error_block = f"\nErreur précédente à corriger :\n{previous_error}\n" if previous_error else ""

        prompt = (
            f"Tu es un expert Python. Génère un connecteur MCP pour le service '{service}'.\n"
            f"Librairie Python : {lib}\n"
            f"Outils à créer : {', '.join(tools)}\n"
            f"{error_block}\n"
            f"Documentation :\n{doc}\n\n"
            "=== TEMPLATE MCP (spotify_mcp.py) ===\n"
            f"{self._template_mcp}\n\n"
            "=== TEMPLATE DÉCLARATIONS ===\n"
            f"{self._template_decl}\n\n"
            "=== TEMPLATE DISPATCH (ada.py) ===\n"
            f"{self._template_dispatch}\n\n"
            "RÈGLES ABSOLUES :\n"
            f"1. La classe s'appelle {service.capitalize()}MCP\n"
            f"2. Le fichier s'appelle {analysis.get('file_name', service + '_mcp.py')}\n"
            "3. Toutes les méthodes retournent str, jamais d'exception non catchée\n"
            "4. Imports en haut du fichier (pas lazy sauf dépendances lourdes)\n"
            "5. Variables d'env via os.getenv() en haut du fichier\n"
            f"6. Noms d'outils préfixés par '{service}_'\n\n"
            "Réponds avec EXACTEMENT ces 4 blocs délimités, sans autre texte :\n"
            "===MCP_FILE===\n"
            "<code complet du fichier MCP>\n"
            "===DECLARATIONS===\n"
            "<déclarations tool_dict Python + variables + ajout dans MCP_TOOLS>\n"
            "===DISPATCH===\n"
            "<bloc elif pour _execute_text_tool d'ada.py>\n"
            "===INIT===\n"
            "<une ligne Python pour instancier le MCP dans _init_agents>"
        )

        response = await asyncio.to_thread(
            self._client.models.generate_content,
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        raw = response.text

        def extract(marker_start: str, marker_end: str) -> str:
            start = raw.find(marker_start)
            end   = raw.find(marker_end, start + len(marker_start))
            if start == -1:
                return ""
            content = raw[start + len(marker_start): end if end != -1 else None]
            return content.strip()

        return {
            "mcp_file":     extract("===MCP_FILE===", "===DECLARATIONS==="),
            "declarations": extract("===DECLARATIONS===", "===DISPATCH==="),
            "dispatch":     extract("===DISPATCH===", "===INIT==="),
            "init":         extract("===INIT===", "===END===") or raw.split("===INIT===")[-1].strip(),
        }

    # ── Étape 4 : Validate ───────────────────────────────────────────────────

    async def _validate(self, mcp_code: str, service_name: str) -> tuple[bool, str]:
        """
        Valide le code MCP généré :
        1. Syntaxe Python (ast.parse)
        2. Import réel en subprocess isolé
        Retourne (ok: bool, error_message: str)
        """
        # Étape 1 : syntaxe
        try:
            ast.parse(mcp_code)
        except SyntaxError as e:
            return False, f"SyntaxError: {e}"

        # Étape 2 : import subprocess isolé
        with tempfile.NamedTemporaryFile(
            suffix=".py", mode="w", encoding="utf-8",
            dir=tempfile.gettempdir(), delete=False,
            prefix=f"_test_{service_name}_"
        ) as tmp:
            tmp.write(mcp_code)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                [sys.executable, "-c",
                 "import importlib.util, sys; "
                 "p = sys.argv[1]; "
                 "spec = importlib.util.spec_from_file_location('test_mcp', p); "
                 "mod = importlib.util.module_from_spec(spec); "
                 "spec.loader.exec_module(mod); print('OK')",
                 tmp_path],
                capture_output=True, text=True, timeout=15,
                cwd=str(BACKEND_DIR)
            )
            if result.returncode == 0 and "OK" in result.stdout:
                return True, ""
            error = result.stderr.strip() or result.stdout.strip()
            return False, error
        except subprocess.TimeoutExpired:
            return False, "Import timeout (>15s)"
        except Exception as e:
            return False, str(e)
        finally:
            try:
                Path(tmp_path).unlink()
            except Exception:
                pass

    async def _validate_with_retry(
        self, analysis: dict, doc: str, max_tries: int = 3
    ) -> Optional[dict]:
        """
        Génère + valide, jusqu'à max_tries fois.
        Retourne les blocs de code validés, ou None si échec × max_tries.
        """
        service = analysis.get("service_name", "unknown")
        previous_error = ""

        for attempt in range(1, max_tries + 1):
            print(f"[Evolution] Génération tentative {attempt}/{max_tries}...")
            blocks = await self._generate(analysis, doc, previous_error)

            mcp_code = blocks.get("mcp_file", "")
            if not mcp_code:
                previous_error = "Bloc ===MCP_FILE=== vide dans la réponse."
                continue

            ok, error = await self._validate(mcp_code, service)
            if ok:
                print(f"[Evolution] Validation OK tentative {attempt}")
                return blocks
            else:
                print(f"[Evolution] Validation échouée tentative {attempt}: {error}")
                previous_error = error

        return None

    # ── Étape 5 : Write ──────────────────────────────────────────────────────

    def _write_files(self, analysis: dict, blocks: dict) -> str:
        """
        Écrit le MCP et injecte dans mcp_tools_declarations.py, ada.py,
        external_bridge.py. Git backup avant, commit après.
        """
        service   = analysis.get("service_name", "unknown")
        file_name = analysis.get("file_name", f"{service}_mcp.py")
        mcp_path  = MCPS_DIR / file_name

        if not self._validate_path(mcp_path):
            return f"ERREUR path non autorisé : {mcp_path}"

        # Git backup
        backup = self._git_backup()
        if "échoué" in backup:
            return f"ERREUR backup git : {backup}"

        errors = []

        # 1. Écrire le fichier MCP
        try:
            mcp_path.write_text(blocks["mcp_file"], encoding="utf-8")
        except Exception as e:
            errors.append(f"MCP file: {e}")

        # 2. Injecter dans mcp_tools_declarations.py
        decl_path = BACKEND_DIR / "mcp_tools_declarations.py"
        try:
            content = decl_path.read_text(encoding="utf-8")
            insert_before = "\nMCP_TOOLS = ["
            if insert_before in content:
                idx = content.find(insert_before)
                content = (
                    content[:idx]
                    + f"\n# ── {service.upper()} (auto-généré) ─────────────────────────────────────────────\n"
                    + blocks["declarations"]
                    + "\n"
                    + content[idx:]
                )
                decl_path.write_text(content, encoding="utf-8")
                # Injecter aussi les noms de variables dans la liste MCP_TOOLS
                import re as _re
                # Extraire les noms de variables de type: var_name = {
                var_names = _re.findall(r'^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\{', blocks["declarations"], _re.MULTILINE)
                if var_names:
                    content2 = decl_path.read_text(encoding="utf-8")
                    # Chercher le ] de fermeture de MCP_TOOLS
                    list_start = content2.find("MCP_TOOLS = [")
                    if list_start != -1:
                        close_bracket = content2.rfind("]", list_start)
                        if close_bracket != -1:
                            refs = "".join(f"    {v},\n" for v in var_names)
                            content2 = content2[:close_bracket] + refs + content2[close_bracket:]
                            decl_path.write_text(content2, encoding="utf-8")
            else:
                errors.append("MCP_TOOLS marker introuvable dans mcp_tools_declarations.py")
        except Exception as e:
            errors.append(f"declarations: {e}")

        # 3. Injecter dans ada.py — dispatch dans _execute_text_tool
        ada_path = BACKEND_DIR / "ada.py"
        try:
            content = ada_path.read_text(encoding="utf-8")
            insert_before = "                return f\"MCP '{name}' non mappé.\""
            if insert_before in content:
                idx = content.find(insert_before)
                dispatch = blocks["dispatch"]
                dispatch_indented = "\n".join(
                    "                " + line if line.strip() else line
                    for line in dispatch.split("\n")
                )
                content = content[:idx] + dispatch_indented + "\n" + content[idx:]
                ada_path.write_text(content, encoding="utf-8")
            else:
                errors.append("Marqueur dispatch introuvable dans ada.py")
        except Exception as e:
            errors.append(f"ada.py dispatch: {e}")

        # 4. Injecter init dans external_bridge.py — fin de _init_agents
        bridge_path = BACKEND_DIR / "external_bridge.py"
        try:
            content = bridge_path.read_text(encoding="utf-8")
            marker = "warnings.warn(f\"[TextAgent] MonitoringAgent: {e}\")"
            if marker in content:
                idx = content.find(marker) + len(marker)
                init_line = blocks["init"].strip()
                init_block = (
                    f"\n        try:\n"
                    f"            {init_line}\n"
                    f"        except Exception as e:\n"
                    f"            warnings.warn(f\"[TextAgent] {service.capitalize()}MCP: {{e}}\")"
                )
                content = content[:idx] + init_block + content[idx:]
                bridge_path.write_text(content, encoding="utf-8")
            else:
                errors.append("Marqueur _init_agents introuvable dans external_bridge.py")
        except Exception as e:
            errors.append(f"external_bridge.py init: {e}")

        if errors:
            return "Erreurs d'injection :\n" + "\n".join(f"  • {e}" for e in errors)

        self._git_commit(f"feat: auto-evolution Ada — {service}_mcp + déclarations + dispatch")
        return "OK"

    # ── Étape 6 : Restart ────────────────────────────────────────────────────

    def _restart(self) -> None:
        """Lance restart_ada.sh en arrière-plan (détaché du process Ada)."""
        if not RESTART_SCRIPT.exists():
            print(f"[Evolution] WARN: {RESTART_SCRIPT} introuvable — restart manuel requis")
            return
        try:
            subprocess.Popen(
                ["bash", str(RESTART_SCRIPT)],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"[Evolution] Erreur lancement restart: {e}")

    # ── Orchestrateur ────────────────────────────────────────────────────────

    async def evolve(self, goal: str, failed_context: str) -> str:
        """
        Point d'entrée principal. Orchestration complète :
        analyze → research → validate_with_retry → write → restart
        """
        service_name = "inconnu"
        try:
            # 1. Analyser
            print(f"[Evolution] ANALYZE: {goal}")
            analysis = await self._analyze(goal, failed_context)
            service_name = analysis.get("service_name", "inconnu")
            print(f"[Evolution] Service identifié : {service_name}")

            # 2. Rechercher la documentation
            print(f"[Evolution] RESEARCH: {service_name}")
            doc = await self._research(analysis)

            # 3. Générer + Valider (max 3 essais)
            print(f"[Evolution] GENERATE+VALIDATE: {service_name}")
            blocks = await self._validate_with_retry(analysis, doc, max_tries=3)

            if blocks is None:
                msg = (
                    f"[ADA EVOLUTION] Échec après 3 tentatives pour '{goal}'.\n"
                    f"Service : {service_name}\n"
                    "Aucun fichier déployé. Intervention manuelle requise."
                )
                await self._notify_telegram(msg)
                return msg

            # 4. Écrire les fichiers
            print(f"[Evolution] WRITE: {service_name}")
            write_result = await asyncio.to_thread(self._write_files, analysis, blocks)
            if write_result != "OK":
                msg = f"[ADA EVOLUTION] Erreur écriture : {write_result}"
                await self._notify_telegram(msg)
                return msg

            # 5. Redémarrer
            print(f"[Evolution] RESTART")
            self._restart()

            success_msg = (
                f"Outil '{service_name}' créé avec succès.\n"
                f"Fichier : backend/mcps/{analysis.get('file_name')}\n"
                f"Je redémarre dans 3 secondes pour activer le nouvel outil."
            )
            await self._notify_telegram(f"[ADA EVOLUTION] {success_msg}")
            return success_msg

        except Exception as e:
            error_msg = f"[ADA EVOLUTION] Erreur inattendue ({service_name}): {e}"
            await self._notify_telegram(error_msg)
            return error_msg
