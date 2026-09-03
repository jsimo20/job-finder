#!/usr/bin/env sh
# The setup eval. Runs SETUP.md's steps, in order, on a tree that has only the
# files a clone has, and asserts what each step is documented to do. Zero
# tokens; no network beyond pip (and the example ATS boards when COLLECT=1).
#
# It refuses to run on anything but a fresh clone, so it cannot touch a real
# profile/ by accident. Run it through scripts/fresh_clone_docker.sh, or in any
# throwaway checkout:
#
#     sh scripts/fresh_clone_check.sh
#
# Exit 0 when every assertion holds, 1 when any fails, 2 when the tree is not a
# fresh clone. Two of the stages are not about the code:
#
#   - "unattended gates on an empty clone" pins the exit codes the batch skill
#     reads (3 = nothing to check, never a pass).
#   - "ground-truth paths" checks that every file the apply loop reads exists
#     where `job_apply.load_config()` resolves it on a SETUP.md-built profile,
#     and that no prompt under .claude/ or cowork-plugin/ names a profile layout
#     of its own. A prompt that hard-codes one user's folders is a gap the next
#     user hits on their first weekly run, with nobody watching.
set -u

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python}"
OUT="$(mktemp)"
TODAY="$(date +%F)"
PASSES=0
FAILS=0

pass() { PASSES=$((PASSES + 1)); printf 'PASS  %s\n' "$1"; }
fail() { FAILS=$((FAILS + 1)); printf 'FAIL  %s\n' "$1"; }
show() { sed 's/^/      | /' "$OUT" | tail -n "${1:-15}"; }
stage() { printf '\n== %s ==\n' "$1"; }

# expect_exit <label> <wanted exit> <command...>
expect_exit() {
    label=$1; want=$2; shift 2
    "$@" >"$OUT" 2>&1; got=$?
    if [ "$got" -eq "$want" ]; then
        pass "$label (exit $got)"
    else
        fail "$label: exit $got, wanted $want"; show
    fi
}

# expect_output <label> <extended regex>   -- against the last command's output
expect_output() {
    if grep -qiE "$2" "$OUT"; then pass "$1"; else fail "$1: no line matching /$2/"; show; fi
}

expect_file() { if [ -e "$2" ]; then pass "$1"; else fail "$1: $2 missing"; fi; }

# ── 0. Refuse anything that is not a fresh clone ─────────────────────────────
stage "fresh-clone guard"
for p in .env profile config/pipeline.toml data digests .venv .cowork-deps .playwright-mcp; do
    if [ -e "$p" ]; then fail "not a fresh clone: $p exists"; fi
done
if [ "$FAILS" -gt 0 ]; then
    echo "refusing to run: this tree has local state a clone would not."
    exit 2
fi
"$PYTHON" --version >"$OUT" 2>&1 && pass "interpreter: $(cat "$OUT") ($(uname -s))"

# ── SETUP.md §2 Install ──────────────────────────────────────────────────────
stage "SETUP.md §2: install"
expect_exit "python -m venv .venv" 0 "$PYTHON" -m venv .venv
if [ -d .venv/bin ]; then BIN="$PWD/.venv/bin"; else BIN="$PWD/.venv/Scripts"; fi
# What `activate` does, without sourcing a bash-only script under sh.
PATH="$BIN:$PATH"; export PATH
VIRTUAL_ENV="$PWD/.venv"; export VIRTUAL_ENV
expect_exit "pip install uv" 0 python -m pip install --quiet uv
expect_exit 'uv pip install -e ".[dev]"' 0 uv pip install --quiet -e ".[dev]"
expect_exit "job-finder console script is on PATH" 0 job-finder --help

stage "SETUP.md §2: the suite passes on a fresh clone with no profile"
expect_exit "python -m pytest -q" 0 python -m pytest -q -p no:cacheprovider
expect_output "pytest reports only passes" '^[0-9]+ passed'

# ── Before any personal config exists ────────────────────────────────────────
stage "commands a new user runs before configuring anything"
expect_exit "job-finder status with nothing configured" 0 job-finder status
expect_output "status says no digest yet" 'none archived'
expect_output "status says no pipeline run yet" 'no pipeline run recorded'
expect_exit "profile_check with no profile exits 1" 1 python -m job_finder.profile_check
expect_output "profile_check points at the copy step" 'cp -r profile\.example profile'

# ── SETUP.md §3 Profile ──────────────────────────────────────────────────────
stage "SETUP.md §3: profile from the example"
expect_exit "cp -r profile.example profile" 0 cp -r profile.example profile
expect_exit "an unedited example copy is refused" 1 python -m job_finder.profile_check
expect_output "profile_check names the placeholder identity" 'placeholder'
expect_output "profile_check names the missing pipeline.toml" 'pipeline\.toml not found'
expect_output "profile_check names the empty company list" 'no tracked companies'

# ── SETUP.md §4 + §5 Pipeline config and companies ───────────────────────────
stage "SETUP.md §4 + §5: pipeline config and company list"
expect_exit "cp config/pipeline.example.toml config/pipeline.toml" 0 \
    cp config/pipeline.example.toml config/pipeline.toml
expect_exit "job-finder companies import config/companies.example.json" 0 \
    job-finder companies import config/companies.example.json
expect_exit "job-finder companies list" 0 job-finder companies list
expect_output "the example companies are listed" 'gitlab'
expect_exit "job-finder init-db" 0 job-finder init-db
expect_exit "job-finder digest-archive list on an empty archive" 0 job-finder digest-archive list
expect_exit "job-finder applied list on an empty ledger" 0 job-finder applied list
expect_exit "job-finder no-auto list on an empty blocklist" 0 job-finder no-auto list
expect_exit "job-finder status after §5" 0 job-finder status
expect_output "status counts the imported companies" '3 tracked companies'

# ── The gates the unattended batch reads, before anything has been rendered ──
stage "unattended gates on an empty clone: 3 means nothing to check, never a pass"
expect_exit "letter_linter --date today" 3 python -m job_finder.letter_linter --date "$TODAY"
expect_exit "fill_grader --date today --gate" 3 python -m job_finder.fill_grader --date "$TODAY" --gate
expect_exit "skill_terms --folder <absent>" 3 python -m job_finder.skill_terms --folder profile/applications/none

# ── render() end to end on the example profile, zero tokens ──────────────────
stage "job_apply.render() on the example profile"
cat >"$OUT.render.py" <<'PY'
from job_finder import job_apply

posting_row = {
    "external_id": "fresh-1", "title": "Senior Product Manager, Platform",
    "company_name": "Example Corp", "location": "Farport, EX",
    "url": "https://example.com/jobs/fresh-1", "total_score": 80, "queue": "main",
}
resume_data = {
    "name": "Alex Sample",
    "title": "Senior Product Manager  |  Example Positioning",
    "contact": "555-555-0100",
    "experience": [{"company": "EXAMPLE CORP", "role": "SENIOR PM",
                    "dates": "JAN 2020 - PRESENT",
                    "bullets": ["Shipped the example platform to example customers."]}],
    "skills": [["Category One", "body one"], ["Category Two", "body two"],
               ["Category Three", "body three"], ["Category Four", "body four"]],
    "education": {"degree": "BS Example", "minor": "Minor: examples",
                  "school": "Example University", "dates": "2012 - 2016"},
    "certifications": ["Example certificate"],
}
cover_letter = {
    "date": "January 1, 2026",
    "recipient": "Example Corp Hiring Team\nExample Corp\nFarport, EX",
    "salutation": "To the Example Corp Hiring Team,",
    "paragraphs": [
        "Most platform teams ship the API first and the console later. Example Corp did it the other way around, which puts the weight on the console from day one.",
        "At Sample Co that weight lands on the developer console I own. Most of my time goes to what a developer sees in the first five minutes.",
        "The console is in Phase 1 and still in beta, so there are no results to point at yet.",
        "We moved to Farport in June. I look forward to discussing this opportunity in greater detail with you.",
    ],
    "closing": "Thanks,",
    "title_subtitle": "Senior Product Manager | Example Positioning",
}
out = job_apply.render(posting_row=posting_row, resume_data=resume_data,
                       cover_letter=cover_letter, why_this_matches=["one", "two"],
                       open_browser=False)
print(out)
PY
expect_exit "render() writes the per-job folder" 0 python "$OUT.render.py"
FOLDER="$(tail -n 1 "$OUT")"
expect_file "resume PDF" "$FOLDER/Alex_Sample_Resume_example-corp.pdf"
expect_file "cover letter PDF" "$FOLDER/Alex_Sample_CoverLetter_example-corp.pdf"
expect_file "cover_letter.json beside the PDFs" "$FOLDER/cover_letter.json"
expect_file "apply.md" "$FOLDER/apply.md"
expect_file "standard_answers.md copied in" "$FOLDER/standard_answers.md"
case "$FOLDER" in
    */profile/applications/*) pass "folder lands under profile/applications" ;;
    *) fail "folder landed at $FOLDER, not under profile/applications" ;;
esac

stage "gates with one rendered folder: they find it"
python -m job_finder.letter_linter --date "$TODAY" >"$OUT" 2>&1; got=$?
if [ "$got" -eq 3 ]; then
    fail "letter_linter --date today still reports nothing to lint (exit 3)"; show
else
    pass "letter_linter found the rendered letter (exit $got; 0 clean, 4 blocked)"; show 8
fi
expect_exit "skill_terms --folder <rendered> with no resume_skills.json" 3 \
    python -m job_finder.skill_terms --folder "$FOLDER"

# ── Every ground-truth path the apply loop reads, where load_config puts it ──
stage "ground-truth paths on a SETUP.md-built profile"
cat >"$OUT.paths.py" <<'PY'
import sys
from job_finder import job_apply, settings

cfg = job_apply.load_config(settings.require_profile())
paths = {
    "resume_master.md": cfg.resume_master_md,
    "personal_statement.md": cfg.personal_statement_md,
    "standard_answers.md": cfg.standard_answers_md,
    "qa_checklist.md": cfg.qa_checklist_md,
    "claims_ground_truth": cfg.claims_ground_truth,
    "writing_style": cfg.writing_style,
    "resume_skill": cfg.resume_skill,
}
missing = 0
for name, p in paths.items():
    ok = p.exists()
    missing += not ok
    print(f"  {'ok     ' if ok else 'MISSING'} {name:22} {p.relative_to(settings.REPO_ROOT)}")
sys.exit(1 if missing else 0)
PY
python "$OUT.paths.py" >"$OUT" 2>&1; got=$?
show 10
if [ "$got" -eq 0 ]; then
    pass "every file load_config() resolves exists"
else
    fail "load_config() resolves to files the example does not ship"
fi

# The prompts must resolve these paths the same way and never name a layout: a
# `profile/<dir>/` in a prompt is one user's folders baked into an unattended run.
grep -rnE 'profile/[A-Za-z_-]+/' .claude cowork-plugin --include='*.md' 2>/dev/null \
    | grep -v 'profile/applications/' >"$OUT"
if [ -s "$OUT" ]; then
    fail "a prompt names a profile layout instead of resolving it through [paths]"; show 10
else
    pass "no prompt under .claude/ or cowork-plugin/ names a profile layout"
fi

# ── The Cowork device VM path: bare python3, no editable install ─────────────
if [ "$(uname -s)" = "Linux" ] && command -v python3 >/dev/null 2>&1; then
    stage "Cowork device VM path: PYTHONPATH=\".cowork-deps:src\" python3"
    # Leave the venv so this is the system interpreter the VM would have.
    PATH="$(echo "$PATH" | sed "s|$BIN:||")"; export PATH; unset VIRTUAL_ENV
    expect_exit "sh scripts/bootstrap_cowork_deps.sh" 0 sh scripts/bootstrap_cowork_deps.sh
    expect_output "bootstrap's own import check passed" 'cowork-deps ready'
    expect_exit "liveness.partition() on an empty list" 0 sh -c '
        echo "[]" | PYTHONPATH=".cowork-deps:src" python3 -c "
from job_finder import liveness
import json, sys
worth, dead = liveness.partition(json.load(sys.stdin))
print(json.dumps({\"worth\": worth, \"dead\": dead}))
"'
    # 0 or 4 means it ran and graded; anything else (1 on a missing module, 3 on
    # nothing found) means the VM path did not reach the letter.
    expect_exit "letter_linter through the VM prefix graded the letter" 0 sh -c "
        PYTHONPATH='.cowork-deps:src' python3 -m job_finder.letter_linter --date $TODAY --quiet
        rc=\$?; [ \$rc -eq 0 ] || [ \$rc -eq 4 ]"
    expect_exit "job_finder.cli without --cli extras fails as documented" 1 sh -c '
        PYTHONPATH=".cowork-deps:src" python3 -m job_finder.cli digest-archive list'
    expect_output "...on a missing module, not something else" 'No module named'
    PATH="$BIN:$PATH"; export PATH
fi

# ── Optional: poll the three example boards (network, zero tokens) ───────────
if [ "${COLLECT:-0}" = "1" ]; then
    stage "COLLECT=1: job-finder collect against the example companies"
    expect_exit "job-finder collect" 0 job-finder collect
    show 12
fi

# ── Summary ──────────────────────────────────────────────────────────────────
printf '\n%d passed, %d failed\n' "$PASSES" "$FAILS"
rm -f "$OUT" "$OUT.render.py" "$OUT.paths.py"
[ "$FAILS" -eq 0 ]
