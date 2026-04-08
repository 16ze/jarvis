import os
import json

HOMEASSISTANT_URL = os.getenv("HOMEASSISTANT_URL", "")
HOMEASSISTANT_TOKEN = os.getenv("HOMEASSISTANT_TOKEN", "")


class HomeAssistantMCP:
    def __init__(self):
        self._client = None

    def _ensure_connected(self):
        if not self._client:
            if not HOMEASSISTANT_URL or not HOMEASSISTANT_TOKEN:
                return False
            import httpx
            self._client = httpx.Client(
                base_url=HOMEASSISTANT_URL.rstrip("/"),
                headers={
                    "Authorization": f"Bearer {HOMEASSISTANT_TOKEN}",
                    "Content-Type": "application/json",
                },
                timeout=10.0,
            )
        return True

    def get_states(self, domain: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur HomeAssistant: HOMEASSISTANT_URL ou HOMEASSISTANT_TOKEN manquant."
        try:
            response = self._client.get("/api/states")
            response.raise_for_status()
            states = response.json()
            if domain:
                states = [s for s in states if s.get("entity_id", "").startswith(f"{domain}.")]
            if not states:
                return f"Aucune entité trouvée{f' pour le domaine {domain}' if domain else ''}."
            lines = []
            for s in states:
                entity_id = s.get("entity_id", "?")
                state = s.get("state", "?")
                friendly = s.get("attributes", {}).get("friendly_name", "")
                name = friendly if friendly else entity_id
                lines.append(f"{entity_id} | {name} | état: {state}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur HomeAssistant: {str(e)}"

    def get_entity(self, entity_id: str) -> str:
        if not self._ensure_connected():
            return "Erreur HomeAssistant: HOMEASSISTANT_URL ou HOMEASSISTANT_TOKEN manquant."
        try:
            response = self._client.get(f"/api/states/{entity_id}")
            response.raise_for_status()
            s = response.json()
            state = s.get("state", "?")
            attrs = s.get("attributes", {})
            friendly = attrs.get("friendly_name", entity_id)
            lines = [f"Entité: {entity_id}", f"Nom: {friendly}", f"État: {state}"]
            for key, val in attrs.items():
                if key != "friendly_name":
                    lines.append(f"  {key}: {val}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur HomeAssistant: {str(e)}"

    def call_service(self, domain: str, service: str, entity_id: str = "", data_json: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur HomeAssistant: HOMEASSISTANT_URL ou HOMEASSISTANT_TOKEN manquant."
        try:
            payload = {}
            if data_json:
                payload = json.loads(data_json)
            if entity_id:
                payload["entity_id"] = entity_id
            response = self._client.post(f"/api/services/{domain}/{service}", json=payload)
            response.raise_for_status()
            return f"Service {domain}.{service} appelé avec succès{f' sur {entity_id}' if entity_id else ''}."
        except Exception as e:
            return f"Erreur HomeAssistant: {str(e)}"

    def turn_on(self, entity_id: str) -> str:
        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
        return self.call_service(domain, "turn_on", entity_id=entity_id)

    def turn_off(self, entity_id: str) -> str:
        domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
        return self.call_service(domain, "turn_off", entity_id=entity_id)

    def set_value(self, entity_id: str, value: str) -> str:
        if not self._ensure_connected():
            return "Erreur HomeAssistant: HOMEASSISTANT_URL ou HOMEASSISTANT_TOKEN manquant."
        try:
            domain = entity_id.split(".")[0] if "." in entity_id else "homeassistant"
            service_map = {
                "input_number": ("input_number", "set_value", "value"),
                "input_text": ("input_text", "set_value", "value"),
                "input_select": ("input_select", "select_option", "option"),
                "light": ("light", "turn_on", "brightness"),
                "climate": ("climate", "set_temperature", "temperature"),
            }
            if domain in service_map:
                svc_domain, svc_name, field = service_map[domain]
                payload = {"entity_id": entity_id, field: value}
                response = self._client.post(f"/api/services/{svc_domain}/{svc_name}", json=payload)
            else:
                payload = {"entity_id": entity_id, "value": value}
                response = self._client.post(f"/api/services/{domain}/set_value", json=payload)
            response.raise_for_status()
            return f"Valeur '{value}' définie sur {entity_id}."
        except Exception as e:
            return f"Erreur HomeAssistant: {str(e)}"
