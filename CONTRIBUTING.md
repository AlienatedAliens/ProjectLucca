# Contributing to Project Lucca

Thank you for your interest in contributing to Project Lucca. Lucca is an autonomous, local-first desktop companion combining neural language models, symbolic reasoning, and sandboxed execution.

Because Lucca operates with strict safety invariants and empirical provenance, all contributors (human and AI agents alike) must adhere to the ground rules below.

---

## 1. Ground Rules & Invariants

1. **Never Alter Measured Results:**  
   Never modify measured benchmark numbers, raw benchmark artifacts (`data/benchmarks/`), or test logs to make documentation look better. Change the wording around the numbers or add caveats, never the numbers.
2. **Work in Small, Atomic Pull Requests:**  
   Group changes by area (e.g., documentation fixes in one PR, symbolic rule engine improvements in another). Do not mix doc rewrites with core code changes.
3. **Zero `Any` Invariant (`D-AUD-01`):**  
   All code added to `src/lucca/core/`, `brain/`, `reasoning/`, `sandbox/`, or `ui/` must be strictly typed. The use of `typing.Any` is strictly forbidden and checked by static gates.
4. **Quarantine Invariant for Induced Rules (`D-REAS-06`):**  
   Dynamically mined or synthesized MicroScheme LISP rules must be registered strictly in `QUARANTINE` mode. Never auto-promote rules to `ACTIVE`.
5. **No Direct Host Fallback (`D-AUD-13`):**  
   Sandboxed execution must never fall back to direct host execution. Execution runs inside Docker CE in WSL2.
6. **No Superlatives Without Artifact Citations:**  
   Do not describe results as "state-of-the-art", "flawless", or "verified" without citing the exact reproducible benchmark artifact, sample size, and hardware configuration.
7. **Human Owner Approval:**  
   All PRs must be reviewed and approved by the repository owner before merging.

---

## 2. Development Workflow

### Setup
```powershell
# Clone repository
git clone https://github.com/seatr/ProjectLucca.git
cd ProjectLucca

# Install dependencies via uv
uv sync

# Run environment verification
uv run python -m lucca.core.env_check
```

### Pre-Commit Checklist
Before submitting a pull request, ensure all static gates and regression tests pass:

```powershell
# 1. Run static architectural gates (enforces typing, manifest, and contract invariants)
uv run pytest tests/test_static_gates.py

# 2. Run fast unit test battery
uv run pytest -m "not tier2 and not hw and not soak and not net"

# 3. Check code formatting
uv run ruff check .
```

---

## 3. Disclosing AI-Assisted Work
Contributions developed with the assistance of AI coding tools or autonomous agents are welcome, but must be explicitly disclosed in the PR description, including the models used and human verification steps performed.
