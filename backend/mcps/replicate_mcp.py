import os
import json

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")


class ReplicateMCP:
    def __init__(self):
        self._client = None

    def _ensure_connected(self):
        if not self._client:
            if not REPLICATE_API_TOKEN:
                return False
            import replicate
            self._client = replicate.Client(api_token=REPLICATE_API_TOKEN)
        return True

    def generate_image(
        self,
        prompt: str,
        model: str = "stability-ai/sdxl",
        width: int = 1024,
        height: int = 1024,
    ) -> str:
        if not self._ensure_connected():
            return "Erreur Replicate: REPLICATE_API_TOKEN manquant."
        try:
            output = self._client.run(
                model,
                input={
                    "prompt": prompt,
                    "width": width,
                    "height": height,
                },
            )
            if not output:
                return "Aucune image générée."
            if isinstance(output, list):
                urls = [str(url) for url in output]
            else:
                urls = [str(output)]
            lines = [f"Image(s) générée(s) pour: '{prompt}'"]
            for i, url in enumerate(urls, 1):
                lines.append(f"  Image {i}: {url}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Replicate: {str(e)}"

    def run_model(self, model_version: str, input_json: str) -> str:
        if not self._ensure_connected():
            return "Erreur Replicate: REPLICATE_API_TOKEN manquant."
        try:
            input_data = json.loads(input_json)
            output = self._client.run(model_version, input=input_data)
            if output is None:
                return "Modèle exécuté, aucune sortie."
            if isinstance(output, (list, dict)):
                result = json.dumps(output, indent=2, default=str)
            else:
                result = str(output)
            if len(result) > 2000:
                result = result[:2000] + "... [sortie tronquée]"
            return f"Résultat du modèle {model_version}:\n{result}"
        except json.JSONDecodeError as e:
            return f"Erreur Replicate: input_json invalide — {str(e)}"
        except Exception as e:
            return f"Erreur Replicate: {str(e)}"

    def list_predictions(self, limit: int = 10) -> str:
        if not self._ensure_connected():
            return "Erreur Replicate: REPLICATE_API_TOKEN manquant."
        try:
            import replicate
            predictions = replicate.predictions.list()
            items = []
            for pred in predictions:
                items.append(pred)
                if len(items) >= limit:
                    break
            if not items:
                return "Aucune prédiction récente."
            lines = [f"Prédictions récentes ({len(items)}):"]
            for p in items:
                pred_id = getattr(p, "id", "?")
                status = getattr(p, "status", "?")
                model = getattr(p, "model", getattr(p, "version", "?"))
                created = str(getattr(p, "created_at", "?"))[:19]
                output = getattr(p, "output", None)
                output_str = ""
                if output:
                    if isinstance(output, list):
                        output_str = f" | Sorties: {len(output)}"
                    else:
                        output_str = " | Sortie disponible"
                lines.append(f"  [{pred_id}] {model} | {status} | {created}{output_str}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Replicate: {str(e)}"
