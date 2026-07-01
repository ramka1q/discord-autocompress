@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Step 1 - GitHub login

where gh >nul 2>nul
if errorlevel 1 goto :nogh

gh auth status >nul 2>nul
if not errorlevel 1 goto :already

echo ============================================================
echo   A browser will open to sign in to GitHub.
echo   1. Note the CODE shown below.
echo   2. Press Enter - the GitHub page opens.
echo   3. Paste the code and click Authorize.
echo   No account yet? You can sign up there for free.
echo ============================================================
echo.
gh auth login --hostname github.com --git-protocol https --web
echo.
gh auth status >nul 2>nul
if errorlevel 1 goto :failed
echo [OK] Done! Now run:  "Step 2 - Create repo.bat"
goto :end

:nogh
echo [*] Installing GitHub CLI...
winget install -e --id GitHub.cli --silent --accept-package-agreements --accept-source-agreements
echo.
echo [!] GitHub CLI installed. CLOSE this window and run this file again.
goto :end

:already
echo [OK] You are already signed in. Run:  "Step 2 - Create repo.bat"
goto :end

:failed
echo [!] Login did not finish. Try running this file again.

:end
echo.
pause
