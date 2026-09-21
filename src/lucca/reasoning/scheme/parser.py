"""
MicroScheme v2 Parser & Canonical Serializer
Spec 05 §2, §3, §7
"""

import hashlib
import re
from dataclasses import dataclass

from lucca.core.exceptions import SchemeSyntaxError
from lucca.core.schemas import Say, ToolCall
from lucca.reasoning.scheme.lexer import Token, tokenize


@dataclass(frozen=True)
class Symbol:
    name: str
    line: int = 1
    col: int = 1


@dataclass(frozen=True)
class Keyword:
    name: str
    line: int = 1
    col: int = 1


SchemeAtom = int | float | bool | str | Symbol | Keyword
SchemeNode = SchemeAtom | list["SchemeNode"]
type SchemeValue = SchemeAtom | list["SchemeValue"] | Say | ToolCall

ALLOWED_OPS = frozenset(
    {
        "rule",
        "list",
        "tool",
        "say",
        "yield-to-core",
        "interrupt-core",
        "and",
        "or",
        "not",
        "if",
        "=",
        "<",
        ">",
        "<=",
        ">=",
        "+",
        "-",
        "*",
        "/",
        "intent=",
        "entity-has?",
        "entity",
        "entity-int",
        "entity-num",
        "entity-str",
        "transcript-has?",
        "transcript-matches-glob?",
        "app-running?",
        "hour-between?",
        "weekday?",
        "last-tool-ok?",
        "last-tool=",
        "session-turns>=",
        "str-contains?",
        "str-lower",
        "len",
        "min",
        "max",
        "defmacro",
    }
)

STATE_PREDICATES = frozenset(
    {
        "intent=",
        "entity-has?",
        "entity",
        "entity-int",
        "entity-num",
        "entity-str",
        "transcript-has?",
        "transcript-matches-glob?",
        "app-running?",
        "hour-between?",
        "weekday?",
        "last-tool-ok?",
        "last-tool=",
        "session-turns>=",
    }
)

RULE_ID_REGEX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*-v[0-9]+$")
MAX_NESTING_DEPTH = 32


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    when_expr: SchemeNode
    plan_expr: SchemeNode
    priority: int
    source_canonical: str
    source_hash: str


class Parser:
    def __init__(self, tokens: list[Token], macro_registry: object | None = None) -> None:
        self.tokens = tokens
        self.pos = 0
        self.depth = 0
        self.macro_registry = macro_registry
        self._in_macro_body = False

    def parse_all(self) -> SchemeNode:
        if not self.tokens:
            raise SchemeSyntaxError("Empty source: no tokens to parse")
        result = self._parse_expr()
        if self.pos < len(self.tokens):
            extra = self.tokens[self.pos]
            raise SchemeSyntaxError(
                f"Unexpected token '{extra.value}' after top-level expression",
                extra.line,
                extra.col,
            )
        return result

    def parse_all_forms(self) -> list[SchemeNode]:
        if not self.tokens:
            raise SchemeSyntaxError("Empty source: no tokens to parse")
        forms: list[SchemeNode] = []
        while self.pos < len(self.tokens):
            forms.append(self._parse_expr())
        return forms

    def _parse_defmacro_form(self, lparen: Token) -> list[SchemeNode]:
        defmacro_tok = self.tokens[self.pos]
        self.pos += 1  # consume 'defmacro'

        if self.pos >= len(self.tokens) or self.tokens[self.pos].type != "SYMBOL":
            line = self.tokens[self.pos].line if self.pos < len(self.tokens) else defmacro_tok.line
            col = self.tokens[self.pos].col if self.pos < len(self.tokens) else defmacro_tok.col
            raise SchemeSyntaxError("Macro name must be a symbol", line, col)

        name_tok = self.tokens[self.pos]
        macro_name = str(name_tok.value)
        if macro_name in ALLOWED_OPS:
            raise SchemeSyntaxError(
                f"Cannot define macro shadowing primitive '{macro_name}'",
                name_tok.line,
                name_tok.col,
            )
        self.pos += 1
        name_sym = Symbol(macro_name, name_tok.line, name_tok.col)

        # Parse parameter list '(' params... ')'
        if self.pos >= len(self.tokens) or self.tokens[self.pos].type != "LPAREN":
            line = self.tokens[self.pos].line if self.pos < len(self.tokens) else name_tok.line
            col = self.tokens[self.pos].col if self.pos < len(self.tokens) else name_tok.col
            raise SchemeSyntaxError("Expected '(' for macro parameter list", line, col)

        param_lparen = self.tokens[self.pos]
        self.pos += 1  # consume '('
        params: list[SchemeNode] = []
        seen_params: set[str] = set()
        while True:
            if self.pos >= len(self.tokens):
                raise SchemeSyntaxError(
                    "Unclosed parenthesis in macro parameters", param_lparen.line, param_lparen.col
                )
            cur = self.tokens[self.pos]
            if cur.type == "RPAREN":
                self.pos += 1  # consume ')'
                break
            if cur.type != "SYMBOL":
                raise SchemeSyntaxError(
                    f"Macro parameter must be a symbol, got {cur.value}", cur.line, cur.col
                )
            p_name = str(cur.value)
            if p_name in seen_params:
                raise SchemeSyntaxError(
                    f"Duplicate macro parameter '{p_name}' in definition of '{macro_name}'",
                    cur.line,
                    cur.col,
                )
            seen_params.add(p_name)
            params.append(Symbol(p_name, cur.line, cur.col))
            self.pos += 1

        # Parse macro body with _in_macro_body = True so template symbols/operators are preserved
        prev_in_macro = self._in_macro_body
        self._in_macro_body = True
        try:
            body = self._parse_expr()
        finally:
            self._in_macro_body = prev_in_macro

        if self.pos >= len(self.tokens) or self.tokens[self.pos].type != "RPAREN":
            line = self.tokens[self.pos].line if self.pos < len(self.tokens) else lparen.line
            col = self.tokens[self.pos].col if self.pos < len(self.tokens) else lparen.col
            raise SchemeSyntaxError("Expected ')' closing defmacro form", line, col)
        self.pos += 1  # consume ')'
        self.depth -= 1

        macro_node: list[SchemeNode] = [
            Symbol("defmacro", defmacro_tok.line, defmacro_tok.col),
            name_sym,
            params,
            body,
        ]
        if self.macro_registry is not None and hasattr(self.macro_registry, "register"):
            from lucca.reasoning.scheme.macros import parse_defmacro  # noqa: PLC0415

            macro_def = parse_defmacro(macro_node)
            self.macro_registry.register(macro_def)
        return macro_node

    def _parse_expr(self) -> SchemeNode:
        if self.pos >= len(self.tokens):
            last = self.tokens[-1] if self.tokens else None
            line = last.line if last else 1
            col = last.col if last else 1
            raise SchemeSyntaxError("Unexpected end of tokens while parsing expression", line, col)

        tok = self.tokens[self.pos]

        if tok.type == "LPAREN":
            return self._parse_list()
        elif tok.type == "RPAREN":
            raise SchemeSyntaxError("Unexpected closing parenthesis ')'", tok.line, tok.col)
        elif tok.type == "KEYWORD":
            self.pos += 1
            return Keyword(str(tok.value), tok.line, tok.col)
        elif tok.type == "SYMBOL":
            self.pos += 1
            sym_name = str(tok.value)
            if sym_name == "define":
                raise SchemeSyntaxError(
                    "Primitive shadowing or 'define' is forbidden", tok.line, tok.col
                )
            return Symbol(sym_name, tok.line, tok.col)
        elif tok.type in ("STRING", "NUMBER", "BOOLEAN"):
            self.pos += 1
            return tok.value
        else:
            raise SchemeSyntaxError(f"Unexpected token type '{tok.type}'", tok.line, tok.col)

    def _parse_list(self) -> list[SchemeNode]:
        lparen = self.tokens[self.pos]
        self.pos += 1  # consume '('
        self.depth += 1

        if self.depth > MAX_NESTING_DEPTH:
            raise SchemeSyntaxError(
                f"Maximum nesting depth of {MAX_NESTING_DEPTH} exceeded",
                lparen.line,
                lparen.col,
            )

        # Check if this list starts with 'defmacro'
        if (
            self.pos < len(self.tokens)
            and self.tokens[self.pos].type == "SYMBOL"
            and self.tokens[self.pos].value == "defmacro"
        ):
            return self._parse_defmacro_form(lparen)

        items: list[SchemeNode] = []
        while True:
            if self.pos >= len(self.tokens):
                raise SchemeSyntaxError(
                    "Unclosed parenthesis: expected ')' before EOF", lparen.line, lparen.col
                )

            cur = self.tokens[self.pos]
            if cur.type == "RPAREN":
                self.pos += 1  # consume ')'
                self.depth -= 1
                break

            items.append(self._parse_expr())

        # Validate operator if list represents an invocation
        if items and isinstance(items[0], Symbol):
            op = items[0].name
            if op == "define":
                raise SchemeSyntaxError(
                    "Primitive shadowing or 'define' is forbidden", items[0].line, items[0].col
                )
            if not self._in_macro_body and op not in ALLOWED_OPS:
                has_macro = False
                if self.macro_registry is not None and hasattr(self.macro_registry, "has"):
                    has_macro = self.macro_registry.has(op)
                if not has_macro:
                    raise SchemeSyntaxError(
                        f"Unknown or disallowed operator '{op}'", items[0].line, items[0].col
                    )

            # Check 'if' arity at parse time (Spec 05 §3)
            if op == "if":
                # (if cond then [else]) -> len(items) must be 3 or 4 (including 'if')
                arg_count = len(items) - 1
                if arg_count not in (2, 3):
                    raise SchemeSyntaxError(
                        f"'if' form requires 2 or 3 arguments, got {arg_count}",
                        items[0].line,
                        items[0].col,
                    )

        return items


def to_canonical(node: SchemeNode) -> str:
    """Deterministic, canonical MicroScheme pretty-printer."""
    if isinstance(node, bool):
        return "#t" if node else "#f"
    elif isinstance(node, (int, float)):
        return str(node)
    elif isinstance(node, str):
        escaped = (
            node.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
        )
        return f'"{escaped}"'
    elif isinstance(node, Symbol):
        return node.name
    elif isinstance(node, Keyword):
        return node.name
    elif isinstance(node, list):
        if not node:
            return "()"
        head = node[0]
        if isinstance(head, Symbol) and head.name == "rule" and len(node) >= 6:
            # Format rule canonically
            rule_id = to_canonical(node[1])
            # Find keywords
            when_expr = None
            plan_expr = None
            priority = 0
            i = 2
            while i < len(node):
                k = node[i]
                if isinstance(k, Keyword) and i + 1 < len(node):
                    if k.name == ":when":
                        when_expr = to_canonical(node[i + 1])
                    elif k.name == ":plan":
                        plan_expr = to_canonical(node[i + 1])
                    elif k.name == ":priority":
                        val = node[i + 1]
                        if isinstance(val, int):
                            priority = val
                    i += 2
                else:
                    i += 1
            lines = [f"(rule {rule_id}"]
            if when_expr is not None:
                lines.append(f"  :when {when_expr}")
            if plan_expr is not None:
                lines.append(f"  :plan {plan_expr}")
            if priority != 0:
                lines.append(f"  :priority {priority}")
            lines[-1] += ")"
            return "\n".join(lines)
        return "(" + " ".join(to_canonical(x) for x in node) + ")"
    raise SchemeSyntaxError(f"Cannot serialize object of type {type(node)}")


def parse(source: str) -> SchemeNode:
    tokens = tokenize(source)
    parser = Parser(tokens)
    return parser.parse_all()


def has_state_predicate(node: SchemeNode) -> bool:
    if isinstance(node, Symbol):
        return node.name in STATE_PREDICATES
    elif isinstance(node, list):
        return any(has_state_predicate(item) for item in node)
    return False


def _validate_operators(node: SchemeNode) -> None:
    """Verifies that all operator symbols in the node are strictly in ALLOWED_OPS."""
    if isinstance(node, list) and node:
        head = node[0]
        if isinstance(head, Symbol):
            op = head.name
            if op not in ALLOWED_OPS:
                raise SchemeSyntaxError(
                    f"Disallowed operator '{op}' after macro expansion", head.line, head.col
                )
        for child in node:
            _validate_operators(child)


def _validate_action_node(action: SchemeNode) -> None:
    if not isinstance(action, list) or not action or not isinstance(action[0], Symbol):
        raise SchemeSyntaxError(
            "Plan action must be a list starting with 'tool', 'say', "
            f"'yield-to-core', or 'interrupt-core', got {action}"
        )
    action_name = action[0].name
    if action_name == "tool":
        if len(action) < 2 or not isinstance(action[1], str):
            raise SchemeSyntaxError(f"Tool action requires a string tool name, got {action}")
        kidx = 2
        while kidx < len(action):
            if not isinstance(action[kidx], Keyword):
                raise SchemeSyntaxError(
                    f"Expected keyword in tool call kwargs, got {action[kidx]}"
                )
            if kidx + 1 >= len(action):
                raise SchemeSyntaxError(f"Missing value for keyword {action[kidx]}")
            kidx += 2
    elif action_name == "say":
        if len(action) != 2 or not isinstance(action[1], str):
            raise SchemeSyntaxError(
                f"Say action requires exactly one string argument, got {action}"
            )
    elif action_name == "yield-to-core":
        if len(action) < 2 or not isinstance(action[1], str):
            raise SchemeSyntaxError(
                f"yield-to-core requires at least a reason string, got {action}"
            )
        kidx = 2
        while kidx < len(action):
            if not isinstance(action[kidx], Keyword):
                raise SchemeSyntaxError(
                    f"Expected keyword in yield-to-core context kwargs, got {action[kidx]}"
                )
            if kidx + 1 >= len(action):
                raise SchemeSyntaxError(f"Missing value for keyword {action[kidx]}")
            kidx += 2
    elif action_name == "interrupt-core":
        if len(action) > 2 or (len(action) == 2 and not isinstance(action[1], str)):
            raise SchemeSyntaxError(
                f"interrupt-core accepts at most one reason string, got {action}"
            )
    else:
        raise SchemeSyntaxError(
            f"Unknown plan action '{action_name}'; must be 'tool', 'say', "
            "'yield-to-core', or 'interrupt-core'"
        )


def _validate_plan_structure(plan_node: SchemeNode) -> None:
    if not isinstance(plan_node, list) or not plan_node or not isinstance(plan_node[0], Symbol):
        raise SchemeSyntaxError("Rule :plan clause must be of form (list ...) or (if ...)")

    head = plan_node[0].name
    if head == "if":
        if len(plan_node) != 4:
            raise SchemeSyntaxError(
                "Plan 'if' form requires exactly 3 arguments (cond then else), "
                f"got {len(plan_node) - 1}"
            )
        _validate_plan_structure(plan_node[2])
        _validate_plan_structure(plan_node[3])
    elif head == "list":
        for action in plan_node[1:]:
            _validate_action_node(action)
    else:
        raise SchemeSyntaxError(
            f"Rule :plan clause must be of form (list ...) or (if ...), got ({head} ...)"
        )


def parse_rule(source: str, macro_registry: object | None = None) -> RuleDefinition:
    """
    Parses and strictly validates a canonical MicroScheme rule according to Spec 05 §2 & §7.
    Supports top-level (defmacro ...) definitions and macro expansion prior to compilation.
    """
    from lucca.reasoning.scheme.macros import (  # noqa: PLC0415
        MacroExpander,
        MacroRegistry,
        parse_defmacro,
    )

    reg: MacroRegistry
    if macro_registry is None:
        reg = MacroRegistry()
    elif isinstance(macro_registry, MacroRegistry):
        reg = macro_registry
    else:
        reg = MacroRegistry()

    tokens = tokenize(source)
    parser = Parser(tokens, macro_registry=reg)
    forms = parser.parse_all_forms()

    rule_ast: SchemeNode | None = None
    for form in forms:
        if isinstance(form, list) and form and isinstance(form[0], Symbol):
            if form[0].name == "defmacro":
                macro_def = parse_defmacro(form)
                reg.register(macro_def)
            elif form[0].name == "rule":
                if rule_ast is not None:
                    raise SchemeSyntaxError(
                        "Multiple 'rule' forms found in source; only one allowed per rule file"
                    )
                rule_ast = form
            else:
                raise SchemeSyntaxError(
                    f"Top-level form must be 'defmacro' or 'rule', got '{form[0].name}'"
                )
        else:
            raise SchemeSyntaxError(
                f"Top-level form must be a list starting with 'defmacro' or 'rule', got {form}"
            )

    if rule_ast is None:
        raise SchemeSyntaxError("No 'rule' form found in source")

    # Expand macros in rule AST
    expander = MacroExpander(reg)
    ast = expander.expand(rule_ast)

    # Validate that all operations are in ALLOWED_OPS after expansion
    _validate_operators(ast)

    if not isinstance(ast, list) or len(ast) < 6:
        raise SchemeSyntaxError(
            'Rule must be a list of form (rule "id" :when ... :plan ... [:priority N])'
        )

    if not isinstance(ast[0], Symbol) or ast[0].name != "rule":
        raise SchemeSyntaxError("Top-level form must be 'rule'")

    rule_id_node = ast[1]
    if not isinstance(rule_id_node, str):
        raise SchemeSyntaxError(f"Rule ID must be a string literal, got {type(rule_id_node)}")
    if not RULE_ID_REGEX.match(rule_id_node):
        raise SchemeSyntaxError(
            f"Rule ID '{rule_id_node}' must be kebab-case with version suffix "
            "(e.g. 'open-calculator-v1')"
        )

    when_expr: SchemeNode | None = None
    plan_expr: SchemeNode | None = None
    priority = 0

    idx = 2
    seen_keywords: set[str] = set()
    while idx < len(ast):
        kw_node = ast[idx]
        if not isinstance(kw_node, Keyword):
            raise SchemeSyntaxError(f"Expected keyword at position {idx}, got {kw_node}")

        kw = kw_node.name
        if kw in seen_keywords:
            raise SchemeSyntaxError(
                f"Duplicate keyword '{kw}' in rule definition", kw_node.line, kw_node.col
            )
        seen_keywords.add(kw)

        if idx + 1 >= len(ast):
            raise SchemeSyntaxError(f"Keyword '{kw}' missing value", kw_node.line, kw_node.col)

        val = ast[idx + 1]
        if kw == ":when":
            when_expr = val
        elif kw == ":plan":
            plan_expr = val
        elif kw == ":priority":
            if not isinstance(val, int):
                raise SchemeSyntaxError(f":priority must be an integer, got {val}")
            priority = val
        else:
            raise SchemeSyntaxError(f"Unrecognized rule keyword '{kw}'", kw_node.line, kw_node.col)

        idx += 2

    if when_expr is None:
        raise SchemeSyntaxError("Rule is missing required :when clause")
    if plan_expr is None:
        raise SchemeSyntaxError("Rule is missing required :plan clause")

    # Spec 05 §7 constraint 5: :when must reference at least one state predicate
    if not has_state_predicate(when_expr):
        raise SchemeSyntaxError("Rule :when clause must reference at least one state predicate")

    # Validate :plan structure: (list action*) or (if cond then else)
    _validate_plan_structure(plan_expr)

    source_canonical = to_canonical(ast)
    source_hash = hashlib.sha256(source_canonical.encode("utf-8")).hexdigest()

    return RuleDefinition(
        rule_id=rule_id_node,
        when_expr=when_expr,
        plan_expr=plan_expr,
        priority=priority,
        source_canonical=source_canonical,
        source_hash=source_hash,
    )
