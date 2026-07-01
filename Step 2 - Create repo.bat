@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal
set REPO=discord-autocompress
title Step 2 - create repo and build friend archive

gh auth status >nul 2>nul
if errorlevel 1 goto :nologin

for /f "delims=" %%u in ('gh api user -q .login 2^>nul') do set GHUSER=%%u
if "%GHUSER%"=="" goto :nouser
echo [*] Account: %GHUSER%    Repository: %REPO%

echo [*] Writing repo address into update.py...
powershell -NoProfile -Command "$p='update.py'; $c=Get-Content $p -Raw -Encoding UTF8; $c=$c -replace 'https://raw.githubusercontent.com/USERNAME/REPO/main', 'https://raw.githubusercontent.com/%GHUSER%/%REPO%/main'; [IO.File]::WriteAllText($p,$c,(New-Object Text.UTF8Encoding($false)))"

if not exist ".git" git init -b main >nul 2>nul
git config user.name "%GHUSER%"
git config user.email "%GHUSER%@users.noreply.github.com"
git add -A
git commit -m "Discord Auto-Compress" >nul 2>nul

gh repo view %GHUSER%/%REPO% >nul 2>nul
if errorlevel 1 goto :createrepo
echo [*] Repository already exists - pushing update...
git remote get-url origin >nul 2>nul || git remote add origin https://github.com/%GHUSER%/%REPO%.git
git push -u origin main
goto :afterpush

:createrepo
echo [*] Creating repository on GitHub and uploading files...
gh repo create %REPO% --public --source=. --remote=origin --push

:afterpush
if errorlevel 1 goto :pushfail
echo [*] Building the archive for your friend...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'Install.bat','update.py','Update now.bat' -DestinationPath 'discord-autocompress-setup.zip' -Force"
echo.
echo ============================================================
echo   [OK] DONE!
echo   Repository:  https://github.com/%GHUSER%/%REPO%
echo   Send your friend this file:  discord-autocompress-setup.zip
echo   It is in this folder.
echo.
echo   When you change something later - run:  "Publish update.bat"
echo ============================================================
goto :end

:nologin
echo [!] Sign in first: run  "Step 1 - GitHub login.bat"
goto :end
:nouser
echo [!] Could not read your GitHub username. Check the login again.
goto :end
:pushfail
echo [!] Upload to GitHub failed. Scroll up for the reason.

:end
echo.
pause
