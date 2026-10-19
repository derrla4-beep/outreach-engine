"""Safety tests for automatic follow-ups, against a fake Gmail mailbox.

The rule under test: anyone who replied (in any way Gmail can show) never gets
another email. Each no-send case asserts that nothing was sent at all.
"""

import base64
import io
import email
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import followups  # noqa: E402
import sent_log  # noqa: E402
import stats  # noqa: E402

ME = followups.MY_EMAIL
CONTACT = "chris.smith@bigbank.com"
MONDAY = datetime(2026, 10, 5, 14, 0, tzinfo=timezone.utc)   # 10 AM EDT
TUESDAY, WEDNESDAY, THURSDAY = date(2026, 10, 6), date(2026, 10, 7), date(2026, 10, 8)


def ms(dt: datetime) -> str:
    return str(int(dt.timestamp() * 1000))


class _Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, num_retries=0):
        return self.fn()


class FakeGmail:
    """Just enough of the Gmail API for followups.py: threads.get, messages.list/get/send."""

    def __init__(self):
        self.msgs = {}
        self.sent = []
        self.fail_threads = False
        self._n = 0

    # -- building the mailbox -------------------------------------------------
    def add(self, thread_id, sender, when, subject="Hello", to=CONTACT, name="",
            labels=(), extra_headers=None, text=""):
        self._n += 1
        mid = f"m{self._n}"
        headers = {"From": f"{name} <{sender}>" if name else sender, "To": to,
                   "Subject": subject, "Message-ID": f"<{mid}@mail>"}
        headers.update(extra_headers or {})
        self.msgs[mid] = {
            "id": mid, "threadId": thread_id, "internalDate": ms(when), "labelIds": list(labels),
            "payload": {"headers": [{"name": k, "value": v} for k, v in headers.items()]},
            "_text": text,
        }
        return mid

    # -- API surface ----------------------------------------------------------
    def users(self):
        return self

    def threads(self):
        return _Threads(self)

    def messages(self):
        return _Messages(self)

    # -- tiny query evaluator for the query shapes followups.py builds ---------
    def search(self, q):
        m_after = re.search(r"after:(\d+)", q)
        after = int(m_after.group(1)) * 1000 if m_after else 0
        quoted = re.findall(r'"([^"]+)"', q)
        out = []
        for m in self.msgs.values():
            if int(m["internalDate"]) <= after:
                continue
            h = {x["name"].lower(): x["value"] for x in m["payload"]["headers"]}
            sender = followups._sender(m)
            disp = email.utils.parseaddr(h["from"])[0]
            haystack = " ".join(h.values()) + " " + m["_text"]
            if q.startswith("in:sent to:"):
                addr = q.split()[1][3:]
                ok = sender == ME and addr in h["to"].lower() and "DRAFT" not in m["labelIds"]
            elif q.startswith("from:(mailer-daemon"):
                ok = sender.split("@")[0] in ("mailer-daemon", "postmaster") and quoted[0] in haystack
            elif q.startswith('from:"'):
                ok = disp == quoted[0]
            else:
                target = q.split()[0][5:]
                if "@" in target:
                    ok = sender == target
                else:  # company domain + quoted term
                    ok = sender.endswith(target) and quoted[0] in haystack
            if ok:
                out.append({"id": m["id"]})
        return out


class _Threads:
    def __init__(self, g):
        self.g = g

    def get(self, userId, id, format=None, metadataHeaders=None):
        def run():
            if self.g.fail_threads:
                raise RuntimeError("HttpError 500")
            msgs = [m for m in self.g.msgs.values() if m["threadId"] == id]
            if not msgs:
                raise RuntimeError("HttpError 404: thread not found")
            return {"id": id, "messages": msgs}
        return _Req(run)


class _Messages:
    def __init__(self, g):
        self.g = g

    def list(self, userId, q, includeSpamTrash=False, maxResults=50):
        return _Req(lambda: {"messages": self.g.search(q)})

    def get(self, userId, id, format=None, metadataHeaders=None):
        return _Req(lambda: self.g.msgs[id])

    def send(self, userId, body):
        def run():
            parsed = email.message_from_bytes(base64.urlsafe_b64decode(body["raw"]))
            self.g.sent.append({"threadId": body.get("threadId"), "msg": parsed})
            mid = self.g.add(body["threadId"], ME, datetime.now(tz=timezone.utc),
                             subject=parsed["subject"], to=parsed["to"])
            return {"id": mid, "threadId": body["threadId"]}
        return _Req(run)


# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sent_log, "SENT_LOG_FILE", tmp_path / "sent_log.json")
    monkeypatch.setattr(followups, "STOP_LIST_FILE", tmp_path / "do_not_followup.txt")


@pytest.fixture
def gmail():
    return FakeGmail()


def make_contact(g, name="Chris Smith", to=CONTACT, subject="Your Citi FIG move", followups_sent=0):
    """An original sent Monday (plus any follow-ups already sent) and its sent_log record."""
    tid = f"t-{to}"
    mid = g.add(tid, ME, MONDAY, subject=subject, to=to)
    rec = sent_log.new_record({"to": to, "name": name, "subject": subject,
                               "body": f"Good Morning {name.split()[0]},\n\nLine 1"}, tid, mid, MONDAY)
    for n in range(1, followups_sent + 1):
        when = datetime(2026, 10, 5 + n, 14, 0, tzinfo=timezone.utc)
        fid = g.add(tid, ME, when, subject="Re: " + subject, to=to)
        rec["followups"].append({"n": n, "msg_id": fid, "sent_at": when.isoformat()})
    return rec


def quiet_console():
    return Console(file=io.StringIO())


def save(*recs):
    sent_log.save(list(recs))


PROMPTS = []


def run(g, today, hold="k", confirm="send", on_send_prompt=None, limit=None):
    """Run --followups, answering each HOLD prompt with `hold` and the final confirm
    prompt with `confirm`. Every prompt asked is recorded in PROMPTS. Returns sends."""
    PROMPTS.clear()

    def ask(prompt, choices=None, default=None):
        if "(r)elease" in prompt:
            PROMPTS.append("hold")
            return hold
        if "Type 'send'" in prompt:
            PROMPTS.append("confirm")
            if on_send_prompt:
                on_send_prompt()
            return confirm
        raise AssertionError(f"unexpected prompt: {prompt}")

    return followups.run_followups(quiet_console(), limit=limit, service=g, today=today,
                                   ask=ask, sleep=lambda s: None)


def body_of(sent):
    for part in sent["msg"].walk():
        if part.get_content_type() == "text/plain":
            return part.get_payload(decode=True).decode("utf-8")
    raise AssertionError("no text/plain part")


AFTER_SEND = datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)


# --- Cases that must NOT send ------------------------------------------------

def test_reply_in_thread_blocks(gmail):
    rec = make_contact(gmail)
    gmail.add(rec["thread_id"], CONTACT, AFTER_SEND, subject="Re: Your Citi FIG move")
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []
    assert sent_log.load()[0]["reply"]["how"] == "thread"


def test_reply_in_new_thread_with_other_subject_blocks(gmail):
    rec = make_contact(gmail)
    gmail.add("other-thread", CONTACT, AFTER_SEND, subject="Coffee next week?")
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []
    assert sent_log.load()[0]["reply"]["how"] == "mailbox"


def test_reply_arriving_between_preview_and_send_blocks(gmail):
    rec = make_contact(gmail)
    save(rec)
    inject = lambda: gmail.add(rec["thread_id"], CONTACT, datetime.now(tz=timezone.utc), subject="Re: x")
    assert run(gmail, TUESDAY, on_send_prompt=inject) == 0 and gmail.sent == []


def test_auto_reply_is_held_and_not_sent(gmail):
    rec = make_contact(gmail)
    gmail.add(rec["thread_id"], CONTACT, AFTER_SEND, subject="Automatic reply: Your Citi FIG move",
              extra_headers={"Auto-Submitted": "auto-replied"})
    save(rec)
    assert run(gmail, TUESDAY, hold="k") == 0 and gmail.sent == []
    assert PROMPTS == ["hold"]
    saved = sent_log.load()[0]
    assert saved["auto_reply_at"] and not saved["reply"]  # not counted as a reply


def test_bounce_blocks(gmail):
    rec = make_contact(gmail)
    gmail.add(rec["thread_id"], "mailer-daemon@googlemail.com", AFTER_SEND,
              subject="Delivery Status Notification (Failure)", text=CONTACT)
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []
    assert sent_log.load()[0]["bounced_at"]


def test_colleague_mentioning_contact_is_held(gmail):
    rec = make_contact(gmail)
    gmail.add("t-assistant", "jane.doe@bigbank.com", AFTER_SEND, subject="Re: meeting",
              text="Chris Smith asked me to set up time")
    save(rec)
    assert run(gmail, TUESDAY, hold="k") == 0 and gmail.sent == []
    assert PROMPTS == ["hold"]


def test_same_name_from_other_address_is_held(gmail):
    rec = make_contact(gmail)
    gmail.add("t-personal", "chris.smith.88@gmail.com", AFTER_SEND, name="Chris Smith", subject="hey")
    save(rec)
    assert run(gmail, TUESDAY, hold="k") == 0 and gmail.sent == []
    assert PROMPTS == ["hold"]


def test_stop_list_blocks(gmail):
    rec = make_contact(gmail)
    save(rec)
    followups.STOP_LIST_FILE.write_text(CONTACT.upper() + "\n", encoding="utf-8")
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


def test_mark_replied_blocks_and_counts(gmail):
    rec = make_contact(gmail)
    save(rec)
    followups.mark_replied(CONTACT, quiet_console())
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []
    assert sent_log.load()[0]["reply"]["how"] == "manual"


def test_gmail_error_blocks(gmail):
    rec = make_contact(gmail)
    save(rec)
    gmail.fail_threads = True
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


def test_missing_thread_blocks(gmail):
    rec = make_contact(gmail)
    rec["thread_id"] = "t-deleted"
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


def test_my_own_reply_in_thread_blocks(gmail):
    rec = make_contact(gmail)
    gmail.add(rec["thread_id"], ME, AFTER_SEND, subject="Re: Your Citi FIG move")
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


def test_my_draft_in_thread_blocks(gmail):
    rec = make_contact(gmail)
    gmail.add(rec["thread_id"], ME, AFTER_SEND, labels=("DRAFT",))
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


def test_separate_email_from_me_blocks(gmail):
    rec = make_contact(gmail)
    gmail.add("t-separate", ME, AFTER_SEND, subject="Following up on our call", to=CONTACT)
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


def test_not_confirming_sends_nothing(gmail):
    save(make_contact(gmail))
    assert run(gmail, TUESDAY, confirm="no") == 0 and gmail.sent == []


def test_running_twice_same_day_sends_once(gmail):
    save(make_contact(gmail))
    assert run(gmail, TUESDAY) == 1
    assert run(gmail, TUESDAY) == 0
    assert len(gmail.sent) == 1


def test_never_a_third_followup(gmail):
    rec = make_contact(gmail, followups_sent=2)
    save(rec)
    assert followups.due_followup(rec, date(2026, 10, 12)) is None
    assert run(gmail, date(2026, 10, 12)) == 0 and gmail.sent == []


def test_backfilled_records_are_never_followed_up(gmail):
    rec = make_contact(gmail)
    rec["source"] = "backfill"
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


# --- Timing ------------------------------------------------------------------

def test_schedule_monday_tuesday_thursday(gmail):
    rec = make_contact(gmail)
    assert followups.due_followup(rec, date(2026, 10, 5)) is None   # Monday: same day
    assert followups.due_followup(rec, TUESDAY) == 1
    rec = make_contact(gmail, to="b@bigbank.com", followups_sent=1)  # #1 went out Tuesday
    assert followups.due_followup(rec, WEDNESDAY) is None
    assert followups.due_followup(rec, THURSDAY) == 2
    assert followups.due_followup(make_contact(gmail, to="c@x.com"), date(2026, 10, 13)) is None  # stale


# --- Cases that SHOULD send --------------------------------------------------

def test_silent_contact_gets_exact_followup_1_threaded(gmail):
    rec = make_contact(gmail)
    save(rec)
    assert run(gmail, TUESDAY) == 1
    s = gmail.sent[0]
    assert s["threadId"] == rec["thread_id"]
    assert s["msg"]["To"] == CONTACT
    assert s["msg"]["Subject"] == "Re: Your Citi FIG move"
    assert s["msg"]["In-Reply-To"] == f"<{rec['original_msg_id']}@mail>"
    assert body_of(s) == followups.TEMPLATES[1].format(first_name="Chris")
    assert not any(p.get_content_type() == "application/pdf" for p in s["msg"].walk())
    assert sent_log.load()[0]["followups"][0]["n"] == 1


def test_silent_contact_gets_followup_2_on_thursday(gmail):
    rec = make_contact(gmail, followups_sent=1)
    save(rec)
    assert run(gmail, THURSDAY) == 1
    assert body_of(gmail.sent[0]) == followups.TEMPLATES[2].format(first_name="Chris")
    assert gmail.sent[0]["msg"]["In-Reply-To"] == f"<{rec['followups'][0]['msg_id']}@mail>"


def test_released_hold_sends(gmail):
    rec = make_contact(gmail)
    gmail.add(rec["thread_id"], CONTACT, AFTER_SEND, subject="Out of office")
    save(rec)
    assert run(gmail, TUESDAY, hold="r") == 1


def test_greeting_name_is_used(gmail):
    rec = make_contact(gmail, name="Christopher Smith")
    rec["first_name"] = sent_log.first_name_for("Good Morning Chris,\n\nLine 1", "Christopher Smith")
    save(rec)
    assert run(gmail, TUESDAY) == 1
    assert body_of(gmail.sent[0]).startswith("Hi Chris,\n")


# --- Stats -------------------------------------------------------------------

def test_reply_credited_to_the_email_before_it(gmail):
    rec = make_contact(gmail, followups_sent=1)
    reply_at = datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc)
    gmail.add(rec["thread_id"], CONTACT, reply_at, subject="Re: x")
    check = followups.check_contact(gmail, rec, set(), thorough=False)
    followups.apply_detection(rec, check)
    assert rec["reply"]["after"] == "followup1"


def test_summary_rates_exclude_bounces(gmail):
    a = make_contact(gmail, to="a@x.com")
    a["reply"] = {"at": "2026-10-05T18:00:00+00:00", "after": "original", "how": "thread"}
    b = make_contact(gmail, to="b@x.com", followups_sent=1)
    b["reply"] = {"at": "2026-10-07T18:00:00+00:00", "after": "followup1", "how": "thread"}
    c = make_contact(gmail, to="c@x.com", followups_sent=2)
    d = make_contact(gmail, to="d@x.com")
    d["bounced_at"] = "2026-10-05T15:00:00+00:00"
    s = stats.summarize([a, b, c, d])
    assert s["contacted"] == 3 and s["replied"] == 2 and s["reply_rate"] == "67%"
    assert s["to_original"] == "1/3 33%"
    assert s["after_fu1"] == "1/2 50%"
    assert s["after_fu2"] == "0/1 0%"
    assert s["bounced"] == 1


def test_limit_zero_sends_nothing(gmail):
    save(make_contact(gmail))
    sent = followups.run_followups(quiet_console(), limit=0, service=gmail, today=TUESDAY,
                                   ask=lambda *a, **k: "send", sleep=lambda s: None)
    assert sent == 0 and gmail.sent == []


# --- Review findings: false positives/negatives in the checks ----------------

def test_reply_whose_subject_has_vacation_words_counts_as_reply(gmail):
    rec = make_contact(gmail, subject="Your vacation rental coverage")
    gmail.add(rec["thread_id"], CONTACT, AFTER_SEND, subject="Re: Your vacation rental coverage")
    save(rec)
    assert run(gmail, TUESDAY, hold="r") == 0 and gmail.sent == []
    assert PROMPTS == [] and sent_log.load()[0]["reply"]


def test_delay_notice_is_held_not_bounced(gmail):
    rec = make_contact(gmail)
    gmail.add(rec["thread_id"], "mailer-daemon@googlemail.com", AFTER_SEND,
              subject="Delivery Status Notification (Delay)", text=CONTACT)
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []
    assert PROMPTS == ["hold"] and not sent_log.load()[0]["bounced_at"]


def test_bounce_found_only_by_mailbox_search_blocks(gmail):
    rec = make_contact(gmail)
    gmail.add("t-bounce", "mailer-daemon@googlemail.com", AFTER_SEND,
              subject="Delivery Status Notification (Failure)", text=f"Address not found: {CONTACT}")
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []
    assert sent_log.load()[0]["bounced_at"]


def test_reply_from_unquoted_comma_display_name_blocks(gmail):
    rec = make_contact(gmail)
    rec_from = gmail.add("t-new", CONTACT, AFTER_SEND, subject="hi")
    hdrs = gmail.msgs[rec_from]["payload"]["headers"]
    hdrs[0]["value"] = f"Smith, Chris <{CONTACT}>"
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []
    assert sent_log.load()[0]["reply"]


def test_mail_from_contact_before_the_original_is_not_a_reply(gmail):
    rec = make_contact(gmail)
    gmail.add("t-earlier", CONTACT, datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc), subject="old")
    save(rec)
    assert run(gmail, TUESDAY) == 1
    assert sent_log.load()[0]["reply"] is None


def test_colleague_check_uses_surname_not_suffix(gmail):
    assert followups.name_parts("Chris Smith, CFA") == ("Chris Smith", "Smith")
    assert followups.name_parts("Michael N.") == ("", "")
    rec = make_contact(gmail, name="Chris Smith Jr.")
    gmail.add("t-assistant", "jane.doe@bigbank.com", AFTER_SEND, text="Smith asked me to reply")
    save(rec)
    assert run(gmail, TUESDAY) == 0 and PROMPTS == ["hold"]


def test_stop_list_survives_bom_comments_and_names(gmail):
    rec = make_contact(gmail)
    save(rec)
    followups.STOP_LIST_FILE.write_bytes(
        "\ufeffother@x.com\nChris Smith <Chris.Smith@bigbank.com>  # called me 10/6\n".encode("utf-8"))
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


def test_stop_list_utf16(gmail):
    rec = make_contact(gmail)
    save(rec)
    followups.STOP_LIST_FILE.write_bytes(f"{CONTACT}\r\n".encode("utf-16"))
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


def test_mark_replied_without_trailing_newline_keeps_both(gmail):
    followups.STOP_LIST_FILE.write_text("a@x.com", encoding="utf-8")
    assert followups.mark_replied("Chris <b@y.com>", quiet_console())
    assert {"a@x.com", "b@y.com"} <= followups.load_stop_list()
    assert not followups.mark_replied("not an address", quiet_console())


def test_original_missing_from_thread_blocks(gmail):
    rec = make_contact(gmail)
    rec["original_msg_id"] = "m-gone"
    save(rec)
    assert run(gmail, TUESDAY) == 0 and gmail.sent == []


def test_released_hold_not_sent_if_a_new_reason_appears(gmail):
    rec = make_contact(gmail)
    gmail.add(rec["thread_id"], CONTACT, AFTER_SEND, subject="Out of office")
    save(rec)
    inject = lambda: gmail.add("t-assistant", "jane.doe@bigbank.com", datetime.now(tz=timezone.utc),
                               text="Smith asked me to reply")
    assert run(gmail, TUESDAY, hold="r", on_send_prompt=inject) == 0 and gmail.sent == []


def test_no_followups_on_weekends_or_too_soon(gmail):
    rec = make_contact(gmail)
    assert followups.due_followup(rec, date(2026, 10, 10)) is None   # Saturday
    late = sent_log.new_record({"to": "z@x.com", "name": "Z Q", "subject": "s", "body": ""},
                               "t", "m", datetime(2026, 10, 6, 3, 30, tzinfo=timezone.utc))  # Mon 11:30 PM EDT
    eight_am_tue = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    assert followups.due_followup(late, TUESDAY, eight_am_tue) is None
    assert followups.due_followup(late, TUESDAY, eight_am_tue.replace(hour=20)) == 1


def test_limit_counts_only_ready_ones_and_reports(gmail):
    save(make_contact(gmail, to="a@bigbank.com"), make_contact(gmail, to="b@bigbank.com"))
    assert run(gmail, TUESDAY, limit=1) == 1
