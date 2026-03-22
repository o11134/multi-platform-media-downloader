from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
class AnalysisOptions:
    scope_mode: str = "auto"
    max_items: int = 50
    video_only: bool = True
    cookies_mode: str = "auto"
    cookies_browser: str = "chrome"
    cookies_file: str = ""


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
    source_platform: str = "unknown"
    source_kind: str = "direct"


def format_duration(seconds: int) -> str:
    if seconds <= 0:
        return "00:00"

    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class PlaylistAnalyzer:
    @staticmethod
    def _clean_host(host: str) -> str:
        return host.lower().strip().split(":")[0]

    @staticmethod
    def _detect_platform(host: str) -> str:
        if host in {"youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com"} or host.endswith(".youtube.com"):
            return "youtube"
        if host in {"instagram.com", "www.instagram.com", "m.instagram.com"} or host.endswith(".instagram.com"):
            return "instagram"
        if host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"} or host.endswith(".tiktok.com"):
            return "tiktok"
        if host in {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}:
            return "x"
        return "unknown"

    @staticmethod
    def _kind_from_url(url: str, platform: str) -> str:
        parsed = urlparse(url)
        path = (parsed.path or "").strip("/")
        segments = [part for part in path.split("/") if part]

        if platform == "youtube":
            query = parse_qs(parsed.query)
            if query.get("list"):
                return "collection"
            return "direct"

        if platform == "instagram":
            if any(part in {"reel", "p", "tv"} for part in segments):
                return "direct"
            if segments:
                return "profile"
            return "direct"

        if platform == "tiktok":
            if "video" in segments:
                return "direct"
            if segments and segments[0].startswith("@"):
                return "profile"
            return "direct"

        if platform == "x":
            if "status" in segments:
                return "direct"
            if len(segments) >= 2 and segments[0] == "i" and segments[1] == "lists":
                return "collection"
            if segments:
                return "profile"
            return "direct"

        return "direct"

    @staticmethod
    def _resolve_kind(detected_kind: str, scope_mode: str) -> str:
        normalized = scope_mode.lower().strip()
        if normalized == "direct":
            return "direct"
        if normalized in {"profile", "profile_collection", "collection"}:
            if detected_kind in {"profile", "collection"}:
                return detected_kind
            return "direct"
        return detected_kind

    @staticmethod
    def _build_cookie_options(options: AnalysisOptions) -> dict[str, Any]:
        mode = (options.cookies_mode or "auto").lower().strip()
        browser = (options.cookies_browser or "chrome").strip()
        cookie_file = (options.cookies_file or "").strip()

        ydl_cookie_options: dict[str, Any] = {}
        if mode == "off":
            return ydl_cookie_options
        if mode == "auto":
            if cookie_file and Path(cookie_file).exists():
                ydl_cookie_options["cookiefile"] = cookie_file
            return ydl_cookie_options
        if mode == "browser" and browser:
            ydl_cookie_options["cookiesfrombrowser"] = (browser,)
            return ydl_cookie_options
        if mode == "file" and cookie_file:
            ydl_cookie_options["cookiefile"] = cookie_file
        return ydl_cookie_options

    @staticmethod
    def _is_video_entry(entry: dict[str, Any]) -> bool:
        duration = int(entry.get("duration") or 0)
        if duration > 0:
            return True

        vcodec = str(entry.get("vcodec") or "").lower().strip()
        if vcodec and vcodec != "none":
            return True

        formats = entry.get("formats") or []
        if isinstance(formats, list):
            for fmt in formats:
                if not isinstance(fmt, dict):
                    continue
                fmt_vcodec = str(fmt.get("vcodec") or "").lower().strip()
                if fmt_vcodec and fmt_vcodec != "none":
                    return True
        return False

    @staticmethod
    def _entry_to_video(entry: dict[str, Any]) -> PlaylistVideo | None:
        video_id = (entry.get("id") or "").strip()
        title = (entry.get("title") or "Untitled media").strip()
        duration_seconds = int(entry.get("duration") or 0)
        webpage_url = (entry.get("webpage_url") or entry.get("url") or "").strip()

        thumbnail = (entry.get("thumbnail") or "").strip()
        if not thumbnail and entry.get("thumbnails"):
            thumbnails = entry.get("thumbnails") or []
            if thumbnails:
                thumbnail = (thumbnails[-1].get("url") or "").strip()

        if not webpage_url:
            return None
        if not video_id:
            video_id = webpage_url

        return PlaylistVideo(
            video_id=video_id,
            title=title,
            duration_seconds=duration_seconds,
            webpage_url=webpage_url,
            thumbnail_url=thumbnail,
        )

    def is_valid_playlist_url(self, url: str) -> bool:
        if not url:
            return False

        parsed = urlparse(url.strip())
        if parsed.scheme not in ("http", "https"):
            return False

        host = self._clean_host(parsed.netloc)
        if self._detect_platform(host) == "unknown":
            return False
        return True

    def analyze(self, url: str, options: AnalysisOptions | None = None) -> PlaylistInfo:
        options = options or AnalysisOptions()
        clean_url = url.strip()
        if not self.is_valid_playlist_url(clean_url):
            raise InvalidUrlError("Please enter a valid YouTube, Instagram, TikTok, or X URL.")

        parsed = urlparse(clean_url)
        host = self._clean_host(parsed.netloc)
        platform = self._detect_platform(host)
        detected_kind = self._kind_from_url(clean_url, platform)
        if (options.scope_mode or "").strip().lower() == "direct" and detected_kind in {"profile", "collection"}:
            raise InvalidUrlError("Direct Link mode is enabled, but this URL is a profile/collection URL.")
        kind = self._resolve_kind(detected_kind, options.scope_mode)
        max_items = max(1, min(500, int(options.max_items or 50)))

        ydl_options: dict[str, Any] = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": False,
            "ignoreerrors": True,
            "noplaylist": kind == "direct",
            "no_warnings": True,
            "socket_timeout": 20,
            "playlistend": max_items,
        }
        ydl_options.update(self._build_cookie_options(options))

        try:
            with YoutubeDL(cast(Any, ydl_options)) as ydl:
                data = ydl.extract_info(clean_url, download=False)
        except DownloadError as exc:
            message = str(exc).strip()
            lower = message.lower()
            if "could not copy" in lower and "cookie database" in lower:
                raise PlaylistUnavailableError(
                    "Browser cookies are unavailable. Close the browser and retry, or switch Cookies mode to File/Off."
                ) from exc
            if "unsupported url" in lower:
                raise InvalidUrlError("Unsupported URL. Please paste a supported media URL.") from exc
            if "private" in lower or "protected" in lower:
                raise PlaylistUnavailableError(
                    "This content is private and may require account cookies in settings."
                ) from exc
            if "not found" in lower or "404" in lower:
                raise PlaylistUnavailableError("Content not found. Check the URL and try again.") from exc
            if "429" in lower or "too many requests" in lower:
                raise PlaylistUnavailableError(
                    "Rate-limited by platform (429). Wait a minute and retry."
                ) from exc
            if "login required" in lower or "sign in" in lower or "authentication" in lower:
                raise PlaylistUnavailableError(
                    "Authentication required. Enable browser/file cookies in settings and retry."
                ) from exc
            if "network" in lower or "connection" in lower or "timed out" in lower:
                raise PlaylistUnavailableError(
                    "Network error while analyzing content. Check your connection and retry."
                ) from exc
            raise PlaylistUnavailableError(f"Could not analyze content: {message}") from exc
        except Exception as exc:  # noqa: BLE001
            raise PlaylistUnavailableError(f"Could not analyze content: {exc}") from exc

        if not data:
            raise PlaylistUnavailableError("No metadata returned for this URL.")

        entries_raw = data.get("entries") if isinstance(data, dict) else None
        if entries_raw:
            entries = [entry for entry in entries_raw if entry]
        elif isinstance(data, dict):
            entries = [data]
        else:
            entries = []

        if not entries:
            raise PlaylistUnavailableError("No downloadable entries found. The URL may be private, empty, or unavailable.")

        videos: list[PlaylistVideo] = []
        total_duration = 0

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_dict = cast(dict[str, Any], entry)

            if options.video_only and not self._is_video_entry(entry_dict):
                continue

            video = self._entry_to_video(entry_dict)
            if not video:
                continue

            total_duration += max(0, video.duration_seconds)
            videos.append(video)

            if kind in {"profile", "collection"} and len(videos) >= max_items:
                break

        if not videos:
            raise PlaylistUnavailableError("No valid videos were found for this URL.")

        default_titles = {
            "youtube": "YouTube Media",
            "instagram": "Instagram Media",
            "tiktok": "TikTok Media",
            "x": "X Media",
        }
        playlist_title = (data.get("title") or default_titles.get(platform, "Media Collection")).strip()
        return PlaylistInfo(
            title=playlist_title,
            video_count=len(videos),
            total_duration_seconds=total_duration,
            videos=videos,
            source_platform=platform,
            source_kind=kind,
        )
