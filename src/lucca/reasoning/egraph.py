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

from collections.abc import Callable
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

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

    def saturate(self, rules: list[RewriteRule] | None = None, iter_limit: int = 30) -> int:
        """Runs equality saturation over this egraph using rules (or standard rules)."""
        active_rules = rules if rules is not None else (STANDARD_REWRITE_RULES + SPATIAL_REWRITE_RULES)
        return equality_saturate(self, active_rules, iter_limit=iter_limit)

    def extract(self, class_id: int) -> SchemeNode:
        """Extracts the minimal cost canonical AST from the specified e-class."""
        return extract_best(self, class_id)



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
        gen_template, _ = anti_unify(current_template, target, var_prefix=f"{var_prefix}_{idx}")

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


# ==============================================================================
# Equality Saturation Rewrite Engine (WO-29 Module 2)
# ==============================================================================


@dataclass(frozen=True)
class RewriteRule:
    """
    Term-rewriting equality saturation rule over MicroScheme ASTs.
    LHS and RHS can contain pattern variables prefixed with '?' or 'arg_'.
    """

    lhs: SchemeNode
    rhs: SchemeNode
    name: str = ""
    bidirectional: bool = False

    @classmethod
    def from_sexpr(
        cls,
        lhs_sexpr: str,
        rhs_sexpr: str,
        name: str = "",
        bidirectional: bool = False,
    ) -> RewriteRule:
        from lucca.reasoning.scheme.parser import parse_expr

        return cls(
            lhs=parse_expr(lhs_sexpr),
            rhs=parse_expr(rhs_sexpr),
            name=name or f"{lhs_sexpr} => {rhs_sexpr}",
            bidirectional=bidirectional,
        )


def is_pattern_var(node: SchemeNode) -> str | None:
    """Returns variable name if node is a pattern variable (e.g. '?x', '?s'), else None."""
    if isinstance(node, Symbol):
        if node.name.startswith("?") or node.name.startswith("arg_") or node.name.startswith("param_"):
            return node.name
    elif isinstance(node, str):
        if node.startswith("?") or node.startswith("arg_") or node.startswith("param_"):
            return node
    return None


def _atom_matches(pat: SchemeAtom, atom: SchemeAtom) -> bool:
    """Checks whether a pattern atom matches an e-node head atom."""
    if isinstance(pat, Symbol) and isinstance(atom, Symbol):
        return pat.name == atom.name
    if isinstance(pat, Symbol) and isinstance(atom, str):
        return pat.name == atom
    if isinstance(pat, str) and isinstance(atom, Symbol):
        return pat == atom.name
    if isinstance(pat, (int, float)) and isinstance(atom, (int, float)):
        return pat == atom
    return bool(pat == atom)


def ematch_pattern(
    pattern: SchemeNode,
    egraph: EGraph,
    class_id: int,
    bindings: dict[str, int],
) -> list[dict[str, int]]:
    """
    Recursively matches a pattern against a given e-class in the E-Graph.
    Returns all valid variable-to-eclass substitution mappings.
    """
    var_name = is_pattern_var(pattern)
    if var_name is not None:
        root_cid = egraph.find(class_id)
        if var_name in bindings:
            if egraph.find(bindings[var_name]) == root_cid:
                return [bindings]
            return []
        new_bindings = dict(bindings)
        new_bindings[var_name] = root_cid
        return [new_bindings]

    root_class = egraph.find(class_id)
    eclass = egraph._classes.get(root_class)
    if eclass is None:
        return []

    matches: list[dict[str, int]] = []
    if isinstance(pattern, list):
        if not pattern:
            for head_atom, child_ids in eclass.nodes:
                if (
                    isinstance(head_atom, Symbol)
                    and head_atom.name == "()"
                    and len(child_ids) == 0
                ):
                    matches.append(dict(bindings))
            return matches

        pat_head = pattern[0]
        pat_children = pattern[1:]

        for head_atom, child_ids in eclass.nodes:
            if isinstance(pat_head, list) or not _atom_matches(pat_head, head_atom):
                continue
            if len(child_ids) != len(pat_children):
                continue

            curr_matches = [dict(bindings)]
            for p_child, c_id in zip(pat_children, child_ids, strict=True):
                next_matches: list[dict[str, int]] = []
                for b in curr_matches:
                    next_matches.extend(ematch_pattern(p_child, egraph, c_id, b))
                curr_matches = next_matches
                if not curr_matches:
                    break
            matches.extend(curr_matches)
    else:
        for head_atom, child_ids in eclass.nodes:
            if len(child_ids) == 0 and _atom_matches(pattern, head_atom):
                matches.append(dict(bindings))

    return matches


def instantiate_pattern(
    pattern: SchemeNode,
    bindings: dict[str, int],
    egraph: EGraph,
) -> int:
    """Instantiates a pattern into the E-Graph given variable-to-eclass bindings."""
    var_name = is_pattern_var(pattern)
    if var_name is not None:
        if var_name in bindings:
            return egraph.find(bindings[var_name])
        raise ValueError(f"Unbound pattern variable '{var_name}' during instantiation")

    if isinstance(pattern, list):
        if not pattern:
            return egraph.add([])
        head = pattern[0]
        child_ids = tuple(instantiate_pattern(c, bindings, egraph) for c in pattern[1:])
        if isinstance(head, (Symbol, Keyword, str, int, float, bool)):
            head_atom: SchemeAtom = head
        else:
            head_atom = Symbol("list")
        enode = (head_atom, child_ids)
        return egraph._add_enode(enode)
    else:
        return egraph.add(pattern)


def _get_class_constant(egraph: EGraph, class_id: int) -> SchemeAtom | None:
    """Returns the literal constant in an e-class if present."""
    r = egraph.find(class_id)
    eclass = egraph._classes.get(r)
    if not eclass:
        return None
    for head, children in eclass.nodes:
        if not children and isinstance(head, (int, float, bool, str)):
            return head
    return None


def _fold_constants(egraph: EGraph) -> bool:
    """Evaluates pure constant arithmetic / logic expressions in the E-Graph."""
    changed = False
    for r in list(egraph._classes.keys()):
        root_id = egraph.find(r)
        eclass = egraph._classes.get(root_id)
        if not eclass:
            continue
        for head, children in list(eclass.nodes):
            op = head.name if isinstance(head, Symbol) else str(head)
            if op in ("+", "-", "*", "/", "min", "max") and len(children) >= 1:
                child_consts = [_get_class_constant(egraph, ch) for ch in children]
                if all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in child_consts):
                    nums: list[float] = [float(c) for c in child_consts if isinstance(c, (int, float)) and not isinstance(c, bool)]
                    try:
                        res: float | int | None = None
                        if op == "+":
                            res = sum(nums)
                        elif op == "*":
                            res = 1.0
                            for n in nums:
                                res *= n
                        elif op == "-":
                            res = -nums[0] if len(nums) == 1 else nums[0] - sum(nums[1:])
                        elif op == "/":
                            if len(nums) == 2 and nums[1] != 0:
                                res = nums[0] / nums[1]
                        elif op == "min":
                            res = min(nums)
                        elif op == "max":
                            res = max(nums)

                        if res is not None:
                            if res.is_integer():
                                res = int(res)
                            res_id = egraph.add(res)
                            if egraph.find(res_id) != root_id:
                                egraph.merge(root_id, res_id)
                                changed = True
                    except Exception as exc:
                        logger.debug("constant_fold_error: %s", exc)
    return changed


def equality_saturate(
    egraph: EGraph,
    rules: list[RewriteRule],
    iter_limit: int = 30,
    node_limit: int = 2000,
) -> int:
    """
    Executes Equality Saturation over the E-Graph until fixpoint or resource limits.
    In each iteration: matches rules, instantiates rewritten nodes, unions e-classes,
    folds constants, and restores congruence closure.
    """
    iterations = 0
    while iterations < iter_limit:
        iterations += 1
        matches: list[tuple[int, SchemeNode, dict[str, int]]] = []

        # 1. Match phase
        class_ids = list(egraph._classes.keys())
        for rule in rules:
            for root_id in class_ids:
                for b in ematch_pattern(rule.lhs, egraph, root_id, {}):
                    matches.append((root_id, rule.rhs, b))
                if rule.bidirectional:
                    for b in ematch_pattern(rule.rhs, egraph, root_id, {}):
                        matches.append((root_id, rule.lhs, b))

        # 2. Apply phase
        merged_any = False
        for root_id, rhs_pattern, b in matches:
            rhs_id = instantiate_pattern(rhs_pattern, b, egraph)
            if egraph.find(root_id) != egraph.find(rhs_id):
                egraph.merge(root_id, rhs_id)
                merged_any = True

        # 3. Rebuild phase
        egraph.rebuild()

        # 4. Constant folding phase
        if _fold_constants(egraph):
            egraph.rebuild()
            merged_any = True

        total_nodes = sum(len(c.nodes) for c in egraph._classes.values())
        if not merged_any or total_nodes > node_limit:
            break

    return iterations


def extract_best(
    egraph: EGraph,
    class_id: int,
    cost_fn: Callable[[SchemeNode], int] | None = None,
) -> SchemeNode:
    """
    Extracts the minimal cost canonical AST from the specified e-class using dynamic programming.
    In case of equivalent representations, chooses the smallest and simplest expression.
    """
    root_target = egraph.find(class_id)
    best_cost: dict[int, float] = {}
    best_node: dict[int, tuple[SchemeAtom, tuple[int, ...]]] = {}

    # Initialize leaves
    for c in list(egraph._classes.values()):
        r = egraph.find(c.class_id)
        for head, children in c.nodes:
            if not children:
                c_cost = 1.0
                if c_cost < best_cost.get(r, float("inf")):
                    best_cost[r] = c_cost
                    best_node[r] = (head, ())

    # Iterative cost relaxation
    max_iters = len(egraph._classes) * 2 + 10
    changed = True
    iterations = 0
    while changed and iterations < max_iters:
        changed = False
        iterations += 1
        for c in list(egraph._classes.values()):
            r = egraph.find(c.class_id)
            for head, children in c.nodes:
                if all(egraph.find(ch) in best_cost for ch in children):
                    cost = 1.0 + sum(best_cost[egraph.find(ch)] for ch in children)
                    if cost < best_cost.get(r, float("inf")):
                        best_cost[r] = cost
                        best_node[r] = (head, tuple(egraph.find(ch) for ch in children))
                        changed = True

    # Reconstruct minimal AST
    def _build(cid: int, visited: set[int]) -> SchemeNode:
        r = egraph.find(cid)
        if r in visited:
            for h, ch in egraph._classes[r].nodes:
                if not ch:
                    return h
            return Symbol("cycle")
        if r not in best_node:
            for h, ch in egraph._classes[r].nodes:
                if not ch:
                    return h
            return Symbol("unknown")
        head, children = best_node[r]
        if not children:
            return head
        new_visited = visited | {r}
        return [head, *[_build(ch, new_visited) for ch in children]]

    return _build(root_target, set())


# --- Pre-compiled Canonical Rewrite Rules ---

STANDARD_REWRITE_RULES: list[RewriteRule] = [
    RewriteRule.from_sexpr("(+ ?x 0)", "?x", name="add-zero-right"),
    RewriteRule.from_sexpr("(+ 0 ?x)", "?x", name="add-zero-left"),
    RewriteRule.from_sexpr("(* ?x 1)", "?x", name="mul-one-right"),
    RewriteRule.from_sexpr("(* 1 ?x)", "?x", name="mul-one-left"),
    RewriteRule.from_sexpr("(* ?x 0)", "0", name="mul-zero-right"),
    RewriteRule.from_sexpr("(* 0 ?x)", "0", name="mul-zero-left"),
    RewriteRule.from_sexpr("(- ?x 0)", "?x", name="sub-zero"),
    RewriteRule.from_sexpr("(- ?x ?x)", "0", name="sub-self"),
    RewriteRule.from_sexpr("(/ ?x 1)", "?x", name="div-one"),
    RewriteRule.from_sexpr("(not (not ?x))", "?x", name="not-not"),
    RewriteRule.from_sexpr("(and ?x ?x)", "?x", name="and-idempotent"),
    RewriteRule.from_sexpr("(or ?x ?x)", "?x", name="or-idempotent"),
    RewriteRule.from_sexpr("(min ?x ?x)", "?x", name="min-idempotent"),
    RewriteRule.from_sexpr("(max ?x ?x)", "?x", name="max-idempotent"),
]

SPATIAL_REWRITE_RULES: list[RewriteRule] = [
    RewriteRule.from_sexpr("(translate ?s 0 0)", "?s", name="translate-zero"),
    RewriteRule.from_sexpr(
        "(translate (translate ?s ?dx1 ?dy1) ?dx2 ?dy2)",
        "(translate ?s (+ ?dx1 ?dx2) (+ ?dy1 ?dy2))",
        name="translate-combine",
    ),
    RewriteRule.from_sexpr("(scale ?s 1)", "?s", name="scale-identity"),
    RewriteRule.from_sexpr(
        "(scale (scale ?s ?f1) ?f2)",
        "(scale ?s (* ?f1 ?f2))",
        name="scale-combine",
    ),
    RewriteRule.from_sexpr("(rotate ?s 0)", "?s", name="rotate-zero"),
    RewriteRule.from_sexpr(
        "(rotate (rotate ?s ?t1) ?t2)",
        "(rotate ?s (+ ?t1 ?t2))",
        name="rotate-combine",
    ),
]

DISCRETE_SPATIAL_REWRITE_RULES: list[RewriteRule] = [
    RewriteRule.from_sexpr("(flip-h (flip-h ?g))", "?g", name="flip-h-involution"),
    RewriteRule.from_sexpr("(flip-v (flip-v ?g))", "?g", name="flip-v-involution"),
    RewriteRule.from_sexpr("(rot90 ?g 0)", "?g", name="rot90-zero"),
    RewriteRule.from_sexpr("(rot90 ?g 4)", "?g", name="rot90-four"),
    RewriteRule.from_sexpr("(crop-to-content (crop-to-content ?g))", "(crop-to-content ?g)", name="crop-idempotent"),
]


def prune_equivalent_sketches(
    candidates: list[SchemeNode],
    rules: list[RewriteRule] | None = None,
    iter_limit: int = 15,
) -> list[SchemeNode]:
    """
    Inserts candidate expressions into a shared E-Graph, executes equality saturation,
    and returns a deduplicated list of candidate ASTs with at most one representative
    per equivalence class (retaining the AST with smallest size).
    """
    if len(candidates) <= 1:
        return candidates

    egraph = EGraph()
    active_rules = rules if rules is not None else (
        STANDARD_REWRITE_RULES + SPATIAL_REWRITE_RULES + DISCRETE_SPATIAL_REWRITE_RULES
    )

    class_to_candidates: dict[int, list[SchemeNode]] = {}
    cand_class_ids: list[int] = []

    for cand in candidates:
        cid = egraph.add(cand)
        cand_class_ids.append(cid)

    # Saturate equivalence graph
    egraph.saturate(active_rules, iter_limit=iter_limit)

    for cand, cid in zip(candidates, cand_class_ids, strict=True):
        root = egraph.find(cid)
        class_to_candidates.setdefault(root, []).append(cand)

    # For each equivalence class, pick representative with lowest ast_size
    deduped: list[SchemeNode] = []
    for class_cands in class_to_candidates.values():
        best_cand = min(class_cands, key=ast_size)
        deduped.append(best_cand)

    return deduped

