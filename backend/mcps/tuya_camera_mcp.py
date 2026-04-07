"""
TuyaCameraMCP — Yeux d'Ada via caméra SmartLife/Tuya PTZ.

Fournit :
  - get_rtsp_url()       → URL RTSP rafraîchie automatiquement (expire ~30min)
  - ptz_move(dir, ms)    → rotation directionnelle
  - ptz_preset(n)        → position préenregistrée
  - take_snapshot()      → capture d'une frame → payload image Gemini
"""
import asyncio
import base64
import io
import os
import time

try:
    import tinytuya
except ImportError:
    tinytuya = None
    print("[TuyaCamera] WARNING: tinytuya not installed. Run: pip install tinytuya")

try:
    import cv2
    import PIL.Image
except ImportError:
    cv2 = None
    PIL = None

# Direction code → Tuya DPS value (PTZ standard 8 directions)
_PTZ_DIR = {
    "up": "0",
    "upper_right": "1",
    "right": "2",
    "lower_right": "3",
    "down": "4",
    "lower_left": "5",
    "left": "6",
    "upper_left": "7",
}
_PTZ_DIR_FR = {
    "haut": "up",
    "droite": "right",
    "bas": "down",
    "gauche": "left",
    "haut-droite": "upper_right",
    "bas-droite": "lower_right",
    "bas-gauche": "lower_left",
    "haut-gauche": "upper_left",
}


class TuyaCameraMCP:
    def __init__(self):
        self._cloud = None
        self._device_id: str = os.getenv("TUYA_CAMERA_DEVICE_ID", "bfa3abf3b230492633dtqe")
        self._rtsp_url: str | None = None
        self._rtsp_expires: float = 0.0
        self._initialized = False
        self._motion_watch_active = False
        self._init()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init(self):
        if not tinytuya:
            return
        api_key = os.getenv("TUYA_API_KEY", "")
        api_secret = os.getenv("TUYA_API_SECRET", "")
        api_region = os.getenv("TUYA_API_REGION", "eu")

        # Fallback : lire tinytuya.json si les env vars sont absentes
        if not api_key or not api_secret:
            import json
            from pathlib import Path
            tinytuya_json = Path(__file__).parent.parent / "tinytuya.json"
            if tinytuya_json.exists():
                try:
                    cfg = json.loads(tinytuya_json.read_text())
                    api_key = api_key or cfg.get("apiKey", "")
                    api_secret = api_secret or cfg.get("apiSecret", "")
                    api_region = api_region or cfg.get("apiRegion", "eu")
                    print("[TuyaCamera] Credentials chargés depuis tinytuya.json")
                except Exception as e:
                    print(f"[TuyaCamera] Erreur lecture tinytuya.json: {e}")

        if not api_key or not api_secret:
            print("[TuyaCamera] TUYA_API_KEY / TUYA_API_SECRET manquants.")
            return
        try:
            self._cloud = tinytuya.Cloud(
                apiRegion=api_region,
                apiKey=api_key,
                apiSecret=api_secret,
            )
            self._initialized = True
            print(f"[TuyaCamera] Initialisé — device_id={self._device_id}")
        except Exception as e:
            print(f"[TuyaCamera] Init error: {e}")

    # ── RTSP stream URL ────────────────────────────────────────────────────────

    def _fetch_rtsp_sync(self) -> str | None:
        if not self._cloud:
            return None
        try:
            result = self._cloud.cloudrequest(
                f"/v1.0/devices/{self._device_id}/stream/actions/allocate",
                post={"type": "rtsp"},
            )
            if result and result.get("success"):
                url = result.get("result", {}).get("url")
                if url:
                    print(f"[TuyaCamera] RTSP URL obtenue (expire dans ~30min)")
                    return url
            print(f"[TuyaCamera] Réponse RTSP inattendue: {result}")
        except Exception as e:
            print(f"[TuyaCamera] Erreur fetch RTSP: {e}")
        return None

    async def get_rtsp_url(self) -> str | None:
        """Retourne l'URL RTSP valide, la rafraîchit si expirée."""
        now = time.time()
        if self._rtsp_url and now < self._rtsp_expires:
            return self._rtsp_url
        url = await asyncio.to_thread(self._fetch_rtsp_sync)
        if url:
            self._rtsp_url = url
            self._rtsp_expires = now + 25 * 60  # refresh 5min avant expiry
        return url

    def invalidate_rtsp(self):
        """Force le rafraîchissement de l'URL RTSP au prochain appel."""
        self._rtsp_url = None
        self._rtsp_expires = 0.0

    # ── PTZ ───────────────────────────────────────────────────────────────────

    def _resolve_direction(self, direction: str) -> str | None:
        """Accepte direction en FR ou EN, retourne la clé anglaise ou None."""
        d = direction.lower().strip()
        d = _PTZ_DIR_FR.get(d, d)  # traduire FR → EN si nécessaire
        return d if d in _PTZ_DIR else None

    def _ptz_move_sync(self, direction: str, duration_ms: int) -> str:
        if not self._cloud:
            return "Erreur: TuyaCameraMCP non initialisé (vérifier TUYA_API_KEY)"
        dir_key = self._resolve_direction(direction)
        if not dir_key:
            valid = list(_PTZ_DIR.keys()) + list(_PTZ_DIR_FR.keys())
            return f"Direction inconnue: '{direction}'. Valeurs acceptées: {valid}"
        code = _PTZ_DIR[dir_key]
        try:
            # Démarrer le mouvement
            self._cloud.cloudrequest(
                f"/v1.0/devices/{self._device_id}/commands",
                post={"commands": [{"code": "ptz_control", "value": code}]},
            )
            time.sleep(max(100, min(duration_ms, 5000)) / 1000)
            # Arrêter
            self._cloud.cloudrequest(
                f"/v1.0/devices/{self._device_id}/commands",
                post={"commands": [{"code": "ptz_stop", "value": "0"}]},
            )
            return f"Caméra déplacée vers '{dir_key}' pendant {duration_ms}ms."
        except Exception as e:
            return f"Erreur PTZ move: {e}"

    async def ptz_move(self, direction: str, duration_ms: int = 600) -> str:
        return await asyncio.to_thread(self._ptz_move_sync, direction, duration_ms)

    def _ptz_preset_sync(self, preset: int) -> str:
        if not self._cloud:
            return "Erreur: TuyaCameraMCP non initialisé"
        try:
            self._cloud.cloudrequest(
                f"/v1.0/devices/{self._device_id}/commands",
                post={"commands": [{"code": "ptz_preset_goto", "value": str(preset)}]},
            )
            return f"Caméra positionnée sur preset {preset}."
        except Exception as e:
            return f"Erreur PTZ preset: {e}"

    async def ptz_preset(self, preset: int) -> str:
        return await asyncio.to_thread(self._ptz_preset_sync, preset)

    # ── Snapshot ──────────────────────────────────────────────────────────────

    async def take_snapshot(self) -> dict | None:
        """
        Capture une frame depuis le flux RTSP.
        Retourne un payload image Gemini: {"mime_type": "image/jpeg", "data": "<b64>"}
        ou None si échec.
        """
        if not cv2 or not PIL:
            print("[TuyaCamera] cv2/PIL non disponibles pour le snapshot.")
            return None

        rtsp_url = await self.get_rtsp_url()
        if not rtsp_url:
            print("[TuyaCamera] Impossible d'obtenir l'URL RTSP.")
            return None

        def _capture() -> dict | None:
            cap = cv2.VideoCapture(rtsp_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            # Lire quelques frames pour vider le buffer initial
            for _ in range(3):
                cap.read()
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return None
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = PIL.Image.fromarray(frame_rgb)
            img.thumbnail([1024, 1024])
            buf = io.BytesIO()
            img.save(buf, format="jpeg", quality=85)
            return {
                "mime_type": "image/jpeg",
                "data": base64.b64encode(buf.getvalue()).decode(),
            }

        try:
            payload = await asyncio.to_thread(_capture)
            if payload:
                print("[TuyaCamera] Snapshot capturé.")
            else:
                print("[TuyaCamera] Snapshot échoué — frame vide.")
                self.invalidate_rtsp()  # URL peut-être expirée
            return payload
        except Exception as e:
            print(f"[TuyaCamera] Erreur snapshot: {e}")
            return None

    # ── Tracking automatique ──────────────────────────────────────────────────

    def _set_tracking_sync(self, enabled: bool) -> str:
        """Active/désactive le suivi automatique de mouvement (auto-tracking PTZ)."""
        if not self._cloud:
            return "Erreur: TuyaCameraMCP non initialisé"
        try:
            result = self._cloud.cloudrequest(
                f"/v1.0/devices/{self._device_id}/commands",
                post={"commands": [{"code": "track_switch", "value": enabled}]},
            )
            state = "activé" if enabled else "désactivé"
            if result and result.get("success"):
                return f"Suivi automatique {state}."
            # Certains modèles utilisent un code différent
            result2 = self._cloud.cloudrequest(
                f"/v1.0/devices/{self._device_id}/commands",
                post={"commands": [{"code": "motion_tracking", "value": enabled}]},
            )
            return f"Suivi automatique {state}."
        except Exception as e:
            return f"Erreur tracking: {e}"

    async def set_tracking(self, enabled: bool) -> str:
        return await asyncio.to_thread(self._set_tracking_sync, enabled)

    # ── Détection de mouvement ────────────────────────────────────────────────

    def _set_motion_detect_sync(self, enabled: bool, sensitivity: str = "medium") -> str:
        """Active/désactive la détection de mouvement et règle la sensibilité."""
        if not self._cloud:
            return "Erreur: TuyaCameraMCP non initialisé"
        # Sensibilité : "low"→"0", "medium"→"1", "high"→"2"
        sens_map = {"low": "0", "faible": "0", "medium": "1", "moyen": "1",
                    "moyenne": "1", "high": "2", "élevée": "2", "eleve": "2"}
        sens_code = sens_map.get(sensitivity.lower(), "1")
        try:
            commands = [{"code": "motion_switch", "value": enabled}]
            if enabled:
                commands.append({"code": "motion_sensitivity", "value": sens_code})
            self._cloud.cloudrequest(
                f"/v1.0/devices/{self._device_id}/commands",
                post={"commands": commands},
            )
            state = "activée" if enabled else "désactivée"
            sens_label = {"0": "faible", "1": "moyenne", "2": "élevée"}.get(sens_code, "moyenne")
            return f"Détection de mouvement {state}" + (f" (sensibilité {sens_label})." if enabled else ".")
        except Exception as e:
            return f"Erreur motion detect: {e}"

    async def set_motion_detect(self, enabled: bool, sensitivity: str = "medium") -> str:
        return await asyncio.to_thread(self._set_motion_detect_sync, enabled, sensitivity)

    # ── Surveillance active (polling alertes) ────────────────────────────────

    def _get_motion_events_sync(self, limit: int = 10) -> list[dict]:
        """Récupère les derniers événements de mouvement depuis le cloud Tuya."""
        if not self._cloud:
            return []
        try:
            result = self._cloud.cloudrequest(
                f"/v2.0/cloud/thing/{self._device_id}/alarm/logs",
                params={"page_size": limit},
            )
            if result and result.get("success"):
                return result.get("result", {}).get("logs", [])
        except Exception as e:
            print(f"[TuyaCamera] Erreur get_motion_events: {e}")
        return []

    async def get_motion_events(self, limit: int = 10) -> list[dict]:
        return await asyncio.to_thread(self._get_motion_events_sync, limit)

    async def start_motion_watch(
        self,
        on_motion,          # async callable(snapshot_payload | None)
        poll_interval: int = 15,
        with_snapshot: bool = True,
    ):
        """
        Boucle de surveillance : poll les événements toutes les `poll_interval` secondes.
        Appelle `on_motion(payload)` dès qu'un nouveau mouvement est détecté.
        `payload` est le dict image Gemini ou None si snapshot désactivé.
        """
        self._motion_watch_active = True
        last_event_id: str | None = None
        print(f"[TuyaCamera] Surveillance mouvement démarrée (poll {poll_interval}s).")
        while self._motion_watch_active:
            try:
                events = await self.get_motion_events(limit=5)
                if events:
                    newest = events[0]
                    event_id = str(newest.get("alarm_id") or newest.get("event_id") or newest.get("id", ""))
                    if event_id and event_id != last_event_id:
                        last_event_id = event_id
                        print(f"[TuyaCamera] Mouvement détecté ! event_id={event_id}")
                        snapshot = await self.take_snapshot() if with_snapshot else None
                        await on_motion(snapshot)
            except Exception as e:
                print(f"[TuyaCamera] Erreur motion watch: {e}")
            await asyncio.sleep(poll_interval)
        print("[TuyaCamera] Surveillance mouvement arrêtée.")

    def stop_motion_watch(self):
        self._motion_watch_active = False
