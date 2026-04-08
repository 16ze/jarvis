import json
import os

import httpx

VERCEL_TOKEN = os.getenv("VERCEL_TOKEN", "")
VERCEL_TEAM_ID = os.getenv("VERCEL_TEAM_ID", "")
_BASE_URL = "https://api.vercel.com"

_vercel_available = bool(VERCEL_TOKEN)


class VercelMCP:
    def __init__(self):
        if not _vercel_available:
            self._headers = {}
        else:
            self._headers = {
                "Authorization": f"Bearer {VERCEL_TOKEN}",
                "Content-Type": "application/json",
            }

    def _params(self, extra: dict = None) -> dict:
        """Injecte teamId si défini, fusionne avec les params supplémentaires."""
        params = {}
        if VERCEL_TEAM_ID:
            params["teamId"] = VERCEL_TEAM_ID
        if extra:
            params.update({k: v for k, v in extra.items() if v not in (None, "", [])})
        return params

    def _get(self, path: str, params: dict = None) -> dict:
        if not _vercel_available:
            raise RuntimeError("VERCEL_TOKEN non configuré.")
        url = f"{_BASE_URL}{path}"
        with httpx.Client(timeout=15) as client:
            response = client.get(url, headers=self._headers, params=self._params(params))
            response.raise_for_status()
            return response.json()

    # ─── PROJECTS ────────────────────────────────────────────────────────────

    def list_projects(self, limit: int = 20) -> str:
        """Liste les projets Vercel de l'équipe/compte."""
        try:
            data = self._get("/v9/projects", {"limit": limit})
            projects = data.get("projects", [])
            if not projects:
                return "Aucun projet trouvé."
            lines = []
            for p in projects:
                framework = p.get("framework") or "N/A"
                updated = p.get("updatedAt", "?")
                lines.append(f"  - {p['name']} (ID: {p['id']}) | Framework: {framework} | Mis à jour: {updated}")
            return f"{len(projects)} projet(s) :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur Vercel list_projects: {str(e)}"

    def get_project(self, project_id_or_name: str) -> str:
        """Détail complet d'un projet (ID ou nom)."""
        try:
            data = self._get(f"/v9/projects/{project_id_or_name}")
            return json.dumps(
                {
                    "id": data.get("id"),
                    "name": data.get("name"),
                    "framework": data.get("framework"),
                    "nodeVersion": data.get("nodeVersion"),
                    "productionDeployment": data.get("latestDeployments", [{}])[0].get("url") if data.get("latestDeployments") else None,
                    "createdAt": data.get("createdAt"),
                    "updatedAt": data.get("updatedAt"),
                    "link": data.get("link"),
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return f"Erreur Vercel get_project: {str(e)}"

    # ─── DEPLOYMENTS ─────────────────────────────────────────────────────────

    def list_deployments(self, project_id: str = "", limit: int = 10) -> str:
        """Liste les derniers deployments, filtrés par projet si fourni."""
        try:
            params = {"limit": limit}
            if project_id:
                params["projectId"] = project_id
            data = self._get("/v6/deployments", params)
            deployments = data.get("deployments", [])
            if not deployments:
                return "Aucun deployment trouvé."
            lines = []
            for d in deployments:
                state = d.get("state", "?")
                url = d.get("url", "?")
                created = d.get("created", "?")
                lines.append(f"  - {d['uid']} | {state} | {url} | {created}")
            return f"{len(deployments)} deployment(s) :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur Vercel list_deployments: {str(e)}"

    def get_deployment(self, deployment_id: str) -> str:
        """Statut et détail d'un deployment spécifique."""
        try:
            data = self._get(f"/v13/deployments/{deployment_id}")
            return json.dumps(
                {
                    "id": data.get("id"),
                    "url": data.get("url"),
                    "state": data.get("state"),
                    "readyState": data.get("readyState"),
                    "createdAt": data.get("createdAt"),
                    "buildingAt": data.get("buildingAt"),
                    "ready": data.get("ready"),
                    "errorMessage": data.get("errorMessage"),
                    "target": data.get("target"),
                },
                ensure_ascii=False,
                indent=2,
            )
        except Exception as e:
            return f"Erreur Vercel get_deployment: {str(e)}"

    def get_deployment_logs(self, deployment_id: str) -> str:
        """Récupère les logs d'un deployment."""
        try:
            data = self._get(f"/v2/deployments/{deployment_id}/events")
            events = data if isinstance(data, list) else data.get("events", [])
            if not events:
                return f"Aucun log pour le deployment {deployment_id}."
            lines = []
            for ev in events:
                text = ev.get("text") or ev.get("payload", {}).get("text", "")
                created = ev.get("created", "")
                if text:
                    lines.append(f"[{created}] {text}")
            return "\n".join(lines) if lines else "Logs vides."
        except Exception as e:
            return f"Erreur Vercel get_deployment_logs: {str(e)}"

    # ─── DOMAINS ─────────────────────────────────────────────────────────────

    def list_domains(self, project_id: str = "") -> str:
        """Liste les domaines, filtrés par projet si fourni."""
        try:
            if project_id:
                data = self._get(f"/v9/projects/{project_id}/domains")
                domains = data.get("domains", [])
            else:
                data = self._get("/v5/domains")
                domains = data.get("domains", [])
            if not domains:
                return "Aucun domaine trouvé."
            lines = [f"  - {d.get('name', d.get('domain', '?'))} | Vérifié: {d.get('verified', '?')}" for d in domains]
            return f"{len(domains)} domaine(s) :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur Vercel list_domains: {str(e)}"

    # ─── ENV VARS ────────────────────────────────────────────────────────────

    def get_env_vars(self, project_id: str) -> str:
        """Liste les noms des variables d'environnement d'un projet (valeurs masquées)."""
        try:
            data = self._get(f"/v9/projects/{project_id}/env")
            env_vars = data.get("envs", [])
            if not env_vars:
                return f"Aucune variable d'environnement pour le projet '{project_id}'."
            lines = []
            for ev in env_vars:
                key = ev.get("key", "?")
                target = ", ".join(ev.get("target", []))
                ev_type = ev.get("type", "?")
                lines.append(f"  - {key} | Type: {ev_type} | Cibles: {target}")
            return f"{len(env_vars)} variable(s) d'env :\n" + "\n".join(lines)
        except Exception as e:
            return f"Erreur Vercel get_env_vars: {str(e)}"
