from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


class AnalyzerError(Exception):
    """Base analyzer error."""


class InvalidUrlError(AnalyzerError):
    """Raised when the provided URL is not a valid YouTube playlist URL."""


class PlaylistUnavailableError(AnalyzerError):
    """Raised when playlist data cannot be fetched."""


@dataclass(slots=True)
class PlaylistVideo:
    video_id: str
    title: str
    duration_seconds: int
    webpage_url: str
    thumbnail_url: str


@dataclass(slots=True)
class PlaylistInfo:
    title: str
    video_count: int
    total_duration_seconds: int
    videos: list[PlaylistVideo]


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "00:00"

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class PlaylistAnalyzer:
    YOUTUBE_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be")

    @staticmethod
    def _is_youtube_host(host: str) -> bool:
        host = host.lower().strip()
        allowed_hosts = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
        if host in allowed_hosts:
            return True
        return host.endswith(".youtube.com")

    def is_valid_playlist_url(self, url: str) -> bool:
        if not url:
            return False

        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False

        host = parsed.netloc.lower().split(":")[0]
        if not self._is_youtube_host(host):
            return False

        query = parse_qs(parsed.query)
        return bool(query.get("list"))

    def analyze(self, url: str) -> PlaylistInfo:
        clean_url = url.strip()
        if not self.is_valid_playlist_url(clean_url):
            raise InvalidUrlError("Please enter a valid YouTube playlist URL.")

        options: dict[str, Any] = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": False,
            "ignoreerrors": True,
            "noplaylist": False,
            "no_warnings": True,
            "socket_timeout": 20,
        }

        try:
            with YoutubeDL(cast(Any, options)) as ydl:
                data = ydl.extract_info(clean_url, download=False)
        except DownloadError as exc:
            message = str(exc).strip()
            lower = message.lower()
            if "unsupported url" in lower:
                raise InvalidUrlError("Unsupported URL. Please paste a playlist URL.") from exc
            if "private" in lower:
                raise PlaylistUnavailableError(
                    "The playlist is private and cannot be analyzed without credentials."
                ) from exc
            if "not found" in lower or "404" in lower:
                raise PlaylistUnavailableError("Playlist not found. Check the URL and try again.") from exc
            if "429" in lower or "too many requests" in lower:
                raise PlaylistUnavailableError(
                    "YouTube rate-limited this request (429). Wait a minute and retry."
                ) from exc
            if "network" in lower or "connection" in lower or "timed out" in lower:
                raise PlaylistUnavailableError(
                    "Network error while analyzing playlist. Check your connection and retry."
                ) from exc
            raise PlaylistUnavailableError(f"Could not analyze playlist: {message}") from exc
        except Exception as exc:  # noqa: BLE001
            raise PlaylistUnavailableError(f"Could not analyze playlist: {exc}") from exc

        if not data:
            raise PlaylistUnavailableError("Playlist returned no metadata.")

        entries = data.get("entries") or []
        if not entries:
            raise PlaylistUnavailableError(
                "No downloadable entries found. The playlist may be private, empty, or unavailable."
            )

        videos: list[PlaylistVideo] = []
        total_duration = 0

        for entry in entries:
            if not entry:
                continue

            video_id = (entry.get("id") or "").strip()
            title = (entry.get("title") or "Untitled video").strip()
            duration_seconds = int(entry.get("duration") or 0)
            total_duration += max(0, duration_seconds)

            webpage_url = (
                (entry.get("webpage_url") or "").strip()
                or (f"https://www.youtube.com/watch?v={video_id}" if video_id else "")
            )

            thumbnail = (entry.get("thumbnail") or "").strip()
            if not thumbnail and entry.get("thumbnails"):
                thumbnails = entry.get("thumbnails") or []
                if thumbnails:
                    thumbnail = (thumbnails[-1].get("url") or "").strip()

            if not video_id or not webpage_url:
                continue

            videos.append(
                PlaylistVideo(
                    video_id=video_id,
                    title=title,
                    duration_seconds=duration_seconds,
                    webpage_url=webpage_url,
                    thumbnail_url=thumbnail,
                )
            )

        if not videos:
            raise PlaylistUnavailableError("No valid videos were available in this playlist.")

        playlist_title = (data.get("title") or "YouTube Playlist").strip()
        return PlaylistInfo(
            title=playlist_title,
            video_count=len(videos),
            total_duration_seconds=total_duration,
            videos=videos,
        )
