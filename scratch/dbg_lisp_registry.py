"""Headless verification of the LISP Studio registry loading logic."""

from lucca.core.schemas import SkillMeta
from lucca.reasoning.skills import SkillManager

mgr = SkillManager()
rules: dict[str, dict] = {}
for root, default_status in ((mgr.skills_dir, None), (mgr.retired_dir, "RETIRED")):
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("_") or child.name.startswith("."):
            continue
        meta_file = child / "meta_info.json"
        plan_file = child / "plan.scm"
        if not meta_file.exists():
            continue
        try:
            meta = SkillMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"PARSE FAIL {meta_file}: {exc}")
            continue
        code = plan_file.read_text(encoding="utf-8") if plan_file.exists() else ""
        status = default_status or meta.status
        rules[meta.id] = {
            "category": ", ".join(meta.categories) if meta.categories else "-",
            "purpose": meta.description or meta.intent,
            "state": status,
            "code_len": len(code),
            "on_disk": True,
        }

print(f"Loaded {len(rules)} pathways:")
for rid, data in sorted(rules.items()):
    print(f"  {rid:26s} [{data['state']:9s}] {data['category']:28s} code={data['code_len']}ch")