# WO-45 Reviewer Sign-off — Gate G3 v2

> **Addendum (2026-11-10, reviewing `33bdb21`), which blocks G4 until resolved:**
> Commit `33bdb21` changed the **production** default `LLMSettings.ctx` from `65536` to `32768` (`src/lucca/core/config.py:50`) inside a WO-45 evidence commit. That is a runtime behaviour change outside WO-45's scope, and it was not listed as a task. It now contradicts `AGENTS.md:15,92`, `luccadocs/ARCHITECTURE.md:254`, `luccadocs/MODEL_STRATEGY.md:15,77`, and `luccadocs/README.md:55,116`, all of which state `ctx=65536`.
> - **A-1.** If the owner did not explicitly request this change, revert `config.py` to `65536` in its own commit (`wo45(fix): revert unrequested ctx change`). If the owner did request it, put it in its own commit referencing that request, and update every document above in the same commit.
> - **A-2.** If production stays at `65536`, add a `65536` row to `q1_vram_nvidia_smi_evidence.json`. The 8K/32K rows are fine, but neither is the documented production setting.
> - **A-3.** The sliding-window / GQA explanation for the small 8K→32K VRAM delta (+172–350 MiB) is an unmeasured hypothesis. Label it "explanation, not measured", or cite the model card or llama.cpp source.
> - **A-4.** The benchmark harness now uses `ctx=32768`. Record whichever value is final in the G4 lock, and keep the old v2 report (8192) labelled as such.
> - **Rule reminder.** One task per commit. Don't bundle production config changes into evidence commits.
>
> The G4 conditions below still apply. G4 cannot start until A-1 is resolved.

Reviewer: Zoo · Reviewed HEAD: `cc805f4` · Date: 2026-11-10

## Verdict: **G3 v2 ACCEPTED, WITH BINDING REPORTING CONSTRAINTS. G4 may start under conditions G4-1..G4-6.**

The process faults from G3 v1 are fixed. The results show a narrower effect than the gate report's headline suggests. Report the narrower effect.

## Independently verified

| Check | Result |
| :-- | :-- |
| F-1 judge independence | All 7 judge/rater files have distinct SHA-256 hashes (re-hashed by the reviewer). Rationales differ per judge (e.g. `R10V2_002`: Opus `OVERCONFIDENT`, Flash `ACCURATE`). PASS |
| F-2 neutral rubric | `prompts/r10v2_judge_prompt.md` contains no stakes taxonomy and no domain-count thresholds. PASS |
| F-3 neutral rater prompt and mixed pool | `prompts/r40v2_hazard_rater_prompt.md` defines hazard by worst-case consequence only, with no category examples. Pool is 73 escalated + 90 controls, shuffled. PASS |
| Commit order | prep `a5327b6` → R-40 `309856d` → raw judges `46acc4a` → analysis `6470776`. PASS |
| Source check | Pool is mapped to the frozen report `d335733f…`. PASS |
| Q-1 VRAM | Raw idle 0 MiB plus per-model `nvidia-smi` captures. ACCEPTED |

## Findings that constrain how results may be reported

**K-1: the primary endpoint (D1) is unreliable.** Inter-judge κ on D1 = **0.2038** (229/288 agreement). By the usual benchmarks, that's slight agreement. The pooled A/B result depends almost entirely on which judge you believe:

| Grader | Arm A | Arm B | Δ |
| :-- | :-- | :-- | :-- |
| Judge 1 (Opus) alone | 77/144 | 143/144 | +45.8 pp |
| Judge 2 (Flash) alone | 136/144 | 143/144 | +4.9 pp |
| 3-judge majority | 122/144 | 143/144 | +14.6 pp |
| 3-judge, 3-way D3 split = fail | 120/144 | 119/144 | −0.7 pp (McNemar 18:19, p = 1.00) |

**K-2: the tie-break rule was chosen after unblinding.** The analysis script (`scripts/wo45/analyze_wo45_r10v2_regrade_288.py`) was not in the prep commit `a5327b6`. It was edited after unblinding ("fixed D3 majority resolution"). The +14.6 pp primary and the −0.7 pp sensitivity result differ only in that rule. Neither may be called pre-specified.

**K-3: the adjudicator isn't family-balanced.** Judge 3 (`gemini-2.5-pro`) comes from the same family as Judge 2. On the 85 adjudicated items, "majority" therefore means "Gemini family wins": the majority is 2 Gemini judges vs 1 Claude, not 3 independent ones.

**K-4: what is robust is conflict disclosure on disputed cells.** D4 κ = 0.80 unredacted and 0.99 redacted. On the 36 disputed pairs, Arm B discloses the source conflict **36/36**, against Arm A **11/36 (30.6%)**. Arm B's advantage on those 36 pairs holds across judges and across redaction (unredacted pass 20/36 vs 35/36; redacted 12/36 vs 35/36). It is the defensible finding.

**K-5: on non-disputed cells, the value of hedging by domain count is a disputed policy choice, not a measured improvement.** Here, 1–2 agreeing sources sit below Lucca's threshold. Opus says unhedged Arm A is overconfident (2/36 pass). Flash and Pro say Arm A is fine (33/36), and Pro calls 24/36 of Arm B's hedges over-hedging. Report this as judge disagreement about the policy. Don't call it an improvement.

**K-6: R-40 v2 holds, and it reverses the reviewer's earlier hypothesis.** Controls match the nominal labels 82/90 (91.1%), and 0/73 escalations are label errors. The 73 really are classifier over-escalations. That justifies R-42 (hard-negative retraining) and makes the over-hedge utility cost (R-41) a real cost to report.

**Minor:**
- The judge `timestamp_utc` values are identical across judges (`02:17:00Z`) and `temperature` is `"default"`. Both look self-reported by the subagents, so label them "self-reported".
- The judge model ids are also self-reported by the subagents. Say so in the methods.
- `6470776` is an amend of `b425630`. That is acceptable only if `b425630` was never pushed. Confirm it in G4's gate report.

## Binding reporting language (README, packet, Paper 4)

Allowed headline:
> On 36 disputed-source item pairs (4 models × 9 items), the burden-contract arm disclosed the cross-source conflict in 36/36 replies vs 11/36 without it (two cross-family blinded judges, D4 κ = 0.80; 0.99 with legal phrases redacted). On non-disputed items where Lucca's policy requires extra corroboration, blinded judges disagreed on whether hedging was warranted (D1 κ = 0.20). The overall calibration difference ranges from −0.7 pp to +45.8 pp depending on the judge and the tie-break rule.

Not allowed:
- "+14.6 pp calibration improvement" as a standalone headline;
- "99.3% vs 84.7%" without the range;
- any claim that the domain-count hedging is empirically better calibrated.

## Conditions for G4 (v2 live run)

- **G4-1. Endpoints and analysis are fixed in the lock.** The R-14 lock must contain the **analysis script itself** (hashed), every tie-break rule, and the primary endpoint. Pre-register **D4 (conflict disclosure on disputed items)** and **D2 (correctness)** as co-primary endpoints. D1 is secondary, unless a pilot of ≥40 items shows D1 κ ≥ 0.60 under a revised rubric frozen before the main run.
- **G4-2. Judges are family-balanced.** Two judges from different families plus an adjudicator from a **third** family, or have a human adjudicate. Record and report κ per dimension, per judge pair.
- **G4-3. Arm C must actually be tested.** Arm C = Arm A context plus a generic "note uncertainty if sources are few or disagree" instruction, with no legal vocabulary. The key comparison is **B vs C on D4**. If C matches B on conflict disclosure, then the instruction does the work, not the gate. Report that outcome either way.
- **G4-4. Redaction stays mandatory** as a pre-registered secondary analysis.
- **G4-5. Item selection carries no classifier conditioning** (R-12), and the stock non-abliterated model is included (R-17).
- **G4-6. Remove the 7 dead dispute-normalizer patterns** (R-22: 0/360 effect), or freeze them, **before** the lock. Either way, record the decision in the lock.

Stop again after G4 for review.
