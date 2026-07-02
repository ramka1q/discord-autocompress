@echo off
chcp 65001 >nul
cd /d "%~dp0.."
title Update now
echo Checking for updates on GitHub...
python update.py
echo.
pause
