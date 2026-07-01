@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*discord_overlay.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; 'Stopped PID ' + $_.ProcessId }"
echo.
echo Done.
pause
