@echo off
setlocal enabledelayedexpansion

REM Build script for a single-file Windows executable.
REM Run this file from the project root.

set "APP_NAME=KineticDownloader"
set "MAIN_FILE=main.py"
set "ICON_FILE=assets\icon.ico"
set "ISS_FILE=installer.iss"
set "ISCC_EXE="

echo [1/5] Installing dependencies...
python -m pip install --upgrade pip
if errorlevel 1 goto :error

python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [2/5] Cleaning previous build outputs...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /q "%APP_NAME%.spec"
if exist "YouTubePlaylistDownloader.spec" del /q "YouTubePlaylistDownloader.spec"

echo [3/5] Running PyInstaller...
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

echo [4/5] Looking for Inno Setup compiler...
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if not defined ISCC_EXE (
  echo Inno Setup not found. Skipping installer build.
  echo Install Inno Setup 6 to generate setup file: https://jrsoftware.org/isdl.php
  goto :done
)

if not exist "%ISS_FILE%" (
  echo %ISS_FILE% not found. Skipping installer build.
  goto :done
)

echo [5/5] Building installer with Inno Setup...
"%ISCC_EXE%" "%ISS_FILE%"
if errorlevel 1 goto :error

:done
echo Build complete.
echo Executable: dist\%APP_NAME%.exe
if exist "dist\KineticDownloader-Setup.exe" echo Installer: dist\KineticDownloader-Setup.exe
goto :eof

:error
echo.
echo Build failed. See output above.
exit /b 1
