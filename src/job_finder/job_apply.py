"""Apply-prep: turn a posting row into a per-job folder with tailored resume,
cover letter, standard answers, and apply notes.

Two entry points:
- tailor(posting_row): runs an LLM call to propose RESUME_DATA + cover letter
  + why-this-matches. Used when called from a plain script (no Claude in loop).
- render(posting_row, resume_data, cover_letter, why_this_matches): pure,
  deterministic. Writes the per-job folder. Called by /job-apply after the
  user approves the tailoring proposals shown by Claude.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import webbrowser
from datetime import date
from pathlib import Path
from typing import Any, Mapping

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - optional for render()
    Anthropic = None  # type: ignore[assignment]

from . import settings

REPO_ROOT = Path(__file__).resolve().parents[2]


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

class Config:
    """Resolved paths for apply-prep, read from profile/profile.toml [paths]."""

    def __init__(self, *, inputs_dir: Path, applications_dir: Path,
                 session_context_path: Path, resume_skill: Path) -> None:
        self.inputs_dir = inputs_dir
        self.applications_dir = applications_dir
        self.session_context_path = session_context_path
        self.resume_skill = resume_skill

    @property
    def resume_master_md(self) -> Path:
        return self.inputs_dir / "resume_master.md"

    @property
    def personal_statement_md(self) -> Path:
        return self.inputs_dir / "personal_statement.md"

    @property
    def standard_answers_md(self) -> Path:
        return self.inputs_dir / "standard_answers.md"

    @property
    def qa_checklist_md(self) -> Path:
        return self.inputs_dir / "qa_checklist.md"


def load_config(profile: Mapping[str, Any] | None = None) -> Config:
    """Resolve apply-prep paths from the profile's [paths] table.

    Every path defaults into the gitignored profile/ directory, so a new user
    who drops their driving docs there needs no [paths] section at all.
    """
    profile = profile if profile is not None else settings.load_profile()
    paths = profile.get("paths", {})
    base = settings.profile_dir()

    repo_root = Path(__file__).resolve().parents[2]

    def _resolve(key: str, default: Path) -> Path:
        """Absolute paths as given; relative ones against the repo, never the cwd.

        A relative path lets the profile point at junctions inside the workspace
        instead of reaching outside it, but resolving those against the working
        directory would break every caller that runs from somewhere else -- the
        scheduled task among them.
        """
        raw = paths.get(key)
        if not raw:
            return default
        path = Path(raw).expanduser()
        return path if path.is_absolute() else (repo_root / path)

    return Config(
        inputs_dir=_resolve("inputs_dir", base),
        applications_dir=_resolve("applications_dir", base / "applications"),
        session_context_path=_resolve("session_context_path", base / "session_context.md"),
        resume_skill=_resolve("resume_skill_path", base / "generate_resume.py"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Path helpers
# ─────────────────────────────────────────────────────────────────────────────

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# A bare "&" is invalid in ReportLab's markup, but callers reuse RESUME_DATA
# strings that are already escaped ("AI &amp; Platforms"). Escaping blindly
# double-escapes those into a literal "&amp;" on the page, so skip ampersands
# that already open a character entity.
_BARE_AMP_RE = re.compile(r"&(?!(?:[A-Za-z][A-Za-z0-9]*|#\d+|#[xX][0-9A-Fa-f]+);)")


def esc_amp(text: str) -> str:
    """Escape bare ampersands for ReportLab, leaving existing entities alone."""
    return _BARE_AMP_RE.sub("&amp;", text)


def slugify(value: str, *, max_len: int = 40) -> str:
    s = _SLUG_RE.sub("-", value.lower()).strip("-")
    return s[:max_len].rstrip("-") or "untitled"


def outdir_for(posting_row: Mapping[str, Any], applications_dir: Path) -> Path:
    today = date.today().isoformat()
    company = slugify(str(posting_row["company_name"]))
    role = slugify(str(posting_row["title"]))
    return applications_dir / f"{today}_{company}_{role}"


# ─────────────────────────────────────────────────────────────────────────────
# Resume rendering
# ─────────────────────────────────────────────────────────────────────────────

RESUME_DATA_BLOCK = re.compile(
    r"# ---------- RESUME DATA \(EDIT ONLY THIS BLOCK\) ----------\n"
    r".*?\n"
    r"# ---------- STYLES \(LOCKED\) ----------",
    re.DOTALL,
)

RESUME_MAIN_BLOCK = re.compile(
    r'if __name__ == "__main__":\n.*?(?=\n\S|\Z)', re.DOTALL,
)


def _render_resume(skill_path: Path, resume_data: dict, output_pdf: Path) -> None:
    """Copy generate_resume.py, swap RESUME_DATA + output path, run it."""
    if not skill_path.exists():
        raise FileNotFoundError(f"resume_generator script not found: {skill_path}")
    src = skill_path.read_text(encoding="utf-8")

    new_block = (
        "# ---------- RESUME DATA (EDIT ONLY THIS BLOCK) ----------\n"
        f"RESUME_DATA = {json.dumps(resume_data, indent=4, ensure_ascii=False)}\n\n"
        "# ---------- STYLES (LOCKED) ----------"
    )
    patched, n = RESUME_DATA_BLOCK.subn(lambda _m: new_block, src, count=1)
    if n != 1:
        raise RuntimeError("Could not locate RESUME_DATA block in generate_resume.py — has the skill template changed?")

    main_replacement = (
        f'if __name__ == "__main__":\n'
        f"    build_pdf({json.dumps(str(output_pdf))})\n"
        f'    print("Built:", {json.dumps(str(output_pdf))})\n'
    )
    patched, n = RESUME_MAIN_BLOCK.subn(lambda _m: main_replacement, patched, count=1)
    if n != 1:
        patched = patched.rstrip() + "\n\n" + main_replacement

    script_copy = output_pdf.with_suffix(".py")
    script_copy.write_text(patched, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(script_copy)],
        cwd=script_copy.parent,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Resume PDF build failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}\n"
            f"Script preserved at: {script_copy}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Cover letter rendering
# ─────────────────────────────────────────────────────────────────────────────

def _render_cover_letter(identity: Mapping[str, str], cover_letter: dict,
                         output_pdf: Path) -> None:
    """Build a single-page cover letter PDF. Layout is self-contained here.

    identity comes from profile.toml [identity]: name, email, phone, and
    optionally linkedin and title_subtitle.

    cover_letter dict shape:
      {
        "date": "May 17, 2026",
        "recipient": "Hiring Team\\nCompany Name\\nCity, State",
        "salutation": "To the Hiring Team,",
        "paragraphs": ["First para...", "Second para...", ...],
        "closing": "Looking forward to talking,",
        "title_subtitle": "Senior Product Manager | Positioning Line",
      }
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib import colors

    NAVY = colors.HexColor("#1B2A4A")
    CHARCOAL = colors.HexColor("#2D3436")
    ACCENT = colors.HexColor("#2C5F8A")
    LIGHT = colors.HexColor("#A3BAC3")

    s = {
        "name_header": ParagraphStyle("nh", fontName="Helvetica-Bold", fontSize=18,
                                      textColor=NAVY, spaceAfter=1, alignment=TA_CENTER, leading=20),
        "title_header": ParagraphStyle("th", fontName="Helvetica", fontSize=10,
                                       textColor=ACCENT, spaceAfter=1, alignment=TA_CENTER, leading=12),
        "contact_header": ParagraphStyle("ch", fontName="Helvetica", fontSize=8.5,
                                         textColor=CHARCOAL, spaceAfter=0, alignment=TA_CENTER, leading=11),
        "date": ParagraphStyle("d", fontName="Helvetica", fontSize=9,
                               textColor=CHARCOAL, spaceAfter=4, alignment=TA_LEFT, leading=12),
        "recipient": ParagraphStyle("r", fontName="Helvetica", fontSize=9,
                                    textColor=CHARCOAL, spaceAfter=1, alignment=TA_LEFT, leading=13),
        "recipient_last": ParagraphStyle("rl", fontName="Helvetica", fontSize=9,
                                         textColor=CHARCOAL, spaceAfter=10, alignment=TA_LEFT, leading=13),
        "salutation": ParagraphStyle("sa", fontName="Helvetica", fontSize=9.5,
                                     textColor=CHARCOAL, spaceAfter=6, alignment=TA_LEFT, leading=13),
        "body": ParagraphStyle("b", fontName="Helvetica", fontSize=9.5,
                               textColor=CHARCOAL, spaceAfter=7, alignment=TA_JUSTIFY, leading=14),
        "closing": ParagraphStyle("cl", fontName="Helvetica", fontSize=9.5,
                                  textColor=CHARCOAL, spaceAfter=2, alignment=TA_LEFT, leading=14),
        "sig_name": ParagraphStyle("sn", fontName="Helvetica-Bold", fontSize=10,
                                   textColor=NAVY, spaceAfter=1, alignment=TA_LEFT, leading=13),
        "sig_contact": ParagraphStyle("sc", fontName="Helvetica", fontSize=8.5,
                                      textColor=CHARCOAL, alignment=TA_LEFT, leading=11),
    }

    name = identity["name"]
    email = identity["email"]
    phone = identity["phone"]
    linkedin = identity.get("linkedin", "")

    doc = SimpleDocTemplate(
        str(output_pdf), pagesize=letter,
        leftMargin=0.65 * inch, rightMargin=0.65 * inch,
        topMargin=0.55 * inch, bottomMargin=0.55 * inch,
        title=f"{name} — Cover Letter",
        author=name,
        subject="Cover Letter",
        creator=name,
    )

    story = []
    title_subtitle = cover_letter.get("title_subtitle") or identity.get("title_subtitle", "")
    story.append(Paragraph(name, s["name_header"]))
    if title_subtitle:
        story.append(Paragraph(esc_amp(title_subtitle), s["title_header"]))
    contact_bits = [
        phone,
        f'<a href="mailto:{email}" color="#2C5F8A">{email}</a>',
    ]
    if linkedin:
        contact_bits.append(f'<a href="{linkedin}" color="#2C5F8A">LinkedIn</a>')
    story.append(Paragraph("  &middot;  ".join(contact_bits), s["contact_header"]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT, spaceBefore=3, spaceAfter=8))

    story.append(Paragraph(esc_amp(cover_letter["date"]), s["date"]))
    recipient_lines = cover_letter["recipient"].split("\n")
    for i, line in enumerate(recipient_lines):
        style = s["recipient_last"] if i == len(recipient_lines) - 1 else s["recipient"]
        story.append(Paragraph(esc_amp(line), style))

    story.append(Paragraph(esc_amp(cover_letter["salutation"]), s["salutation"]))
    for para in cover_letter["paragraphs"]:
        story.append(Paragraph(esc_amp(para), s["body"]))

    story.append(Spacer(1, 4))
    story.append(Paragraph(esc_amp(cover_letter.get("closing", "Looking forward,")), s["closing"]))
    story.append(Paragraph(name, s["sig_name"]))
    story.append(Paragraph(
        f'<a href="mailto:{email}" color="#2C5F8A">{email}</a>  ·  {phone}',
        s["sig_contact"]
    ))

    doc.build(story)


# ─────────────────────────────────────────────────────────────────────────────
# Per-job folder assembly
# ─────────────────────────────────────────────────────────────────────────────

APPLY_MD_TEMPLATE = """# Apply notes — {company} / {title}

- **External ID:** `{external_id}` (use `job-finder mark-applied {external_id}` after submit)
- **Score / Queue:** {score} / {queue}
- **Location:** {location}
- **URL:** {url}

## Why this matches
{why_bullets}

## QA checklist
{qa_checklist}
"""

# Fallback when the profile has no qa_checklist.md. Users add their own
# fact-specific checks (metric baselines, framings to avoid) in that file.
DEFAULT_QA_CHECKLIST = """- [ ] Single page?
- [ ] All bullet dots at same x?
- [ ] No "orphan" wrapped word you can eliminate by tightening?
- [ ] Hyperlinks render in accent blue?
- [ ] Every metric traceable to your master resume?
- [ ] PDF metadata set (title, author, subject, creator)?"""


def _qa_checklist(config: Config) -> str:
    # profile/ first, then inputs_dir — they're the same directory unless the
    # user pointed [paths].inputs_dir somewhere else.
    for candidate in (settings.profile_dir() / "qa_checklist.md", config.qa_checklist_md):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8").strip()
    return DEFAULT_QA_CHECKLIST


def render(
    *,
    posting_row: Mapping[str, Any],
    resume_data: dict,
    cover_letter: dict,
    why_this_matches: list[str],
    config: Config | None = None,
    profile: Mapping[str, Any] | None = None,
    open_browser: bool = True,
) -> Path:
    """Write the per-job folder. Returns the folder path.

    Idempotent: re-running on the same role overwrites in place.
    """
    profile = profile if profile is not None else settings.require_profile()
    identity = profile["identity"]
    config = config or load_config(profile)
    outdir = outdir_for(posting_row, config.applications_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    name_token = re.sub(r"[^A-Za-z0-9]+", "_", identity["name"]).strip("_")
    company_slug = slugify(str(posting_row["company_name"]))
    resume_pdf = outdir / f"{name_token}_Resume_{company_slug}.pdf"
    cover_pdf = outdir / f"{name_token}_CoverLetter_{company_slug}.pdf"

    try:
        _render_resume(config.resume_skill, resume_data, resume_pdf)
    except Exception as exc:
        raw = outdir / "_resume_call_raw.json"
        raw.write_text(json.dumps(resume_data, indent=2, ensure_ascii=False), encoding="utf-8")
        raise RuntimeError(f"Resume render failed; RESUME_DATA dumped to {raw}") from exc

    _render_cover_letter(identity, cover_letter, cover_pdf)

    if config.standard_answers_md.exists():
        shutil.copy2(config.standard_answers_md, outdir / "standard_answers.md")
    else:
        (outdir / "standard_answers.md").write_text(
            f"# standard_answers.md not found at {config.standard_answers_md}\n",
            encoding="utf-8",
        )

    why_bullets = "\n".join(f"- {b}" for b in why_this_matches) or "- (none provided)"
    (outdir / "apply.md").write_text(
        APPLY_MD_TEMPLATE.format(
            company=posting_row["company_name"],
            title=posting_row["title"],
            external_id=posting_row["external_id"],
            score=posting_row.get("total_score", "?"),
            queue=posting_row.get("queue", "?"),
            location=posting_row.get("location", "?"),
            url=posting_row["url"],
            why_bullets=why_bullets,
            qa_checklist=_qa_checklist(config),
        ),
        encoding="utf-8",
    )

    if open_browser:
        try:
            webbrowser.open(str(posting_row["url"]))
        except Exception as exc:
            print(f"[job_apply] webbrowser.open failed: {exc}. URL: {posting_row['url']}", file=sys.stderr)

    return outdir


# ─────────────────────────────────────────────────────────────────────────────
# tailor() — LLM call. Optional convenience for non-Claude-Code usage.
# /job-apply slash command does this work itself so it can show diffs.
# ─────────────────────────────────────────────────────────────────────────────

TAILOR_SYSTEM = """You are {name}'s resume + cover letter tailoring assistant.

You will be given a job description, {name}'s master resume (markdown), their personal statement, and their anti-overstatement rules (session context).

Your job: produce a JSON object with three keys:

1. resume_data — a Python-style dict matching the RESUME_DATA schema in generate_resume.py:
   keys: name, title, contact, experience (list of {company, role, dates, bullets}),
         skills (list of [category, body] pairs), education, certifications (list)
   Edit ONLY the order and wording of bullets, the title subtitle, and the skill
   category order. Keep all factual content traceable to the master.

2. cover_letter — dict with keys: date, recipient, salutation, paragraphs (list of strings),
   closing, title_subtitle. Body should be 3-5 paragraphs, traceable to source material.

3. why_this_matches — list of 3-5 short bullets justifying the fit.

Return ONLY valid JSON. No commentary."""


def tailor(posting_row: Mapping[str, Any], *, config: Config | None = None,
           profile: Mapping[str, Any] | None = None,
           model: str = "claude-opus-4-7") -> dict:
    """Run a single Claude call to propose resume_data + cover_letter + why_this_matches.

    Used standalone. /job-apply slash command does this work conversationally
    instead, so it can show diffs and accept feedback before render().
    """
    if Anthropic is None:
        raise RuntimeError("anthropic package not installed")
    profile = profile if profile is not None else settings.require_profile()
    config = config or load_config(profile)

    resume_master = config.resume_master_md.read_text(encoding="utf-8")
    personal_statement = config.personal_statement_md.read_text(encoding="utf-8")
    session_ctx = (
        config.session_context_path.read_text(encoding="utf-8")
        if config.session_context_path.exists() else "(session context file not found)"
    )

    user_prompt = (
        f"## Job description\n\n**Company:** {posting_row['company_name']}\n"
        f"**Role:** {posting_row['title']}\n"
        f"**URL:** {posting_row['url']}\n\n"
        f"```\n{posting_row.get('jd_text') or '(no jd_text in DB — fall back to title + company)'}\n```\n\n"
        f"## Master resume\n\n{resume_master}\n\n"
        f"## Personal statement\n\n{personal_statement}\n\n"
        f"## Anti-overstatement rules (session context)\n\n{session_ctx}\n"
    )

    client = Anthropic()
    # .replace, not .format — the prompt body contains literal JSON braces.
    system_text = TAILOR_SYSTEM.replace("{name}", profile["identity"]["name"])
    msg = client.messages.create(
        model=model,
        max_tokens=8000,
        system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return json.loads(text)
