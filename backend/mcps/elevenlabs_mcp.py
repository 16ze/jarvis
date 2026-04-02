import os

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_DEFAULT_VOICE_ID", "")


class ElevenLabsMCP:
    def __init__(self):
        self._client = None

    def _ensure_connected(self):
        if not self._client:
            if not ELEVENLABS_API_KEY:
                return False
            from elevenlabs.client import ElevenLabs
            self._client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        return True

    def text_to_speech(self, text: str, voice_id: str = "", output_path: str = "") -> str:
        if not self._ensure_connected():
            return "Erreur ElevenLabs: ELEVENLABS_API_KEY manquant."
        try:
            target_voice = voice_id or ELEVENLABS_DEFAULT_VOICE_ID or "Rachel"
            if not output_path:
                import tempfile
                output_path = os.path.join(tempfile.gettempdir(), f"jarvis_tts_{os.getpid()}.mp3")
            audio_generator = self._client.text_to_speech.convert(
                voice_id=target_voice,
                text=text,
                model_id="eleven_multilingual_v2",
            )
            with open(output_path, "wb") as f:
                for chunk in audio_generator:
                    f.write(chunk)
            size_kb = os.path.getsize(output_path) // 1024
            return f"Audio généré: {output_path} ({size_kb} KB)"
        except Exception as e:
            return f"Erreur ElevenLabs: {str(e)}"

    def list_voices(self) -> str:
        if not self._ensure_connected():
            return "Erreur ElevenLabs: ELEVENLABS_API_KEY manquant."
        try:
            response = self._client.voices.get_all()
            voices = response.voices if hasattr(response, "voices") else []
            if not voices:
                return "Aucune voix disponible."
            lines = ["Voix ElevenLabs disponibles:"]
            for v in voices:
                voice_id = v.voice_id
                name = v.name
                category = getattr(v, "category", "?")
                labels = getattr(v, "labels", {}) or {}
                gender = labels.get("gender", "?")
                accent = labels.get("accent", "")
                accent_str = f" | Accent: {accent}" if accent else ""
                lines.append(f"  [{voice_id}] {name} | {category} | Genre: {gender}{accent_str}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur ElevenLabs: {str(e)}"

    def get_voice(self, voice_id: str) -> str:
        if not self._ensure_connected():
            return "Erreur ElevenLabs: ELEVENLABS_API_KEY manquant."
        try:
            voice = self._client.voices.get(voice_id)
            name = voice.name
            category = getattr(voice, "category", "?")
            description = getattr(voice, "description", "") or ""
            labels = getattr(voice, "labels", {}) or {}
            settings = getattr(voice, "settings", None)
            lines = [
                f"Voix: {name}",
                f"ID: {voice_id}",
                f"Catégorie: {category}",
            ]
            if description:
                lines.append(f"Description: {description}")
            for key, val in labels.items():
                lines.append(f"  {key}: {val}")
            if settings:
                lines.append(f"Stabilité: {getattr(settings, 'stability', '?')}")
                lines.append(f"Similarité: {getattr(settings, 'similarity_boost', '?')}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur ElevenLabs: {str(e)}"

    def clone_voice(self, name: str, files_paths: list) -> str:
        if not self._ensure_connected():
            return "Erreur ElevenLabs: ELEVENLABS_API_KEY manquant."
        try:
            if not files_paths:
                return "Erreur ElevenLabs: Au moins un fichier audio requis pour cloner une voix."
            files = []
            for path in files_paths:
                if not os.path.exists(path):
                    return f"Erreur ElevenLabs: Fichier introuvable: {path}"
                files.append(open(path, "rb"))
            try:
                voice = self._client.clone(
                    name=name,
                    files=files,
                )
                voice_id = voice.voice_id if hasattr(voice, "voice_id") else str(voice)
                return (
                    f"Voix clonée: {name}\n"
                    f"ID: {voice_id}\n"
                    f"Fichiers utilisés: {len(files_paths)}"
                )
            finally:
                for f in files:
                    f.close()
        except Exception as e:
            return f"Erreur ElevenLabs: {str(e)}"
