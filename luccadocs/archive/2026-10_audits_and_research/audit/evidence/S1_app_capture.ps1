# S1 step 15: start `uv run python -m lucca.main` in the background (log -> S1_24_lucca_main.log), wait 60 s,
# then capture process table, GPU, WSL memory, listening sockets, screenshot, and container state.
# Leaves the app RUNNING for steps 16-18; step 19 shuts it down. Writes only under docs\audit\evidence.
$ErrorActionPreference = 'Continue'
$ev = $PSScriptRoot
function UtcNow { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }
function Hdr($name, $cmd) { "=== ARTEFACT: $name`r`n=== PRODUCER: S1`r`n=== UTC: $(UtcNow)`r`n=== COMMAND: $cmd`r`n=== OUTPUT ===" }

$log = Join-Path $ev 'S1_24_lucca_main.log'
$errlog = Join-Path $ev 'S1_24_lucca_main.stderr.log'
$meta = Join-Path $ev 'S1_24a_lucca_main_launch.txt'
Hdr 'S1_24a_lucca_main_launch.txt' 'uv run python -m lucca.main  (Start-Process, cwd=C:\Projects\ProjectLucca, stdout->S1_24_lucca_main.log, stderr->S1_24_lucca_main.stderr.log)' | Set-Content $meta -Encoding UTF8
$pre = & nvidia-smi '--query-gpu=memory.used' '--format=csv'
"VRAM_BEFORE_APP: $($pre -join ' ')" | Add-Content $meta
$p = Start-Process -FilePath 'uv' -ArgumentList @('run', 'python', '-m', 'lucca.main') -WorkingDirectory 'C:\Projects\ProjectLucca' -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -WindowStyle Hidden
$null = $p.Handle
"UV_PID: $($p.Id)" | Add-Content $meta
"SPAWN_UTC: $(UtcNow)" | Add-Content $meta
Set-Content (Join-Path $ev 'S1_24_uv_pid.txt') $p.Id
Start-Sleep -Seconds 60
"AFTER_60S_UTC: $(UtcNow)" | Add-Content $meta
"UV_HAS_EXITED: $($p.HasExited)  EXIT_CODE: $(if ($p.HasExited) { $p.ExitCode } else { 'n/a' })" | Add-Content $meta
"--- stdout log so far:" | Add-Content $meta
Get-Content $log -ErrorAction SilentlyContinue | Add-Content $meta
"--- stderr log so far:" | Add-Content $meta
Get-Content $errlog -ErrorAction SilentlyContinue | Add-Content $meta

# S1_25 process table
$f = Join-Path $ev 'S1_25_process_table.txt'
Hdr 'S1_25_process_table.txt' 'tasklist /fi "imagename eq python.exe" /v ; S1_ps_helpers.ps1 -Action proctable' | Set-Content $f -Encoding UTF8
& cmd.exe /c 'tasklist /fi "imagename eq python.exe" /v' 2>&1 | Add-Content $f
& cmd.exe /c 'tasklist /fi "imagename eq llama-server.exe" /v' 2>&1 | Add-Content $f
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ev 'S1_ps_helpers.ps1') -Action proctable 2>&1 | Add-Content $f

# S1_26 full nvidia-smi
$f = Join-Path $ev 'S1_26_gpu_full_app.txt'
Hdr 'S1_26_gpu_full_app.txt' 'nvidia-smi ; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv' | Set-Content $f -Encoding UTF8
& nvidia-smi 2>&1 | Add-Content $f
& nvidia-smi '--query-compute-apps=pid,process_name,used_memory' '--format=csv' 2>&1 | Add-Content $f

# S1_27 WSL mem under load
$f = Join-Path $ev 'S1_27_wsl_mem_under_load.txt'
Hdr 'S1_27_wsl_mem_under_load.txt' 'wsl -d Ubuntu -- free -m ; wsl -d Ubuntu -- docker stats --no-stream' | Set-Content $f -Encoding UTF8
& cmd.exe /c 'wsl -d Ubuntu -- free -m' 2>&1 | Add-Content $f
& cmd.exe /c 'wsl -d Ubuntu -- docker stats --no-stream' 2>&1 | Add-Content $f

# S1_28 listening sockets
$f = Join-Path $ev 'S1_28_listening_sockets.txt'
Hdr 'S1_28_listening_sockets.txt' 'netstat -ano | findstr LISTEN ; S1_ps_helpers.ps1 -Action sockets' | Set-Content $f -Encoding UTF8
& cmd.exe /c 'netstat -ano | findstr LISTEN' 2>&1 | Add-Content $f
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ev 'S1_ps_helpers.ps1') -Action sockets 2>&1 | Add-Content $f

# S1_29 screenshot
$shot = Join-Path $ev 'S1_29_ui_screenshot.png'
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $ev 'S1_ps_helpers.ps1') -Action screenshot -Arg $shot 2>&1 | Add-Content $meta

# S1_22b / S1_23 containers after app start
$f = Join-Path $ev 'S1_22b_container_ports_mounts_app_running.txt'
Hdr 'S1_22b_container_ports_mounts_app_running.txt' 'wsl -d Ubuntu -- docker ps -a --format "{{.Names}} STATUS={{.Status}} PORTS=[{{.Ports}}] MOUNTS=[{{.Mounts}}]"' | Set-Content $f -Encoding UTF8
& cmd.exe /c 'wsl -d Ubuntu -- docker ps -a --format "{{.Names}} STATUS={{.Status}} PORTS=[{{.Ports}}] MOUNTS=[{{.Mounts}}]"' 2>&1 | Add-Content $f
& cmd.exe /c 'wsl -d Ubuntu -- docker ps -a' 2>&1 | Add-Content $f
$names = & cmd.exe /c 'wsl -d Ubuntu -- docker ps -a --format "{{.Names}}"' 2>$null | Where-Object { $_ -match '^\S+$' }
$f2 = Join-Path $ev 'S1_23_container_inspect.json'
if ($names) {
    "// ARTEFACT: S1_23_container_inspect.json  PRODUCER: S1  UTC: $(UtcNow)  COMMAND: wsl -d Ubuntu -- docker inspect $($names -join ' ')" | Set-Content $f2 -Encoding UTF8
    & cmd.exe /c "wsl -d Ubuntu -- docker inspect $($names -join ' ')" 2>&1 | Add-Content $f2
    "--- extracted security fields:" | Add-Content $f
    & cmd.exe /c "wsl -d Ubuntu -- docker inspect --format ""{{.Name}} User={{.Config.User}} ReadonlyRootfs={{.HostConfig.ReadonlyRootfs}} NetworkMode={{.HostConfig.NetworkMode}} Memory={{.HostConfig.Memory}} PidsLimit={{.HostConfig.PidsLimit}} CapDrop={{.HostConfig.CapDrop}} SecurityOpt={{.HostConfig.SecurityOpt}} PortBindings={{.HostConfig.PortBindings}} Mounts={{range .Mounts}}[{{.Type}} {{.Source}} -> {{.Destination}} rw={{.RW}}] {{end}}"" $($names -join ' ')" 2>&1 | Add-Content $f
}
else {
    "// ARTEFACT: S1_23_container_inspect.json  PRODUCER: S1  UTC: $(UtcNow)`r`n// NO CONTAINERS EXIST (docker ps -a empty) 60 s after lucca.main start -> nothing to inspect." | Set-Content $f2 -Encoding UTF8
    "NO CONTAINERS EXIST 60 s after app start." | Add-Content $f
}
"=== DONE_UTC: $(UtcNow)" | Add-Content $meta
Get-Content $meta
Get-Content (Join-Path $ev 'S1_25_process_table.txt') | Select-Object -Skip 5
Get-Content (Join-Path $ev 'S1_26_gpu_full_app.txt') | Select-Object -First 30
Get-Content (Join-Path $ev 'S1_27_wsl_mem_under_load.txt')
Get-Content (Join-Path $ev 'S1_28_listening_sockets.txt') | Select-String -Pattern 'Filtered|PID=' -Context 0, 0 | Select-Object -Last 30
Get-Content $f
