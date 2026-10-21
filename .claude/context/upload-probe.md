# Upload probe

Proves the Playwright server can attach a file from this folder, and finds the
**uploads root**: the absolute path on the user's computer that every
`browser_file_upload` path starts from. Run it before anything that uploads.

The server accepts uploads only from its output folder and its working folder.
The marketplace plugin sets the output folder to `job-finder/.playwright-mcp`
inside the user's home folder. A folder anywhere else gets its own browser
plugin, under Rejected below. In Claude Code the repo is the working folder
and uploads work wherever it is.

Use one Playwright tool set, any tool whose name contains `playwright`. If two
sets are present, probe each until one is accepted, and use that one for the
whole run.

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
  errors, or step 6 returns 0. Quote the errors verbatim. Until it is fixed,
  every resume and cover letter needs attaching by hand; forms still get
  filled with everything that is not a file.

  On Cowork, with the user there to answer, give the folder its own browser
  plugin:

  1. Take the folder's path on the user's computer exactly as the session
     states it (a note such as "The user picked these folders on their
     computer"). Never build or guess it from a username, the mount path or a
     usual folder layout. If the session does not state it, stop here.
  2. Build the plugin into the folder:

     ```sh
     sh scripts/py -m job_finder.browser_plugin --host-dir '<that path>'
     ```

  3. Tell the user, then stop and wait:

     > One more step so I can attach your resume and cover letter. In the
     > Claude app, open **Customize > Plugins**, choose the option to upload a
     > plugin, and pick **job-finder-browser.zip** from your job-finder
     > folder. Then start a new chat in this folder and say "set me up".

  A run with nobody to answer, or with no stated path, ends its report with:
  say "set me up" in this folder to fix attaching files.

- **Inconclusive:** the probe could not run (no Playwright tools, no file
  chooser, the `data:` URL blocked). Report it as inconclusive, never as a
  pass, and expect to attach files by hand.

**Never work around a rejection.** The allowed roots are a security boundary
on a browser-driving agent: no `browser_run_code_unsafe`, no self-written JS,
no copying files into another directory the server allows.
