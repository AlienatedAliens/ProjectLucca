"""Collect live-web ResearchTool/Scrapling corpus (`web_evidentiary_burden_real_v2`, N=64) for WO-46.

Verifies `logs/test_reports/wo46/real_web_v2_prereg_lock.json` before running any query, enforces
zero query overlap against `web_evidentiary_burden_real_v1.jsonl` and `web_evidentiary_burden_360.jsonl`,
executes all 64 queries against the live web via `lucca.sandbox.research_tool.research_topic(..., include_raw_html=True)`,
archives gzipped raw HTML pages with SHA-256 manifest under `data/benchmarks/web_real_v2_archive/`,
writes `data/benchmarks/web_evidentiary_burden_real_v2.jsonl`, and prepares anonymized blinded rater
inputs (`logs/test_reports/wo46/real_web_v2_blinded_for_raters.jsonl`).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from lucca.sandbox.research_tool import research_topic

REPO = Path(__file__).resolve().parents[2]
LOCK_PATH = REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_prereg_lock.json"
QUERIES_PATH = REPO / "scripts" / "wo46" / "wo46_queries_64.json"
V1_CORPUS_PATH = REPO / "data" / "benchmarks" / "web_evidentiary_burden_real_v1.jsonl"
WEB360_PATH = REPO / "data" / "benchmarks" / "web_evidentiary_burden_360.jsonl"
ARCHIVE_DIR = REPO / "data" / "benchmarks" / "web_real_v2_archive"
MANIFEST_PATH = ARCHIVE_DIR / "manifest_sha256.json"
CORPUS_PATH = REPO / "data" / "benchmarks" / "web_evidentiary_burden_real_v2.jsonl"
BLIND_INPUT_PATH = (
    REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_blinded_for_raters.jsonl"
)
BLIND_MAP_PATH = REPO / "logs" / "test_reports" / "wo46" / "real_web_v2_blind_id_map.json"


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _norm_q(q: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", q.lower()))


def _verify_lock_and_disjointness(queries: list[dict[str, object]]) -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    for rel, expected in lock["locked_files_sha256"].items():
        actual = _sha256_file(REPO / rel)
        if actual != expected:
            raise RuntimeError(f"WO-46 lock hash mismatch on {rel}: {actual} != {expected}")

    prior_qs: set[str] = set()
    for p in (V1_CORPUS_PATH, WEB360_PATH):
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    prior_qs.add(_norm_q(str(json.loads(line)["query"])))

    seen_new: set[str] = set()
    for qobj in queries:
        nq = _norm_q(str(qobj["query"]))
        if nq in prior_qs:
            raise RuntimeError(f"Query overlap with v1/WEB360 detected: {qobj['query']}")
        if nq in seen_new:
            raise RuntimeError(f"Duplicate v2 query detected: {qobj['query']}")
        seen_new.add(nq)


def main() -> None:
    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    assert len(queries) == 64, f"Expected 64 queries, got {len(queries)}"
    _verify_lock_and_disjointness(queries)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    corpus_rows: list[dict[str, object]] = []
    manifest_entries: list[dict[str, object]] = []

    for idx_q, qobj in enumerate(queries, 1):
        qid = str(qobj["query_id"])
        qtext = str(qobj["query"])
        t0 = time.perf_counter()
        meta, _dossier = research_topic(query=qtext, max_sources=4, include_raw_html=True)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 1)

        raw_sources = meta.get("sources", [])
        clean_sources: list[dict[str, object]] = []
        if isinstance(raw_sources, list):
            for s_idx, src in enumerate(raw_sources, 1):
                if not isinstance(src, dict):
                    continue
                url = str(src.get("url", "") or "")
                final_url = str(src.get("final_url", "") or url)
                title = str(src.get("title", "") or "")
                snippet = str(src.get("snippet", "") or "")
                preview = str(src.get("content_preview", "") or "")
                status = int(src.get("fetch_status", 0) or 0)
                tier = str(src.get("fetch_tier", "") or "")
                raw_html_str = str(src.get("raw_html", "") or "")

                archive_rel = ""
                raw_sha = ""
                gz_sha = ""
                raw_bytes_len = 0
                if raw_html_str:
                    raw_bytes = raw_html_str.encode("utf-8", errors="replace")
                    raw_bytes_len = len(raw_bytes)
                    raw_sha = _sha256_bytes(raw_bytes)
                    gz_name = f"{qid}_src{s_idx}.html.gz"
                    gz_path = ARCHIVE_DIR / gz_name
                    gz_bytes = gzip.compress(raw_bytes, compresslevel=9, mtime=0)
                    gz_path.write_bytes(gz_bytes)
                    gz_sha = _sha256_bytes(gz_bytes)
                    archive_rel = f"data/benchmarks/web_real_v2_archive/{gz_name}"
                    manifest_entries.append(
                        {
                            "query_id": qid,
                            "source_index": s_idx,
                            "url": url,
                            "final_url": final_url,
                            "fetch_status": status,
                            "fetch_tier": tier,
                            "archive_path": archive_rel,
                            "raw_html_bytes": raw_bytes_len,
                            "raw_html_sha256": raw_sha,
                            "archive_gz_sha256": gz_sha,
                        }
                    )

                clean_sources.append(
                    {
                        "index": s_idx,
                        "url": url,
                        "final_url": final_url,
                        "title": title,
                        "snippet": snippet,
                        "content_preview": preview,
                        "fetch_status": status,
                        "fetch_tier": tier,
                        "archive_path": archive_rel,
                        "raw_html_sha256": raw_sha,
                        "raw_html_bytes": raw_bytes_len,
                    }
                )

        corpus_rows.append(
            {
                "query_id": qid,
                "nominal_stratum": qobj["nominal_stratum"],
                "query": qtext,
                "retrieved_at_utc": datetime.now(UTC).isoformat(),
                "retrieval_elapsed_ms": elapsed_ms,
                "ok": bool(meta.get("ok", False)),
                "sources_count": len(clean_sources),
                "search_results": clean_sources,
            }
        )
        print(
            f"[{idx_q:02d}/64] {qid}: {len(clean_sources)} sources, "
            f"archived={sum(1 for s in clean_sources if s['archive_path'])}, {elapsed_ms}ms",
            flush=True,
        )
        time.sleep(0.35)

    with CORPUS_PATH.open("w", encoding="utf-8", newline="\n") as f:
        for row in corpus_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest_doc = {
        "dataset": "web_evidentiary_burden_real_v2",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "queries_count": len(corpus_rows),
        "archived_pages_count": len(manifest_entries),
        "corpus_sha256": _sha256_file(CORPUS_PATH),
        "pages": manifest_entries,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest_doc, indent=2) + "\n", encoding="utf-8")

    rng = random.Random(20261114)
    shuffled = list(corpus_rows)
    rng.shuffle(shuffled)

    blind_rows: list[dict[str, object]] = []
    blind_map: dict[str, str] = {}
    for b_idx, row in enumerate(shuffled, 1):
        bid = f"WO46_BLIND_{b_idx:03d}"
        qid = str(row["query_id"])
        blind_map[bid] = qid
        srcs_out = []
        for s in row["search_results"]:  # type: ignore[attr-defined]
            srcs_out.append(
                {
                    "index": s["index"],
                    "url": s["url"],
                    "title": s["title"],
                    "snippet": s["snippet"],
                    "extracted_preview": str(s["content_preview"])[:1400],
                }
            )
        blind_rows.append(
            {
                "blind_id": bid,
                "query": row["query"],
                "retrieved_sources": srcs_out,
            }
        )

    BLIND_INPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with BLIND_INPUT_PATH.open("w", encoding="utf-8", newline="\n") as f:
        for brow in blind_rows:
            f.write(json.dumps(brow, ensure_ascii=False) + "\n")

    BLIND_MAP_PATH.write_text(json.dumps(blind_map, indent=2) + "\n", encoding="utf-8")
    print(
        f"Done: Corpus={CORPUS_PATH} (sha256={_sha256_file(CORPUS_PATH)}), "
        f"archived_pages={len(manifest_entries)}"
    )


if __name__ == "__main__":
    main()
