# job-finder

job-finder runs inside the Claude desktop app. It watches the job boards of
companies you choose, ranks new postings against what you're looking for, and
writes a tailored resume and cover letter for each role you pick. Then it fills
in the application and leaves it open for you to check and submit yourself.
When an application turns into an interview, it writes a prep sheet and runs a
mock interview with you. Everything it knows about you stays in one folder on
your computer.

## Get started

1. **Claude Pro or higher.** job-finder runs in Cowork, which is not on the
   free plan: https://claude.com/pricing
2. **The Claude desktop app**, signed in with the same account:
   https://claude.com/download
3. **Download the plugin:**
   https://github.com/jsimo20/job-finder/releases/latest/download/job-finder-cowork-plugin.zip
4. **Install it.** In the Claude app, start a new chat, click the **+** next to
   the message box and add the plugin from the zip.
5. **Make an empty folder called `job-finder` directly in your home folder**
   (on a Mac, Finder > Go > Home; on Windows, `C:\Users\<your name>`), not in
   Documents. Click **+** again and connect it.
6. **Say "set me up".** It's a conversation of about 20 to 30 minutes: where
   you live, the jobs you want, your pay floor, your resume and a few
   paragraphs about yourself in your own words. It may stop once to have you
   change a Claude setting or install Node.js so it can fill forms, and it
   tells you exactly what to click.

At the end it schedules a weekly run on a morning you usually have the app
open. Then let that run use your folder without asking: click **Scheduled** in
the left sidebar, open **Job finder weekly run**, and click the warning sign
next to the folder.

## What you can ask for

Open a chat with your job-finder folder connected and ask in plain words:

| Say | What happens |
|---|---|
| "run my weekly job search" | Checks every company's job board, reads the new postings, writes a ranked digest, then prepares applications for the top roles |
| "help me apply to this job" with a link or the description | Tailors a resume and cover letter for that role, checks every claim against your resume, and fills the form |
| "add companies: Acme, Globex" / "find me more companies" | Adds companies to the list it watches |
| "prep me for my interview with Acme" | Re-reads the posting and what you sent, writes a prep sheet, and runs a mock interview with feedback after every answer |
| "change my settings" | Updates where you'd work, the jobs you want, your pay floor or your profile |

## What it never does

- Submit an application. Every form is left open for you.
- Answer salary questions.
- Claim anything that isn't in your resume or something you told it.
- Contact anyone on your behalf.

## What it can't do yet

- **Read big employers' own careers sites.** It watches the common job boards
  (Greenhouse, Lever, Ashby). Most large companies post only on their own
  sites. Add one you care about and its careers page shows up in your digest
  under **Manual check**; paste any role you find there into a chat.
- **Fill forms that need an account first** (Workday and similar). It still
  prepares the resume and cover letter; you fill in the form.
- **Run while the app is closed.** A missed week catches up the next time
  you open it.

## Your data

Your profile, search settings, application history and the companies you
track all live in your folder. None of it is part of this project, and this
repository contains no one's personal data. Updates replace the engine's own
files and never touch yours.

## Updates

Each scheduled run updates the engine automatically. You only download the
plugin again when a release note says to.
