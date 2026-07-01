@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal
title Build DiscordAutoCompress.exe

rem ---------- find real Python ----------
set "PYCMD="
py -3 --version >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"
if defined PYCMD goto :havepy
python --version >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
if defined PYCMD goto :havepy
echo [!] Python not found. Install it from python.org, then run this again.
goto :end

:havepy
echo [*] Python: %PYCMD%

rem ---------- ensure PyInstaller ----------
%PYCMD% -m PyInstaller --version >nul 2>nul
if not errorlevel 1 goto :build
echo [*] Installing PyInstaller...
%PYCMD% -m pip install --disable-pip-version-check pyinstaller
if errorlevel 1 goto :pipfail

:build
echo [*] Building DiscordAutoCompress.exe (this takes a minute)...
%PYCMD% -m PyInstaller --onefile --noconsole --name DiscordAutoCompress --distpath dist --workpath build_pyi --noconfirm launcher.py
if errorlevel 1 goto :buildfail

echo.
echo ============================================================
echo   [OK] Done!   dist\DiscordAutoCompress.exe
echo   Send THIS ONE .exe to your friend - no Python needed for them.
echo   The .exe pulls the latest program code from your GitHub on start,
echo   so your future changes still reach the friend automatically.
echo   Note: the friend still needs ffmpeg with ffplay:
echo         winget install Gyan.FFmpeg
echo ============================================================
goto :end

:pipfail
echo [!] Could not install PyInstaller. Check the internet and try again.
goto :end
:buildfail
echo [!] Build failed. See the messages above.

:end
echo.
pause
