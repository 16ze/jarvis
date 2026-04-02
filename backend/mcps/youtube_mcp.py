import os
import re

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")


def _extract_video_id(video_id_or_url: str) -> str:
    if "youtube.com" in video_id_or_url or "youtu.be" in video_id_or_url:
        patterns = [
            r"(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})",
            r"(?:embed/)([a-zA-Z0-9_-]{11})",
        ]
        for pattern in patterns:
            match = re.search(pattern, video_id_or_url)
            if match:
                return match.group(1)
    return video_id_or_url


class YouTubeMCP:
    def __init__(self):
        self._client = None

    def _ensure_connected(self):
        if not self._client:
            if not YOUTUBE_API_KEY:
                return False
            from googleapiclient.discovery import build
            self._client = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        return True

    def search_videos(self, query: str, limit: int = 5) -> str:
        if not self._ensure_connected():
            return "Erreur YouTube: YOUTUBE_API_KEY manquant."
        try:
            response = self._client.search().list(
                q=query,
                part="snippet",
                type="video",
                maxResults=limit,
                order="relevance",
            ).execute()
            items = response.get("items", [])
            if not items:
                return f"Aucune vidéo trouvée pour '{query}'."
            video_ids = [item["id"]["videoId"] for item in items]
            stats_response = self._client.videos().list(
                part="statistics",
                id=",".join(video_ids),
            ).execute()
            stats_map = {v["id"]: v.get("statistics", {}) for v in stats_response.get("items", [])}
            lines = [f"Résultats YouTube pour '{query}':"]
            for item in items:
                video_id = item["id"]["videoId"]
                snippet = item.get("snippet", {})
                title = snippet.get("title", "?")
                channel = snippet.get("channelTitle", "?")
                views = stats_map.get(video_id, {}).get("viewCount", "?")
                url = f"https://www.youtube.com/watch?v={video_id}"
                views_str = f"{int(views):,}" if views != "?" else "?"
                lines.append(f"  {title}\n    Chaîne: {channel} | Vues: {views_str}\n    {url}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur YouTube: {str(e)}"

    def get_video_info(self, video_id_or_url: str) -> str:
        if not self._ensure_connected():
            return "Erreur YouTube: YOUTUBE_API_KEY manquant."
        try:
            video_id = _extract_video_id(video_id_or_url)
            response = self._client.videos().list(
                part="snippet,statistics,contentDetails",
                id=video_id,
            ).execute()
            items = response.get("items", [])
            if not items:
                return f"Vidéo introuvable: {video_id_or_url}"
            item = items[0]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            details = item.get("contentDetails", {})
            title = snippet.get("title", "?")
            channel = snippet.get("channelTitle", "?")
            description = snippet.get("description", "")[:300]
            published = snippet.get("publishedAt", "?")[:10]
            duration_raw = details.get("duration", "PT0S")
            duration_match = re.findall(r"(\d+)([HMS])", duration_raw)
            duration_parts = {"H": 0, "M": 0, "S": 0}
            for val, unit in duration_match:
                duration_parts[unit] = int(val)
            duration = f"{duration_parts['H']}:{duration_parts['M']:02d}:{duration_parts['S']:02d}" if duration_parts["H"] else f"{duration_parts['M']}:{duration_parts['S']:02d}"
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            return (
                f"Titre: {title}\n"
                f"Chaîne: {channel}\n"
                f"Publié: {published}\n"
                f"Durée: {duration}\n"
                f"Vues: {views:,} | Likes: {likes:,} | Commentaires: {comments:,}\n"
                f"URL: https://www.youtube.com/watch?v={video_id}\n"
                f"Description: {description}{'...' if len(snippet.get('description', '')) > 300 else ''}"
            )
        except Exception as e:
            return f"Erreur YouTube: {str(e)}"

    def get_channel_videos(self, channel_id: str, limit: int = 10) -> str:
        if not self._ensure_connected():
            return "Erreur YouTube: YOUTUBE_API_KEY manquant."
        try:
            response = self._client.search().list(
                channelId=channel_id,
                part="snippet",
                type="video",
                order="date",
                maxResults=limit,
            ).execute()
            items = response.get("items", [])
            if not items:
                return f"Aucune vidéo trouvée pour la chaîne: {channel_id}"
            lines = [f"Vidéos récentes de la chaîne {channel_id}:"]
            for item in items:
                video_id = item["id"]["videoId"]
                snippet = item.get("snippet", {})
                title = snippet.get("title", "?")
                published = snippet.get("publishedAt", "?")[:10]
                url = f"https://www.youtube.com/watch?v={video_id}"
                lines.append(f"  [{published}] {title}\n    {url}")
            return "\n".join(lines)
        except Exception as e:
            return f"Erreur YouTube: {str(e)}"

    def get_transcript(self, video_id_or_url: str) -> str:
        if not YOUTUBE_API_KEY and not video_id_or_url:
            return "Erreur YouTube: YOUTUBE_API_KEY manquant."
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            video_id = _extract_video_id(video_id_or_url)
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            try:
                transcript = transcript_list.find_manually_created_transcript(["fr", "en"])
            except Exception:
                try:
                    transcript = transcript_list.find_generated_transcript(["fr", "en"])
                except Exception:
                    transcript = next(iter(transcript_list))
            data = transcript.fetch()
            full_text = " ".join(entry.get("text", "") for entry in data)
            if len(full_text) > 4000:
                full_text = full_text[:4000] + "... [transcription tronquée]"
            return f"Transcription ({transcript.language}) — vidéo {video_id}:\n\n{full_text}"
        except Exception as e:
            return f"Erreur YouTube: {str(e)}"
