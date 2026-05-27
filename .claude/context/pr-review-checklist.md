# PR Review Checklist

The python-code-reviewer agent imports this when running. Keep it short — it's the agent's working memory, not documentation.

## Before commenting
- [ ] Diff understood end to end (run `git diff origin/main...HEAD`)
- [ ] Adjacent files read only when needed to interpret the diff
- [ ] Repo's `ruff`/`pylint`/`mypy` config respected — don't redo what tooling already enforces

## Per-file pass
- [ ] Correctness: nulls, off-by-one, resource leaks, async/sync mixing
- [ ] Style: Google guide via `@.claude/context/google-python-style.md` (Python only)
- [ ] Idioms / perf: f-strings, comprehensions, pathlib, N+1
- [ ] Security: agent rules via `@.claude/context/ai-agent-security.md` when relevant; OWASP Top 10:2025 always
- [ ] Tests: present, asserting behavior not implementation
- [ ] No commented-out code, no `print()` debug residue, no logged secrets

## Severity tagging
- `CRITICAL` — security, data loss, build break → block
- `HIGH` — bug, perf regression, public API contract break → request changes
- `MEDIUM` — likely defect, missing test → request changes
- `LOW` — minor improvement → suggestion
- `NIT` — preference, formatting → optional

## Output discipline
- One comment per file + one summary at top
- Every finding: path, line, why, fixed code
- No fluff, no recap of the PR description
- Approve cleanly when clean — don't manufacture findings
