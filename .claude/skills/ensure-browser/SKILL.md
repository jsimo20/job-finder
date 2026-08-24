---
name: ensure-browser
description: Get a usable browser for autofill before dispatching a fill agent. Starts Chrome if it is not running, waits for the Claude in Chrome extension to connect, and selects it. Use whenever a session needs to drive a form and `list_connected_browsers` is empty, or before an unattended batch that will autofill anything.
---

# ensure-browser

The Claude in Chrome tools attach to a Chrome the user is already running with
the extension connected. They do not launch one. A session that finds
`list_connected_browsers` empty is usually looking at a machine where Chrome
simply is not open, which this skill fixes, rather than a machine where the
extension is missing, which it cannot.

Run this **before** dispatching `application-autofiller-chrome`, not after it
fails.

## Which surface you actually need

Check in this order and stop at the first that works. Do not run this skill at
all if an earlier option already applies.

1. **Greenhouse, and the session can run Python.** Use
   `python -m job_finder.fill_greenhouse`. It drives its own Chromium, needs no
   connected browser, and costs roughly 2k tokens against the agent's 63k.
2. **`mcp__playwright__*` tools are loaded.** Use `application-autofiller`.
   Playwright launches its own browser, so this skill is unnecessary. The tools
   only load when the session is rooted in `projects/job-finder/`.
3. **Neither of the above.** You need a connected Chrome, so continue here.

## Procedure

### 1. Is a browser already connected?

`list_connected_browsers`. A non-empty result means you are done: call
`select_browser` with that `deviceId` and stop. Prefer an entry whose
`isLocal` is true.

### 2. Is Chrome running?

```powershell
Get-Process chrome -ErrorAction SilentlyContinue | Measure-Object | Select-Object -ExpandProperty Count
```

A count above zero with an empty browser list means Chrome is up but the
extension has not connected. Skip to step 4; starting a second Chrome will not
help.

### 3. Start Chrome

```powershell
$chrome = @("$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
            "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
            "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe") |
          Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { "chrome.exe not found"; exit 1 }
Start-Process $chrome -ArgumentList "about:blank"
```

Launch the default profile with no extra flags. The extension lives in that
profile and connects on its own; a custom `--user-data-dir` gets a clean
profile with no extension in it, which looks exactly like a failure and is not
one.

### 4. Wait for the extension to connect

Poll `list_connected_browsers` a few times, a couple of seconds apart, for
about 20 seconds total. Connection lags process start.

### 5. Select it

`select_browser` with the `deviceId`, then `tabs_context_mcp` once before any
other browser call. The Chrome tools require the tab-group context to exist.

## When this cannot help, and what to say

If Chrome is running and the list is still empty after step 4, the extension is
not installed or not signed in. **No skill can fix that**; it is a one-time
setup in the browser, by the user, in the extension's own interface.

Say exactly that and stop. Do not:

- start more Chrome processes hoping one connects
- launch Chrome with a different profile or `--user-data-dir`
- fall back to a browser tool the workflow did not authorise
- describe the run as blocked without naming the extension as the reason

For an unattended batch, a missing browser is not a dead end. Every role still
gets the full tailor, fact-check and render, and each folder gets an
`APPLY_NOTES.md` handoff for manual submission. Report the browser as
unavailable and keep going.

## Hard rules

- **Getting a browser is not permission to use it for anything else.** This
  skill exists so a fill agent can reach one application form. It is Chrome
  signed into the user's real accounts, so work only in tabs the fill agent
  creates and never read or navigate a tab it did not open.
- **Never sign in, create a profile, or accept a prompt** in the browser you
  start. If Chrome opens asking to sign in or restore a session, leave it and
  report what it asked.
- **Never submit anything.** The fill agents stop at the filled-but-unsubmitted
  state; starting the browser does not change that.
