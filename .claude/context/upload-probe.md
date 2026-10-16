# Upload probe

Proves the Playwright server can attach a file from this folder, and finds the
**uploads root**: the absolute path on the user's computer that every
`browser_file_upload` path starts from. Run it before anything that uploads.

The server accepts uploads only from its output folder and its working folder.
The plugin sets the output folder to `job-finder/.playwright-mcp` inside the
user's home folder, so on Cowork uploads work only when the connected folder
is `job-finder`, directly in the home folder. In Claude Code the repo is the
working folder and uploads work wherever it is.

Use one Playwright tool set, any tool whose name contains `playwright`. If two
sets are present, probe the first; if it is rejected, probe the second, and
use whichever is accepted for the whole run.

If any call fails with a `[File chooser]` modal state, call
`browser_file_upload` with no `paths` to close it, then repeat the call.

1. From the folder root:

   ```sh
   mkdir -p .playwright-mcp/uploads && echo upload probe > .playwright-mcp/uploads/_probe.txt
   ```

2. `browser_navigate` to `data:text/html,<input type="file" id="probe">`.
3. `browser_snapshot`, then `browser_click` the input. The ref goes in
   `target`, not `ref`.
4. `browser_file_upload` with `paths: ["/job-finder-probe-nonexistent/_probe.txt"]`.
   The error is expected and ends `Allowed roots: <a>, <b>`. The uploads root
   is the allowed root ending in `.playwright-mcp`; keep it exactly, with its
   own separator.
5. `browser_file_upload` the uploads root + `uploads` + `_probe.txt`, joined
   with that separator. Click the input again first if the chooser closed.
6. `browser_evaluate`: `() => document.getElementById('probe').files.length`.
   A call that returns without an error is not proof; this count is.

Leave `_probe.txt`; deleting it can stop an unattended run on a permission
prompt, and the next probe overwrites it.

## Outcomes

- **Accepted:** step 6 returns 1. Pass the uploads root to whatever uploads
  next.
- **Rejected:** step 4 names no root ending in `.playwright-mcp`, or step 5
  errors, or step 6 returns 0. Quote the errors verbatim. Every resume and
  cover letter then needs attaching by hand; the forms still get filled with
  everything that is not a file. On Cowork the cause is the folder's location.
  Tell the user, once:

  > To attach your resume and cover letter, I need your `job-finder` folder
  > to sit directly in your home folder: on a Mac, open Finder and choose
  > **Go > Home**; on Windows, it's `C:\Users\<your name>`. Move the folder
  > there, connect it again with the **+** next to the message box, and say
  > "set me up" so the weekly run uses the new spot.

- **Inconclusive:** the probe could not run (no Playwright tools, no file
  chooser, the `data:` URL blocked). Report it as inconclusive, never as a
  pass, and expect to attach files by hand.

**Never work around a rejection.** The allowed roots are a security boundary
on a browser-driving agent: no `browser_run_code_unsafe`, no self-written JS,
no copying files into another directory the server allows.
