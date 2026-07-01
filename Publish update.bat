@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Publish update to GitHub

gh auth status >nul 2>nul
if errorlevel 1 goto :nologin
if not exist ".git" goto :norepo

echo [*] Uploading changes to GitHub...
git add -A
git commit -m "update %date% %time%" >nul 2>nul
git push
echo.
echo [OK] Done. Your friend gets it on the next launch of the program.
echo     Or they can run:  "Update now.bat"
goto :end

:nologin
echo [!] Sign in first: run  "Step 1 - GitHub login.bat"
goto :end
:norepo
echo [!] Repository not created yet. Run  "Step 2 - Create repo.bat"

:end
echo.
pause
