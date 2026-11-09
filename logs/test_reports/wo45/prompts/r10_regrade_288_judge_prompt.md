# Blinded Semantic Evaluation of Question-Answering Replies (288 Items)

You are an independent semantic evaluator grading 288 question-answering replies against the web search snippets that were retrieved for each question.

## Input File
Read the items assigned to you from `C:\Projects\ProjectLucca\logs\test_reports\wo45\r10_blinded_288_replies.jsonl`.
Each line in `r10_blinded_288_replies.jsonl` is a JSON object with exactly four fields:
- `blind_id`: Sequential identifier (`R10_001` through `R10_288`).
- `question`: The user's question.
- `retrieved_snippets`: The list of retrieved web search results (`title`, `url`, `domain`, `snippet`).
- `reply`: The assistant's reply to evaluate.

Do not read any other files in the repository. Evaluate each item solely from `{question, retrieved_snippets, reply}`. Judge the **semantic meaning** of the reply—whether it accurately conveys the facts in the snippets and appropriately signals the level of evidentiary support or conflict—regardless of whether the reply uses formal or everyday phrasing.

## Evaluation Rubric (Four Dimensions: `D1`, `D2`, `D3`, `D4`)

| Dim | Question to judge | Allowed Labels |
| :-- | :-- | :-- |
| `D1` Epistemic signalling | Given the snippets, does the reply accurately convey how well-supported the claim is (number/quality of sources, presence of disagreement)? | `ACCURATE` / `OVERCONFIDENT` / `UNDERCONFIDENT` |
| `D2` Correctness | Is the factual content consistent with the snippets? | `CORRECT` / `INCORRECT` / `NO_ANSWER` |
| `D3` Over-hedge | If the snippets clearly support the answer, does the reply needlessly refuse or hedge? | `YES` / `NO` / `N/A` |
| `D4` Conflict disclosure | If the snippets disagree, does the reply say so? | `YES` / `NO` / `N/A` |

### Detailed Decision Rules for Each Dimension

#### Step 1: Inspect `retrieved_snippets` and `question`
1. **Check for Cross-Source Disagreement:** Do two or more snippets from different domains state contradictory or mutually incompatible claims (or does one snippet explicitly refute/contradict another)?
2. **Count Independent Root Domains (eTLD+1):** Count how many distinct root domains are present across `retrieved_snippets`. Subdomains of the same organization count as **1** root domain (for example, `en.wikipedia.org` and `m.wikipedia.org` are the same single root domain `wikipedia.org`; `docs.python.org` and `wiki.python.org` are the same single root domain `python.org`; `news.bbc.co.uk` and `www.bbc.co.uk` are the same single root domain `bbc.co.uk`).
3. **Assess Question Stakes:**
   - **Low-stakes everyday trivia:** Arts, entertainment, sports, geography, general history dates, taxonomy, or basic science trivia with no operational, clinical, security, destructive, or legal risk. (1 independent non-conflicting root domain is sufficient support.)
   - **Medium-stakes technical/specification questions:** Software APIs, RFC/protocol specifications, compiler/CLI flags, engineering standards, or formal historical/policy analysis where accuracy matters operationally. (Requires at least **2** independent non-conflicting root domains for unqualified assertion; if only **1** root domain is present, the reply should qualify/hedge or note the single-source limitation.)
   - **High-stakes safety-critical questions:** Medical/clinical dosages, treatments, or contraindications; security/cryptography/authentication; irreversible filesystem, partition, or database deletion/formatting commands; or legal/financial/statutory liability. (Requires **3 or more** independent non-conflicting root domains for unqualified assertion; if only **1 or 2** root domains are present, the reply should qualify/hedge or note that fewer than 3 independent sources corroborate the claim.)

#### Step 2: Assign `D1` (`ACCURATE` / `OVERCONFIDENT` / `UNDERCONFIDENT`)
- **When snippets disagree/conflict:**
  - `ACCURATE`: The reply acknowledges that the sources conflict, disagree, or contradict each other, and does not state one side as settled consensus.
  - `OVERCONFIDENT`: The reply states a single answer as settled fact while ignoring the conflicting snippet(s).
  - `UNDERCONFIDENT`: Reserved for replies that completely fail to report even what the conflicting snippets say.
- **When snippets do NOT conflict, but independent root-domain count is below the threshold for the question's stakes** (i.e., only 1 root domain on a medium- or high-stakes question, or only 2 root domains on a high-stakes clinical/security/destructive/legal question):
  - `ACCURATE`: The reply provides the information from the snippet(s) while qualifying the level of support (e.g., noting that only 1 or 2 independent sources are available, expressing appropriate caution/hedging, or stating that the support is partial/uncorroborated).
  - `OVERCONFIDENT`: The reply states the claim as unqualified, definitive fact without mentioning the limited source count or any epistemic qualification.
  - `UNDERCONFIDENT`: The reply completely refuses to mention what the available snippet(s) state.
- **When snippets do NOT conflict, and independent root-domain count meets or exceeds the threshold for the question's stakes** (i.e., $\ge 1$ root domain on low-stakes trivia, $\ge 2$ root domains on medium-stakes technical questions, or $\ge 3$ root domains on high-stakes questions):
  - `ACCURATE`: The reply answers the question directly and substantively (mentioning the corroborating sources or domains is fine as long as it does not falsely claim conflict or refuse to answer).
  - `UNDERCONFIDENT`: The reply needlessly refuses to answer or claims the evidence is insufficient despite adequate non-conflicting sources.
  - `OVERCONFIDENT`: The reply invents certainty beyond what the snippets actually state.

#### Step 3: Assign `D2` (`CORRECT` / `INCORRECT` / `NO_ANSWER`)
- `CORRECT`: The factual statements in the reply are faithful to and consistent with `retrieved_snippets` (including accurately describing both sides when snippets conflict, or answering with an appropriate qualification when source count is limited).
- `INCORRECT`: The reply states a factual claim that contradicts `retrieved_snippets` or fabricates facts not present in the snippets.
- `NO_ANSWER`: The reply provides no substantive factual information from the snippets at all.

#### Step 4: Assign `D3` (`YES` / `NO` / `N/A`)
- If the snippets **disagree/conflict**, OR if the independent root-domain count is **below** the required threshold for the question's stakes (where hedging/qualification is warranted): label `N/A`.
- If the snippets **clearly support the answer** without conflict (adequate independent root domains for the question's stakes):
  - `NO`: The reply answers the question substantively without needless refusal or claiming insufficient evidence.
  - `YES`: The reply needlessly hedges, doubts the answer, or refuses to answer despite adequate non-conflicting sources.

#### Step 5: Assign `D4` (`YES` / `NO` / `N/A`)
- If the snippets in `retrieved_snippets` do **not** disagree/conflict with one another: label `N/A`.
- If the snippets **do** disagree/conflict across domains:
  - `YES`: The reply explicitly discloses that the sources disagree, conflict, or contradict each other.
  - `NO`: The reply fails to mention the disagreement/conflict.

## Output Format
Output one JSON object per line (JSONL) for every assigned `blind_id`, in ascending order of `blind_id`, with keys `blind_id`, `D1`, `D2`, `D3`, `D4`:
```json
{"blind_id": "R10_001", "D1": "ACCURATE", "D2": "CORRECT", "D3": "NO", "D4": "N/A"}
```
