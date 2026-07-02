@echo off
cd /d "%~dp0"
echo ================================================
echo   Discord Auto-Compress - set support links
echo ================================================
echo.
echo These links power the Support button in the app and
echo the Sponsor button on GitHub. Leave blank to keep empty.
echo.
echo Donate link examples:
echo   https://ko-fi.com/yourname
echo   https://buymeacoffee.com/yourname
echo   https://paypal.me/yourname
echo.
set /p SUP=Donate link:
echo.
echo Pro .exe sale link examples:
echo   https://yourname.gumroad.com/l/discord-autocompress
echo   https://yourname.lemonsqueezy.com/...
echo.
set /p PRO=Pro sale link (optional):
echo.

set "PYCMD="
py -3 --version >nul 2>&1 && set "PYCMD=py -3"
if not defined PYCMD python --version >nul 2>&1 && set "PYCMD=python"
if not defined PYCMD goto nopy

%PYCMD% set_links.py "%SUP%" "%PRO%"
if errorlevel 1 goto failed
echo.
echo Links saved to monetize.py and .github\FUNDING.yml
echo.

set /p PUB=Publish to GitHub now so all users get it? [y/N]:
if /i not "%PUB%"=="y" goto done
git add monetize.py ".github\FUNDING.yml"
git commit -m "Update support/donate links"
git push origin main
echo.
echo Published. Friends get the Support button on next launch.
goto done

:nopy
echo Python not found. Install it from https://python.org and retry.
goto end
:failed
echo Failed to write links.
goto end
:done
echo.
echo All done.
:end
echo.
pause
