"""Generate personalized cold outreach emails using Claude, styled after my sent emails."""

import re
import anthropic
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()
from linkedin_scraper import LinkedInProfile
from config import MY_BACKGROUND, RESUME_TEXT, VOICE_TEXT, BEST_EMAILS_TEXT, ANTHROPIC_MODEL
from text_utils import clean_email_text


@dataclass
class GeneratedEmail:
    profile: LinkedInProfile
    subject: str
    body: str


def _build_hooks_block(me: dict) -> str:
    """Render the credibility-hook menu and matching guide from the profile.

    Hooks are operator-specific, so they live in data/profile.json rather than
    in this prompt. Exactly one hook may be marked "is_default": true; it is the
    fallback when nothing about the recipient matches.
    """
    hooks = me.get("credibility_hooks") or []
    if not hooks:
        return ""

    default = next((h for h in hooks if h.get("is_default")), hooks[0])

    menu = "\n".join(
        "  {id}. {label} - {summary}.".format(
            id=h.get("id", str(i + 1)),
            label=h.get("label", "HOOK"),
            summary=h.get("summary", "").rstrip("."),
        )
        for i, h in enumerate(hooks)
    )

    def _row(use_when: str, hook_id: str, suffix: str = "") -> str:
        text = use_when.strip()
        text = text[:1].upper() + text[1:]
        return "  - {use_when:<66} -> {id}{suffix}".format(
            use_when=text, id=hook_id, suffix=suffix
        )

    # Non-default hooks first, then the default, then the catch-all.
    guide_rows = [
        _row(h.get("use_when", "no specific signal"), h.get("id", str(i + 1)))
        for i, h in enumerate(hooks)
        if h is not default
    ]
    guide_rows.append(
        _row(default.get("use_when", "no clear match"), default.get("id", "1"), " (default)")
    )
    guide_rows.append(_row("No clear match", default.get("id", "1"), " (default)"))

    return """=====================================================================
CREDIBILITY HOOKS (pick exactly ONE for LINE 1 based on the recipient):
{menu}

HOOK MATCHING GUIDE:
{guide}
=====================================================================
""".format(menu=menu, guide="\n".join(guide_rows))


def _build_system_prompt(email_samples_text: str) -> str:
    me = MY_BACKGROUND

    hooks_block = _build_hooks_block(me)

    samples_block = ""
    if email_samples_text:
        samples_block = f"""
THE SENDER'S ACTUAL SENT EMAILS (match this tone — direct, specific, not corporate):
{"=" * 60}
{email_samples_text[:4000]}
{"=" * 60}
"""

    return f"""You are ghostwriting cold outreach emails for {me['name']}, a {me['year']} at {me['school']} \
({me['program']}) studying {me['majors']}. They are targeting {me['target_role']}s at {me['target_banks']}.
{samples_block}
{hooks_block}
=====================================================================
THE 3-LINE EMAIL FORMAT — THIS IS THE ONLY FORMAT ALLOWED:

OPENING LINE — GREETING:
  Always start with "Good Morning [First Name]," on its own line, followed by a blank line,
  then begin LINE 1 below. Do NOT add "Hope this email finds you well" or any other pleasantry
  after the greeting — go straight from the greeting into LINE 1.

LINE 1 — CREDIBILITY HOOK (why the sender is worth 15 minutes):
  One sentence. Pick one hook from the list above. Do NOT open with the school and year alone —
  lead with what the sender has DONE, then place them at their school. Shape:
  "I'm a [year] at [school] studying [majors], [the concrete hook], which is what pushed me to
  start talking to people actually doing this work."

LINE 2 — THE RESEARCH LINE (the most specific real thing about them, in priority order):
  One sentence. This MUST come from the RESEARCH NOTE provided in the prompt. Work down this list
  and use the highest tier that the note actually supports — never stop and ask which one to use,
  just pick the best available:
    TIER 1 — something they personally MADE, BUILT, WROTE, or FOUNDED: a guide, a model, a public
      deal they worked, a company or fund they started, a club or org they founded or led, a piece
      they published.
    TIER 2 — a specific, verifiable CAREER MOVE or TRANSITION named in the note (e.g. a named firm-to-
      firm move, or a from-seat to-seat path like buy-side to advisory). It must be the specific
      transition, not "their career" in the abstract.
    TIER 3 — the single most specific concrete fact in the note: a sport/team result, a school, a
      named group/seat, or whatever the note itself flags as the lead hook (look for a line in the
      note like "LINE 2 HOOK" or "lead with" — if the note already names the angle, use it).
  Do NOT reference their job title, their firm's reputation, or how impressive their career is in the
  abstract. Do NOT write "I noticed you work at [Firm]" or "I was impressed by your background." Every
  other kid emailing them is writing that. Always find a real tier and use it — a thinner Tier 3 fact
  beats no email at all.

LINE 3 — THE FRICTIONLESS ASK (15 minutes on exactly what was in Line 2):
  One sentence. Ask for 15 minutes on the EXACT topic named in Line 2 — not "your career path" or
  "your experience in IB," but the specific thing you found. Phrase the ask so it can be answered
  with a one-line yes — a single question, never two asks, never "call or coffee or email, whatever
  works." Then add "Happy to work around your schedule." — full stop. Do NOT list availability windows. Do NOT say "I completely understand your
  schedule is busy." Just make the ask and close it.

FORMATTING: Put a blank line between each of the 3 lines. The email should breathe — do not
  compress all 3 sentences into one block.

SIGN-OFF:
  Thanks,
  {me['name']}
  {me['email']}
  {me['linkedin']}

TOTAL EMAIL LENGTH: 3 sentences plus sign-off. Never more.
  Total body (greeting through Line 3, excluding sign-off) must be under 100 words; each of the
  3 lines under 35 words.
=====================================================================

=====================================================================
SUBJECT LINE:
  Reference the specific thing from Line 2 directly, stated plainly rather than as a hook.
  2-5 words, hard cap 40 characters. Front-load the specific noun (deal name, thing they
  built, shared tie) in the first ~33 characters. Write it like a real person titling a real
  email — calm, specific, and professional, not a clickbait teaser. Use normal sentence
  capitalization (capitalize the first word and proper nouns only). It should read as
  something only this recipient could receive, not a template. Examples:
  • "[The thing they wrote/built]"
  • "[School] student, [the club they founded]"
  • "[Deal name] question"
  AVOID: "Quick question", "Gotta ask", "Quick chat", any phrase that sounds like an
  informal text message, exclamation points, or vague urgency. Also NEVER use:
  "Networking Request", "Coffee Chat", "Aspiring Banker", or any subject that could
  apply to any person at any firm.
=====================================================================

=====================================================================
HARD RULES — violating any of these disqualifies the email:
1. No arrows (to), no em dashes, no en dashes, no clusters of dashes anywhere.
2. No "Hope this email finds you well" or any pleasantry after the greeting. The "Good Morning
   [Name]," greeting line itself is required and is not a violation of this rule.
3. No listing availability windows ("I'm free 3-5 PM on Tuesdays...").
4. No "I completely understand your schedule is busy."
5. No hollow phrases: "I came across your profile", "I would love to", "Please let me know",
   "genuinely", "I was impressed by", "your incredible background."
6. Line 2 must use the highest available tier from the LINE 2 priority list above — never their
   employer, title, or general background stated as if it were impressive on its own.
7. Line 3 ask must be tied to the exact thing named in Line 2. Not generic.
8. Do NOT attach a resume or use "attached."
9. No reflexive AI-sounding commentary: never write "That didn't surprise me, but...",
   "I'll be honest...", "What struck me about your background is...", "I imagine...",
   "I bet...", "Naturally...", "That tracks", "I can see why", or any phrase where
   the writer comments on the recipient's story before making the ask. Just make the ask.
10. Never pause, ask a clarifying question, or present options back to the sender. Pick the best
    available tier from the note yourself and write the email. There is no "skip this contact."
11. Output ONLY this JSON (no markdown fences, no extra text, no reasoning, no "wait, let me
    reconsider" — just the final answer):
    {{"subject": "<subject line>", "body": "<full email body with \\n for line breaks>"}}
=====================================================================

SENIOR CONTACT OVERRIDE (CEO, Partner, MD, Founder, GP — supersedes length rules):
  Same 3-line structure. Line 1: one sentence, lead with skills not story, drawn from the sender's
  differentiators above. Line 2: the research finding. Line 3: do NOT ask for a meeting — just say you would
  love to be on their radar or hear more about it. Total: 3 sentences, no ask for a specific call."""


_SENIOR_TITLE_KEYWORDS = {
    "ceo", "chief executive", "president", "founder", "co-founder", "cofounder",
    "managing director", "managing partner", "general partner",
    "partner", "principal",
}


def _is_senior_contact(profile: LinkedInProfile) -> bool:
    if profile.notes and "SENIOR CONTACT" in profile.notes.upper():
        return True
    if not profile.title:
        return False
    title_lower = profile.title.lower()
    return any(kw in title_lower for kw in _SENIOR_TITLE_KEYWORDS)


def _build_user_prompt(profile: LinkedInProfile) -> str:
    me = MY_BACKGROUND

    lines = [
        f"- Name: {profile.full_name}",
        f"- Title: {profile.title}",
        f"- Company: {profile.company}",
    ]

    if profile.location:
        lines.append(f"- Location: {profile.location}")

    if profile.school:
        school = f"- School: {profile.school}"
        if profile.grad_year:
            school += f" (class of {profile.grad_year})"
        lines.append(school)

    if profile.past_roles:
        lines.append(f"- Past roles: {profile.past_roles}")

    if profile.fraternity:
        lines.append(f"- Fraternity/sorority: {profile.fraternity}")

    if profile.clubs:
        lines.append(f"- Clubs/organizations: {profile.clubs}")

    if profile.activities:
        lines.append(f"- Activities/leadership: {profile.activities}")

    if profile.about:
        lines.append(f"- About them: {profile.about}")

    lines.append(f"- LinkedIn: {profile.url}")

    profile_block = "\n".join(lines)

    line2_research = ""
    if profile.notes:
        line2_research = f"""
*** LINE 2 RESEARCH — USE THIS FOR THE RESEARCH LINE ONLY ***
{profile.notes}

This is the raw research for LINE 2 of the email. Extract the single most specific thing the
recipient personally MADE, BUILT, WROTE, or FOUNDED from this note. That becomes LINE 2.
Then LINE 3's ask must tie directly back to that exact thing — not their career generally.
If multiple things are listed, pick the one most relevant to the sender's background and most
likely to make the recipient feel like you actually found something real.
*************************************************************
"""

    senior_flag = ""
    if _is_senior_contact(profile):
        senior_flag = """
*** SENIOR CONTACT — apply the Senior Contact Override from the system prompt ***
"""

    return f"""Write a cold outreach email to this person using the 3-line format from the system prompt.

{profile_block}
{line2_research}{senior_flag}
Follow the format exactly: LINE 1 (the sender's credibility hook), LINE 2 (the highest tier the research \
note supports — see the LINE 2 priority list in the system prompt), LINE 3 (15-minute ask tied to \
LINE 2 + "Happy to work around your schedule"). Subject references the LINE 2 finding specifically."""


def _strip_signoff(body: str) -> str:
    me = MY_BACKGROUND
    for marker in (f"Thanks,\n{me['name']}", f"Thank you,\n{me['name']}"):
        idx = body.find(marker)
        if idx != -1:
            return body[:idx].strip()
    return body.strip()


def _validate_email_body(body: str) -> list[str]:
    """Check the generated body against the numeric/structural constraints the
    model doesn't reliably self-enforce from prose alone (word caps, single-ask
    phrasing). Returns a list of violation descriptions, empty if none."""
    content = _strip_signoff(body)
    violations = []

    word_count = len(content.split())
    if word_count > 100:
        violations.append(
            f"Body is {word_count} words (greeting through Line 3, excluding sign-off) — must be under 100."
        )

    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    for p in paragraphs[1:4]:
        wc = len(p.split())
        if wc > 35:
            violations.append(f"A body line is {wc} words (must be under 35): \"{p[:60]}\"")

    ask_line = paragraphs[3] if len(paragraphs) > 3 else content
    question_count = ask_line.count("?")
    if question_count > 1:
        violations.append("Line 3 contains more than one question mark — must be a single ask.")
    elif question_count == 1 and re.search(r"\band (how|what|why|whether|when)\b", ask_line, re.IGNORECASE):
        violations.append(
            "Line 3's question combines two asks joined by 'and' (e.g. 'what X and how Y') — "
            "must be a single one-line-yes question about one thing."
        )

    return violations


def generate_email(
    profile: LinkedInProfile,
    email_samples_text: str,
    client: anthropic.Anthropic,
) -> GeneratedEmail:
    import json

    _clean = clean_email_text

    def _ensure_signoff(body: str) -> str:
        me = MY_BACKGROUND
        if me["name"] in body and me["email"] in body:
            return body
        return body.rstrip() + f"\n\nThanks,\n{me['name']}\n{me['email']}\n{me['linkedin']}"

    def _find_json_objects(text: str) -> list[str]:
        """Find every top-level {...} span via brace matching, so that
        Claude second-guessing itself (emitting a draft, commentary, then a
        corrected JSON blob) doesn't get treated as one giant malformed span."""
        spans = []
        depth = 0
        start = None
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start is not None:
                        spans.append(text[start:i + 1])
                        start = None
        return spans

    def _parse(raw_text: str) -> dict | None:
        # Strip markdown fences if Claude adds them despite instructions
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```")[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            raw_text = raw_text.strip()

        # Claude sometimes second-guesses itself and emits an initial JSON blob,
        # some reasoning about which rule it violated, and then a corrected JSON
        # blob. Take the LAST object that actually parses with the right keys,
        # since that's the final, self-corrected answer.
        for candidate in reversed(_find_json_objects(raw_text)):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if "subject" in parsed and "body" in parsed:
                return parsed
        return None

    system_prompt = _build_system_prompt(email_samples_text)
    messages = [{"role": "user", "content": _build_user_prompt(profile)}]

    for attempt in range(2):
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        raw = response.content[0].text.strip()
        data = _parse(raw)

        if data is None:
            fallback_subject = (
                f"Question for {profile.company}"
                if profile.company
                else f"{MY_BACKGROUND['school']} student question"
            )
            return GeneratedEmail(
                profile=profile,
                subject=fallback_subject,
                body=_ensure_signoff(_clean(raw)),
            )

        subject = _clean(data["subject"])
        body = _ensure_signoff(_clean(data["body"]))
        violations = _validate_email_body(body)

        if not violations or attempt == 1:
            if violations:
                print(
                    f"  [!] {profile.full_name}: still has issues after one retry: "
                    + "; ".join(violations)
                )
            return GeneratedEmail(profile=profile, subject=subject, body=body)

        messages.append({"role": "assistant", "content": raw})
        messages.append({
            "role": "user",
            "content": (
                "That violates the format rules:\n- " + "\n- ".join(violations) +
                "\n\nRewrite it fully, fixing these issues, keeping every other rule from the "
                "system prompt the same. Output ONLY the corrected JSON in the same format."
            ),
        })


def generate_emails_batch(
    profiles: list[LinkedInProfile],
    email_samples_text: str,
) -> list[GeneratedEmail]:
    client = anthropic.Anthropic()
    results = []
    for i, profile in enumerate(profiles, 1):
        print(f"  [{i}/{len(profiles)}] Generating email for {profile.full_name} ({profile.company})...")
        email = generate_email(profile, email_samples_text, client)
        results.append(email)
    return results
