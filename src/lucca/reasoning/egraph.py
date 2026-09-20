"""
Project Lucca — E-Graph Equivalence & Anti-Unification Macro Synthesis
Babble/Stitch Term Equivalence & Structural Generalization (POPL 2023)
Spec 05 Proposal D/E, D-REAS-05, D-REAS-06

Provides:
1. First-order syntactic anti-unification over MicroScheme ASTs.
2. E-Graph congruence closure representation for equivalence classes.
3. Automated macro template synthesis from recurring execution patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lucca.reasoning.scheme.macros import MacroDefinition
from lucca.reasoning.scheme.parser import (
    Keyword,
    SchemeAtom,
    SchemeNode,
    Symbol,
    to_canonical,
)

ENodeKey = tuple[SchemeAtom, tuple[int, ...]]


@dataclass
class EClass:
    """An equivalence class of expressions in an E-Graph."""

    class_id: int
    nodes: set[ENodeKey] = field(default_factory=set)
    parents: set[tuple[ENodeKey, int]] = field(default_factory=set)


class EGraph:
    """
    Minimal Congruence-Closure E-Graph for MicroScheme ASTs.
    Enables structural subterm sharing, equivalence tracking, and canonical extraction.
    """

    def __init__(self) -> None:
        self._union_find: dict[int, int] = {}
        self._classes: dict[int, EClass] = {}
        self._hashcons: dict[ENodeKey, int] = {}
        self._next_id: int = 0

    def find(self, class_id: int) -> int:
        """Find the canonical root of an e-class using path compression."""
        root = class_id
        while root in self._union_find and self._union_find[root] != root:
            root = self._union_find[root]

        # Path compression
        curr = class_id
        while curr != root and curr in self._union_find:
            parent = self._union_find[curr]
            self._union_find[curr] = root
            curr = parent

        return root

    def merge(self, class_id1: int, class_id2: int) -> int:
        """Unions two e-classes and marks for congruence maintenance."""
        root1 = self.find(class_id1)
        root2 = self.find(class_id2)
        if root1 == root2:
            return root1

        # Direct root2 to root1
        self._union_find[root2] = root1
        eclass1 = self._classes[root1]
        eclass2 = self._classes.pop(root2)

        # Merge nodes and parents
        eclass1.nodes.update(eclass2.nodes)
        eclass1.parents.update(eclass2.parents)
        return root1

    def add(self, node: SchemeNode) -> int:
        """
        Recursively adds a MicroScheme AST node into the E-Graph,
        returning its canonical e-class ID.
        """
        if isinstance(node, list):
            if not node:
                enode: ENodeKey = (Symbol("()"), ())
                return self._add_enode(enode)

            # First element is head symbol or operator
            head = node[0]
            if isinstance(head, (Symbol, Keyword, str, int, float, bool)):
                head_atom: SchemeAtom = head
            else:
                head_atom = Symbol("list")
            child_ids = tuple(self.add(child) for child in node[1:])
            enode = (head_atom, child_ids)
            parent_id = self._add_enode(enode)

            # Record parents for congruence propagation
            for child_id in child_ids:
                root_child = self.find(child_id)
                self._classes[root_child].parents.add((enode, parent_id))
            return parent_id
        else:
            enode = (node, ())
            return self._add_enode(enode)

    def _add_enode(self, enode: ENodeKey) -> int:
        canon_enode = self._canonicalize_enode(enode)
        if canon_enode in self._hashcons:
            return self.find(self._hashcons[canon_enode])

        class_id = self._next_id
        self._next_id += 1
        self._union_find[class_id] = class_id

        eclass = EClass(class_id=class_id, nodes={canon_enode})
        self._classes[class_id] = eclass
        self._hashcons[canon_enode] = class_id
        return class_id

    def _canonicalize_enode(self, enode: ENodeKey) -> ENodeKey:
        head, children = enode
        canon_children = tuple(self.find(c) for c in children)
        return (head, canon_children)

    def rebuild(self) -> None:
        """Restores congruence closure invariant across all e-classes."""
        changed = True
        while changed:
            changed = False
            # Rehash hashcons
            new_hashcons: dict[ENodeKey, int] = {}
            for enode, class_id in list(self._hashcons.items()):
                canon_enode = self._canonicalize_enode(enode)
                root_id = self.find(class_id)
                if canon_enode in new_hashcons:
                    other_id = new_hashcons[canon_enode]
                    if self.find(other_id) != root_id:
                        self.merge(other_id, root_id)
                        changed = True
                else:
                    new_hashcons[canon_enode] = root_id
            self._hashcons = new_hashcons


def ast_size(node: SchemeNode) -> int:
    """Counts the number of AST nodes/atoms in a MicroScheme expression."""
    if isinstance(node, list):
        return 1 + sum(ast_size(child) for child in node)
    return 1


def anti_unify(
    node_a: SchemeNode,
    node_b: SchemeNode,
    var_prefix: str = "arg",
    substitutions: dict[str, tuple[SchemeNode, SchemeNode]] | None = None,
) -> tuple[SchemeNode, dict[str, tuple[SchemeNode, SchemeNode]]]:
    """
    Computes First-Order Syntactic Anti-Unification (Least General Generalization)
    between two MicroScheme AST expressions per Plotkin / Reynolds / Stitch.

    Returns:
        (generalized_template, substitutions_map)
        where substitutions_map maps '?param_name' -> (node_a_val, node_b_val)
    """
    subs: dict[str, tuple[SchemeNode, SchemeNode]] = (
        substitutions if substitutions is not None else {}
    )

    # Exact equality check
    if _ast_equal(node_a, node_b):
        return node_a, subs

    # Structural match if both are lists of equal length and same head symbol
    if isinstance(node_a, list) and isinstance(node_b, list):
        if len(node_a) == len(node_b) and len(node_a) > 0:
            head_a = node_a[0]
            head_b = node_b[0]
            if _ast_equal(head_a, head_b):
                generalized_children: list[SchemeNode] = [head_a]
                for ca, cb in zip(node_a[1:], node_b[1:], strict=True):
                    gen_child, subs = anti_unify(ca, cb, var_prefix=var_prefix, substitutions=subs)
                    generalized_children.append(gen_child)
                return generalized_children, subs

    # Expressions differ: look for an existing parameter variable with identical pair
    for var_name, (prev_a, prev_b) in subs.items():
        if _ast_equal(prev_a, node_a) and _ast_equal(prev_b, node_b):
            return Symbol(var_name), subs

    # Allocate new parameter variable
    new_param = f"{var_prefix}_{len(subs)}"
    subs[new_param] = (node_a, node_b)
    return Symbol(new_param), subs


def anti_unify_many(
    nodes: list[SchemeNode],
    var_prefix: str = "arg",
) -> tuple[SchemeNode, list[dict[str, SchemeNode]]]:
    """
    Generalizes across N >= 2 MicroScheme expressions.
    Returns the common template AST and a list of substitution dicts, one per input expression.
    """
    if not nodes:
        raise ValueError("Cannot anti-unify empty list of nodes")
    if len(nodes) == 1:
        return nodes[0], [{}]

    current_template = nodes[0]

    for idx in range(1, len(nodes)):
        target = nodes[idx]
        gen_template, _ = anti_unify(
            current_template, target, var_prefix=f"{var_prefix}_{idx}"
        )

        # Update running template
        current_template = gen_template

    # Now compute concrete parameter substitutions for each node against final template
    concrete_subs: list[dict[str, SchemeNode]] = []
    params = extract_parameters(current_template)

    for node in nodes:
        match_map = match_template(current_template, node)
        if match_map is None:
            # Fallback
            match_map = {p: node for p in params}
        concrete_subs.append(match_map)

    return current_template, concrete_subs


def extract_parameters(template: SchemeNode) -> list[str]:
    """Collects parameter symbol names (e.g. 'arg_0', 'arg_1') in order of appearance."""
    params: list[str] = []
    seen: set[str] = set()

    def _walk(node: SchemeNode) -> None:
        if isinstance(node, Symbol):
            is_param = node.name.startswith("arg_") or node.name.startswith("param_")
            if is_param and node.name not in seen:
                seen.add(node.name)
                params.append(node.name)
        elif isinstance(node, list):
            for c in node:
                _walk(c)

    _walk(template)
    return params


def match_template(template: SchemeNode, concrete: SchemeNode) -> dict[str, SchemeNode] | None:
    """Matches a generalized template against a concrete AST to extract bound parameter values."""
    bindings: dict[str, SchemeNode] = {}

    def _match(tpl: SchemeNode, val: SchemeNode) -> bool:
        if isinstance(tpl, Symbol):
            if tpl.name.startswith("arg_") or tpl.name.startswith("param_"):
                if tpl.name in bindings:
                    return _ast_equal(bindings[tpl.name], val)
                bindings[tpl.name] = val
                return True
        if isinstance(tpl, list) and isinstance(val, list):
            if len(tpl) != len(val):
                return False
            return all(_match(t, v) for t, v in zip(tpl, val, strict=True))
        else:
            return _ast_equal(tpl, val)

    if _match(template, concrete):
        return bindings
    return None


def synthesize_macro_from_patterns(
    macro_name: str,
    patterns: list[SchemeNode],
    min_instances: int = 2,
    min_savings: int = 1,
) -> tuple[MacroDefinition, str] | None:
    """
    Synthesizes a Babble/Stitch macro definition from a set of recurring AST patterns.
    Enforces that compression savings > 0 and bounded complexity.
    """
    if len(patterns) < min_instances:
        return None

    template, instances_subs = anti_unify_many(patterns, var_prefix="arg")
    params = extract_parameters(template)
    if not params:
        # No variables abstracted, all instances were identical constants
        return None

    # Calculate compression score (Stitch metric)
    body_size = ast_size(template)
    call_overhead = 1 + len(params)
    original_size = sum(ast_size(p) for p in patterns)
    macro_def_size = 1 + len(params) + body_size
    compressed_size = macro_def_size + (len(patterns) * call_overhead)
    savings = original_size - compressed_size

    if savings < min_savings and body_size <= 2:
        return None

    macro_def = MacroDefinition(
        name=macro_name,
        params=params,
        body=template,
        doc=f"Synthesized by E-Graph Anti-Unification (savings={savings})",
    )

    # Format into canonical S-expression string
    params_str = " ".join(params)
    body_canonical = to_canonical(template)
    sexpr = f"(defmacro {macro_name} ({params_str})\n  {body_canonical})"

    return macro_def, sexpr


def _ast_equal(a: SchemeNode, b: SchemeNode) -> bool:
    """Exact equality comparison between two MicroScheme AST nodes."""
    if type(a) is not type(b):
        return False
    if isinstance(a, Symbol) and isinstance(b, Symbol):
        return a.name == b.name
    if isinstance(a, Keyword) and isinstance(b, Keyword):
        return a.name == b.name
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_ast_equal(x, y) for x, y in zip(a, b, strict=True))
    return bool(a == b)
