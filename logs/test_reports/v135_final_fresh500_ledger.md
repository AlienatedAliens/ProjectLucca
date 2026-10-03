# v1.35 Failure Ledger — `checkpoint_math500_v1.35-final-fresh-500.json`

- Items: **500**  | Strict pass: **429**  | Lenient pass: **451**  | Strict failures listed below: **71**
- Failure classes (strict failures): `(strict-only fail)`=22, `equivalence_format_miss`=7, `genuine_derivation_miss`=23, `prose_slip`=5, `runtime_crash`=14
- finish_reason over ALL items: `length`=12, `stop`=488
- **TOKEN-CAP TRUNCATION**: `finish_reason=length` on **12** items, of which **9** are strict failures (idx: [180, 276, 311, 339, 399, 425, 429, 436, 445]). These are the primary v1.35 'bullshit' losses: the model ran out of tokens.
- completion_tokens >= 750 (at/near cap): **82** items
- T1 latency in 15.0–16.5 s (timeout-suspect window), ALL items: **10** (idx: 10, 19, 105, 205, 362, 388, 419, 432, 481, 497)
- runtime_crash exception types: `AttributeError`=6, `NameError`=3, `unknown`=2, `KeyError`=1, `TypeError`=1, `IndexError`=1

## Paired comparison vs baseline (STRICT, same idx)

> NOTE: baseline checkpoint has no `strict_pass` field (pre-v1.35 grader); its `passed` field was used instead. If `passed` followed the lenient grader, this comparison is lenient-vs-strict and understates gains. Prefer a baseline regraded under v1.35-dual.

- Gains (baseline FAIL → current PASS): **66**  idx: [2, 5, 10, 49, 55, 61, 63, 67, 71, 74, 82, 87, 95, 98, 102, 113, 122, 134, 151, 164, 168, 178, 181, 191, 193, 201, 215, 234, 261, 263, 268, 280, 281, 288, 297, 302, 323, 325, 328, 336, 342, 347, 348, 350, 368, 393, 400, 402, 408, 413, 414, 417, 431, 439, 447, 453, 458, 459, 460, 463, 472, 475, 479, 480, 496, 498]
- Losses (baseline PASS → current FAIL): **30**  idx: [42, 54, 75, 99, 105, 108, 110, 119, 140, 157, 180, 200, 203, 208, 231, 239, 240, 250, 298, 305, 339, 370, 419, 429, 433, 436, 438, 440, 448, 497]
  - **INVARIANT losses** (baseline finished `stop`, no Turn 2 — output should have been bit-identical): **20**  idx: [42, 54, 75, 110, 119, 140, 157, 200, 203, 208, 231, 239, 240, 250, 298, 305, 433, 440, 448, 497]
  - Expected losses (baseline hit `length` or used Turn 2 — rescue path legitimately changed): **10**  idx: [99, 105, 108, 180, 339, 370, 419, 429, 436, 438]
- Net: **+36**  (churn = gains + losses = 96)

> **Gate verdict: STOP.** Rule: a *budget/mechanism* change is accepted iff INVARIANT losses == 0. Expected losses are labeled in the table below (usually `reasoning` loop or `grader`), not rationalised away. For a *feedback-content* change (Fix B), apply the rule to total losses instead.

## Strict failures — fill LABEL with exactly one of: `infra` / `extraction` / `grader` / `library-misuse` / `reasoning`

v1.35 scope = `infra`, `extraction`, `grader`, and `library-misuse` fixed ONLY via feedback-governor traceback content. `reasoning` is out of scope — leave it.

| idx | class | S/L | exit | finish | tok | T1 s | T2 s | fb trig/ok | stage | exception / stderr head | pred | expected | AUTO HINT | LABEL | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | (strict-only) | N/Y | 0 | stop | 154 | 3.3 | 0.0 | N/N | fenced |  | -1/2 | -\$0.50 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 13 | genuine_derivation_miss | N/N | 0 | stop | 423 | 8.5 | 0.0 | N/N | fenced |  | 31 | 7 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 16 | (strict-only) | N/Y | 0 | stop | 112 | 2.4 | 0.0 | N/N | fenced |  | 10 | 10\;\text{edges} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 24 | genuine_derivation_miss | N/N | 0 | stop | 333 | 6.7 | 0.0 | N/N | fenced |  | 11 | 14 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 28 | genuine_derivation_miss | N/N | 0 | stop | 438 | 9.1 | 0.0 | N/N | fenced |  | 24 | 16 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 33 | (strict-only) | N/Y | 0 | stop | 739 | 15.0 | 0.0 | N/N | fenced |  | (0.733333333333333, 0.1… | \left( \frac{11}{15}, \… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 42 | (strict-only) | N/Y | 0 | stop | 469 | 9.7 | 0.0 | N/N | fenced |  | 17.3205080756888 | 10\sqrt3 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 50 | (strict-only) | N/Y | 0 | stop | 457 | 9.3 | 0.0 | N/N | fenced |  | -asin(sqrt(sqrt(3) + 2)… | -\frac{5 \pi}{12}, -\fr… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 52 | runtime_crash | N/N | -9 | stop | 676 | 8.2 | 6.5 | Y/N | fenced | execution_failed |  | 6\sqrt{3}+6 | CRASH:unknown -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical excep… |  |  |
| 54 | genuine_derivation_miss | N/N | 0 | stop | 191 | 4.0 | 0.0 | N/N | fenced |  | 2 | 3 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 75 | runtime_crash | N/N | 1 | stop | 1425 | 18.2 | 11.2 | Y/N | fenced | AttributeError |  | 87^\circ | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… |  |  |
| 88 | (strict-only) | N/Y | 0 | stop | 1852 | 30.9 | 7.2 | Y/Y | fenced |  | 105, 45, 30 | 105^\circ | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 90 | genuine_derivation_miss | N/N | 0 | stop | 490 | 9.9 | 0.0 | N/N | fenced |  | -1/4, 5/4 | 2 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 91 | (strict-only) | N/Y | 0 | stop | 247 | 5.1 | 0.0 | N/N | fenced |  | 15.5241746962600 | \sqrt{241} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 99 | prose_slip | N/N | 0 | stop | 1625 | 24.9 | 8.2 | Y/N | fenced |  |  | 6 | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction |  |  |
| 105 | equivalence_format_miss | N/N | 0 | stop | 817 | 16.4 | 0.0 | N/N | fenced |  | -1 | \frac{37}{11} | TIMEOUT-SUSPECT(T1=16.37s in uniform window); FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 108 | genuine_derivation_miss | N/N | 0 | stop | 205 | 4.3 | 0.0 | N/N | fenced |  | (x**2 + x + 1)*(Mod(x*(… | 0 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 110 | equivalence_format_miss | N/N | 0 | stop | 1004 | 20.0 | 0.0 | N/N | fenced |  | -1 | \frac{29}{15} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 119 | genuine_derivation_miss | N/N | 0 | stop | 136 | 2.9 | 0.0 | N/N | fenced |  | -12 | 13 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 132 | prose_slip | N/N | 0 | stop | 767 | 8.8 | 6.8 | Y/N | fenced |  |  | 8 | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction |  |  |
| 140 | (strict-only) | N/Y | 0 | stop | 135 | 2.8 | 0.0 | N/N | fenced |  | 1.20013716637183 | \frac{5\sqrt{42}}{27} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 141 | equivalence_format_miss | N/N | 0 | stop | 2268 | 30.8 | 15.6 | Y/Y | fenced |  | 1.52170894158256/pi | \frac{21}{64} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 145 | genuine_derivation_miss | N/N | 0 | stop | 826 | 16.7 | 0.0 | N/N | fenced |  | 27 | 134 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 155 | runtime_crash | N/N | 1 | stop | 1639 | 23.6 | 9.5 | Y/N | fenced | AttributeError |  | 31 | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… |  |  |
| 157 | (strict-only) | N/Y | 0 | stop | 381 | 7.7 | 0.0 | N/N | fenced |  | 4.666666666666667 | \frac{14}{3} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 165 | runtime_crash | N/N | -9 | stop | 2640 | 30.9 | 23.3 | Y/N | fenced | execution_failed | 0 | 2014 | CRASH:unknown -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical excep… |  |  |
| 180 | genuine_derivation_miss | N/N | 0 | length | 3072 | 30.7 | 31.6 | Y/N | fenced |  | 20 | 70 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 200 | (strict-only) | N/Y | 0 | stop | 211 | 4.4 | 0.0 | N/N | fenced |  | 0.123456790123457 | \frac{10}{81} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 202 | equivalence_format_miss | N/N | 0 | stop | 1008 | 20.4 | 0.0 | N/N | fenced |  | -24/13 | \frac{24}{5} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 203 | (strict-only) | N/Y | 0 | stop | 303 | 6.3 | 0.0 | N/N | fenced |  | 389/50 | 7.78 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 208 | runtime_crash | N/N | 1 | stop | 733 | 8.3 | 6.8 | Y/N | fenced | KeyError |  | 697 | CRASH:KeyError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exce… |  |  |
| 212 | genuine_derivation_miss | N/N | 0 | stop | 426 | 8.6 | 0.0 | N/N | fenced |  | 7 | 9 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 213 | (strict-only) | N/Y | 0 | stop | 392 | 8.0 | 0.0 | N/N | fenced |  | 2.66666666666667 | \frac83 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 231 | (strict-only) | N/Y | 0 | stop | 743 | 15.0 | 0.0 | N/N | fenced |  | 1.50000000000000 | \tfrac{3}{2} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 239 | runtime_crash | N/N | 1 | stop | 420 | 4.5 | 4.4 | Y/N | fenced | TypeError |  | 0 | CRASH:TypeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 240 | runtime_crash | N/N | 1 | stop | 1004 | 12.5 | 8.1 | Y/N | fenced | AttributeError |  | 9 + 11i | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… |  |  |
| 248 | genuine_derivation_miss | N/N | 0 | stop | 2710 | 30.8 | 24.4 | Y/Y | fenced |  | (7, -10) | (-7,10) | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 250 | runtime_crash | N/N | 1 | stop | 570 | 6.5 | 5.1 | Y/N | fenced | AttributeError |  | 17 | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… |  |  |
| 276 | prose_slip | N/N | 0 | length | 3072 | 30.7 | 31.7 | Y/N | fenced |  |  | \frac{\sqrt{10}}{5} | TRUNCATION(finish_reason=length) -> infra/extraction; EMPTY-OUTPUT -> infra/extraction; P… |  |  |
| 284 | equivalence_format_miss | N/N | 0 | stop | 2005 | 30.8 | 10.2 | Y/Y | fenced |  | 1/2 - sqrt(2)/2 | \frac{1}{2} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 298 | (strict-only) | N/Y | 0 | stop | 85 | 1.9 | 0.0 | N/N | fenced |  | 121/100 | 1.21 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 305 | runtime_crash | N/N | 1 | stop | 417 | 4.3 | 4.4 | Y/N | fenced | NameError |  | 200 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 306 | genuine_derivation_miss | N/N | 0 | stop | 1227 | 24.6 | 0.0 | N/N | fenced |  | 8720/4782969 | 0 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 308 | (strict-only) | N/Y | 0 | stop | 1462 | 29.2 | 0.0 | N/N | fenced |  | -1/12, 1/2 | \frac{1}{2}, -\frac{1}{… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 309 | (strict-only) | N/Y | 0 | stop | 205 | 4.3 | 0.0 | N/N | fenced |  | 33 | 33\% | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 310 | (strict-only) | N/Y | 0 | stop | 230 | 4.7 | 0.0 | N/N | fenced |  | -8.0 + 2.0*I | -8 + 2i | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 311 | equivalence_format_miss | N/N | 0 | length | 3072 | 31.0 | 31.8 | Y/N | fenced |  | 4 | 20^\circ | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … |  |  |
| 315 | (strict-only) | N/Y | 0 | stop | 372 | 7.6 | 0.0 | N/N | fenced |  | 0.395061728395062*pi | \frac{32\pi}{81} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 318 | (strict-only) | N/Y | 0 | stop | 340 | 7.0 | 0.0 | N/N | fenced |  | (0.75, -0.75) | \frac{3}{4}, -\frac{3}{… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 331 | genuine_derivation_miss | N/N | 0 | stop | 503 | 4.1 | 6.3 | Y/Y | fenced |  | [] | 1, -3 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 339 | prose_slip | N/N | 0 | length | 3072 | 31.0 | 31.9 | Y/N | fenced |  |  | \frac{3}{4}\pi\text{ in… | TRUNCATION(finish_reason=length) -> infra/extraction; EMPTY-OUTPUT -> infra/extraction; P… |  |  |
| 340 | (strict-only) | N/Y | 0 | stop | 301 | 6.3 | 0.0 | N/N | fenced |  | (-0.666666666666667, -2… | \left( -\frac{2}{3}, -\… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 346 | runtime_crash | N/N | 1 | stop | 3049 | 30.8 | 31.3 | Y/N | fenced | AttributeError | 4 | \frac{9}{4}, -\frac{9}{… | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… |  |  |
| 349 | runtime_crash | N/N | 1 | stop | 2884 | 30.9 | 27.4 | Y/N | fenced | IndexError | 1 | \begin{pmatrix} 1 \\ -2… | CRASH:IndexError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical ex… |  |  |
| 370 | runtime_crash | N/N | 1 | stop | 1948 | 31.0 | 9.2 | Y/N | fenced | NameError | 1 | 1112 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 376 | runtime_crash | N/N | 1 | stop | 297 | 2.7 | 3.6 | Y/N | fenced | AttributeError |  | 0 | CRASH:AttributeError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identica… |  |  |
| 388 | genuine_derivation_miss | N/N | 0 | stop | 750 | 15.3 | 0.0 | N/N | fenced |  | 0 | 19 | TIMEOUT-SUSPECT(T1=15.27s in uniform window); DERIVATION-MISS -> reasoning (NOT v1.35 sco… |  |  |
| 397 | genuine_derivation_miss | N/N | 0 | stop | 176 | 3.7 | 0.0 | N/N | fenced |  | 31 | 10 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 399 | prose_slip | N/N | 0 | length | 3072 | 31.3 | 32.1 | Y/N | fenced |  |  | 84 | TRUNCATION(finish_reason=length) -> infra/extraction; EMPTY-OUTPUT -> infra/extraction; P… |  |  |
| 419 | genuine_derivation_miss | N/N | 0 | stop | 796 | 16.2 | 0.0 | N/N | fenced |  | 7 | 743 | TIMEOUT-SUSPECT(T1=16.22s in uniform window); DERIVATION-MISS -> reasoning (NOT v1.35 sco… |  |  |
| 425 | genuine_derivation_miss | N/N | 0 | length | 3072 | 30.8 | 30.7 | Y/N | fenced |  | 2 | 82 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 429 | equivalence_format_miss | N/N | 0 | length | 3072 | 30.8 | 31.6 | Y/N | fenced |  | -20 | -\frac{\sqrt{10}}{10} | TRUNCATION(finish_reason=length) -> infra/extraction; FORMAT-MISS -> grader or reasoning … |  |  |
| 433 | (strict-only) | N/Y | 0 | stop | 205 | 4.3 | 0.0 | N/N | fenced |  | 14.1660667202811/log(17) | 5 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 436 | genuine_derivation_miss | N/N | 0 | length | 3072 | 30.8 | 31.9 | Y/N | fenced |  | 1 | (-4x^2+x+1)(4x^2+x+1) | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 438 | genuine_derivation_miss | N/N | 0 | stop | 343 | 7.0 | 0.0 | N/N | fenced |  | 19 | 11 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 440 | genuine_derivation_miss | N/N | 0 | stop | 860 | 17.4 | 0.0 | N/N | fenced |  | 2*I*y + 2*x | -1 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 445 | genuine_derivation_miss | N/N | 0 | length | 3072 | 30.7 | 31.7 | Y/N | fenced |  | 3 | -9 | TRUNCATION(finish_reason=length) -> infra/extraction; DERIVATION-MISS -> reasoning (NOT v… |  |  |
| 448 | runtime_crash | N/N | 1 | stop | 246 | 2.4 | 2.9 | Y/N | fenced | NameError |  | 79 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 452 | genuine_derivation_miss | N/N | 0 | stop | 1957 | 30.9 | 9.4 | Y/Y | fenced |  | 25/6 | 4 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 495 | (strict-only) | N/Y | 0 | stop | 153 | 3.3 | 0.0 | N/N | fenced |  | 3.87298334620742 | \sqrt{15} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 497 | genuine_derivation_miss | N/N | 0 | stop | 780 | 15.7 | 0.0 | N/N | fenced |  | -1/2 | 7.5 | TIMEOUT-SUSPECT(T1=15.69s in uniform window); DERIVATION-MISS -> reasoning (NOT v1.35 sco… |  |  |

## Label counts (fill after labeling)

- `infra`: 
- `extraction`: 
- `grader`: 
- `library-misuse`: 
- `reasoning`: 
