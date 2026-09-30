"""
Project Lucca — AST Preflight Sanitizer & Tolerant Code Extractor
Spec 12 & Spec 32 (Zero-Simulation, Zero-Syntax-Crash Deterministic Pipeline)

Validates, repairs, and guarantees execution semantics of LLM-generated code
before sending it to the Docker sandbox container:
1. Multi-Stage Tolerant Extraction:
   - Fenced markdown block (```python ... ``` or ``` ... ```)
   - Unfenced code lines (heuristic filter for Python statements)
   - Longest contiguous slice that parses via ast.parse()
   - Explicit 'empty' stage flag when no code exists
2. Token-level AST operator repairs (Zero regex):
   - Caret exponentiation: x^2 -> x**2 (strictly preserving string literals & comments)
   - Implicit multiplication: 2x -> 2*x, 3(a+b) -> 3*(a+b), (a)(b) -> (a)*(b)
   - Degree and infinity symbol mappings
3. Structural Syntax Repairs:
   - Unclosed brackets: (), [], {}
   - Unclosed docstrings/quotes: triple quotes and single quotes
   - Truncated trailing incomplete statements
4. Guarantees entrypoint execution:
   - Injects print(fn()) if solve()/main() was defined but never called
   - Injects print(last_var) if no print statement exists
5. Injects missing standard mathematical imports (sympy, math, itertools).
"""

from __future__ import annotations

import ast
import io
from typing import Tuple
import tokenize

import structlog

logger = structlog.get_logger(__name__)


def _looks_like_code(block: str) -> bool:
    """Heuristic check if a text block contains Python code constructs."""
    keywords = (
        "import ", "from ", "def ", "class ", "print(", "return ",
        "if ", "elif ", "else:", "for ", "while ", "try:", "except",
        "with ", "assert ", "lambda ",
    )
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if not lines:
        return False
    matches = sum(1 for l in lines if any(l.startswith(k) for k in keywords) or ("=" in l and not l.startswith(("#", "-", "*", ">"))))
    return matches >= 1


def _try_parse(code: str) -> Tuple[bool, ast.AST | None, str]:
    """Helper to safely parse AST."""
    try:
        tree = ast.parse(code)
        return True, tree, ""
    except SyntaxError as e:
        return False, None, f"SyntaxError at line {e.lineno}: {e.msg}"
    except Exception as e:
        logger.debug("ast_parse_unknown_error", error=str(e))
        return False, None, f"ParseError: {e}"


def _normalize_tokens(code: str) -> str:
    """
    Lexical token-level normalization using Python standard library tokenize.
    Preserves string literals and comments 100% untouched.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
        new_tokens = []
        for i, tok in enumerate(tokens):
            if i > 0:
                prev = tokens[i - 1]
                if prev.type == tokenize.NUMBER and tok.type == tokenize.NAME:
                    new_tokens.append((tokenize.OP, "*"))
                elif prev.type == tokenize.NUMBER and tok.type == tokenize.OP and tok.string == "(":
                    new_tokens.append((tokenize.OP, "*"))
                elif prev.type == tokenize.OP and prev.string == ")" and tok.type in (tokenize.NAME, tokenize.NUMBER):
                    new_tokens.append((tokenize.OP, "*"))
                elif prev.type == tokenize.OP and prev.string == ")" and tok.type == tokenize.OP and tok.string == "(":
                    new_tokens.append((tokenize.OP, "*"))

            if tok.type == tokenize.OP and tok.string == "^":
                new_tokens.append((tokenize.OP, "**"))
                continue

            if tok.type == tokenize.NAME and tok.string == "Degree":
                new_tokens.extend([
                    (tokenize.OP, "("),
                    (tokenize.NAME, "sp"),
                    (tokenize.OP, "."),
                    (tokenize.NAME, "pi"),
                    (tokenize.OP, "/"),
                    (tokenize.NUMBER, "180"),
                    (tokenize.OP, ")"),
                ])
                continue
            elif tok.type == tokenize.NAME and tok.string == "infinity":
                new_tokens.append((tokenize.NAME, "oo"))
                continue

            new_tokens.append((tok.type, tok.string))

        return tokenize.untokenize(new_tokens)
    except Exception as exc:
        logger.debug("tokenize_normalization_fallback", error=str(exc))
        return code


def _close_brackets_and_quotes(code: str) -> str:
    """Auto-closes unclosed docstrings and parenthesis/bracket pairs."""
    # 1. Unclosed docstrings
    if code.count('"""') % 2 != 0:
        code += '\n"""\n'
    if code.count("'''") % 2 != 0:
        code += "\n'''\n"

    # 2. Unclosed brackets
    open_parens = code.count("(") - code.count(")")
    open_brackets = code.count("[") - code.count("]")
    open_braces = code.count("{") - code.count("}")
    if open_parens > 0:
        code += ")" * open_parens
    if open_brackets > 0:
        code += "]" * open_brackets
    if open_braces > 0:
        code += "}" * open_braces

    return code


def extract_python_code_tolerant(raw_text: str) -> Tuple[str, str]:
    """
    Extracts Python code from raw LLM output using multi-stage tolerant fallback.
    Order of extraction:
      1. Fenced markdown block (```python ... ``` or ``` ... ```)
      2. Unfenced code lines (blocks beginning with import/def/class/var assignment)
      3. Longest contiguous slice that successfully parses via ast.parse()
    Returns:
      (extracted_code: str, extraction_stage: str)
      stage is one of: 'fenced', 'unfenced', 'longest_ast_slice', 'empty'
    """
    if not raw_text or not raw_text.strip():
        return "", "empty"

    text = raw_text.strip()

    # --- Stage 1: Fenced markdown blocks ---
    if "```" in text:
        # Search for ```python first
        if "```python" in text:
            parts = text.split("```python")
            for part in reversed(parts[1:]):
                block = part.split("```")[0].strip()
                if block:
                    candidate = _close_brackets_and_quotes(_normalize_tokens(block))
                    parsed, _, _ = _try_parse(candidate)
                    if parsed or _looks_like_code(block):
                        return block, "fenced"

        # Search for general ``` blocks
        parts = text.split("```")
        if len(parts) >= 3:
            for i in range(len(parts) - 2, 0, -2):
                block = parts[i].strip()
                if block.startswith("python\n") or block.startswith("py\n"):
                    block = block.split("\n", 1)[1].strip()
                candidate = _close_brackets_and_quotes(_normalize_tokens(block))
                if block and (_looks_like_code(block) or _try_parse(candidate)[0]):
                    return block, "fenced"
        elif len(parts) == 2:
            block = parts[1].strip()
            if block.startswith("python\n") or block.startswith("py\n"):
                block = block.split("\n", 1)[1].strip()
            candidate = _close_brackets_and_quotes(_normalize_tokens(block))
            if block and (_looks_like_code(block) or _try_parse(candidate)[0]):
                return block, "fenced"

    # --- Stage 2: Unfenced code blocks ---
    lines = text.splitlines()
    code_lines = []
    for l in lines:
        trimmed = l.strip()
        if not trimmed:
            continue
        if any(
            trimmed.startswith(k)
            for k in (
                "import ", "from ", "def ", "class ", "print(", "return ",
                "if ", "elif ", "else:", "for ", "while ", "try:", "except",
                "with ", "assert ",
            )
        ) or ("=" in trimmed and not trimmed.startswith(("#", "-", "*", ">"))):
            code_lines.append(l)

    if code_lines:
        candidate_raw = "\n".join(code_lines).strip()
        candidate = _close_brackets_and_quotes(_normalize_tokens(candidate_raw))
        parsed, _, _ = _try_parse(candidate)
        if parsed:
            return candidate_raw, "unfenced"

    # --- Stage 3: Longest continuous slice that parses via ast.parse ---
    n = len(lines)
    best_slice = ""
    best_len = 0
    for start in range(n):
        for end in range(n, start, -1):
            if end - start <= best_len:
                break
            candidate_raw = "\n".join(lines[start:end]).strip()
            if not candidate_raw:
                continue
            candidate = _close_brackets_and_quotes(_normalize_tokens(candidate_raw))
            parsed, tree, _ = _try_parse(candidate)
            if parsed and tree is not None:
                has_substance = any(
                    not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Constant)
                    for stmt in tree.body
                )
                if has_substance and (end - start) > best_len:
                    best_len = end - start
                    best_slice = candidate_raw
                    break

    if best_slice:
        return best_slice, "longest_ast_slice"

    return "", "empty"


def sanitize_and_repair_python_code(raw_code: str) -> Tuple[str, bool, str]:
    """
    Sanitize, repair, and guarantee execution for python code.
    Returns:
        repaired_code: str
        is_valid: bool (True if ast.parse succeeds)
        error_msg: str (syntax error details if unrepairable)
    """
    code = raw_code.strip()
    if not code:
        return "", False, "Empty code"

    # Pre-extraction if markdown fences are present
    if "```" in code:
        extracted, stage = extract_python_code_tolerant(code)
        if extracted:
            code = extracted

    # Step 1: Lexical token-level normalization (Zero-Regex tokenizer engine)
    code = _normalize_tokens(code)

    # Step 2: Bracket and quote closure
    code = _close_brackets_and_quotes(code)

    # Step 3: Try initial AST parse
    parsed, tree, err = _try_parse(code)
    if not parsed:
        # If full block fails parse, check if text has embedded code slice
        extracted, stage = extract_python_code_tolerant(code)
        if extracted and stage != "empty" and extracted != code:
            code = _close_brackets_and_quotes(_normalize_tokens(extracted))
            parsed, tree, err = _try_parse(code)

        # Truncate broken trailing lines if still not parsing
        if not parsed:
            lines = code.splitlines()
            while lines and not parsed:
                lines.pop()
                candidate = "\n".join(lines).strip()
                candidate = _close_brackets_and_quotes(candidate)
                parsed, tree, err = _try_parse(candidate)
                if parsed:
                    code = candidate
                    break

    if not parsed or tree is None:
        return code, False, err

    # Step 4: Inject missing common imports by inspecting AST nodes directly
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used_attr_bases = {node.value.id for node in ast.walk(tree) if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)}

    imports_to_add: list[str] = []

    # Check if sympy is needed
    sympy_symbols = {"symbols", "Symbol", "solve", "solveset", "factor", "expand", "simplify", "Matrix", "Rational", "Eq", "diff", "integrate", "pi", "oo"}
    if ("sp" in used_attr_bases or any(s in used_names for s in sympy_symbols)) and "sympy" not in used_names:
        imports_to_add.append("import sympy as sp\nfrom sympy import *")

    # Check if math is needed
    math_symbols = {"sqrt", "factorial", "gcd", "lcm", "floor", "ceil", "comb", "perm"}
    if ("math" in used_attr_bases or any(m in used_names for m in math_symbols)) and "math" not in used_names and "sympy" not in used_names:
        imports_to_add.append("import math")

    # Check if itertools is needed
    itertools_symbols = {"permutations", "combinations", "product", "accumulate"}
    if ("itertools" in used_attr_bases or any(it in used_names for it in itertools_symbols)) and "itertools" not in used_names:
        imports_to_add.append("import itertools")

    if imports_to_add:
        code = "\n".join(imports_to_add) + "\n\n" + code
        parsed, tree, err = _try_parse(code)
        if not parsed or tree is None:
            return code, False, err

    # Step 5: Check and guarantee execution (uncalled top-level functions or missing print)
    called_functions: set[str] = set()
    top_level_fns: list[str] = []
    has_print = False
    assigned_variables: list[str] = []

    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            top_level_fns.append(stmt.name)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    assigned_variables.append(target.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == "print":
                has_print = True
            else:
                called_functions.add(node.func.id)

    # If top-level functions were defined but never invoked at top level:
    uncalled = [fn for fn in top_level_fns if fn not in called_functions]
    if uncalled:
        candidate_fns = [fn for fn in uncalled if fn in ("solve", "solution", "main", "compute", "calc", "calculate", "find_answer")]
        target_fn = candidate_fns[-1] if candidate_fns else uncalled[-1]
        code += f"\n\n_res = {target_fn}()\nif _res is not None:\n    print(_res)\n"
    elif not has_print:
        if assigned_variables:
            var_candidates = [v for v in assigned_variables if v in ("ans", "answer", "res", "result", "sol", "solution", "total")]
            chosen_var = var_candidates[-1] if var_candidates else assigned_variables[-1]
            code += f"\n\nprint({chosen_var})\n"
        elif tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr = tree.body[-1]
            try:
                expr_src = ast.unparse(last_expr.value)
                code += f"\n\nprint({expr_src})\n"
            except Exception as exc:
                logger.debug("ast_unparse_failed", error=str(exc))

    return code, True, ""
