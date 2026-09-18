# S1 evidence runner — Project Lucca audit (subtask S1)
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File docs\audit\evidence\S1_run.ps1 -Name S1_01_gpu_baseline.txt -Cmd "nvidia-smi ..." [-TimeoutSec 600]
# Runs <Cmd> via cmd.exe /c, captures stdout+stderr, exit code, UTC timestamps and duration into docs\audit\evidence\<Name>,
# and appends one CSV row to docs\audit\evidence\S1_command_log.csv. It never modifies anything outside docs\audit\evidence.
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Cmd,
    [int]$TimeoutSec = 0,
    [switch]$Append
)
$ErrorActionPreference = 'Continue'
$evDir = Join-Path $PSScriptRoot '.'
$outPath = Join-Path $evDir $Name
$logPath = Join-Path $evDir 'S1_command_log.csv'
$utc = { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }
$start = & $utc
$sw = [System.Diagnostics.Stopwatch]::StartNew()

$header = @()
$header += "=== ARTEFACT: $Name"
$header += "=== PRODUCER: S1"
$header += "=== UTC_START: $start"
$header += "=== CWD: $(Get-Location)"
$header += "=== COMMAND: $Cmd"
$header += "=== OUTPUT (stdout+stderr merged) ==="
if ($Append) { Add-Content -Path $outPath -Value ($header -join "`r`n") -Encoding UTF8 }
else { Set-Content -Path $outPath -Value ($header -join "`r`n") -Encoding UTF8 }

$exit = $null
$timedOut = $false
if ($TimeoutSec -gt 0) {
    $tmpOut = [System.IO.Path]::GetTempFileName()
    $p = Start-Process -FilePath 'cmd.exe' -ArgumentList "/c ($Cmd) > `"$tmpOut`" 2>&1" -PassThru -NoNewWindow
    $null = $p.Handle  # cache handle so ExitCode is readable after exit
    if (-not $p.WaitForExit($TimeoutSec * 1000)) {
        $timedOut = $true
        # kill whole tree
        & taskkill /PID $p.Id /T /F 2>&1 | Out-Null
        Start-Sleep -Milliseconds 500
    }
    $p.Refresh()
    $exit = $p.ExitCode
    if (Test-Path $tmpOut) { Get-Content $tmpOut -Raw -ErrorAction SilentlyContinue | Add-Content -Path $outPath -Encoding UTF8; Remove-Item $tmpOut -Force -ErrorAction SilentlyContinue }
}
else {
    $output = & cmd.exe /c "($Cmd) 2>&1"
    $exit = $LASTEXITCODE
    if ($null -ne $output) { ($output | Out-String) | Add-Content -Path $outPath -Encoding UTF8 }
}
$sw.Stop()
$end = & $utc
$footer = @()
$footer += "=== EXIT_CODE: $exit"
$footer += "=== TIMED_OUT: $timedOut"
$footer += "=== DURATION_S: $([math]::Round($sw.Elapsed.TotalSeconds, 2))"
$footer += "=== UTC_END: $end"
Add-Content -Path $outPath -Value ($footer -join "`r`n") -Encoding UTF8

if (-not (Test-Path $logPath)) { Set-Content -Path $logPath -Value 'artefact,utc_start,utc_end,duration_s,exit_code,timed_out,command' -Encoding UTF8 }
$cmdEsc = '"' + ($Cmd -replace '"', '""') + '"'
Add-Content -Path $logPath -Value "$Name,$start,$end,$([math]::Round($sw.Elapsed.TotalSeconds, 2)),$exit,$timedOut,$cmdEsc" -Encoding UTF8
Write-Host "[$Name] exit=$exit timed_out=$timedOut duration=$([math]::Round($sw.Elapsed.TotalSeconds, 2))s"
