# Project Lucca: WSL2 Memory Clamping Configuration Script
# Canonical: docs/07_contradiction_register.md Section C1-C3 (Register C2/C3)

$wslConfigPath = Join-Path $env:USERPROFILE ".wslconfig"

$lines = @(
    "[wsl2]",
    "memory=4608MB",
    "processors=4",
    "swap=0",
    "networkingMode=nat",
    "localhostForwarding=true",
    "nestedVirtualization=false",
    "",
    "[experimental]",
    "# pageReporting=true (kernel default in Linux 5.15+; unknown as config key in WSL 2.x)",
    "autoMemoryReclaim=gradual",
    "sparseVhd=true"
)
$targetConfig = $lines -join "`r`n"

Write-Host "=================================================" -ForegroundColor Cyan
Write-Host "  Project Lucca - WSL2 Memory Configuration" -ForegroundColor Cyan
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
Write-Host "[SUCCESS] .wslconfig successfully updated with canonical settings!" -ForegroundColor Green
Write-Host ""
Write-Host "Configuration written:" -ForegroundColor Gray
Get-Content $wslConfigPath | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

Write-Host ""
Write-Host "To apply these changes, restart WSL in PowerShell: wsl --shutdown" -ForegroundColor Yellow
