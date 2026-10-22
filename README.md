# Banking Outreach

A cold-email pipeline for recruiting (built for investment banking, works for any
networking-heavy search). **Claude Code writes each email** from your background and a note
about the contact, **Python sends it through your Gmail**, follows up with people who
haven't replied, and tracks your reply rates.

Nothing runs on a schedule. Every send is a command you run and confirm.

## How it works

```
 You paste contacts           Claude Code                      You run
 (name, email, LinkedIn,  ->  reads knowledge_base.md      ->  Mon  python main.py --send-now
  a note on each)             + email_rules.md,                Tue  python main.py --followups   (#1)
                              writes each email, queues it     Thu  python main.py --followups   (#2)
                              with add_emails.py                    python main.py --stats
```

- **Personal, not mail-merged.** Every email is a short 4-line note: who you are (one hook
  matched to the recipient), that you're recruiting, one specific thing about *them*, and
  one easy ask. The rules live in `email_rules.md`.
- **Checked before queueing.** `add_emails.py` rejects emails that break the mechanical rules
  (word caps, banned phrases, double asks) and refuses anyone you've already emailed.
- **Safe follow-ups.** Before each follow-up, `followups.py` checks Gmail for any reply,
  auto-reply, bounce, or message you sent them by hand, and checks it again right before
  sending. Anyone who replied never gets another email. Anything unclear is held for you
  to decide. `tests/test_followups.py` covers every no-send case.
- **Reply stats.** `--stats` shows reply rates overall, per weekly batch, and by
  original / follow-up #1 / #2.

## Get started

**New here? Read [`PLAYBOOK.md`](PLAYBOOK.md) first.** It's the full setup step by step:
what to upload, which spreadsheets to build, the skills and add-ons to install, the weekly
rhythm, and every lesson that took trial and error.

1. Follow [`SETUP.md`](SETUP.md): install, fill in your info, connect Gmail (~20 min).
2. Open the folder in [Claude Code](https://claude.com/claude-code) and paste a few contacts:

   ```
   Jane Doe | jane.doe@examplebank.com | https://www.linkedin.com/in/jane-doe/ |
   Tech M&A analyst, ran her college's investment club, same hometown as me
   ```

   Claude writes the emails, shows them to you, and queues them.
3. Send them with `python main.py --send-now` (it shows a table and asks you to type
   `send`). All commands are in [`COMMANDS.md`](COMMANDS.md).

## Files

| File | What it is |
|---|---|
| `PLAYBOOK.md` | **Start here.** The full setup around the code: uploads, spreadsheets, skills, lessons |
| `knowledge_base.md` | **Fill in.** Your resume + background; the only source of facts about you |
| `email_rules.md` | **Fill in the hooks.** The rulebook Claude writes every email by |
| `config.py` | **Fill in.** Your name and sending address |
| `CLAUDE.md` / `AGENTS.md` | Instructions Claude Code / Codex follow in this repo |
| `main.py` | Entry point for `--send-now`, `--followups`, `--stats`, `--mark-replied` |
| `add_emails.py` | Queues a batch of emails Claude wrote, after checking the rules and duplicates |
| `email_checks.py` | The mechanical rule checks + processed LinkedIn URLs |
| `schedule_sender.py` | The queue and the Monday send |
| `followups.py` | Reply checks + follow-up sends (`TEMPLATES` holds the follow-up text) |
| `stats.py` | Reply-rate report |
| `sent_log.py` | `data/sent_log.json`: every email sent, its follow-ups and reply |
| `text_utils.py`, `gmail_auth.py` | Shared helpers, Gmail login |
| `urls.txt` | LinkedIn URL + personalization note per contact |
| `data/` | Queue, sent log, stop list (start empty) |

## Privacy

Once you start using it, `data/`, `urls.txt`, and `knowledge_base.md` hold your contacts'
emails and your personal details. Keep your copy of the repo **private**. Gmail
credentials (`credentials.json`, `token.json`) and PDFs are gitignored.
