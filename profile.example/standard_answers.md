# Standard application answers

Copied into every per-application folder by `job_apply.render()`. The
deterministic Greenhouse filler and the autofill agent both read it. Keep the
`**Key:** value` format for the contact block — the filler parses it with that
exact shape (any value here overrides `profile.toml [identity]`).

## Contact

- **Full name:** Alex Sample
- **Preferred name:** Alex
- **Email:** alex.sample@example.com
- **Phone:** 555-555-0100
- **LinkedIn:** https://www.linkedin.com/in/your-handle/
- **GitHub:** https://github.com/your-handle
- **Location:** Boston, MA
- **Address:** 123 Example St, Boston MA 02101

## Work authorization

- Authorized to work in the US: Yes
- Require visa sponsorship now or in the future: No

## Common screening questions

Add your stock answers here — the autofill agent quotes them verbatim when a
form asks. Examples of questions worth pre-answering:

- How did you hear about this role? Company careers page.
- Willing to work hybrid/onsite: (your answer)
- Earliest start date: (your answer)

## Never answered automatically

Salary and compensation fields are always left blank, whatever a form says.
Legal questions (non-competes, prior agreements, export control) are always
left for you.
