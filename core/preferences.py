from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(slots=True)
class AppPreferences:
    last_output_dir: str = ""
    notifications_enabled: bool = True
    sound_enabled: bool = True
    auto_subfolder: bool = True
    parallel_downloads: int = 2
    quality: str = "1080p"
    file_format: str = "MP4"
    appearance_mode: str = "dark"
    scope_mode: str = "auto"
    max_items: int = 50
    video_only: bool = True
    cookies_mode: str = "auto"
    cookies_browser: str = "chrome"
    cookies_file: str = ""


class PreferencesStore:
    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> AppPreferences:
        if not self._file_path.exists():
            return AppPreferences()

        try:
            raw = json.loads(self._file_path.read_text(encoding="utf-8"))
            scope_mode = str(raw.get("scope_mode", "auto")).lower()
            if scope_mode in {"profile", "collection"}:
                scope_mode = "profile_collection"
            if scope_mode not in {"auto", "direct", "profile_collection"}:
                scope_mode = "auto"

            cookies_mode = str(raw.get("cookies_mode", "auto")).lower()
            if cookies_mode not in {"auto", "browser", "file", "off"}:
                cookies_mode = "auto"

            cookies_browser = str(raw.get("cookies_browser", "chrome")).lower()
            if cookies_browser not in {"chrome", "edge", "firefox", "brave"}:
                cookies_browser = "chrome"

            return AppPreferences(
                last_output_dir=str(raw.get("last_output_dir", "")),
                notifications_enabled=bool(raw.get("notifications_enabled", True)),
                sound_enabled=bool(raw.get("sound_enabled", True)),
                auto_subfolder=bool(raw.get("auto_subfolder", True)),
                parallel_downloads=max(1, min(3, int(raw.get("parallel_downloads", 2)))),
                quality=str(raw.get("quality", "1080p")),
                file_format=str(raw.get("file_format", "MP4")),
                appearance_mode=str(raw.get("appearance_mode", "dark")).lower(),
                scope_mode=scope_mode,
                max_items=max(1, min(500, int(raw.get("max_items", 50)))),
                video_only=bool(raw.get("video_only", True)),
                cookies_mode=cookies_mode,
                cookies_browser=cookies_browser,
                cookies_file=str(raw.get("cookies_file", "")),
            )
        except Exception:
            return AppPreferences()

    def save(self, preferences: AppPreferences) -> None:
        try:
            payload = json.dumps(asdict(preferences), ensure_ascii=False, indent=2)
            self._file_path.write_text(payload, encoding="utf-8")
        except Exception:
            # Preference write failures should not interrupt the main app.
            pass
