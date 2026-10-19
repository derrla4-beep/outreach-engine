# Outreach Email Rules

The rulebook Claude Code follows when writing each outreach email. Read
`knowledge_base.md` first; only state facts about the sender that are in it.

> **Customize:** fill in the "About the sender" line and the credibility hooks below
> from your own `knowledge_base.md`. The format, subject-line rules, and hard rules work
> as-is. Delete this note when you're done.

**About the sender.** [Your Name] is a [year] at [School] studying [major]. They are
targeting [role, e.g. Summer 2028 investment banking summer analyst roles] at
[types of firms].

`add_emails.py` checks the mechanical rules (word caps, banned phrases, single ask,
subject length) and prints SKIPPED with the reason when one fails.

---

## Credibility hooks (pick exactly ONE for Line 1)

List 4-7 of your strongest, most specific experiences. Each gets a letter, a one-line
summary with real numbers, and WHEN to use it. Examples of the shape:

- **A. [Current/most relevant role].** [What you do there, with a number.] Default hook
  for anyone in [the industry]: it is real, current, relevant work.
- **B. [Something you founded or built].** [One line.] Use when the recipient has a
  founder or entrepreneurial background.
- **C. [Sport].** [Captaincy or result.] Use when the recipient played a sport.
- **D. [Technical skill / major].** [One line.] Use when the recipient has a quant, CS,
  or technical background.
- **E. [Leadership role in a club or org].** [One line.] Use when the recipient had a
  similar role in college.
- **F. [Competition or award].** [One line.] Use for a recipient tied to that space.

**Matching guide**

| Recipient | Hook |
|---|---|
| Founder or entrepreneurial path | B |
| Played a sport | C |
| CS, quant, math, or data background | D |
| Leadership role in a college org/frat | E |
| Tied to [your competition's space] | F |
| In the industry, or no clear match | A |

When two hooks match, prefer the shared specific (B, C) over the generic default (A).

---

## The 4-line format (the only format allowed)

Write like a person talking, not a cover letter. Use contractions ("I'm", "I've",
"here's"). Join clauses with ordinary words ("and", "right now", "where", "so") instead
of stacking appositives. If a sentence couldn't be said out loud, rewrite it.

**Greeting.** Always "Good Morning [First Name]," on its own line, then a blank line,
then Line 1. No "Hope this email finds you well" or any pleasantry after it.

**Line 1: who you are.** One sentence. The plain self-introduction, then the ONE hook as
the second clause:

> "I'm a [year] at [School] studying [major], and right now I'm [the hook, in plain
> words]."

Keep the "I'm a [year] at [School] studying [major]" frame stable. VARY THE SECOND
CLAUSE EVERY TIME: many recipients work at the same firm and compare notes, so an
identical clause reads as a mail merge. Rotate which detail of the hook you foreground
and vary the sentence shape ("and right now I'm...", "and at [Firm] I...").

**Line 2: the recruiting line.** One short sentence saying plainly that you're
recruiting, naming the firm: "I'm interested in recruiting at [Firm] this cycle and
wanted to reach out."

- The role is ALWAYS the one in "About the sender". Never restate it as the recipient's
  own function.
- Use the firm's normal short name ("Jefferies", not "Jefferies Financial Group Inc.").
- If the firm doesn't run a program for your target role, don't name it: "I'm
  recruiting for [role] this cycle and wanted to reach out."
- Vary the phrasing across emails. One idea only; don't stack the research or the ask on it.

**Line 3: the research line.** One sentence from the contact's note. Use the highest tier
the note supports; never stop to ask which one:

1. Something they personally MADE, BUILT, WROTE, or FOUNDED (a guide, a model, a public
   deal they worked, a company or fund, a club they founded or led, a published piece).
2. A specific, verifiable CAREER MOVE named in the note (a named firm-to-firm move, or a
   seat-to-seat path like buy-side to advisory).
3. The single most specific concrete fact in the note (a sport result, a school, a named
   group or seat, or whatever the note flags as the lead hook).

Phrase it like a person who noticed something real: "Your move from equity research over
to tech coverage is the exact path I've been trying to understand." Never reference their
title, their firm's reputation, or how impressive their career is in the abstract.

**Line 4: the frictionless ask.** One sentence asking for 15 minutes on the EXACT topic
in Line 3, answerable with a one-line yes. A single question, never two asks. Then
"Happy to work around your schedule." Full stop. No availability windows.

**Formatting.** A blank line between each line.

**Sign-off.** Added automatically; never write it:
"P.S. I've attached my resume in case you wanted to take a look." then "Thanks," and the
Gmail signature. The resume PDF is attached automatically, so never mention the resume
in Lines 1-4.

**Length.** Greeting through Line 4 under 130 words; each line under 35 words.

---

## Subject line

Reference the specific thing from Line 3, stated plainly. 2-5 words, hard cap 40
characters, specific noun in the first ~33 characters. Sentence case. Calm and
professional, something only this recipient could receive:

- "[The thing they wrote/built]"
- "[School] student, [the club they founded]"
- "[Deal name] question"

Never: "Quick question", "Gotta ask", "Quick chat", "Networking Request", "Coffee Chat",
"Aspiring Banker", exclamation points, vague urgency, or anything that fits anyone.

---

## Hard rules (any violation disqualifies the email)

1. No arrows, em dashes, en dashes, or dash clusters anywhere.
2. No pleasantry after the greeting. The "Good Morning [Name]," line itself is required.
3. No availability windows ("I'm free 3-5 PM on Tuesdays...").
4. No "I completely understand your schedule is busy."
5. No hollow phrases: "I came across your profile", "I would love to", "Please let me
   know", "genuinely", "I was impressed by", "your incredible background".
6. Line 3 uses the highest available tier, never their employer or title as if impressive.
7. Line 4's ask is tied to the exact thing in Line 3.
8. Never mention the resume or attachment in Lines 1-4.
9. No reflexive commentary: "That didn't surprise me, but...", "I'll be honest...",
   "What struck me about your background is...", "I imagine...", "I bet...",
   "Naturally...", "That tracks", "I can see why". Just make the ask.
10. Never pause to ask which tier to use; pick the best one and write it. (The one
    exception is in CLAUDE.md: a note that is cut off or unverified, hold and ask.)
11. **Confidentiality.** If any hook touches confidential work (a client, a live deal, an
    internal product), state only what's safe to say publicly. Never client names,
    internal numbers, colleague names, or internal URLs. [List your specifics here.]
12. **No corporate register.** Never "I am currently serving as", "I wanted to take a
    moment", "I am reaching out to express my interest in", "I am writing to inquire".
13. **Timeline.** Anything `knowledge_base.md` marks as done stays in the past tense,
    even if a contact note says otherwise (the note is stale).
14. **Personal tie = personal ask.** When Line 3 is a shared experience (hometown, high
    school, school, a sport, a city), Line 4 asks about THAT experience in plain human
    terms, not a group, desk, or deal-flow question.

---

## Senior contact override

Applies when the title is CEO, Chief Executive, President, Founder/Co-founder, Managing
Director, Managing Partner, General Partner, Partner, or Principal (matched as whole
words), or the note says SENIOR CONTACT. Vice President / SVP / EVP / AVP are NOT senior
for this rule; they still get the normal ask.

Same 4 lines and spoken register. Line 1 leads with skills (modeling, technical skills,
research depth) inside the usual "I'm a [year] at [School]..." frame. Line 2 keeps the
recruiting line (it matters more here, since there is no call ask). Line 3 is the
research. Line 4 does NOT ask for a meeting: say you'd like to be on their radar or to
hear more about it.
