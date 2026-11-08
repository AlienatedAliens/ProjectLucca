from lucca.reasoning.smt_verifier import SMTVerifier

v = SMTVerifier()
rule = """(rule "unmodeled-vuln-v1"
  :when (and (intent= "launch_app") (transcript-matches-glob? "dangerous*"))
  :plan (list (tool "launch_app" :app "calc"))
  :priority 1)"""
res = v.verify_source(rule)
print("Verified:", res.verified)
print("Status:", res.status)
print("Reasons:", res.reasons)
