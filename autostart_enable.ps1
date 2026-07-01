# Вмикає автозапуск вартового: створює ярлик у теці Startup.
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pyw = Join-Path (Split-Path (Get-Command python).Source) 'pythonw.exe'
if (-not (Test-Path $pyw)) { Write-Host '[!] pythonw.exe not found'; exit 1 }
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Discord Auto-Compress.lnk'
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = '"' + (Join-Path $dir 'discord_overlay.py') + '"'
$s.WorkingDirectory = $dir
$s.WindowStyle = 7
$s.Description = 'Discord Auto-Compress watcher (autostart)'
$s.Save()
Write-Host "Autostart ENABLED ->" $lnk
