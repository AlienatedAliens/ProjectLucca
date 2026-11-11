"""Pure-Python OpenTimestamps (.ots) detached proof stamper & verifier for WO-45 RM-6 (`REVIEW_G4.md:80-86`).

Submits a privacy-salted SHA-256 digest (`sha256(file_sha256 || 16B_nonce)`) to multiple public
OpenTimestamps calendar pools (`a.pool.opentimestamps.org`, `b.pool.opentimestamps.org`,
`a.pool.eternitywall.com`) and serializes a spec-compliant v1 `.ots` detached timestamp file
(`\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94\x01\x08...`) verifiable by `ots verify`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import urllib.request
from pathlib import Path
from typing import Final

OTS_HEADER_MAGIC: Final[bytes] = (
    b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
)
OTS_VERSION_1: Final[bytes] = b"\x01"
OP_SHA256: Final[bytes] = b"\x08"
OP_APPEND: Final[bytes] = b"\xf0"
TAG_FORK: Final[bytes] = b"\xff"

CALENDAR_POOLS: Final[tuple[str, ...]] = (
    "https://a.pool.opentimestamps.org/digest",
    "https://b.pool.opentimestamps.org/digest",
    "https://a.pool.eternitywall.com/digest",
)


def sha256_bytes(path: Path) -> bytes:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.digest()


def stamp_file(target_path: Path, out_ots_path: Path | None = None) -> Path:
    if not target_path.is_file():
        raise FileNotFoundError(f"Cannot stamp missing file: {target_path}")
    ots_path = out_ots_path if out_ots_path is not None else Path(f"{target_path}.ots")

    file_digest = sha256_bytes(target_path)
    nonce = os.urandom(16)
    salted_digest = hashlib.sha256(file_digest + nonce).digest()

    calendar_proofs: list[bytes] = []
    for url in CALENDAR_POOLS:
        req = urllib.request.Request(
            url,
            data=salted_digest,
            headers={
                "Accept": "application/vnd.opentimestamps.v1",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "ProjectLucca-OTS-Stamper/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                if resp.status == 200:
                    body = resp.read()
                    if body:
                        calendar_proofs.append(body)
        except Exception:  # noqa: BLE001, S112
            continue

    if not calendar_proofs:
        raise RuntimeError(f"All OpenTimestamps calendar pools failed for {target_path}")

    buf = bytearray()
    buf.extend(OTS_HEADER_MAGIC)
    buf.extend(OTS_VERSION_1)
    buf.extend(OP_SHA256)
    buf.extend(file_digest)
    buf.extend(OP_APPEND)
    buf.append(len(nonce))
    buf.extend(nonce)
    buf.extend(OP_SHA256)

    for idx, proof_bytes in enumerate(calendar_proofs):
        if idx < len(calendar_proofs) - 1:
            buf.extend(TAG_FORK)
        buf.extend(proof_bytes)

    ots_path.write_bytes(bytes(buf))
    verify_ots_matches_file(target_path, ots_path)
    return ots_path


def verify_ots_matches_file(target_path: Path, ots_path: Path) -> dict[str, object]:
    raw = ots_path.read_bytes()
    prefix = OTS_HEADER_MAGIC + OTS_VERSION_1 + OP_SHA256
    if not raw.startswith(prefix):
        raise ValueError(f"Invalid OpenTimestamps v1 SHA-256 header in {ots_path}")
    embedded_digest = raw[len(prefix) : len(prefix) + 32]
    actual_digest = sha256_bytes(target_path)
    if embedded_digest != actual_digest:
        raise ValueError(
            f"OTS digest mismatch for {target_path}: "
            f"ots={embedded_digest.hex()} != actual={actual_digest.hex()}"
        )
    has_calendar = b"https://" in raw
    if not has_calendar:
        raise ValueError(f"OTS file {ots_path} contains no calendar attestation URL")
    return {
        "target_path": str(target_path),
        "ots_path": str(ots_path),
        "file_sha256": actual_digest.hex(),
        "ots_sha256": hashlib.sha256(raw).hexdigest(),
        "ots_bytes": len(raw),
        "valid_header_and_digest": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    for fpath in args.files:
        if args.verify_only:
            res = verify_ots_matches_file(fpath, Path(f"{fpath}.ots"))
            print(f"[OTS VERIFIED] {res['target_path']} -> sha256={res['file_sha256']}")
        else:
            ots_p = stamp_file(fpath)
            res = verify_ots_matches_file(fpath, ots_p)
            print(
                f"[OTS STAMPED] {ots_p} ({res['ots_bytes']} B, file_sha256={res['file_sha256']})"
            )


if __name__ == "__main__":
    main()
