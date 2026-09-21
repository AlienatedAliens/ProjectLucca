"""
Negative Regression Test Fixture for D-REAS-07 (Default-Failure Test).
Enforces that unmodeled or unrecognized MicroScheme predicates fail closed
under SMT formal verification rather than defaulting to True.
"""

from lucca.reasoning.smt_verifier import SMTVerifier


def test_smt_verifier_rejects_unmodeled_predicates_fail_closed():
    """Verifies that an unmodeled predicate paired with valid preconditions fails closed."""
    verifier = SMTVerifier(timeout_ms=500)

    # transcript-matches-glob? is a valid MicroScheme parser predicate but not modeled in Z3
    source = """
    (rule "unmodeled-predicate-rule-v1"
      :when (and (intent= "launch_app")
                 (transcript-matches-glob? "admin*"))
      :plan (list (tool "launch_app" :app "calculator"))
      :priority 5)
    """
    res = verifier.verify_source(source)

    assert res.verified is False, "SMT verifier must NOT verify rules with unmodeled predicates"
    assert res.status == "UNMODELED_PREDICATE"
    assert any("unmodeled predicate" in r.lower() for r in res.reasons)


def test_smt_verifier_rejects_arbitrary_unmodeled_operator():
    """Verifies that attempting to verify an unhandled operator in AST translates to failure."""
    verifier = SMTVerifier(timeout_ms=500)

    source = """
    (rule "unmodeled-str-rule-v1"
      :when (and (intent= "launch_app")
                 (str-contains? "secret_key" "secret"))
      :plan (list (tool "launch_app" :app "calculator"))
      :priority 5)
    """
    res = verifier.verify_source(source)

    assert res.verified is False
    assert res.status in ("UNMODELED_PREDICATE", "SYNTAX_ERROR")
