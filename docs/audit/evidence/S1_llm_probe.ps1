# S1 step 12-13: start llama-server with EXACTLY the flags computed by lucca.brain.server_ctl.build_launch_command
# (see S1_15a_launch_cmd_from_code.txt), poll /health, capture VRAM + bind, then 5x streaming TTFT probes.
# Writes only under docs\audit\evidence. Server is left RUNNING for later steps (stopped in step 19).
param([switch]$DropLogFormat)
$ErrorActionPreference = 'Continue'
$ev = $PSScriptRoot
$sfx = if ($DropLogFormat) { 'b' } else { '' }
function UtcNow { (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ') }

$exe = 'C:\ProjectLucca\app\llama-server\llama-server.exe'
$args = @(
    '--model', 'C:\ProjectLucca\models\llm\ultravox-v0_5-llama-3_1-8b-Q6_K.gguf',
    '--n-gpu-layers', '99', '--ctx-size', '8192', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0',
    '--parallel', '1', '--flash-attn', 'on', '--host', '127.0.0.1', '--port', '8080', '--no-webui', '--jinja',
    '--log-format', 'json', '--mmproj', 'C:\ProjectLucca\models\llm\mmproj-ultravox-v0_5-llama-3_1-8b-Q8_0.gguf'
)
if ($DropLogFormat) { $args = @($args | Where-Object { $_ -ne '--log-format' -and $_ -ne 'json' }) }
$log = Join-Path $ev "S1_15${sfx}_llama_server.log"
$errlog = Join-Path $ev "S1_15${sfx}_llama_server.stderr.log"
$probe = Join-Path $ev "S1_15b${sfx}_llm_start_health.txt"

"=== ARTEFACT: S1_15b${sfx}_llm_start_health.txt / S1_15${sfx}_llama_server.log" | Set-Content $probe -Encoding UTF8
"=== PRODUCER: S1" | Add-Content $probe
"=== UTC_START: $(UtcNow)" | Add-Content $probe
"=== COMMAND: $exe $($args -join ' ')" | Add-Content $probe
if ($DropLogFormat) { "=== DEVIATION: identical to build_launch_command() output EXCEPT '--log-format json' removed, because the installed llama-server build rejects it (S1_15_llama_server.stderr.log: 'error: invalid argument: --log-format'). Measurement variant only; code untouched." | Add-Content $probe }
"=== NOTE: stdout -> S1_15${sfx}_llama_server.log ; stderr -> S1_15${sfx}_llama_server.stderr.log (Start-Process cannot merge)" | Add-Content $probe

$pre = & nvidia-smi '--query-gpu=memory.used' '--format=csv'
"VRAM_BEFORE_START: $pre" | Add-Content $probe

$sw = [System.Diagnostics.Stopwatch]::StartNew()
$p = Start-Process -FilePath $exe -ArgumentList $args -RedirectStandardOutput $log -RedirectStandardError $errlog -PassThru -WindowStyle Hidden
$null = $p.Handle
"LLAMA_PID: $($p.Id)" | Add-Content $probe
"SPAWN_UTC: $(UtcNow)" | Add-Content $probe

$healthy = $false; $lastCode = ''; $lastBody = ''
while ($sw.Elapsed.TotalSeconds -lt 180) {
    if ($p.HasExited) { "SERVER_EXITED_EARLY exit_code=$($p.ExitCode) at $([math]::Round($sw.Elapsed.TotalSeconds,2))s" | Add-Content $probe; break }
    try {
        $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8080/health' -UseBasicParsing -TimeoutSec 2
        $lastCode = $r.StatusCode; $lastBody = $r.Content
        if ($r.StatusCode -eq 200) { $healthy = $true; break }
    }
    catch {
        $lastCode = $_.Exception.Message
        if ($_.Exception.Response) { try { $lastCode = [int]$_.Exception.Response.StatusCode } catch {} }
    }
    Start-Sleep -Milliseconds 500
}
$tth = [math]::Round($sw.Elapsed.TotalSeconds, 2)
"HEALTHY: $healthy" | Add-Content $probe
"TIME_TO_HEALTHY_S: $tth" | Add-Content $probe
"LAST_HEALTH_STATUS: $lastCode" | Add-Content $probe
"LAST_HEALTH_BODY: $lastBody" | Add-Content $probe
"HEALTHY_UTC: $(UtcNow)" | Add-Content $probe

# S1_16 VRAM after LLM
$g = Join-Path $ev "S1_16${sfx}_gpu_after_llm.txt"
"=== ARTEFACT: S1_16${sfx}_gpu_after_llm.txt`r`n=== PRODUCER: S1`r`n=== UTC: $(UtcNow)`r`n=== COMMAND: nvidia-smi --query-gpu=memory.used,memory.total --format=csv ; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv" | Set-Content $g -Encoding UTF8
& nvidia-smi '--query-gpu=memory.used,memory.total' '--format=csv' 2>&1 | Add-Content $g
& nvidia-smi '--query-compute-apps=pid,process_name,used_memory' '--format=csv' 2>&1 | Add-Content $g
Start-Sleep -Seconds 5
"--- 5 s later:" | Add-Content $g
& nvidia-smi '--query-gpu=memory.used,memory.total' '--format=csv' 2>&1 | Add-Content $g

# S1_17 bind proof
$b = Join-Path $ev "S1_17${sfx}_llm_bind.txt"
"=== ARTEFACT: S1_17${sfx}_llm_bind.txt`r`n=== PRODUCER: S1`r`n=== UTC: $(UtcNow)`r`n=== COMMAND: netstat -ano | findstr 8080 ; Get-NetTCPConnection -LocalPort 8080" | Set-Content $b -Encoding UTF8
& cmd.exe /c "netstat -ano | findstr 8080" 2>&1 | Add-Content $b
"--- Get-NetTCPConnection -LocalPort 8080:" | Add-Content $b
Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | Format-Table LocalAddress, LocalPort, State, OwningProcess -AutoSize | Out-String | Add-Content $b
"--- server /props (model metadata):" | Add-Content $b
try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8080/props' -UseBasicParsing -TimeoutSec 5).Content | Add-Content $b } catch { "props error: $($_.Exception.Message)" | Add-Content $b }

# S1_18 TTFT probes x5
$t = Join-Path $ev "S1_18${sfx}_llm_ttft_probe.txt"
"=== ARTEFACT: S1_18${sfx}_llm_ttft_probe.txt`r`n=== PRODUCER: S1`r`n=== UTC_START: $(UtcNow)" | Set-Content $t -Encoding UTF8
$prompt = 'Please list five colours of the rainbow and one short fact about each colour in one line each.'
$bodyObj = @{ model = 'ultravox'; stream = $true; max_tokens = 64; temperature = 0.6; messages = @(@{ role = 'user'; content = $prompt }) }
$body = $bodyObj | ConvertTo-Json -Depth 5 -Compress
"=== METHOD: HttpWebRequest POST http://127.0.0.1:8080/v1/chat/completions stream=true max_tokens=64; TTFT = time from request send to first SSE 'data:' line containing non-empty delta content; TOTAL = time to '[DONE]'" | Add-Content $t
"=== PROMPT (~20 tokens): $prompt" | Add-Content $t
"=== BODY: $body" | Add-Content $t
if ($healthy) {
    for ($i = 1; $i -le 5; $i++) {
        $sw2 = [System.Diagnostics.Stopwatch]::StartNew()
        $ttft = $null; $total = $null; $ntok = 0; $firstChunkRaw = ''; $err = ''
        try {
            $req = [System.Net.HttpWebRequest]::Create('http://127.0.0.1:8080/v1/chat/completions')
            $req.Method = 'POST'; $req.ContentType = 'application/json'; $req.Timeout = 120000; $req.ReadWriteTimeout = 120000
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
            $req.ContentLength = $bytes.Length
            $rs = $req.GetRequestStream(); $rs.Write($bytes, 0, $bytes.Length); $rs.Close()
            $resp = $req.GetResponse()
            $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
            while (-not $sr.EndOfStream) {
                $line = $sr.ReadLine()
                if ($line -like 'data: *') {
                    $payload = $line.Substring(6)
                    if ($payload -eq '[DONE]') { $total = $sw2.Elapsed.TotalMilliseconds; break }
                    try {
                        $j = $payload | ConvertFrom-Json
                        $content = $j.choices[0].delta.content
                        if ($null -ne $content -and $content -ne '') {
                            $ntok++
                            if ($null -eq $ttft) { $ttft = $sw2.Elapsed.TotalMilliseconds; $firstChunkRaw = $payload }
                        }
                        if ($j.choices[0].finish_reason) { $finish = $j.choices[0].finish_reason }
                        if ($j.timings) { $timings = $j.timings | ConvertTo-Json -Compress }
                    }
                    catch { }
                }
            }
            if ($null -eq $total) { $total = $sw2.Elapsed.TotalMilliseconds }
            $sr.Close(); $resp.Close()
        }
        catch { $err = $_.Exception.Message; $total = $sw2.Elapsed.TotalMilliseconds }
        "RUN $i  UTC=$(UtcNow)  TTFT_ms=$([math]::Round($ttft,1))  TOTAL_ms=$([math]::Round($total,1))  content_chunks=$ntok  finish=$finish  err=$err" | Add-Content $t
        "   first_chunk=$firstChunkRaw" | Add-Content $t
        if ($timings) { "   server_timings=$timings" | Add-Content $t }
        Start-Sleep -Seconds 1
    }
}
else { "SKIPPED: server not healthy" | Add-Content $t }
"=== UTC_END: $(UtcNow)" | Add-Content $t
Get-Content $probe
Get-Content $g
Get-Content $b | Select-Object -First 12
Get-Content $t
