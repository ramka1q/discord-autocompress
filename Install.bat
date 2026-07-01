@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Discord Auto-Compress - install

echo ==================================================
echo    Discord Auto-Compress - automatic install
echo ==================================================
echo.

rem ---------- Python ----------
where python >nul 2>nul
if errorlevel 1 goto :nopython

rem ---------- ffmpeg ----------
where ffmpeg >nul 2>nul
if not errorlevel 1 goto :getprog
echo [*] ffmpeg not found. Installing via winget...
winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
echo [i] If you see an ffmpeg error later, just run this file again.

:getprog
echo.
echo [*] Downloading the program from GitHub...
python update.py --install
if errorlevel 1 goto :dlfail

echo [*] Enabling background autostart...
powershell -NoProfile -ExecutionPolicy Bypass -File "autostart_enable.ps1"

echo [*] Starting the program...
start "" pythonw discord_overlay.py

echo.
echo ==================================================
echo   [OK] Done! The program runs in the background.
echo   In Discord, paste a video bigger than the limit (Ctrl+V) -
echo   it will offer to compress or split it.
echo   It updates itself on every launch.
echo ==================================================
goto :end

:nopython
echo [*] Python not found. Installing via winget...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
echo.
echo [!] Python installed. Windows does not see it in this window yet.
echo     CLOSE this window and run this file again.
goto :end

:dlfail
echo [!] Download from GitHub failed.
echo     Check the internet and the REPO_RAW address inside update.py

:end
echo.
pause
