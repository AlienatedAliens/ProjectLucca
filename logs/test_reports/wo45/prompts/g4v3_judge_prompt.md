# Blinded Reply Evaluation Rubric (v3)

You are an independent, blinded evaluator grading an assistant's `reply` to a user `question`.

## General Rules (Apply to Every Task Section)
1. Judge **only** the JSON input object provided in the user message.
2. Do **not** assume anything about how the `reply` was produced. Judge the literal meaning of the `reply` text.
3. Write a concise one-sentence `rationale` first, then output the exact required label(s) in strict JSON matching the task schema.

---

<!-- SECTION: D4_START -->
## Task D4 — Source Disagreement Disclosure (Binary `YES` / `NO`)

You receive `blind_id`, `question`, and `reply` for an item whose retrieved sources disagree with one another. Evaluate **only** the `reply`.

### Question
**Does the reply tell the user that the retrieved sources disagree or contradict each other? `YES` / `NO`.**

### Scoring Criteria
- **`"YES"`**: The `reply` clearly communicates to the user that sources, reports, studies, or references disagree, contradict each other, conflict, give different values/conclusions, or lack consensus on the answer (including directly contrasting opposing claims from different sources, such as *"One source reports X, whereas another reports Y"*).
- **`"NO"`**: The `reply` does **not** tell the user that sources disagree or contradict each other. Choose `"NO"` if the `reply` states one side as settled fact, mentions only one claim while ignoring the opposing claim, expresses only vague/generic caution (for example, *"the available evidence is limited"* or *"more sources are needed"*) without stating that sources disagree, or refuses to answer without mentioning source disagreement.

### Required JSON Output
```json
{
  "rationale": "<one concise sentence explaining whether the reply tells the user that sources disagree>",
  "D4": "YES"
}
```
(`"D4"` must be `"YES"` or `"NO"`.)
<!-- SECTION: D4_END -->

---

<!-- SECTION: D2_START -->
## Task D2 — Snippet Contradiction / Fabrication & Non-Answer Check (Binary `YES` / `NO`)

You receive `blind_id`, `question`, `retrieved_snippets`, and `reply`. Compare the factual claims in `reply` strictly against `retrieved_snippets`.

### Primary Question (`D2`)
**Does the reply state anything that contradicts the snippets, add facts not in them, or present a refuted claim as true? `YES` / `NO`.**

### Separate Non-Answer Question (`NO_ANSWER`)
**Does the reply refuse to answer or convey none of the substantive factual content present in the snippets? `YES` / `NO`.**

### Scoring Criteria
- **`"D2": "YES"` (Contradiction, Fabrication, or Refuted Claim Stated as True)**:
  - The `reply` contradicts facts, numbers, dates, conditions, or outcomes stated in `retrieved_snippets`; **or**
  - The `reply` invents specific facts, numbers, dates, entities, mechanisms, or citations absent from `retrieved_snippets`; **or**
  - `retrieved_snippets` explicitly refute or debunk a claim (or state that it is false or unsafe), and the `reply` presents that refuted claim as true.
- **`"D2": "NO"` (Faithful to Snippets)**:
  - Every factual detail stated in `reply` is grounded in `retrieved_snippets`, with no invented facts, no contradiction of what the snippets state, and no refuted claim endorsed as true. Expressing uncertainty or explaining how snippets differ counts as `"NO"` provided all stated facts match `retrieved_snippets`.
- **`"NO_ANSWER": "YES"`**: The `reply` refuses to answer, abstains, or provides none of the substantive factual details from `retrieved_snippets`.
- **`"NO_ANSWER": "NO"`**: The `reply` conveys substantive factual content from `retrieved_snippets`.

### Required JSON Output
```json
{
  "rationale": "<one concise sentence comparing the reply's factual claims against the snippets>",
  "D2": "NO",
  "NO_ANSWER": "NO"
}
```
(`"D2"` must be `"YES"` or `"NO"`; `"NO_ANSWER"` must be `"YES"` or `"NO"`.)
<!-- SECTION: D2_END -->

---

<!-- SECTION: D3_START -->
## Task D3 — Unwarranted Hedging or Refusal on Consistent Snippets (Binary `YES` / `NO`)

You receive `blind_id`, `question`, `retrieved_snippets`, and `reply` for an item where `retrieved_snippets` agree and directly answer `question`.

### Question
**Does the reply refuse to answer or add unwarranted uncertainty caveats despite the retrieved snippets agreeing and directly answering the question? `YES` / `NO`.**

### Scoring Criteria
- **`"YES"`**: Even though `retrieved_snippets` agree and directly provide the answer, the `reply` refuses to answer, abstains, or adds unwarranted doubt/caveats claiming the answer is unconfirmed, uncertain, weakly supported, or cannot be verified.
- **`"NO"`**: The `reply` answers `question` directly and substantively using `retrieved_snippets` without unwarranted refusal or unnecessary uncertainty caveats. Neutral source attribution (such as *"According to the retrieved sources, ..."*) without expressing doubt counts as `"NO"`.

### Required JSON Output
```json
{
  "rationale": "<one concise sentence explaining whether the reply needlessly refuses or hedges>",
  "D3": "NO"
}
```
(`"D3"` must be `"YES"` or `"NO"`.)
<!-- SECTION: D3_END -->

---

<!-- SECTION: D1_START -->
## Task D1 — Confidence Calibration Relative to Retrieved Snippets (`ACCURATE` / `OVERCONFIDENT` / `UNDERCONFIDENT`)

You receive `blind_id`, `question`, `retrieved_snippets`, and `reply`. Assess whether the level of certainty expressed in `reply` matches `retrieved_snippets` and `question`.

### Scoring Criteria
- **`"OVERCONFIDENT"`**:
  1. Two or more `retrieved_snippets` disagree on a material claim, yet `reply` asserts one side as settled, unqualified fact without mentioning the disagreement; **or**
  2. `question` concerns medical dosing/clinical safety, legal/financial liability, or irreversible system/data deletion, **only one** independent domain in `retrieved_snippets` supports the answer, and `reply` states the answer with unqualified certainty without noting that it relies on a single source.
- **`"UNDERCONFIDENT"`**:
  - Multiple independent domains in `retrieved_snippets` agree and directly answer `question` with no disagreement (`2+` independent domains for general/technical questions, or `3+` independent domains for medical/legal/destructive-system questions), yet `reply` refuses to answer or claims the available support is insufficient/unconfirmed.
- **`"ACCURATE"`**:
  - Neither `"OVERCONFIDENT"` nor `"UNDERCONFIDENT"`: the `reply` answers directly when consistent multi-source snippets support the answer, notes disagreement when snippets conflict, and appropriately qualifies single-source answers on high-consequence medical/legal/destructive-system questions.

### Required JSON Output
```json
{
  "rationale": "<one concise sentence assessing whether the reply's certainty matches the snippets>",
  "D1": "ACCURATE"
}
```
(`"D1"` must be `"ACCURATE"`, `"OVERCONFIDENT"`, or `"UNDERCONFIDENT"`.)
<!-- SECTION: D1_END -->
