# Вмикає автозапуск вартового: створює ярлик у теці Startup.
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Знаходимо СПРАВЖНІЙ python через лаунчер py (не заглушку Microsoft Store), звідти pythonw.exe
$pyexe = $null
try { $pyexe = (& py -3 -c "import sys;print(sys.executable)" 2>$null) } catch {}
if (-not $pyexe) { $pyexe = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $pyexe) { Write-Host '[!] Python not found'; exit 1 }
$pyw = Join-Path (Split-Path $pyexe) 'pythonw.exe'
if (-not (Test-Path $pyw)) { $pyw = $pyexe }  # запасний варіант
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
