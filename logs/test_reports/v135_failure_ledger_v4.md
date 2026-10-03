# v1.35 Failure Ledger — `checkpoint_math500_v1.35-dev-400-v4.json`

- Items: **400**  | Strict pass: **322**  | Lenient pass: **341**  | Strict failures listed below: **78**
- Failure classes (strict failures): `(strict-only fail)`=19, `equivalence_format_miss`=26, `genuine_derivation_miss`=18, `prose_slip`=5, `runtime_crash`=10
- finish_reason over ALL items: `length`=15, `stop`=385
- **TOKEN-CAP TRUNCATION**: `finish_reason=length` on **15** items, of which **13** are strict failures (idx: [11, 20, 37, 55, 65, 67, 85, 105, 123, 137, 165, 187, 361]). These are the primary v1.35 'bullshit' losses: the model ran out of tokens.
- completion_tokens >= 750 (at/near cap): **89** items
- T1 latency in 15.0–16.5 s (timeout-suspect window), ALL items: **8** (idx: 64, 95, 98, 193, 210, 266, 270, 376)
- runtime_crash exception types: `NameError`=4, `unknown`=4, `AttributeError`=1, `IndexError`=1

## Paired comparison vs baseline (STRICT, same idx)

- Gains (baseline FAIL → current PASS): **0**  idx: []
- Losses (baseline PASS → current FAIL): **3**  idx: [21, 146, 147]
  - **INVARIANT losses** (baseline finished `stop`, no Turn 2 — output should have been bit-identical): **0**  idx: []
  - Expected losses (baseline hit `length` or used Turn 2 — rescue path legitimately changed): **3**  idx: [21, 146, 147]
- Net: **-3**  (churn = gains + losses = 3)

> **Gate verdict: REJECT.** Fix B rejected: losses=3 idx=[21, 146, 147], gains=0. Rule for feedback-content change: total losses must be 0 and gains >= 2. Code reverted; proceeding to Step 5 using v3 as current baseline.

## Strict failures — fill LABEL with exactly one of: `infra` / `extraction` / `grader` / `library-misuse` / `reasoning`

v1.35 scope = `infra`, `extraction`, `grader`, and `library-misuse` fixed ONLY via feedback-governor traceback content. `reasoning` is out of scope — leave it.

| idx | class | S/L | exit | finish | tok | T1 s | T2 s | fb trig/ok | stage | exception / stderr head | pred | expected | AUTO HINT | LABEL | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4 | genuine_derivation_miss | N/N | 0 | stop | 2320 | 30.9 | 16.6 | Y/Y | fenced |  | 3 < \lambda \le 4 | (3,4] | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 10 | runtime_crash | N/N | 1 | stop | 2149 | 30.9 | 13.2 | Y/N | fenced | AttributeError |  | 120^\circ | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… |  |  |
| 11 | genuine_derivation_miss | N/N | 0 | length | 3072 | 31.1 | 31.8 | Y/N | fenced |  | 4 | 504 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 12 | runtime_crash | N/N | 1 | stop | 180 | 2.5 | 1.7 | Y/N | fenced | NameError |  | 210 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 20 | genuine_derivation_miss | N/N | 0 | length | 3072 | 30.8 | 30.8 | Y/N | fenced |  | 1 | -9 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 21 | runtime_crash | N/N | 1 | stop | 690 | 8.6 | 5.7 | Y/N | fenced | NameError |  | \text{even} | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 27 | runtime_crash | N/N | -9 | stop | 1164 | 17.0 | 7.2 | Y/N | fenced | execution_failed |  | 1+274i | CRASH:unknown -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical excep… |  |  |
| 30 | (strict-only) | N/Y | 0 | stop | 303 | 6.2 | 0.0 | N/N | fenced |  | 13.2871972318339 | \frac{3840}{289} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 37 | prose_slip | N/N | 0 | length | 3072 | 30.7 | 31.6 | Y/N | fenced |  |  | 64 | TRUNCATION(finish_reason=length) -> infra/extraction; EMPTY-OUTPUT -> infra/extraction; P… |  |  |
| 39 | equivalence_format_miss | N/N | 0 | stop | 400 | 8.1 | 0.0 | N/N | fenced |  | 1/6 | \frac{1}{3} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 46 | runtime_crash | N/N | -9 | stop | 399 | 4.3 | 4.2 | Y/N | fenced | execution_failed |  | -2 | CRASH:unknown -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical excep… |  |  |
| 55 | equivalence_format_miss | N/N | 0 | length | 3072 | 31.6 | 31.9 | Y/N | fenced |  | 11 | 2\sqrt{113} | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … |  |  |
| 58 | (strict-only) | N/Y | 0 | stop | 183 | 3.8 | 0.0 | N/N | fenced |  | 1.20000000000000 | \frac65 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 65 | (strict-only) | N/Y | 0 | length | 1536 | 30.9 | 0.0 | N/N | fenced |  | -tan(4*pi/9) + 4*cos(pi… | -\sqrt{3} | TRUNCATION(finish_reason=length) -> infra/extraction; STRICT-ONLY-FAIL -> grader candidat… |  |  |
| 67 | equivalence_format_miss | N/N | 0 | length | 3072 | 31.2 | 32.0 | Y/N | fenced |  | 45 | \frac{270}7\text{ degre… | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … |  |  |
| 69 | genuine_derivation_miss | N/N | 0 | stop | 2796 | 31.4 | 26.5 | Y/Y | fenced |  | 9 | 19 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 74 | genuine_derivation_miss | N/N | 0 | stop | 294 | 6.0 | 0.0 | N/N | fenced |  | 16 | 4 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 80 | genuine_derivation_miss | N/N | 0 | stop | 1874 | 30.8 | 7.1 | Y/Y | fenced |  | 5x + -7y + 11z + 4 = 0 | 5x - 7y + 11z + 4 = 0 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 82 | (strict-only) | N/Y | 0 | stop | 161 | 3.4 | 0.0 | N/N | fenced |  | 0.577350269189626 | \frac{\sqrt{3}}{3} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 84 | genuine_derivation_miss | N/N | 0 | stop | 311 | 6.3 | 0.0 | N/N | fenced |  | 13 | 23 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 85 | equivalence_format_miss | N/N | 0 | length | 1536 | 30.8 | 0.0 | N/N | fenced |  | 2 < infinity | (2,\infty) | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … |  |  |
| 89 | prose_slip | N/N | 0 | stop | 1397 | 14.9 | 13.3 | Y/N | fenced |  |  | 6 | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction |  |  |
| 103 | (strict-only) | N/Y | 0 | stop | 290 | 5.9 | 0.0 | N/N | fenced |  | 0.666666666666667 | \frac{2}{3} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 105 | genuine_derivation_miss | N/N | 0 | length | 3072 | 30.7 | 31.6 | Y/N | fenced |  | 1 | 0 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 106 | (strict-only) | N/Y | 0 | stop | 398 | 8.3 | 0.0 | N/N | fenced |  | Matrix([[-2], [-14], [-… | \begin{pmatrix} -2 \\ -… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 107 | (strict-only) | N/Y | 0 | stop | 198 | 4.2 | 0.0 | N/N | fenced |  | (1.5, -13) | \left( \frac{3}{2}, -13… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 117 | genuine_derivation_miss | N/N | 0 | stop | 173 | 3.6 | 0.0 | N/N | fenced |  | 21/2 | 6 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 118 | equivalence_format_miss | N/N | 0 | stop | 2108 | 30.6 | 11.4 | Y/Y | fenced |  | 11111111100 | 11,\! 111,\! 111,\! 100 | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 123 | genuine_derivation_miss | N/N | 0 | length | 3072 | 30.8 | 31.7 | Y/N | fenced |  | -4 | 54 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 125 | (strict-only) | N/Y | 0 | stop | 432 | 8.8 | 0.0 | N/N | fenced |  | 3*sin(pi/9)**2*sin(2*pi… | \frac{9}{256} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 128 | (strict-only) | N/Y | 0 | stop | 132 | 2.8 | 0.0 | N/N | fenced |  | C | \text{(C)} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 133 | (strict-only) | N/Y | 0 | stop | 1380 | 27.7 | 0.0 | N/N | fenced |  | 998.5 | \frac{1997}{2} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 137 | genuine_derivation_miss | N/N | 0 | length | 2523 | 19.7 | 31.5 | Y/N | fenced |  | 20 | 12 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 141 | genuine_derivation_miss | N/N | 0 | stop | 1438 | 29.1 | 0.0 | N/N | fenced |  | 154.0 | 116 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 146 | runtime_crash | N/N | 1 | stop | 433 | 5.1 | 4.1 | Y/N | fenced | sympy.polys.polyerrors.UnificationFailed: Cannot … |  | -13x+3 | CRASH:unknown -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical excep… |  |  |
| 147 | runtime_crash | N/N | 1 | stop | 354 | 4.8 | 2.7 | Y/N | fenced | NameError | Fraction | 8 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 149 | (strict-only) | N/Y | 0 | stop | 244 | 5.0 | 0.0 | N/N | fenced |  | Matrix([[-1, 0], [0, -1… | \begin{pmatrix} -1 & 0 … | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 156 | (strict-only) | N/Y | 0 | stop | 308 | 6.3 | 0.0 | N/N | fenced |  | E | \text{(E)} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 158 | equivalence_format_miss | N/N | 0 | stop | 440 | 8.9 | 0.0 | N/N | fenced |  | 72*12**(1/3) | 864 \mbox{ inches}^2 | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 165 | equivalence_format_miss | N/N | 0 | length | 3072 | 31.0 | 32.0 | Y/N | fenced |  | 0 | 1\frac{4}{5} | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … |  |  |
| 168 | equivalence_format_miss | N/N | 0 | stop | 1160 | 23.4 | 0.0 | N/N | fenced |  | 150 | 180^\circ | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 185 | equivalence_format_miss | N/N | 0 | stop | 2079 | 30.8 | 11.8 | Y/Y | fenced |  | 2*sqrt(2) + 3, 3 - 2*sq… | 3 \pm 2 \sqrt{2} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 187 | equivalence_format_miss | N/N | 0 | length | 3072 | 30.8 | 30.6 | Y/N | fenced |  | 3 | \frac{17}{21} | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … |  |  |
| 191 | genuine_derivation_miss | N/N | 0 | stop | 353 | 7.2 | 0.0 | N/N | fenced |  | 7/2 | 4 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 194 | equivalence_format_miss | N/N | 0 | stop | 541 | 6.7 | 4.4 | Y/Y | fenced |  | Interval(3/5, 8/3) | \left(\frac{3}{5},\frac… | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 197 | (strict-only) | N/Y | 0 | stop | 1009 | 20.3 | 0.0 | N/N | fenced |  | B | \text{(B)} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 199 | (strict-only) | N/Y | 0 | stop | 246 | 5.2 | 0.0 | N/N | fenced |  | Matrix([[-18], [-49], [… | \begin{pmatrix} -18 \\ … | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 206 | equivalence_format_miss | N/N | 0 | stop | 242 | 5.0 | 0.0 | N/N | fenced |  | 0.473684210526316 | \frac9{19} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 208 | prose_slip | N/N | 0 | stop | 528 | 6.0 | 5.0 | Y/N | fenced |  |  | (-\infty, 0] | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction |  |  |
| 209 | equivalence_format_miss | N/N | 0 | stop | 1048 | 21.0 | 0.0 | N/N | fenced |  | 1.0 + 3*sqrt(3) | 1+2\sqrt{3} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 213 | (strict-only) | N/Y | 0 | stop | 209 | 4.3 | 0.0 | N/N | fenced |  | Interval(5, oo) | (5,\infty) | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 217 | prose_slip | N/N | 0 | stop | 411 | 4.7 | 4.0 | Y/N | fenced |  |  | 12 | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction |  |  |
| 220 | genuine_derivation_miss | N/N | 0 | stop | 150 | 3.1 | 0.0 | N/N | fenced |  | 1 | -128 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 225 | genuine_derivation_miss | N/N | 0 | stop | 1913 | 31.1 | 8.6 | Y/Y | fenced |  | 150 | 120 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 227 | equivalence_format_miss | N/N | 0 | stop | 1019 | 20.4 | 0.0 | N/N | fenced |  | -9/100 | \frac{9}{100} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 228 | runtime_crash | N/N | 1 | stop | 2048 | 23.7 | 18.2 | Y/N | fenced | IndexError |  | 15 | CRASH:IndexError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical ex… |  |  |
| 229 | genuine_derivation_miss | N/N | 0 | stop | 1691 | 17.0 | 16.9 | Y/N | fenced |  | 0 | 3 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 241 | runtime_crash | N/N | -1 | stop | 1713 | 24.9 | 10.2 | Y/N | fenced | Execution timed out after 10 seconds |  | 55^\circ | CRASH:unknown -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical excep… |  |  |
| 257 | equivalence_format_miss | N/N | 0 | stop | 461 | 9.3 | 0.0 | N/N | fenced |  | Interval(-sqrt(3), sqrt… | (-\sqrt{3}, \sqrt{3}) | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 262 | equivalence_format_miss | N/N | 0 | stop | 858 | 10.0 | 7.7 | Y/Y | fenced |  | -16*sqrt(3) | 16 \sqrt{3} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 280 | genuine_derivation_miss | N/N | 0 | stop | 261 | 5.4 | 0.0 | N/N | fenced |  | 12th | 12 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 281 | equivalence_format_miss | N/N | 0 | stop | 1091 | 14.5 | 7.6 | Y/Y | fenced |  | Interval(0, 36) | (0,9) \cup (9,36) | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 284 | equivalence_format_miss | N/N | 0 | stop | 239 | 4.9 | 0.0 | N/N | fenced |  | Interval(-2, 7) | x \in [-2,7] | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 290 | (strict-only) | N/Y | 0 | stop | 293 | 6.0 | 0.0 | N/N | fenced |  | 0.916515138991168 | \frac{\sqrt{21}}{5} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 293 | prose_slip | N/N | 0 | stop | 1869 | 31.0 | 7.5 | Y/N | fenced |  |  | \sqrt{66} | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction |  |  |
| 301 | equivalence_format_miss | N/N | 0 | stop | 2013 | 30.8 | 10.4 | Y/Y | fenced |  | -56*sqrt(sqrt(2) + 2) -… | \frac{14}{3} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 309 | (strict-only) | N/Y | 0 | stop | 404 | 8.1 | 0.0 | N/N | fenced |  | Matrix([[0.200000000000… | \begin{pmatrix} 1/5 \\ … | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 320 | (strict-only) | N/Y | 0 | stop | 966 | 19.3 | 0.0 | N/N | fenced |  | Matrix([[-7], [16], [5]… | \begin{pmatrix} -7 \\ 1… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 321 | equivalence_format_miss | N/N | 0 | stop | 439 | 5.3 | 3.9 | Y/Y | fenced |  | (16/49, 48/49, 24/49) | \begin{pmatrix} 16/49 \… | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 323 | equivalence_format_miss | N/N | 0 | stop | 2133 | 30.8 | 12.9 | Y/Y | fenced |  | [-2, -sqrt(2 - I)*sqrt(… | \{1\pm\sqrt{5},-2\} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 332 | equivalence_format_miss | N/N | 0 | stop | 1191 | 23.8 | 0.0 | N/N | fenced |  | Interval(pi**2/8, 5*pi*… | \left[ \frac{\pi^2}{8},… | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 336 | equivalence_format_miss | N/N | 0 | stop | 358 | 7.2 | 0.0 | N/N | fenced |  | Union(Interval(-oo, 2),… | (-\infty, 2) \cup (3, \… | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 346 | genuine_derivation_miss | N/N | 0 | stop | 1480 | 29.9 | 0.0 | N/N | fenced |  | 0.0 | 15 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 361 | equivalence_format_miss | N/N | 0 | length | 3072 | 30.9 | 31.8 | Y/N | fenced |  | 0 | 75^\circ | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … |  |  |
| 370 | runtime_crash | N/N | 1 | stop | 188 | 2.2 | 1.9 | Y/N | fenced | NameError | ceil | 25 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 373 | equivalence_format_miss | N/N | 0 | stop | 118 | 2.5 | 0.0 | N/N | fenced |  | 275/2 | 137 \frac{1}{2} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 396 | equivalence_format_miss | N/N | 0 | stop | 1418 | 28.4 | 0.0 | N/N | fenced |  | Interval(2, 102) | (2,12) \cup (12,102) | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 398 | (strict-only) | N/Y | 0 | stop | 344 | 6.9 | 0.0 | N/N | fenced |  | 3.50000000000000 | \frac{7}{2} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |

## Label counts (fill after labeling)

- `infra`: 
- `extraction`: 
- `grader`: 
- `library-misuse`: 
- `reasoning`: 
