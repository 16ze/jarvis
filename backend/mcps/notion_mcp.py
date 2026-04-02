import os
import json

NOTION_TOKEN = os.getenv("NOTION_TOKEN")


class NotionMCP:
    def __init__(self):
        self._client = None

    def _ensure_connected(self):
        if not self._client:
            if not NOTION_TOKEN:
                return False
            from notion_client import Client
            self._client = Client(auth=NOTION_TOKEN)
        return True

    def search(self, query: str, limit: int = 10) -> str:
        if not self._ensure_connected():
            return "Erreur Notion: NOTION_TOKEN manquant dans les variables d'environnement."
        try:
            response = self._client.search(
                query=query,
                page_size=limit,
            )
            results = response.get("results", [])
            if not results:
                return f"Aucun résultat pour '{query}'."
            lines = []
            for r in results:
                obj_type = r.get("object", "?")
                r_id = r.get("id", "?")
                if obj_type == "page":
                    props = r.get("properties", {})
                    title = ""
                    for prop in props.values():
                        if prop.get("type") == "title":
                            title_parts = prop.get("title", [])
                            title = "".join(t.get("plain_text", "") for t in title_parts)
                            break
                    if not title:
                        title = r.get("url", r_id)
                    lines.append(f"[page] {title} | id: {r_id}")
                elif obj_type == "database":
                    title_parts = r.get("title", [])
                    title = "".join(t.get("plain_text", "") for t in title_parts)
                    lines.append(f"[database] {title} | id: {r_id}")
                else:
                    lines.append(f"[{obj_type}] id: {r_id}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Notion: {str(e)}"

    def get_page(self, page_id: str) -> str:
        if not self._ensure_connected():
            return "Erreur Notion: NOTION_TOKEN manquant dans les variables d'environnement."
        try:
            blocks = self._client.blocks.children.list(block_id=page_id)
            results = blocks.get("results", [])
            if not results:
                return f"Page {page_id} vide ou introuvable."
            lines = []
            for block in results:
                block_type = block.get("type", "")
                content = block.get(block_type, {})
                rich_text = content.get("rich_text", [])
                text = "".join(t.get("plain_text", "") for t in rich_text)
                if text:
                    lines.append(text)
            return "\n".join(lines) if lines else "(contenu non textuel)"
        except Exception as e:
            return f"Erreur Notion: {str(e)}"

    def create_page(self, parent_id: str, title: str, content: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur Notion: NOTION_TOKEN manquant dans les variables d'environnement."
        try:
            children = []
            if content:
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": content}}]
                    },
                })
            page = self._client.pages.create(
                parent={"page_id": parent_id},
                properties={
                    "title": {
                        "title": [{"type": "text", "text": {"content": title}}]
                    }
                },
                children=children,
            )
            return f"Page '{title}' créée. id: {page['id']} | url: {page.get('url', '')}"
        except Exception as e:
            return f"Erreur Notion: {str(e)}"

    def query_database(self, database_id: str, filter_json: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur Notion: NOTION_TOKEN manquant dans les variables d'environnement."
        try:
            kwargs = {"database_id": database_id}
            if filter_json:
                kwargs["filter"] = json.loads(filter_json)
            response = self._client.databases.query(**kwargs)
            results = response.get("results", [])
            if not results:
                return "Aucun résultat dans cette base de données."
            lines = []
            for row in results:
                row_id = row.get("id", "?")
                props = row.get("properties", {})
                prop_parts = []
                for key, val in props.items():
                    val_type = val.get("type", "")
                    if val_type == "title":
                        text = "".join(t.get("plain_text", "") for t in val.get("title", []))
                        prop_parts.append(f"{key}: {text}")
                    elif val_type == "rich_text":
                        text = "".join(t.get("plain_text", "") for t in val.get("rich_text", []))
                        prop_parts.append(f"{key}: {text}")
                    elif val_type in ("number", "checkbox", "select", "status"):
                        prop_parts.append(f"{key}: {val.get(val_type)}")
                    elif val_type == "date":
                        date_val = val.get("date") or {}
                        prop_parts.append(f"{key}: {date_val.get('start', '')}")
                lines.append(f"id: {row_id} | " + " | ".join(prop_parts))
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Notion: {str(e)}"

    def append_to_page(self, page_id: str, content: str) -> str:
        if not self._ensure_connected():
            return "Erreur Notion: NOTION_TOKEN manquant dans les variables d'environnement."
        try:
            self._client.blocks.children.append(
                block_id=page_id,
                children=[
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"type": "text", "text": {"content": content}}]
                        },
                    }
                ],
            )
            return f"Contenu ajouté à la page {page_id}."
        except Exception as e:
            return f"Erreur Notion: {str(e)}"
