---
name: job-finder-weekly
description: The whole weekly cycle in one unattended run, with no API key. Polls every tracked board, reads the surviving job descriptions in-session, scores them, writes the digest, then runs the apply batch over the top N roles and reports once. Idempotent on a seven-day stamp, so a daily trigger is a no-op until a run is due. Accepts --top N (default 3), --apply-only, --pipeline-only, --force.
---

Run the weekly cycle end to end without stopping to ask. Built for a session
nobody is watching: a scheduled task, or someone who will read one report.

`$ARGUMENTS`: `--top N` or a bare number sets how many roles the apply batch
takes (default 3); `--apply-only` skips the pipeline; `--pipeline-only` skips
the apply batch; `--force` runs the pipeline even when the stamp says it is not
due; `--no-update` skips the engine update in step 0. Confirm what you are
about to do in your first message, in one line.

**Every Python call below is prefixed `PYTHONPATH=".cowork-deps:src" python3`,
run from the repo root.** On Windows in Claude Code, drop the prefix and use
`.venv/Scripts/python.exe`. If `.cowork-deps/` is missing, build it first with
`sh scripts/bootstrap_cowork_deps.sh`; it is gitignored and a fresh clone will
not have it.

## 0. Update the engine

Skip this step when `--no-update` was given, or when `.git` exists in the repo
root **without** `.git/shallow`: that is a developer checkout, which `git pull`
owns and an overlay would clobber. Every other install came from the setup
skill, as a tarball or a `git clone --depth 1` (which leaves `.git/shallow`),
and has no way to update itself except this.

```sh
curl -fsSL --max-time 60 -o /tmp/jf-main.tar.gz https://github.com/jsimo20/job-finder/archive/refs/heads/main.tar.gz \
  && tar tzf /tmp/jf-main.tar.gz > /dev/null \
  && before=$(cksum < pyproject.toml) \
  && tar xzf /tmp/jf-main.tar.gz --strip-components=1 \
  && { [ "$before" = "$(cksum < pyproject.toml)" ] && [ -d .cowork-deps ] || sh scripts/bootstrap_cowork_deps.sh; }
```

The archive is downloaded and verified before anything is extracted, so a
dropped connection leaves the current version intact. Extraction only writes
tracked files; `profile/`, `data/`, `.env`, `config/pipeline.toml` and
`.cowork-deps/` are gitignored and never in the archive.

**A failed update never stops the run.** Continue on the current version and
put one line in the report saying the update did not apply. Files deleted
upstream are not removed by an overlay and are harmless.

## 1. Is a run due?

```sh
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.weekly status
```

`due` is true when no run has ever finished or the last one is seven or more
days old. **If it is false and `--force` was not given, skip to step 5** (the
apply batch still runs against the existing digest) and say in the report that
the pipeline was not due. This is what makes a daily trigger safe: six days
out of seven the pipeline half costs nothing.

## 2. Collect

```sh
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.weekly collect
```

Zero tokens. Polls every tracked board, applies the title and location
filters, and writes every surviving job description that still needs reading
to `data/weekly/pending_extractions.jsonl`, one JSON object per line:
`posting_id`, `company`, `title`, `jd_text`. The printed stats carry
`pending_extractions` (how many), plus `errors` and `errors_detail` (boards
that did not answer). Put all three in the report; a board that failed
contributed nothing to this week's digest, and exit 0 does not say so.

## 3. Read the job descriptions

This is the one step that spends tokens. Estimate it first and say it:
roughly 2,000 tokens per pending posting, so 80 pending is about 160k. Then
proceed; a scheduled run has nobody to ask.

Get the instructions, verbatim, and split the work into batches of 25:

```sh
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.weekly prompt > data/weekly/extraction_prompt.txt
cd data/weekly && rm -f batch_* answers_* && split -l 25 -d pending_extractions.jsonl batch_ && cd ../..
ls data/weekly/batch_*
```

For each batch file, one subagent, all dispatched at once in a single
message (never one per posting; the per-agent startup cost is ~34k tokens, so
agent count is the whole bill). Use the smallest model the surface offers,
Haiku where you can pick. Each subagent's prompt is:

> Read `data/weekly/extraction_prompt.txt` and follow it exactly. Then read
> `data/weekly/batch_NN`, one JSON object per line. For each line, read its
> `jd_text` and produce the JSON object the instructions describe, with one
> extra field: `"posting_id"` copied from the input line unchanged. Write every
> result to `data/weekly/answers_NN.jsonl`, one JSON object per line, no prose,
> no fences, no blank lines. Reply with only the count of lines written.

If this surface cannot dispatch subagents, do the same work yourself, one
batch at a time, writing the same files. Never skip a batch silently.

Then store the answers:

```sh
cat data/weekly/answers_*.jsonl > data/weekly/extractions.jsonl
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.weekly import-extractions data/weekly/extractions.jsonl
```

Read `imported`, `skipped` and `errors_detail`. A skipped line is malformed
JSON or a `posting_id` that was not pending; re-run only those postings once,
by writing them to a fresh batch file, and import again. After that, report
whatever is still missing as unread rather than trying a third time.

## 4. Finish

```sh
PYTHONPATH=".cowork-deps:src" python3 -m job_finder.weekly finish
```

Scores every extraction, scans the configured discovery sites (a failure
there is reported in `discover_error` and does not stop the run), renders the
digest, archives it in `data/state.db`, and stamps the run. The printed
`digest` path is the week's output; name it in the report.

## 5. Apply

Unless `--pipeline-only` was given: read `.claude/skills/job-apply-batch/SKILL.md`
and follow it for the top N roles. Everything about the apply loop, its gates
and its hard rules lives there and is not restated here. Pass the same count
through; its default is 5 but this skill's default is 3, because on Cowork
every form costs roughly 63k tokens through the autofill agent.

## 6. Report once

One message, in this order:

1. Whether the pipeline ran, and why not if it did not.
2. Collect: companies polled, postings read, kept, boards that errored.
3. Extraction: pending, imported, still unread, tokens spent (your estimate).
4. The digest path and the top roles it holds.
5. The apply batch's own report sections, unchanged.

Delete `data/weekly/batch_*` and `data/weekly/answers_*` at the end;
`pending_extractions.jsonl` and `extractions.jsonl` stay for the next run to
overwrite.

## Hard rules

- The apply batch's hard rules apply unchanged: never Submit, salary blank,
  nothing untraceable, honour the no-auto list.
- Never add an API key, a credential or a payment detail to get past a step.
  The pipeline half needs none; if something asks for one, that is a bug to
  report, not a prompt to answer.
- A batch whose answers file is missing is a batch that was not read. Say so.
