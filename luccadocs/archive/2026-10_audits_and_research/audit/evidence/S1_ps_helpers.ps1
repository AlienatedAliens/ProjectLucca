# S1 PowerShell-native capture helpers (audit subtask S1). Read-only against the system; writes nothing itself.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File docs\audit\evidence\S1_ps_helpers.ps1 -Action <hostmem|proctable|sockets|screenshot|sha256> [-Arg <value>]
param(
    [Parameter(Mandatory = $true)][string]$Action,
    [string]$Arg = ''
)
$ErrorActionPreference = 'Continue'
"UTC_NOW: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
switch ($Action) {
    'hostmem' {
        Get-CimInstance Win32_OperatingSystem | Select-Object TotalVisibleMemorySize, FreePhysicalMemory | Format-List | Out-String -Width 200
        "--- Top 15 processes by working set (WS bytes) ---"
        Get-Process | Sort-Object WS -Descending | Select-Object -First 15 Name, Id, WS | Format-Table -AutoSize | Out-String -Width 200
    }
    'proctable' {
        "--- Get-Process python*,llama*,lucca*,uv* : Name Id WS PM CPU StartTime CommandLine ---"
        $procs = Get-Process | Where-Object { $_.Name -like 'python*' -or $_.Name -like 'llama*' -or $_.Name -like 'lucca*' -or $_.Name -like 'uv*' }
        foreach ($p in $procs) {
            $cl = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" -ErrorAction SilentlyContinue).CommandLine
            $ppid = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" -ErrorAction SilentlyContinue).ParentProcessId
            "{0,-20} PID={1,-7} PPID={2,-7} WS_MB={3,9:N1} PM_MB={4,9:N1} CPU_s={5,8:N1} START={6}" -f $p.Name, $p.Id, $ppid, ($p.WS / 1MB), ($p.PM / 1MB), $p.CPU, $p.StartTime
            "    CMD: $cl"
        }
        if (-not $procs) { "(no matching processes)" }
    }
    'sockets' {
        "--- Get-NetTCPConnection -State Listen (all) with owning process name ---"
        Get-NetTCPConnection -State Listen | ForEach-Object {
            $pn = (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).Name
            "{0,-40} :{1,-6} PID={2,-7} {3}" -f $_.LocalAddress, $_.LocalPort, $_.OwningProcess, $pn
        } | Sort-Object
        "--- Filtered to python/llama/lucca/uv owners ---"
        Get-NetTCPConnection -State Listen | ForEach-Object {
            $pn = (Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue).Name
            if ($pn -like 'python*' -or $pn -like 'llama*' -or $pn -like 'lucca*' -or $pn -like 'uv*') {
                $flag = if ($_.LocalAddress -ne '127.0.0.1' -and $_.LocalAddress -ne '::1') { '  <== NOT LOOPBACK' } else { '' }
                "{0,-40} :{1,-6} PID={2,-7} {3}{4}" -f $_.LocalAddress, $_.LocalPort, $_.OwningProcess, $pn, $flag
            }
        }
    }
    'screenshot' {
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        $b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
        $bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
        $g = [System.Drawing.Graphics]::FromImage($bmp)
        $g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
        $bmp.Save($Arg, [System.Drawing.Imaging.ImageFormat]::Png)
        $g.Dispose(); $bmp.Dispose()
        "Saved screenshot $($b.Width)x$($b.Height) to $Arg"
    }
    'sha256' {
        # $Arg = path to MANIFEST.json ; verifies each listed file's sha256 with certutil
        $manifestPath = $Arg
        $root = Split-Path $manifestPath -Parent
        "--- MANIFEST: $manifestPath ---"
        Get-Content $manifestPath -Raw
        "--- VERIFICATION (certutil -hashfile) ---"
        $m = Get-Content $manifestPath -Raw | ConvertFrom-Json
        # Handle common shapes: {"files":[{path,sha256}]} or {path: sha} or [{path,sha256}]
        $entries = @()
        if ($m.PSObject.Properties.Name -contains 'files') { $entries = $m.files }
        elseif ($m -is [System.Array]) { $entries = $m }
        else { foreach ($p in $m.PSObject.Properties) { if ($p.Value -is [string]) { $entries += [pscustomobject]@{ path = $p.Name; sha256 = $p.Value } } elseif ($p.Value.PSObject.Properties.Name -contains 'sha256') { $entries += [pscustomobject]@{ path = ($(if ($p.Value.path) { $p.Value.path } else { $p.Name })); sha256 = $p.Value.sha256 } } } }
        if (-not $entries) { "Could not derive file entries from manifest shape; keys: $($m.PSObject.Properties.Name -join ', ')" }
        foreach ($e in $entries) {
            $rel = if ($e.path) { $e.path } elseif ($e.file) { $e.file } elseif ($e.name) { $e.name } else { "$e" }
            $exp = if ($e.sha256) { $e.sha256 } elseif ($e.sha) { $e.sha } else { '' }
            $full = if ([System.IO.Path]::IsPathRooted($rel)) { $rel } else { Join-Path $root $rel }
            if (-not (Test-Path $full)) { "MISSING   $rel  (expected $exp)"; continue }
            $sizeMB = [math]::Round((Get-Item $full).Length / 1MB, 1)
            $out = & certutil -hashfile "$full" SHA256 2>&1
            $act = ($out | Where-Object { $_ -match '^[0-9a-fA-F]{64}$' } | Select-Object -First 1)
            if (-not $act) { $act = ($out | Select-Object -Skip 1 -First 1) -replace ' ', '' }
            $status = if ($exp -and $act -and ($act.ToLower() -eq $exp.ToLower())) { 'MATCH   ' } elseif (-not $exp) { 'NO_EXPECTED' } else { 'MISMATCH' }
            "$status  $rel  size_MB=$sizeMB  actual=$act  expected=$exp"
        }
    }
    default { "Unknown action $Action" }
}
