import os

SPOTIFY_CLIENT_ID     = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI  = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8000/spotify/callback")
SPOTIFY_CACHE_PATH    = os.path.join(os.path.dirname(__file__), "..", ".spotify_token")

SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "playlist-read-private "
    "user-library-read"
)


class SpotifyMCP:
    def __init__(self):
        self._sp = None
        self._oauth = None

    def _get_oauth(self):
        """Retourne l'objet SpotifyOAuth (non-interactif, lit le cache si disponible)."""
        if self._oauth is None:
            import spotipy
            from spotipy.oauth2 import SpotifyOAuth
            self._oauth = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope=SCOPES,
                cache_path=SPOTIFY_CACHE_PATH,
                open_browser=False,
            )
        return self._oauth

    def get_auth_url(self) -> str:
        """Retourne l'URL d'autorisation OAuth à visiter dans le navigateur."""
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            return "SPOTIFY_CLIENT_ID ou SPOTIFY_CLIENT_SECRET manquant."
        return self._get_oauth().get_authorize_url()

    def handle_callback(self, code: str) -> bool:
        """Échange le code OAuth contre un token et le met en cache. Appelé par server.py."""
        try:
            token_info = self._get_oauth().get_access_token(code, as_dict=True, check_cache=False)
            if not token_info:
                return False
            import spotipy
            self._sp = spotipy.Spotify(auth_manager=self._get_oauth())
            return True
        except Exception as e:
            print(f"[SPOTIFY] handle_callback error: {e}")
            return False

    def _ensure_connected(self) -> bool:
        """Tente de se connecter via le token caché. Retourne False si pas encore autorisé."""
        if self._sp:
            return True
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            return False
        try:
            import spotipy
            oauth = self._get_oauth()
            token_info = oauth.get_cached_token()
            if not token_info:
                return False
            if oauth.is_token_expired(token_info):
                token_info = oauth.refresh_access_token(token_info["refresh_token"])
            if not token_info:
                return False
            self._sp = spotipy.Spotify(auth_manager=oauth)
            return True
        except Exception as e:
            print(f"[SPOTIFY] _ensure_connected error: {e}")
            return False

    def _not_auth_msg(self) -> str:
        url = self.get_auth_url()
        return f"Spotify non autorisé. Visite cette URL pour autoriser : {url}"

    def get_current_playback(self) -> str:
        if not self._ensure_connected():
            return self._not_auth_msg()
        try:
            playback = self._sp.current_playback()
            if not playback or not playback.get("item"):
                return "Rien ne joue en ce moment."
            item = playback["item"]
            track = item.get("name", "?")
            artists = ", ".join(a["name"] for a in item.get("artists", []))
            album = item.get("album", {}).get("name", "?")
            progress_ms = playback.get("progress_ms", 0)
            duration_ms = item.get("duration_ms", 1)
            progress = f"{progress_ms // 60000}:{(progress_ms % 60000) // 1000:02d}"
            duration = f"{duration_ms // 60000}:{(duration_ms % 60000) // 1000:02d}"
            is_playing = playback.get("is_playing", False)
            volume = playback.get("device", {}).get("volume_percent", "?")
            device = playback.get("device", {}).get("name", "?")
            return (
                f"{'En lecture' if is_playing else 'En pause'}: {track}\n"
                f"Artiste(s): {artists}\n"
                f"Album: {album}\n"
                f"Progression: {progress} / {duration}\n"
                f"Volume: {volume}% | Appareil: {device}"
            )
        except Exception as e:
            return f"Erreur Spotify: {str(e)}"

    def play(self, uri: str = "", device_id: str = "") -> str:
        if not self._ensure_connected():
            return self._not_auth_msg()
        try:
            kwargs = {}
            if device_id:
                kwargs["device_id"] = device_id
            if uri:
                if uri.startswith("spotify:track:"):
                    kwargs["uris"] = [uri]
                else:
                    kwargs["context_uri"] = uri
            self._sp.start_playback(**kwargs)
            return f"Lecture {'de ' + uri if uri else ''}démarrée."
        except Exception as e:
            return f"Erreur Spotify: {str(e)}"

    def pause(self) -> str:
        if not self._ensure_connected():
            return self._not_auth_msg()
        try:
            self._sp.pause_playback()
            return "Lecture mise en pause."
        except Exception as e:
            return f"Erreur Spotify: {str(e)}"

    def next_track(self) -> str:
        if not self._ensure_connected():
            return self._not_auth_msg()
        try:
            self._sp.next_track()
            return "Piste suivante."
        except Exception as e:
            return f"Erreur Spotify: {str(e)}"

    def previous_track(self) -> str:
        if not self._ensure_connected():
            return self._not_auth_msg()
        try:
            self._sp.previous_track()
            return "Piste précédente."
        except Exception as e:
            return f"Erreur Spotify: {str(e)}"

    def set_volume(self, volume_percent: int) -> str:
        if not self._ensure_connected():
            return self._not_auth_msg()
        try:
            volume = max(0, min(100, int(volume_percent)))
            self._sp.volume(volume)
            return f"Volume réglé à {volume}%."
        except Exception as e:
            return f"Erreur Spotify: {str(e)}"

    def search(self, query: str, search_type: str = "track", limit: int = 5) -> str:
        if not self._ensure_connected():
            return self._not_auth_msg()
        try:
            valid_types = {"track", "album", "playlist", "artist"}
            if search_type not in valid_types:
                search_type = "track"
            results = self._sp.search(q=query, type=search_type, limit=limit)
            items = results.get(f"{search_type}s", {}).get("items", [])
            if not items:
                return f"Aucun résultat pour '{query}' (type: {search_type})."
            lines = []
            for item in items:
                name = item.get("name", "?")
                uri = item.get("uri", "")
                if search_type == "track":
                    artists = ", ".join(a["name"] for a in item.get("artists", []))
                    lines.append(f"{name} — {artists} | {uri}")
                elif search_type == "album":
                    artists = ", ".join(a["name"] for a in item.get("artists", []))
                    lines.append(f"{name} — {artists} | {uri}")
                elif search_type == "playlist":
                    owner = item.get("owner", {}).get("display_name", "?")
                    lines.append(f"{name} (par {owner}) | {uri}")
                else:
                    lines.append(f"{name} | {uri}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Spotify: {str(e)}"

    def get_playlists(self, limit: int = 20) -> str:
        if not self._ensure_connected():
            return self._not_auth_msg()
        try:
            results = self._sp.current_user_playlists(limit=limit)
            items = results.get("items", [])
            if not items:
                return "Aucune playlist trouvée."
            lines = []
            for p in items:
                name = p.get("name", "?")
                uri = p.get("uri", "")
                total = p.get("tracks", {}).get("total", "?")
                lines.append(f"{name} | {total} titres | {uri}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur Spotify: {str(e)}"

    def add_to_queue(self, uri: str) -> str:
        if not self._ensure_connected():
            return self._not_auth_msg()
        try:
            self._sp.add_to_queue(uri)
            return f"'{uri}' ajouté à la file de lecture."
        except Exception as e:
            return f"Erreur Spotify: {str(e)}"
