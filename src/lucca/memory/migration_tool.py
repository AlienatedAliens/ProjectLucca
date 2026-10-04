"""
Project Lucca — Cryptographic Memory Key Migration Tool
Facilitates migration of legacy HMAC-signed memory records from historical
dev-fallback keys to persisted active master keys without data loss.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
from typing import Final

import structlog

from lucca.core.schemas import Provenance
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import derive_provenance_key

logger = structlog.get_logger(__name__)

# Canonical historical development fallback key used in pre-v1.35.2 runs
DEV_FALLBACK_MASTER_KEY: Final[bytes] = b"0123456789abcdef0123456789abcdef"

_EXCLUDED: Final[frozenset[str]] = frozenset(
    {"signature", "signer_id", "entry_id", "content_sha256"}
)


@dataclasses.dataclass(slots=True)
class KeyMigrationReport:
    """Detailed summary of memory key migration execution."""

    total_scanned: int = 0
    migrated_count: int = 0
    already_valid_count: int = 0
    tampered_skipped_count: int = 0
    quarantine_cleared_count: int = 0
    errors: list[str] = dataclasses.field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return len(self.errors) == 0


def migrate_memory_keys(
    db: DatabaseManager,
    new_master_key: bytes,
    old_master_key: bytes = DEV_FALLBACK_MASTER_KEY,
    dry_run: bool = False,
    force: bool = False,
) -> KeyMigrationReport:
    """Migrates existing memory envelopes signed with old_master_key to new_master_key.

    Steps:
    1. Verifies content SHA-256 integrity to ensure records were not modified at rest.
    2. Verifies payload JSON correspondence.
    3. Validates that the existing signature matches old_master_key (or force is True).
    4. Computes new HMAC-SHA256 signature using new_master_key.
    5. Atomically updates provenance_envelopes and removes migrated records from memory_quarantine.
    """
    if len(new_master_key) < 32:
        raise ValueError(f"new_master_key must be at least 32 bytes, got {len(new_master_key)}")
    if len(old_master_key) < 32:
        raise ValueError(f"old_master_key must be at least 32 bytes, got {len(old_master_key)}")

    report = KeyMigrationReport()

    # Ensure quarantine table exists
    writer = db.get_writer()
    writer.execute("BEGIN IMMEDIATE")
    try:
        writer.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_quarantine (
                memory_id INTEGER PRIMARY KEY,
                entry_id TEXT,
                reason TEXT,
                stage TEXT,
                quarantined_at REAL
            )
            """
        )
        writer.execute("COMMIT")
    except Exception:
        writer.execute("ROLLBACK")
        raise

    # Fetch all memories with provenance envelopes
    with db.read_cursor() as cur:
        cur.execute(
            """
            SELECT m.memory_id, m.content, e.entry_id, e.provenance, e.signature,
                   e.content_sha256, e.payload_json
            FROM memories m
            JOIN provenance_envelopes e ON m.entry_id = e.entry_id
            ORDER BY m.memory_id ASC
            """
        )
        rows = cur.fetchall()

    report.total_scanned = len(rows)

    updates_to_apply: list[tuple[str, str, str, int]] = []
    quarantine_ids_to_clear: list[int] = []

    for row in rows:
        mid = int(row["memory_id"])
        content_str = str(row["content"])
        entry_id = str(row["entry_id"])
        prov_str = str(row["provenance"])
        stored_sig = str(row["signature"])
        stored_sha = str(row["content_sha256"])
        payload_raw = str(row["payload_json"])

        # Stage 1: Fast-fail content SHA-256 check
        actual_sha = hashlib.sha256(content_str.encode("utf-8")).hexdigest()
        if actual_sha != stored_sha:
            report.tampered_skipped_count += 1
            report.errors.append(
                f"Memory #{mid} (entry {entry_id[:8]}): content SHA-256 mismatch; skipping"
            )
            continue

        # Stage 2: Payload JSON validation and canonical bytes reconstruction
        try:
            raw_dict = json.loads(payload_raw)
            if not isinstance(raw_dict, dict):
                raise ValueError("payload_json root is not an object")
        except Exception as exc:  # noqa: BLE001
            logger.debug("migration_payload_parse_error", memory_id=mid, error=str(exc))
            report.tampered_skipped_count += 1
            report.errors.append(
                f"Memory #{mid} (entry {entry_id[:8]}): invalid payload JSON ({exc})"
            )
            continue

        if "content" in raw_dict and raw_dict["content"] != content_str:
            report.tampered_skipped_count += 1
            report.errors.append(
                f"Memory #{mid} (entry {entry_id[:8]}): payload content != memories.content"
            )
            continue

        canon_dict = {k: v for k, v in raw_dict.items() if k not in _EXCLUDED}
        canonical_bytes = json.dumps(
            canon_dict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        try:
            prov_enum = Provenance(prov_str)
        except ValueError:
            report.tampered_skipped_count += 1
            report.errors.append(
                f"Memory #{mid} (entry {entry_id[:8]}): unknown provenance '{prov_str}'"
            )
            continue

        # Compute signature under new key
        new_derived = derive_provenance_key(new_master_key, prov_enum)
        new_sig = base64.b64encode(
            hmac.new(new_derived, canonical_bytes, hashlib.sha256).digest()
        ).decode("ascii")

        if hmac.compare_digest(stored_sig, new_sig):
            # Already valid under new key
            report.already_valid_count += 1
            quarantine_ids_to_clear.append(mid)
            continue

        # Check if current signature matches old key
        old_derived = derive_provenance_key(old_master_key, prov_enum)
        old_sig = base64.b64encode(
            hmac.new(old_derived, canonical_bytes, hashlib.sha256).digest()
        ).decode("ascii")

        is_old_match = hmac.compare_digest(stored_sig, old_sig)
        if not is_old_match and not force:
            report.tampered_skipped_count += 1
            report.errors.append(
                f"Memory #{mid} (entry {entry_id[:8]}): "
                "signature does not match old key and force=False"
            )
            continue

        # Eligible for migration: update payload_json signature and record
        raw_dict["signature"] = new_sig
        new_payload_json = json.dumps(
            raw_dict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        updates_to_apply.append((new_sig, new_payload_json, entry_id, mid))
        quarantine_ids_to_clear.append(mid)

    # Apply database mutations atomically if not a dry run
    if not dry_run and updates_to_apply:
        writer = db.get_writer()
        writer.execute("BEGIN IMMEDIATE")
        try:
            for new_sig, new_payload_json, entry_id, _mid in updates_to_apply:
                writer.execute(
                    """
                    UPDATE provenance_envelopes
                    SET signature = ?, payload_json = ?
                    WHERE entry_id = ?
                    """,
                    (new_sig, new_payload_json, entry_id),
                )

            if quarantine_ids_to_clear:
                placeholders = ",".join("?" for _ in quarantine_ids_to_clear)
                writer.execute(
                    f"DELETE FROM memory_quarantine WHERE memory_id IN ({placeholders})",  # noqa: S608
                    quarantine_ids_to_clear,
                )
            writer.execute("COMMIT")
        except Exception:
            writer.execute("ROLLBACK")
            raise

        report.migrated_count = len(updates_to_apply)
        report.quarantine_cleared_count = len(quarantine_ids_to_clear)
    elif dry_run:
        report.migrated_count = len(updates_to_apply)
        report.quarantine_cleared_count = len(quarantine_ids_to_clear)

    logger.info(
        "memory_key_migration_completed",
        scanned=report.total_scanned,
        migrated=report.migrated_count,
        already_valid=report.already_valid_count,
        tampered_skipped=report.tampered_skipped_count,
        quarantine_cleared=report.quarantine_cleared_count,
        dry_run=dry_run,
    )

    return report
