"""Profile doctor: verify the gitignored profile/ is filled in, not a copy of
the example. Run it after setup and before the first real application:

    python -m job_finder.profile_check

Exit code 0 = ready; 1 = issues listed below the report.
"""
from __future__ import annotations

import re
import sys

from . import settings
from .job_apply import load_config

# Values that mean "still the example template".
PLACEHOLDERS = {
    "name": {"alex sample", ""},
    "email_domains": {"example.com"},
    "phone": {"555-555-0100", ""},
    "handle_fragments": ("your-handle",),
}


def check() -> list[str]:
    issues: list[str] = []

    if not settings.PIPELINE_CONFIG_PATH.exists():
        issues.append("config/pipeline.toml not found — running on the example "
                      "defaults. Copy config/pipeline.example.toml and edit it "
                      "for your own search (SETUP.md §4)")

    from . import state
    if not state.list_companies():
        issues.append("no tracked companies in data/state.db — import a starter list: "
                      "`job-finder companies import config/companies.example.json` "
                      "then build your own (SETUP.md §5)")

    real = settings.PROFILE_DIR / "profile.toml"
    if not real.exists():
        return ["profile/profile.toml does not exist — run `cp -r profile.example profile` "
                "and fill it in (SETUP.md §3)"]

    profile = settings.load_profile(real)
    ident = profile.get("identity", {})

    if ident.get("name", "").strip().lower() in PLACEHOLDERS["name"]:
        issues.append("[identity].name is still the example placeholder")
    email = ident.get("email", "").strip().lower()
    if not email or email.rsplit("@", 1)[-1] in PLACEHOLDERS["email_domains"]:
        issues.append("[identity].email is missing or still @example.com")
    if ident.get("phone", "").strip() in PLACEHOLDERS["phone"]:
        issues.append("[identity].phone is missing or still the example placeholder")
    for key in ("linkedin", "github"):
        v = ident.get(key, "")
        if any(f in v for f in PLACEHOLDERS["handle_fragments"]):
            issues.append(f"[identity].{key} still points at the example handle")
    if not ident.get("city"):
        issues.append("[identity].city is empty — autofill needs it for location fields")

    config = load_config(profile)
    for doc, path in (("resume_master.md", config.resume_master_md),
                      ("personal_statement.md", config.personal_statement_md),
                      ("standard_answers.md", config.standard_answers_md)):
        if not path.exists():
            issues.append(f"{doc} not found at {path} — the tailoring and autofill "
                          "workflows read it (SETUP.md §3)")
        else:
            # ": <FILL IN" = a field whose VALUE is still the placeholder;
            # prose that merely mentions <FILL IN> (the file's own
            # instructions) is fine.
            if re.search(r":\s*`?<FILL IN", path.read_text(encoding="utf-8", errors="replace")):
                issues.append(f"{path.name} still has fields set to <FILL IN>")
    if not config.writing_style.exists():
        issues.append(f"writing-style.md not found at {config.writing_style} — the "
                      "fact-checker reads it as the voice authority and the letter "
                      "linter enforces a subset of it (SETUP.md §3)")
    if not config.claims_ground_truth.exists():
        issues.append(f"claims_ground_truth.md not found at {config.claims_ground_truth} — "
                      "the tailoring and fact-checking workflows read it (SETUP.md §3)")
    if not config.resume_skill.exists():
        issues.append(f"resume generator not found at {config.resume_skill} — copy "
                      "profile.example/generate_resume.py and edit its RESUME_DATA block")
    if not (settings.PROFILE_DIR / "fit_profile.md").exists():
        issues.append("profile/fit_profile.md missing — the digest triager ranks roles with it")

    return issues


def main() -> int:
    issues = check()
    if not issues:
        print("profile check: PASS — pipeline config, identity, driving docs, "
              "and generator all present.")
        print("Reminder: the tracked-company list lives in data/state.db — "
              "`job-finder companies list` to inspect it (SETUP.md §5).")
        return 0
    print(f"profile check: {len(issues)} issue(s)\n")
    for issue in issues:
        print(f"  - {issue}")
    print("\nFix these before running the apply workflow. See SETUP.md §3.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
