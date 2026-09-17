# Project Lucca — Enterprise Hardware Topology & IPC Specification
**Document ID:** `SPEC-TOPOLOGY-003`  
**Revision:** 2.1  
**Classification:** Systems Engineering Specification  

---

## 1. System Partitioning & Physical Compute Map

Project Lucca operates across three distinct system domains:
1. **Domain A (Windows 11 Native Host):** Real-time I/O, audio capture, speaker output, OpenVINO NPU inference, sprite/lip-sync UI, memory subsystem, and orchestration.
2. **Domain B (WSL2 Linux Virtual Machine):** High-throughput LLM server (vLLM) running on the RTX 5080 with direct GPU-PV / CUDA passthrough.
3. **Domain C (Docker Sandbox inside WSL2):** Untrusted tool execution environment with dropped Linux capabilities, filesystem scoping, and blocked local subnet egress.

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                        DOMAIN A: WINDOWS 11 NATIVE HOST                       │
│                                                                               │
│  [Push-to-Talk] ──► [WASAPI Audio In (16kHz)] ──► [Silero VAD (ONNX/CPU)]     │
│                                                           │                   │
│  [2D Avatar UI] ◄── [WASAPI Audio Out] ◄── [Kokoro TTS (OpenVINO NPU INT8)]   │
│                                                           ▲                   │
│                                                           │ Sentence Stream   │
│  [Three-Tier Memory] ◄── [Orchestrator Core] ◄────────────┴─────────────────┐ │
│  (Chroma + NetworkX)      (Micro-Scheme LISP Engine)                        │ │
│                                  │                                          │ │
└──────────────────────────────────┼──────────────────────────────────────────┼─┘
                                   │ HTTP/1.1 Keep-Alive                      │
                                   │ Streaming POST (localhost:8000)          │
                                   ▼                                          │
┌─────────────────────────────────────────────────────────────────────────────┼─┐
│                        DOMAIN B: WSL2 LINUX ENVIRONMENT                     │ │
│                                                                             │ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │ │
│  │ vLLM Server (Python 3.12, CUDA 12.8, PyTorch 2.6+)                     │ │ │
│  │ - Engine: Ultravox 8B (Llama 3.1 8B Backbone + Whisper Large v3 Turbo) │ │ │
│  │ - Hardware: NVIDIA GeForce RTX 5080 (16GB VRAM, sm_120 Blackwell)     │ │ │
│  │ - Quantization: NVFP8 / Q6_K GGUF (Ceiling: 9.5GB VRAM)                │ │ │
│  └────────────────────────────────────────────────────────────────────────┘ │ │
│                                  │                                          │ │
│                                  │ Docker Engine API / Local Pipe           │ │
│                                  ▼                                          │ │
│  ┌───────────────────────────────────────────────────────────────────────┐  │ │
│  │              DOMAIN C: DOCKER SANDBOX (lucca-sandbox)                 │  │ │
│  │                                                                       │  │ │
│  │  - User: `lucca_sandbox` (UID 1000, unprivileged)                    │  │ │
│  │  - Filesystem: Read-Only Root, `/workspace` ephemeral bind mount      │  │ │
│  │  - Volume: `/data/persist` dedicated named persistent volume          │  │ │
│  │  - Network: Custom bridge `lucca-net` (Blocked RFC1918 egress)        │  │ │
│  │  - Tools: Safe File I/O, Headless Playwright (Read-only Web Fetch)   │  │ │
│  └───────────────────────────────────────────────────────────────────────┘  │ │
└─────────────────────────────────────────────────────────────────────────────┴─┘
```

---

## 2. Memory Clamping & Resource Budget Specifications

### 2.1 Host RAM Clamping (`.wslconfig`)
To prevent WSL2 from starving Windows 11 host memory and inducing swap paging:
Create or edit `%USERPROFILE%\.wslconfig`:
```ini
[wsl2]
# Strictly limit WSL2 VM memory to 4.5 GB out of 16 GB total
memory=4608MB

# Assign 4 cores to WSL2 (leaves 20 cores for Windows host & audio)
processors=4

# Clamped swap space
swap=2048MB

# Disable page reporting to prevent sudden memory spikes
pageReporting=false

# Enable localhost forwarding to route host <-> WSL2 on 127.0.0.1
localhostForwarding=true

# Nested virtualization not required
nestedVirtualization=false
```

### 2.2 RTX 5080 VRAM Budget Allocation (16,384 MB Total)
vLLM must be launched with strict memory utilization bounds:
```bash
vllm serve fixie-ai/ultravox-v0_5-llama-3_1-8b \
  --host 0.0.0.0 \
  --port 8000 \
  --gpu-memory-utilization 0.62 \
  --max-model-len 4096 \
  --max-num-seqs 1 \
  --enforce-eager \
  --trust-remote-code
```
* **Base Model (FP8 / Q6_K):** ~7,400 MB – 8,200 MB
* **KV Cache Allocation (0.62 limit):** ~1,900 MB (sufficient for 4,096 tokens)
* **CUDA Context & Runtime:** ~800 MB
* **Total Allocated VRAM:** **~10,150 MB – 10,900 MB**
* **Headroom Remaining:** **~5,480 MB free** (prevents memory thrashing or OOM during OS desktop compositing).

---

## 3. OpenVINO NPU Persistent Cache & Runtime Configuration

On the Windows Host, OpenVINO compiles the Kokoro TTS model directly for the Intel Arrow Lake NPU. To eliminate the 15-second cold-start compilation latency on startup:

```python
import openvino as ov
from pathlib import Path

def get_optimized_npu_core(cache_dir: Path) -> ov.Core:
    cache_dir.mkdir(parents=True, exist_ok=True)
    core = ov.Core()
    
    # Configure persistent compilation cache
    core.set_property("NPU", {
        "CACHE_DIR": str(cache_dir),
        "PERFORMANCE_HINT": "LATENCY",
        "NPU_COMPILATION_MODE_PARAMS": "compute-layers=ALL",
    })
    return core
```
* **First Run:** OpenVINO compiles the IR graph to an NPU binary blob (~12s).
* **Subsequent Starts:** OpenVINO validates blob hash and loads model in **$< 45\text{ms}$**.

---

## 4. Real-Time Audio Subsystem (Windows Native)

### 4.1 Windows Multimedia Class Scheduler Service (MMCSS)
To prevent audio crackle or buffer underruns when the CPU experiences bursty load, the audio threads register with `Avrt.dll`:

```python
import ctypes
from ctypes import wintypes

def elevate_thread_priority_mmcss() -> int:
    """Elevates calling thread to Windows MMCSS Pro Audio priority."""
    avrt = ctypes.windll.Avrt
    task_index = wintypes.DWORD(0)
    handle = avrt.AvSetMmThreadCharacteristicsW("Pro Audio", ctypes.byref(task_index))
    if not handle:
        raise OSError("Failed to set MMCSS Pro Audio thread characteristics.")
    return handle

def revert_thread_priority_mmcss(handle: int) -> None:
    ctypes.windll.Avrt.AvRevertMmThreadCharacteristics(handle)
```

### 4.2 Low-Latency Asynchronous Audio Engine Architecture
* **Sample Rate:** Standardized to **24,000 Hz** (Kokoro native) or **16,000 Hz** (Ultravox native) with zero-copy linear interpolation.
* **Format:** 16-bit signed PCM (int16), Mono.
* **Buffer Size:** 512 frames (~21.3ms per hardware callback) to maintain absolute minimum latency.

```
[ Microphone ]
      │
      ▼ WASAPI Input Callback (21.3ms chunks)
[ Circular Audio Buffer ]
      │
      ├── (On Hotkey Press) ──► Record PCM frames into memory buffer
      │
      └── (On Hotkey Release) ──► Flush PCM buffer
                                        │
                                        ▼
                           Encode to WAV (in-memory BytesIO)
                                        │
                                        ▼ Base64
                           HTTP/1.1 POST to vLLM / Ultravox
```

---

## 5. Sandboxed IPC & Container Security Architecture

### 5.1 Docker Sandbox Launch Manifest
The sandbox container is deployed on the WSL2 host via the following security profile:

```bash
docker run -d \
  --name lucca-sandbox \
  --user 1000:1000 \
  --read-only \
  --security-opt=no-new-privileges:true \
  --cap-drop=ALL \
  --net=lucca-net \
  --memory=1536m \
  --cpus=2.0 \
  --pids-limit=64 \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  -v /var/lucca/ephemeral_workspace:/workspace:rw \
  -v lucca_persistent_vol:/data/persist:rw \
  lucca-sandbox-runtime:latest
```

### 5.2 Network Egress Clamping via Iptables
The custom network `lucca-net` is configured inside WSL2:
```bash
# Create dedicated network
docker network create --subnet 172.28.0.0/16 lucca-net

# Block RFC1918 Private Subnets
iptables -I DOCKER-USER -s 172.28.0.0/16 -d 10.0.0.0/8 -j REJECT --reject-with icmp-port-unreachable
iptables -I DOCKER-USER -s 172.28.0.0/16 -d 172.16.0.0/12 -j REJECT --reject-with icmp-port-unreachable
iptables -I DOCKER-USER -s 172.28.0.0/16 -d 192.168.0.0/16 -j REJECT --reject-with icmp-port-unreachable
iptables -I DOCKER-USER -s 172.28.0.0/16 -d 169.254.0.0/16 -j REJECT --reject-with icmp-port-unreachable

# Allow Public Web Outbound (Ports 80, 443) and DNS (Port 53)
iptables -I DOCKER-USER -s 172.28.0.0/16 -p tcp -m multiport --dports 80,443 -j ACCEPT
iptables -I DOCKER-USER -s 172.28.0.0/16 -p udp --dport 53 -j ACCEPT
```

---

## 6. Blackwell SM120 Build Environment Recipe

To compile `vLLM` and `llama-cpp-python` against the NVIDIA GeForce RTX 5080 (Blackwell Architecture, Compute Capability 12.0):

```bash
# 1. Install CUDA Toolkit 12.8 inside WSL2 (Ubuntu 22.04 / 24.04)
wget https://developer.download.nvidia.com/compute/cuda/12.8.0/local_installers/cuda_12.8.0_570.86.10_linux.run
sudo sh cuda_12.8.0_570.86.10_linux.run --silent --toolkit

# 2. Configure Environment Variables
export CUDA_HOME=/usr/local/cuda-12.8
export PATH=$CUDA_HOME/bin:$PATH
export LD_LIBRARY_PATH=$CUDA_HOME/lib64:$LD_LIBRARY_PATH
export TORCH_CUDA_ARCH_LIST="12.0"

# 3. Install PyTorch 2.6+ with CUDA 12.8
pip install --pre torch torchvision torchaudio --index-url https://download.pytorch.org/whl/nightly/cu128

# 4. Build vLLM from source for SM120
git clone https://github.com/vllm-project/vllm.git
cd vllm
pip install -r requirements/build.txt
pip install --no-build-isolation -e .
```
This guarantees that FlashAttention, custom cutlass kernels, and AWQ/FP8 matrix routines compile with Blackwell native instructions rather than falling back to unoptimized PTX JIT compilation.
