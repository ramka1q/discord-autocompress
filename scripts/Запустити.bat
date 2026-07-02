@echo off
chcp 65001 >nul
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
    echo [!] Python not found.
    echo [!] Install Python 3.8+ from https://python.org
    echo [!] During install, check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

python discord_toolbox.py
if errorlevel 1 (
    echo.
    echo [!] App exited with an error. See message above.
    pause
)
