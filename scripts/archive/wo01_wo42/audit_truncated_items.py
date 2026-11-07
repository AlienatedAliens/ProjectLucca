import json
import ast
import re

ckpt = json.load(open('logs/test_reports/v1.3/checkpoint_math500_v1.3-baseline-heldout-400.json', encoding='utf-8'))

def has_ast_print(code_str):
    if not code_str:
        return False
    try:
        tree = ast.parse(code_str)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'print':
                return True
    except Exception:
        return 'print' in code_str
    return False

no_print_items = [x for x in ckpt if not has_ast_print(x.get('generated_code'))]

# 35 comment-only/truncated items
comment_truncated = []
for x in no_print_items:
    code = x.get('generated_code', '')
    try:
        tree = ast.parse(code)
        assigns = [s for s in tree.body if isinstance(s, ast.Assign)]
        fns = [s for s in tree.body if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef))]
        explicit = [t.id for s in assigns for t in s.targets if isinstance(t, ast.Name) and t.id.lower() in ('ans', 'answer', 'result', 'res', 'sol', 'solution', 'final_answer')]
        if not explicit and (len(assigns) == 0 or len([l for l in code.splitlines() if l.strip().startswith('#')]) >= len(code.splitlines()) / 2):
            comment_truncated.append(x)
    except Exception:
        comment_truncated.append(x)

print(f"Total no-print items: {len(no_print_items)}")
print(f"Selected comment-only / truncated items: {len(comment_truncated)}")

# Correlation with max_tokens (768)
hit_length_limit = [x for x in comment_truncated if x['llm_latency_s'] >= 14.5]
stopped_under = [x for x in comment_truncated if x['llm_latency_s'] < 14.5]

print(f"Hit 768-token limit (finish_reason='length'): {len(hit_length_limit)} ({len(hit_length_limit)/len(comment_truncated)*100:.1f}%)")
print(f"Stopped before limit (finish_reason='stop'): {len(stopped_under)} ({len(stopped_under)/len(comment_truncated)*100:.1f}%)")

print("\n--- Items Hitting 768-Token Limit (Truncated) ---")
for x in hit_length_limit[:12]:
    code = x.get('generated_code', '')
    last_line = code.splitlines()[-1] if code.splitlines() else ''
    print(f"Idx {x['idx']:3d} | Latency: {x['llm_latency_s']:5.2f}s | Chars: {len(code):4d} | Last Line: {last_line[:60]}")

print("\n--- Items Stopping Before Limit (Model Rambled and Stopped) ---")
for x in stopped_under[:12]:
    code = x.get('generated_code', '')
    last_line = code.splitlines()[-1] if code.splitlines() else ''
    print(f"Idx {x['idx']:3d} | Latency: {x['llm_latency_s']:5.2f}s | Chars: {len(code):4d} | Last Line: {last_line[:60]}")
