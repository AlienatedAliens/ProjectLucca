"""
Direct unit tests for MicroScheme v2 Bounded Macro System.
lucca.reasoning.scheme.macros
Spec 05 Proposal D (D-REAS-05)
"""

import pytest

from lucca.core.exceptions import SchemeSyntaxError
from lucca.reasoning.scheme.macros import (
    MAX_MACRO_DEPTH,
    MAX_MACRO_STEPS,
    MacroDefinition,
    MacroExpander,
    MacroRegistry,
    parse_defmacro,
)
from lucca.reasoning.scheme.parser import ALLOWED_OPS, Symbol, parse


def test_macro_definition_dataclass() -> None:
    """MacroDefinition stores name, params, body, and optional doc."""
    m = MacroDefinition(
        name="my-macro",
        params=["x", "y"],
        body=[Symbol("+"), Symbol("x"), Symbol("y")],
        doc="Adds two values",
    )
    assert m.name == "my-macro"
    assert m.params == ["x", "y"]
    assert m.doc == "Adds two values"


def test_macro_registry_registration_and_lookup() -> None:
    """MacroRegistry correctly registers, retrieves, and checks existence of macros."""
    reg = MacroRegistry()
    macro = MacroDefinition("when-calc", ["body"], [Symbol("and"), True, Symbol("body")])
    reg.register(macro)

    assert reg.has("when-calc") is True
    assert ("when-calc" in reg) is True
    assert reg.get("when-calc") == macro
    assert reg.has("nonexistent") is False
    assert reg.get("nonexistent") is None


def test_macro_registry_refuses_shadowing_primitives() -> None:
    """MacroRegistry raises SchemeSyntaxError if a macro name shadows an ALLOWED_OPS primitive."""
    import re
    reg = MacroRegistry()
    for prim in ["+", "and", "rule", "say", "tool", "list", "assert"]:
        assert prim in ALLOWED_OPS
        bad_macro = MacroDefinition(prim, ["x"], Symbol("x"))
        with pytest.raises(SchemeSyntaxError, match=f"Cannot define macro with primitive name '{re.escape(prim)}'"):
            reg.register(bad_macro)


def test_parse_defmacro_valid() -> None:
    """parse_defmacro successfully parses a valid defmacro AST."""
    ast = parse('(defmacro when-app (app-name body) (and (intent= "launch_app") (entity-has? "app" app-name) body))')
    macro_def = parse_defmacro(ast)
    assert macro_def.name == "when-app"
    assert macro_def.params == ["app-name", "body"]
    assert isinstance(macro_def.body, list)


def test_parse_defmacro_errors() -> None:
    """parse_defmacro enforces strict structural rules and raises SchemeSyntaxError."""
    # Not a list or length < 4
    with pytest.raises(SchemeSyntaxError, match="defmacro must be of form"):
        parse_defmacro(Symbol("defmacro"))
    with pytest.raises(SchemeSyntaxError, match="defmacro must be of form"):
        parse_defmacro([Symbol("defmacro"), Symbol("m"), []])

    # Head not 'defmacro'
    with pytest.raises(SchemeSyntaxError, match="Expected 'defmacro' at head"):
        parse_defmacro([Symbol("other"), Symbol("m"), [], Symbol("x")])

    # Macro name not a symbol
    with pytest.raises(SchemeSyntaxError, match="Macro name must be a symbol"):
        parse_defmacro([Symbol("defmacro"), "m_string", [], Symbol("x")])

    # Macro name shadows primitive
    with pytest.raises(SchemeSyntaxError, match="Cannot define macro shadowing primitive"):
        parse_defmacro([Symbol("defmacro"), Symbol("+"), [], Symbol("x")])

    # Params not a list
    with pytest.raises(SchemeSyntaxError, match="Macro parameter list must be a list"):
        parse_defmacro([Symbol("defmacro"), Symbol("m"), Symbol("not-list"), Symbol("x")])

    # Param not a symbol
    with pytest.raises(SchemeSyntaxError, match="Macro parameter must be a symbol"):
        parse_defmacro([Symbol("defmacro"), Symbol("m"), [123], Symbol("x")])

    # Duplicate parameter
    with pytest.raises(SchemeSyntaxError, match="Duplicate macro parameter 'a'"):
        parse_defmacro([Symbol("defmacro"), Symbol("m"), [Symbol("a"), Symbol("a")], Symbol("x")])


def test_macro_expander_basic_and_nested() -> None:
    """MacroExpander expands macros with parameter substitution and supports nested expansion."""
    reg = MacroRegistry()
    # (defmacro double (x) (+ x x))
    m1 = MacroDefinition("double", ["x"], [Symbol("+"), Symbol("x"), Symbol("x")])
    # (defmacro quad (x) (double (double x)))
    m2 = MacroDefinition(
        "quad",
        ["x"],
        [Symbol("double"), [Symbol("double"), Symbol("x")]],
    )
    reg.register(m1)
    reg.register(m2)

    expander = MacroExpander(reg)

    # Simple expansion: (double 5) -> (+ 5 5)
    node1 = [Symbol("double"), 5]
    expanded1 = expander.expand(node1)
    assert expanded1 == [Symbol("+"), 5, 5]

    # Nested expansion: (quad 2) -> (+ (+ 2 2) (+ 2 2))
    node2 = [Symbol("quad"), 2]
    expander.step_count = 0
    expanded2 = expander.expand(node2)
    assert expanded2 == [
        Symbol("+"),
        [Symbol("+"), 2, 2],
        [Symbol("+"), 2, 2],
    ]


def test_macro_expander_arity_mismatch() -> None:
    """MacroExpander raises SchemeSyntaxError if argument count does not match macro arity."""
    reg = MacroRegistry()
    m = MacroDefinition("my-macro", ["a", "b"], [Symbol("+"), Symbol("a"), Symbol("b")])
    reg.register(m)

    expander = MacroExpander(reg)
    with pytest.raises(SchemeSyntaxError, match="Macro 'my-macro' expects 2 arguments, got 1"):
        expander.expand([Symbol("my-macro"), 1])

    with pytest.raises(SchemeSyntaxError, match="Macro 'my-macro' expects 2 arguments, got 3"):
        expander.expand([Symbol("my-macro"), 1, 2, 3])


def test_macro_expander_max_depth_bound() -> None:
    """Macro expansion depth > MAX_MACRO_DEPTH (8) raises SchemeSyntaxError."""
    reg = MacroRegistry()
    # Self-recursive infinite macro: (defmacro inf (x) (inf x))
    inf_macro = MacroDefinition("inf", ["x"], [Symbol("inf"), Symbol("x")])
    reg.register(inf_macro)

    expander = MacroExpander(reg)
    with pytest.raises(SchemeSyntaxError, match=f"Macro expansion depth limit exceeded \\({MAX_MACRO_DEPTH}\\)"):
        expander.expand([Symbol("inf"), 1])


def test_macro_expander_max_steps_bound() -> None:
    """Macro expansion steps > MAX_MACRO_STEPS (64) raises SchemeSyntaxError."""
    reg = MacroRegistry()
    # Leaf macro: (defmacro leaf (x) (+ x 1))
    leaf_macro = MacroDefinition("leaf", ["x"], [Symbol("+"), Symbol("x"), 1])
    reg.register(leaf_macro)

    # 70 macro invocations in a single list form (depth 1, but 70 expansion steps > 64)
    many_macros: list[object] = [Symbol("list")] + [[Symbol("leaf"), i] for i in range(70)]

    expander = MacroExpander(reg)
    with pytest.raises(SchemeSyntaxError, match=f"Macro expansion step limit exceeded \\({MAX_MACRO_STEPS}\\)"):
        expander.expand(many_macros)
