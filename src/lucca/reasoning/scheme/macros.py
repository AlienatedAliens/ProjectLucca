"""
MicroScheme Bounded Macro System
Spec 05 Proposal D (D-REAS-05)
Provides hygienic compile-time macro expansion with recursion depth and step bounds.
"""

import copy
from dataclasses import dataclass

from lucca.core.exceptions import SchemeSyntaxError
from lucca.reasoning.scheme.parser import (
    ALLOWED_OPS,
    SchemeNode,
    Symbol,
)

MAX_MACRO_DEPTH = 8
MAX_MACRO_STEPS = 64


@dataclass(frozen=True)
class MacroDefinition:
    name: str
    params: list[str]
    body: SchemeNode
    doc: str = ""


class MacroRegistry:
    def __init__(self, macros: dict[str, MacroDefinition] | None = None) -> None:
        self._macros: dict[str, MacroDefinition] = dict(macros) if macros else {}

    def register(self, macro: MacroDefinition) -> None:
        if macro.name in ALLOWED_OPS:
            raise SchemeSyntaxError(f"Cannot define macro with primitive name '{macro.name}'")
        self._macros[macro.name] = macro

    def get(self, name: str) -> MacroDefinition | None:
        return self._macros.get(name)

    def has(self, name: str) -> bool:
        return name in self._macros

    def __contains__(self, name: str) -> bool:
        return name in self._macros

    def all_macros(self) -> dict[str, MacroDefinition]:
        return dict(self._macros)


def parse_defmacro(node: SchemeNode) -> MacroDefinition:
    """
    Parses a (defmacro <name> (<params>...) <body>) AST node into a MacroDefinition.
    """
    if not isinstance(node, list) or len(node) < 4:
        raise SchemeSyntaxError("defmacro must be of form: (defmacro <name> (<params>...) <body>)")

    head = node[0]
    if not isinstance(head, Symbol) or head.name != "defmacro":
        raise SchemeSyntaxError(f"Expected 'defmacro' at head of form, got {head}")

    name_node = node[1]
    if not isinstance(name_node, Symbol):
        raise SchemeSyntaxError(f"Macro name must be a symbol, got {name_node}")

    name = name_node.name
    if name in ALLOWED_OPS:
        raise SchemeSyntaxError(
            f"Cannot define macro shadowing primitive '{name}'",
            name_node.line,
            name_node.col,
        )

    params_node = node[2]
    if not isinstance(params_node, list):
        msg = f"Macro parameter list must be a list of symbols, got {params_node}"
        raise SchemeSyntaxError(msg)

    params: list[str] = []
    seen_params: set[str] = set()
    for p in params_node:
        if not isinstance(p, Symbol):
            raise SchemeSyntaxError(f"Macro parameter must be a symbol, got {p}")
        if p.name in seen_params:
            msg = f"Duplicate macro parameter '{p.name}' in definition of '{name}'"
            raise SchemeSyntaxError(msg)
        seen_params.add(p.name)
        params.append(p.name)

    body = node[3]
    return MacroDefinition(name=name, params=params, body=body)


class MacroExpander:
    """
    Expands macros in MicroScheme AST nodes prior to type checking and compilation.
    Enforces strict recursion depth (<=8) and step bounds (<=64) to prevent expansion bombs.
    """

    def __init__(self, registry: MacroRegistry | None = None) -> None:
        self.registry = registry or MacroRegistry()
        self.step_count = 0

    def expand(self, node: SchemeNode, depth: int = 0) -> SchemeNode:
        if depth > MAX_MACRO_DEPTH:
            raise SchemeSyntaxError(
                f"Macro expansion depth limit exceeded ({MAX_MACRO_DEPTH}): "
                "possible circular or infinite macro recursion"
            )

        if not isinstance(node, list) or not node:
            return node

        # Check if list represents a macro invocation: (macro_name arg1 arg2 ...)
        head = node[0]
        if isinstance(head, Symbol) and self.registry.has(head.name):
            macro_def = self.registry.get(head.name)
            if macro_def is None:
                return node

            args = node[1:]
            if len(args) != len(macro_def.params):
                raise SchemeSyntaxError(
                    f"Macro '{macro_def.name}' expects {len(macro_def.params)} arguments, "
                    f"got {len(args)}"
                )

            self.step_count += 1
            if self.step_count > MAX_MACRO_STEPS:
                raise SchemeSyntaxError(
                    f"Macro expansion step limit exceeded ({MAX_MACRO_STEPS}): "
                    "macro expansion exceeds complexity budget"
                )

            # Substitute parameter symbols with argument nodes
            subst_map: dict[str, SchemeNode] = dict(zip(macro_def.params, args, strict=True))
            expanded_body = self._substitute(macro_def.body, subst_map)

            # Recursively expand the result in case macro expands to another macro
            return self.expand(expanded_body, depth=depth + 1)

        # Recursively expand all children
        expanded_children: list[SchemeNode] = []
        for child in node:
            expanded_children.append(self.expand(child, depth=depth))
        return expanded_children

    def _substitute(self, template: SchemeNode, subst_map: dict[str, SchemeNode]) -> SchemeNode:
        if isinstance(template, Symbol):
            if template.name in subst_map:
                return copy.deepcopy(subst_map[template.name])
            return template
        elif isinstance(template, list):
            return [self._substitute(child, subst_map) for child in template]
        else:
            return template
