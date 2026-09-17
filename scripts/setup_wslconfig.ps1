# Project Lucca: WSL2 Memory Clamping Configuration Script
# Sets WSL2 to strictly 4.5GB RAM to prevent Windows 11 host paging

$wslConfigPath = [System.IO.Path]::Combine($env:USERPROFILE, ".wslconfig")

$targetConfig = @"
[wsl2]
memory=4608MB
processors=4
swap=2048MB
pageReporting=false
localhostForwarding=true
nestedVirtualization=false
"@

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  Project Lucca — WSL2 Memory Configuration" -ForegroundColor Cyan
Write-Host "=================================================" -ForegroundColor Cyan

if (Test-Path $wslConfigPath) {
    Write-Host "[INFO] Existing .wslconfig found at: $wslConfigPath" -ForegroundColor Yellow
    $backupPath = "$wslConfigPath.bak_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Copy-Item $wslConfigPath $backupPath
    Write-Host "[INFO] Backup created at: $backupPath" -ForegroundColor Green
} else {
    Write-Host "[INFO] No existing .wslconfig found. Creating new configuration..." -ForegroundColor Yellow
}

Set-Content -Path $wslConfigPath -Value $targetConfig -Encoding UTF8
Write-Host "[SUCCESS] .wslconfig successfully updated with 4.5GB RAM clamp!" -ForegroundColor Green
Write-Host ""
Write-Host "Configuration written:" -ForegroundColor Gray
Get-Content $wslConfigPath | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "To apply these changes, restart WSL in PowerShell: 'wsl --shutdown'" -ForegroundColor Yellow
