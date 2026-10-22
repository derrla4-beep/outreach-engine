# The Playbook: my full setup, and what yours should look like

The README and SETUP.md cover the code. This file covers everything around it: what to
upload, which spreadsheets to build, which Claude Code add-ons I run, the weekly rhythm,
and the lessons that took a lot of trial and error. Follow it top to bottom once and you
end up with the setup I use every week.

**Contents**

1. [What the whole system looks like](#1-what-the-whole-system-looks-like)
2. [Accounts and tools](#2-accounts-and-tools)
3. [Upload everything about yourself](#3-upload-everything-about-yourself)
4. [Build the spreadsheets](#4-build-the-spreadsheets)
5. [Save your repeat jobs as skills](#5-save-your-repeat-jobs-as-skills)
6. [Token efficiency: the files and add-ons that keep Claude cheap and consistent](#6-token-efficiency)
7. [The weekly rhythm](#7-the-weekly-rhythm)
8. [Lessons that took trial and error](#8-lessons-that-took-trial-and-error)
9. [Copy-paste prompts](#9-copy-paste-prompts)

---

## 1. What the whole system looks like

```
 YOUR MATERIALS                 SPREADSHEETS (Google Sheets)       THIS REPO
 resume, behaviorals,    --->   Internship Tracker  (targets)  ->  knowledge_base.md
 essays, connections,           Networking Batches  (contacts)     email_rules.md
 best past emails               Do Not Contact      (dedupe)       add_emails.py -> queue
                                Response Tracker    (stats)        main.py --send-now  (Mon)
                                Chats / Connections (pipeline)     main.py --followups (Tue, Thu)
                                                                   main.py --stats
        ^                                ^                                |
        |                                |                                |
        +------ "run update": Claude reads Gmail + Calendar, updates the sheets ----+
```

There are two kinds of work:

- **Claude does the thinking work**: finds and vets contacts ("run batch"), writes every
  email from your knowledge base, queues them, and syncs your inbox and calendar back into
  the sheets ("run update").
- **You press the buttons**: every send is a command you run and confirm. Nothing is
  scheduled. (See [lesson 1](#sending) for why.)

---

## 2. Accounts and tools

Set these up first. Everything below assumes them.

| Tool | What it's for | Notes |
|---|---|---|
| [Claude Code](https://claude.com/claude-code) | Runs in this folder; writes emails, runs scripts | Sign in with your claude.ai account so the connectors below work |
| claude.ai **connectors**: Gmail, Google Calendar, Google Drive | Lets Claude read replies, coffee-chat invites, and your sheets | claude.ai > Settings > Connectors. Read-only use is all you need |
| **Claude in Chrome** extension | Lets Claude work in your real browser: LinkedIn, Hunter, Google Sheets | You stay signed in; Claude works in its own tab |
| Gmail API (SETUP.md step 3) | The scripts send and check replies through it | Separate from the connector. The scripts need it; the connector is for Claude |
| [Hunter.io](https://hunter.io) | Finds and verifies work emails | Starter plan is plenty. Budget about 500 credits a week |
| LinkedIn | Finding people and reading their profiles | |
| Google Sheets | Every tracker in section 4 | |
| Python 3.10+ | Runs the scripts | On Windows the command is `python`, not `python3` |

---

## 3. Upload everything about yourself

The emails are only as personal as what Claude knows about you. Claude is told to never
state a fact about you that isn't in `knowledge_base.md`, so anything you leave out simply
never shows up. Give it everything once, have it distill it, and you never upload it again.

### Step 1: make a materials folder

Create a folder called `my_materials/` in the repo root (it's gitignored, so none of it
leaves your computer). Drop in as much of this as you have:

| Upload | Why it helps |
|---|---|
| **Resume** (PDF, also copy it to the repo root with "resume" in the name) | Section 1 of the knowledge base; also attached to every email |
| **Behavioral stories** (your STAR stories / interview prep doc) | The best source of specific hooks: real numbers, real moments |
| **Essays** (application essays, "why this industry", personal statements) | Gives Claude your honest "why", in your own words |
| **Old resumes** | Older roles that are off the current resume but still make great hooks |
| **LinkedIn connections export** | Finds warm contacts and shared ties. LinkedIn > Settings > Data privacy > Get a copy of your data > Connections. You get `Connections.csv` |
| **People you already know** (family friends, alumni you've met, anyone who offered to help) | Goes into the Warm Contact list in `CLAUDE.md` |
| **Your 3-5 best past emails** (ones that got replies) | Shows Claude your voice |
| **Coffee chat notes** | What people told you; good for follow-ups and future hooks |
| **Your target list** (firms, programs, deadlines) | Seeds the Internship Tracker |

### Step 2: have Claude build your knowledge base

Open Claude Code in the repo and paste [prompt A](#prompt-a-build-my-knowledge-base). Claude
reads every file, fills in `knowledge_base.md` and the hooks in `email_rules.md`, then
interviews you on the gaps (hometown, high school, sports results, things you built).

Answer in detail. Hometown, high school, a sport, a city you lived in: these are the hooks
that get replies, and they only exist if you write them down.

### Step 3: keep it current

- New resume: replace Section 1 of `knowledge_base.md` and drop the new PDF in the root
  (the newest "resume" PDF wins; prefix an old one with `#` to retire it).
- Something finished (an internship, study abroad): add it to Section 4, "Facts to keep
  straight", in the past tense. Otherwise old contact notes make Claude write it as future.
- New warm contacts: add them under "Warm Contact Reminders" in `CLAUDE.md`. Claude then
  reminds you of them every time you ask who to reach out to.

---

## 4. Build the spreadsheets

I run two Google Sheets. Paste [prompt B](#prompt-b-build-my-spreadsheets) into Claude
(with Claude in Chrome connected) and it builds them for you. Here is what they need to hold.

**Keep the column headers exactly as you set them up.** Claude and its scripts find
columns by name, so renaming one later breaks things quietly.

### Sheet 1: Internship Tracker (what you're applying to)

**Tab "Tracker"**, one row per program:

| Column | What goes in it |
|---|---|
| Company | Short normal name ("Jefferies", not "Jefferies Financial Group Inc.") |
| Program | e.g. Summer 2027 IB Analyst |
| Location | |
| Type | Internship, insight program, full-time |
| Division | IB, S&T, research, private credit... |
| Status | Not applied / Applied / Awaiting / Interview / Offer / Rejected |
| Referral? | Yes / Promised / blank |
| # Referrals | Count |
| Contacts / Referral Info | "Name (team/office) call Fri 10/16 9:30am", appended by run update |
| Confidence | |
| Interest | High / Medium / Low |
| Date Applied | |
| Next Step | The concrete next action ("Chat w/ X 10/16, ask them to flag the app") |
| Follow-Up Date | |
| Notes | Facts only; Claude appends, never overwrites yours |

**Tab "Summary"**: formulas only (count by status, apps this week, referrals). Claude never
writes here.

This sheet decides **who to network into**: firms you applied to recently and have no
referral at get the most contacts each week.

### Sheet 2: Networking Batches (who you're emailing)

**Tab "Batches"**, one row per contact. This is what you paste into Claude Code to write
emails.

| Column | What goes in it |
|---|---|
| First Name | The name they go by |
| Last Name | |
| Email | Verified (see [lesson 4](#emails)) |
| Company | |
| Location | Where they work now. Blank defaults to New York |
| Description for Claude | The note: career path, school with years, shared hooks, what you applied to there. Add "SENIOR CONTACT" for MD and up. See the example below |
| LinkedIn | Profile URL |
| Went to [Your School] | Checkbox, only when confirmed |
| Status | Scheduled / Hold / Sent |
| Send Date | |

A good "Description for Claude" looks like this (written casually, like notes to a friend):

> [school] 2021-2025 undergrad, same HS as me. first-year IB analyst, did a PE internship
> before. closest to recruiting, ask how they landed it. firm line: applied to their fall insight
> program, want to be a competitive applicant + learn from people inside.

Put students and ex-interns at the bottom below two blank rows with Status "Hold" (reach
them on LinkedIn or a school email, never their firm email).

**Tab "Do Not Contact"**: everyone you've ever emailed or queued. This is the master
dedupe list.

| Name | Email | Company | LinkedIn | Date contacted | Source | Replied | Bounced |
|---|---|---|---|---|---|---|---|

- Have Claude write a small Google Apps Script (Extensions > Apps Script) with an
  `onEdit` trigger plus a `prettify` function that copies every Batches row into Do Not
  Contact and formats the sheets. Prompt B asks for this.
- After each Monday send, have Claude append everyone in `data/sent_log.json` too.
- Duplicate rule: same email, same LinkedIn URL, **or** same firm + same last name + same
  first initial.

**Tab "Response Tracker"**: one row per send week. Emails sent, Bounced, Replies, Positive
replies, Chats booked, Referrals, Follow-ups sent, Hunter credits, then rate columns and KPI
cards as formulas. Claude fills the counts; never let it touch the formulas.

**Tab "Scheduled/incoming Chats"**: left block = booked chats sorted by date
("Firm team - Fri 10/16 9:30am"); right block = in progress (replied but not booked,
waiting on them, warm intros with drafts ready). Move people left once booked.

**Tab "Connections"**: chats that already happened. Name, Company, Sector, Role, and your
own notes on how it went. Claude adds the facts; you write the vibe.

---

## 5. Save your repeat jobs as skills

A **skill** is a saved instruction file Claude follows when you say a trigger phrase. I have
two, and they're the reason I can say two words instead of re-explaining a 50-step process
every session. Make yours with [prompt C](#prompt-c-create-my-two-skills) (Claude uses its
skill-creator to write them; save them to your claude.ai account so they work everywhere).

### "run batch": find, vet, and add new contacts

1. **Pick targets** from the Internship Tracker. Never skip a firm, just weight it: recent
   applications, "Awaiting", high interest, and zero referrals get the most contacts.
   Already-referred or heavily networked firms get a few.
2. **Plan the split first** (e.g. 25 / 15 / 10 / 10 / 5 / 5 / 5) so the session doesn't end
   halfway through one firm. Plan about 20% extra people: some will be duplicates or fail
   email checks.
3. **Source people**: LinkedIn people search filtered to the current company, plus
   keywords like your school or "investment banking analyst new york". Hunter's Domain
   Search for smaller firms. Dedupe against Do Not Contact **before** opening profiles.
4. **Vet every person** (read experience dates and education). See [lesson 3](#vetting).
5. **Write the note** in "Description for Claude".
6. **Verify every guessed email** in Hunter.
7. **Paste rows into Batches**, run the Apps Script, and confirm Do Not Contact grew by the
   same number.
8. **Report back**: count by firm, best hooks, who was skipped and why, duplicate rate per
   firm, Hunter credits used, weekly running total.

**Hard stop at 75 contacts per session.** About 6-7 sessions a week gets you to 450-500.

When a firm gets **thin** (more than half of search results are already in Do Not
Contact), widen in this order: other offices, adjacent teams (capital markets,
restructuring, private credit, S&T, research), more senior titles, then new firms.
Re-emailing the same person is a last resort: non-responders only, after 4-6 weeks, and
only with real news.

### "run update": sync inbox and calendar into the sheets

Read-only on email and calendar (it never sends, replies, or accepts invites).

1. **Replies** since the last send: classify positive / neutral question / negative.
2. **Bounces and auto-replies**, including Trash. Note out-of-office return dates.
3. **Calendar**: the full window from 2 days ago to 3 weeks out. Match coffee chats to
   reply threads and check the time zone matches what the person wrote.
4. **Update the sheets**: Tracker (contacts, referrals, next step), Chats, Connections,
   Response Tracker counts, and Replied / Bounced in Do Not Contact.
5. **Pool check**: per firm, how many you've contacted, the duplicate rate, and whether
   it's healthy / watch (30-50%) / thin (over 50%), with the next lever.
6. **Report back**: chats this week and next, new referrals, replies waiting on you,
   bounces, weekly stats, pool table.

---

## 6. Token efficiency

Every time Claude has to rediscover something, you pay for it in tokens and get slightly
different results. The setup is built so Claude reads small, distilled files instead of
re-deriving things.

### The repo files that do this

| File | What it saves |
|---|---|
| `CLAUDE.md` | Loaded automatically every session. The workflow is written once, so you never re-explain it, and Claude never invents an old or different process |
| `AGENTS.md` | Same instructions for Codex, if you use it |
| `knowledge_base.md` | Your whole background distilled into one short file. Claude reads it instead of re-reading your PDFs, essays, and stories every batch |
| `email_rules.md` | One rulebook: format, hooks, banned phrases. No re-explaining your voice |
| `add_emails.py` + `email_checks.py` | Code checks the mechanical rules (word caps, banned phrases, double asks, duplicates) for free, so Claude doesn't spend tokens self-policing and you don't spend them catching its mistakes |
| `followups.py` (`TEMPLATES`) | Follow-ups are fixed text; Claude writes nothing for them |
| `COMMANDS.md` | Every command in one place, so you never ask Claude what to run |
| `urls.txt` | One line of research per contact, saved. Re-writing an email never needs a re-research |

### Claude Code add-ons I run

| What | Install (type in Claude Code) | What it does |
|---|---|---|
| [superpowers](https://github.com/obra/superpowers) | `/plugin marketplace add obra/superpowers-marketplace` then `/plugin install superpowers@superpowers-marketplace` | Skills for planning before building, debugging methodically, and verifying before claiming something works |
| [andrej-karpathy-skills](https://github.com/forrestchang/andrej-karpathy-skills) | `/plugin marketplace add forrestchang/andrej-karpathy-skills` then `/plugin install andrej-karpathy-skills@karpathy-skills` | Guidelines that stop Claude from over-engineering: small, surgical changes |
| Your two skills | Section 5 | The biggest single saver: "run batch" and "run update" instead of long explanations |
| Memory | Built in | When something goes wrong, say "remember this" and why. Claude saves it and won't repeat the mistake next session |

### Habits

- **One task per session.** Run `/clear` between unrelated jobs (a batch, then an update).
  Long sessions drag everything earlier along with them.
- **Cap batches** (75 contacts). Huge sessions get summarized mid-way and lose detail.
- **Read sheets as data, not screenshots.** Tell Claude to read Google Sheets through the
  Drive connector or as CSV, never by scrolling and screenshotting.
- **Keep browser outputs short.** In Chrome, have Claude save intermediate results in the
  page's storage and read them back in small chunks; long outputs get dropped.
- **Update the files, not the chat.** If you correct Claude about your background or
  voice, have it edit `knowledge_base.md` / `email_rules.md` so the fix sticks.

---

## 7. The weekly rhythm

| Day | What you do | Command |
|---|---|---|
| Throughout the week | "run batch" sessions until you hit your weekly target | (Claude, in Chrome) |
| Sunday / before sending | Paste the week's Scheduled rows from Batches into Claude Code. It writes and queues every email | (Claude runs `add_emails.py`) |
| **Monday** | Send the batch | `python main.py --send-now` |
| **Tuesday** | Follow-up #1 to anyone who hasn't replied | `python main.py --followups` |
| **Thursday** | Follow-up #2 | `python main.py --followups` |
| Anytime | "run update" to sync replies and chats into the sheets | (Claude) |
| Anytime | Reply rates | `python main.py --stats` |
| Someone replied by call, text, or LinkedIn | Stop their follow-ups | `python main.py --mark-replied their@email.com` |

Use `--dry-run` on any send command to preview first. Leave the window open during
`--send-now`; emails go out about 2 seconds apart.

---

## 8. Lessons that took trial and error

<a id="sending"></a>
### Sending

1. **Send by hand, never on a schedule.** I first used a Windows scheduled task. Every time
   the computer was asleep at the send minute, the backlog got pushed to a later date
   instead of sent, and 78 emails sat unsent for weeks while the log said "nothing due".
   Now Monday is one command I run myself. If you miss a send, just run `--send-now`; never
   push dates forward.
2. **Gmail signature.** Original emails use your Gmail **default signature for new emails**.
   Set it before the first send.
3. **Google logs you out after 7 days** while your OAuth app is in "Testing". The next
   command just reopens the browser. Publishing the app stops it.
4. **Follow-ups never go to anyone who replied.** The checks include auto-replies,
   bounces, emails you sent by hand, and replies from a different address. Anything unclear
   is held for you. Never loosen these checks.

<a id="writing"></a>
### Writing

5. **Vary Line 1 every email.** People at the same firm compare notes; an identical
   sentence reads as a mail merge.
6. **Senior contacts (MD, Partner, Founder) get no meeting ask.** Ask to be on their radar
   instead. VPs still get the normal ask.
7. **A personal tie gets a personal ask.** Same high school? Ask about that, not their
   deal flow.
8. **Finished things stay past tense**, even if an old contact note says otherwise.
9. **Hold, don't guess.** If a note is cut off or unverified, Claude holds that one person
   and asks you; the rest still get queued.

<a id="vetting"></a>
### Vetting contacts

10. **Read the date span on every school.** About 4 years = their undergrad (use it as the
    hook). 1-2 years = a master's or MBA ("did their master's at X"). Under a year, or
    summer / exchange / visiting = not their school; never use it as a shared-school hook.
11. **Graduating next year or later = still a student.** Put them in Hold; don't email their
    firm address.
12. **Check they still work there.** An end date on the role, or a newer job elsewhere, means
    skip.
13. **Use the name they go by** in First Name, but build the email from their legal name
    (the LinkedIn URL often shows it).
14. **If the profile name doesn't match the search result, drop the person.**

<a id="emails"></a>
### Emails and bounces

15. **Verify every guessed email** on Hunter unless the domain is catch-all (accepts
    everything). If invalid, try nickname, legal name, no hyphen, shortened surname, and
    first-initial + last before giving up.
16. **Keep a table of confirmed email formats per firm** in your batch skill (first.last,
    flast, quirks like hyphens being dropped). It saves credits and guesses every week.
17. **"UNVERIFIED" tag: 10% max.** Only for things genuinely unconfirmed after trying.
    Anything tagged gets held back, so overusing it quietly shrinks your batch.
18. **Bounces hide in Trash.** Search everywhere when counting them. A firm whose server
    rejects verification (even for known-good addresses) isn't a bad-address problem.

<a id="sheets"></a>
### Sheets and the browser

19. **Row numbers lie.** Reading a sheet as CSV skips hidden and blank rows, so the line
    number isn't the sheet row. Before writing to a cell, Claude jumps to it in the Name Box
    and reads what's there.
20. **Insert new rows at the top**, above the existing data, so the Hold area at the bottom
    is never touched.
21. **After pasting, re-read the sheet** to confirm the count and that emails are unique,
    then run the sync script and confirm Do Not Contact grew.
22. **Check the full 3-week calendar window** before saying a chat invite is missing; next
    week's chats are easy to miss. Watch time zones ("3:30 central" = 4:30 ET).
23. **A blank row may be on purpose** (you pulled someone to text them instead). Claude
    asks; it doesn't restore.

<a id="files"></a>
### Files

24. **Keep your copy private.** Once used, `data/`, `urls.txt`, `knowledge_base.md`, and
    `my_materials/` hold real people's emails and your personal details.
25. **If the repo is in OneDrive or iCloud, you get version history for free.** A bad edit
    that wipes a file can be recovered there (right-click > Version history) even when it
    was never committed to git. Have Claude back a file up before rewriting it.

---

## 9. Copy-paste prompts

### Prompt A: build my knowledge base

```
Read every file in my_materials/ (resume, behavioral stories, essays, old resumes,
connections export, past emails, notes). Then:
1. Fill in knowledge_base.md. Section 1 is my resume verbatim. Sections 2-4 are the
   story behind it: school path, hometown and high school, sports with specific results,
   things I built, why this industry, organizations, older experience, other interests,
   what I'm recruiting for, and facts to keep straight. Only write what the files say.
2. Fill in "About the sender" and 4-7 credibility hooks in email_rules.md, each with
   real numbers and a "use when" rule, plus the matching table.
3. From my connections export and notes, list warm contacts (people I actually know,
   alumni from my school or high school at target firms) and add the strongest under
   "Warm Contact Reminders" in CLAUDE.md.
4. Fill in config.py with my name and sending address.
5. Then interview me, one question at a time, on anything missing or vague. Push for
   specifics: numbers, results, names of places.
```

### Prompt B: build my spreadsheets

```
Using Claude in Chrome and Google Sheets, build two spreadsheets for my outreach,
following section 4 of PLAYBOOK.md exactly:
1. "Internship Tracker" with tabs Tracker and Summary (Summary is formulas only).
   Seed Tracker from my target list in my_materials/.
2. "Networking Batches" with tabs Batches, Do Not Contact, Response Tracker,
   Scheduled/incoming Chats, and Connections, with the exact columns listed.
3. An Apps Script in Networking Batches with an onEdit trigger and a prettify function
   that copies every Batches contact into Do Not Contact (no duplicates by email,
   LinkedIn URL, or firm + last name + first initial) and formats the tabs.
4. Freeze the header rows and add data validation for Status columns.
When done, give me both links and save them in my batch and update skills.
```

### Prompt C: create my two skills

```
Use skill-creator to make two skills, following section 5 of PLAYBOOK.md, with my
sheet links, my school, my hooks from knowledge_base.md, and my weekly target:
1. "run-networking-batch", triggered by "run batch": pick targets from the Internship
   Tracker, plan the split, source on LinkedIn and Hunter, dedupe against Do Not
   Contact, vet every profile (education date spans, still at the firm, students to
   Hold), write the Description for Claude, verify emails, paste into Batches, run
   prettify, and report. Hard stop at 75 contacts. Include an empty table of confirmed
   email formats per firm that you add to every session.
2. "run-update", triggered by "run update": read-only on Gmail and Calendar; sync
   replies, bounces, and coffee chats (3-week window) into all the sheets, run the pool
   check, and report.
Include every lesson in section 8 of PLAYBOOK.md that applies.
```

### Prompt D: write this week's emails

```
Here are this week's contacts from my Batches sheet (Status = Scheduled):
[paste the rows]
Write and queue them following CLAUDE.md.
```

### Prompt E: when Claude gets something wrong

```
That was wrong because [reason]. Fix it, then update [knowledge_base.md /
email_rules.md / my skill] so it never happens again, and remember it.
```
