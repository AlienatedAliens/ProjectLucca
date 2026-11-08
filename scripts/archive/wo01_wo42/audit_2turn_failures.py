import json
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

with open('logs/test_reports/final_math500_v1.3_heldout_400_aggregate.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

items = data.get('items', [])
failed_items = [x for x in items if not x.get('passed')]
print(f"Total Failures in 2-Turn Version: {len(failed_items)} / {len(items)}")

fb_triggered_but_failed = [x for x in failed_items if x.get('feedback_triggered')]
code_ran_zero_exit_wrong = [x for x in failed_items if not x.get('feedback_triggered') and x.get('exit_code') == 0]
crash_no_feedback = [x for x in failed_items if not x.get('feedback_triggered') and x.get('exit_code') != 0]

print(f"1. Feedback Triggered but Turn-2 Failed: {len(fb_triggered_but_failed)}")
print(f"2. Code Ran Cleanly (Exit 0) but Wrong Math / Format Miss: {len(code_ran_zero_exit_wrong)}")
print(f"3. Crash but Feedback Not Triggered (Exit != 0): {len(crash_no_feedback)}")

print("\n--- Details of the 12 Feedback Failures (Triggered but Failed) ---")
for idx, x in enumerate(fb_triggered_but_failed):
    pred = x.get('predicted_ans')
    exp = x.get('expected_ans')
    code = x.get('generated_code', '')
    stderr = x.get('stderr', '')
    exit_c = x.get('exit_code')
    print(f"[{idx+1}] Idx {x.get('idx')}: Subj: {x.get('subject')} (L{x.get('level')})")
    print(f"     Exit Code: {exit_c} | Stderr: {stderr[:60]!r}")
    print(f"     Pred: {pred!r} | Exp: {exp!r}")

print("\n--- Why did 106 cases have Exit 0 but Fail? ---")
format_misses = []
wrong_math = []
empty_pred = []
for x in code_ran_zero_exit_wrong:
    pred = str(x.get('predicted_ans', '')).strip()
    exp = str(x.get('expected_ans', '')).strip()
    if not pred:
        empty_pred.append(x)
    elif pred in exp or exp in pred:
        format_misses.append(x)
    else:
        wrong_math.append(x)

print(f"   Empty Output (printed nothing or prose without answer): {len(empty_pred)}")
print(f"   Likely Format Miss (substring / unnormalized LaTeX match): {len(format_misses)}")
print(f"   Genuine Wrong Math (computed wrong value): {len(wrong_math)}")

print("\nSample Likely Format Misses:")
for x in format_misses[:6]:
    print(f"   Idx {x.get('idx')}: Pred={x.get('predicted_ans')!r} | Exp={x.get('expected_ans')!r}")

print("\nSample Genuine Wrong Math:")
for x in wrong_math[:6]:
    print(f"   Idx {x.get('idx')}: Pred={x.get('predicted_ans')!r} | Exp={x.get('expected_ans')!r}")
