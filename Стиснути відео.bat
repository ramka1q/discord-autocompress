@echo off
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python not found. Install from https://python.org ^(check "Add to PATH"^).
    pause & exit /b 1
)
where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [!] ffmpeg not found. Install:  winget install Gyan.FFmpeg
    pause & exit /b 1
)

python discord_compressor.py
if errorlevel 1 (
    echo.
    echo [!] App exited with an error. See message above.
    pause
)
