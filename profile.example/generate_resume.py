"""
Canonical resume generator — copy to profile/ and edit ONLY the RESUME_DATA
dict below with your own history. Never modify styles, layout, or spacing
constants; job_apply.render() swaps the RESUME_DATA block per application and
relies on the two block markers staying exactly as they are.
"""

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)

# ---------- DESIGN TOKENS (LOCKED — DO NOT EDIT) ----------
NAVY = HexColor("#1B2A4A")
CHARCOAL = HexColor("#2D3436")
ACCENT = HexColor("#2C5F8A")
LIGHT = HexColor("#A3BAC3")

# ---------- RESUME DATA (EDIT ONLY THIS BLOCK) ----------
RESUME_DATA = {
    "name": "Alex Sample",
    "title": "Senior Product Manager  |  Your Positioning Line",
    "contact": '<font color="#2C5F8A">555-555-0100</font>  |  <a href="mailto:alex.sample@example.com" color="#2C5F8A">alex.sample@example.com</a>  |  <a href="https://www.linkedin.com/in/your-handle/" color="#2C5F8A">LinkedIn</a>',

    "experience": [
        {
            "company": "Current Company",
            "role": "Senior Product Manager",
            "dates": "JAN 2023 – PRESENT",
            "bullets": [
                "One outcome-focused bullet with a concrete metric you can defend in an interview.",
                "Another bullet: what you built or decided, and what changed because of it.",
            ],
        },
        {
            "company": "Previous Company",
            "role": "Product Manager",
            "dates": "JUN 2020 – JAN 2023",
            "bullets": [
                "Keep bullets outcome-first and traceable to your resume_master.md.",
            ],
        },
    ],

    "skills": [
        ("Category One", "comma-separated skills that appear in your master resume"),
        ("Category Two", "keep categories few and honest"),
        ("Category Three", "tools and methods you actually use"),
        ("Category Four", "no skills you could not discuss in an interview"),
    ],

    "education": {
        "degree": "Bachelor of Science — Your Major",
        "minor": "Minor: Your Minor",
        "school": "Your University",
        "dates": "SEP 2014 – JUN 2018",
    },

    "certifications": [
        "Certifications, patents, or awards worth a line each",
    ],
}

# ---------- STYLES (LOCKED) ----------
styles = {
    "name": ParagraphStyle("name", fontName="Helvetica-Bold", fontSize=18,
                           textColor=NAVY, alignment=TA_CENTER, leading=20, spaceAfter=1),
    "title": ParagraphStyle("title", fontName="Helvetica", fontSize=10,
                            textColor=ACCENT, alignment=TA_CENTER, leading=12,
                            spaceBefore=7, spaceAfter=1),
    "contact": ParagraphStyle("contact", fontName="Helvetica", fontSize=8.5,
                              textColor=CHARCOAL, alignment=TA_CENTER, leading=11, spaceAfter=4),
    "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=11,
                              textColor=NAVY, alignment=TA_LEFT, leading=13,
                              spaceBefore=7, spaceAfter=2),
    "role_left": ParagraphStyle("role_left", fontName="Helvetica-Bold", fontSize=9,
                                textColor=CHARCOAL, alignment=TA_LEFT, leading=11),
    "role_right": ParagraphStyle("role_right", fontName="Helvetica", fontSize=8.5,
                                 textColor=LIGHT, alignment=TA_RIGHT, leading=11),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=8.5,
                             textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                             leftIndent=8, firstLineIndent=-8, spaceAfter=2),
    "skill_cat": ParagraphStyle("skill_cat", fontName="Helvetica-Bold", fontSize=9,
                                textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                                spaceBefore=7, spaceAfter=2),
    "skill_body": ParagraphStyle("skill_body", fontName="Helvetica", fontSize=8.5,
                                 textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                                 leftIndent=8, firstLineIndent=-8, spaceAfter=2),
    "edu_body": ParagraphStyle("edu_body", fontName="Helvetica", fontSize=8.5,
                               textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                               leftIndent=8, firstLineIndent=-8, spaceAfter=2),
    "cert_body": ParagraphStyle("cert_body", fontName="Helvetica", fontSize=8.5,
                                textColor=CHARCOAL, alignment=TA_LEFT, leading=11,
                                leftIndent=8, firstLineIndent=-8, spaceAfter=2),
}


def make_company_row(company, role, dates, first=False):
    """Two-col table for role/dates with hAlign='LEFT' to prevent phantom indent."""
    left = Paragraph(f"<b>{company}</b> &nbsp;|&nbsp; {role}", styles["role_left"])
    right = Paragraph(dates, styles["role_right"])
    t = Table([[left, right]], colWidths=[4.9 * inch, 2.3 * inch])
    t.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    t.hAlign = "LEFT"
    t.spaceBefore = 7
    return t


def build_story():
    s = []
    # Header
    s.append(Paragraph(RESUME_DATA["name"], styles["name"]))
    s.append(Paragraph(RESUME_DATA["title"], styles["title"]))
    s.append(Paragraph(RESUME_DATA["contact"], styles["contact"]))

    # Experience
    s.append(Paragraph("EXPERIENCE", styles["section"]))
    for i, job in enumerate(RESUME_DATA["experience"]):
        s.append(make_company_row(job["company"], job["role"], job["dates"], first=(i == 0)))
        for b in job["bullets"]:
            s.append(Paragraph(f"&bull;&nbsp;&nbsp;{b}", styles["bullet"]))

    # Skills
    s.append(Paragraph("SKILLS", styles["section"]))
    for cat, body in RESUME_DATA["skills"]:
        s.append(Paragraph(cat, styles["skill_cat"]))
        s.append(Paragraph(f"&bull;&nbsp;&nbsp;{body}", styles["skill_body"]))

    # Education
    s.append(Paragraph("EDUCATION", styles["section"]))
    edu = RESUME_DATA["education"]
    s.append(make_company_row(edu["school"], edu["degree"], edu["dates"], first=True))
    s.append(Paragraph(f"&bull;&nbsp;&nbsp;{edu['minor']}", styles["edu_body"]))

    # Certifications
    s.append(Paragraph("CERTIFICATIONS &amp; PATENTS", styles["section"]))
    s.append(Spacer(1, 5))
    for c in RESUME_DATA["certifications"]:
        s.append(Paragraph(f"&bull;&nbsp;&nbsp;{c}", styles["cert_body"]))

    return s


def build_pdf(path):
    doc = SimpleDocTemplate(
        path,
        pagesize=LETTER,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=f"{RESUME_DATA['name']} — Resume",
        author=RESUME_DATA["name"],
        subject="Resume",
        creator=RESUME_DATA["name"],
    )
    doc.build(build_story())


if __name__ == "__main__":
    out = "resume.pdf"
    build_pdf(out)
    print(f"Built: {out}")
