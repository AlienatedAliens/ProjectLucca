"""
Project Lucca — Cryptographic Memory Key Migration Tool
Facilitates migration of legacy HMAC-signed memory records from historical
dev-fallback keys to persisted active master keys without data loss.

DEPRECATION WARNING:
This tool is a one-time migration facility for v1.35.x legacy envelopes and will
be permanently excised in v1.36.0.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import shutil
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import structlog

from lucca.core.schemas import Provenance
from lucca.memory.db import DatabaseManager
from lucca.memory.signers import derive_provenance_key

logger = structlog.get_logger(__name__)

# Known historical development fallback keys detected across repository revisions
KNOWN_LEGACY_KEYS: Final[tuple[bytes, ...]] = (
    b"01234567890123456789012345678901",  # Core dev key from signer_factory
    b"dev_master_key_do_not_use_in_prod", # Canonical dev string
    b"\x00" * 32,                         # 32 null bytes fallback
    b"0123456789abcdef0123456789abcdef", # Hex fallback key
)

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
    lisp_assertions_held_count: int = 0
    provenance_counts: dict[str, int] = dataclasses.field(default_factory=dict)
    backup_path: str | None = None
    already_migrated: bool = False
    errors: list[str] = dataclasses.field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return len(self.errors) == 0


def migrate_memory_keys(
    db: DatabaseManager,
    new_master_key: bytes,
    legacy_keys: Sequence[bytes] = KNOWN_LEGACY_KEYS,
    target_entry_id: str | None = None,
    dry_run: bool = False,
    rebless_lisp_assertions: bool = False,
    create_backup: bool = True,
) -> KeyMigrationReport:
    """Migrates existing memory envelopes signed with legacy keys to new_master_key.

    Safeguards:
    1. One-time migration flag in SQLite prevents accidental duplicate migration runs.
    2. File backup of database before any writes.
    3. Multi-key legacy verification: checks against all known historical fallbacks.
    4. LISP_ASSERTION rows are held for review by default (never auto-blessed into grounding).
    5. Atomic transaction with rollback on failure.
    6. Strict avoidance of --force: unverified rows are never re-signed.
    """
    if len(new_master_key) < 32:
        raise ValueError(f"new_master_key must be at least 32 bytes, got {len(new_master_key)}")

    logger.warning(
        "migration_deprecation_notice",
        message="Memory key migration is a one-time migration utility for v1.35.x",
    )

    report = KeyMigrationReport()

    # Ensure quarantine and migration metadata tables exist
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
        writer.execute(
            """
            CREATE TABLE IF NOT EXISTS migration_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
            """
        )
        writer.execute("COMMIT")
    except Exception:
        writer.execute("ROLLBACK")
        raise

    # Check migration done flag if doing full migration
    if target_entry_id is None:
        with db.read_cursor() as cur:
            cur.execute("SELECT value FROM migration_metadata WHERE key = 'keys_migrated'")
            row = cur.fetchone()
            if row and row["value"] == "1":
                report.already_migrated = True
                report.errors.append("Migration already completed. Migration done flag is set.")
                return report

    # Fetch candidate envelopes
    query = """
        SELECT m.memory_id, m.content, e.entry_id, e.provenance, e.signature,
               e.content_sha256, e.payload_json
        FROM memories m
        JOIN provenance_envelopes e ON m.entry_id = e.entry_id
    """
    params: list[str] = []
    if target_entry_id:
        query += " WHERE e.entry_id = ?"
        params.append(target_entry_id)
    query += " ORDER BY m.memory_id ASC"

    with db.read_cursor() as cur:
        cur.execute(query, tuple(params))
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

        report.provenance_counts[prov_str] = report.provenance_counts.get(prov_str, 0) + 1

        # Safeguard: LISP_ASSERTION rows are LLM-proposed abductive inferences.
        # They must not be automatically re-blessed into grounding-eligible memory.
        if prov_str == Provenance.LISP_ASSERTION.value and not rebless_lisp_assertions:
            report.lisp_assertions_held_count += 1
            report.errors.append(
                f"Memory #{mid} (entry {entry_id[:8]}): LISP_ASSERTION held; "
                "not automatically re-blessed as grounding-eligible"
            )
            continue

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

        # Compute signature under active new key
        new_derived = derive_provenance_key(new_master_key, prov_enum)
        new_sig = base64.b64encode(
            hmac.new(new_derived, canonical_bytes, hashlib.sha256).digest()
        ).decode("ascii")

        if hmac.compare_digest(stored_sig, new_sig):
            # Already valid under active new key
            report.already_valid_count += 1
            quarantine_ids_to_clear.append(mid)
            continue

        # Test against all known candidate legacy keys
        matched_legacy = False
        for leg_key in legacy_keys:
            if len(leg_key) < 32:
                continue
            old_derived = derive_provenance_key(leg_key, prov_enum)
            old_sig = base64.b64encode(
                hmac.new(old_derived, canonical_bytes, hashlib.sha256).digest()
            ).decode("ascii")
            if hmac.compare_digest(stored_sig, old_sig):
                matched_legacy = True
                break

        if not matched_legacy:
            report.tampered_skipped_count += 1
            report.errors.append(
                f"Memory #{mid} (entry {entry_id[:8]}): "
                "signature does not match active key or any known legacy fallback"
            )
            continue

        # Valid legacy row: prepare new signature and updated payload JSON
        raw_dict["signature"] = new_sig
        new_payload_json = json.dumps(
            raw_dict,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        updates_to_apply.append((new_sig, new_payload_json, entry_id, mid))
        quarantine_ids_to_clear.append(mid)

    # Database backup prior to writes
    if not dry_run and updates_to_apply and create_backup:
        try:
            db_path = Path(db.db_path)
            if db_path.exists():
                now_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
                bak_path = db_path.parent / f"{db_path.name}.bak.{now_str}"
                shutil.copy2(db_path, bak_path)
                report.backup_path = str(bak_path)
                logger.info("memory_db_backup_created", path=report.backup_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("memory_db_backup_failed", error=str(exc))
            report.errors.append(f"Backup failed: {exc}")
            return report

    # Apply database mutations atomically if not dry run
    if not dry_run and (updates_to_apply or quarantine_ids_to_clear):
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

            if target_entry_id is None:
                now_iso = datetime.now(UTC).isoformat()
                writer.execute(
                    """
                    INSERT OR REPLACE INTO migration_metadata (key, value, updated_at)
                    VALUES ('keys_migrated', '1', ?)
                    """,
                    (now_iso,),
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
        lisp_held=report.lisp_assertions_held_count,
        quarantine_cleared=report.quarantine_cleared_count,
        dry_run=dry_run,
    )

    return report
