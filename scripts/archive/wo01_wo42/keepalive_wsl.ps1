# Project Lucca -- WSL2 Keepalive Daemon
# Prevents Windows from shutting down WSL2 VM when idle.

$existing = Get-WmiObject Win32_Process -Filter "Name = 'wsl.exe'" -ErrorAction SilentlyContinue | 
    Where-Object { $_.CommandLine -match "sleep infinity" }

if (-not $existing) {
    Start-Process -FilePath "wsl.exe" -ArgumentList @("-d", "Ubuntu", "--exec", "sleep", "infinity") -WindowStyle Hidden
    Write-Host "[WSL Keepalive] Started persistent WSL2 keepalive daemon."
} else {
    Write-Host "[WSL Keepalive] Daemon is already running."
}
