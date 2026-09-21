from lucca.reasoning.smt_verifier import SMTVerifier, StateContext
from lucca.reasoning.scheme.parser import parse_rule
import z3

# 1. UNSATISFIABLE rule
source_unsat = '''(rule "contradictory-rule-v1"
  :when (and (intent= "launch_app")
             (intent= "file_read"))
  :plan (list (tool "launch_app" :app "calculator"))
  :priority 5)'''

rdef_unsat = parse_rule(source_unsat)
verifier = SMTVerifier(timeout_ms=500)
ctx_unsat = StateContext()
when_z3_unsat = verifier._translate_expr(rdef_unsat.when_expr, ctx_unsat)

solver_unsat = z3.Solver()
for ax in ctx_unsat.get_axioms():
    solver_unsat.add(ax)
solver_unsat.add(when_z3_unsat)

print("=== UNSATISFIABLE RULE AUDIT ===")
print("MicroScheme Source:\n", source_unsat)
print("\nTranslated Z3 Expression:\n", when_z3_unsat)
print("\nZ3 Solver Assertions Sent:")
for a in solver_unsat.assertions():
    print(" ", a)
check_unsat = solver_unsat.check()
print("\nDirect Z3 Solver Result:", check_unsat)
res_unsat = verifier.verify_source(source_unsat)
print("SMTVerifier Status:", res_unsat.status)
print("SMTVerifier Reasons:", res_unsat.reasons)

# 2. TAUTOLOGY rule
source_taut = '''(rule "tautology-rule-v1"
  :when (or (intent= "launch_app")
            (not (intent= "launch_app")))
  :plan (list (tool "launch_app" :app "calculator"))
  :priority 5)'''

rdef_taut = parse_rule(source_taut)
ctx_taut = StateContext()
when_z3_taut = verifier._translate_expr(rdef_taut.when_expr, ctx_taut)

solver_taut = z3.Solver()
for ax in ctx_taut.get_axioms():
    solver_taut.add(ax)
solver_taut.add(z3.Not(when_z3_taut))

print("\n=== TAUTOLOGY RULE AUDIT ===")
print("MicroScheme Source:\n", source_taut)
print("\nTranslated Z3 Expression:\n", when_z3_taut)
print("\nZ3 Solver Negation Assertions Sent (Checking if Not(When) is UNSAT):")
for a in solver_taut.assertions():
    print(" ", a)
check_taut = solver_taut.check()
print("\nDirect Z3 Solver Result for Not(P):", check_taut)
res_taut = verifier.verify_source(source_taut)
print("SMTVerifier Status:", res_taut.status)
print("SMTVerifier Reasons:", res_taut.reasons)
