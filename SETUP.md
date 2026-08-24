# Setup Guide

## 1. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium   # only if you plan to use --urls scraping mode
```

## 2. Create your profile

Everything about the sender lives in one gitignored file:

```bash
cp data/profile.example.json data/profile.json
```

Edit it: name, email, LinkedIn, school, target role, differentiators, and the
`credibility_hooks` list. Each hook needs a `summary` (the concrete thing you did) and a
`use_when` (the signal in the recipient's background that makes it the right pick). Mark
exactly one hook `"is_default": true` — it is the fallback when nothing matches.

If you skip this step the tool runs against `data/profile.example.json` with a fictional
sender, which is useful for seeing the pipeline work but not for sending real mail.

## 3. Set your Anthropic API key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Or create a `.env` file (gitignored):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Get a key at https://console.anthropic.com/

## 4. Set up the Gmail API

Needed to sample your sent mail for tone, create drafts, and send. Skip with `--no-gmail`.

### 4a. Create a Google Cloud project

1. Go to https://console.cloud.google.com/
2. Create a project
3. **APIs & Services** → **Library** → search **Gmail API** → Enable

### 4b. Create OAuth2 credentials

1. **APIs & Services** → **Credentials** → **+ Create Credentials** → **OAuth client ID**
2. Application type: **Desktop app**
3. **Create** → **Download JSON**
4. Rename it to `credentials.json` in the project root (gitignored)

### 4c. Configure the OAuth consent screen

1. **APIs & Services** → **OAuth consent screen**
2. User Type: **External** (for a personal Gmail account)
3. Fill in an app name and your email
4. **Scopes**: add `gmail.readonly` and `gmail.compose`
5. **Test users**: add your own Gmail address

### 4d. Authenticate

```bash
python main.py --auth
```

Opens a browser once and saves `token.json` locally (gitignored).

---

## Usage

### CSV mode (recommended)

```bash
python main.py --template     # writes data/profiles.csv
# fill it in, then:
python main.py --csv
```

For each generated email you can save it to a file, push it as a Gmail draft, or queue it
for timezone-aware sending.

### URL mode

```bash
echo "https://www.linkedin.com/in/someone/ | played college baseball, lead with that" >> urls.txt
python main.py --urls urls.txt
```

First run opens a browser to log in to LinkedIn; the session is saved. LinkedIn blocks
scraping aggressively — CSV mode is the reliable path.

### The send queue and follow-ups

```bash
python main.py --list-queue    # what's pending
python main.py --send-queue    # send anything now due
python main.py --followup      # scan threads, queue follow-ups
```

`--send-queue` is the command to put on a cron job or scheduled task; it is a no-op when
nothing is due.

### Reviewing the pipeline

```bash
python server.py     # then open http://127.0.0.1:5000
```

Local only, no authentication. Do not expose it to a network.

### Linting research notes

```bash
python main.py --check urls.txt
```

Flags hedge and unverified language in your notes before any generation happens.

---

## CSV format

| Column | Required | Description |
|---|---|---|
| `url` | No | LinkedIn profile URL |
| `first_name` | Yes | First name |
| `last_name` | Yes | Last name |
| `title` | Yes | Current job title |
| `company` | Yes | Current employer |
| `school` | No | Undergraduate school |
| `grad_year` | No | Graduation year |
| `notes` | No | The specific angle: what they built, a career move, a shared tie |

The `notes` column is what makes or breaks the email. See the tier rules in
[docs/DESIGN.md](docs/DESIGN.md).

---

## A note on data

`data/profiles.csv`, `data/contacts.json`, and everything else holding real people's
information is gitignored. The committed `*.example.*` files are entirely synthetic. Keep it
that way — see [Data & privacy](docs/DESIGN.md#data--privacy).
