"""
Project Lucca — Standalone RVC Worker Process (Python 3.10 / .venv-voice)
Spec 07 §5, ADR-008

Receives audio chunks over binary stdin, executes GPU-accelerated Asuka RVC
neural voice conversion via PyTorch CUDA 12.8 + HuBERT + HiFi-GAN,
and writes converted float32 waveforms to binary stdout.
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[3]
REPO_ROOT = Path(__file__).resolve().parents[4]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import numpy as np
import structlog

# Ensure all logging goes strictly to sys.stderr so sys.stdout is 100% pure IPC
structlog.configure(
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)


def main() -> None:
    if sys.platform == "win32":
        import msvcrt

        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)

    from lucca.speech.rvc.converter import AsukaRVCConverter

    conv = AsukaRVCConverter()
    if not conv.load_models():
        sys.stderr.write("Failed to load Asuka RVC models on GPU\n")
        sys.stderr.flush()
        sys.exit(1)

    # Signal parent process that models are resident in VRAM and ready
    sys.stdout.buffer.write(b"READY\n")
    sys.stdout.buffer.flush()

    while True:
        hdr = sys.stdin.buffer.read(12)
        if not hdr or len(hdr) < 12:
            break

        byte_len, orig_sr, out_sr = struct.unpack("<III", hdr)
        chunks: list[bytes] = []
        bytes_read = 0
        while bytes_read < byte_len:
            c = sys.stdin.buffer.read(min(byte_len - bytes_read, 65536))
            if not c:
                break
            chunks.append(c)
            bytes_read += len(c)

        if bytes_read != byte_len:
            break

        in_bytes = b"".join(chunks)
        audio_in = np.frombuffer(in_bytes, dtype=np.float32)

        try:
            audio_out = conv.convert(audio_in, orig_sr=orig_sr, out_sr=out_sr)
        except Exception as exc:  # noqa: BLE001
            logger.error("rvc_worker_convert_failed", error=str(exc))
            audio_out = audio_in

        out_bytes = audio_out.astype(np.float32).tobytes()
        sys.stdout.buffer.write(struct.pack("<I", len(out_bytes)))
        sys.stdout.buffer.write(out_bytes)
        sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
