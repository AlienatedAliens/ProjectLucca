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
import textwrap
import tokenize

import structlog
import sympy as _sp_ref

logger = structlog.get_logger(__name__)


def _looks_like_code(block: str) -> bool:
    """Heuristic check if a text block contains Python code constructs."""
    keywords = (
        "import ", "from ", "def ", "class ", "print(", "return ",
        "if ", "elif ", "else:", "for ", "while ", "try:", "except",
        "with ", "assert ", "lambda ",
    )
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if not lines:
        return False
    matches = sum(
        1
        for ln in lines
        if any(ln.startswith(k) for k in keywords)
        or ("=" in ln and not ln.startswith(("#", "-", "*", ">")))
    )
    return matches >= 1


def _try_parse(code: str) -> tuple[bool, ast.Module | None, str]:
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
                    elif (
                        prev.type == tokenize.NUMBER and tok.type == tokenize.OP and tok.string
                        == "("
                    ):
                        new_tokens.append((tokenize.OP, "*"))
                    elif prev.type == tokenize.OP and prev.string == ")" and tok.type in (
                        tokenize.NAME, tokenize.NUMBER):
                        new_tokens.append((tokenize.OP, "*"))
                    elif (
                        prev.type == tokenize.OP and prev.string == ")" and tok.type == tokenize.OP
                        and tok.string == "("
                    ):
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
        _noisy = ("line continuation", "unterminated string", "unindent", "unexpected eof",
            "syntax")
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


def extract_python_code_tolerant(raw_text: str) -> tuple[str, str]:
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
    for ln in lines:
        trimmed = ln.strip()
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
            code_lines.append(ln)

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


def sanitize_and_repair_python_code(raw_code: str) -> tuple[str, bool, str]:
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

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # 4b-1. Rewrite expr.solve(...) -> sp.solve(expr, ...) (except when z3 is the receiver
            # or module)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "solve":
                if not (isinstance(node.func.value, ast.Name) and node.func.value.id in ("sp",
                    "sympy", "z3", "s", "solver", "opt")):
                    if "z3" not in code or "sympy" in code:
                        caller_expr = node.func.value
                        node.func = ast.Attribute(value=ast.Name(id="sp", ctx=ast.Load()),
                            attr="solve", ctx=ast.Load())
                        node.args.insert(0, caller_expr)
                        modified_ast = True

            # 4b-2. Rewrite expr.coeff(...) -> expr.expand().coeff(...) for unexpanded SymPy
            # expressions (Milestone 36.5)
            if isinstance(node.func, ast.Attribute) and node.func.attr == "coeff":
                caller_expr = node.func.value
                is_already_expanded = (
                    isinstance(caller_expr, ast.Call)
                    and isinstance(caller_expr.func, ast.Attribute)
                    and caller_expr.func.attr == "expand"
                )
                if not is_already_expanded:
                    expanded_caller = ast.Call(
                        func=ast.Attribute(value=caller_expr, attr="expand", ctx=ast.Load()),
                        args=[],
                        keywords=[],
                    )
                    node.func.value = expanded_caller
                    modified_ast = True

    if modified_ast:
        try:
            ast.fix_missing_locations(tree)
            code = ast.unparse(tree)
            parsed, new_tree, err = _try_parse(code)
            if not parsed or new_tree is None:
                return code, False, err
            tree = new_tree
        except Exception as exc:
            logger.debug("ast_unparse_failed", error=str(exc))

    # 4c. Inspect all used names, attribute bases, and defined/imported symbols
    used_names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used_attr_bases = {node.value.id for node in ast.walk(tree) if isinstance(node,
        ast.Attribute) and isinstance(node.value, ast.Name)}

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

    z3_symbols = {"Solver", "Int", "Ints", "Real", "Reals", "Bool", "Bools", "sat", "unsat", "Or",
        "And", "Not", "Distinct"}
    has_z3 = "z3" in used_attr_bases or "z3" in imported_modules or any(
        z in used_names for z in z3_symbols)
    unassigned_used = used_names - assigned_names

    # Check if sympy is needed (do not inject sympy into pure Z3 scripts just because `solve` or
    # `simplify` is called)
    sympy_symbols = {"symbols", "Symbol", "solveset", "factor", "expand", "Matrix", "Rational",
        "Eq", "diff", "integrate", "pi", "oo", "prime", "totient", "divisor_sigma", "primepi"}
    if not has_z3:
        sympy_symbols = sympy_symbols | {"solve", "simplify"}
    if (
        "sp" in used_attr_bases or "sympy" in used_attr_bases or "sympy" in unassigned_used or any(
            s in unassigned_used for s
            in sympy_symbols)) and "sympy" not in imported_modules and "sp" not in imported_names:
        imports_to_add.append("import sympy\nimport sympy as sp\nfrom sympy import *")

    # Check if math is needed
    math_symbols = {"sqrt", "factorial", "gcd", "lcm", "floor", "ceil", "comb", "perm"}
    if (
        "math" in used_attr_bases or any(
            m in unassigned_used for m
            in math_symbols
        )
    ) and "math" not in imported_modules and "sympy" not in imported_modules:
        imports_to_add.append("import math")

    # Check if itertools is needed
    itertools_symbols = {"permutations", "combinations", "product", "accumulate", "count", "cycle",
        "repeat"}
    if (
        "itertools" in used_attr_bases or any(
            it in unassigned_used for it
            in itertools_symbols)) and "itertools" not in imported_modules:
        imports_to_add.append("import itertools")

    # Check if fractions.Fraction is needed
    if (
        "Fraction" in unassigned_used and "Fraction" not in imported_names and "fractions" not
        in imported_modules
    ):
        imports_to_add.append("from fractions import Fraction")

    # Check if container_world / ContainerWorld / World / KnowledgeBase / Agent is needed
    cw_symbols = {"ContainerWorld", "World", "KnowledgeBase", "BeliefTracker", "Agent"}
    if (
        "container_world" in used_attr_bases or any(
            c in unassigned_used for c
            in cw_symbols)) and "container_world" not in imported_modules and not any(c
            in imported_names for c in cw_symbols):
        imports_to_add.append("from container_world import ContainerWorld, World, KnowledgeBase, "
            "BeliefTracker, Agent")

    # Check if z3 is needed
    if has_z3:
        if "z3" not in imported_modules and not any(z in imported_names for z in z3_symbols):
            imports_to_add.append(

                    "import z3\nfrom z3 import *\ntry:\n    z3.Solver.sat = z3.sat\n    "
                    "z3.Solver.unsat = z3.unsat\n    z3.IntNumRef.__int__ = lambda self: "
                        "self.as_long()\n    z3.IntNumRef.__index__ = lambda self: "
                        "self.as_long()\nexcept Exception:\n    pass"

            )
        elif "z3.Solver.sat" not in code:
            imports_to_add.append(

                    "import z3\ntry:\n    z3.Solver.sat = z3.sat\n    z3.Solver.unsat = "
                        "z3.unsat\n   "
                    " z3.IntNumRef.__int__ = lambda self: self.as_long()\n    "
                        "z3.IntNumRef.__index__ = lambda self: self.as_long()\nexcept Exception:\n "
                        "   pass"

            )

    if imports_to_add:
        code = "\n".join(imports_to_add) + "\n\n" + code
        parsed, new_tree, err = _try_parse(code)
        if not parsed or new_tree is None:
            return code, False, err
        tree = new_tree

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
            # Replace/append print for unprinted trailing expression (e.g. w.query(...) or
            # sp.totient(...))
            try:
                last_expr_code = ast.unparse(tree.body[-1].value)
                code = code + f"\nprint({last_expr_code})"
            except Exception as exc:
                logger.debug("ast_unparse_last_expr_failed", error=str(exc))
        elif "solve" in assigned_names and any(isinstance(stmt,
            ast.FunctionDef) and stmt.name == "solve" for stmt in tree.body):
            code = code + "\nprint(solve())"
        elif "main" in assigned_names and any(isinstance(stmt,
            ast.FunctionDef) and stmt.name == "main" for stmt in tree.body):
            code = code + "\nprint(main())"

    return code, True, ""


# Canonical alias for compatibility
sanitize_python_code = sanitize_and_repair_python_code
