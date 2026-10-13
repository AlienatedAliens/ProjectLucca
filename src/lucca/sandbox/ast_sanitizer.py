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
import keyword
from typing import Tuple
import textwrap
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
                is_kw = tok.type == tokenize.NAME and keyword.iskeyword(tok.string)
                if not is_kw:
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
        err_str = str(exc)
        _noisy = ("line continuation", "unterminated string", "unindent", "unexpected EOF", "syntax")
        if not any(n in err_str.lower() for n in _noisy):
            logger.debug("tokenize_normalization_fallback", error=err_str)
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
                block = textwrap.dedent(part.split("```")[0]).strip()
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
                block = textwrap.dedent(block).strip()
                candidate = _close_brackets_and_quotes(_normalize_tokens(block))
                if block and (_looks_like_code(block) or _try_parse(candidate)[0]):
                    return block, "fenced"
        elif len(parts) == 2:
            block = parts[1].strip()
            if block.startswith("python\n") or block.startswith("py\n"):
                block = block.split("\n", 1)[1].strip()
            block = textwrap.dedent(block).strip()
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

    # Step 4: Semantic AST validation, cleanup, and import injection
    # 4a. Filter hallucinated imports in `from sympy import ...`
    try:
        import sympy as _sp_ref
        _valid_sympy_names = set(dir(_sp_ref))
    except Exception as exc:
        logger.debug("sympy_dir_inspection_failed", error=str(exc))
        _valid_sympy_names = set()

    modified_ast = False
    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module == "sympy" and _valid_sympy_names:
            filtered_aliases = [
                alias for alias in stmt.names
                if alias.name == "*" or alias.name in _valid_sympy_names
            ]
            if len(filtered_aliases) != len(stmt.names):
                stmt.names = filtered_aliases if filtered_aliases else [ast.alias(name="*")]
                modified_ast = True

    # 4b. Pre-flight repair for differentiation wrt composite expression (e.g. sp.diff(expr, u) where u = x/h)
    assigned_composite_exprs: dict[str, int] = {}
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if isinstance(node.value, (ast.BinOp, ast.UnaryOp)):
                        assigned_composite_exprs[target.id] = i

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # 4b-1. Rewrite expr.solve(...) -> sp.solve(expr, ...)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "solve":
                if not (isinstance(node.func.value, ast.Name) and node.func.value.id in ("sp", "sympy")):
                    caller_expr = node.func.value
                    node.func = ast.Attribute(value=ast.Name(id="sp", ctx=ast.Load()), attr="solve", ctx=ast.Load())
                    node.args.insert(0, caller_expr)
                    modified_ast = True

            # 4b-2. Pre-flight repair for diff wrt composite expressions
            is_diff = False
            if isinstance(node.func, ast.Name) and node.func.id == "diff":
                is_diff = True
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "diff":
                is_diff = True
            if is_diff and len(node.args) >= 2:
                var_arg = node.args[1]
                if isinstance(var_arg, ast.Name) and var_arg.id in assigned_composite_exprs:
                    idx = assigned_composite_exprs[var_arg.id]
                    parsed_node = ast.parse(f"{var_arg.id} = sp.symbols('{var_arg.id}', real=True, positive=True)").body[0]
                    tree.body[idx] = parsed_node
                    modified_ast = True
                elif isinstance(var_arg, (ast.BinOp, ast.UnaryOp)):
                    var_name = "_diff_var_"
                    tree.body.insert(0, ast.parse(f"{var_name} = sp.symbols('{var_name}', real=True, positive=True)").body[0])
                    node.args[1] = ast.Name(id=var_name, ctx=ast.Load())
                    modified_ast = True

    if modified_ast:
        try:
            ast.fix_missing_locations(tree)
            code = ast.unparse(tree)
            parsed, tree, err = _try_parse(code)
            if not parsed or tree is None:
                return code, False, err
        except Exception as exc:
            logger.debug("ast_unparse_failed", error=str(exc))

    # 4c. Inspect all used names, attribute bases, and defined/imported symbols
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used_attr_bases = {node.value.id for node in ast.walk(tree) if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)}

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    assigned_names: set[str] = set()

    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name)
        elif isinstance(stmt, ast.ImportFrom):
            if stmt.module:
                imported_modules.add(stmt.module)
            for alias in stmt.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    assigned_names.add(target.id)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assigned_names.add(stmt.name)

    imports_to_add: list[str] = []

    # Check if sympy is needed
    sympy_symbols = {"symbols", "Symbol", "solve", "solveset", "factor", "expand", "simplify", "Matrix", "Rational", "Eq", "diff", "integrate", "pi", "oo", "prime", "totient", "divisor_sigma", "primepi"}
    if ("sp" in used_attr_bases or "sympy" in used_attr_bases or "sympy" in used_names or any(s in used_names for s in sympy_symbols)) and "sympy" not in imported_modules and "sp" not in imported_names:
        imports_to_add.append("import sympy\nimport sympy as sp\nfrom sympy import *")

    # Check if math is needed
    math_symbols = {"sqrt", "factorial", "gcd", "lcm", "floor", "ceil", "comb", "perm"}
    if ("math" in used_attr_bases or any(m in used_names for m in math_symbols)) and "math" not in imported_modules and "sympy" not in imported_modules:
        imports_to_add.append("import math")

    # Check if itertools is needed
    itertools_symbols = {"permutations", "combinations", "product", "accumulate", "count", "cycle", "repeat"}
    if ("itertools" in used_attr_bases or any(it in used_names for it in itertools_symbols)) and "itertools" not in imported_modules:
        imports_to_add.append("import itertools")

    # Check if fractions.Fraction is needed
    if "Fraction" in used_names and "Fraction" not in imported_names and "fractions" not in imported_modules:
        imports_to_add.append("from fractions import Fraction")

    # Check if container_world / ContainerWorld / World / KnowledgeBase is needed
    cw_symbols = {"ContainerWorld", "World", "KnowledgeBase", "BeliefTracker"}
    if ("container_world" in used_attr_bases or any(c in used_names for c in cw_symbols)) and "container_world" not in imported_modules and not any(c in imported_names for c in cw_symbols):
        imports_to_add.append("from container_world import ContainerWorld, World, KnowledgeBase, BeliefTracker")

    # Check if z3 is needed
    z3_symbols = {"Solver", "Int", "Ints", "Real", "Reals", "Bool", "Bools", "sat", "unsat", "Or", "And", "Not", "Distinct"}
    if ("z3" in used_attr_bases or any(z in used_names for z in z3_symbols)) and "z3" not in imported_modules and not any(z in imported_names for z in z3_symbols):
        imports_to_add.append(
            "import z3\nfrom z3 import *\ntry:\n    z3.Solver.sat = z3.sat\n    z3.Solver.unsat = z3.unsat\nexcept Exception:\n    pass"
        )

    # Pre-flight definitions for commonly assumed math sets
    preflight_defs: list[str] = []
    if "primes" in used_names and "primes" not in assigned_names and "primes" not in imported_names:
        preflight_defs.append("primes = list(sp.primerange(2, 1000)) if 'sp' in globals() else []")
        if "sympy" not in imported_modules and "sp" not in imported_names:
            imports_to_add.insert(0, "import sympy as sp\nfrom sympy import *")
    if "odds" in used_names and "odds" not in assigned_names and "odds" not in imported_names:
        preflight_defs.append("odds = list(range(1, 1000, 2))")
    if "evens" in used_names and "evens" not in assigned_names and "evens" not in imported_names:
        preflight_defs.append("evens = list(range(0, 1000, 2))")

    header_additions: list[str] = imports_to_add + preflight_defs
    if header_additions:
        code = "\n".join(header_additions) + "\n\n" + code
        parsed, tree, err = _try_parse(code)
        if not parsed or tree is None:
            return code, False, err

    # 4d. AST Auto-Print Synthesis (Turn 1 Zero-Shot Optimization, Spec 32)
    has_print = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "print":
                has_print = True
                break

    if not has_print and tree.body:
        common_targets = [
            "final_answer", "ans", "result", "sol", "answer", "res",
            "target", "output", "prediction", "location", "believed_loc",
        ]
        found_target = None
        for tgt in common_targets:
            if tgt in assigned_names:
                found_target = tgt
                break

        if found_target:
            code = code + f"\nprint({found_target})"
        elif isinstance(tree.body[-1], (ast.Assign, ast.AnnAssign)):
            last_stmt = tree.body[-1]
            target_name = None
            if isinstance(last_stmt, ast.Assign) and last_stmt.targets:
                first_tgt = last_stmt.targets[0]
                if isinstance(first_tgt, ast.Name):
                    target_name = first_tgt.id
            elif isinstance(last_stmt, ast.AnnAssign) and isinstance(last_stmt.target, ast.Name):
                target_name = last_stmt.target.id

            if target_name and target_name not in ("_", "__"):
                code = code + f"\nprint({target_name})"
        elif isinstance(tree.body[-1], ast.Expr):
            # Replace/append print for unprinted trailing expression (e.g. w.query(...) or sp.totient(...))
            try:
                last_expr_code = ast.unparse(tree.body[-1].value)
                code = code + f"\nprint({last_expr_code})"
            except Exception:
                pass
        elif "solve" in assigned_names and any(isinstance(stmt, ast.FunctionDef) and stmt.name == "solve" for stmt in tree.body):
            code = code + "\nprint(solve())"
        elif "main" in assigned_names and any(isinstance(stmt, ast.FunctionDef) and stmt.name == "main" for stmt in tree.body):
            code = code + "\nprint(main())"

    return code, True, ""


# Canonical alias for compatibility
sanitize_python_code = sanitize_and_repair_python_code
