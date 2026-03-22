# Kinetic Downloader

Professional multi-platform media downloader with a Kinetic Console UI.

## Quick Installation (Top Priority)

Use this if you just want to install and use the app like any normal Windows program.

1. Download `KineticDownloader-Setup.exe`.
2. Run the installer.
3. Click Next -> Install -> Finish.
4. Open **Kinetic Downloader** from Start Menu (or Desktop shortcut if selected).

Latest verified artifacts (this workspace build):

- `dist/KineticDownloader.exe`
- `dist/KineticDownloader-Setup.exe`

End-user requirements:

- Windows 10 or Windows 11

You do **not** need:

- Python
- pip
- Inno Setup

## Portable Option (No Installer)

If you prefer a direct app file, use:

- `KineticDownloader.exe`

This is a single-file executable that can run directly on Windows.

## Features

- Kinetic Console desktop interface with:
  - fixed top bar, left navigation rail, and bottom status bar
  - multi-page workflow: Dashboard, Playlists, History, Settings
- Multi-platform URL analysis using `yt-dlp`:
  - supported platforms: YouTube, Instagram, TikTok, X (Twitter)
  - source detection: direct link, profile, collection/list (based on URL + selected mode)
  - media title, item count, aggregated duration
  - per-item metadata and thumbnails
- Analysis modes:
  - `auto` (recommended): detect behavior from URL type
  - `direct`: direct post/video links only
  - `profile_collection`: profile/list extraction when supported
  - configurable extraction limit for profile/collection mode (default: 50)
  - optional "videos only" filtering
- Playlist/media operations:
  - scrollable video table
  - select all / deselect all
  - per-video pause/resume
  - per-video copy-link action
- Download pipeline:
  - quality presets: 1080p / 720p / 480p / 360p / Audio Only
  - formats: MP4 / MKV / MP3 / M4A
  - parallel downloads (1-3)
  - retry with exponential backoff
  - adaptive global cooldown on rate-limit events (HTTP 429)
  - per-video progress + overall progress
  - live transfer speed/status updates
- Robust runtime controls:
  - pause/resume/cancel queue controls
  - non-blocking UI (threaded background operations)
- Storage and notifications:
  - output folder picker
  - optional source subfolder creation
  - completion sound + Windows toast support
- Authentication options for restricted/private content:
  - cookies mode: `auto`, `browser`, `file`, `off`
  - browser source selection: Chrome / Edge / Firefox / Brave
  - file-based `cookies.txt` picker from Settings
- History and telemetry:
  - SQLite-backed download history
  - source metadata tracking (`source_platform`, `source_kind`)
  - structured error codes
  - in-app history stats and actions
- Preference persistence:
  - remembers output folder, format/quality, concurrency, toggles, theme mode
  - remembers analysis mode, extraction limit, video-only mode, and cookie settings

## Supported URL Types

- YouTube:
  - direct video links
  - playlist links
- Instagram:
  - direct reel/post links
  - profile links (when extractable)
- TikTok:
  - direct video links
  - profile links
- X (Twitter):
  - direct status links
  - profile/list links (availability depends on upstream extractor and access rules)

## Cookies and Access Notes

- Some profile/list/private URLs require authentication cookies.
- Recommended setup for stability:
  1. Keep Cookies mode on `auto` for normal usage.
  2. If protected URLs fail, switch to `file` and use a valid `cookies.txt` export.
  3. If using `browser` mode, fully close the browser first so cookie DB locks are released.
- If the platform or extractor blocks access, the app shows a categorized error code/message in UI and History.

## Screenshots

Add screenshots here (placeholders):

- `docs/screenshots/dashboard.png`
- `docs/screenshots/playlists.png`
- `docs/screenshots/history.png`
- `docs/screenshots/settings.png`

## For Developers (Build From Source)

Use this section only if you want to build the project yourself.

Build requirements:

- Windows 10 or Windows 11
- Python 3.11+
- Inno Setup 6 (only if you want to build `KineticDownloader-Setup.exe` yourself)

Note: `build.bat` checks common Inno Setup install paths, including `%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`.

### Build single `.exe` + installer

Run:

```bat
.\build.bat
```

Build outputs:

```text
dist\KineticDownloader.exe
dist\KineticDownloader-Setup.exe
```

Notes:

- `KineticDownloader.exe` is generated with PyInstaller.
- `KineticDownloader-Setup.exe` is generated only when Inno Setup is available.
- If Inno Setup is missing, `build.bat` still builds `.exe` and skips installer generation.

Manual PyInstaller command (if needed):

```bat
pyinstaller --noconfirm --clean --onefile --noconsole --name "KineticDownloader" --icon "assets\icon.ico" --add-data "assets;assets" --collect-all customtkinter --collect-all yt_dlp --collect-all imageio_ffmpeg --hidden-import PIL._tkinter_finder --hidden-import win10toast "main.py"
```

Manual installer build (if needed):

1. Install Inno Setup 6.
2. Open `installer.iss` in Inno Setup Compiler.
3. Click Build.
4. Output is created at `dist\KineticDownloader-Setup.exe`.

## Project Structure

```text
youtube-playlist-downloader/
├── main.py
├── build.bat
├── installer.iss
├── requirements.txt
├── README.md
├── assets/
│   └── icon.ico
├── core/
│   ├── __init__.py
│   ├── analyzer.py
│   ├── database.py
│   ├── downloader.py
│   └── preferences.py
└── ui/
    ├── __init__.py
    ├── main_window.py
    ├── playlist_view.py
    └── settings.py
```

## Design System Credit

This UI is built using the **Kinetic Console** design system.

## Tech Stack

- Python
- CustomTkinter
- yt-dlp
- SQLite
- PyInstaller
- Pillow
