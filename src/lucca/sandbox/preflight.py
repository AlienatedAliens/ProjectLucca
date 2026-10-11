"""
Project Lucca — Preflight Code Assertion Extractor & Test Runner Generator
Spec 12 / WO-26 Phase 4 (Autonomous "Run-Before-You-Speak" Code Verification)
Extracts docstring test cases (doctest, arrow, equality, assert) and compiles
isolated assertion checks for Docker execution.
"""

from __future__ import annotations

import ast
import doctest
import re
from typing import Final

import structlog

logger = structlog.get_logger(__name__)


_ARROW_OR_EQ_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:>>>\s*)?(?:assert\s+)?([A-Za-z_]\w*\s*\(.*?\))\s*(?:===?|=>|->|➞)\s*(.+?)(?:\s*#.*)?$"
)


def extract_python_code(text: str) -> str:
    """Extracts executable Python code from markdown blocks or raw text using tolerant AST fallback."""
    if not text:
        return ""
    import textwrap
    from lucca.sandbox.ast_sanitizer import extract_python_code_tolerant, sanitize_and_repair_python_code
    code, stage = extract_python_code_tolerant(text)
    if not code:
        return ""
    code = textwrap.dedent(code).strip()
    repaired, ok, _ = sanitize_and_repair_python_code(code)
    return textwrap.dedent(repaired).strip() if ok else code


def extract_docstring_assertions(
    code_text: str, docstring_examples: list[str] | None = None
) -> list[str]:
    """Extracts executable assertion statements from code docstrings and prompt examples.

    Supports:
    1. Doctest examples: `>>> func(...)\nwant` and `>>> func(...) == want`
    2. Equalities without `>>>`: `func(...) == want`
    3. Arrow notations: `func(...) => want`, `func(...) -> want`, `func(...) ➞ want`
    4. Explicit assert statements: `assert func(...) == want`
    """
    assertions: list[str] = []

    def _process_item(item_str: str) -> None:
        cleaned = item_str.strip()
        if not cleaned:
            return
        if cleaned.startswith("assert "):
            assertions.append(cleaned)
            return

        m = _ARROW_OR_EQ_PATTERN.match(cleaned)
        if m:
            lhs = m.group(1).strip()
            rhs = m.group(2).strip()
            if rhs in ("True", "False"):
                assertions.append(f"assert ({lhs}) is {rhs}")
            else:
                assertions.append(f"assert ({lhs}) == ({rhs})")
            return

        if ">>>" in cleaned:
            try:
                parsed = doctest.DocTestParser().get_examples(cleaned)
                for p in parsed:
                    src = re.sub(r"#.*$", "", p.source.strip()).strip()
                    want = p.want.strip()
                    if not src:
                        continue
                    if want:
                        if want in ("True", "False") and any(
                            op in src for op in ("==", "!=", "<", ">", "<=", ">=", " in ", " is ")
                        ):
                            assertions.append(f"assert ({src}) is {want}")
                        else:
                            want_single = " ".join(want.splitlines())
                            assertions.append(f"assert ({src}) == ({want_single})")
                    else:
                        assertions.append(f"assert ({src})")
            except Exception as exc:
                logger.debug("preflight_docstring_item_parse_failed", error=str(exc))

    if docstring_examples:
        for ex in docstring_examples:
            _process_item(ex)

    try:
        tree = ast.parse(code_text)
        docstrings: list[str] = []
        mod_doc = ast.get_docstring(tree)
        if mod_doc:
            docstrings.append(mod_doc)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                doc = ast.get_docstring(node)
                if doc:
                    docstrings.append(doc)

        for doc in docstrings:
            try:
                parsed_examples = doctest.DocTestParser().get_examples(doc)
                for ex in parsed_examples:
                    src = re.sub(r"#.*$", "", ex.source.strip()).strip()
                    want = ex.want.strip()
                    if not src:
                        continue
                    if want:
                        if want in ("True", "False") and any(
                            op in src for op in ("==", "!=", "<", ">", "<=", ">=", " in ", " is ")
                        ):
                            assertions.append(f"assert ({src}) is {want}")
                        else:
                            want_single = " ".join(want.splitlines())
                            assertions.append(f"assert ({src}) == ({want_single})")
                    elif any(
                        op in src for op in ("==", "!=", "<", ">", "<=", ">=", " in ", " is ")
                    ):
                        assertions.append(f"assert ({src})")
            except Exception as exc:
                logger.debug("preflight_doctest_parse_failed", error=str(exc))

            for line in doc.splitlines():
                line = line.strip()
                if ">>>" in line:
                    continue
                m = _ARROW_OR_EQ_PATTERN.match(line)
                if m:
                    lhs = m.group(1).strip()
                    rhs = m.group(2).strip()
                    if rhs in ("True", "False"):
                        assertions.append(f"assert ({lhs}) is {rhs}")
                    else:
                        assertions.append(f"assert ({lhs}) == ({rhs})")
    except Exception as exc:
        logger.debug("preflight_ast_walk_failed", error=str(exc))

    # Deduplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for a in assertions:
        if a not in seen:
            seen.add(a)
            deduped.append(a)
    return deduped


def build_preflight_runner_code(code: str, assertions: list[str]) -> str:
    """Wraps code and assertions into a self-diagnosing execution harness.

    Emits rich, human- and model-readable diff messages on stderr upon failure.
    """
    env_preamble = (
        "import os\n"
        "os.environ['OPENBLAS_NUM_THREADS'] = '1'\n"
        "os.environ['MKL_NUM_THREADS'] = '1'\n"
        "os.environ['OMP_NUM_THREADS'] = '1'\n"
    )
    if not assertions:
        return f"{env_preamble}\n{code}\n\n# Preflight syntax and import sanity check passed\n"

    checks: list[str] = []
    for a_str in assertions:
        try:
            parsed = ast.parse(a_str).body[0]
            if (
                isinstance(parsed, ast.Assert)
                and isinstance(parsed.test, ast.Compare)
                and len(parsed.test.ops) == 1
                and isinstance(parsed.test.ops[0], ast.Eq)
            ):
                lhs = ast.unparse(parsed.test.left)
                rhs = ast.unparse(parsed.test.comparators[0])
                checks.append(
                    f"try:\n"
                    f"    __val = {lhs}\n"
                    f"    __exp = {rhs}\n"
                    f"    assert __val == __exp\n"
                    f"except AssertionError:\n"
                    f"    import sys\n"
                    f'    sys.stderr.write(f"AssertionError: {lhs} == {rhs} failed.\\nGot: {{__val!r}}\\nExpected: {{__exp!r}}\\n")\n'
                    f"    sys.exit(1)\n"
                )
                continue
        except Exception as exc:
            logger.debug("preflight_assertion_ast_parse_failed", error=str(exc))

        checks.append(
            f"try:\n"
            f"    {a_str}\n"
            f"except AssertionError:\n"
            f"    import sys\n"
            f'    sys.stderr.write("AssertionError: {a_str} failed.\\n")\n'
            f"    sys.exit(1)\n"
        )

    runner = f"{env_preamble}\n{code}\n\n# --- Preflight Spec Assertions ---\n" + "\n".join(checks)
    return runner
