# Rule 04: Code Quality, Typing & Testing Standards

1. **Python Standards:**
   - Target version: Python 3.12+.
   - Package manager: `uv`.
   - Linter/Formatter: `ruff`.

2. **Type Safety:**
   - All cross-boundary IPC, payloads, and tool arguments must use Pydantic v2 schemas (`BaseModel`).
   - Zero tolerance for untyped dictionaries or `Any` in public module signatures.

3. **Mechanical Testing Mandate:**
   - Every module must include unit tests verifying boundary values and failure recovery.
   - All tests must be runnable via `uv run pytest tests/`.
   - Never write mock tests that merely assert `True == True`. Test mathematical invariants, failure cases, and latency budgets.
