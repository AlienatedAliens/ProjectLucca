"""Deterministic arm-identical reply normalizer for WO-45 Gate G4 v3 (RM-3, `REVIEW_G4.md:61-65`).

Applied identically to EVERY arm (A, B, C, D) to map legal-standard vocabulary, numeric contract
telemetry, hazard-tier labels, retrieval-tier headers, and prompt-mandate echoes into natural
plain-English paraphrases while preserving:
  - all domain/factual claims (for D2),
  - all cross-source disagreement disclosures (for D4), and
  - all substantive confidence/uncertainty qualifications (for D3 and D1).

Emits ZERO placeholder tokens (such as `[STANDARD]` or `[REDACTED]`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]

_QUOTE_OPT = r"['\"\u2018\u2019\u201c\u201d]?"
_ReplType = str | Callable[[re.Match[str]], str]

_LEGAL_STD = (
    rf"{_QUOTE_OPT}(?:beyond\s+(?:a\s+)?reasonable\s+doubt|"
    rf"clear\s+and\s+convincing(?:\s+evidence)?|"
    rf"balance\s+of\s+probabilities|"
    rf"preponderance\s+of\s+(?:the\s+)?evidence|"
    rf"scintilla(?:\s+of\s+evidence)?){_QUOTE_OPT}"
)

_NORMALIZATION_RULES: Final[tuple[tuple[re.Pattern[str], _ReplType], ...]] = (
    # 1. Strip bracketed or unbracketed contract names, tier headers, "**Note:**", or legacy placeholders
    (
        re.compile(
            r"\[(?:Epistemic\s+Burden\s+Contract|Tier\s*\d+[^\]]*|STANDARD|REDACTED)\]\s*:?\s*",
            re.I,
        ),
        "",
    ),
    (
        re.compile(
            r"\s*,?\s*(?:as\s+required\s+by|under|per|according\s+to)\s+(?:the\s+)?Epistemic\s+Burden\s+Contract\b",
            re.I,
        ),
        "",
    ),
    (re.compile(r"\b(?:the\s+)?Epistemic\s+Burden\s+Contract\b", re.I), "the retrieved sources"),
    (re.compile(r"\*{1,2}Note\s*:?\*{1,2}\s*:?\s*", re.I), ""),
    (re.compile(r"\bPlease\s+note\s+that\s+", re.I), ""),
    # 2. Remove explicit prompt-mandate self-reference ("I must state that", "this claim must be stated as")
    (
        re.compile(
            r"\bI\s+(?:must|am\s+required\s+to|have\s+to)\s+(?:explicitly\s+)?(?:state|note|report|disclose|point\s+out)\s+that\s+",
            re.I,
        ),
        "",
    ),
    (
        re.compile(
            r"\b(?:any|this|the|such\s+a)\s+(?:answer|claim|information|statement|conclusion|response)\s+must\s+be\s+(?:framed|treated|classified|stated|presented|regarded)\s+as\b",
            re.I,
        ),
        "this claim remains",
    ),
    # 3. Normalize retrieval-header echoes ("untrusted web searches", "general web search results")
    (re.compile(r"\buntrusted\s+web\s+search(?:es|ing)?\b", re.I), "web search results"),
    (
        re.compile(r"\band\s+general\s+web\s+search\s+results\b", re.I),
        "and another search result",
    ),
    # 4. Parenthetical and inline confidence telemetry ("(confidence 0.70 from one source)", "(0.40)", "confidence score")
    (
        re.compile(
            r"\(\s*(?:with\s+)?(?:only\s+|low\s+|high\s+)?(?:conf(?:idence)?(?:\s+level|\s+score)?\s*(?:of\s+|:?\s*)?)?0\.\d+\s*(?:from\s+([^)]+))?\)",
            re.I,
        ),
        lambda m: f"(from {m.group(1).strip()})" if m.group(1) else "",
    ),
    (
        re.compile(
            r"\s*,?\s*(?:with\s+)?(?:only\s+|a\s+)?(?:low\s+|high\s+|moderate\s+)?confidence(?:\s+level|\s+score)?\s*(?:of\s+|:?\s*)0\.\d+\b",
            re.I,
        ),
        "",
    ),
    (
        re.compile(
            r"\b(?:with\s+)?(?:only\s+)?0\.\d+\s+confidence(?:\s+level|\s+score)?\b",
            re.I,
        ),
        "with limited support",
    ),
    (
        re.compile(
            r"\b(?:the\s+)?confidence(?:\s+level|\s+score)?\s+(?:in\s+this\s+\w+\s+)?is\s+(?:low|high|moderate)?\s*\(?0\.\d+\)?\s*,?\s*",
            re.I,
        ),
        "",
    ),
    (re.compile(r"\blow\s+confidence\s+(?:level|score)\b", re.I), "weak support"),
    (re.compile(r"\bhigh\s+confidence\s+(?:level|score)\b", re.I), "strong support"),
    (re.compile(r"\bconfidence\s+(?:level|score)\b", re.I), "degree of support"),
    # 5. Participial, prepositional ("below..."), and finite ("falls below...") unmet threshold phrases
    (
        re.compile(
            rf"\b(?:as|since|because)\s+(?:the\s+)?(?:required\s+|applicable\s+)?(?:legal\s+|evidentiary\s+|epistemic\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?)\s+(?:is|was)\s+{_LEGAL_STD}",
            re.I,
        ),
        "so additional independent sources would be needed for full certainty",
    ),
    (
        re.compile(
            rf"\b(?:falling\s+below|failing\s+to\s+meet)\s+(?:the\s+)?(?:required\s+|necessary\s+|applicable\s+)?{_LEGAL_STD}(?:\s+(?:legal\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?))?(?:\s+required)?",
            re.I,
        ),
        "lacking strong enough support to confirm",
    ),
    (
        re.compile(
            r"\b(?:falling\s+below|failing\s+to\s+meet)\s+(?:the\s+)?(?:required\s+|necessary\s+|applicable\s+)?(?:legal\s+|evidentiary\s+|epistemic\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?)(?:\s+required)?",
            re.I,
        ),
        "lacking strong enough support to confirm",
    ),
    (
        re.compile(
            rf"\b(?:falls?\s+below|does\s+not\s+meet|fails?\s+to\s+meet)\s+(?:the\s+)?(?:required\s+|necessary\s+|applicable\s+)?{_LEGAL_STD}(?:\s+(?:legal\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?))?(?:\s+required)?",
            re.I,
        ),
        "does not have strong enough support to confirm",
    ),
    (
        re.compile(
            r"\b(?:falls?\s+below|does\s+not\s+meet|fails?\s+to\s+meet)\s+(?:the\s+)?(?:required\s+|necessary\s+|applicable\s+)?(?:legal\s+|evidentiary\s+|epistemic\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?)(?:\s+required)?",
            re.I,
        ),
        "does not have strong enough support to confirm",
    ),
    (
        re.compile(
            rf"\b(?:below|short\s+of)\s+(?:the\s+)?(?:required\s+|necessary\s+|applicable\s+)?{_LEGAL_STD}(?:\s+(?:legal\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?))?(?:\s+required)?",
            re.I,
        ),
        "short of the certainty needed to confirm",
    ),
    (
        re.compile(
            r"\b(?:below|short\s+of)\s+(?:the\s+)?(?:required\s+|necessary\s+|applicable\s+)?(?:legal\s+|evidentiary\s+|epistemic\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?)(?:\s+required)?",
            re.I,
        ),
        "short of the certainty needed to confirm",
    ),
    # 6. Participial vs finite met legal-standard & threshold phrases
    (
        re.compile(
            rf"\b(?:meeting|satisfying|reaching|aligning\s+with)\s+(?:a\s+|the\s+)?(?:required\s+|necessary\s+|applicable\s+)?{_LEGAL_STD}(?:\s+(?:legal\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?))?(?:\s+required)?",
            re.I,
        ),
        "consistent with the available sources",
    ),
    (
        re.compile(
            rf"\b(?:meeting|satisfying|reaching|aligning\s+with)\s+(?:a\s+|the\s+)?(?:required\s+|necessary\s+|applicable\s+)?(?:legal\s+|evidentiary\s+|epistemic\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?)(?:\s+of\s+(?:a\s+|the\s+)?{_LEGAL_STD})?(?:\s+required)?",
            re.I,
        ),
        "consistent with the available sources",
    ),
    (
        re.compile(
            rf"\b(?:meets?|satisfies|reaches?|aligns?\s+with)\s+(?:a\s+|the\s+)?(?:required\s+|necessary\s+|applicable\s+)?{_LEGAL_STD}(?:\s+(?:legal\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?))?(?:\s+required)?",
            re.I,
        ),
        "has moderate support from the available sources",
    ),
    (
        re.compile(
            rf"\b(?:meets?|satisfies|reaches?|aligns?\s+with)\s+(?:a\s+|the\s+)?(?:required\s+|necessary\s+|applicable\s+)?(?:legal\s+|evidentiary\s+|epistemic\s+)?(?:standard(?:\s+of\s+proof)?|threshold|burden(?:\s+of\s+proof)?)(?:\s+of\s+(?:a\s+|the\s+)?{_LEGAL_STD})?(?:\s+required)?(?:\s*\([^)]*\))?",
            re.I,
        ),
        "is supported by the available sources",
    ),
    (
        re.compile(
            rf"\b(?:at|under|based\s+on|with|by)\s+(?:a\s+|the\s+)?(?:degree\s+of\s+support\s+of\s+|confidence\s+level\s+of\s+)?(?:required\s+)?{_LEGAL_STD}(?:\s+(?:standard(?:\s+of\s+proof)?|threshold|level))?",
            re.I,
        ),
        "based on the available sources",
    ),
    # 7. Remaining standalone legal-standard phrases -> plain paraphrases
    (
        re.compile(
            rf"(?:\ba\s+|\bthe\s+)?{_QUOTE_OPT}\bbeyond\s+(?:a\s+)?reasonable\s+doubt\b{_QUOTE_OPT}(?:\s+(?:standard|threshold|level))?",
            re.I,
        ),
        "with high certainty",
    ),
    (
        re.compile(
            rf"(?:\ba\s+|\bthe\s+)?{_QUOTE_OPT}\bclear\s+and\s+convincing(?:\s+evidence)?\b{_QUOTE_OPT}(?:\s+(?:standard|threshold|level))?",
            re.I,
        ),
        "strong support",
    ),
    (
        re.compile(
            rf"(?:\ba\s+|\bthe\s+)?{_QUOTE_OPT}\bbalance\s+of\s+probabilities\b{_QUOTE_OPT}(?:\s+(?:standard|threshold|level))?",
            re.I,
        ),
        "moderate support",
    ),
    (
        re.compile(
            rf"(?:\ba\s+|\bthe\s+)?{_QUOTE_OPT}\bpreponderance\s+of\s+(?:the\s+)?evidence\b{_QUOTE_OPT}(?:\s+(?:standard|threshold|level))?",
            re.I,
        ),
        "moderate support",
    ),
    (
        re.compile(
            rf"(?:\ba\s+|\bthe\s+)?{_QUOTE_OPT}\bscintilla(?:\s+of\s+evidence)?\b{_QUOTE_OPT}(?:\s+(?:standard|threshold|level))?",
            re.I,
        ),
        "limited support",
    ),
    # 8. Speculation / unverified speculation -> plain uncertainty phrasing
    (
        re.compile(
            rf"\ban\s+{_QUOTE_OPT}unverified\s+speculation{_QUOTE_OPT}\b",
            re.I,
        ),
        "an unconfirmed claim",
    ),
    (
        re.compile(
            rf"{_QUOTE_OPT}\bunverified\s+speculation\b{_QUOTE_OPT}",
            re.I,
        ),
        "unconfirmed",
    ),
    (
        re.compile(
            rf"\b(?:an?\s+)?(?:mere\s+|pure\s+)?{_QUOTE_OPT}speculation{_QUOTE_OPT}\b",
            re.I,
        ),
        "an unconfirmed claim",
    ),
    (re.compile(r"\bspeculative\b", re.I), "unconfirmed"),
    # 9. Remaining contract lexicon terms: standard of proof, burden, threshold, epistemic
    (
        re.compile(
            r"\b(?:the\s+)?(?:required\s+|applicable\s+|legal\s+|evidentiary\s+|epistemic\s+)*standard\s+of\s+proof(?:\s+required)?\b",
            re.I,
        ),
        "the support needed",
    ),
    (
        re.compile(
            r"\b(?:the\s+)?(?:required\s+|applicable\s+|evidentiary\s+|epistemic\s+)(?:level\s+of\s+support|standard)\b",
            re.I,
        ),
        "stronger support",
    ),
    (
        re.compile(
            r"\b(?:evidentiary\s+|epistemic\s+|proof\s+)?burdens?\s+of\s+proof\b",
            re.I,
        ),
        "support needed",
    ),
    (re.compile(r"\bburdens?\b", re.I), "support"),
    (re.compile(r"\bthresholds?\b", re.I), "support level"),
    (re.compile(r"\bepistemically\b", re.I), "factually"),
    (re.compile(r"\bepistemic\b", re.I), "factual"),
    # 10. Contract hazard-tier & boilerplate phrases
    (
        re.compile(
            r"\s*(?:required\s+)?for\s+(?:a\s+|an\s+|this\s+)?(?:high|medium|low)[-\s]hazard\s+(?:\w+\s+)?(?:query|queries|question|questions|topic|topics|domain|domains|request|requests|inquiry|inquiries)\b",
            re.I,
        ),
        "",
    ),
    (
        re.compile(
            r"\b(?:high|medium|low)[-\s]hazard\s+(?:\w+\s+)?(?:query|queries|question|questions|topic|topics|claim|claims)\b",
            re.I,
        ),
        "this question",
    ),
    (re.compile(r"\b(?:high|medium|low)[-\s]hazard\b", re.I), "sensitive"),
    (re.compile(r"\s*for\s+this\s+(?:query|inquiry)\b", re.I), ""),
    # 11. Smooth redundant self-referential meta-sentences ("This is supported by the available sources.")
    (
        re.compile(
            r"\s*This\s+(?:information\s+|conclusion\s+|fact\s+)?(?:is\s+supported\s+by|is\s+based\s+on|aligns\s+with)\s+the\s+(?:available|retrieved)\s+sources\.?",
            re.I,
        ),
        "",
    ),
    (re.compile(r"\bunconfirmed\s+short\s+of\b", re.I), "unconfirmed and short of"),
)

# Forbidden lexicon scanned on EVERY normalized reply (RM-3 Acceptance Check 1: must be 0 hits).
FORBIDDEN_LEXICON_PATTERNS: Final[dict[str, re.Pattern[str]]] = {
    "balance_of_probabilities": re.compile(r"\bbalance\s+of\s+probabilities\b", re.I),
    "preponderance": re.compile(r"\bpreponderance\b", re.I),
    "clear_and_convincing": re.compile(r"\bclear\s+and\s+convincing\b", re.I),
    "reasonable_doubt": re.compile(r"\breasonable\s+doubt\b", re.I),
    "scintilla": re.compile(r"\bscintilla\b", re.I),
    "standard_of_proof": re.compile(r"\bstandard\s+of\s+proof\b", re.I),
    "required_standard": re.compile(r"\brequired\s+standard\b", re.I),
    "threshold": re.compile(r"\bthresholds?\b", re.I),
    "burden": re.compile(r"\bburdens?\b", re.I),
    "epistemic": re.compile(r"\bepistemic(?:ally)?\b", re.I),
    "speculation": re.compile(r"\bspeculat(?:ion|ive)\b", re.I),
    "hazard_tier": re.compile(r"\b(?:high|medium|low)[-\s]hazard\b", re.I),
    "contract_word": re.compile(r"\bburden\s+contract\b|\bweight\s+of\s+support\s+contract\b", re.I),
    "numeric_confidence_telemetry": re.compile(
        r"\b(?:confidence(?:\s+level|\s+score)?\s*(?:of\s+|:?\s*)?0\.\d+|0\.\d+\s+confidence)\b",
        re.I,
    ),
    "placeholder_tokens": re.compile(
        r"\[(?:STANDARD|REDACTED|Epistemic\s+Burden|Tier\s*\d+)\b", re.I
    ),
}


def _fix_sentence_capitalization_and_spacing(text: str) -> str:
    s = re.sub(r"[ \t]+", " ", text)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\bwith\s+with\b", "with", s, flags=re.I)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"\.\s*,", ",", s)
    s = re.sub(r"([,;:])\s*([.;!?])", r"\2", s)
    s = re.sub(r"\.\s*\.", ".", s)
    s = s.strip()
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    s = re.sub(
        r"([.!?]\s+)([a-z])",
        lambda m: m.group(1) + m.group(2).upper(),
        s,
    )
    return s


def normalize_reply(text: str) -> str:
    """Deterministically normalize a single reply identically regardless of arm."""
    if not text:
        return ""
    out = text
    for pat, repl in _NORMALIZATION_RULES:
        out = pat.sub(repl, out)
    return _fix_sentence_capitalization_and_spacing(out)


def scan_forbidden_lexicon(texts: list[str]) -> dict[str, int]:
    counts = {k: 0 for k in FORBIDDEN_LEXICON_PATTERNS}
    for t in texts:
        for name, pat in FORBIDDEN_LEXICON_PATTERNS.items():
            if pat.search(t):
                counts[name] += 1
    return counts


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verify-v2-raw",
        type=Path,
        default=REPO_ROOT / "logs" / "test_reports" / "wo45" / "g4_live_v2_raw_generations.json",
    )
    parser.add_argument("--out-check-json", type=Path, default=None)
    args = parser.parse_args()

    raw_data = json.loads(args.verify_v2_raw.read_text(encoding="utf-8"))
    turns = raw_data["turn_records"]

    before_by_arm: dict[str, dict[str, int]] = {}
    after_by_arm: dict[str, dict[str, int]] = {}
    arms = sorted({str(t["arm"]) for t in turns})
    for arm in arms:
        raw_texts = [str(t["reply"]) for t in turns if str(t["arm"]) == arm]
        norm_texts = [normalize_reply(x) for x in raw_texts]
        before_by_arm[arm] = scan_forbidden_lexicon(raw_texts)
        after_by_arm[arm] = scan_forbidden_lexicon(norm_texts)

    total_after_hits = sum(sum(v.values()) for v in after_by_arm.values())
    summary = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "normalizer_script_sha256": sha256_file(Path(__file__).resolve()),
        "source_file": str(args.verify_v2_raw.relative_to(REPO_ROOT)).replace("\\", "/"),
        "n_turns_scanned": len(turns),
        "before_normalization_hits_by_arm": before_by_arm,
        "after_normalization_hits_by_arm": after_by_arm,
        "total_forbidden_hits_after_normalization": total_after_hits,
        "acceptance_check_1_zero_hits": total_after_hits == 0,
    }
    if args.out_check_json is not None:
        args.out_check_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_check_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if total_after_hits != 0:
        raise SystemExit(f"Lexicon scan failed with {total_after_hits} residual hits!")


if __name__ == "__main__":
    main()
