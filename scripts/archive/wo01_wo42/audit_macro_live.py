from lucca.reasoning.egraph import synthesize_macro_from_patterns, ast_size
from lucca.reasoning.scheme.parser import parse_rule

p1 = parse_rule("""(rule "r1-v1"
  :when (and (intent= "launch_app") (entity-has? "app" "calc") (not (app-running? "calc")))
  :plan (list (say "hi")) :priority 1)""").when_expr

p2 = parse_rule("""(rule "r2-v1"
  :when (and (intent= "launch_app") (entity-has? "app" "notepad") (not (app-running? "notepad")))
  :plan (list (say "hi")) :priority 1)""").when_expr

p3 = parse_rule("""(rule "r3-v1"
  :when (and (intent= "launch_app") (entity-has? "app" "edge") (not (app-running? "edge")))
  :plan (list (say "hi")) :priority 1)""").when_expr

mdef, sexpr = synthesize_macro_from_patterns("when-launch-app", [p1, p2, p3])
print("Synthesized Macro:")
print(sexpr)
print("Metadata Doc:", mdef.doc)
orig = sum(ast_size(p) for p in [p1, p2, p3])
body_sz = ast_size(mdef.body)
call_ovh = 1 + len(mdef.params)
macro_def_sz = 1 + len(mdef.params) + body_sz
comp = macro_def_sz + (3 * call_ovh)
savings = orig - comp
print(f"Original AST Size: {orig}")
print(f"Template Body Size: {body_sz}")
print(f"Params Count: {len(mdef.params)} ({mdef.params})")
print(f"Compressed AST Size: {comp}")
print(f"Delta Size (Savings): {savings} AST nodes")
