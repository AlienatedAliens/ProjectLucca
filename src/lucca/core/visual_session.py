"""
Project Lucca — Visual Session Store (WO-37 Phase 0)
D-BRAIN-05, D-SEC-04, D-AUD-01

Maintains thread-safe local session image caching and on-demand reloading.
Deduplicates attached/captured frames by SHA-256 and bounds memory to MAX_IMAGES.
Zero-Any typing strictly enforced per D-AUD-01.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
from pathlib import Path
import threading
import time


@dataclass
class VisualArtifact:
    image_id: str       # "img_01", "img_02", ...
    sha256: str         # hex digest of raw JPEG bytes
    path: Path          # absolute path on disk
    captured_at: float  # time.time()
    description: str = ""


class VisualSessionStore:
    MAX_IMAGES: int = 8

    def __init__(self, store_dir: Path) -> None:
        self.store_dir: Path = store_dir
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self._lock: threading.RLock = threading.RLock()
        self._artifacts: list[VisualArtifact] = []
        self._counter: int = 0

    def store_image(self, b64_jpeg: str, description: str = "screenshot") -> VisualArtifact:
        """Decodes b64, hashes SHA-256, writes {sha256[:16]}.jpg, appends to index, evicts oldest if > MAX_IMAGES."""
        with self._lock:
            clean_b64 = b64_jpeg
            if "," in clean_b64:
                clean_b64 = clean_b64.split(",", 1)[1]
            raw_bytes = base64.b64decode(clean_b64)
            digest = hashlib.sha256(raw_bytes).hexdigest()

            # Check if already stored (dedup by SHA-256)
            for art in self._artifacts:
                if art.sha256 == digest:
                    return art

            self._counter += 1
            image_id = f"img_{self._counter:02d}"
            file_name = f"{digest[:16]}.jpg"
            img_path = self.store_dir / file_name
            img_path.write_bytes(raw_bytes)

            artifact = VisualArtifact(
                image_id=image_id,
                sha256=digest,
                path=img_path,
                captured_at=time.time(),
                description=description,
            )
            self._artifacts.append(artifact)

            # Evict oldest if count > MAX_IMAGES
            while len(self._artifacts) > self.MAX_IMAGES:
                evicted = self._artifacts.pop(0)
                try:
                    if evicted.path.exists() and not any(a.path == evicted.path for a in self._artifacts):
                        evicted.path.unlink(missing_ok=True)
                except OSError:
                    pass

            return artifact

    def get_active(self) -> VisualArtifact | None:
        with self._lock:
            return self._artifacts[-1] if self._artifacts else None

    def get_by_id(self, image_id: str) -> VisualArtifact | None:
        with self._lock:
            for art in self._artifacts:
                if art.image_id == image_id:
                    return art
            return None

    def load_b64(self, artifact: VisualArtifact) -> str | None:
        """Path.read_bytes() + base64 encode. Returns None on OSError."""
        try:
            raw = artifact.path.read_bytes()
            return base64.b64encode(raw).decode("ascii")
        except OSError:
            return None

    def clear(self) -> None:
        with self._lock:
            self._artifacts.clear()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._artifacts)
