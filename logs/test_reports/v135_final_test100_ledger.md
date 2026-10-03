# v1.35 Failure Ledger — `checkpoint_math500_v1.35-final-test-100.json`

- Items: **100**  | Strict pass: **86**  | Lenient pass: **89**  | Strict failures listed below: **14**
- Failure classes (strict failures): `(strict-only fail)`=3, `equivalence_format_miss`=5, `genuine_derivation_miss`=3, `runtime_crash`=3
- finish_reason over ALL items: `length`=1, `stop`=99
- **TOKEN-CAP TRUNCATION**: `finish_reason=length` on **1** items, of which **1** are strict failures (idx: [44]). These are the primary v1.35 'bullshit' losses: the model ran out of tokens.
- completion_tokens >= 750 (at/near cap): **13** items
- T1 latency in 15.0–16.5 s (timeout-suspect window), ALL items: **0** (idx: )
- runtime_crash exception types: `AttributeError`=2, `ValueError`=1

## Paired comparison vs baseline (STRICT, same idx)

> NOTE: baseline checkpoint has no `strict_pass` field (pre-v1.35 grader); its `passed` field was used instead. If `passed` followed the lenient grader, this comparison is lenient-vs-strict and understates gains. Prefer a baseline regraded under v1.35-dual.

- Gains (baseline FAIL → current PASS): **7**  idx: [1, 22, 51, 65, 82, 85, 98]
- Losses (baseline PASS → current FAIL): **5**  idx: [3, 12, 26, 86, 97]
  - **INVARIANT losses** (baseline finished `stop`, no Turn 2 — output should have been bit-identical): **4**  idx: [3, 26, 86, 97]
  - Expected losses (baseline hit `length` or used Turn 2 — rescue path legitimately changed): **1**  idx: [12]
- Net: **+2**  (churn = gains + losses = 12)

> **Gate verdict: STOP.** Rule: a *budget/mechanism* change is accepted iff INVARIANT losses == 0. Expected losses are labeled in the table below (usually `reasoning` loop or `grader`), not rationalised away. For a *feedback-content* change (Fix B), apply the rule to total losses instead.

## Strict failures — fill LABEL with exactly one of: `infra` / `extraction` / `grader` / `library-misuse` / `reasoning`

v1.35 scope = `infra`, `extraction`, `grader`, and `library-misuse` fixed ONLY via feedback-governor traceback content. `reasoning` is out of scope — leave it.

| idx | class | S/L | exit | finish | tok | T1 s | T2 s | fb trig/ok | stage | exception / stderr head | pred | expected | AUTO HINT | LABEL | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | (strict-only) | N/Y | 0 | stop | 56 | 1.4 | 0.0 | N/N | fenced |  | 4.666666666666667 | \frac{14}{3} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 8 | runtime_crash | N/N | 1 | stop | 680 | 6.4 | 7.6 | Y/N | fenced | AttributeError |  | 90^\circ | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… |  |  |
| 12 | equivalence_format_miss | N/N | 0 | stop | 1285 | 25.9 | 0.0 | N/N | fenced |  | 311/3528 | \frac{3}{56} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 18 | equivalence_format_miss | N/N | 0 | stop | 831 | 16.9 | 0.0 | N/N | fenced |  | 3*pi/2 | \pi | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 19 | genuine_derivation_miss | N/N | 0 | stop | 2783 | 31.1 | 26.1 | Y/Y | fenced |  | 62 | 28 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 26 | (strict-only) | N/Y | 0 | stop | 566 | 11.6 | 0.0 | N/N | fenced |  | -2.00000000000000, 1.00… | 1,-2 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 29 | genuine_derivation_miss | N/N | 0 | stop | 59 | 1.4 | 0.0 | N/N | fenced |  | I*(7 + 2*I) | -2 + 7i | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 44 | equivalence_format_miss | N/N | 0 | length | 3072 | 31.0 | 31.9 | Y/N | fenced |  | 1 | 70 \sqrt{2} | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … |  |  |
| 61 | runtime_crash | N/N | 1 | stop | 1870 | 30.7 | 6.8 | Y/N | fenced | ValueError | 3 | (6,31,-1) | CRASH:ValueError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical ex… |  |  |
| 64 | runtime_crash | N/N | 1 | stop | 1985 | 31.0 | 10.0 | Y/N | fenced | AttributeError | 4 | 10 | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… |  |  |
| 86 | equivalence_format_miss | N/N | 0 | stop | 165 | 3.5 | 0.0 | N/N | fenced |  | -sqrt(5) | \sqrt{5} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 95 | genuine_derivation_miss | N/N | 0 | stop | 2244 | 31.2 | 15.3 | Y/Y | fenced |  | 130 | 80 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 97 | (strict-only) | N/Y | 0 | stop | 297 | 6.2 | 0.0 | N/N | fenced |  | 1 - sqrt(19), 1 + sqrt(… | 1 \pm \sqrt{19} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 100 | equivalence_format_miss | N/N | 0 | stop | 392 | 8.0 | 0.0 | N/N | fenced |  | [-1/3, 2/3, 5/3] | \begin{pmatrix} -1/3 \\… | FORMAT-MISS -> grader or reasoning (inspect) |  |  |

## Label counts (fill after labeling)

- `infra`: 
- `extraction`: 
- `grader`: 
- `library-misuse`: 
- `reasoning`: 
