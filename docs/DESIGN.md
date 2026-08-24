# Design notes

Decisions in this system that were not obvious, and what they cost.

---

## Data & privacy

This is the constraint that shaped the repository layout, so it goes first.

The tool operates on a list of real people who never agreed to appear in a public
repository: their names, employers, LinkedIn profiles, work email addresses, and private
notes about how to approach them. That data is genuinely useful to the tool and genuinely
inappropriate to publish.

The split:

- **Real data is gitignored, always.** `data/contacts.json`, `data/profiles.csv`,
  `data/scheduled_queue.json`, `data/followup_state.json`, `data/processed_urls.txt`, and
  the operator's own `data/profile.json` never enter version control. Nor do `voice.txt`,
  `best_emails.txt`, or any `.pdf`/`.docx`/`.xlsx`.
- **Every committed data file is synthetic.** The `*.example.json` / `*.example.csv` files
  contain invented people at invented firms on `example.com` domains.
- **Reads fall back, writes do not.** `config.resolve_data_file()` returns the real file if
  it exists and the committed example otherwise, so a fresh clone runs end to end. Writes go
  through `config.data_path()` and always target the real filename, so example data is never
  mutated into a mixture of fake and real records.
- **Identity is configuration, not source.** Nothing in the `.py` files names the operator.
  The sender's name, email, school, differentiators, and credibility hooks all load from
  `data/profile.json`. This started as a privacy requirement and turned out to be the right
  factoring anyway — the prompt builder is now reusable by anyone.

The failure mode being designed against is the ordinary one: someone clones the repo, runs
it, and accidentally commits their contact list. Making the ignored path the default path is
what prevents that, rather than a warning in a README.

---

## Timezone-aware scheduling

`schedule_sender.py` does not send when generation finishes. It queues each message and
releases it on the next Tuesday, Wednesday, or Thursday between 8:30 and 9:59 AM **in the
recipient's local timezone**, inferred from their location.

Three things fall out of this:

- Monday and Friday are excluded deliberately. Monday morning competes with the weekend
  backlog; Friday afternoon gets read and forgotten.
- The minute is randomized within the window. A queue that fires every message at exactly
  9:00:00 has an obvious machine signature, and recipients who compare notes notice.
- Timezone inference is a keyword match against a location string, and it falls back to a
  fixed default (`America/New_York`) when nothing matches. That default is a real limitation,
  not a neutral choice: it silently mis-times mail to anyone outside the US East Coast whose
  location string is unusual.

The cost is latency: a message written Friday night sits for four days. That is the right
trade when the reply rate on a cold email is a couple of percent and arrival time is one of
the few levers that does not require better writing.

---

## The follow-up state machine

`followup_system.py` scans sent threads and classifies each into one of two cases, which get
different treatment:

1. **No reply at all.** Up to two follow-ups — the first after `FOLLOWUP_DELAY_DAYS`, the
   second after `SECOND_FOLLOWUP_DELAY_DAYS` more — capped hard at `MAX_FOLLOWUPS`.
2. **They replied, you replied, they went quiet.** Exactly one follow-up, ever. Never
   escalated to a second.

The asymmetry is the point. Silence after a first email carries no information; silence
after a real exchange usually means "not now," and a second nudge there converts a neutral
contact into an annoyed one. The system is built to give up.

`FOLLOWUP_MAX_AGE_DAYS` adds a staleness floor: past three weeks a follow-up reads as
strange rather than persistent, so those threads are dropped rather than revived.

The state file (`data/followup_state.json`) is the deduplication boundary. Gmail's thread
list is the source of truth for *what happened*; the state file is the source of truth for
*what we already did about it*. Keeping those separate means a re-scan is idempotent and a
crash mid-run cannot double-send.

---

## Ingestion that degrades instead of failing

`linkedin_scraper.py` has three tiers, in order of reliability: CSV, then Playwright with a
saved session, then plain `requests`.

The ordering is the honest one rather than the impressive one. CSV is the default because
it always works; Playwright is real but breaks whenever LinkedIn changes markup or decides
the session looks automated; the `requests` path is kept mostly for completeness and is
expected to be blocked. A pipeline whose first step is the fragile one fails constantly, and
the fallback that matters is the boring one.

---

## Voice matching from real sent mail

`email_analyzer.py` samples the operator's Gmail sent folder and feeds real examples into
the system prompt, rather than describing a tone in the abstract.

"Write in a direct, specific, non-corporate voice" produces a model's idea of that. Ten
actual emails the person actually sent produce their sentence lengths, their hedges, and the
way they actually open. The heuristic that selects networking mail from the sent folder is
keyword-based and derives its school tokens from the profile, so it is not hardcoded to one
university.

The privacy consequence: those samples are real correspondence, so `voice.txt` and
`best_emails.txt` are gitignored alongside contact data.

---

## Deterministic validation, not a second model call

Two things run after generation and neither is an LLM:

- `email_generator._validate_email_body()` enforces the numeric and structural constraints
  the model does not reliably self-police from prose: a 100-word cap on the body, a 35-word
  cap on each of the three lines, and a single-ask check on line 3 that rejects both multiple
  question marks and two questions joined by "and". The prose-level bans (filler phrases,
  attached-resume language) are prompt rules, not validator checks.
- `text_utils.clean_email_text()` normalizes punctuation: em and en dashes become commas,
  arrows become words, comma spacing is fixed, and numeric grouping like `1,000` is
  protected from the comma normalizer.

Both could have been "ask the model to check its work." Neither is, for the same reason: the
failures being caught are exactly the failures a model is prone to, so asking the same class
of system to catch them is unreliable and costs another round trip. A regex that removes
every em dash removes every em dash.

The generator also parses model output by brace-matching every top-level JSON span rather
than taking the first `{`. When a model second-guesses itself and emits a draft, some
commentary, then a corrected blob, naive parsing picks up the wrong one or chokes on the
whole span. Taking the last valid object is the behavior that matches what the model meant.

---

## Known gaps

- **No reply ground truth.** Status tracking records what was *sent*, not what actually got
  a response, so the system cannot learn which hooks work. The prompt encodes cold-outreach
  best practice, not measured results from this pipeline. Closing this loop is the single
  highest-value next change.
- **Timezone inference is heuristic.** It reads a free-text location string; it will be
  wrong for people who list a headquarters rather than where they sit.
- **The Flask UI has no auth.** It binds locally and assumes a single trusted operator on
  localhost. It should not be exposed to a network as written.
