# Вимикає автозапуск: видаляє ярлик з теки Startup.
$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Discord Auto-Compress.lnk'
if (Test-Path $lnk) {
    Remove-Item $lnk -Force
    Write-Host 'Autostart DISABLED (shortcut removed).'
} else {
    Write-Host 'Autostart was not enabled.'
}
