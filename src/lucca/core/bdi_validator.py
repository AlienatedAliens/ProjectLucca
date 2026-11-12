"""
Project Lucca — Speculative BDI Invariant Validator
Milestone 4 (Architecture B Hardened by Architecture C) & WO-39 Milestone 2.4

Evaluates candidate System 2 tool calls speculatively before dispatch:
  Action = Arbitrate(S1(State), S2(Prompt, K))

Modal Operators:
- Prohibition (F): Strict invariants that immediately reject tool calls before RPC dispatch.
  Rejects attempts targeting OS directories (%WINDIR%, System32, /etc),
  mutation of databases/binaries (*.sqlite, *.exe, *.ps1), reverse shells,
  taint-tracked memory/workspace exfiltration, or violated Z3 resource/deontic bounds.
- Obligation (O): Mandatory actions required by epistemic/deontic rules.
- Permission (P): Safe workspace operations permitted by default.

Invariants:
1. Deterministic AST, MicroScheme S-expression precondition, and Z3 SMT constraint evaluation.
2. Sub-millisecond execution budget for fast-path checks; genuine AST/S-expr/Z3 step gas metering.
3. Zero-Any Rule Compliant (Strictly typed Pydantic & object interfaces).
"""

from __future__ import annotations

import ast
import dataclasses
import enum
import hashlib
import json
import re
import time
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from pydantic import BaseModel, Field, JsonValue

from lucca.core.schemas import Provenance, canonicalize_predicate
from lucca.memory.entities import FIRST_PERSON_TERMS, canonicalise
from lucca.memory.latent_probe import BelnapValue
from lucca.memory.tokens import derive_ed25519_public_keys, verify_provenance_signature
from lucca.sandbox.policy import TaintFlags

if TYPE_CHECKING:
    from lucca.memory.db import DatabaseManager

try:
    import z3
    _HAS_Z3 = True
except ImportError:  # pragma: no cover
    z3 = None
    _HAS_Z3 = False


class DeonticNorm(enum.StrEnum):
    PERMITTED = "permitted"
    PROHIBITED = "prohibited"
    OBLIGATORY = "obligatory"


PremiseStatus = Literal[
    "VALID",
    "EXPIRED",
    "MISSING",
    "CONFLICT",
    "UNTRUSTED",
    "TAMPERED",
    "THRESHOLD_VIOLATED",
]

PREMISE_SEXPR_OPS: Final[dict[str, tuple[bool, str | None]]] = {
    "fresh-fact?": (False, None),
    "fresh-fact=": (False, "="),
    "fresh-fact<=": (False, "<="),
    "fresh-fact>=": (False, ">="),
    "fresh-fact<": (False, "<"),
    "fresh-fact>": (False, ">"),
    "fresh-tool-fact?": (True, None),
    "fresh-tool-fact=": (True, "="),
    "fresh-tool-fact<=": (True, "<="),
    "fresh-tool-fact>=": (True, ">="),
    "fresh-tool-fact<": (True, "<"),
    "fresh-tool-fact>": (True, ">"),
}

_EXCLUDED_ENVELOPE_FIELDS: Final[frozenset[str]] = frozenset(
    {"signature", "signer_id", "entry_id", "content_sha256"}
)


@dataclasses.dataclass(frozen=True)
class _PremiseCandidateRow:
    memory_id: int
    entry_id: str
    provenance: Provenance
    object_value: str
    valid_from: float
    valid_to: float | None
    valid_until: float | None
    superseded_by: int | None
    tamper_stage: str | None = None


class InspectedPremiseRecord(BaseModel, frozen=True):
    """Audit record of a grounded state premise checked before tool dispatch."""

    subject: str
    predicate: str
    status: PremiseStatus
    belnap_state: BelnapValue
    provenance: Provenance | None = None
    entry_id: str | None = None
    memory_id: int | None = None
    object_value: str | None = None
    expected_constraint: str | None = None
    valid_from: float | None = None
    valid_until: float | None = None
    valid_to: float | None = None
    superseded_by: int | None = None
    tamper_stage: str | None = None
    checked_at: float


class BDIValidationResult(BaseModel):
    is_valid: bool = Field(description="Whether the candidate tool call is permitted to execute.")
    norm: DeonticNorm = Field(
        description="Deontic classification: PERMITTED, PROHIBITED, or OBLIGATORY."
    )
    reason: str | None = Field(
        default=None, description="Diagnostic justification or rule violation description."
    )
    elapsed_us: float = Field(default=0.0, description="Validation latency in microseconds.")
    gas_used: int = Field(default=0, description="Gas consumed during evaluation.")
    inspected_premises: list[InspectedPremiseRecord] = Field(
        default_factory=list,
        description="Per-premise freshness and Belnap valuation audit records.",
    )
    source_entry_ids: list[str] = Field(
        default_factory=list,
        description="Envelope entry_ids of all grounded premises inspected during validation.",
    )


FORBIDDEN_EXTENSIONS: Final[frozenset[str]] = frozenset(
    {".sqlite", ".db", ".exe", ".dll", ".bat", ".ps1", ".vbs", ".cmd", ".sh", ".sys", ".ini"}
)

SYSTEM_PATH_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"^[A-Za-z]:[/\\](?:windows|system32|program\s*files|programdata|appdata[/\\]local[/\\]microsoft)|"
    r"^/(?:etc|sys|proc|root|bin|sbin|usr[/\\]bin)|"
    r"(?:^|[/\\])(?:windows|system32|winnt)(?:[/\\]|$)"
    r")",
    re.IGNORECASE,
)

TRAVERSAL_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?:\.\.[/\\]|[/\\]\.\.|^\.\.$|\x00|%2e%2e|%2f|%5c)",
    re.IGNORECASE,
)

MALICIOUS_PYTHON_REGEX: Final[re.Pattern[str]] = re.compile(
    r"(?:"
    r"System\.Net\.Sockets\.TCPClient|"
    r"socket\.socket\s*\(|"
    r"pty\.spawn|"
    r"/bin/sh\s+-i|"
    r"subprocess\.(?:run|Popen|call)\s*\(\s*\[?['\"](?:powershell|cmd|bash|sh)\b|"
    r"os\.system\s*\(\s*['\"](?:powershell|cmd|bash|sh|rm\s+-rf|del\s+/[fFqQ]|format)\b|"
    r"ctypes\.windll|"
    r"winreg\.|"
    r"shutil\.rmtree\s*\(\s*r?['\"][A-Za-z]:[/\\]windows"
    r")",
    re.IGNORECASE,
)

# Default MicroScheme S-expression deontic preconditions evaluated per tool call
DEFAULT_DEONTIC_SEXPRS: Final[tuple[str, ...]] = (
    '(not (and (tool= "fetch_url") (tainted? "private") (external-url?)))',
    '(not (and (or (tool= "write_file") (tool= "delete_file")) (forbidden-ext?)))',
)

# Resource bound specifications verified via Z3 SMT solver when numeric args are present
NUMERIC_ARG_BOUNDS: Final[dict[str, tuple[float, float]]] = {
    "timeout": (0.01, 300.0),
    "timeout_s": (0.01, 300.0),
    "max_results": (1.0, 100.0),
    "limit": (1.0, 10000.0),
    "port": (1.0, 65535.0),
    "depth": (0.0, 64.0),
    "max_depth": (1.0, 64.0),
    "memory_mb": (1.0, 16384.0),
}

SExprNode = str | list["SExprNode"]


def _parse_sexpr(text: str) -> SExprNode:
    """Lightweight deterministic S-expression parser for deontic preconditions."""
    tokens: list[str] = [str(m) for m in re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text.strip())]
    if not tokens:
        return []
    pos = 0

    def _read() -> SExprNode:
        nonlocal pos
        if pos >= len(tokens):
            return []
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            lst: list[SExprNode] = []
            while pos < len(tokens) and tokens[pos] != ")":
                lst.append(_read())
            if pos < len(tokens) and tokens[pos] == ")":
                pos += 1
            return lst
        if tok.startswith('"') and tok.endswith('"') and len(tok) >= 2:
            return tok[1:-1]
        return tok

    return _read()


class SpeculativeBDIValidator:
    """
    Speculative BDI Invariant Validator (Milestone 4 & WO-39 Milestone 2.4).
    Intercepts candidate tool calls emitted by System 2 (ToolCallEnd)
    before any RPC or OS side-effect occurs.
    """

    def __init__(
        self,
        workspace_root: Path | str = "C:/ProjectLucca/workspace",
        deontic_rules: list[str] | None = None,
        db: DatabaseManager | None = None,
        clock_fn: Callable[[], float] = time.time,
        tool_premises: dict[str, list[tuple[str, str]]] | None = None,
        master_key: bytes | None = None,
        public_keys: dict[Provenance, Ed25519PublicKey] | None = None,
        policy_path: Path | str | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        self.db: DatabaseManager | None = db
        self._clock_fn: Callable[[], float] = clock_fn
        self._master_key: bytes | None = master_key
        if public_keys is not None:
            self._public_keys: dict[Provenance, Ed25519PublicKey] = dict(public_keys)
        elif master_key is not None and len(master_key) >= 32:
            self._public_keys = derive_ed25519_public_keys(master_key)
        else:
            self._public_keys = {}

        self._tool_premises: dict[str, list[tuple[str, str, bool]]] = (
            {k: [(s, p, False) for s, p in v] for k, v in tool_premises.items()}
            if tool_premises
            else {}
        )
        loaded_rules, loaded_premises = self._load_policy_toml(policy_path)
        if deontic_rules is not None:
            self.deontic_sexprs: list[str] = list(deontic_rules)
        elif loaded_rules:
            merged = list(DEFAULT_DEONTIC_SEXPRS)
            for r_str in loaded_rules:
                if r_str not in merged:
                    merged.append(r_str)
            self.deontic_sexprs = merged
        else:
            self.deontic_sexprs = list(DEFAULT_DEONTIC_SEXPRS)

        for t_name, p_list in loaded_premises.items():
            if t_name not in self._tool_premises:
                self._tool_premises[t_name] = p_list

        self._parsed_rules: list[SExprNode] = [_parse_sexpr(s) for s in self.deontic_sexprs]

    @staticmethod
    def _load_policy_toml(
        policy_path: Path | str | None,
    ) -> tuple[list[str], dict[str, list[tuple[str, str, bool]]]]:
        p_file = (
            Path(policy_path)
            if policy_path is not None
            else Path("config/deontic_policy.toml")
        )
        if not p_file.exists():
            return [], {}
        try:
            raw = tomllib.loads(p_file.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            return [], {}
        rules: list[str] = []
        raw_rules = raw.get("sexpr_rules")
        if isinstance(raw_rules, list):
            for item in raw_rules:
                if isinstance(item, str) and item.strip():
                    rules.append(item.strip())
        premises: dict[str, list[tuple[str, str, bool]]] = {}
        raw_prem = raw.get("tool_premises")
        if isinstance(raw_prem, dict):
            for t_key, entries in raw_prem.items():
                if not isinstance(t_key, str) or not isinstance(entries, list):
                    continue
                parsed_entries: list[tuple[str, str, bool]] = []
                for ent in entries:
                    if isinstance(ent, dict):
                        s_v = ent.get("subject") or ent.get("s")
                        p_v = ent.get("predicate") or ent.get("p")
                        req_tv = bool(ent.get("tool_verified", False))
                        if isinstance(s_v, str) and isinstance(p_v, str) and s_v and p_v:
                            parsed_entries.append((s_v, p_v, req_tv))
                if parsed_entries:
                    premises[t_key] = parsed_entries
        return rules, premises

    def register_tool_premises(
        self,
        tool_name: str,
        premises: list[tuple[str, str]],
        *,
        require_tool_verified: bool = False,
    ) -> None:
        """Registers mandatory (subject, predicate) freshness preconditions for a tool."""
        self._tool_premises[tool_name] = [
            (s, p, require_tool_verified) for s, p in premises
        ]

    def add_deontic_rule(self, sexpr: str) -> None:
        """Registers an additional S-expression deontic precondition."""
        self.deontic_sexprs.append(sexpr)
        self._parsed_rules.append(_parse_sexpr(sexpr))

    def _verify_premise_integrity(
        self,
        *,
        content_str: str,
        stored_sha: str,
        stored_sig: str,
        prov_enum: Provenance,
        p_obj: dict[str, JsonValue],
        st: dict[str, JsonValue],
        row_valid_from: float,
        row_valid_until: float | None,
    ) -> str | None:
        """Verifies D-MEM-05 SHA-256, signed-TTL consistency, and Ed25519 signature."""
        actual_sha = hashlib.sha256(content_str.encode("utf-8")).hexdigest()
        if stored_sha and actual_sha != stored_sha:
            return "content_sha256"
        if "content" in p_obj and str(p_obj.get("content", "")) != content_str:
            return "payload_content_mismatch"

        c_raw = p_obj.get("created_at")
        signed_created = (
            float(c_raw)
            if isinstance(c_raw, (int, float)) and not isinstance(c_raw, bool)
            else row_valid_from
        )
        vf_raw = st.get("valid_from")
        signed_vf = (
            float(vf_raw)
            if isinstance(vf_raw, (int, float)) and not isinstance(vf_raw, bool)
            else signed_created
        )
        signed_vu: float | None = None
        vu_raw = st.get("valid_until")
        ttl_raw = st.get("ttl_seconds")
        if isinstance(vu_raw, (int, float)) and not isinstance(vu_raw, bool):
            signed_vu = float(vu_raw)
        elif isinstance(ttl_raw, (int, float)) and not isinstance(ttl_raw, bool):
            signed_vu = signed_vf + float(ttl_raw)

        if abs(row_valid_from - signed_vf) > 1e-6:
            return "valid_from_column_tamper"
        if (row_valid_until is None) != (signed_vu is None):
            return "valid_until_column_tamper"
        if (
            row_valid_until is not None
            and signed_vu is not None
            and abs(row_valid_until - signed_vu) > 1e-6
        ):
            return "valid_until_column_tamper"

        if self._public_keys or self._master_key is not None:
            if not stored_sig:
                return "missing_signature"
            canon_dict = {
                k: v for k, v in p_obj.items() if k not in _EXCLUDED_ENVELOPE_FIELDS
            }
            canonical_bytes = json.dumps(
                canon_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            if not verify_provenance_signature(
                stored_sig,
                canonical_bytes,
                prov_enum,
                public_key=self._public_keys.get(prov_enum),
                master_key=self._master_key,
                allow_legacy_hmac=(self._master_key is not None),
            ):
                return "ed25519_signature"
        return None

    @staticmethod
    def _check_premise_value_constraint(
        actual_obj: str,
        value_op: str,
        expected_value: float | str,
    ) -> bool:
        """Evaluates string equality or Z3/float numeric bound on a live premise value."""
        cleaned = actual_obj.strip()
        if value_op == "=":
            try:
                lv = float(cleaned)
                rv = float(expected_value)
                return abs(lv - rv) <= 1e-9
            except (TypeError, ValueError):
                return cleaned.lower() == str(expected_value).strip().lower()

        try:
            actual_f = float(cleaned)
            bound_f = float(expected_value)
        except (TypeError, ValueError):
            return False

        if _HAS_Z3 and z3 is not None:
            solver = z3.Solver()
            solver.set("timeout", 20)
            var = z3.Real("premise_val")
            solver.add(var == z3.RealVal(actual_f))
            b_val = z3.RealVal(bound_f)
            if value_op == "<=":
                solver.add(var <= b_val)
            elif value_op == ">=":
                solver.add(var >= b_val)
            elif value_op == "<":
                solver.add(var < b_val)
            elif value_op == ">":
                solver.add(var > b_val)
            else:
                return False
            return bool(solver.check() == z3.sat)

        if value_op == "<=":
            return actual_f <= bound_f
        if value_op == ">=":
            return actual_f >= bound_f
        if value_op == "<":
            return actual_f < bound_f
        if value_op == ">":
            return actual_f > bound_f
        return False

    @staticmethod
    def _build_premise_record(
        *,
        subject: str,
        predicate: str,
        status: PremiseStatus,
        belnap_state: BelnapValue,
        checked_at: float,
        cand: _PremiseCandidateRow | None = None,
        expected_constraint: str | None = None,
    ) -> InspectedPremiseRecord:
        if cand is None:
            return InspectedPremiseRecord(
                subject=subject,
                predicate=predicate,
                status=status,
                belnap_state=belnap_state,
                expected_constraint=expected_constraint,
                checked_at=checked_at,
            )
        return InspectedPremiseRecord(
            subject=subject,
            predicate=predicate,
            status=status,
            belnap_state=belnap_state,
            provenance=cand.provenance,
            entry_id=cand.entry_id,
            memory_id=cand.memory_id,
            object_value=cand.object_value,
            expected_constraint=expected_constraint,
            valid_from=cand.valid_from,
            valid_to=cand.valid_to,
            valid_until=cand.valid_until,
            superseded_by=cand.superseded_by,
            tamper_stage=cand.tamper_stage,
            checked_at=checked_at,
        )

    def inspect_premise(
        self,
        subject: str,
        predicate: str,
        now: float | None = None,
        *,
        allowed_provenances: frozenset[Provenance] | None = None,
        value_op: str | None = None,
        expected_value: float | str | None = None,
    ) -> InspectedPremiseRecord:
        """Inspects grounded SQLite state for (subject, predicate) freshness, cryptographic
        integrity, provenance eligibility, and optional value/Z3 threshold constraints.
        """
        checked_at = float(now if now is not None else self._clock_fn())
        constraint_str = (
            f"{value_op} {expected_value}"
            if value_op is not None and expected_value is not None
            else None
        )
        p_norm = canonicalize_predicate(predicate)
        if not subject.strip():
            return self._build_premise_record(
                subject="<missing_arg>",
                predicate=p_norm,
                status="MISSING",
                belnap_state=BelnapValue.NEITHER,
                checked_at=checked_at,
                expected_constraint=constraint_str,
            )

        raw_s = canonicalise(subject)
        s_norm = "user" if raw_s in FIRST_PERSON_TERMS else (raw_s or subject.strip().lower())

        if self.db is None:
            return self._build_premise_record(
                subject=s_norm,
                predicate=p_norm,
                status="MISSING",
                belnap_state=BelnapValue.NEITHER,
                checked_at=checked_at,
                expected_constraint=constraint_str,
            )

        trusted_matched: list[_PremiseCandidateRow] = []
        untrusted_unretracted: list[_PremiseCandidateRow] = []
        tampered_unretracted: list[_PremiseCandidateRow] = []

        with self.db.read_cursor() as cur:
            cur.execute(
                """
                SELECT m.memory_id, m.entry_id, m.content, m.valid_from, m.valid_to,
                       m.valid_until, m.superseded_by,
                       p.provenance, p.content_sha256, p.signature, p.payload_json
                FROM memories m
                JOIN provenance_envelopes p ON m.entry_id = p.entry_id
                WHERE m.forgotten_at IS NULL
                  AND p.grounding_eligible = 1
                  AND m.kind IN ('fact', 'tool_fact', 'rule_assertion')
                  AND json_extract(p.payload_json, '$.structured.p') IS NOT NULL
                ORDER BY m.valid_from DESC, m.memory_id DESC
                """
            )
            for row in cur.fetchall():
                payload_str = str(row["payload_json"] or "")
                if not payload_str:
                    continue
                try:
                    p_obj = json.loads(payload_str)
                    prov_enum = Provenance(str(row["provenance"]))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if not isinstance(p_obj, dict):
                    continue
                st = p_obj.get("structured")
                if not isinstance(st, dict):
                    continue
                cand_raw_s = canonicalise(str(st.get("s", "")))
                cand_s = (
                    "user" if (not cand_raw_s or cand_raw_s in FIRST_PERSON_TERMS) else cand_raw_s
                )
                cand_p = canonicalize_predicate(str(st.get("p", "")))
                if cand_s != s_norm or cand_p != p_norm:
                    continue

                v_from = float(row["valid_from"])
                v_to = float(row["valid_to"]) if row["valid_to"] is not None else None
                v_until = float(row["valid_until"]) if row["valid_until"] is not None else None
                sup_by = int(row["superseded_by"]) if row["superseded_by"] is not None else None

                tamper_stage = self._verify_premise_integrity(
                    content_str=str(row["content"] or ""),
                    stored_sha=str(row["content_sha256"] or ""),
                    stored_sig=str(row["signature"] or ""),
                    prov_enum=prov_enum,
                    p_obj=p_obj,
                    st=st,
                    row_valid_from=v_from,
                    row_valid_until=v_until,
                )
                cand = _PremiseCandidateRow(
                    memory_id=int(row["memory_id"]),
                    entry_id=str(row["entry_id"]),
                    provenance=prov_enum,
                    object_value=str(st.get("o", "")),
                    valid_from=v_from,
                    valid_to=v_to,
                    valid_until=v_until,
                    superseded_by=sup_by,
                    tamper_stage=tamper_stage,
                )
                if tamper_stage is not None:
                    if v_to is None and sup_by is None:
                        tampered_unretracted.append(cand)
                    continue
                if allowed_provenances is not None and prov_enum not in allowed_provenances:
                    if v_to is None and sup_by is None:
                        untrusted_unretracted.append(cand)
                    continue
                trusted_matched.append(cand)

        if tampered_unretracted:
            return self._build_premise_record(
                subject=s_norm,
                predicate=p_norm,
                status="TAMPERED",
                belnap_state=BelnapValue.NEITHER,
                checked_at=checked_at,
                cand=tampered_unretracted[0],
                expected_constraint=constraint_str,
            )

        unretracted = [r for r in trusted_matched if r.valid_to is None and r.superseded_by is None]
        live = [r for r in unretracted if r.valid_until is None or r.valid_until > checked_at]
        expired = [
            r for r in unretracted if r.valid_until is not None and r.valid_until <= checked_at
        ]

        if live:
            distinct_vals = {r.object_value.strip().lower() for r in live}
            top = live[0]
            if len(distinct_vals) > 1:
                return self._build_premise_record(
                    subject=s_norm,
                    predicate=p_norm,
                    status="CONFLICT",
                    belnap_state=BelnapValue.BOTH,
                    checked_at=checked_at,
                    cand=top,
                    expected_constraint=constraint_str,
                )
            if (
                value_op is not None
                and expected_value is not None
                and not self._check_premise_value_constraint(
                    top.object_value, value_op, expected_value
                )
            ):
                return self._build_premise_record(
                    subject=s_norm,
                    predicate=p_norm,
                    status="THRESHOLD_VIOLATED",
                    belnap_state=BelnapValue.FALSE,
                    checked_at=checked_at,
                    cand=top,
                    expected_constraint=constraint_str,
                )
            return self._build_premise_record(
                subject=s_norm,
                predicate=p_norm,
                status="VALID",
                belnap_state=BelnapValue.TRUE,
                checked_at=checked_at,
                cand=top,
                expected_constraint=constraint_str,
            )

        if expired:
            return self._build_premise_record(
                subject=s_norm,
                predicate=p_norm,
                status="EXPIRED",
                belnap_state=BelnapValue.NEITHER,
                checked_at=checked_at,
                cand=expired[0],
                expected_constraint=constraint_str,
            )

        if untrusted_unretracted:
            return self._build_premise_record(
                subject=s_norm,
                predicate=p_norm,
                status="UNTRUSTED",
                belnap_state=BelnapValue.NEITHER,
                checked_at=checked_at,
                cand=untrusted_unretracted[0],
                expected_constraint=constraint_str,
            )

        return self._build_premise_record(
            subject=s_norm,
            predicate=p_norm,
            status="MISSING",
            belnap_state=BelnapValue.NEITHER,
            checked_at=checked_at,
            cand=trusted_matched[0] if trusted_matched else None,
            expected_constraint=constraint_str,
        )

    def _eval_sexpr_node(
        self,
        node: SExprNode,
        tool_name: str,
        tool_args: dict[str, JsonValue],
        taint_flags: int,
        path_arg: str | None,
        inspected: list[InspectedPremiseRecord] | None = None,
        checked_at: float | None = None,
    ) -> tuple[bool | float | str, int]:
        """Evaluates a parsed S-expression AST node and returns (value, ast_steps_consumed)."""
        if isinstance(node, str):
            try:
                return float(node), 1
            except ValueError:
                return node, 1
        if not node:
            return True, 1

        head = str(node[0]).lower()
        steps = 1

        if head == "not" and len(node) >= 2:
            val, s = self._eval_sexpr_node(
                node[1], tool_name, tool_args, taint_flags, path_arg, inspected, checked_at
            )
            return (not bool(val)), steps + s

        if head == "and":
            result = True
            for child in node[1:]:
                val, s = self._eval_sexpr_node(
                    child, tool_name, tool_args, taint_flags, path_arg, inspected, checked_at
                )
                steps += s
                if not bool(val):
                    result = False
            return result, steps

        if head == "or":
            result = False
            for child in node[1:]:
                val, s = self._eval_sexpr_node(
                    child, tool_name, tool_args, taint_flags, path_arg, inspected, checked_at
                )
                steps += s
                if bool(val):
                    result = True
                    break
            return result, steps

        if head == "arg" and len(node) >= 2:
            arg_key, s = self._eval_sexpr_node(
                node[1], tool_name, tool_args, taint_flags, path_arg, inspected, checked_at
            )
            raw_v = tool_args.get(str(arg_key))
            return ("" if raw_v is None else str(raw_v)), steps + s

        if head in PREMISE_SEXPR_OPS:
            req_tool_ver, val_op = PREMISE_SEXPR_OPS[head]
            min_arity = 3 if val_op is None else 4
            if len(node) >= min_arity:
                subj_val, s1 = self._eval_sexpr_node(
                    node[1], tool_name, tool_args, taint_flags, path_arg, inspected, checked_at
                )
                pred_val, s2 = self._eval_sexpr_node(
                    node[2], tool_name, tool_args, taint_flags, path_arg, inspected, checked_at
                )
                s_extra = 0
                exp_val: float | str | None = None
                if val_op is not None:
                    ev_raw, s_extra = self._eval_sexpr_node(
                        node[3], tool_name, tool_args, taint_flags, path_arg, inspected, checked_at
                    )
                    exp_val = str(ev_raw) if isinstance(ev_raw, bool) else ev_raw
                allowed_provs = (
                    frozenset({Provenance.TOOL_VERIFIED}) if req_tool_ver else None
                )
                rec = self.inspect_premise(
                    str(subj_val),
                    str(pred_val),
                    now=checked_at,
                    allowed_provenances=allowed_provs,
                    value_op=val_op,
                    expected_value=exp_val,
                )
                if inspected is not None:
                    inspected.append(rec)
                return (rec.status == "VALID"), steps + s1 + s2 + s_extra + 2

        if head == "tool=" and len(node) >= 2:
            target_tool, s = self._eval_sexpr_node(
                node[1], tool_name, tool_args, taint_flags, path_arg
            )
            return (tool_name == str(target_tool)), steps + s

        if head == "tainted?" and len(node) >= 2:
            kind, s = self._eval_sexpr_node(node[1], tool_name, tool_args, taint_flags, path_arg)
            steps += s
            if str(kind).lower() == "private":
                return (
                    bool(
                        taint_flags & (TaintFlags.SENSITIVE_MEMORY | TaintFlags.WORKSPACE_PRIVATE)),
                    steps,
                )
            return bool(taint_flags), steps

        if head == "external-url?":
            url = str(tool_args.get("url", ""))
            is_local = url.startswith("http://127.0.0.1") or url.startswith("http://localhost")
            return (bool(url) and not is_local), steps + 1

        if head == "forbidden-ext?":
            if not path_arg:
                return False, steps + 1
            ext = Path(path_arg).suffix.lower()
            return (ext in FORBIDDEN_EXTENSIONS), steps + 1

        if head == "arg-has?" and len(node) >= 2:
            arg_key, s = self._eval_sexpr_node(node[1], tool_name, tool_args, taint_flags, path_arg)
            return (str(arg_key) in tool_args), steps + s

        if head in ("<=", ">=", "<", ">", "=") and len(node) >= 3:
            lhs_Key, s1 = self._eval_sexpr_node(node[1], tool_name, tool_args, taint_flags,
                path_arg)
            rhs_val, s2 = self._eval_sexpr_node(node[2], tool_name, tool_args, taint_flags,
                path_arg)
            steps += s1 + s2
            raw_arg = tool_args.get(str(lhs_Key), lhs_Key)
            try:
                lv = float(raw_arg)  # type: ignore[arg-type]
                rv = float(rhs_val)
            except (TypeError, ValueError):
                return True, steps
            if head == "<=":
                return lv <= rv, steps
            if head == ">=":
                return lv >= rv, steps
            if head == "<":
                return lv < rv, steps
            if head == ">":
                return lv > rv, steps
            return lv == rv, steps

        return True, steps

    def _inspect_python_ast(self, code: str) -> tuple[bool, str | None, int]:
        """Walks the Python AST to detect host-escape calls and meter actual AST node complexity."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return True, None, 2

        node_count = 0
        for node in ast.walk(tree):
            node_count += 1
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    func_name = f"{node.func.value.id}.{node.func.attr}"
                elif isinstance(node.func, ast.Name):
                    func_name = node.func.id
                if func_name in ("pty.spawn", "socket.socket", "ctypes.windll"):
                    return (
                        False,
                        f"Host escape or forbidden system call '{func_name}' detected in AST",
                        node_count,
                    )
            elif isinstance(node, ast.While):
                is_const_true = isinstance(node.test,
                    ast.Constant) and bool(node.test.value) is True
                if is_const_true:
                    has_exit = any(
                        isinstance(sub, (ast.Break, ast.Return, ast.Raise))
                        for stmt in node.body
                        for sub in ast.walk(stmt)
                    )
                    if not has_exit:
                        return (
                            False,
                            "Unbounded infinite 'while True' loop without break/return "
                                "detected in AST",
                            node_count,
                        )
        return True, None, max(1, node_count)

    def verify_z3_constraints(
        self,
        tool_name: str,
        tool_args: dict[str, JsonValue],
        taint_flags: int = 0,
    ) -> tuple[bool, str | None, int]:
        """
        Evaluates numeric resource bounds and symbolic deontic constraints via Z3 SMT solver.
        Returns (is_satisfiable, violation_reason, z3_steps_used).
        """
        numeric_Automatic: list[tuple[str, float, float, float]] = []
        for k, (lo, hi) in NUMERIC_ARG_BOUNDS.items():
            if k in tool_args and isinstance(tool_args[k], (int, float)) and not isinstance(
                tool_args[k], bool
            ):
                numeric_Automatic.append((k, float(tool_args[k]), lo, hi))  # type: ignore[arg-type]

        has_private_taint = bool(
            taint_flags & (TaintFlags.SENSITIVE_MEMORY | TaintFlags.WORKSPACE_PRIVATE)
        )
        is_fetch = tool_name == "fetch_url"

        if not numeric_Automatic and not (is_fetch and has_private_taint):
            return True, None, 0

        if not _HAS_Z3 or z3 is None:
            steps = 0
            for k, val, lo, hi in numeric_Automatic:
                steps += 2
                if not (lo <= val <= hi):
                    return (
                        False,
                        f"Resource bound constraint violated for '{
                            k}={val}' (allowed [{lo}, {hi}])",
                        steps,
                    )
            return True, None, steps

        solver = z3.Solver()
        solver.set("timeout", 20)
        z3_steps = 1

        if is_fetch:
            url = str(tool_args.get("url", ""))
            is_ext = bool(url) and not (
                url.startswith("http://127.0.0.1") or url.startswith("http://localhost")
            )
            taint_var = z3.Bool("tainted_private")
            egress_var = z3.Bool("external_egress")
            solver.add(taint_var == z3.BoolVal(has_private_taint))
            solver.add(egress_var == z3.BoolVal(is_ext))
            solver.add(z3.Implies(taint_var, z3.Not(egress_var)))
            z3_steps += 3
            if solver.check() == z3.unsat:
                return (
                    False,
                    "Outbound network egress prohibited while session context contains tainted "
                        "memory or workspace data",
                    z3_steps,
                )

        for k, val, lo, hi in numeric_Automatic:
            var = z3.Real(f"arg_{k}")
            solver.push()
            solver.add(var == z3.RealVal(val))
            solver.add(var >= z3.RealVal(lo))
            solver.add(var <= z3.RealVal(hi))
            z3_steps += 3
            if solver.check() == z3.unsat:
                solver.pop()
                return (
                    False,
                    f"Z3 resource-bound constraint violated: {k}={val} outside [{lo}, {hi}]",
                    z3_steps,
                )
            solver.pop()

        return True, None, z3_steps

    def validate_tool_call(
        self,
        tool_name: str,
        tool_args: dict[str, JsonValue],
        taint_flags: int = 0,
        inquiry_text: str | None = None,
    ) -> BDIValidationResult:
        """
        Speculatively validates a candidate tool call against deontic invariants,
        MicroScheme S-expression preconditions, and Z3 resource-bound constraints.
        """
        t0 = time.perf_counter()
        gas_used = 0

        # 1. Path Containment Invariants (Prohibition)
        path_arg = self._extract_path_argument(tool_args)
        if path_arg:
            gas_used += 1
            if TRAVERSAL_REGEX.search(path_arg):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return BDIValidationResult(
                    is_valid=False,
                    norm=DeonticNorm.PROHIBITED,
                    reason=f"Path traversal or invalid sequence detected in argument: {path_arg!r}",
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                )

            gas_used += 1
            if SYSTEM_PATH_REGEX.search(path_arg):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return BDIValidationResult(
                    is_valid=False,
                    norm=DeonticNorm.PROHIBITED,
                    reason=f"Access to protected system directory prohibited: {path_arg!r}",
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                )

            # 2. Mutation Invariants on Sensitive File Extensions (Prohibition)
            if tool_name in ("write_file", "delete_file"):
                gas_used += 1
                ext = Path(path_arg).suffix.lower()
                if ext in FORBIDDEN_EXTENSIONS:
                    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                    return BDIValidationResult(
                        is_valid=False,
                        norm=DeonticNorm.PROHIBITED,
                        reason=(
                            f"Direct modification of sensitive file format '{ext}' is prohibited"
                        ),
                        elapsed_us=elapsed_us,
                        gas_used=gas_used,
                    )

        # 3. Malicious Code & Host-Escape Invariant in run_python (Regex + AST walk)
        if tool_name == "run_python":
            code = str(tool_args.get("code", ""))
            gas_used += 1
            if code and MALICIOUS_PYTHON_REGEX.search(code):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return BDIValidationResult(
                    is_valid=False,
                    norm=DeonticNorm.PROHIBITED,
                    reason=(
                        "Host escape, socket reverse-shell, or destructive system call "
                        "detected in python script"
                    ),
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                )
            if code:
                ast_ok, ast_reason, ast_steps = self._inspect_python_ast(code)
                gas_used += ast_steps
                if not ast_ok:
                    elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                    return BDIValidationResult(
                        is_valid=False,
                        norm=DeonticNorm.PROHIBITED,
                        reason=ast_reason,
                        elapsed_us=elapsed_us,
                        gas_used=gas_used,
                    )

        checked_at = float(self._clock_fn())
        inspected: list[InspectedPremiseRecord] = []

        # 3b. Registered Tool & Call-Scoped Evidential Premise Freshness Gates
        req_pairs: list[tuple[str, str, bool]] = list(self._tool_premises.get(tool_name, []))
        raw_req = tool_args.get("_required_premises")
        if isinstance(raw_req, list):
            for entry in raw_req:
                if isinstance(entry, dict):
                    s_val = entry.get("s") or entry.get("subject")
                    p_val = entry.get("p") or entry.get("predicate")
                    req_tv = bool(entry.get("tool_verified", False))
                    if isinstance(s_val, str) and isinstance(p_val, str) and s_val and p_val:
                        req_pairs.append((s_val, p_val, req_tv))

        for subj_req, pred_req, req_tv in req_pairs:
            allowed_p = frozenset({Provenance.TOOL_VERIFIED}) if req_tv else None
            inspected.append(
                self.inspect_premise(
                    subj_req, pred_req, now=checked_at, allowed_provenances=allowed_p
                )
            )
            gas_used += 2

        failed_premises = [rec for rec in inspected if rec.status != "VALID"]
        if failed_premises:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            src_ids = list(dict.fromkeys(r.entry_id for r in inspected if r.entry_id))
            return BDIValidationResult(
                is_valid=False,
                norm=DeonticNorm.PROHIBITED,
                reason=self._format_premise_failure_reason(failed_premises),
                elapsed_us=elapsed_us,
                gas_used=gas_used,
                inspected_premises=inspected,
                source_entry_ids=src_ids,
            )

        # 4. MicroScheme S-Expression Deontic Preconditions
        extra_preconds = tool_args.get("_preconditions")
        rules_to_eval = list(self._parsed_rules)
        if isinstance(extra_preconds, str) and extra_preconds.strip():
            rules_to_eval.append(_parse_sexpr(extra_preconds))
        elif isinstance(extra_preconds, list):
            for p_str in extra_preconds:
                if isinstance(p_str, str) and p_str.strip():
                    rules_to_eval.append(_parse_sexpr(p_str))

        for parsed_rule in rules_to_eval:
            ok_val, rule_steps = self._eval_sexpr_node(
                parsed_rule,
                tool_name,
                tool_args,
                taint_flags,
                path_arg,
                inspected,
                checked_at,
            )
            gas_used += rule_steps
            if not bool(ok_val):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                src_ids = list(dict.fromkeys(r.entry_id for r in inspected if r.entry_id))
                sexpr_failed = [rec for rec in inspected if rec.status != "VALID"]
                if sexpr_failed:
                    reason_msg = self._format_premise_failure_reason(sexpr_failed)
                elif tool_name == "fetch_url":
                    reason_msg = (
                        "Outbound network egress prohibited while session context "
                        "contains tainted memory or workspace data"
                    )
                else:
                    reason_msg = "MicroScheme deontic S-expression precondition violated"
                return BDIValidationResult(
                    is_valid=False,
                    norm=DeonticNorm.PROHIBITED,
                    reason=reason_msg,
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                    inspected_premises=inspected,
                    source_entry_ids=src_ids,
                )

        src_ids = list(dict.fromkeys(r.entry_id for r in inspected if r.entry_id))

        # 5. Z3 SMT Resource-Bound & Deontic Verification
        z3_ok, z3_reason, z3_steps = self.verify_z3_constraints(
            tool_name, tool_args, taint_flags=taint_flags
        )
        gas_used += z3_steps
        if not z3_ok:
            elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
            return BDIValidationResult(
                is_valid=False,
                norm=DeonticNorm.PROHIBITED,
                reason=z3_reason,
                elapsed_us=elapsed_us,
                gas_used=gas_used,
                inspected_premises=inspected,
                source_entry_ids=src_ids,
            )

        # 6. Hardware Query Epistemic Obligation (Obligation)
        if inquiry_text:
            gas_used += 1
            lower_inquiry = inquiry_text.lower()
            is_hardware_inquiry = any(
                hw in lower_inquiry
                for hw in ("gpu", "vram", "cpu load", "ram amount", "workstation hardware")
            )
            if is_hardware_inquiry and tool_name not in ("query_capabilities", "list_dir"):
                elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
                return BDIValidationResult(
                    is_valid=True,
                    norm=DeonticNorm.OBLIGATORY,
                    reason="Hardware state inquiry obligates querying live hardware telemetry",
                    elapsed_us=elapsed_us,
                    gas_used=gas_used,
                    inspected_premises=inspected,
                    source_entry_ids=src_ids,
                )

        gas_used = max(1, gas_used)
        elapsed_us = (time.perf_counter() - t0) * 1_000_000.0
        return BDIValidationResult(
            is_valid=True,
            norm=DeonticNorm.PERMITTED,
            reason="Tool call satisfies all speculative deontic invariants",
            elapsed_us=elapsed_us,
            gas_used=gas_used,
            inspected_premises=inspected,
            source_entry_ids=src_ids,
        )

    @staticmethod
    def _format_premise_failure_reason(failed: list[InspectedPremiseRecord]) -> str:
        parts: list[str] = []
        for rec in failed:
            b_val = rec.belnap_state.value
            if rec.status == "EXPIRED":
                parts.append(
                    f"({rec.subject}, {rec.predicate}) EXPIRED [Belnap {b_val}]: "
                    f"entry_id={rec.entry_id} valid_until={rec.valid_until} <= "
                    f"checked_at={rec.checked_at} (superseded_by={rec.superseded_by})"
                )
            elif rec.status == "THRESHOLD_VIOLATED":
                parts.append(
                    f"({rec.subject}, {rec.predicate}) THRESHOLD_VIOLATED [Belnap {b_val}]: "
                    f"entry_id={rec.entry_id} value={rec.object_value!r} failed "
                    f"constraint '{rec.expected_constraint}'"
                )
            elif rec.status == "TAMPERED":
                parts.append(
                    f"({rec.subject}, {rec.predicate}) TAMPERED [Belnap {b_val}]: "
                    f"entry_id={rec.entry_id} failed {rec.tamper_stage} integrity check"
                )
            elif rec.status == "UNTRUSTED":
                prov_s = rec.provenance.value if rec.provenance is not None else "unknown"
                parts.append(
                    f"({rec.subject}, {rec.predicate}) UNTRUSTED [Belnap {b_val}]: "
                    f"entry_id={rec.entry_id} provenance={prov_s} is not TOOL_VERIFIED"
                )
            elif rec.status == "CONFLICT":
                parts.append(
                    f"({rec.subject}, {rec.predicate}) CONFLICT [Belnap {b_val}]: "
                    f"conflicting active facts around entry_id={rec.entry_id}"
                )
            else:
                parts.append(
                    f"({rec.subject}, {rec.predicate}) MISSING [Belnap {b_val}]: "
                    f"no active grounded premise at checked_at={rec.checked_at}"
                )
        return "Evidential precondition violation: " + "; ".join(parts)

    def _extract_path_argument(self, tool_args: dict[str, JsonValue]) -> str | None:
        """Extracts the primary path or target argument from tool parameters."""
        for key in ("path", "rel_path", "target", "file", "filename"):
            if key in tool_args and isinstance(tool_args[key], str):
                return str(tool_args[key]).strip()
        return None
