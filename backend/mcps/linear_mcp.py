import os
import json
import httpx

LINEAR_API_KEY = os.getenv("LINEAR_API_KEY")
LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearMCP:
    def __init__(self):
        self._api_key = LINEAR_API_KEY

    def _check_config(self) -> str | None:
        if not self._api_key:
            return "Erreur Linear: LINEAR_API_KEY manquant dans les variables d'environnement."
        return None

    def _query(self, query: str, variables: dict = None) -> dict:
        headers = {
            "Authorization": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        response = httpx.post(LINEAR_API_URL, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()

    def list_issues(self, team_id: str = "", status: str = "", limit: int = 20) -> str:
        err = self._check_config()
        if err:
            return err
        try:
            filters = []
            if team_id:
                filters.append(f'team: {{id: {{eq: "{team_id}"}}}}')
            if status:
                filters.append(f'state: {{name: {{eq: "{status}"}}}}')
            filter_str = ("filter: {" + ", ".join(filters) + "}") if filters else ""
            query = f"""
            query {{
                issues(first: {limit} {filter_str}) {{
                    nodes {{
                        id
                        title
                        description
                        priority
                        state {{ name }}
                        assignee {{ name }}
                        createdAt
                    }}
                }}
            }}
            """
            data = self._query(query)
            issues = data.get("data", {}).get("issues", {}).get("nodes", [])
            if not issues:
                return "Aucune issue trouvée."
            lines = []
            for i in issues:
                state = i.get("state", {}).get("name", "?") if i.get("state") else "?"
                assignee = i.get("assignee", {}).get("name", "Non assigné") if i.get("assignee") else "Non assigné"
                lines.append(
                    f"[{state}] {i.get('title', '?')} | id: {i.get('id', '?')} | "
                    f"priorité: {i.get('priority', 0)} | assigné: {assignee}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Linear: {str(e)}"

    def get_issue(self, issue_id: str) -> str:
        err = self._check_config()
        if err:
            return err
        try:
            query = """
            query($id: String!) {
                issue(id: $id) {
                    id
                    title
                    description
                    priority
                    state { name }
                    assignee { name email }
                    team { name }
                    createdAt
                    updatedAt
                }
            }
            """
            data = self._query(query, {"id": issue_id})
            issue = data.get("data", {}).get("issue")
            if not issue:
                return f"Issue {issue_id} introuvable."
            state = issue.get("state", {}).get("name", "?") if issue.get("state") else "?"
            assignee = issue.get("assignee", {}).get("name", "Non assigné") if issue.get("assignee") else "Non assigné"
            team = issue.get("team", {}).get("name", "?") if issue.get("team") else "?"
            return (
                f"Titre: {issue.get('title', '?')}\n"
                f"État: {state}\n"
                f"Équipe: {team}\n"
                f"Assigné: {assignee}\n"
                f"Priorité: {issue.get('priority', 0)}\n"
                f"Description: {issue.get('description', '') or '(vide)'}\n"
                f"Créé: {issue.get('createdAt', '?')}\n"
                f"Modifié: {issue.get('updatedAt', '?')}"
            )
        except Exception as e:
            return f"Erreur Linear: {str(e)}"

    def create_issue(self, title: str, description: str = "", team_id: str = "", priority: int = 0) -> str:
        err = self._check_config()
        if err:
            return err
        try:
            query = """
            mutation($input: IssueCreateInput!) {
                issueCreate(input: $input) {
                    success
                    issue { id title url }
                }
            }
            """
            input_data = {"title": title, "priority": priority}
            if description:
                input_data["description"] = description
            if team_id:
                input_data["teamId"] = team_id
            data = self._query(query, {"input": input_data})
            result = data.get("data", {}).get("issueCreate", {})
            if not result.get("success"):
                return "Erreur Linear: création d'issue échouée."
            issue = result.get("issue", {})
            return f"Issue créée: '{issue.get('title')}' | id: {issue.get('id')} | url: {issue.get('url')}"
        except Exception as e:
            return f"Erreur Linear: {str(e)}"

    def update_issue(self, issue_id: str, status: str = "", title: str = "", description: str = "") -> str:
        err = self._check_config()
        if err:
            return err
        try:
            input_data = {}
            if title:
                input_data["title"] = title
            if description:
                input_data["description"] = description
            if status:
                # Résoudre le stateId depuis le nom
                state_query = f"""
                query {{
                    workflowStates(filter: {{name: {{eq: "{status}"}}}}) {{
                        nodes {{ id name }}
                    }}
                }}
                """
                state_data = self._query(state_query)
                states = state_data.get("data", {}).get("workflowStates", {}).get("nodes", [])
                if states:
                    input_data["stateId"] = states[0]["id"]
            if not input_data:
                return "Aucun champ à mettre à jour fourni."
            query = """
            mutation($id: String!, $input: IssueUpdateInput!) {
                issueUpdate(id: $id, input: $input) {
                    success
                    issue { id title }
                }
            }
            """
            data = self._query(query, {"id": issue_id, "input": input_data})
            result = data.get("data", {}).get("issueUpdate", {})
            if not result.get("success"):
                return f"Erreur Linear: mise à jour de l'issue {issue_id} échouée."
            return f"Issue {issue_id} mise à jour."
        except Exception as e:
            return f"Erreur Linear: {str(e)}"

    def list_projects(self, team_id: str = "") -> str:
        err = self._check_config()
        if err:
            return err
        try:
            filter_str = f'(filter: {{teams: {{id: {{eq: "{team_id}"}}}}}})' if team_id else ""
            query = f"""
            query {{
                projects{filter_str} {{
                    nodes {{
                        id
                        name
                        description
                        state
                        progress
                    }}
                }}
            }}
            """
            data = self._query(query)
            projects = data.get("data", {}).get("projects", {}).get("nodes", [])
            if not projects:
                return "Aucun projet trouvé."
            lines = []
            for p in projects:
                lines.append(
                    f"[{p.get('state', '?')}] {p.get('name', '?')} | "
                    f"progression: {round(p.get('progress', 0) * 100)}% | id: {p.get('id', '?')}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Linear: {str(e)}"

    def list_teams(self) -> str:
        err = self._check_config()
        if err:
            return err
        try:
            query = """
            query {
                teams {
                    nodes {
                        id
                        name
                        key
                        description
                    }
                }
            }
            """
            data = self._query(query)
            teams = data.get("data", {}).get("teams", {}).get("nodes", [])
            if not teams:
                return "Aucune équipe trouvée."
            lines = []
            for t in teams:
                lines.append(f"[{t.get('key', '?')}] {t.get('name', '?')} | id: {t.get('id', '?')}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Linear: {str(e)}"
