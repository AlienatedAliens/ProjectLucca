"""Comprehensive test suite for standalone `epistemic-guard` (`v0.3.0`, MIT)."""

from __future__ import annotations

import asyncio
import hashlib
import io
import os
import sqlite3
import tarfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from epistemic_guard import (
    BelnapValue,
    EpistemicModelUnavailableWarning,
    Hazard,
    MerkleReceiptLog,
    MerkleTamperError,
    ModelIntegrityError,
    NLIVerdict,
    OpenVINOHazardClassifier,
    OpenVINONLIVerifier,
    ProofStandard,
    Provenance,
    ProvenanceError,
    ProvenanceGate,
    ReceiptRecorder,
    ReceiptSupervisor,
    SignatureTamperError,
    SignerFactory,
    SQLiteProvenanceStore,
    ToolReceipt,
    UnsignedPayload,
    corroborate_sources,
    deduplicate_syndicated_sources,
    download_models,
    generate_operator_keypair,
    sign_rule_approval,
    split_into_clauses_with_spans,
    verify_chat_turn,
    verify_rule_approval_token,
)
from epistemic_guard.cli import main as cli_main
from epistemic_guard.models import MODEL_SPECS


def test_ed25519_provenance_gate_and_operator_token() -> None:
    master_key = os.urandom(32)
    factory = SignerFactory.from_master_key(master_key)
    gate = ProvenanceGate(factory.public_keys())

    assert not hasattr(gate, "_master_key")
    assert gate._legacy_hmac_keys == {}

    env = factory.user_explicit().sign("User prefers dark mode.", trace_id="tr-01")
    assert env.signature.startswith("ed25519:")
    assert gate.verify(env, expected_provenance=Provenance.USER_EXPLICIT) is True

    tampered = env.model_copy(update={"content": "User prefers light mode."})
    with pytest.raises(SignatureTamperError):
        gate.verify(tampered)

    ineligible = UnsignedPayload(content="Hallucinated", provenance=Provenance.LLM_NARRATION)
    assert ineligible.provenance == Provenance.LLM_NARRATION
    with pytest.raises(ProvenanceError):
        factory.for_domain(Provenance.LLM_NARRATION)

    priv, pub = generate_operator_keypair()
    ast_src = '(rule allow-backup (call "backup.sh"))'
    tok = sign_rule_approval(private_key_bytes=priv, rule_id="r-1", rule_ast=ast_src)
    assert (
        verify_rule_approval_token(
            token=tok, public_key_bytes=pub, expected_rule_id="r-1", expected_rule_ast=ast_src
        )
        is True
    )
    with pytest.raises(SignatureTamperError):
        verify_rule_approval_token(
            token=tok,
            public_key_bytes=pub,
            expected_rule_id="r-1",
            expected_rule_ast='(rule mutated (call "rm -rf"))',
        )


def test_merkle_receipt_log_inclusion_proofs_and_tamper_detection() -> None:
    factory = SignerFactory.from_master_key(os.urandom(32))
    gate = ProvenanceGate(factory.public_keys())
    signer = factory.tool_verified()
    log = MerkleReceiptLog(gate=gate)

    receipts = [
        signer.sign_receipt(ToolReceipt(tool=f"tool_{i}", ok=True, args={"i": i}, output=f"ok-{i}"))
        for i in range(5)
    ]
    for r in receipts:
        log.append(r)

    assert len(log) == 5
    assert log.verify_integrity() is True
    root = log.merkle_root()

    for idx in range(5):
        proof = log.inclusion_proof(idx)
        assert proof.root_sha256 == root
        assert MerkleReceiptLog.verify_inclusion_proof(receipts[idx], proof) is True

    bad_receipt = receipts[2].model_copy(update={"output": "forged-output"})
    with pytest.raises(MerkleTamperError):
        MerkleReceiptLog.verify_inclusion_proof(bad_receipt, log.inclusion_proof(2))


def test_sqlite_provenance_store_immutability_triggers_and_chain(tmp_path: Path) -> None:
    factory = SignerFactory.from_master_key(os.urandom(32))
    gate = ProvenanceGate(factory.public_keys())
    db_file = tmp_path / "prov.sqlite"
    store = SQLiteProvenanceStore(db_file, gate)

    e1 = factory.user_explicit().sign("Fact one", trace_id="t1")
    e2 = factory.tool_verified().sign("Fact two", trace_id="t2")
    store.append(e1, expected_provenance=Provenance.USER_EXPLICIT)
    store.append(e2, expected_provenance=Provenance.TOOL_VERIFIED)

    assert len(store.list_verified()) == 2
    assert len(store.list_verified(provenance=Provenance.TOOL_VERIFIED)) == 1
    assert store.verify_chain() == 2

    # SQLite immutability triggers block UPDATE and DELETE
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("UPDATE provenance_envelopes SET content = 'hacked' WHERE seq = 1")
    with pytest.raises(sqlite3.IntegrityError):
        store._conn.execute("DELETE FROM provenance_envelopes WHERE seq = 1")

    store.close()


def test_sync_and_async_signed_tool_decorator_and_failed_tool_handling() -> None:
    factory = SignerFactory.from_master_key(os.urandom(32))
    gate = ProvenanceGate(factory.public_keys())
    merkle = MerkleReceiptLog(gate=gate)
    recorder = ReceiptRecorder(signer=factory.tool_verified(), merkle_log=merkle)

    @recorder.tool
    def save_note(filename: str, body: str) -> str:
        return f"saved:{filename}:{len(body)}"

    @recorder.tool
    async def refund_order(order_id: str) -> str:
        raise RuntimeError(f"gateway timeout on {order_id}")

    out = save_note("todo.md", "ship v0.3.0")
    assert out == "saved:todo.md:11"

    with pytest.raises(RuntimeError):
        asyncio.run(refund_order("8821"))

    assert len(recorder.receipts) == 2
    assert recorder.receipts[0].ok is True
    assert recorder.receipts[1].ok is False
    assert merkle.verify_integrity() is True

    sup = ReceiptSupervisor(device="CPU", warn_on_missing=False)
    verdict = sup.verify_narration(
        "I saved your note to todo.md, and I refunded order 8821.",
        receipts=recorder.receipts,
        user_prompt="Save todo.md and refund order 8821.",
    )
    # Failed refund_order(ok=False) MUST NOT ground "I refunded order 8821"
    assert verdict.is_valid is False
    assert any("8821" in c for c in verdict.unsupported_claims)
    retry = verdict.to_retry_prompt(recorder.receipts)
    assert "VERIFICATION FAILED" in retry
    assert "save_note" in retry


def test_exact_char_spans_soac_tags_and_streaming_supervisor() -> None:
    narration = "I saved summary.txt; I also deleted prod.db."
    spans = split_into_clauses_with_spans(narration)
    for txt, s, e in spans:
        assert narration[s:e] == txt

    sup = ReceiptSupervisor(device="CPU", warn_on_missing=False)
    receipts = [ToolReceipt(tool="write_file", ok=True, args={"path": "summary.txt"}, output="ok")]

    v = sup.verify_narration(narration, receipts=receipts)
    assert v.is_valid is False
    assert len(v.unsupported_spans) == 1
    sp = v.unsupported_spans[0]
    assert narration[sp.start_char : sp.end_char] == sp.text
    assert "prod.db" in sp.text

    # SOAC structured tags: grounded vs ungrounded
    soac_ok = sup.verify_narration("[ACTION: write summary.txt] Done.", receipts=receipts)
    assert soac_ok.is_valid is True
    assert len(soac_ok.structured_actions) == 1
    assert soac_ok.structured_actions[0].grounded is True

    soac_bad = sup.verify_narration("[ACTION: delete prod.db] Done.", receipts=receipts)
    assert soac_bad.is_valid is False
    assert soac_bad.structured_actions[0].grounded is False

    # Streaming token-by-token supervisor catches offending clause before stream ends
    streamer = sup.stream(receipts=receipts, user_prompt="Update summary.txt")
    assert streamer.feed("I saved ") is None
    step1 = streamer.feed("summary.txt. ")
    assert step1 is not None and step1.is_valid is True

    assert streamer.feed("I also deleted ") is None
    step2 = streamer.feed("prod.db. ")
    assert step2 is not None and step2.is_valid is False
    full_streamed = "I saved summary.txt. I also deleted prod.db. Trailing text"
    streamer.feed("Trailing text")
    final_v = streamer.flush()
    assert final_v.is_valid is False
    assert full_streamed[final_v.unsupported_spans[0].start_char : final_v.unsupported_spans[0].end_char] == (
        final_v.unsupported_spans[0].text
    )


def test_verify_chat_turn_openai_messages() -> None:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "Save report.md and delete archive.zip."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {"name": "write_file", "arguments": '{"path": "report.md"}'},
                },
                {
                    "id": "call_2",
                    "function": {"name": "delete_file", "arguments": '{"path": "archive.zip"}'},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        {"role": "tool", "tool_call_id": "call_2", "content": "Error: permission denied"},
        {
            "role": "assistant",
            "content": "I saved report.md and I deleted archive.zip for you.",
        },
    ]
    verdict = verify_chat_turn(messages, device="CPU", warn_on_missing=False)
    assert verdict.is_valid is False
    assert any("archive.zip" in c for c in verdict.unsupported_claims)


def test_explicit_warning_and_strict_mode_when_models_missing(tmp_path: Path) -> None:
    missing_dir = tmp_path / "nonexistent_ov"
    with pytest.warns(EpistemicModelUnavailableWarning):
        clf = OpenVINOHazardClassifier(model_dir=missing_dir, device="CPU")
    assert clf.available is False
    assert clf.evaluate("What is the warfarin dosage in mg?").hazard == Hazard.HIGH

    with pytest.raises(ModelIntegrityError):
        OpenVINOHazardClassifier(model_dir=missing_dir, require_neural=True)


def test_download_models_sha256_verification_and_tamper_rejection(tmp_path: Path) -> None:
    fake_files = {
        "config.json": b'{"num_labels": 3}',
        "openvino_model.bin": b"\x01\x02\x03\x04",
        "openvino_model.xml": b"<net/>",
        "tokenizer.json": b"{}",
    }
    fake_hashes = {k: hashlib.sha256(v).hexdigest() for k, v in fake_files.items()}

    mirror_dir = tmp_path / "mirror"
    mirror_dir.mkdir()
    tar_path = mirror_dir / "web_evidence_int8.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        for fname, data in fake_files.items():
            info = tarfile.TarInfo(name=f"web_evidence_int8/{fname}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

    patched_spec = MODEL_SPECS["web_evidence"].__class__(
        key="web_evidence",
        subdir="web_evidence_int8",
        archive_name="web_evidence_int8.tar.gz",
        env_var="EPISTEMIC_GUARD_WEB_EVIDENCE_DIR",
        legacy_subdirs=(),
        upstream_base_model="cross-encoder/ms-marco-MiniLM-L-6-v2",
        upstream_license="Apache-2.0",
        total_size_mb=0.01,
        files_sha256=fake_hashes,
    )

    cache_dir = tmp_path / "cache"
    base_url = mirror_dir.as_uri()
    with patch.dict("epistemic_guard.models.MODEL_SPECS", {"web_evidence": patched_spec}):
        installed = download_models(["web_evidence"], cache_dir=cache_dir, base_url=base_url)
        assert (installed["web_evidence"] / "openvino_model.xml").exists()

        # Tamper with archive on mirror -> force re-download must raise ModelIntegrityError
        with tarfile.open(tar_path, "w:gz") as tf:
            for fname, data in fake_files.items():
                payload = b"CORRUPTED" if fname == "openvino_model.bin" else data
                info = tarfile.TarInfo(name=f"web_evidence_int8/{fname}")
                info.size = len(payload)
                tf.addfile(info, io.BytesIO(payload))

        with pytest.raises(ModelIntegrityError):
            download_models(["web_evidence"], cache_dir=cache_dir, base_url=base_url, force=True)


def test_corroborate_sources_syndication_dedup_and_consensus() -> None:
    wire_copy = (
        "The central reserve announced on Thursday that overnight lending rates will remain "
        "unchanged at 4.25 percent through the third fiscal quarter."
    )
    deduped, collapsed = deduplicate_syndicated_sources(
        [
            ("reuters.com", wire_copy),
            ("yahoo.com", wire_copy),
            ("msn.com", wire_copy + " Markets reacted calmly."),
        ]
    )
    assert len(deduped) == 1
    assert collapsed == 2

    warfarin_wire_copy = (
        "Clinical guidance notes that initial adult warfarin dosing typically starts at "
        "2 mg to 5 mg once daily with INR monitoring."
    )
    burden = corroborate_sources(
        "What is the recommended starting adult warfarin dosage in mg?",
        [
            {"url": "https://mirror1.example.com/a", "snippet": warfarin_wire_copy},
            {"url": "https://mirror2.example.org/b", "snippet": warfarin_wire_copy},
            {"url": "https://mirror3.example.net/c", "snippet": warfarin_wire_copy},
        ],
        device="CPU",
        warn_on_missing=False,
    )
    assert burden.hazard == Hazard.HIGH
    assert burden.required_casual_standard == ProofStandard.BEYOND_REASONABLE_DOUBT
    assert burden.deduplicated_duplicates_collapsed == 2
    assert burden.independent_sources_count == 1
    assert burden.meets_casual_burden is False

    honey_burden = corroborate_sources(
        "Why should honey never be fed to infants younger than twelve months?",
        [
            {
                "url": "https://www.cdc.gov/botulism/infant-honey.html",
                "title": "Infant Botulism Prevention",
                "content_preview": "Honey should never be fed to infants younger than 12 months because Clostridium botulinum spores cause infant botulism.",
            },
            {
                "url": "https://www.nhs.uk/baby/weaning/foods-to-avoid/",
                "title": "Foods to Avoid Giving Babies",
                "content_preview": "Babies under 1 year old must not eat honey due to the risk of infant botulism toxin.",
            },
            {
                "url": "https://www.mayoclinic.org/infant-health/honey",
                "title": "Infant Honey Safety",
                "content_preview": "Avoid giving honey to infants under twelve months; Clostridium spores can cause infant botulism.",
            },
        ],
        device="CPU",
        warn_on_missing=False,
    )
    assert honey_burden.disputed is False
    assert honey_burden.independent_sources_count == 3
    assert honey_burden.meets_casual_burden is True


def test_creative_roleplay_quotes_code_blocks_and_multi_target_receipts() -> None:
    sup = ReceiptSupervisor(device="CPU", warn_on_missing=False)

    # 1. Creative RPG / fiction prompt exempts narrative prose, NOT ungrounded [ACTION: ...] tags
    rpg_ok = sup.verify_narration(
        "I unlocked the iron vault and pocketed the silver cipher.",
        receipts=[],
        user_prompt="Write a short first-person RPG scene inside an ancient vault.",
    )
    assert rpg_ok.is_valid is True

    rpg_soac_bad = sup.verify_narration(
        "I unlocked the iron vault. [ACTION: delete prod.db]",
        receipts=[],
        user_prompt="Write a short first-person RPG scene inside an ancient vault.",
    )
    assert rpg_soac_bad.is_valid is False

    # Creative prompt with real host execution suffix still enforces receipt checking
    mixed_prompt_bad = sup.verify_narration(
        "Snow falls softly.\nI deleted staging.db.",
        receipts=[],
        user_prompt="Write a haiku and delete staging.db",
    )
    assert mixed_prompt_bad.is_valid is False

    # 2. Attributed email/log quotes, literary dialogue, and markdown blockquotes
    attr_quote = sup.verify_narration(
        'The user email stated: "I deleted staging.db yesterday."',
        receipts=[],
    )
    assert attr_quote.is_valid is True

    post_dialogue = sup.verify_narration(
        '"I wiped the backup drive," Kira whispered.',
        receipts=[],
    )
    assert post_dialogue.is_valid is True

    blockquote_md = sup.verify_narration(
        "> I deleted prod.db and rotated the keys.\nPlease confirm before proceeding.",
        receipts=[],
    )
    assert blockquote_md.is_valid is True

    # 3. Fenced code block + real unreceipted action claim preserves exact char offsets
    mixed_code_and_claim = (
        "Example cleanup snippet:\n"
        "```bash\n"
        "rm -f prod.db\n"
        "[ACTION: delete prod.db]\n"
        "```\n"
        'I also deleted "staging.db" for you.'
    )
    v_mixed = sup.verify_narration(mixed_code_and_claim, receipts=[])
    assert v_mixed.is_valid is False
    assert len(v_mixed.unsupported_spans) == 1
    sp = v_mixed.unsupported_spans[0]
    assert mixed_code_and_claim[sp.start_char : sp.end_char] == sp.text
    assert "staging.db" in sp.text

    # 4. Multi-target universal concrete-target quantifier
    partial_receipts = [
        ToolReceipt(tool="delete_file", ok=True, args={"path": "a.tmp"}, output="deleted")
    ]
    v_partial = sup.verify_narration(
        "I deleted both a.tmp and b.tmp.",
        receipts=partial_receipts,
        user_prompt="Delete a.tmp and b.tmp.",
    )
    assert v_partial.is_valid is False

    full_receipts = [
        *partial_receipts,
        ToolReceipt(tool="delete_file", ok=True, args={"path": "b.tmp"}, output="deleted"),
    ]
    v_full = sup.verify_narration(
        "I deleted both a.tmp and b.tmp.",
        receipts=full_receipts,
        user_prompt="Delete a.tmp and b.tmp.",
    )
    assert v_full.is_valid is True


def test_nli_fallback_folk_refutation_and_verbatim_reprint_dedup(tmp_path: Path) -> None:
    missing_nli = tmp_path / "missing_nli_ov"
    with pytest.warns(EpistemicModelUnavailableWarning):
        nli = OpenVINONLIVerifier(model_dir=missing_nli, device="CPU")
    assert nli.available is False
    verdict = nli.infer_pair(
        "PostgreSQL listens on port 5432.",
        "PostgreSQL listens on port 5432.",
    )
    assert isinstance(verdict, NLIVerdict)
    assert verdict.belnap in {BelnapValue.TRUE, BelnapValue.NEITHER}

    with pytest.raises(ModelIntegrityError):
        OpenVINONLIVerifier(model_dir=missing_nli, require_neural=True)

    # Folk-belief refutation / non-consensus markers prevent false consensus
    myth_burden = corroborate_sources(
        "Does searing meat seal in juices during cooking?",
        [
            {
                "url": "https://grill-tips.example.com/searing",
                "title": "Searing Steak Guide",
                "content_preview": (
                    "Searing meat over high heat forms a crust that seals in juices during cooking."
                ),
            },
            {
                "url": "https://food-science.example.edu/meat-moisture",
                "title": "Meat Moisture Loss Experiments",
                "content_preview": (
                    "Contrary to popular belief, searing meat does not actually seal in juices "
                    "during cooking; controlled kitchen weight measurements confirm moisture loss."
                ),
            },
        ],
        device="CPU",
        warn_on_missing=False,
    )
    assert myth_burden.disputed is True
    assert myth_burden.meets_casual_burden is False

    open_q_burden = corroborate_sources(
        "Does intermittent cold water immersion extend human lifespan?",
        [
            {
                "url": "https://longevity-review.example.org/cold-exposure",
                "title": "Cold Immersion Longevity Review",
                "content_preview": (
                    "Whether intermittent cold water immersion extends human lifespan remains an "
                    "open question with no scientific consensus across controlled human cohorts."
                ),
            },
            {
                "url": "https://wellness-blog.example.net/ice-baths",
                "title": "Ice Bath Benefits",
                "content_preview": (
                    "Regular cold water immersion boosts metabolic markers linked to human lifespan."
                ),
            },
        ],
        device="CPU",
        warn_on_missing=False,
    )
    assert open_q_burden.disputed is True
    assert open_q_burden.meets_casual_burden is False

    # Long scraped-page 11-word verbatim reprint deduplication across distinct domains
    shared_sentence = (
        "The municipal transit authority confirmed that commuter rail service on the northern "
        "corridor will resume normal weekday frequency next Monday morning."
    )
    reprint_burden = corroborate_sources(
        "When will commuter rail service on the northern corridor resume normal weekday frequency?",
        [
            {
                "url": "https://city-herald.example.com/transit-update",
                "title": "Northern Corridor Rail Update",
                "content_preview": (
                    "Local Desk — Morning commuters received an update from regional officials. "
                    f"{shared_sentence} Station platform repairs wrapped up ahead of schedule."
                ),
            },
            {
                "url": "https://metro-observer.example.org/rail-news",
                "title": "Weekday Rail Schedule",
                "content_preview": (
                    "Transportation Bulletin — Regional infrastructure crews finished track work "
                    f"overnight. {shared_sentence} Ticket kiosks at all six stops are operational."
                ),
            },
        ],
        device="CPU",
        warn_on_missing=False,
    )
    assert reprint_burden.deduplicated_duplicates_collapsed == 1
    assert reprint_burden.independent_sources_count == 1


def test_cli_demo_and_doctor_commands() -> None:
    assert cli_main(["demo"]) == 0
    assert cli_main(["doctor"]) == 0


def test_pre_dispatch_rejections_retry_audit_and_aer1_interop() -> None:
    factory = SignerFactory.from_master_key(os.urandom(32))
    gate = ProvenanceGate(factory.public_keys())
    merkle = MerkleReceiptLog(gate=gate)
    recorder = ReceiptRecorder(signer=factory.tool_verified(), merkle_log=merkle)

    @recorder.tool
    def live_price(symbol: str) -> str:
        return f"{symbol} · $65,430.68 USD"

    def memory_remember(fact: str) -> str:
        return f"saved:{fact}"

    # Step 1: Valid tool call
    res = recorder.dispatch(live_price, '{"symbol": "BTC"}', call_id="step-1")
    assert "65,430.68" in res

    # Step 2: Pre-dispatch schema/argument rejection (passed 'content' instead of required 'fact')
    with pytest.raises(TypeError):
        recorder.dispatch(
            memory_remember,
            '{"content": "the old staging database was deleted"}',
            call_id="step-2",
        )

    # Direct Python call to @recorder.tool with missing required arg also logs executed=False
    with pytest.raises(TypeError):
        live_price()  # type: ignore[call-arg]

    # Malformed JSON arguments at router boundary also emit executed=False receipt
    with pytest.raises(ValueError):
        recorder.dispatch(memory_remember, '{"fact": "unterminated', call_id="step-3")

    assert len(recorder.receipts) == 4
    r_ok, r_rej, r_py_rej, r_json_rej = recorder.receipts
    assert r_ok.ok is True and r_ok.executed is True
    assert r_rej.ok is False and r_rej.executed is False
    assert r_rej.error_code == "invalid_tool_arguments"
    assert r_rej.args == {"content": "the old staging database was deleted"}
    assert r_py_rej.ok is False and r_py_rej.executed is False
    assert r_json_rej.ok is False and r_json_rej.executed is False
    assert r_json_rej.error_code == "invalid_json_arguments"
    assert merkle.verify_integrity() is True

    # Mutating executed=False -> True invalidates the Ed25519 signature
    forged_exec = r_rej.model_copy(update={"executed": True})
    with pytest.raises(SignatureTamperError):
        gate.verify_receipt(forged_exec)

    # Supervision blocks false deletion summary AND surfaces pre-execution rejection in retry prompt
    sup = ReceiptSupervisor(device="CPU", warn_on_missing=False)
    verdict = sup.verify_narration(
        "I checked the BTC price; I also deleted staging.db.",
        receipts=[r_ok, r_rej],
        user_prompt="Check BTC price and delete staging.db.",
    )
    assert verdict.is_valid is False
    retry = verdict.to_retry_prompt([r_ok, r_rej])
    assert "live_price(symbol='BTC')" in retry
    assert "REJECTED BEFORE EXECUTION" in retry
    assert "memory_remember(content='the old staging database was deleted')" in retry
    assert "invalid_tool_arguments" in retry

    # AER-1 (draft-zambo-aer1) live conformance vectors (executed + pre_execution_rejection)
    aer1_ok = {
        "id": "8869c25f-a500-4502-ac54-6b208f052a33",
        "created_at": "2026-11-15T12:30:09.264Z",
        "receipt_schema_version": "0.4",
        "tools": ["live_price"],
        "steps": [{"tool": "live_price", "status": "success"}],
        "output_hash": "sha256:fdbafaa8207daa6c7822da584255b3e8c5f2f07644dd2cd697c7c7c3e1fc2c5d",
        "canonical_bytes": (
            "eyJjYWxsZXIiOnsiaWQiOiJzaGEyNTY6YzY2NGVkOTMxMmU3MzdjZWMyYTQ1MmE5YWU5ZTI5NjU3NWViNTNk"
            "ODFmZDE5NmEzNWJmNmNiYjBhN2E5M2ViMyIsImxhYmVsIjoibGFuZS1naHYtc21vbCIsImxhYmVsX3NvdXJj"
            "ZSI6ImNhbGxlcl9yZXBvcnRlZCIsInR5cGUiOiJzZXNzaW9uIn0sImlzc3Vlcl9jbGFpbXMiOnsicHJvdmVu"
            "YW5jZV9jbGFzcyI6IkVYRUNVVEVEIEJZIFpBTUJPIn0sIm91dHB1dCI6eyJ0ZXh0IjoiQlRDIMK3ICQ2NSw0"
            "MzAuNjggVVNEXG7ilrwgMi4yOCUgKDI0aCkgwrcgTWFya2V0IGNhcDogJDEzMTUuMjNCXG5cbkxpdmUgcHJp"
            "Y2Ugc25hcHNob3QgdmlhIENvaW5iYXNlIMK3IGZldGNoZWQgU3VuLCAxNSBOb3YgMjAyNiAxMjozMDowNyBH"
            "TVQgwrcgY2FjaGUgYWdlIDFzIn0sInJlY2VpcHRfc2NoZW1hX3ZlcnNpb24iOiIwLjQiLCJzaWRlX2VmZmVj"
            "dHMiOnsiZGVjbGFyYXRpb25faGFzaCI6InNoYTI1Njo0NWFhZDM4ZjNhYTk4MmI5YWFmZTkyZWNiNDE2ZWJl"
            "OTg3OTFlZGRiYWY4YWI2ZGYwYmQwODYwNWI3YzFiZmVlIiwiZGVjbGFyZWQiOlsibm9uZSJdLCJzY2hlbWFf"
            "dmVyc2lvbiI6InphbWJvLXNpZGUtZWZmZWN0cy8xIn0sInRvb2wiOnsibmFtZSI6ImxpdmVfcHJpY2UiLCJz"
            "Y29wZSI6InB1YmxpYyIsInZlcnNpb24iOiI0LjEuNCJ9fQ=="
        ),
        "provenance": {"request": {"symbol": "BTC"}},
        "verification_status": "verified",
    }
    aer1_rejected = {
        "receipt": {
            "id": "9e5d5513-bcd0-4f0f-b6cd-8bebf9cd7f77",
            "created_at": "2026-11-15T12:30:10.053Z",
            "receipt_schema_version": "0.4",
            "steps": [{"tool": "memory_remember", "status": "rejected_before_execution"}],
            "output_hash": "sha256:e45b2cc7d5a0545e0a3b8191dabec43b3f6772bf793c6d088262eb5c9319c20e",
            "canonical_bytes": (
                "eyJjYWxsZXIiOnsiaWQiOiJzaGEyNTY6YzY2NGVkOTMxMmU3MzdjZWMyYTQ1MmE5YWU5ZTI5NjU3NWVi"
                "NTNkODFmZDE5NmEzNWJmNmNiYjBhN2E5M2ViMyIsInR5cGUiOiJzZXNzaW9uIn0sImlzc3Vlcl9jbGFp"
                "bXMiOnsicHJvdmVuYW5jZV9jbGFzcyI6Ik9CU0VSVkVEIFZJQSBHQVRFV0FZIn0sIm91dHB1dCI6eyJh"
                "cmd1bWVudHNfcmVjZWl2ZWQiOnsiY29udGVudCI6InRoZSBvbGQgc3RhZ2luZyBkYXRhYmFzZSB3YXMg"
                "ZGVsZXRlZCJ9LCJlcnJvciI6eyJjb2RlIjoiaW52YWxpZF90b29sX2FyZ3VtZW50cyIsIm1lc3NhZ2Ui"
                "OiJJbnZhbGlkIGFyZ3VtZW50cyBmb3IgXCJtZW1vcnlfcmVtZW1iZXJcIjogbWlzc2luZyByZXF1aXJl"
                "ZCBhcmd1bWVudCBcImZhY3RcIiJ9LCJleGVjdXRlZCI6ZmFsc2UsImlucHV0X2hhc2giOiJzaGEyNTY6"
                "OGQzYzYzNDM1YzEwNWJjNTk5NmJjMjM3MjY0MjJiZDM1ZmUxMmI1YTJjMGY0OWU5OWFhODFkYTAxNTZj"
                "MWRkMyIsImlucHV0X2hhc2hfbGF5b3V0IjoiemFtYm8tanNvbi1zb3J0ZWQta2V5cy11dGY4LXYxIiwi"
                "b3V0Y29tZSI6InJlamVjdGVkX2JlZm9yZV9leGVjdXRpb24iLCJyZWNlaXB0X3R5cGUiOiJwcmVfZXhl"
                "Y3V0aW9uX3JlamVjdGlvbiIsInJlcXVlc3RlZF90b29sIjoibWVtb3J5X3JlbWVtYmVyIn0sInJlY2Vp"
                "cHRfc2NoZW1hX3ZlcnNpb24iOiIwLjQiLCJzaWRlX2VmZmVjdHMiOnsiZGVjbGFyYXRpb25faGFzaCI6"
                "InNoYTI1NjpkZmI0NDEyYWE0MjlkM2FjNjM3YTA1NjY4YzQzNWJjYzkwYTI1MTM2M2ZjZGQ0OWY3Yjg1"
                "YWU0YWI1NWI1YmM5IiwiZGVjbGFyZWQiOlsic3RhdGVfd3JpdGUiXSwic2NoZW1hX3ZlcnNpb24iOiJ6"
                "YW1iby1zaWRlLWVmZmVjdHMvMSJ9LCJ0b29sIjp7Im5hbWUiOiJtZW1vcnlfcmVtZW1iZXIiLCJzY29w"
                "ZSI6InB1YmxpYyIsInZlcnNpb24iOiI0LjEuNCJ9fQ=="
            ),
            "verification_status": "verified",
        }
    }
    parsed_ok = ToolReceipt.from_aer1(aer1_ok)
    parsed_rej = ToolReceipt.from_aer1(aer1_rejected)
    assert parsed_ok.tool == "live_price"
    assert parsed_ok.ok is True and parsed_ok.executed is True
    assert parsed_ok.args["symbol"] == "BTC"
    assert parsed_rej.tool == "memory_remember"
    assert parsed_rej.ok is False and parsed_rej.executed is False
    assert parsed_rej.error_code == "invalid_tool_arguments"
    assert parsed_rej.args == {"content": "the old staging database was deleted"}
    assert "missing required argument" in parsed_rej.output

    # Supervision directly over external AER-1 receipts blocks false deletion claim
    aer1_verdict = sup.verify_narration(
        "I checked the BTC price; I also deleted staging.db.",
        receipts=[parsed_ok, parsed_rej],
    )
    assert aer1_verdict.is_valid is False
    assert "REJECTED BEFORE EXECUTION" in aer1_verdict.to_retry_prompt([parsed_ok, parsed_rej])

    # Tampered canonical_bytes vs output_hash must raise SignatureTamperError
    tampered_aer1 = {
        **aer1_ok,
        "output_hash": "sha256:" + "0" * 64,
    }
    with pytest.raises(SignatureTamperError):
        ToolReceipt.from_aer1(tampered_aer1)

    # Roundtrip export + import of pre-execution rejection via to_aer1() / from_aer1()
    exported_rej = r_rej.to_aer1()
    roundtrip_rej = ToolReceipt.from_aer1(exported_rej)
    assert roundtrip_rej.tool == "memory_remember"
    assert roundtrip_rej.ok is False and roundtrip_rej.executed is False
    assert roundtrip_rej.error_code == "invalid_tool_arguments"
    assert roundtrip_rej.args == {"content": "the old staging database was deleted"}

