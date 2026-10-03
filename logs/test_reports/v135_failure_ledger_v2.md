# v1.35 Failure Ledger — `checkpoint_math500_v1.35-dev-400-v2.json`

- Items: **400**  | Strict pass: **306**  | Lenient pass: **322**  | Strict failures listed below: **94**
- Failure classes (strict failures): `(strict-only fail)`=16, `equivalence_format_miss`=26, `genuine_derivation_miss`=23, `prose_slip`=15, `runtime_crash`=14
- finish_reason over ALL items: `length`=43, `stop`=357
- **TOKEN-CAP TRUNCATION**: `finish_reason=length` on **43** items, of which **42** are strict failures (idx: [1, 2, 4, 11, 20, 38, 55, 65, 67, 69, 77, 78, 85, 90, 105, 120, 123, 133, 140, 165, 168, 182, 185, 187, 204, 207, 209, 218, 225, 229, 234, 272, 293, 301, 322, 323, 326, 345, 346, 361, 382, 395]). These are the primary v1.35 'bullshit' losses: the model ran out of tokens.
- completion_tokens >= 750 (at/near cap): **91** items
- T1 latency in 15.0–16.5 s (timeout-suspect window), ALL items: **84** (idx: 1, 2, 4, 9, 10, 11, 20, 27, 37, 38, 48, 55, 57, 64, 65, 67, 69, 77, 78, 80, 85, 89, 90, 94, 95, 98, 105, 118, 120, 123, 133, 137, 140, 141, 143, 165, 168, 182, 185, 187 …)
- runtime_crash exception types: `NameError`=5, `AttributeError`=3, `unknown`=2, `KeyError`=2, `ValueError`=1, `TypeError`=1

## Strict failures — fill LABEL with exactly one of: `infra` / `extraction` / `grader` / `library-misuse` / `reasoning`

v1.35 scope = `infra`, `extraction`, `grader`, and `library-misuse` fixed ONLY via feedback-governor traceback content. `reasoning` is out of scope — leave it.

| idx | class | S/L | exit | finish | tok | T1 s | T2 s | fb trig/ok | stage | exception / stderr head | pred | expected | AUTO HINT | LABEL | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.7 | 16.1 | Y/N | fenced |  | 5 | 145^\circ | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.70s in unifor… |  |  |
| 2 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.8 | 16.0 | Y/N | fenced |  | 2 | 850 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.78s in unifor… |  |  |
| 4 | prose_slip | N/N | 0 | length | 1536 | 15.5 | 15.9 | Y/N | fenced |  |  | (3,4] | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.46s in unifor… |  |  |
| 10 | runtime_crash | N/N | 1 | stop | 1443 | 15.7 | 14.2 | Y/N | fenced | ValueError | 3 | 120^\circ | TIMEOUT-SUSPECT(T1=15.67s in uniform window); CRASH:ValueError -> library-misuse or infra… |  |  |
| 11 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.7 | 16.0 | Y/N | fenced |  | 3 | 504 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.71s in unifor… |  |  |
| 12 | runtime_crash | N/N | 1 | stop | 180 | 2.5 | 1.7 | Y/N | fenced | NameError |  | 210 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 20 | prose_slip | N/N | 0 | length | 1536 | 15.6 | 15.6 | Y/N | fenced |  |  | -9 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.55s in unifor… |  |  |
| 27 | runtime_crash | N/N | -9 | stop | 1097 | 15.5 | 7.2 | Y/N | fenced | execution_failed | 0 | 1+274i | TIMEOUT-SUSPECT(T1=15.48s in uniform window); CRASH:unknown -> library-misuse or infra; T… |  |  |
| 30 | (strict-only) | N/Y | 0 | stop | 303 | 6.3 | 0.0 | N/N | fenced |  | 13.2871972318339 | \frac{3840}{289} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 38 | runtime_crash | N/N | 1 | length | 1536 | 15.6 | 15.9 | Y/N | fenced | NameError | 20 | 204_5 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.61s in unifor… |  |  |
| 39 | equivalence_format_miss | N/N | 0 | stop | 400 | 8.3 | 0.0 | N/N | fenced |  | 1/6 | \frac{1}{3} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 46 | runtime_crash | N/N | -9 | stop | 506 | 4.3 | 6.4 | Y/N | fenced | execution_failed |  | -2 | CRASH:unknown -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical excep… |  |  |
| 55 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.6 | 16.0 | Y/N | fenced |  | 7 | 2\sqrt{113} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.57s in unifor… |  |  |
| 57 | runtime_crash | N/N | 1 | stop | 1041 | 15.6 | 6.1 | Y/N | fenced | AttributeError | 9 | 30^\circ | TIMEOUT-SUSPECT(T1=15.57s in uniform window); CRASH:AttributeError -> library-misuse or i… |  |  |
| 58 | (strict-only) | N/Y | 0 | stop | 183 | 4.0 | 0.0 | N/N | fenced |  | 1.20000000000000 | \frac65 | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 65 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.7 | 16.0 | Y/N | fenced |  | 100 | -\sqrt{3} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.71s in unifor… |  |  |
| 67 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.6 | 16.1 | Y/N | fenced |  | 0 | \frac{270}7\text{ degre… | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.64s in unifor… |  |  |
| 69 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.9 | 16.5 | Y/N | fenced |  | 1 | 19 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.94s in unifor… |  |  |
| 74 | genuine_derivation_miss | N/N | 0 | stop | 294 | 6.0 | 0.0 | N/N | fenced |  | 16 | 4 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 77 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.5 | 16.0 | Y/N | fenced |  | 21 | .0000672 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.49s in unifor… |  |  |
| 78 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.8 | 16.1 | Y/N | fenced |  | 2 | 30^\circ | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.83s in unifor… |  |  |
| 80 | genuine_derivation_miss | N/N | 0 | stop | 1279 | 15.5 | 10.4 | Y/Y | fenced |  | 5x + -7y + 11z + 4 = 0 | 5x - 7y + 11z + 4 = 0 | TIMEOUT-SUSPECT(T1=15.49s in uniform window); DERIVATION-MISS -> reasoning (NOT v1.35 sco… |  |  |
| 82 | (strict-only) | N/Y | 0 | stop | 161 | 3.4 | 0.0 | N/N | fenced |  | 0.577350269189626 | \frac{\sqrt{3}}{3} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 84 | genuine_derivation_miss | N/N | 0 | stop | 311 | 6.4 | 0.0 | N/N | fenced |  | 13 | 23 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 85 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.5 | 16.0 | Y/N | fenced |  | 0.9 | (2,\infty) | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.51s in unifor… |  |  |
| 89 | prose_slip | N/N | 0 | stop | 1397 | 15.0 | 13.4 | Y/N | fenced |  |  | 6 | TIMEOUT-SUSPECT(T1=15.04s in uniform window); EMPTY-OUTPUT -> infra/extraction; PROSE-SLI… |  |  |
| 90 | genuine_derivation_miss | N/N | 0 | length | 1536 | 16.0 | 16.3 | Y/N | fenced |  | 2 | 160 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.95s in unifor… |  |  |
| 103 | (strict-only) | N/Y | 0 | stop | 290 | 6.0 | 0.0 | N/N | fenced |  | 0.666666666666667 | \frac{2}{3} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 105 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.6 | 16.0 | Y/N | fenced |  | 4 | 0 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.64s in unifor… |  |  |
| 106 | (strict-only) | N/Y | 0 | stop | 398 | 8.3 | 0.0 | N/N | fenced |  | Matrix([[-2], [-14], [-… | \begin{pmatrix} -2 \\ -… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 107 | (strict-only) | N/Y | 0 | stop | 198 | 4.2 | 0.0 | N/N | fenced |  | (1.5, -13) | \left( \frac{3}{2}, -13… | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 117 | genuine_derivation_miss | N/N | 0 | stop | 173 | 3.7 | 0.0 | N/N | fenced |  | 21/2 | 6 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 118 | equivalence_format_miss | N/N | 0 | stop | 1340 | 15.5 | 11.6 | Y/Y | fenced |  | 11111111100 | 11,\! 111,\! 111,\! 100 | TIMEOUT-SUSPECT(T1=15.53s in uniform window); FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 120 | equivalence_format_miss | N/N | 0 | length | 1536 | 16.0 | 16.5 | Y/N | fenced |  | 5 | \frac{1}{2} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=16.03s in unifor… |  |  |
| 123 | prose_slip | N/N | 0 | length | 1536 | 15.6 | 16.2 | Y/N | fenced |  |  | 54 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.61s in unifor… |  |  |
| 125 | (strict-only) | N/Y | 0 | stop | 432 | 8.9 | 0.0 | N/N | fenced |  | 3*sin(pi/9)**2*sin(2*pi… | \frac{9}{256} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 128 | (strict-only) | N/Y | 0 | stop | 132 | 2.8 | 0.0 | N/N | fenced |  | C | \text{(C)} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 133 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.6 | 15.5 | Y/N | fenced |  | 1 | \frac{1997}{2} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.58s in unifor… |  |  |
| 137 | (strict-only) | N/Y | 0 | stop | 1248 | 15.4 | 10.3 | Y/Y | fenced |  | sin(4*pi/9)**(-2) + sin… | 12 | TIMEOUT-SUSPECT(T1=15.44s in uniform window); STRICT-ONLY-FAIL -> grader candidate (check… |  |  |
| 140 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.7 | 15.8 | Y/N | fenced |  | 3 | 16 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.67s in unifor… |  |  |
| 141 | genuine_derivation_miss | N/N | 0 | stop | 1458 | 15.9 | 14.7 | Y/Y | fenced |  | 154 | 116 | TIMEOUT-SUSPECT(T1=15.93s in uniform window); DERIVATION-MISS -> reasoning (NOT v1.35 sco… |  |  |
| 149 | (strict-only) | N/Y | 0 | stop | 244 | 5.2 | 0.0 | N/N | fenced |  | Matrix([[-1, 0], [0, -1… | \begin{pmatrix} -1 & 0 … | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 156 | (strict-only) | N/Y | 0 | stop | 308 | 6.5 | 0.0 | N/N | fenced |  | E | \text{(E)} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 158 | equivalence_format_miss | N/N | 0 | stop | 440 | 9.1 | 0.0 | N/N | fenced |  | 72*12**(1/3) | 864 \mbox{ inches}^2 | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 165 | prose_slip | N/N | 0 | length | 1536 | 15.7 | 16.2 | Y/N | fenced |  |  | 1\frac{4}{5} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.73s in unifor… |  |  |
| 168 | runtime_crash | N/N | 1 | length | 1536 | 15.6 | 16.1 | Y/N | fenced | NameError |  | 180^\circ | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.63s in unifor… |  |  |
| 182 | prose_slip | N/N | 0 | length | 1536 | 15.8 | 16.3 | Y/N | fenced |  |  | 36^\circ | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.79s in unifor… |  |  |
| 185 | runtime_crash | N/N | 1 | length | 1536 | 15.6 | 16.1 | Y/N | fenced | TypeError | 4 | 3 \pm 2 \sqrt{2} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.56s in unifor… |  |  |
| 187 | prose_slip | N/N | 0 | length | 1536 | 15.7 | 15.6 | Y/N | fenced |  |  | \frac{17}{21} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.65s in unifor… |  |  |
| 191 | genuine_derivation_miss | N/N | 0 | stop | 353 | 7.3 | 0.0 | N/N | fenced |  | 7/2 | 4 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 194 | equivalence_format_miss | N/N | 0 | stop | 541 | 6.8 | 4.5 | Y/Y | fenced |  | Interval(3/5, 8/3) | \left(\frac{3}{5},\frac… | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 199 | (strict-only) | N/Y | 0 | stop | 246 | 5.2 | 0.0 | N/N | fenced |  | Matrix([[-18], [-49], [… | \begin{pmatrix} -18 \\ … | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 204 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.7 | 16.1 | Y/N | fenced |  | 0.5 | 28 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.65s in unifor… |  |  |
| 206 | equivalence_format_miss | N/N | 0 | stop | 242 | 5.1 | 0.0 | N/N | fenced |  | 0.473684210526316 | \frac9{19} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 207 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.7 | 16.0 | Y/N | fenced |  | 3 | 6 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.66s in unifor… |  |  |
| 208 | prose_slip | N/N | 0 | stop | 528 | 6.0 | 5.1 | Y/N | fenced |  |  | (-\infty, 0] | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction |  |  |
| 209 | prose_slip | N/N | 0 | length | 1536 | 15.6 | 16.0 | Y/N | fenced |  |  | 1+2\sqrt{3} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.61s in unifor… |  |  |
| 213 | (strict-only) | N/Y | 0 | stop | 209 | 4.4 | 0.0 | N/N | fenced |  | Interval(5, oo) | (5,\infty) | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 217 | prose_slip | N/N | 0 | stop | 411 | 4.7 | 4.0 | Y/N | fenced |  |  | 12 | EMPTY-OUTPUT -> infra/extraction; PROSE-SLIP -> extraction |  |  |
| 218 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.6 | 16.0 | Y/N | fenced |  | 1 | 0 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.57s in unifor… |  |  |
| 220 | genuine_derivation_miss | N/N | 0 | stop | 150 | 3.2 | 0.0 | N/N | fenced |  | 1 | -128 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 225 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.8 | 16.2 | Y/N | fenced |  | 1 | 120 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.84s in unifor… |  |  |
| 227 | equivalence_format_miss | N/N | 0 | stop | 976 | 15.5 | 4.7 | Y/Y | fenced |  | -9/100 | \frac{9}{100} | TIMEOUT-SUSPECT(T1=15.52s in uniform window); FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 228 | runtime_crash | N/N | 1 | stop | 1188 | 15.8 | 9.1 | Y/N | fenced | KeyError | 5 | 15 | TIMEOUT-SUSPECT(T1=15.83s in uniform window); CRASH:KeyError -> library-misuse or infra; … |  |  |
| 229 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.7 | 15.5 | Y/N | fenced |  | 0 | 3 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.73s in unifor… |  |  |
| 234 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.7 | 15.6 | Y/N | fenced |  | val | 3 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.65s in unifor… |  |  |
| 241 | runtime_crash | N/N | 1 | stop | 1370 | 15.7 | 12.8 | Y/N | fenced | AttributeError | 2 | 55^\circ | TIMEOUT-SUSPECT(T1=15.71s in uniform window); CRASH:AttributeError -> library-misuse or i… |  |  |
| 257 | equivalence_format_miss | N/N | 0 | stop | 461 | 9.4 | 0.0 | N/N | fenced |  | Interval(-sqrt(3), sqrt… | (-\sqrt{3}, \sqrt{3}) | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 262 | equivalence_format_miss | N/N | 0 | stop | 821 | 10.1 | 7.1 | Y/Y | fenced |  | -16*sqrt(3) | 16 \sqrt{3} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 272 | prose_slip | N/N | 0 | length | 1536 | 15.5 | 16.0 | Y/N | fenced |  |  | 17 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.53s in unifor… |  |  |
| 280 | genuine_derivation_miss | N/N | 0 | stop | 261 | 5.5 | 0.0 | N/N | fenced |  | 12th | 12 | DERIVATION-MISS -> reasoning (NOT v1.35 scope) |  |  |
| 281 | equivalence_format_miss | N/N | 0 | stop | 1021 | 14.5 | 6.3 | Y/Y | fenced |  | Interval(0, 36) | (0,9) \cup (9,36) | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 284 | equivalence_format_miss | N/N | 0 | stop | 239 | 5.0 | 0.0 | N/N | fenced |  | Interval(-2, 7) | x \in [-2,7] | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 290 | (strict-only) | N/Y | 0 | stop | 293 | 6.1 | 0.0 | N/N | fenced |  | 0.916515138991168 | \frac{\sqrt{21}}{5} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 293 | prose_slip | N/N | 0 | length | 1536 | 15.8 | 16.2 | Y/N | fenced |  |  | \sqrt{66} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.83s in unifor… |  |  |
| 301 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.6 | 16.0 | Y/N | fenced |  | 2 | \frac{14}{3} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.63s in unifor… |  |  |
| 309 | (strict-only) | N/Y | 0 | stop | 404 | 8.2 | 0.0 | N/N | fenced |  | Matrix([[0.200000000000… | \begin{pmatrix} 1/5 \\ … | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |
| 320 | runtime_crash | N/N | 1 | stop | 1079 | 15.6 | 6.8 | Y/N | fenced | KeyError | 0 | \begin{pmatrix} -7 \\ 1… | TIMEOUT-SUSPECT(T1=15.57s in uniform window); CRASH:KeyError -> library-misuse or infra; … |  |  |
| 321 | equivalence_format_miss | N/N | 0 | stop | 441 | 5.5 | 4.0 | Y/Y | fenced |  | (16/49, 48/49, 24/49) | \begin{pmatrix} 16/49 \… | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 322 | prose_slip | N/N | 0 | length | 1536 | 15.6 | 16.1 | Y/N | fenced |  |  | 27 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.60s in unifor… |  |  |
| 323 | runtime_crash | N/N | 1 | length | 1536 | 15.7 | 16.1 | Y/N | fenced | NameError |  | \{1\pm\sqrt{5},-2\} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.72s in unifor… |  |  |
| 326 | prose_slip | N/N | 0 | length | 1536 | 15.6 | 16.1 | Y/N | fenced |  |  | 3R^2 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.57s in unifor… |  |  |
| 332 | equivalence_format_miss | N/N | 0 | stop | 1374 | 15.5 | 12.7 | Y/Y | fenced |  | (pi**2/8, 5*pi**2/4) | \left[ \frac{\pi^2}{8},… | TIMEOUT-SUSPECT(T1=15.46s in uniform window); FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 336 | equivalence_format_miss | N/N | 0 | stop | 358 | 7.3 | 0.0 | N/N | fenced |  | Union(Interval(-oo, 2),… | (-\infty, 2) \cup (3, \… | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 345 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.6 | 16.1 | Y/N | fenced |  | 2 | \frac{1}{2} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.65s in unifor… |  |  |
| 346 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.9 | 16.2 | Y/N | fenced |  | 2 | 15 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.91s in unifor… |  |  |
| 361 | prose_slip | N/N | 0 | length | 1536 | 15.7 | 16.2 | Y/N | fenced |  |  | 75^\circ | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.70s in unifor… |  |  |
| 370 | runtime_crash | N/N | 1 | stop | 175 | 2.2 | 1.6 | Y/N | fenced | NameError | ceil | 25 | CRASH:NameError -> library-misuse or infra; TURN2-DID-NOT-RECOVER (check if identical exc… |  |  |
| 373 | equivalence_format_miss | N/N | 0 | stop | 118 | 2.5 | 0.0 | N/N | fenced |  | 275/2 | 137 \frac{1}{2} | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 379 | runtime_crash | N/N | 1 | stop | 1486 | 15.6 | 15.1 | Y/N | fenced | AttributeError |  | \frac{2}{1005} | TIMEOUT-SUSPECT(T1=15.59s in uniform window); CRASH:AttributeError -> library-misuse or i… |  |  |
| 382 | genuine_derivation_miss | N/N | 0 | length | 1536 | 15.8 | 15.5 | Y/N | fenced |  | 1 | 8n^2 + 4n + 1 | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.76s in unifor… |  |  |
| 395 | equivalence_format_miss | N/N | 0 | length | 1536 | 15.6 | 16.1 | Y/N | fenced |  | 2 | \frac{1}{4} | TRUNCATION(finish_reason=length) -> infra/extraction; TIMEOUT-SUSPECT(T1=15.62s in unifor… |  |  |
| 396 | equivalence_format_miss | N/N | 0 | stop | 1140 | 23.3 | 0.0 | N/N | fenced |  | Interval(2, 102) | (2,12) \cup (12,102) | FORMAT-MISS -> grader or reasoning (inspect) |  |  |
| 398 | (strict-only) | N/Y | 0 | stop | 344 | 7.0 | 0.0 | N/N | fenced |  | 3.50000000000000 | \frac{7}{2} | STRICT-ONLY-FAIL -> grader candidate (check CAS equivalence) |  |  |

## Label counts (fill after labeling)

- `infra`: 
- `extraction`: 
- `grader`: 
- `library-misuse`: 
- `reasoning`: 
