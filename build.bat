@echo off
setlocal enabledelayedexpansion

REM Build script for a single-file Windows executable.
REM Run this file from the project root.

set "APP_NAME=KineticDownloader"
set "MAIN_FILE=main.py"
set "ICON_FILE=assets\icon.ico"

echo [1/4] Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :error

python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/4] Cleaning previous build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"
if exist "YouTubePlaylistDownloader.spec" del /q "YouTubePlaylistDownloader.spec"

echo [3/4] Running PyInstaller...
pyinstaller --noconfirm --clean --onefile --noconsole ^
  --name "%APP_NAME%" ^
  --icon "%ICON_FILE%" ^
  --add-data "assets;assets" ^
  --collect-all customtkinter ^
  --collect-all yt_dlp ^
  --collect-all imageio_ffmpeg ^
  --hidden-import PIL._tkinter_finder ^
  --hidden-import win10toast ^
  "%MAIN_FILE%"
if errorlevel 1 goto :error

echo [4/4] Build complete.
echo Executable: dist\%APP_NAME%.exe
goto :eof

:error
echo.
echo Build failed. See output above.
exit /b 1
