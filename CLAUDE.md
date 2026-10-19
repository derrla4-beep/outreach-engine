# Banking Outreach — Claude Instructions

## Email Workflow (the ONLY current workflow)
1. The user gives Claude Code contacts: name, LinkedIn URL, email address, notes (often pasted from a spreadsheet).
2. Claude Code reads `knowledge_base.md` (current resume first, then the full background) and uses it to pick the most personal hook for each contact; never state a fact about the user that isn't in it. Then it writes the profile entry into `urls.txt` (format below) and **writes each email itself** following `email_rules.md` (greeting through Line 4 only; the sign-off and resume P.S. are added automatically).
3. Claude Code saves the batch as JSON in a scratch folder (`[{name, to, linkedin_url, location, subject, body}]`), runs `python add_emails.py <batch.json> --dry-run`, fixes any SKIPPED issues, then runs it for real. That queues the emails and marks the URLs processed. It refuses anyone already emailed (checked against Gmail Sent, `data/sent_log.json`, `data/processed_urls.txt`, and the stop list), so it needs Gmail access even for `--dry-run`.
4. The user runs everything themselves; nothing is scheduled to run on its own:
   - **Monday:** `python main.py --send-now` (or `--limit N`). Every send is logged to `data/sent_log.json`.
   - **Tuesday:** `python main.py --followups` sends follow-up #1 to anyone who hasn't replied.
   - **Thursday:** `python main.py --followups` sends follow-up #2.
   - `python main.py --stats` shows reply rates (overall, per weekly batch, to the original / #1 / #2).
   - `python main.py --mark-replied EMAIL` when someone replied outside Gmail (call, LinkedIn, text).

Follow-up texts are fixed templates in `followups.py` (`TEMPLATES`), not written per contact. Never loosen the reply checks in `followups.py`: anyone who has replied must never get another email; any doubt means don't send. Run `python -m pytest tests` after touching it.

If a note is cut off or unverified, hold that one contact and ask; queue the rest.

If `knowledge_base.md` or `email_rules.md` still has `[bracketed]` placeholders, stop and help the user fill them in before writing any email.

## Profile Research Default Behavior
Whenever a LinkedIn profile is researched (user pastes a URL), ALWAYS end by writing the profile entry directly into `urls.txt` with a full personalization note. Do not just suggest it — write it automatically. The format is:

```
https://www.linkedin.com/in/[handle]/ | [firm, group, key background details]; [specific hook or angle]; [any shared connection — school, sport, org, quant background]; [ask about X]
```

Never ask the user to copy it in manually.

## Warm Contact Reminders
Whenever the user asks who they should contact, who to reach out to, or who to add to the list, ALWAYS remind them to consider the following people first:

- [Add warm contacts here: family friends, alumni you've met, people who offered to help]

Surface this list proactively — do not wait for the user to ask twice.
