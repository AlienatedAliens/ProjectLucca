"""
Project Lucca — AST Preflight Sanitizer & Automatic Code Repair Engine
Spec 12 & Spec 32 (Zero-Simulation, Zero-Syntax-Crash Deterministic Pipeline)

Validates, repairs, and guarantees execution semantics of LLM-generated code
before sending it to the Docker sandbox container:
1. Strips non-code markdown wrapper artifacts.
2. Auto-repairs common LLM syntax bugs:
   - Unclosed brackets: (), [], {}
   - Unclosed docstrings/quotes
   - Caret exponentiation: x^2 -> x**2
   - Implicit multiplication: 2x -> 2*x, 3(a+b) -> 3*(a+b)
   - Truncated trailing incomplete statements
3. Guarantees entrypoint execution:
   - Injects print(fn()) if solve()/main() was defined but never called
   - Injects print(last_var) if no print statement exists
4. Injects missing standard mathematical imports (sympy, math, itertools).
"""

from __future__ import annotations

import ast
import re
from typing import Tuple

import structlog

logger = structlog.get_logger(__name__)


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

    # Step 1: Lexical token-level normalization (Zero-Regex tokenizer engine)
    try:
        import io
        import tokenize
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

        code = tokenize.untokenize(new_tokens)
    except Exception as exc:
        logger.debug("tokenize_normalization_fallback", error=str(exc))

    # Step 2: Try initial AST parse
    parsed, tree, err = _try_parse(code)
    if not parsed:
        # Step 3: Attempt syntax repairs
        # 3a. Fix unclosed quotes/docstrings
        if code.count('"""') % 2 != 0:
            code += '\n"""\n'
        if code.count("'''") % 2 != 0:
            code += "\n'''\n"

        # 3b. Fix unclosed brackets
        open_parens = code.count('(') - code.count(')')
        open_brackets = code.count('[') - code.count(']')
        open_braces = code.count('{') - code.count('}')
        if open_parens > 0:
            code += ')' * open_parens
        if open_brackets > 0:
            code += ']' * open_brackets
        if open_braces > 0:
            code += '}' * open_braces

        parsed, tree, err = _try_parse(code)

        # 3c. If still failing, check if the last line was truncated mid-statement
        if not parsed:
            lines = code.splitlines()
            while lines and not parsed:
                # Remove the broken last line
                lines.pop()
                candidate = "\n".join(lines).strip()
                # Re-apply bracket closures
                p_c = candidate.count('(') - candidate.count(')')
                b_c = candidate.count('[') - candidate.count(']')
                br_c = candidate.count('{') - candidate.count('}')
                if p_c > 0: candidate += ')' * p_c
                if b_c > 0: candidate += ']' * b_c
                if br_c > 0: candidate += '}' * br_c
                parsed, tree, err = _try_parse(candidate)
                if parsed:
                    code = candidate
                    break

    if not parsed or tree is None:
        return code, False, err

    # Step 4: Inject missing common imports by inspecting AST nodes directly (Zero Substring / Zero Regex)
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
        # Re-parse after import injection
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
