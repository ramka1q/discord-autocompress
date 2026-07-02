@echo off
chcp 65001 >nul
cd /d "%~dp0.."
where ffmpeg >nul 2>nul
if errorlevel 1 ( echo [!] ffmpeg not found. Install: winget install Gyan.FFmpeg & pause & exit /b 1 )
start "" pythonw discord_overlay.py
