@echo off
chcp 65001 >nul
cd /d "%~dp0.."
setlocal
title Discord Auto-Compress - install

echo ==================================================
echo    Discord Auto-Compress - automatic install
echo ==================================================
echo.

rem ---------- Find REAL Python (skip the Microsoft Store stub) ----------
set "PYCMD="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"
if defined PYCMD goto :havepy
python --version >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
if defined PYCMD goto :havepy
goto :nopython

:havepy
echo [*] Python: %PYCMD%
set "PYW=pythonw"
for /f "delims=" %%i in ('%PYCMD% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))" 2^>nul') do set "PYW=%%i"

rem ---------- ffmpeg ----------
where ffmpeg >nul 2>nul
if not errorlevel 1 goto :getprog
echo [*] ffmpeg not found. Installing via winget...
winget install -e --id Gyan.FFmpeg --silent --accept-package-agreements --accept-source-agreements
echo [i] If you see an ffmpeg error later, just run this file again.

:getprog
echo.
echo [*] Downloading the program from GitHub...
%PYCMD% update.py --install
if errorlevel 1 goto :dlfail

echo [*] Enabling background autostart...
powershell -NoProfile -ExecutionPolicy Bypass -File "autostart_enable.ps1"

echo [*] Starting the program...
start "" "%PYW%" discord_overlay.py

echo.
echo ==================================================
echo   [OK] Done! The program runs in the background.
echo   In Discord, paste a video bigger than the limit (Ctrl+V) -
echo   it will offer to compress or split it.
echo   It updates itself on every launch.
echo ==================================================
goto :end

:nopython
echo [*] Real Python not found (only the Microsoft Store stub, or nothing).
echo     Installing Python via winget...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
echo.
echo [!] Python installed. Windows does not see it in THIS window yet.
echo     CLOSE this window and run Install.bat again.
goto :end

:dlfail
echo [!] Download from GitHub failed.
echo     The repo is public and reachable, so this is usually:
echo       - no internet / a VPN or firewall blocking github;
echo       - or Python could not run update.py.
echo     Check the connection and run Install.bat again.

:end
echo.
pause
