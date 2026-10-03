"""
Project Lucca — CosyVoice 3 Client Bridge
Spec 07 §5, Spec 16 §4, ADR-008, WO-27

Python 3.12 client bridge that communicates with the resident CosyVoice 3 service
in .venv-voice over ZeroMQ. Automatically manages service lifecycle and binds
continuous 3D PAD affective stance latents to neural synthesis conditioning.
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Final

import numpy as np
import zmq

logger = logging.getLogger("lucca.cosyvoice_client")

SERVICE_PORT: Final[int] = 47005
VENV_VOICE_PYTHON: Final[Path] = Path(r"C:\Projects\ProjectLucca\.venv-voice\Scripts\python.exe")
SERVICE_MODULE: Final[str] = "lucca.speech.cosyvoice_service"


class CosyVoice3Client:
    """Client for dispatching synthesis requests to the resident CosyVoice 3 GPU worker."""

    _instance: CosyVoice3Client | None = None

    def __init__(self, port: int = SERVICE_PORT) -> None:
        self.port = port
        self.ctx = zmq.Context()
        self.socket: zmq.Socket | None = None
        self._proc: subprocess.Popen | None = None
        self._connected = False

    @classmethod
    def get_instance(cls) -> CosyVoice3Client:
        if cls._instance is None:
            cls._instance = CosyVoice3Client()
        return cls._instance

    def _get_socket(self) -> zmq.Socket:
        if self.socket is None or self.socket.closed:
            self.socket = self.ctx.socket(zmq.REQ)
            self.socket.setsockopt(zmq.RCVTIMEO, 45000)
            self.socket.setsockopt(zmq.SNDTIMEO, 10000)
            self.socket.connect(f"tcp://127.0.0.1:{self.port}")
        return self.socket

    def ping(self) -> bool:
        """Checks if the CosyVoice 3 service is currently active and responding."""
        try:
            sock = self._get_socket()
            sock.setsockopt(zmq.RCVTIMEO, 200)
            sock.setsockopt(zmq.SNDTIMEO, 200)
            sock.send_json({"cmd": "ping"})
            resp = sock.recv_json()
            sock.setsockopt(zmq.RCVTIMEO, 45000)
            sock.setsockopt(zmq.SNDTIMEO, 10000)
            return bool(resp.get("status") == "ok")
        except Exception as exc:
            logger.debug("cosyvoice_ping_failed: %s", exc)
            self._close_socket()
            return False

    def ensure_service(self, timeout_s: float = 30.0) -> bool:
        """Ensures the CosyVoice 3 GPU daemon is running; spawns it if inactive."""
        if self.ping():
            return True

        if not VENV_VOICE_PYTHON.exists():
            logger.error("CosyVoice environment python not found at %s", VENV_VOICE_PYTHON)
            return False

        logger.info("Spawning CosyVoice 3 worker service in %s...", VENV_VOICE_PYTHON)
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        src_dir = repo_root / "src"

        service_script = repo_root / "src" / "lucca" / "speech" / "cosyvoice_service.py"
        cmd = [
            str(VENV_VOICE_PYTHON),
            str(service_script),
        ]

        env = os_env = dict(**dict(subprocess.os.environ))
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = f"{src_dir};{existing_pp}" if existing_pp else str(src_dir)

        self._proc = subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Poll until service responds to ping
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            time.sleep(1.0)
            if self.ping():
                logger.info("CosyVoice 3 worker is online and verified on port %d", self.port)
                return True

        logger.error("CosyVoice 3 worker failed to start within %.1fs", timeout_s)
        return False

    def synthesize(
        self,
        text: str,
        instruct: str = "",
        prompt_wav: str | None = None,
        profile: str = "inventor",
        speed: float = 1.0,
        stream: bool = True,
        direct_ring: bool = True,
    ) -> dict:
        """
        Sends text to the CosyVoice 3 service for neural synthesis.
        Writes audio directly to the 24kHz shared memory ring when direct_ring=True.
        """
        if not self.ensure_service():
            return {"status": "error", "error": "CosyVoice 3 service unavailable"}

        sock = self._get_socket()
        req = {
            "cmd": "synthesize",
            "text": text,
            "instruct": instruct,
            "prompt_wav": prompt_wav,
            "profile": profile,
            "speed": speed,
            "stream": stream,
            "direct_ring": direct_ring,
        }

        try:
            sock.send_json(req)
            return sock.recv_json()
        except Exception as exc:
            logger.error("Synthesize request error: %s", exc)
            self._close_socket()
            return {"status": "error", "error": str(exc)}

    def test_audio(
        self,
        text: str,
        instruct: str = "",
        prompt_wav: str | None = None,
        profile: str = "inventor",
        speed: float = 1.0,
    ) -> tuple[np.ndarray | None, int]:
        """
        Synthesizes audio and returns the raw PCM samples as a numpy array for UI playback.
        Returns: (samples_f32, sample_rate)
        """
        if not self.ensure_service():
            return None, 24000

        sock = self._get_socket()
        req = {
            "cmd": "test_audio",
            "text": text,
            "instruct": instruct,
            "prompt_wav": prompt_wav,
            "profile": profile,
            "speed": speed,
            "stream": False,
            "direct_ring": False,
        }

        try:
            sock.send_json(req)
            resp = sock.recv_json()
            if resp.get("status") == "ok" and "audio_b64" in resp:
                raw_bytes = base64.b64decode(resp["audio_b64"])
                samples_i16 = np.frombuffer(raw_bytes, dtype=np.int16)
                samples_f32 = (samples_i16.astype(np.float32) / 32767.0)
                return samples_f32, resp.get("sample_rate", 24000)
            return None, 24000
        except Exception as exc:
            logger.error("Test audio request error: %s", exc)
            self._close_socket()
            return None, 24000

    def _close_socket(self) -> None:
        if self.socket is not None:
            try:
                self.socket.close(linger=0)
            except Exception as exc:
                logger.debug("socket_close_failed: %s", exc)
            self.socket = None


VOICE_PROFILES: Final[dict[str, str]] = {
    "inventor": "a passionate systems engineer and inventive companion with introspective self-awareness",
    "companion": "a warm, gentle, and deeply empathetic companion who is patient, attentive, and caring",
    "heroine": "a spirited, fiercely loyal anime heroine with boundless energy and lively enthusiasm",
}


def format_cosyvoice_instruct(
    name: str = "Lucca",
    emotion_instruction: str = "steady, neutral",
    profile: str = "inventor",
) -> str:
    """Formats the instruction prompt for CosyVoice 3 conditioning header."""
    role_desc = VOICE_PROFILES.get(profile.lower(), VOICE_PROFILES["inventor"])
    return f"You are a helpful assistant. Please speak in English as {name} ({role_desc}) with a {emotion_instruction} cadence.<|endofprompt|>"
