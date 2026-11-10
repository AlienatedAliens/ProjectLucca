# Blinded Subagent Task Instructions (Shard Assignment Template)

Read the evaluation rubric at `C:\Projects\ProjectLucca\logs\test_reports\wo45\prompts\g4_live_v2_judge_prompt.md` and evaluate every item in your assigned input JSONL shard (`<ASSIGNED_SHARD_INPUT_PATH>`).

Strict rules:
1. Read **only** `C:\Projects\ProjectLucca\logs\test_reports\wo45\prompts\g4_live_v2_judge_prompt.md` and `<ASSIGNED_SHARD_INPUT_PATH>` using `read_file`.
2. Do **not** read any other file in the repository, do **not** search the repository, and do **not** run any command or script.
3. Evaluate every item directly on `D1`, `D2`, `D3`, and `D4` with a concise 1-sentence rationale per dimension.
4. Write all output JSONL lines (sorted by `blind_id`, valid JSON per line, ending with `\n`) to `<ASSIGNED_SHARD_OUTPUT_PATH>` using `write_file` (`Overwrite=true` on first chunk, `Append=true` on subsequent chunks).
5. When finished, send a short completion message reporting the number of lines written.
