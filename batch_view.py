"""Read-only batch receipt index. Cached answers are history, never relay input."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path


def receipts(home, database, message_ids):
    try:
        return _receipts(home, database, message_ids)
    except sqlite3.Error:
        return {}  # Unavailable evidence must not hide an unanswered request.


def _receipts(home, database, message_ids):
    result = {}
    if not Path(database).is_file() or not message_ids:
        return result
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        for settings_path in (Path(home) / "worker-settings").glob("*.json"):
            try:
                config = json.loads(settings_path.read_text(encoding="utf-8")).get("inbox_batch")
                if not config or Path(config["database"]).resolve() != Path(database).resolve():
                    continue
                jobs = json.loads((Path(config["journal"]) / "batches.json").read_text(encoding="utf-8"))["batches"]
                for job in jobs:
                    originals = job.get("messages", [])
                    visible = [m for m in originals if m["id"] in message_ids]
                    if not visible:
                        continue
                    # A local cache cannot acknowledge an unrelated or altered DB message.
                    valid = []
                    for m in visible:
                        row = db.execute("SELECT sender,recipient,body FROM messages WHERE id=?", (m["id"],)).fetchone()
                        if row == (config["person"], config["recipient"], m["body"]):
                            valid.append(m)
                    if not valid:
                        continue
                    answer = job.get("answer") or job.get("raw_answer") or ""
                    reply = None
                    if job.get("status") == "completed" and answer:
                        for mid in job.get("publication_ids", [job["primary"]]):
                            reply = db.execute("SELECT id FROM messages WHERE reply_to=? AND sender=? AND recipient=? AND body=? LIMIT 1",
                                               (mid, config["recipient"], config["person"], answer)).fetchone()
                            if reply:
                                break
                    status = "delivered" if reply else "local_only" if job.get("status") == "completed" else "held"
                    for m in valid:
                        result[m["id"]] = {"batch": job["id"], "status": status,
                            "replyId": reply[0] if reply else None, "answer": answer,
                            "worker": config["recipient"], "at": max(x["sent_at"] for x in originals),
                            "room": m.get("room"), "error": job.get("publication_error") or job.get("error")}
            except (OSError, ValueError, KeyError, TypeError, IndexError):
                continue  # Missing evidence must not dismiss an unanswered request.
    return result
