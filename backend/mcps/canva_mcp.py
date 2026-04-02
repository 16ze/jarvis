import os
import json

CANVA_CLIENT_ID = os.getenv("CANVA_CLIENT_ID", "")
CANVA_CLIENT_SECRET = os.getenv("CANVA_CLIENT_SECRET", "")
CANVA_ACCESS_TOKEN = os.getenv("CANVA_ACCESS_TOKEN", "")
CANVA_BASE_URL = "https://api.canva.com/rest/v1"


class CanvaMCP:
    def __init__(self):
        self._client = None

    def _ensure_connected(self):
        if not self._client:
            if not CANVA_ACCESS_TOKEN:
                return False
            import httpx
            self._client = httpx.Client(
                base_url=CANVA_BASE_URL,
                headers={
                    "Authorization": f"Bearer {CANVA_ACCESS_TOKEN}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return True

    def list_designs(self, limit: int = 20) -> str:
        if not self._ensure_connected():
            return "Erreur Canva: CANVA_ACCESS_TOKEN manquant."
        try:
            response = self._client.get("/designs", params={"limit": limit})
            response.raise_for_status()
            data = response.json()
            items = data.get("items", [])
            if not items:
                return "Aucun design trouvé."
            lines = ["Designs Canva:"]
            for d in items:
                design_id = d.get("id", "?")
                title = d.get("title", "Sans titre")
                design_type = d.get("design_type", {}).get("name", "?")
                updated = d.get("updated_at", "?")
                url = d.get("urls", {}).get("edit_url", "")
                lines.append(f"  [{design_id}] {title} | Type: {design_type} | Modifié: {updated}")
                if url:
                    lines.append(f"    Lien: {url}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Canva: {str(e)}"

    def get_design(self, design_id: str) -> str:
        if not self._ensure_connected():
            return "Erreur Canva: CANVA_ACCESS_TOKEN manquant."
        try:
            response = self._client.get(f"/designs/{design_id}")
            response.raise_for_status()
            d = response.json().get("design", response.json())
            title = d.get("title", "Sans titre")
            design_type = d.get("design_type", {}).get("name", "?")
            created = d.get("created_at", "?")
            updated = d.get("updated_at", "?")
            urls = d.get("urls", {})
            edit_url = urls.get("edit_url", "N/A")
            view_url = urls.get("view_url", "N/A")
            return (
                f"Design: {title}\n"
                f"ID: {design_id}\n"
                f"Type: {design_type}\n"
                f"Créé: {created} | Modifié: {updated}\n"
                f"Édition: {edit_url}\n"
                f"Vue: {view_url}"
            )
        except Exception as e:
            return f"Erreur Canva: {str(e)}"

    def create_design(self, design_type: str = "presentation", title: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur Canva: CANVA_ACCESS_TOKEN manquant."
        try:
            payload = {
                "design_type": {"name": design_type},
            }
            if title:
                payload["title"] = title
            response = self._client.post("/designs", json=payload)
            response.raise_for_status()
            d = response.json().get("design", response.json())
            design_id = d.get("id", "?")
            edit_url = d.get("urls", {}).get("edit_url", "")
            return (
                f"Design créé: {title or design_type}\n"
                f"ID: {design_id}\n"
                f"Lien: {edit_url}"
            )
        except Exception as e:
            return f"Erreur Canva: {str(e)}"

    def export_design(self, design_id: str, format: str = "png") -> str:
        if not self._ensure_connected():
            return "Erreur Canva: CANVA_ACCESS_TOKEN manquant."
        try:
            valid_formats = {"png", "jpg", "pdf", "gif", "svg", "mp4", "pptx"}
            if format not in valid_formats:
                format = "png"
            payload = {
                "design_id": design_id,
                "format": {"type": format.upper()},
            }
            response = self._client.post("/exports", json=payload)
            response.raise_for_status()
            export = response.json().get("export", response.json())
            export_id = export.get("id", "?")
            status = export.get("status", "?")
            urls = export.get("urls", [])
            lines = [
                f"Export lancé: design {design_id} en {format.upper()}",
                f"Export ID: {export_id} | Statut: {status}",
            ]
            for url in urls:
                lines.append(f"URL: {url}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Canva: {str(e)}"
