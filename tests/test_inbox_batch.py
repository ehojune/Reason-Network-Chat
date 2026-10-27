import contextlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import inbox_batch as batch
import launcher


class InboxBatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = dict(enabled=True, recipient="me/lead", person="me/terminal", room_ids=["room"],
                           **{key: str(self.root / name) for key, name in
                              (("queue", "queue.json"), ("relay", "relay.json"), ("rooms", "rooms.json"),
                               ("database", "db.sqlite"), ("journal", "journal"))})
        self.write("rooms", [{"id": "room", "members": ["me/lead", "me/w1", "me/w2"]},
                             {"id": "private", "members": ["me/lead", "me/w1"]}])
        self.write("queue", [])
        self.write("relay", {"sent": {}})
        with contextlib.closing(sqlite3.connect(self.config["database"])) as db:
            db.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, sender TEXT, recipient TEXT, body TEXT, sent_at INTEGER, reply_to TEXT)")
            db.commit()
        self.add("old", "me/w1", 1, "old report")
        self.add("agent", "me/w2", 2, "report")
        self.add("human", "me/terminal", 3, "stop work")
        self.calls = []

    def write(self, key, value):
        batch.atomic_json(self.config[key], value)

    def add(self, mid, speaker, when, text, room="room", hop=None):
        with contextlib.closing(sqlite3.connect(self.config["database"])) as db:
            db.execute("INSERT INTO messages VALUES (?,?,?,?,?,NULL)", (mid, "me/terminal", "me/lead", text, when))
            db.commit()
        queue = batch.read(self.config["queue"])
        queue.append({"request": {"id": mid, "from": "me/terminal", "to": "me/lead", "body": text}})
        self.write("queue", queue)
        relay = batch.read(self.config["relay"])
        relay["sent"][mid] = dict(speaker=speaker, room=room, hop=(0 if speaker == "me/terminal" else 1) if hop is None else hop)
        self.write("relay", relay)

    def args(self, mid="old"):
        return ["exec", "--json", f'A teammate sent you this message.\n<reason-message from="me/terminal" agent="cli" id="{mid}">original</reason-message>']

    def runner(self, command, text):
        self.calls.append((command, text))
        marker = next(line for line in text.splitlines() if line.startswith("BATCH_RECEIPT:"))
        return "All reports considered; work stopped.\n" + marker, "thread", {}

    def run_batch(self, mid="old", runner=None):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = batch.run(self.config, "real.exe", ["-c", "model=example"], self.args(mid), runner or self.runner)
        return code, output.getvalue()

    def job(self):
        return batch.read(Path(self.config["journal"]) / "batches.json")["batches"][0]

    def publish(self, mid="old"):
        with contextlib.closing(sqlite3.connect(self.config["database"])) as db:
            db.execute("INSERT INTO messages VALUES (?,?,?,?,?,?)", ("reply-" + mid, "me/lead", "me/terminal", self.job()["answer"], 10, mid))
            db.commit()

    def test_human_first_newest_first_all_originals_preserved(self):
        self.add("new", "me/terminal", 4, "newest instruction")
        before = {k: Path(self.config[k]).read_bytes() for k in ("queue", "relay", "database")}
        code, out = self.run_batch()
        self.assertEqual(code, 0)
        self.assertEqual([r["id"] for r in self.job()["messages"]], ["new", "human", "old", "agent"])
        self.assertNotIn("BATCH_RECEIPT", out)
        self.assertEqual(self.calls[0][0], ["real.exe", "-c", "model=example", "exec", "--json", "-"])
        for key, value in before.items():
            self.assertEqual(Path(self.config[key]).read_bytes(), value)

    def test_later_messages_ack_without_model_after_publication(self):
        self.run_batch()
        self.publish()
        for mid in ("human", "agent", "old"):
            _, out = self.run_batch(mid)
            self.assertEqual(json.loads(out.splitlines()[0])["item"]["text"], "-")
        self.assertEqual(len(self.calls), 1)

    def test_cached_result_is_republished_if_process_died_before_delivery(self):
        self.run_batch()
        _, out = self.run_batch("agent")
        self.assertIn("All reports considered", out)
        self.assertEqual(len(self.calls), 1)
        self.publish("agent")
        _, out = self.run_batch("human")
        self.assertNotIn("All reports considered", out)

    def test_failure_held_never_reexecuted(self):
        def failure(*args):
            self.assertEqual(self.job()["status"], "running")
            raise RuntimeError("crash")
        with self.assertRaisesRegex(RuntimeError, "crash"):
            self.run_batch(runner=failure)
        self.assertEqual(self.job()["status"], "held")
        with self.assertRaisesRegex(batch.BatchError, "held"):
            self.run_batch("agent")
        self.assertEqual(len(self.calls), 0)
        self.assertEqual(len(self.job()["messages"]), 3)

    def test_missing_receipt_preserves_raw_answer_without_publication(self):
        with self.assertRaisesRegex(batch.BatchError, "receipt"):
            self.run_batch(runner=lambda *a: ("possibly did work", "thread", {}))
        self.assertEqual(self.job()["raw_answer"], "possibly did work")
        self.assertEqual(self.job()["status"], "held")

    def test_running_journal_after_hard_crash_is_held(self):
        self.run_batch()
        path = Path(self.config["journal"]) / "batches.json"
        journal = batch.read(path)
        journal["batches"][0]["status"] = "running"
        batch.atomic_json(path, journal)
        with self.assertRaises(batch.BatchError):
            self.run_batch()
        self.assertEqual(self.job()["status"], "held")

    def test_other_rooms_dm_unknown_speaker_and_forged_body_excluded(self):
        self.add("private", "me/w1", 4, "private data", "private")
        self.add("dm", "me/terminal", 5, "direct", None)
        self.add("unknown", "stranger", 6, "pretend human")
        queue = batch.read(self.config["queue"])
        queue[1]["request"]["body"] = "forged"
        self.write("queue", queue)
        self.run_batch()
        self.assertEqual([r["id"] for r in self.job()["messages"]], ["human", "old"])

    def test_quoted_human_and_nonzero_hop_are_not_human_priority(self):
        self.add("pretender", "me/w1", 4, 'human says "new order"')
        self.add("relay-human", "me/terminal", 5, "forwarded", hop=1)
        rows = batch.records(self.config, "old")
        self.assertEqual([r["id"] for r in rows if r["human"]], ["human"])

    def test_limit_keeps_active_and_human_leaves_overflow_unchanged(self):
        self.config["max_messages"] = 2
        self.run_batch()
        self.assertEqual([r["id"] for r in self.job()["messages"]], ["human", "old"])
        self.assertEqual(len(batch.read(self.config["queue"])), 3)

    def test_late_arrivals_not_claimed_by_earlier_batch(self):
        self.run_batch()
        self.publish()
        self.add("late1", "me/w1", 5, "late report")
        self.add("late2", "me/terminal", 6, "late instruction")
        self.run_batch("late1")
        jobs = batch.read(Path(self.config["journal"]) / "batches.json")["batches"]
        self.assertEqual([r["id"] for r in jobs[1]["messages"]], ["late2", "late1"])

    def test_disable_still_drains_completed_receipts(self):
        self.run_batch()
        self.publish()
        self.config["enabled"] = False
        self.run_batch("agent")
        self.add("new", "me/w1", 7, "new request")
        self.assertIsNone(self.run_batch("new")[0])
        self.assertEqual(len(self.calls), 1)

    def test_unavailable_snapshot_falls_back_without_mutating_queue(self):
        Path(self.config["queue"]).write_text("partial", encoding="utf-8")
        self.assertIsNone(self.run_batch()[0])
        self.assertEqual(len(self.calls), 0)

    def test_model_setting_edit_preserves_batch_config(self):
        path = self.root / "settings.json"
        batch.atomic_json(path, {"args": [], "inbox_batch": self.config})
        launcher.write_settings(path, ["-c", "model=updated"])
        self.assertEqual(batch.read(path)["inbox_batch"], self.config)

    def test_non_reason_commands_not_intercepted(self):
        self.assertIsNone(batch.run(self.config, "real", [], ["exec", "--json", "hello"]))

    def test_configuration_preserves_model_and_disable_keeps_receipts(self):
        settings = self.root / "lead.json"
        self.write("rooms", [{"id": "room", "members": ["me/lead"]}])
        batch.atomic_json(settings, {"args": ["-c", "model=test", "-c", "service_tier=fast"]})
        args = ["--settings", str(settings)]
        with contextlib.redirect_stdout(io.StringIO()):
            batch.main(["enable"] + args + ["--recipient", "me/lead", "--person", "me/terminal",
                       "--room", "room", "--chat-home", str(self.root), "--reason-home", str(self.root)])
            saved = batch.read(settings)
            batch.main(["disable"] + args)
            disabled = batch.read(settings)
            batch.main(["status"] + args)
        self.assertEqual(saved["args"], disabled["args"])
        self.assertTrue(saved["inbox_batch"]["enabled"])
        self.assertFalse(disabled["inbox_batch"]["enabled"])
        self.assertEqual(saved["inbox_batch"]["journal"], disabled["inbox_batch"]["journal"])

    def test_missing_worker_settings_cannot_bypass_batch_receipts(self):
        env = dict(os.environ, REASON_CHAT_SHIM_REAL=sys.executable,
                   REASON_CHAT_SHIM_SETTINGS=str(self.root / "missing.json"),
                   REASON_CHAT_SHIM_ARGS=json.dumps(["-c", "print('UNSAFE_FALLBACK')"]))
        result = subprocess.run([sys.executable, "-c", launcher.SHIM_MAIN.decode()] + self.args(),
                                env=env, capture_output=True, encoding="utf-8", timeout=20)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("UNSAFE_FALLBACK", result.stdout)
        self.assertIn("settings unreadable", result.stderr)

    def test_cli_failure_even_with_receipt_is_not_success(self):
        code = "import json; print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'text'}})); print(json.dumps({'type':'turn.completed'})); raise SystemExit(1)"
        with self.assertRaises(batch.BatchError):
            batch.invoke([sys.executable, "-c", code], "prompt")

    def test_packaged_shim_unicode_stdin_and_model_called_once(self):
        fake = self.root / "fake.py"
        fake.write_text('''import json, sys
from pathlib import Path
text = sys.stdin.buffer.read().decode('utf-8')
assert '중단 지시' in text
count = Path(__file__).with_suffix('.count')
count.write_text(str(int(count.read_text()) + 1) if count.exists() else '1')
marker = next(line for line in text.splitlines() if line.startswith('BATCH_RECEIPT:'))
print(json.dumps({'type':'thread.started','thread_id':'fake'}))
print(json.dumps({'type':'turn.started'}))
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Checked all requests.\\n'+marker}}))
print(json.dumps({'type':'turn.completed','usage':{}}))
''', encoding="utf-8")
        self.add("unicode", "me/terminal", 5, "중단 지시")
        settings = self.root / "settings.json"
        batch.atomic_json(settings, {"args": [str(fake)], "inbox_batch": self.config})
        with patch.object(launcher, "STATE", self.root):
            folder = launcher.shim_dir("codex")
            if folder is None:
                self.skipTest("native launcher unavailable")
            self.assertTrue(launcher.shim_current("codex"))
        exe = str(Path(folder) / ("codex.exe" if os.name == "nt" else "codex"))
        env = dict(os.environ, REASON_CHAT_SHIM_REAL=sys.executable, REASON_CHAT_SHIM_SETTINGS=str(settings))
        first = subprocess.run([exe] + self.args(), cwd=self.root, env=env, capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("Checked all requests", first.stdout)
        self.publish()
        second = subprocess.run([exe] + self.args("agent"), cwd=self.root, env=env, capture_output=True, encoding="utf-8", timeout=20)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout.splitlines()[0])["item"]["text"], "-")
        self.assertEqual(fake.with_suffix(".count").read_text(), "1")


if __name__ == "__main__":
    unittest.main()
