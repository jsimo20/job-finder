---
description: Autofill a job application form in-browser via the application-autofiller subagent — everything except Submit
argument-hint: <application-url> [path-to-per-job-folder]
---

Standalone autofill for any job application URL — including roles that aren't tracked in the job-finder DB. Delegates the work to the `application-autofiller` subagent (Sonnet), which drives the Playwright MCP through the form, fills every mappable field, uploads the resume + cover-letter PDFs, and stops without submitting. The user reviews the filled form in the open browser and clicks Submit themselves.

This command is intentionally thin — almost all the actual procedure lives in `.claude/agents/application-autofiller.md`. Keeping the subagent definition as the source of truth means both `/fill-application` and `/job-apply`'s step h get the same behavior.

## What to do

### 1. Parse arguments

Argument: `$ARGUMENTS`.

- **First token** = the application URL (required). If missing, ask the user for it.
- **Second token** = absolute path to the per-job folder (optional). The folder should contain the tailored resume PDF, cover letter PDF, and a per-app `standard_answers.md`.

If no folder is given, the autofiller will fall back to the global `standard_answers.md` in the configured `inputs_dir` (`profile/profile.toml` `[paths]`; default `profile/`) for field values and ask which resume / cover-letter PDFs to upload.

### 2. Dispatch the `application-autofiller` subagent

Use the `Agent` tool with `subagent_type: application-autofiller`. Pass these inputs inline in the prompt:

- `application_url`: the URL from $ARGUMENTS
- `folder_path`: the folder path from $ARGUMENTS (or the literal string "GLOBAL_DEFAULTS_ONLY" if none given)
- `short_answer_drafts`: usually empty for the standalone path. If the user handed you any drafted essay text in conversation before invoking this command, include it.

The autofiller runs on Sonnet and handles everything from there. It will produce a structured report (Filled / Blank / Next-step) at the end.

### 3. Surface the report

When the subagent returns, present its report verbatim to the user. Add no commentary unless something needs flagging. End with:

> Ready for your review — check every answer in the open browser window and click Submit yourself. If this was a tracked role, run `job-finder mark-applied <external_id>` after submitting.

### 4. If the form is unreachable — hand off, don't stop short

An account wall, login requirement, or CAPTCHA is a handoff, not a failure. The autofiller reports the blocker and stops (it never creates accounts or enters passwords). When that happens and a per-job folder was given, write `APPLY_NOTES.md` into it: what's blocked and why, what's ready in the folder, the posting URL and req id, any file-type limits the portal states, and the ordered manual steps left. Then tell the user this one needs a hand-submit and link the folder. The command's job ends with the user knowing exactly what to do, never with a silent dead end.

## Prerequisite — Playwright MCP must be loaded

The autofiller's tool list includes `mcp__playwright__*`. Those tools only load when the Claude session is rooted in `projects/job-finder/` (the MCP is project-scoped via `.mcp.json`). If the subagent reports the tools aren't available, the parent session was started in the wrong directory. Tell the user to restart `claude` from inside the project directory; do not fall back to another browser tool.

## Hard rules (enforced by the autofiller)

- **Never submit the form.** Stop at the filled-but-unsubmitted state.
- **Never fabricate.** Leave fields blank rather than guess.
- **Salary always blank.**
- **EEO defaults only**, per `profile/profile.toml` `[eeo]` — fill exactly the questions that table sets a value for; leave every other voluntary-disclosure question blank. Override only if the user says so explicitly in the dispatching conversation.

## Why a subagent?

Earlier versions ran the autofill procedure inline in the main conversation. That meant every snapshot / click / type cycle billed against the Opus tier the parent session runs on. The work is mechanical — Sonnet handles it without quality loss, at ~5× lower cost per token. Delegating to a Sonnet subagent preserves Opus for the drafting work in `/job-apply` that actually benefits from Opus voice and judgment.
