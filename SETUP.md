# Setup Guide

About 20 minutes, once.

## 1. Install dependencies

Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

(On Windows the command is usually `python`; on Mac/Linux it may be `python3`.)

## 2. Make it yours

| File | What to do |
|---|---|
| `config.py` | Set `MY_BACKGROUND` to your name and the Gmail address you'll send from. |
| `knowledge_base.md` | Paste your resume and fill in your background. Claude only writes facts that are in here. |
| `email_rules.md` | Fill in "About the sender" and your credibility hooks. The rest works as-is. |
| `followups.py` | Optional: reword the two follow-up messages in `TEMPLATES`, and add your school's email domain to `PUBLIC_DOMAINS`. |
| `CLAUDE.md` | Optional: list warm contacts under "Warm Contact Reminders". |
| Resume PDF | Drop your resume in the repo root with "resume" in the filename. It's attached to every original email (and gitignored). |

Tip: open the folder in Claude Code and say "help me fill in knowledge_base.md and
email_rules.md". It will interview you.

## 3. Gmail API (read the inbox for replies, send email)

### 3a. Google Cloud project

1. Go to https://console.cloud.google.com/
2. Create a project (e.g. "Outreach")
3. **APIs & Services** -> **Library** -> enable **Gmail API**

### 3b. OAuth consent screen

1. **APIs & Services** -> **OAuth consent screen**, User Type **External**
2. **Scopes**: `gmail.readonly` and `gmail.compose`
3. **Test users**: add the Gmail address you set in `config.py`

### 3c. OAuth credentials

1. **APIs & Services** -> **Credentials** -> **+ Create Credentials** -> **OAuth client ID**
2. Application type: **Desktop app** -> **Create** -> **Download JSON**
3. Rename it to `credentials.json` and put it in the repo root (it's gitignored)

### 3d. Log in

The first command that touches Gmail (for example `python main.py --stats`) opens a
browser to log in and saves `token.json` in the repo root. After that it refreshes itself.
If the OAuth app is still in "Testing" status, Google expires the login after 7 days; the
next command then opens the browser to log in again (publishing the app avoids this).

### 3e. Signature

Original emails end with the Gmail signature set as **Settings > General > Signature
defaults > For new emails use**. Set that to the signature you want on outreach (name,
school, phone, LinkedIn). Follow-ups don't use it; they're signed with your name from
`config.py`.

## 4. Check it works

```bash
python -m pytest tests                 # follow-up safety tests, no Gmail needed
python main.py --send-now --dry-run    # walk the queue, send nothing
python main.py --followups --dry-run   # see who would get a follow-up today
python main.py --stats                 # reply rates
```

## Data files (`data/`)

These start empty and fill up as you use the tool. They hold your contacts' names and
emails, so keep your own copy of the repo **private**.

| File | What it is |
|---|---|
| `scheduled_queue.json` | Emails waiting for `--send-now` |
| `sent_log.json` | Every email sent: thread, follow-ups, reply (backups: `sent_log.pre-*.bak.json`) |
| `do_not_followup.txt` | Addresses that never get a follow-up (`--mark-replied` creates and adds to it) |
| `processed_urls.txt` | LinkedIn URLs already queued |
