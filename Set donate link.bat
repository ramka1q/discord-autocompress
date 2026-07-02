@echo off
cd /d "%~dp0"
echo ================================================
echo   Discord Auto-Compress - set your donate link
echo ================================================
echo.
echo Paste your free donation link. Examples:
echo   https://ko-fi.com/yourname
echo   https://buymeacoffee.com/yourname
echo   https://send.monobank.ua/jar/xxxxxxxx
echo.
echo Leave blank and press Enter to remove the link.
echo.
set /p URL=Donate link:
echo.

set "PYCMD="
py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD goto nopy

%PYCMD% set_links.py "%URL%"
if errorlevel 1 goto failed
echo.
echo Saved to monetize.py and .github\FUNDING.yml
echo.

set /p PUB=Publish to GitHub now so everyone gets it? [y/N]:
if /i not "%PUB%"=="y" goto done
git add monetize.py ".github\FUNDING.yml"
git commit -m "Update donate link"
git push origin main
echo.
echo Published. The Support button now opens your link.
goto done

:nopy
echo Python not found. Install it from https://python.org and retry.
goto end
:failed
echo Failed to write the link.
goto end
:done
echo.
echo All done.
:end
echo.
pause
