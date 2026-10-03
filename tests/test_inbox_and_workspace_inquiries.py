"""
Project Lucca - Inbox Inspection, Batch Handoff, and Workspace Grounding Tests
Validates:
1. list_dir(path='inbox') host-level directory inspection
2. inbox_handoff(filename='all') batch import and inspection
3. EpistemicSearchCascade non-abstention for workspace files and inbox inquiries
"""

import tempfile
from pathlib import Path

from lucca.core.cascade import BelnapValue, EpistemicSearchCascade
from lucca.sandbox.service import SandboxService


def test_inbox_and_workspace_inspection_and_cascade() -> None:
    with tempfile.TemporaryDirectory() as ws_tmp, tempfile.TemporaryDirectory() as in_tmp:
        ws_path = Path(ws_tmp)
        in_path = Path(in_tmp)

        # Seed files
        (ws_path / "notes.txt").write_text("workspace file content")
        (in_path / "doc1.pdf").write_text("doc1")
        (in_path / "doc2.csv").write_text("doc2")

        sandbox = SandboxService(
            workspace_root=ws_path,
            inbox_root=in_path,
            use_direct_fallback=True,
        )

        # 1. list_dir for inbox
        res_inbox = sandbox.execute_tool("call-1", "list_dir", {"path": "inbox"})
        assert res_inbox.ok
        assert res_inbox.exit_code == 0
        assert "doc1.pdf" in str(res_inbox.content)
        assert "doc2.csv" in str(res_inbox.content)

        # 2. list_dir with rel_path='inbox'
        res_rel = sandbox.execute_tool("call-2", "list_dir", {"rel_path": "inbox"})
        assert res_rel.ok
        assert "doc1.pdf" in str(res_rel.content)

        # 3. inbox_handoff inspection mode
        res_inspect = sandbox.execute_tool(
            "call-3", "inbox_handoff", {"filename": "list"}, confirmed=True
        )
        assert res_inspect.ok
        assert "doc1.pdf" in str(res_inspect.content)
        assert "doc2.csv" in str(res_inspect.content)
        assert (in_path / "doc1.pdf").exists()

        # 4. Epistemic cascade: general workspace inquiries
        cascade = EpistemicSearchCascade(sandbox=sandbox)
        res_ws = cascade.query("Do you have any files at all in your workspace?")
        assert res_ws.belnap_status == BelnapValue.TRUE
        assert res_ws.calibrated_refusal is None
        assert "notes.txt" in res_ws.synthesized_context

        # 5. Epistemic cascade: inbox inquiries
        res_inbox_q = cascade.query("Do you see the document I just put in your inbox?")
        assert res_inbox_q.belnap_status == BelnapValue.TRUE
        assert res_inbox_q.calibrated_refusal is None
        assert "doc1.pdf" in res_inbox_q.synthesized_context

        # 6. inbox_handoff batch import
        res_batch = sandbox.execute_tool(
            "call-4", "inbox_handoff", {"filename": "all"}, confirmed=True
        )
        assert res_batch.ok
        assert (ws_path / "doc1.pdf").exists()
        assert (ws_path / "doc2.csv").exists()
        assert not (in_path / "doc1.pdf").exists()
        assert not (in_path / "doc2.csv").exists()
