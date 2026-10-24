# Natural Language Inference (NLI) Second-Annotator Guidelines

```yaml
task: Natural Language Inference (NLI) 3-Way Classification
dataset_size: 100 pairs
target_classes: [ENTAILMENT, CONTRADICTION, NEUTRAL]
```

## 1. Overview & Objective

You are independently labeling 100 premise–hypothesis pairs for Project Lucca's semantic memory verification battery. The goal is to determine the logical/evidential relationship between the **Premise** (a known stored statement or context) and the **Hypothesis** (a proposed new statement, query, or belief).

Your labels will be compared against the primary developer's labels to compute **inter-annotator agreement (Cohen's $\kappa$)** and establish a validated multi-annotator ground truth.

---

## 2. Classification Schema

For each item, assume the **Premise is strictly true**. Choose exactly one label:

### A. `CONTRADICTION`
- **Definition:** If the premise is true, the hypothesis **cannot** be true (they are mutually exclusive or incompatible in the real world).
- **Key indicator:** Direct opposition, opposing preference, incompatible values for a single attribute (e.g. differing dates, locations, numbers, or statuses).
- **Examples:**
  - *Premise:* "The user prefers dark mode in their editor."  
    *Hypothesis:* "The user always uses light mode." $\to$ **`CONTRADICTION`**
  - *Premise:* "The meeting is scheduled for Tuesday at 3 PM."  
    *Hypothesis:* "The meeting is scheduled for Wednesday at 3 PM." $\to$ **`CONTRADICTION`**
  - *Premise:* "The file report.pdf was deleted yesterday."  
    *Hypothesis:* "The file report.pdf still exists in the folder." $\to$ **`CONTRADICTION`**

### B. `ENTAILMENT`
- **Definition:** If the premise is true, the hypothesis **must** be true (it is logically entailed or directly follows from common-sense implications).
- **Key indicator:** Paraphrase, simplification, specific-to-general deduction, or subset relationship.
- **Examples:**
  - *Premise:* "The user lives in Seattle, Washington."  
    *Hypothesis:* "The user lives in Washington State." $\to$ **`ENTAILMENT`**
  - *Premise:* "The backup completed successfully at 02:00."  
    *Hypothesis:* "The backup finished." $\to$ **`ENTAILMENT`**
  - *Premise:* "The user is vegetarian and avoids all meat."  
    *Hypothesis:* "The user does not eat beef." $\to$ **`ENTAILMENT`**

### C. `NEUTRAL`
- **Definition:** The premise does not provide enough information to know whether the hypothesis is true or false. The hypothesis *could* be true, or it *could* be false.
- **Key indicator:** Topic overlap without logical dependency; plausible but unstated additional facts.
- **Examples:**
  - *Premise:* "The user's primary code editor is VS Code."  
    *Hypothesis:* "The user is working on a Python project." $\to$ **`NEUTRAL`** (VS Code supports Python, but the user could be writing TypeScript or Go).
  - *Premise:* "The user lives in Seattle."  
    *Hypothesis:* "The user likes coffee." $\to$ **`NEUTRAL`** (Plausible association, but not logically entailed).

---

## 3. How to Submit Your Annotations

1. Open either `blinded_worksheet.csv` (in Excel, Google Sheets, or any text editor) or `blinded_worksheet.jsonl`.
2. Enter your label into the `annotator_label` column/field for all 100 items:
   - Use exact uppercase strings: `ENTAILMENT`, `CONTRADICTION`, or `NEUTRAL`.
3. Save the completed file as `completed_worksheet.csv` (or `.jsonl`).
4. Run the agreement calculation script:
   ```bash
   uv run python docs/funding/NLI_SECOND_ANNOTATOR_KIT/score_agreement.py --input docs/funding/NLI_SECOND_ANNOTATOR_KIT/completed_worksheet.csv
   ```
