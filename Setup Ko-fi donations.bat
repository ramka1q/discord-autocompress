@echo off
cd /d "%~dp0"
echo ==================================================
echo   Set up Ko-fi donations  (free, 0%% platform fee)
echo ==================================================
echo.
echo Step 1. A browser will open ko-fi.com in a moment.
echo   1) Sign up with Google or email - it is free.
echo   2) Pick your page name. Your page becomes:
echo          ko-fi.com/YOURNAME
echo   3) In Ko-fi: Settings - Payments, connect PayPal
echo      or a card so you can actually receive money.
echo.
pause
start "" "https://ko-fi.com/"
echo.
echo Step 2. When your Ko-fi page is ready, type your
echo Ko-fi name - just the part after ko-fi.com/
echo (you can also paste the full link).
echo.
set /p KOFI=Your Ko-fi name or link:
echo.

set "PYCMD="
py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD goto nopy

%PYCMD% set_links.py "%KOFI%" kofi
if errorlevel 1 goto failed
echo.
echo Saved. The Support button in the app now opens your Ko-fi page.
echo.
set /p PUB=Publish to GitHub now so everyone gets it? [y/N]:
if /i not "%PUB%"=="y" goto done
git add monetize.py ".github\FUNDING.yml"
git commit -m "Set Ko-fi donate link"
git push origin main
echo.
echo Published. Done!
goto done

:nopy
echo Python not found. Install it from https://python.org and retry.
goto end
:failed
echo Failed to write the link.
goto end
:done
echo.
echo All done. Thank you!
:end
echo.
pause
