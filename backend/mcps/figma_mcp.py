import os

FIGMA_ACCESS_TOKEN = os.getenv("FIGMA_ACCESS_TOKEN", "")
FIGMA_BASE_URL = "https://api.figma.com/v1"


class FigmaMCP:
    def __init__(self):
        self._client = None

    def _ensure_connected(self):
        if not self._client:
            if not FIGMA_ACCESS_TOKEN:
                return False
            import httpx
            self._client = httpx.Client(
                base_url=FIGMA_BASE_URL,
                headers={"X-Figma-Token": FIGMA_ACCESS_TOKEN},
                timeout=30.0,
            )
        return True

    def list_files(self, team_id: str = "", project_id: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur Figma: FIGMA_ACCESS_TOKEN manquant."
        try:
            if project_id:
                response = self._client.get(f"/projects/{project_id}/files")
                response.raise_for_status()
                data = response.json()
                files = data.get("files", [])
            elif team_id:
                response = self._client.get(f"/teams/{team_id}/projects")
                response.raise_for_status()
                projects = response.json().get("projects", [])
                files = []
                for proj in projects:
                    r = self._client.get(f"/projects/{proj['id']}/files")
                    r.raise_for_status()
                    proj_files = r.json().get("files", [])
                    for f in proj_files:
                        f["project_name"] = proj.get("name", "?")
                    files.extend(proj_files)
            else:
                return "Fournir team_id ou project_id pour lister les fichiers."
            if not files:
                return "Aucun fichier Figma trouvé."
            lines = ["Fichiers Figma:"]
            for f in files:
                key = f.get("key", "?")
                name = f.get("name", "?")
                last_modified = f.get("last_modified", "?")
                project_name = f.get("project_name", "")
                proj_str = f" | Projet: {project_name}" if project_name else ""
                lines.append(f"  [{key}] {name} | Modifié: {last_modified}{proj_str}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Figma: {str(e)}"

    def get_file(self, file_key: str) -> str:
        if not self._ensure_connected():
            return "Erreur Figma: FIGMA_ACCESS_TOKEN manquant."
        try:
            response = self._client.get(f"/files/{file_key}")
            response.raise_for_status()
            data = response.json()
            name = data.get("name", "?")
            last_modified = data.get("lastModified", "?")
            version = data.get("version", "?")
            document = data.get("document", {})
            pages = document.get("children", [])
            lines = [
                f"Fichier: {name}",
                f"Clé: {file_key}",
                f"Dernière modification: {last_modified}",
                f"Version: {version}",
                f"Pages ({len(pages)}):",
            ]
            for page in pages:
                page_name = page.get("name", "?")
                page_id = page.get("id", "?")
                children_count = len(page.get("children", []))
                lines.append(f"  [{page_id}] {page_name} | {children_count} éléments")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Figma: {str(e)}"

    def get_file_components(self, file_key: str) -> str:
        if not self._ensure_connected():
            return "Erreur Figma: FIGMA_ACCESS_TOKEN manquant."
        try:
            response = self._client.get(f"/files/{file_key}/components")
            response.raise_for_status()
            data = response.json()
            components = data.get("meta", {}).get("components", [])
            if not components:
                return f"Aucun composant dans le fichier {file_key}."
            lines = [f"Composants ({len(components)}):"]
            for c in components:
                node_id = c.get("node_id", "?")
                name = c.get("name", "?")
                description = c.get("description", "")
                desc_str = f" — {description}" if description else ""
                lines.append(f"  [{node_id}] {name}{desc_str}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Figma: {str(e)}"

    def export_node(self, file_key: str, node_id: str, format: str = "png", scale: int = 2) -> str:
        if not self._ensure_connected():
            return "Erreur Figma: FIGMA_ACCESS_TOKEN manquant."
        try:
            valid_formats = {"png", "jpg", "svg", "pdf"}
            if format not in valid_formats:
                format = "png"
            params = {
                "ids": node_id,
                "format": format,
                "scale": scale,
            }
            response = self._client.get(f"/images/{file_key}", params=params)
            response.raise_for_status()
            data = response.json()
            images = data.get("images", {})
            if not images:
                return f"Impossible d'exporter le nœud {node_id}."
            lines = [f"Export du nœud {node_id} ({format.upper()}, scale x{scale}):"]
            for nid, url in images.items():
                lines.append(f"  {nid}: {url}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Figma: {str(e)}"

    def get_comments(self, file_key: str) -> str:
        if not self._ensure_connected():
            return "Erreur Figma: FIGMA_ACCESS_TOKEN manquant."
        try:
            response = self._client.get(f"/files/{file_key}/comments")
            response.raise_for_status()
            comments = response.json().get("comments", [])
            if not comments:
                return f"Aucun commentaire sur le fichier {file_key}."
            lines = [f"Commentaires ({len(comments)}):"]
            for c in comments:
                comment_id = c.get("id", "?")
                author = c.get("user", {}).get("handle", "?")
                message = c.get("message", "")[:200]
                created = c.get("created_at", "?")[:10]
                resolved = " [résolu]" if c.get("resolved_at") else ""
                lines.append(f"  [{comment_id}] {author} ({created}){resolved}: {message}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Figma: {str(e)}"
