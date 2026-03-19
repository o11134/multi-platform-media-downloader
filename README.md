# Kinetic Downloader

Professional YouTube playlist downloader with a Kinetic Console UI.

## Screenshots

Add screenshots here (placeholders):

- `docs/screenshots/dashboard.png`
- `docs/screenshots/playlists.png`
- `docs/screenshots/history.png`
- `docs/screenshots/settings.png`

## Features

- Kinetic Console desktop interface with:
  - fixed top bar, left navigation rail, and bottom status bar
  - multi-page workflow: Dashboard, Playlists, History, Settings
- Playlist analysis from URL using `yt-dlp` metadata extraction:
  - playlist title, video count, aggregated duration
  - per-video metadata and thumbnails
- Playlist operations:
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
  - optional playlist subfolder creation
  - completion sound + Windows toast support
- History and telemetry:
  - SQLite-backed download history
  - structured error codes
  - in-app history stats and actions
- Preference persistence:
  - remembers output folder, format/quality, concurrency, toggles, theme mode

## Requirements

- Windows 10 or Windows 11
- Python 3.11+

## Installation & Run

1. Clone or download this project.
2. Open terminal in project root (`youtube-playlist-downloader`).
3. Create virtual environment:

```bat
python -m venv .venv
```

4. Activate virtual environment:

```bat
.venv\Scripts\activate
```

5. Install dependencies:

```bat
python -m pip install -r requirements.txt
```

6. Run app:

```bat
python main.py
```

## Build .exe

Run:

```bat
.\build.bat
```

Build output:

```text
dist\KineticDownloader.exe
```

Manual PyInstaller command (if needed):

```bat
pyinstaller --noconfirm --clean --onefile --noconsole --name "KineticDownloader" --icon "assets\icon.ico" --add-data "assets;assets" --collect-all customtkinter --collect-all yt_dlp --collect-all imageio_ffmpeg --hidden-import PIL._tkinter_finder --hidden-import win10toast "main.py"
```

## Project Structure

```text
youtube-playlist-downloader/
├── main.py
├── build.bat
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
