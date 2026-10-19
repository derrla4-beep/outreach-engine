# Commands

Run from the project folder. Nothing runs on a schedule; every command is run by hand.
`--dry-run` previews without sending, and `--limit N` caps how many go out.

## Monday: send the batch

```
python main.py --send-now                  shows the whole queue as a table, type "send", sends them all
python main.py --send-now --limit 5        only the next 5
python main.py --send-now --dry-run        show the table without sending anything
python main.py --send-now --review         one by one instead: (s)end (k)eep (x)drop (q)uit
```

- Anyone already emailed (sent log or Gmail Sent) is skipped automatically.
- Emails go out about 2 seconds apart; 200 takes roughly 10 minutes. Leave the window open.

## Tuesday and Thursday: follow-ups

```
python main.py --followups --dry-run       preview who gets #1 / #2 and who's skipped (sends nothing)
python main.py --followups                 checks Gmail, shows the table, type "send" to send
python main.py --followups --limit 20      send at most 20
```

- The same command does both days. On Tuesday it sends #1, and on Thursday it sends #2.
- Anyone who replied is skipped.
- Held contacts ask: (r)elease, (m)ark replied, or (k)eep held.
- Never runs on weekends.

## Anytime

```
python main.py --stats                             reply rates: overall, per week, to original / #1 / #2
python main.py --mark-replied someone@bank.com     they replied by call, LinkedIn or text: never follow up
python main.py                                     prints the command list
```

## Queueing emails

Claude Code runs these for you after writing the emails:

```
python add_emails.py batch.json --dry-run
python add_emails.py batch.json
```

## After editing the follow-up code

```
python -m pytest tests
```
