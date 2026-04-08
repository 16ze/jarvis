"""
CastAgent — Contrôle Chromecast via pychromecast
Toutes les méthodes publiques sont async et retournent une str.
"""
import asyncio
import os
import re
import time
from typing import Optional


class CastAgent:
    def __init__(self):
        self._cast = None          # Chromecast actif
        self._browser = None       # Stop callback discovery
        self._initialized = False

    # ──────────────────────────────────────────────────────────────────────────
    # INITIALISATION
    # ──────────────────────────────────────────────────────────────────────────

    async def initialize(self) -> str:
        """Découverte automatique du Chromecast sur le réseau local."""
        return await asyncio.to_thread(self._sync_initialize)

    def _sync_initialize(self) -> str:
        try:
            import pychromecast
        except ImportError:
            return "Erreur: pychromecast non installé. Lance: pip install pychromecast"

        target_name = os.getenv("CHROMECAST_NAME", "").strip()

        try:
            chromecasts, browser = pychromecast.get_chromecasts(timeout=10)
        except Exception as e:
            return f"Erreur découverte Chromecast: {e}"

        if not chromecasts:
            if browser:
                browser.stop_discovery()
            self._initialized = True
            return "Aucun Chromecast trouvé sur le réseau."

        # Sélection par nom ou premier disponible
        cast = None
        if target_name:
            for cc in chromecasts:
                if cc.name.lower() == target_name.lower():
                    cast = cc
                    break
            if cast is None:
                # Fallback sur le premier si le nom configuré n'est pas trouvé
                cast = chromecasts[0]
                print(f"[CastAgent] '{target_name}' non trouvé, utilise '{cast.name}'")
        else:
            cast = chromecasts[0]

        cast.wait()  # Attend que la connexion soit prête
        self._cast = cast
        self._browser = browser
        self._initialized = True
        host = cast.cast_info.host if cast.cast_info else "?"
        print(f"[CastAgent] Connecté à '{cast.name}' ({host})")
        return f"Chromecast '{cast.name}' connecté ({host})."

    def _ensure_cast(self) -> Optional[str]:
        """Retourne un message d'erreur si aucun Chromecast n'est prêt, None sinon."""
        if not self._cast:
            return "Aucun Chromecast connecté. Appelle initialize() d'abord."
        return None

    # ──────────────────────────────────────────────────────────────────────────
    # STATUS
    # ──────────────────────────────────────────────────────────────────────────

    async def get_status(self) -> str:
        """Retourne ce qui joue en ce moment sur le Chromecast."""
        err = self._ensure_cast()
        if err:
            return err
        return await asyncio.to_thread(self._sync_get_status)

    def _sync_get_status(self) -> str:
        try:
            cast = self._cast
            cast.media_controller.update_status()
            time.sleep(0.5)
            status = cast.media_controller.status

            app = cast.app_display_name or "Aucune app"
            vol = round(cast.status.volume_level * 100) if cast.status else 0
            muted = cast.status.volume_muted if cast.status else False

            if status and status.player_state not in ("UNKNOWN", "IDLE", None):
                title = status.title or "Titre inconnu"
                artist = status.artist or ""
                player_state = status.player_state
                duration = status.duration or 0
                current = status.current_time or 0

                info = f"App: {app} | État: {player_state} | Volume: {vol}%"
                if muted:
                    info += " (muet)"
                info += f"\nEn cours: {title}"
                if artist:
                    info += f" — {artist}"
                if duration:
                    info += f" ({int(current//60)}:{int(current%60):02d} / {int(duration//60)}:{int(duration%60):02d})"
                return info
            else:
                return f"App: {app} | Aucune lecture en cours | Volume: {vol}%"
        except Exception as e:
            return f"Erreur status Chromecast: {e}"

    # ──────────────────────────────────────────────────────────────────────────
    # CONTRÔLES LECTURE
    # ──────────────────────────────────────────────────────────────────────────

    async def play(self) -> str:
        """Reprend la lecture."""
        err = self._ensure_cast()
        if err:
            return err
        return await asyncio.to_thread(self._sync_play)

    def _sync_play(self) -> str:
        try:
            self._cast.media_controller.play()
            return "Lecture reprise."
        except Exception as e:
            return f"Erreur play Chromecast: {e}"

    async def pause(self) -> str:
        """Met en pause."""
        err = self._ensure_cast()
        if err:
            return err
        return await asyncio.to_thread(self._sync_pause)

    def _sync_pause(self) -> str:
        try:
            self._cast.media_controller.pause()
            return "Lecture mise en pause."
        except Exception as e:
            return f"Erreur pause Chromecast: {e}"

    async def stop(self) -> str:
        """Arrête la lecture et quitte l'app."""
        err = self._ensure_cast()
        if err:
            return err
        return await asyncio.to_thread(self._sync_stop)

    def _sync_stop(self) -> str:
        try:
            self._cast.media_controller.stop()
            return "Lecture arrêtée."
        except Exception as e:
            return f"Erreur stop Chromecast: {e}"

    # ──────────────────────────────────────────────────────────────────────────
    # VOLUME
    # ──────────────────────────────────────────────────────────────────────────

    async def set_volume(self, level: float) -> str:
        """Règle le volume (0.0 à 1.0)."""
        err = self._ensure_cast()
        if err:
            return err
        level = max(0.0, min(1.0, float(level)))
        return await asyncio.to_thread(self._sync_set_volume, level)

    def _sync_set_volume(self, level: float) -> str:
        try:
            self._cast.set_volume(level)
            return f"Volume réglé à {int(level * 100)}%."
        except Exception as e:
            return f"Erreur volume Chromecast: {e}"

    # ──────────────────────────────────────────────────────────────────────────
    # YOUTUBE
    # ──────────────────────────────────────────────────────────────────────────

    async def play_youtube(self, video_url: str) -> str:
        """Lance une vidéo YouTube sur le Chromecast via son URL."""
        err = self._ensure_cast()
        if err:
            return err
        video_id = self._extract_youtube_id(video_url)
        if not video_id:
            return f"Impossible d'extraire l'ID YouTube depuis: {video_url}"
        return await asyncio.to_thread(self._sync_play_youtube, video_id)

    def _extract_youtube_id(self, url: str) -> Optional[str]:
        """Extrait l'ID vidéo YouTube depuis une URL."""
        patterns = [
            r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})",
            r"^([a-zA-Z0-9_-]{11})$",  # ID brut
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _sync_play_youtube(self, video_id: str) -> str:
        try:
            from pychromecast.controllers.youtube import YouTubeController
            yt = YouTubeController()
            self._cast.register_handler(yt)
            yt.play_video(video_id)
            return f"Vidéo YouTube '{video_id}' lancée sur '{self._cast.name}'."
        except Exception as e:
            return f"Erreur YouTube Chromecast: {e}"

    # ──────────────────────────────────────────────────────────────────────────
    # MEDIA ARBITRAIRE
    # ──────────────────────────────────────────────────────────────────────────

    async def play_media(self, url: str, media_type: str = "video/mp4") -> str:
        """Lance n'importe quel média via URL directe sur le Chromecast."""
        err = self._ensure_cast()
        if err:
            return err
        return await asyncio.to_thread(self._sync_play_media, url, media_type)

    def _sync_play_media(self, url: str, media_type: str) -> str:
        try:
            self._cast.media_controller.play_media(url, media_type)
            self._cast.media_controller.block_until_active()
            return f"Média lancé sur '{self._cast.name}': {url[:80]}"
        except Exception as e:
            return f"Erreur play_media Chromecast: {e}"

    # ──────────────────────────────────────────────────────────────────────────
    # LISTE DES APPAREILS
    # ──────────────────────────────────────────────────────────────────────────

    async def get_devices(self) -> str:
        """Liste tous les Chromecasts disponibles sur le réseau local."""
        return await asyncio.to_thread(self._sync_get_devices)

    def _sync_get_devices(self) -> str:
        try:
            import pychromecast
            chromecasts, browser = pychromecast.get_chromecasts(timeout=10)
            if not chromecasts:
                if browser:
                    browser.stop_discovery()
                return "Aucun Chromecast détecté sur le réseau."
            result = []
            for cc in chromecasts:
                active = " [ACTIF]" if self._cast and cc.name == self._cast.name else ""
                host = cc.cast_info.host if cc.cast_info else "?"
                result.append(f"• {cc.name} ({host}) — modèle: {cc.model_name}{active}")
            if browser:
                browser.stop_discovery()
            return f"{len(chromecasts)} Chromecast(s) trouvé(s):\n" + "\n".join(result)
        except Exception as e:
            return f"Erreur découverte Chromecast: {e}"

    # ──────────────────────────────────────────────────────────────────────────
    # CLEANUP
    # ──────────────────────────────────────────────────────────────────────────

    def disconnect(self):
        """Déconnecte proprement le Chromecast."""
        try:
            if self._browser:
                self._browser.stop_discovery()
            if self._cast:
                self._cast.disconnect()
        except Exception:
            pass
        self._cast = None
        self._browser = None


# ── Test standalone ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def main():
        agent = CastAgent()
        print(await agent.initialize())
        print(await agent.get_devices())
        print(await agent.get_status())

    asyncio.run(main())
