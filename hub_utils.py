"""Shared utilities for contacts.json."""
from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path

from config import data_path, resolve_data_file

# Writes always target the real file; reads fall back to the committed example.
CONTACTS_FILE = Path(data_path("contacts.json"))


def load() -> dict:
    source = Path(resolve_data_file("contacts.json"))
    if source.exists():
        return json.loads(source.read_text(encoding="utf-8"))
    return {"contacts": [], "meta": {"created": datetime.now().isoformat(), "version": "1.0"}}


def save(data: dict):
    data.setdefault("meta", {})["last_updated"] = datetime.now().isoformat()
    CONTACTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONTACTS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def url_to_id(url: str) -> str:
    handle = url.rstrip("/").split("/")[-1]
    return re.sub(r"[^a-z0-9-]", "-", handle.lower()).strip("-")


def get_contact(cid: str) -> dict | None:
    for c in load()["contacts"]:
        if c["id"] == cid:
            return c
    return None


def update_contact(cid: str, updates: dict) -> dict | None:
    data = load()
    for c in data["contacts"]:
        if c["id"] == cid:
            c.update(updates)
            c["last_updated"] = datetime.now().isoformat()
            save(data)
            return c
    return None


def upsert_contact(contact: dict):
    data = load()
    contact["last_updated"] = datetime.now().isoformat()
    for i, c in enumerate(data["contacts"]):
        if c["id"] == contact["id"]:
            data["contacts"][i] = contact
            save(data)
            return
    data["contacts"].append(contact)
    save(data)


def mark_sent(linkedin_url: str, to: str, subject: str):
    cid = url_to_id(linkedin_url)
    update_contact(cid, {
        "status": "sent",
        "email": to,
        "subject": subject,
        "sent_at": datetime.now().isoformat(),
    })


def mark_queued(linkedin_url: str, to: str, subject: str, scheduled_at: str):
    cid = url_to_id(linkedin_url)
    update_contact(cid, {
        "status": "queued",
        "email": to,
        "subject": subject,
        "scheduled_at": scheduled_at,
    })


def mark_drafted(linkedin_url: str, to: str, subject: str):
    cid = url_to_id(linkedin_url)
    update_contact(cid, {
        "status": "drafted",
        "email": to,
        "subject": subject,
    })
