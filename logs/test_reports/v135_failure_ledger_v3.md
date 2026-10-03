# v1.35 Failure Ledger — `checkpoint_math500_v1.35-dev-400-v3.json`

- Items: **400**  | Strict pass: **325**  | Lenient pass: **345**  | Strict failures listed below: **75**
- Failure classes (strict failures): `(strict-only fail)`=20, `equivalence_format_miss`=26, `genuine_derivation_miss`=17, `prose_slip`=5, `runtime_crash`=7
- finish_reason over ALL items: `length`=14, `stop`=386
- **TOKEN-CAP TRUNCATION**: `finish_reason=length` on **14** items, of which **12** are strict failures (idx: [11, 20, 37, 55, 65, 67, 85, 105, 123, 165, 187, 361]). These are the primary v1.35 'bullshit' losses: the model ran out of tokens.
- completion_tokens >= 750 (at/near cap): **91** items
- T1 latency in 15.0–16.5 s (timeout-suspect window), ALL items: **10** (idx: 48, 64, 89, 95, 98, 193, 210, 266, 270, 376)
- runtime_crash exception types: `AttributeError`=2, `NameError`=2, `unknown`=2, `IndexError`=1

## Paired comparison vs baseline (STRICT, same idx)

- Gains (baseline FAIL → current PASS): **21**  idx: [1, 2, 38, 57, 77, 78, 90, 120, 140, 182, 204, 207, 218, 234, 272, 322, 326, 345, 379, 382, 395]
- Losses (baseline PASS → current FAIL): **2**  idx: [37, 197]
  - **INVARIANT losses** (baseline finished `stop`, no Turn 2 — output should have been bit-identical): **0**  idx: []
  - Expected losses (baseline hit `length` or used Turn 2 — rescue path legitimately changed): **2**  idx: [37, 197]
- Net: **+19**  (churn = gains + losses = 23)

> **Gate verdict: ACCEPT.** Rule: a *budget/mechanism* change is accepted iff INVARIANT losses == 0. Expected losses are labeled in the table below (usually `reasoning` loop or `grader`), not rationalised away. For a *feedback-content* change (Fix B), apply the rule to total losses instead.

## Strict failures — fill LABEL with exactly one of: `infra` / `extraction` / `grader` / `library-misuse` / `reasoning`

v1.35 scope = `infra`, `extraction`, `grader`, and `library-misuse` fixed ONLY via feedback-governor traceback content. `reasoning` is out of scope — leave it.

| idx | class | S/L | exit | finish | tok | T1 s | T2 s | fb trig/ok | stage | exception / stderr head | pred | expected | AUTO HINT | LABEL | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4 | genuine_derivation_miss | N/N | 0 | stop | 2320 | 30.9 | 16.6 | Y/Y | fenced |  | 3 < \lambda \le 4 | (3,4] | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 10 | runtime_crash | N/N | 1 | stop | 2149 | 31.0 | 13.3 | Y/N | fenced | AttributeError |  | 120^\circ | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… | library-misuse | Python AttributeError in model code |
| 11 | genuine_derivation_miss | N/N | 0 | length | 3072 | 31.2 | 31.9 | Y/N | fenced |  | 4 | 504 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… | reasoning | Token budget exhausted; loop/rambling |
| 12 | runtime_crash | N/N | 1 | stop | 180 | 2.6 | 1.7 | Y/N | fenced | NameError |  | 210 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… | library-misuse | Python NameError in model code |
| 20 | genuine_derivation_miss | N/N | 0 | length | 3072 | 31.0 | 31.1 | Y/N | fenced |  | 1 | -9 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… | reasoning | Token budget exhausted; loop/rambling |
| 27 | runtime_crash | N/N | -9 | stop | 1145 | 17.2 | 6.8 | Y/N | fenced | execution_failed |  | 1+274i | CRASH:unknown -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical excep… | infra | Sandbox timeout/SIGKILL during execution |
| 30 | (strict-only) | N/Y | 0 | stop | 303 | 6.3 | 0.0 | N/N | fenced |  | 13.2871972318339 | \frac{3840}{289} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | reasoning | Float approximation instead of exact symbolic |
| 37 | prose_slip | N/N | 0 | length | 3072 | 31.2 | 32.1 | Y/N | fenced |  |  | 64 | TRUNCATION(finish_reason=length) -> infra/extraction; EMPTY-OUTPUT -> infra/extraction; P… | reasoning | Cauchy-Schwarz loop at 1536 tokens |
| 39 | equivalence_format_miss | N/N | 0 | stop | 400 | 8.2 | 0.0 | N/N | fenced |  | 1/6 | \frac{1}{3} | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Mathematical derivation error |
| 46 | runtime_crash | N/N | -9 | stop | 506 | 4.3 | 6.4 | Y/N | fenced | execution_failed |  | -2 | CRASH:unknown -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical excep… | infra | Sandbox timeout/SIGKILL during execution |
| 55 | equivalence_format_miss | N/N | 0 | length | 3072 | 31.1 | 32.0 | Y/N | fenced |  | 11 | 2\sqrt{113} | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … | reasoning | Token budget exhausted; loop/rambling |
| 58 | (strict-only) | N/Y | 0 | stop | 183 | 3.9 | 0.0 | N/N | fenced |  | 1.20000000000000 | \frac65 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Exact decimal vs fraction notation |
| 65 | (strict-only) | N/Y | 0 | length | 1536 | 31.1 | 0.0 | N/N | fenced |  | -tan(4*pi/9) + 4*cos(pi… | -\sqrt{3} | TRUNCATION(finish_reason=length) -> infra/extraction; STRICT-ONLY-FAIL -> grader candidat… | reasoning | Token budget exhausted; loop/rambling |
| 67 | equivalence_format_miss | N/N | 0 | length | 3072 | 31.1 | 32.1 | Y/N | fenced |  | 45 | \frac{270}7\text{ degre… | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … | reasoning | Token budget exhausted; loop/rambling |
| 69 | genuine_derivation_miss | N/N | 0 | stop | 2796 | 31.5 | 26.8 | Y/Y | fenced |  | 9 | 19 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 74 | genuine_derivation_miss | N/N | 0 | stop | 294 | 6.0 | 0.0 | N/N | fenced |  | 16 | 4 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 80 | genuine_derivation_miss | N/N | 0 | stop | 1874 | 31.1 | 7.1 | Y/Y | fenced |  | 5x + -7y + 11z + 4 = 0 | 5x - 7y + 11z + 4 = 0 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 82 | (strict-only) | N/Y | 0 | stop | 161 | 3.4 | 0.0 | N/N | fenced |  | 0.577350269189626 | \frac{\sqrt{3}}{3} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | reasoning | Float approximation instead of exact symbolic |
| 84 | genuine_derivation_miss | N/N | 0 | stop | 311 | 6.4 | 0.0 | N/N | fenced |  | 13 | 23 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 85 | equivalence_format_miss | N/N | 0 | length | 1536 | 31.1 | 0.0 | N/N | fenced |  | 2 < infinity | (2,\infty) | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … | reasoning | Token budget exhausted; loop/rambling |
| 89 | prose_slip | N/N | 0 | stop | 1397 | 15.1 | 13.5 | Y/N | fenced |  |  | 6 | TIMEOUT-SUSPECT(T1=15.11s in uniform window); EMPTY-OUTPUT -> infra/extraction; PROSE-SLI… | extraction | Empty output or missing print statement |
| 103 | (strict-only) | N/Y | 0 | stop | 290 | 5.9 | 0.0 | N/N | fenced |  | 0.666666666666667 | \frac{2}{3} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | reasoning | Float approximation instead of exact symbolic |
| 105 | genuine_derivation_miss | N/N | 0 | length | 3072 | 31.0 | 31.9 | Y/N | fenced |  | 1 | 0 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… | reasoning | Token budget exhausted; loop/rambling |
| 106 | (strict-only) | N/Y | 0 | stop | 398 | 8.4 | 0.0 | N/N | fenced |  | Matrix([[-2], [-14], [-… | \begin{pmatrix} -2 \\ -… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Matrix repr vs LaTeX pmatrix |
| 107 | (strict-only) | N/Y | 0 | stop | 198 | 4.2 | 0.0 | N/N | fenced |  | (1.5, -13) | \left( \frac{3}{2}, -13… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Exact decimal vs fraction notation |
| 117 | genuine_derivation_miss | N/N | 0 | stop | 173 | 3.7 | 0.0 | N/N | fenced |  | 21/2 | 6 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 118 | equivalence_format_miss | N/N | 0 | stop | 2108 | 31.1 | 11.6 | Y/Y | fenced |  | 11111111100 | 11,\! 111,\! 111,\! 100 | FORMAT-MISS -> grader or reasoning (inspect) | grader | Large integer spacing formatting |
| 123 | genuine_derivation_miss | N/N | 0 | length | 3072 | 31.1 | 32.1 | Y/N | fenced |  | -4 | 54 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… | reasoning | Token budget exhausted; loop/rambling |
| 125 | (strict-only) | N/Y | 0 | stop | 432 | 8.9 | 0.0 | N/N | fenced |  | 3*sin(pi/9)**2*sin(2*pi… | \frac{9}{256} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Unsimplified exact trig identity |
| 128 | (strict-only) | N/Y | 0 | stop | 132 | 2.8 | 0.0 | N/N | fenced |  | C | \text{(C)} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Bare choice letter vs text-wrapped letter |
| 133 | (strict-only) | N/Y | 0 | stop | 1380 | 28.2 | 0.0 | N/N | fenced |  | 998.5 | \frac{1997}{2} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Exact decimal vs fraction notation |
| 137 | (strict-only) | N/Y | 0 | stop | 1415 | 20.2 | 9.4 | Y/Y | fenced |  | sin(4*pi/9)**(-2) + sin… | 12 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Unsimplified exact trig identity |
| 141 | genuine_derivation_miss | N/N | 0 | stop | 1438 | 29.7 | 0.0 | N/N | fenced |  | 154.0 | 116 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 149 | (strict-only) | N/Y | 0 | stop | 244 | 5.1 | 0.0 | N/N | fenced |  | Matrix([[-1, 0], [0, -1… | \begin{pmatrix} -1 & 0 … | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Matrix repr vs LaTeX pmatrix |
| 156 | (strict-only) | N/Y | 0 | stop | 308 | 6.5 | 0.0 | N/N | fenced |  | E | \text{(E)} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Bare choice letter vs text-wrapped letter |
| 158 | equivalence_format_miss | N/N | 0 | stop | 440 | 9.0 | 0.0 | N/N | fenced |  | 72*12**(1/3) | 864 \mbox{ inches}^2 | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Mathematical derivation error |
| 165 | equivalence_format_miss | N/N | 0 | length | 3072 | 31.5 | 32.3 | Y/N | fenced |  | 0 | 1\frac{4}{5} | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … | reasoning | Token budget exhausted; loop/rambling |
| 168 | equivalence_format_miss | N/N | 0 | stop | 1160 | 23.8 | 0.0 | N/N | fenced |  | 150 | 180^\circ | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Mathematical derivation error |
| 185 | equivalence_format_miss | N/N | 0 | stop | 2079 | 31.4 | 12.0 | Y/Y | fenced |  | 2*sqrt(2) + 3, 3 - 2*sq… | 3 \pm 2 \sqrt{2} | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Superfluous roots derived |
| 187 | equivalence_format_miss | N/N | 0 | length | 3072 | 31.5 | 31.4 | Y/N | fenced |  | 3 | \frac{17}{21} | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … | reasoning | Token budget exhausted; loop/rambling |
| 191 | genuine_derivation_miss | N/N | 0 | stop | 353 | 7.3 | 0.0 | N/N | fenced |  | 7/2 | 4 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 194 | equivalence_format_miss | N/N | 0 | stop | 541 | 6.8 | 4.5 | Y/Y | fenced |  | Interval(3/5, 8/3) | \left(\frac{3}{5},\frac… | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Incorrect boundary inclusion/exclusion |
| 197 | (strict-only) | N/Y | 0 | stop | 1009 | 20.7 | 0.0 | N/N | fenced |  | B | \text{(B)} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | bare B vs \text{(B)} notation mismatch; Fix C candidate |
| 199 | (strict-only) | N/Y | 0 | stop | 246 | 5.2 | 0.0 | N/N | fenced |  | Matrix([[-18], [-49], [… | \begin{pmatrix} -18 \\ … | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Matrix repr vs LaTeX pmatrix |
| 206 | equivalence_format_miss | N/N | 0 | stop | 242 | 5.1 | 0.0 | N/N | fenced |  | 0.473684210526316 | \frac9{19} | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Mathematical derivation error |
| 208 | prose_slip | N/N | 0 | stop | 528 | 6.0 | 5.1 | Y/N | fenced |  |  | (-\infty, 0] | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction | extraction | Empty output or missing print statement |
| 209 | equivalence_format_miss | N/N | 0 | stop | 1048 | 21.4 | 0.0 | N/N | fenced |  | 1.0 + 3*sqrt(3) | 1+2\sqrt{3} | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Mathematical derivation error |
| 213 | (strict-only) | N/Y | 0 | stop | 209 | 4.4 | 0.0 | N/N | fenced |  | Interval(5, oo) | (5,\infty) | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | SymPy Interval vs LaTeX interval |
| 217 | prose_slip | N/N | 0 | stop | 411 | 4.7 | 4.0 | Y/N | fenced |  |  | 12 | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction | extraction | Empty output or missing print statement |
| 220 | genuine_derivation_miss | N/N | 0 | stop | 150 | 3.2 | 0.0 | N/N | fenced |  | 1 | -128 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 225 | genuine_derivation_miss | N/N | 0 | stop | 1913 | 31.6 | 8.7 | Y/Y | fenced |  | 150 | 120 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 227 | equivalence_format_miss | N/N | 0 | stop | 1019 | 20.8 | 0.0 | N/N | fenced |  | -9/100 | \frac{9}{100} | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Sign error in derivation |
| 228 | runtime_crash | N/N | 1 | stop | 2166 | 24.2 | 21.0 | Y/N | fenced | IndexError |  | 15 | CRASH:IndexError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical ex… | library-misuse | Python IndexError in model code |
| 229 | genuine_derivation_miss | N/N | 0 | stop | 1691 | 17.4 | 17.3 | Y/N | fenced |  | 0 | 3 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 241 | runtime_crash | N/N | 1 | stop | 1650 | 25.2 | 8.9 | Y/N | fenced | AttributeError |  | 55^\circ | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… | library-misuse | Python AttributeError in model code |
| 257 | equivalence_format_miss | N/N | 0 | stop | 461 | 9.3 | 0.0 | N/N | fenced |  | Interval(-sqrt(3), sqrt… | (-\sqrt{3}, \sqrt{3}) | FORMAT-MISS -> grader or reasoning (inspect) | grader | SymPy Interval vs LaTeX interval |
| 262 | equivalence_format_miss | N/N | 0 | stop | 821 | 10.1 | 7.0 | Y/Y | fenced |  | -16*sqrt(3) | 16 \sqrt{3} | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Sign error in derivation |
| 280 | genuine_derivation_miss | N/N | 0 | stop | 261 | 5.4 | 0.0 | N/N | fenced |  | 12th | 12 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 281 | equivalence_format_miss | N/N | 0 | stop | 1021 | 14.6 | 6.2 | Y/Y | fenced |  | Interval(0, 36) | (0,9) \cup (9,36) | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Missed singularity/domain hole |
| 284 | equivalence_format_miss | N/N | 0 | stop | 239 | 5.0 | 0.0 | N/N | fenced |  | Interval(-2, 7) | x \in [-2,7] | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Incorrect boundary inclusion/exclusion |
| 290 | (strict-only) | N/Y | 0 | stop | 293 | 6.0 | 0.0 | N/N | fenced |  | 0.916515138991168 | \frac{\sqrt{21}}{5} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | reasoning | Float approximation instead of exact symbolic |
| 293 | prose_slip | N/N | 0 | stop | 1869 | 31.2 | 7.5 | Y/N | fenced |  |  | \sqrt{66} | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction | extraction | Empty output or missing print statement |
| 301 | equivalence_format_miss | N/N | 0 | stop | 2013 | 31.1 | 10.5 | Y/Y | fenced |  | -56*sqrt(sqrt(2) + 2) -… | \frac{14}{3} | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Mathematical derivation error |
| 309 | (strict-only) | N/Y | 0 | stop | 404 | 8.2 | 0.0 | N/N | fenced |  | Matrix([[0.200000000000… | \begin{pmatrix} 1/5 \\ … | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Matrix repr vs LaTeX pmatrix |
| 320 | (strict-only) | N/Y | 0 | stop | 966 | 19.5 | 0.0 | N/N | fenced |  | Matrix([[-7], [16], [5]… | \begin{pmatrix} -7 \\ 1… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Matrix repr vs LaTeX pmatrix |
| 321 | equivalence_format_miss | N/N | 0 | stop | 441 | 5.4 | 4.0 | Y/Y | fenced |  | (16/49, 48/49, 24/49) | \begin{pmatrix} 16/49 \… | FORMAT-MISS -> grader or reasoning (inspect) | grader | Vector tuple vs column vector |
| 323 | equivalence_format_miss | N/N | 0 | stop | 2133 | 31.0 | 12.9 | Y/Y | fenced |  | [-2, -sqrt(2 - I)*sqrt(… | \{1\pm\sqrt{5},-2\} | FORMAT-MISS -> grader or reasoning (inspect) | grader | List of roots vs set of roots |
| 332 | equivalence_format_miss | N/N | 0 | stop | 1191 | 24.0 | 0.0 | N/N | fenced |  | Interval(pi**2/8, 5*pi*… | \left[ \frac{\pi^2}{8},… | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Incorrect boundary inclusion/exclusion |
| 336 | equivalence_format_miss | N/N | 0 | stop | 358 | 7.3 | 0.0 | N/N | fenced |  | Union(Interval(-oo, 2),… | (-\infty, 2) \cup (3, \… | FORMAT-MISS -> grader or reasoning (inspect) | grader | SymPy Union vs LaTeX union |
| 346 | genuine_derivation_miss | N/N | 0 | stop | 1480 | 30.4 | 0.0 | N/N | fenced |  | 0.0 | 15 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) | reasoning | Derivation error |
| 361 | equivalence_format_miss | N/N | 0 | length | 3072 | 30.9 | 31.8 | Y/N | fenced |  | 0 | 75^\circ | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … | reasoning | Token budget exhausted; loop/rambling |
| 370 | runtime_crash | N/N | 1 | stop | 175 | 2.2 | 1.6 | Y/N | fenced | NameError | ceil | 25 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… | library-misuse | Python NameError in model code |
| 373 | equivalence_format_miss | N/N | 0 | stop | 118 | 2.5 | 0.0 | N/N | fenced |  | 275/2 | 137 \frac{1}{2} | FORMAT-MISS -> grader or reasoning (inspect) | grader | Improper fraction vs mixed fraction |
| 396 | equivalence_format_miss | N/N | 0 | stop | 1418 | 28.6 | 0.0 | N/N | fenced |  | Interval(2, 102) | (2,12) \cup (12,102) | FORMAT-MISS -> grader or reasoning (inspect) | reasoning | Missed singularity/domain hole |
| 398 | (strict-only) | N/Y | 0 | stop | 344 | 7.0 | 0.0 | N/N | fenced |  | 3.50000000000000 | \frac{7}{2} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) | grader | Exact decimal vs fraction notation |

## Label counts (fill after labeling)

- `infra`: **2**
- `extraction`: **4**
- `grader`: **21**
- `library-misuse`: **5**
- `reasoning`: **43**
