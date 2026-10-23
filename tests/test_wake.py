"""Who may be woken, with a fake database: python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("REASON_CHAT_HOME", tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wake  # noqa: E402

FOLDER = tempfile.mkdtemp()
UUID = "01a16830-f72b-7e23-a454-0ed7064fd15e"
ROWS = {
    "sleepy-codex": {"key": f"codex:{UUID}", "agent": "codex", "cwd": FOLDER},
    "busy-codex": {"key": f"codex:{UUID}", "agent": "codex", "cwd": FOLDER},
    "a-claude": {"key": "claude-code:2c4ffb8d-abef-4d1f-bb53-6d2398c43f0a", "agent": "claude-code", "cwd": FOLDER},
    "moved-codex": {"key": f"codex:{UUID}", "agent": "codex", "cwd": os.path.join(FOLDER, "gone")},
    "read-codex": {"key": f"codex:{UUID}", "agent": "codex", "cwd": FOLDER},
    "odd-codex": {"key": "codex:../../etc", "agent": "codex", "cwd": FOLDER},
}
UNREAD = {"pat/sleepy-codex": 2, "pat/busy-codex": 1, "pat/a-claude": 1, "pat/moved-codex": 1, "pat/odd-codex": 1}
WHO = {"person": "pat", "machine": "box", "sessions": [
    {"address": "pat/sleepy-codex", "machine": "box", "status": "offline"},
    {"address": "pat/busy-codex", "machine": "box", "status": "busy"},
    {"address": "pat/far-codex", "machine": "other", "status": "idle"},
]}


def db_rows(sql, params=()):
    if "from sessions" in sql:
        row = ROWS.get(params[0])
        return [row] if row else []
    return [{"n": UNREAD.get(params[0], 0)}]


class WakeTest(unittest.TestCase):
    def setUp(self):
        self.w = wake.Waker(db_rows)

    def bad(self, address, code=400):
        with self.assertRaises(wake.WakeError) as e:
            self.w.target(address, WHO)
        self.assertEqual(e.exception.code, code, str(e.exception))

    def test_ok(self):
        self.assertEqual(self.w.target("pat/sleepy-codex", WHO), (UUID, str(Path(FOLDER))))

    def test_refusals(self):
        self.bad("kim/sleepy-codex")  # someone else's
        self.bad("pat/far-codex")  # another computer
        self.bad("pat/busy-codex", 409)
        self.bad("pat/unknown-codex", 404)
        self.bad("pat/a-claude")  # not a Codex thread
        self.bad("pat/moved-codex")  # folder gone
        self.bad("pat/read-codex")  # nothing unread
        self.bad("pat/odd-codex")  # key is not a uuid
        for junk in (None, 5, "nobody", "a/b/c", "pat/../x"):
            self.bad(junk)

    def test_one_wake_at_a_time(self):
        self.w.state["pat/sleepy-codex"] = {"status": "running", "at": 0, "error": ""}
        old = wake.find_codex
        wake.find_codex = lambda: sys.executable
        try:
            with self.assertRaises(wake.WakeError) as e:
                self.w.wake("pat/sleepy-codex", WHO)
            self.assertEqual(e.exception.code, 409)
        finally:
            wake.find_codex = old

    def test_prompt_is_fixed(self):
        self.assertIn("check_inbox", wake.WAKE_PROMPT)
        self.assertIn("send_message", wake.WAKE_PROMPT)


if __name__ == "__main__":
    unittest.main()
