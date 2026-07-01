@echo off
chcp 65001 >nul
cd /d "%~dp0"
python discord_overlay.py --settings
