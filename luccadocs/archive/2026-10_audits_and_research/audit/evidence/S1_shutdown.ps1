# S1 step 19: ordered shutdown of lucca.main + llama-server with evidence of child exit, VRAM leak, and container state.
$ErrorActionPreference = 'Continue'
$ev = $PSScriptRoot
function UtcNow { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ') }
$f = Join-Path $ev 'S1_37_shutdown.txt'
"=== ARTEFACT: S1_37_shutdown.txt`r`n=== PRODUCER: S1`r`n=== UTC_START: $(UtcNow)" | Set-Content $f -Encoding UTF8
function Snapshot($label) {
    "--- $label @ $(UtcNow)" | Add-Content $f
    $procs = Get-Process | Where-Object { $_.Name -like 'python*' -or $_.Name -like 'llama*' -or $_.Name -like 'uv' }
    if ($procs) { foreach ($p in $procs) { $ppid = (Get-CimInstance Win32_Process -Filter "ProcessId=$($p.Id)" -ErrorAction SilentlyContinue).ParentProcessId; "  {0,-14} PID={1,-6} PPID={2,-6} WS_MB={3,8:N1}" -f $p.Name, $p.Id, $ppid, ($p.WS / 1MB) | Add-Content $f } }
    else { "  (no python/llama/uv processes)" | Add-Content $f }
}
Snapshot 'BEFORE shutdown: python/llama/uv processes'
# Identify the supervisor: python.exe whose command line is "... -m lucca.main" and which has multiprocessing children
$sup = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*-m lucca.main*' -and $_.CommandLine -notlike '*.venv*' } | Select-Object -First 1
$launcher = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*.venv*-m lucca.main*' } | Select-Object -First 1
$uvp = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'uv.exe' -and $_.CommandLine -like '*lucca.main*' } | Select-Object -First 1
"SUPERVISOR_PID=$($sup.ProcessId)  LAUNCHER_PID=$($launcher.ProcessId)  UV_PID=$($uvp.ProcessId)" | Add-Content $f
$children = Get-CimInstance Win32_Process | Where-Object { $_.ParentProcessId -eq $sup.ProcessId } | Select-Object -ExpandProperty ProcessId
"CHILD_PIDS_OF_SUPERVISOR=$($children -join ',')" | Add-Content $f

"--- STEP 1: graceful 'taskkill /PID <supervisor>' (no /F) - emulates Ctrl+C/close for a console process @ $(UtcNow)" | Add-Content $f
& taskkill /PID $sup.ProcessId 2>&1 | Add-Content $f
$sw = [System.Diagnostics.Stopwatch]::StartNew()
Start-Sleep -Seconds 10
"WAITED_S=$([math]::Round($sw.Elapsed.TotalSeconds,1))" | Add-Content $f
Snapshot 'AFTER 10 s (graceful attempt)'
$alive = @()
foreach ($procId in @($sup.ProcessId) + $children) { if (Get-Process -Id $procId -ErrorAction SilentlyContinue) { $alive += $procId } }
"STILL_ALIVE_AFTER_GRACEFUL_10S=$($alive -join ',')  (count=$($alive.Count))" | Add-Content $f

if ($alive.Count -gt 0) {
    "--- STEP 2: taskkill /F /T on supervisor tree @ $(UtcNow)" | Add-Content $f
    & taskkill /F /T /PID $sup.ProcessId 2>&1 | Add-Content $f
    foreach ($procId in $alive) { if (Get-Process -Id $procId -ErrorAction SilentlyContinue) { & taskkill /F /PID $procId 2>&1 | Add-Content $f } }
    Start-Sleep -Seconds 3
    Snapshot 'AFTER force kill'
}
# also clean the uv/launcher wrappers if still around
foreach ($procId in @($launcher.ProcessId, $uvp.ProcessId)) { if ($procId -and (Get-Process -Id $procId -ErrorAction SilentlyContinue)) { "wrapper PID $procId still alive -> taskkill /F" | Add-Content $f; & taskkill /F /PID $procId 2>&1 | Add-Content $f } }

"--- VRAM with app down, llama-server still up @ $(UtcNow)" | Add-Content $f
& nvidia-smi '--query-gpu=memory.used,memory.total' '--format=csv' 2>&1 | Add-Content $f

"--- STEP 3: stop llama-server (graceful taskkill, 5 s, then /F if needed) @ $(UtcNow)" | Add-Content $f
$ll = Get-Process llama-server -ErrorAction SilentlyContinue
foreach ($p in $ll) { "llama-server PID=$($p.Id)" | Add-Content $f; & taskkill /PID $p.Id 2>&1 | Add-Content $f }
Start-Sleep -Seconds 5
$ll2 = Get-Process llama-server -ErrorAction SilentlyContinue
if ($ll2) { "llama-server still alive after graceful 5 s: $($ll2.Id -join ',') -> /F" | Add-Content $f; foreach ($p in $ll2) { & taskkill /F /PID $p.Id 2>&1 | Add-Content $f }; Start-Sleep -Seconds 3 } else { "llama-server exited within 5 s of graceful taskkill" | Add-Content $f }
Snapshot 'FINAL'
"=== UTC_END: $(UtcNow)" | Add-Content $f

# S1_38 GPU after shutdown
$g = Join-Path $ev 'S1_38_gpu_after_shutdown.txt'
"=== ARTEFACT: S1_38_gpu_after_shutdown.txt`r`n=== PRODUCER: S1`r`n=== UTC: $(UtcNow)`r`n=== COMMAND: nvidia-smi ; nvidia-smi --query-gpu=memory.used,memory.total --format=csv (immediately, +10 s)" | Set-Content $g -Encoding UTF8
& nvidia-smi 2>&1 | Add-Content $g
& nvidia-smi '--query-gpu=memory.used,memory.total' '--format=csv' 2>&1 | Add-Content $g
Start-Sleep -Seconds 10
"--- +10 s:" | Add-Content $g
& nvidia-smi '--query-gpu=memory.used,memory.total' '--format=csv' 2>&1 | Add-Content $g

# S1_39 containers after
$c = Join-Path $ev 'S1_39_containers_after.txt'
"=== ARTEFACT: S1_39_containers_after.txt`r`n=== PRODUCER: S1`r`n=== UTC: $(UtcNow)`r`n=== COMMAND: wsl -d Ubuntu -- docker ps -a ; wsl -d Ubuntu -- free -m ; wsl -l -v" | Set-Content $c -Encoding UTF8
& cmd.exe /c 'wsl -d Ubuntu -- docker ps -a' 2>&1 | Add-Content $c
& cmd.exe /c 'wsl -d Ubuntu -- free -m' 2>&1 | Add-Content $c
& cmd.exe /c 'wsl -l -v' 2>&1 | Add-Content $c

# tail of app log after shutdown
"--- S1_24 app stdout tail after shutdown:" | Add-Content $f
Get-Content (Join-Path $ev 'S1_24_lucca_main.log') -ErrorAction SilentlyContinue | Select-Object -Last 25 | Add-Content $f
"--- S1_24 app stderr tail after shutdown:" | Add-Content $f
Get-Content (Join-Path $ev 'S1_24_lucca_main.stderr.log') -ErrorAction SilentlyContinue | Select-Object -Last 25 | Add-Content $f
Get-Content $f
Get-Content $g | Select-Object -Last 6
Get-Content $c
