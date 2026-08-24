#!/usr/bin/env python3
"""
Networking Hub — Flask server
Run: python3 server.py
"""

from pathlib import Path
import json
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import hub_utils

app = Flask(__name__, static_folder=str(Path(__file__).parent))
CORS(app)

HTML_FILE = Path(__file__).parent / "networking_hub.html"


@app.route("/")
def index():
    return send_from_directory(str(Path(__file__).parent), "networking_hub.html")


@app.route("/api/contacts", methods=["GET"])
def get_contacts():
    try:
        data = hub_utils.load()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/contacts/<cid>", methods=["GET"])
def get_contact(cid):
    contact = hub_utils.get_contact(cid)
    if contact is None:
        return jsonify({"error": "Contact not found"}), 404
    return jsonify(contact)


@app.route("/api/contacts/<cid>", methods=["PATCH"])
def update_contact(cid):
    ALLOWED_FIELDS = {"call_notes", "status", "email", "firm", "name", "tags"}
    body = request.get_json(silent=True) or {}
    updates = {k: v for k, v in body.items() if k in ALLOWED_FIELDS}
    if not updates:
        return jsonify({"error": "No valid fields to update"}), 400
    result = hub_utils.update_contact(cid, updates)
    if result is None:
        return jsonify({"error": "Contact not found"}), 404
    return jsonify(result)


@app.route("/api/status", methods=["GET"])
def api_status():
    try:
        data = hub_utils.load()
        contacts = data.get("contacts", [])
        counts = {}
        for c in contacts:
            s = c.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return jsonify({
            "ok": True,
            "total": len(contacts),
            "by_status": counts,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/queue", methods=["GET"])
def api_queue():
    try:
        queue_file = Path(__file__).parent / "data" / "scheduled_queue.json"
        if not queue_file.exists():
            return jsonify([])
        with open(queue_file) as f:
            queue = json.load(f)
        return jsonify(queue)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


CONNECTIONS_FILE = Path(hub_utils.resolve_data_file("personal_connections.json"))


@app.route("/api/connections", methods=["GET"])
def api_connections():
    try:
        if not CONNECTIONS_FILE.exists():
            return jsonify([])
        with open(CONNECTIONS_FILE) as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/connections/<cid>", methods=["PATCH"])
def patch_connection(cid):
    ALLOWED = {"last_called", "next_call", "notes", "status", "context"}
    body = request.get_json(silent=True) or {}
    updates = {k: v for k, v in body.items() if k in ALLOWED}
    if not updates:
        return jsonify({"error": "No valid fields"}), 400
    try:
        conns = json.loads(CONNECTIONS_FILE.read_text()) if CONNECTIONS_FILE.exists() else []
        for c in conns:
            if c["id"] == cid:
                c.update(updates)
                CONNECTIONS_FILE.write_text(json.dumps(conns, indent=2))
                return jsonify(c)
        return jsonify({"error": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print()
    print("  Networking Hub -> http://localhost:5001")
    print()
    app.run(host="0.0.0.0", port=5001, debug=False)
