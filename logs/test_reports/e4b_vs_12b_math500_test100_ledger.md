# v1.35 Failure Ledger — `checkpoint_math500_e4b-test-100.json`

- Items: **100**  | Strict pass: **73**  | Lenient pass: **77**  | Strict failures listed below: **27**
- Failure classes (strict failures): `(strict-only fail)`=4, `equivalence_format_miss`=4, `genuine_derivation_miss`=15, `prose_slip`=1, `runtime_crash`=3
- finish_reason over ALL items: `length`=1, `stop`=99
- **TOKEN-CAP TRUNCATION**: `finish_reason=length` on **1** items, of which **1** are strict failures (idx: [19]). These are the primary v1.35 'bullshit' losses: the model ran out of tokens.
- completion_tokens >= 750 (at/near cap): **21** items
- T1 latency in 15.0–16.5 s (timeout-suspect window), ALL items: **0** (idx: )
- runtime_crash exception types: `NameError`=2, `KeyError`=1

## Paired comparison vs baseline (STRICT, same idx)

- Gains (baseline FAIL → current PASS): **7**  idx: [3, 18, 26, 29, 64, 86, 100]
- Losses (baseline PASS → current FAIL): **20**  idx: [1, 5, 10, 23, 28, 31, 33, 35, 36, 37, 52, 53, 54, 65, 71, 73, 79, 81, 85, 89]
  - **INVARIANT losses** (baseline finished `stop`, no Turn 2 — output should have been bit-identical): **19**  idx: [1, 5, 10, 23, 28, 31, 33, 35, 36, 37, 53, 54, 65, 71, 73, 79, 81, 85, 89]
  - Expected losses (baseline hit `length` or used Turn 2 — rescue path legitimately changed): **1**  idx: [52]
- Net: **-13**  (churn = gains + losses = 27)

> **Gate verdict: STOP.** Rule: a *budget/mechanism* change is accepted iff INVARIANT losses == 0. Expected losses are labeled in the table below (usually `reasoning` loop or `grader`), not rationalised away. For a *feedback-content* change (Fix B), apply the rule to total losses instead.

## Strict failures — fill LABEL with exactly one of: `infra` / `extraction` / `grader` / `library-misuse` / `reasoning`

v1.35 scope = `infra`, `extraction`, `grader`, and `library-misuse` fixed ONLY via feedback-governor traceback content. `reasoning` is out of scope — leave it.

| idx | class | S/L | exit | finish | tok | T1 s | T2 s | fb trig/ok | stage | exception / stderr head | pred | expected | AUTO HINT | LABEL | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | equivalence_format_miss | N/N | 0 | stop | 99 | 1.2 | 0.0 | N/N | fenced |  | 3 pi/2 | \left( 3, \frac{\pi}{2}… | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 5 | equivalence_format_miss | N/N | 0 | stop | 739 | 6.9 | 0.0 | N/N | fenced |  | 18/5 | \text{Evelyn} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 8 | runtime_crash | N/N | 1 | stop | 1736 | 7.4 | 8.8 | Y/N | fenced | NameError |  | 90^\circ | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 10 | genuine_derivation_miss | N/N | 0 | stop | 2200 | 14.2 | 6.2 | Y/Y | fenced |  | 1 | 4 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 12 | (strict-only) | N/Y | 0 | stop | 349 | 3.3 | 0.0 | N/N | fenced |  | 0.053571428571428825 | \frac{3}{56} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 19 | genuine_derivation_miss | N/N | 0 | length | 3072 | 14.2 | 14.2 | Y/N | fenced |  | 63.43 | 28 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 23 | genuine_derivation_miss | N/N | 0 | stop | 509 | 4.8 | 0.0 | N/N | fenced |  | (0,) | 5 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 28 | genuine_derivation_miss | N/N | 0 | stop | 152 | 1.5 | 0.0 | N/N | fenced |  | 114 | 78 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 31 | genuine_derivation_miss | N/N | 0 | stop | 454 | 4.2 | 0.0 | N/N | fenced |  | 662 | 52_8 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 33 | genuine_derivation_miss | N/N | 0 | stop | 197 | 1.9 | 0.0 | N/N | fenced |  | 30 | 720 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 35 | genuine_derivation_miss | N/N | 0 | stop | 73 | 0.8 | 0.0 | N/N | fenced |  | 0 | -125 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 36 | runtime_crash | N/N | 1 | stop | 386 | 2.6 | 1.1 | Y/N | fenced | NameError |  | 3 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 37 | genuine_derivation_miss | N/N | 0 | stop | 205 | 2.0 | 0.0 | N/N | fenced |  | 3 | 3, 5, 7 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 44 | equivalence_format_miss | N/N | 0 | stop | 1324 | 12.2 | 0.0 | N/N | fenced |  | 20*sqrt(5) + 10*sqrt(34) | 70 \sqrt{2} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 52 | genuine_derivation_miss | N/N | 0 | stop | 51 | 0.6 | 0.0 | N/N | fenced |  | (x**5 - x**4 + x**3 - x… | x^5 - x^4 + x^3 - x^2 +… | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 53 | (strict-only) | N/Y | 0 | stop | 55 | 0.6 | 0.0 | N/N | fenced |  | 1.49011611938476e-7*sqr… | 12 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 54 | (strict-only) | N/Y | 0 | stop | 26 | 0.3 | 0.0 | N/N | fenced |  | -0.523598775598299 | -\frac{\pi}{6} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 61 | genuine_derivation_miss | N/N | 0 | stop | 2714 | 14.1 | 11.4 | Y/Y | fenced |  | (558/53, 983/53, -353/5… | (6,31,-1) | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 65 | equivalence_format_miss | N/N | 0 | stop | 1368 | 10.5 | 2.5 | Y/Y | fenced |  | -1/128 | \frac{35}{64} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 71 | genuine_derivation_miss | N/N | 0 | stop | 459 | 4.2 | 0.0 | N/N | fenced |  | 36 | 40_9 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 73 | genuine_derivation_miss | N/N | 0 | stop | 239 | 2.3 | 0.0 | N/N | fenced |  | 0.0 | 3 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 79 | genuine_derivation_miss | N/N | 0 | stop | 574 | 5.3 | 0.0 | N/N | fenced |  | (a, b) | (-2,1) | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 81 | genuine_derivation_miss | N/N | 0 | stop | 2056 | 14.1 | 5.2 | Y/Y | fenced |  | 1093 | 501 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 85 | runtime_crash | N/N | 1 | stop | 1020 | 4.2 | 5.3 | Y/N | fenced | KeyError |  | -1 | CRASH:KeyError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exce… |  |  |
| 89 | prose_slip | N/N | 0 | stop | 1417 | 7.1 | 5.9 | Y/N | fenced |  |  | 2 | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction |  |  |
| 95 | genuine_derivation_miss | N/N | 0 | stop | 186 | 1.9 | 0.0 | N/N | fenced |  | 30 | 80 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 97 | (strict-only) | N/Y | 0 | stop | 1855 | 14.1 | 3.4 | Y/Y | fenced |  | -3.35889894354067,5.358… | 1 \pm \sqrt{19} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |

## Label counts (fill after labeling)

- `infra`: 
- `extraction`: 
- `grader`: 
- `library-misuse`: 
- `reasoning`: 
