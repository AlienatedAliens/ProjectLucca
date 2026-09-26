"""
Direct unit tests for MicroScheme v2 Parser & Canonical Serializer.
lucca.reasoning.scheme.parser
Spec 05 §2, §3, §7
"""

import pytest

from lucca.core.exceptions import SchemeSyntaxError
from lucca.reasoning.scheme.lexer import Token, tokenize
from lucca.reasoning.scheme.parser import (
    ALLOWED_OPS,
    MAX_NESTING_DEPTH,
    RULE_ID_REGEX,
    STATE_PREDICATES,
    Keyword,
    Parser,
    RuleDefinition,
    Symbol,
    _validate_action_node,
    _validate_operators,
    _validate_plan_structure,
    has_state_predicate,
    parse,
    parse_rule,
    to_canonical,
)


def test_symbol_and_keyword_dataclasses() -> None:
    """Symbol and Keyword dataclasses are frozen with line and col info."""
    sym = Symbol("foo", 2, 4)
    assert sym.name == "foo"
    assert sym.line == 2
    assert sym.col == 4

    kw = Keyword(":bar", 3, 1)
    assert kw.name == ":bar"
    assert kw.line == 3
    assert kw.col == 1

    with pytest.raises(Exception):
        sym.name = "baz"  # type: ignore[misc]

    with pytest.raises(Exception):
        kw.name = ":baz"  # type: ignore[misc]


def test_parse_atoms_and_lists() -> None:
    """parse handles integers, floats, booleans, strings, keywords, symbols, and nested lists."""
    assert parse("42") == 42
    assert parse("-3.14") == -3.14
    assert parse("#t") is True
    assert parse("#f") is False
    assert parse('"hello world"') == "hello world"
    assert parse(":my-kw") == Keyword(":my-kw", 1, 1)
    assert parse("my-sym") == Symbol("my-sym", 1, 1)
    assert parse("()") == []

    parsed_list = parse("(+ 1 2)")
    assert isinstance(parsed_list, list)
    assert len(parsed_list) == 3
    assert parsed_list[0] == Symbol("+", 1, 2)
    assert parsed_list[1] == 1
    assert parsed_list[2] == 2


def test_parse_empty_source_raises() -> None:
    """Empty token source raises SchemeSyntaxError."""
    with pytest.raises(SchemeSyntaxError, match="Empty source"):
        parse("")

    with pytest.raises(SchemeSyntaxError, match="Empty source"):
        Parser([]).parse_all_forms()


def test_parse_unexpected_tokens() -> None:
    """Extra tokens, unexpected closing parenthesis, or unclosed parenthesis raise SchemeSyntaxError."""
    with pytest.raises(SchemeSyntaxError, match="Unexpected token '2' after top-level expression"):
        parse("1 2")

    with pytest.raises(SchemeSyntaxError, match="Unexpected closing parenthesis '\\)'"):
        parse(")")

    with pytest.raises(SchemeSyntaxError, match="Unclosed parenthesis: expected '\\)' before EOF"):
        parse("(+ 1 2")


def test_max_nesting_depth_bomb() -> None:
    """Nesting depth > MAX_NESTING_DEPTH (32) raises SchemeSyntaxError."""
    # Nesting 32 levels is accepted
    valid_nested = "(" * MAX_NESTING_DEPTH + "1" + ")" * MAX_NESTING_DEPTH
    assert isinstance(parse(valid_nested), list)

    # Nesting 33 levels is rejected
    bomb = "(" * (MAX_NESTING_DEPTH + 1) + "1" + ")" * (MAX_NESTING_DEPTH + 1)
    with pytest.raises(SchemeSyntaxError, match=f"Maximum nesting depth of {MAX_NESTING_DEPTH} exceeded"):
        parse(bomb)


def test_rule_id_regex_table_driven() -> None:
    """Table-driven test for RULE_ID_REGEX accept and reject patterns."""
    valid_ids = [
        "open-calculator-v1",
        "turn-off-lights-v2",
        "calc-v0",
        "a-b-c-v999",
        "0-v1",
        "intent1-action2-v1",
        "v-v1",
        "rule-9-v12",
    ]
    invalid_ids = [
        "open_calculator-v1",  # underscore
        "Open-Calculator-v1",  # uppercase
        "open-calculator",  # missing -vN
        "open-calculator-v",  # missing version number
        "open-calculator-v1.0",  # decimal version
        "-open-calculator-v1",  # leading dash
        "open-calculator-v1-",  # trailing dash
        "open--calculator-v1",  # double dash
        "",  # empty
        "open calculator-v1",  # space
        "rule-v",  # missing version digits
        "RULE-v1",  # uppercase
        "rule-v01a",  # non-digit in version
    ]

    for rid in valid_ids:
        assert RULE_ID_REGEX.match(rid) is not None, f"Expected {rid} to match RULE_ID_REGEX"

    for rid in invalid_ids:
        assert RULE_ID_REGEX.match(rid) is None, f"Expected {rid} NOT to match RULE_ID_REGEX"


def test_if_arity_checked_at_parse_time() -> None:
    """The 'if' special form requires 2 or 3 arguments at parse time."""
    # 2 arguments: (if cond then)
    assert parse("(if #t 1)") == [Symbol("if", 1, 2), True, 1]

    # 3 arguments: (if cond then else)
    assert parse("(if #t 1 2)") == [Symbol("if", 1, 2), True, 1, 2]

    # 1 argument: invalid
    with pytest.raises(SchemeSyntaxError, match=r"'if' form requires 2 or 3 arguments, got 1"):
        parse("(if #t)")

    # 4 arguments: invalid
    with pytest.raises(SchemeSyntaxError, match=r"'if' form requires 2 or 3 arguments, got 4"):
        parse("(if #t 1 2 3)")


def test_define_and_shadowing_forbidden() -> None:
    """'define' is forbidden both as a symbol and as an operator."""
    with pytest.raises(SchemeSyntaxError, match="Primitive shadowing or 'define' is forbidden"):
        parse("define")

    with pytest.raises(SchemeSyntaxError, match="Primitive shadowing or 'define' is forbidden"):
        parse("(define x 10)")


def test_has_state_predicate() -> None:
    """has_state_predicate recursively checks for presence of any STATE_PREDICATES."""
    for pred in STATE_PREDICATES:
        assert has_state_predicate([Symbol(pred), "arg"]) is True

    assert has_state_predicate(parse("(and (intent= \"launch\") (not (app-running? \"calc\")))")) is True
    assert has_state_predicate(parse("(+ 1 2)")) is False
    assert has_state_predicate(42) is False
    assert has_state_predicate("string") is False


def test_to_canonical_serialization() -> None:
    """to_canonical produces deterministic canonical string representation."""
    assert to_canonical(True) == "#t"
    assert to_canonical(False) == "#f"
    assert to_canonical(42) == "42"
    assert to_canonical(3.14) == "3.14"
    assert to_canonical('test "quotes" and \n newline \t tab \\ backslash') == (
        r'"test \"quotes\" and \n newline \t tab \\ backslash"'
    )
    assert to_canonical(Symbol("foo")) == "foo"
    assert to_canonical(Keyword(":kw")) == ":kw"
    assert to_canonical([]) == "()"
    assert to_canonical([Symbol("+"), 1, 2]) == "(+ 1 2)"

    # Rule canonical serialization
    rule_node = [
        Symbol("rule"),
        "test-rule-v1",
        Keyword(":when"),
        [Symbol("intent="), "launch"],
        Keyword(":plan"),
        [Symbol("list"), [Symbol("say"), "hello"]],
        Keyword(":priority"),
        5,
    ]
    canonical = to_canonical(rule_node)
    assert canonical == '(rule "test-rule-v1"\n  :when (intent= "launch")\n  :plan (list (say "hello"))\n  :priority 5)'

    with pytest.raises(SchemeSyntaxError, match="Cannot serialize object"):
        to_canonical(object())  # type: ignore[arg-type]


def test_parse_rule_valid() -> None:
    """parse_rule parses a valid rule into a RuleDefinition with canonical source and hash."""
    src = """
    (rule "calc-open-v1"
      :when (and (intent= "launch") (entity-has? "app" "calc"))
      :plan (list (say "launching"))
      :priority 3)
    """
    rule_def = parse_rule(src)
    assert isinstance(rule_def, RuleDefinition)
    assert rule_def.rule_id == "calc-open-v1"
    assert rule_def.priority == 3
    assert len(rule_def.source_hash) == 64
    assert 'rule "calc-open-v1"' in rule_def.source_canonical
    assert ":priority 3" in rule_def.source_canonical


def test_parse_rule_structural_validations() -> None:
    """parse_rule rejects malformed, incomplete, or invalid rule structures."""
    # Top-level form must be 'rule' or 'defmacro'
    with pytest.raises(SchemeSyntaxError, match="Top-level form must be 'defmacro' or 'rule'"):
        parse_rule("(+ 1 2)")

    # Multiple rule forms rejected
    with pytest.raises(SchemeSyntaxError, match="Multiple 'rule' forms found"):
        parse_rule('(rule "r1-v1" :when (intent= "a") :plan (list (say "a"))) (rule "r2-v1" :when (intent= "b") :plan (list (say "b")))')

    # Top-level not a list
    with pytest.raises(SchemeSyntaxError, match="Top-level form must be a list"):
        parse_rule("42")

    # No rule form in source (only macro)
    with pytest.raises(SchemeSyntaxError, match="No 'rule' form found in source"):
        parse_rule("(defmacro m () 1)")

    # Rule id not a string
    with pytest.raises(SchemeSyntaxError, match="Rule ID must be a string literal"):
        parse_rule('(rule 123 :when (intent= "a") :plan (list (say "a")))')

    # Invalid rule id regex
    with pytest.raises(SchemeSyntaxError, match="must be kebab-case with version suffix"):
        parse_rule('(rule "bad_id" :when (intent= "a") :plan (list (say "a")))')

    # Duplicate keyword
    with pytest.raises(SchemeSyntaxError, match="Duplicate keyword ':when'"):
        parse_rule('(rule "r-v1" :when (intent= "a") :when (intent= "b") :plan (list (say "a")))')

    # Missing keyword value
    with pytest.raises(SchemeSyntaxError, match="Keyword ':priority' missing value"):
        parse_rule('(rule "r-v1" :when (intent= "a") :plan (list (say "a")) :priority)')

    # Non-integer priority
    with pytest.raises(SchemeSyntaxError, match=":priority must be an integer"):
        parse_rule('(rule "r-v1" :when (intent= "a") :plan (list (say "a")) :priority "high")')

    # Unrecognized keyword
    with pytest.raises(SchemeSyntaxError, match="Unrecognized rule keyword ':foo'"):
        parse_rule('(rule "r-v1" :when (intent= "a") :plan (list (say "a")) :foo 1)')

    # Rule too short (len < 6)
    with pytest.raises(SchemeSyntaxError, match=r'Rule must be a list of form \(rule "id" :when \.\.\. :plan \.\.\. \[:priority N\]\)'):
        parse_rule('(rule "r-v1" :plan (list (say "a")))')

    # Missing required :when with len >= 6
    with pytest.raises(SchemeSyntaxError, match="Rule is missing required :when clause"):
        parse_rule('(rule "r-v1" :priority 5 :plan (list (say "a")))')

    # Missing required :plan with len >= 6
    with pytest.raises(SchemeSyntaxError, match="Rule is missing required :plan clause"):
        parse_rule('(rule "r-v1" :priority 5 :when (intent= "a"))')

    # :when has no state predicate
    with pytest.raises(SchemeSyntaxError, match=":when clause must reference at least one state predicate"):
        parse_rule('(rule "r-v1" :when (= 1 1) :plan (list (say "a")))')


def test_validate_plan_structure_and_actions() -> None:
    """_validate_plan_structure and _validate_action_node enforce valid action forms."""
    # Plan must be (list ...), (if ...), or (assert ...)
    with pytest.raises(SchemeSyntaxError, match="Rule :plan clause must be of form"):
        _validate_plan_structure(Symbol("invalid"))

    with pytest.raises(SchemeSyntaxError, match="Rule :plan clause must be of form"):
        _validate_plan_structure([Symbol("+"), 1, 2])

    # Valid plans
    _validate_plan_structure([Symbol("list"), [Symbol("say"), "hi"]])
    _validate_plan_structure(
        [
            Symbol("if"),
            Symbol("cond"),
            [Symbol("list"), [Symbol("say"), "then"]],
            [Symbol("list"), [Symbol("say"), "else"]],
        ]
    )
    _validate_plan_structure([Symbol("assert"), "sub", "likes", "obj"])

    # 'if' in plan requiring exactly 3 arguments
    with pytest.raises(SchemeSyntaxError, match="Plan 'if' form requires exactly 3 arguments"):
        _validate_plan_structure([Symbol("if"), Symbol("cond"), [Symbol("list")]])

    # Action validations:
    # 1. tool action
    _validate_action_node([Symbol("tool"), "launch_app", Keyword(":app"), "calc"])
    with pytest.raises(SchemeSyntaxError, match="Tool action requires a string tool name"):
        _validate_action_node([Symbol("tool"), 123])
    with pytest.raises(SchemeSyntaxError, match="Expected keyword in tool call kwargs"):
        _validate_action_node([Symbol("tool"), "launch_app", "not_a_kw", "val"])
    with pytest.raises(SchemeSyntaxError, match="Missing value for keyword"):
        _validate_action_node([Symbol("tool"), "launch_app", Keyword(":app")])

    # 2. say action
    _validate_action_node([Symbol("say"), "message"])
    with pytest.raises(SchemeSyntaxError, match="Say action requires exactly one string argument"):
        _validate_action_node([Symbol("say"), 123])
    with pytest.raises(SchemeSyntaxError, match="Say action requires exactly one string argument"):
        _validate_action_node([Symbol("say"), "a", "b"])

    # 3. assert action
    _validate_action_node([Symbol("assert"), "s", "likes", "o"])
    _validate_action_node([Symbol("assert"), ["s", "likes", "o"]])
    with pytest.raises(SchemeSyntaxError, match="Assert action requires a triple"):
        _validate_action_node([Symbol("assert"), "only_one"])
    with pytest.raises(SchemeSyntaxError, match="Assert action has invalid predicate"):
        _validate_action_node([Symbol("assert"), "s", "INVALID PREDICATE!!", "o"])

    # 4. yield-to-core action
    _validate_action_node([Symbol("yield-to-core"), "need help", Keyword(":key"), "val"])
    with pytest.raises(SchemeSyntaxError, match="yield-to-core requires at least a reason string"):
        _validate_action_node([Symbol("yield-to-core"), 42])

    # 5. interrupt-core action
    _validate_action_node([Symbol("interrupt-core")])
    _validate_action_node([Symbol("interrupt-core"), "emergency"])
    with pytest.raises(SchemeSyntaxError, match="interrupt-core accepts at most one reason string"):
        _validate_action_node([Symbol("interrupt-core"), "r1", "r2"])

    # 6. Unknown action
    with pytest.raises(SchemeSyntaxError, match="Unknown plan action 'bogus'"):
        _validate_action_node([Symbol("bogus")])


def test_validate_operators() -> None:
    """_validate_operators checks that all operators in the AST are in ALLOWED_OPS."""
    valid_ast = parse("(+ 1 2)")
    _validate_operators(valid_ast)

    # Disallowed operator
    invalid_ast = [Symbol("forbidden-op", 1, 1), 1, 2]
    with pytest.raises(SchemeSyntaxError, match="Disallowed operator 'forbidden-op'"):
        _validate_operators(invalid_ast)
