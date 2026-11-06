"""Native queue dispatch safety, with real durable files and a read-only Reason DB."""
import json
from contextlib import closing
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wake

UUID = "01a16830-f72b-7e23-a454-0ed7064fd15e"
ADDRESS = "pat/app"


class QueueWakeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.db = self.home / "network.db"
        self.connection = sqlite3.connect(self.db)
        self.addCleanup(self.connection.close)
        self.connection.executescript("""
            create table sessions (name text, key text, agent text, cwd text);
            create table messages (id text primary key, recipient text, wake int, held int, read_at int,
                                   sent_at int default 1);
        """)
        self.connection.execute("insert into sessions values (?, ?, ?, ?)",
                                ("app", "codex:" + UUID, "codex", str(self.home)))
        self.message("m1")
        self.message("m2")
        self.who = {"person": "pat", "machine": "local", "sessions": [
            {"address": ADDRESS, "machine": "local", "status": "idle"}]}
        self.calls = []
        self.enterContext(mock.patch("wake.STATE", self.home))
        self.stack = self.enterContext(mock.patch("wake.held", return_value=True))
        self.enterContext(mock.patch("wake.find_codex", return_value=sys.executable))
        self.enterContext(mock.patch("wake.spawn", side_effect=AssertionError("no second writer")))
        self.runner = self.enterContext(mock.patch("wake.subprocess.run", side_effect=self.run_command))
        self.w = self.waker()

    def waker(self):
        return wake.Waker(self.rows, self.home)

    def rows(self, sql, params=()):
        with closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute(sql, params)]

    def message(self, id, wake_=1, held=0):
        self.connection.execute("insert into messages (id, recipient, wake, held, read_at) values (?, ?, ?, ?, null)",
                                (id, ADDRESS, wake_, held))
        self.connection.commit()

    def read(self):
        self.connection.execute("update messages set read_at=123")
        self.connection.commit()

    def journal(self):
        return json.loads(self.w.queue_path.read_text(encoding="utf-8"))

    def run_command(self, args, **kwargs):
        self.assertNotIn("shell", kwargs)
        self.assertNotIn("--resume", args)
        self.assertNotIn("exec", args)
        if args[-1] == "--help":
            return subprocess.CompletedProcess(args, 0, b"--thread --message", b"")
        self.assertEqual(args, [sys.executable, "queue", "--thread", UUID, "--message", wake.WAKE_PROMPT])
        b = self.journal()["batches"][-1]
        self.assertEqual(b["status"], "intent")  # durable intent already on disk
        self.assertEqual(set(b["ids"]), {r["id"] for r in self.rows("select id from messages where read_at is null")})
        self.calls.append(args)
        return subprocess.CompletedProcess(args, 0, b"accepted-receipt", b"")

    def test_batch_receipt_is_not_read_and_no_replay_on_manual_or_restart(self):
        self.assertEqual(self.w.wake(ADDRESS, self.who)["status"], "queued")
        self.assertEqual(self.w.view()[ADDRESS]["status"], "queued")
        self.assertEqual(self.journal()["batches"][0]["receipt"], "accepted-receipt")
        again = self.waker()
        self.message("m3")
        for w in (self.w, again):
            with self.assertRaises(wake.WakeError):
                w.wake(ADDRESS, self.who)
            w.auto([ADDRESS], self.who)
        self.assertEqual(len(self.calls), 1)
        self.read()
        self.assertEqual(again.view()[ADDRESS]["status"], "done")
        self.message("m4")
        again.wake(ADDRESS, self.who)
        self.assertEqual(self.journal()["batches"][-1]["ids"], ["m4"])
        self.assertEqual(len(self.calls), 2)

    def test_completed_ids_cannot_be_enqueued_again_even_if_marked_unread(self):
        self.w.wake(ADDRESS, self.who)
        self.read()
        self.w.view()
        self.connection.execute("update messages set read_at=null")
        self.connection.commit()
        with self.assertRaises(wake.WakeError):
            self.waker().wake(ADDRESS, self.who)
        self.assertEqual(len(self.calls), 1)

    def test_busy_and_remote_defer_without_intent_or_dispatch(self):
        for session in ({"status": "busy", "machine": "local"}, {"status": "idle", "machine": "remote"},
                        {"status": "offline", "machine": "local"}):
            who = {**self.who, "sessions": [{"address": ADDRESS, **session}]}
            self.w.auto([ADDRESS], who)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.w.queue_path.exists())

    def test_timeout_and_failure_are_held_across_restart_without_resend(self):
        for outcome in (subprocess.TimeoutExpired("queue", 20), OSError("crash"),
                        subprocess.CompletedProcess([], 1, b"", b"error")):
            with self.subTest(outcome=outcome):
                with mock.patch("wake.Waker.supports_queue"), mock.patch("wake.subprocess.run", side_effect=[outcome]):
                    self.assertEqual(self.w.wake(ADDRESS, self.who)["status"], "held")
                again = self.waker()
                again.auto([ADDRESS], self.who)
                with self.assertRaises(wake.WakeError):
                    again.wake(ADDRESS, self.who)
                self.read()
                self.assertEqual(again.view()[ADDRESS]["status"], "done")
                self.message("next" + str(len(self.journal()["batches"])))

    def test_crash_after_intent_before_receipt_is_held(self):
        with mock.patch.object(self.w, "supports_queue"), mock.patch("wake.subprocess.run", side_effect=SystemExit):
            with self.assertRaises(SystemExit):
                self.w.wake(ADDRESS, self.who)
        self.assertEqual(self.journal()["batches"][0]["status"], "intent")
        again = self.waker()
        self.assertEqual(again.view()[ADDRESS]["status"], "held")
        again.auto([ADDRESS], self.who)
        with self.assertRaises(wake.WakeError):
            again.wake(ADDRESS, self.who)

    def test_receipt_write_failure_leaves_intent_and_prevents_second_dispatch(self):
        actual = wake.atomic_json
        def persist(path, data, **kwargs):
            if data["batches"][-1]["status"] == "queued":
                raise OSError("disk failed after enqueue")
            actual(path, data, **kwargs)
        with mock.patch("wake.atomic_json", side_effect=persist):
            with self.assertRaises(OSError):
                self.w.wake(ADDRESS, self.who)
        self.assertEqual(self.waker().view()[ADDRESS]["status"], "held")
        with self.assertRaises(wake.WakeError):
            self.w.wake(ADDRESS, self.who)
        self.assertEqual(len(self.calls), 1)

    def test_intent_write_failure_and_corrupt_journal_never_dispatch(self):
        with mock.patch("wake.atomic_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.w.wake(ADDRESS, self.who)
        self.assertEqual(self.calls, [])
        self.w.queue_path.write_text("{corrupt", encoding="utf-8")
        with self.assertRaises(wake.WakeError):
            self.w.wake(ADDRESS, self.who)
        self.assertEqual(self.calls, [])

    def test_unsupported_queue_and_batch_shims_are_explicit_errors(self):
        for rc in (0, 2):  # old CLI may print global help successfully without supporting queue
            self.w.queue_support.clear()
            with mock.patch("wake.subprocess.run", return_value=subprocess.CompletedProcess([], rc, b"", b"")):
                with self.assertRaisesRegex(wake.WakeError, "does not support native queue"):
                    self.w.wake(ADDRESS, self.who)
        with self.assertRaisesRegex(wake.WakeError, "native Codex executable"):
            self.w.supports_queue("codex.cmd")
        self.assertFalse(self.w.queue_path.exists())

    def test_queued_timeout_and_missing_original_row_do_not_prove_read(self):
        self.w.wake(ADDRESS, self.who)
        self.connection.execute("delete from messages where id='m1'")
        self.connection.execute("update messages set read_at=123")
        self.connection.commit()
        with mock.patch("wake.TIMEOUT", -1):
            self.assertEqual(self.w.view()[ADDRESS]["status"], "held")
        with mock.patch("wake.held", return_value=False):
            self.message("new")
            with self.assertRaises(wake.WakeError):
                self.w.wake(ADDRESS, self.who)  # cannot switch to exec and duplicate delivery

    def test_opt_in_gap_budget_and_restart(self):
        self.w.auto([], self.who)
        self.assertEqual(self.calls, [])
        with mock.patch("wake.AUTO_GAP", 0), mock.patch("wake.AUTO_BUDGET", 2):
            for i in range(3):
                self.w.auto([ADDRESS], self.who)
                self.read()
                self.w = self.waker()
                self.message("new" + str(i))
            self.assertEqual(len(self.calls), 2)
            self.assertIn("limitUntil", self.w.view()[ADDRESS])

    def test_auto_gap_and_new_fyi_do_not_trigger_again(self):
        self.w.auto([ADDRESS], self.who)
        self.read()
        self.w.view()
        self.message("fyi", wake_=0)
        with mock.patch("wake.AUTO_GAP", 0):
            self.w.auto([ADDRESS], self.who)
        self.assertEqual(len(self.calls), 1)
        self.message("new")
        self.waker().auto([ADDRESS], self.who)
        self.assertEqual(len(self.calls), 1)  # gap survives restart

    def test_two_wakers_serialize_dispatch(self):
        import threading
        other = self.waker()
        errors = []
        def dispatch(w):
            try:
                w.wake(ADDRESS, self.who)
            except wake.WakeError as e:
                errors.append(e.code)
        threads = [threading.Thread(target=dispatch, args=(w,)) for w in (self.w, other)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
            self.assertFalse(t.is_alive())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(errors, [409])

    def test_partial_read_keeps_one_outstanding_and_more_than_sql_limit_ids(self):
        for i in range(1000):
            self.message("bulk" + str(i))
        self.w.wake(ADDRESS, self.who)
        self.connection.execute("update messages set read_at=123 where id != 'm2'")
        self.connection.commit()
        self.assertEqual(self.w.view()[ADDRESS]["status"], "queued")
        self.read()
        self.assertEqual(self.w.view()[ADDRESS]["status"], "done")
        self.assertEqual(len(self.journal()["batches"][0]["ids"]), 1002)

    def test_unsupported_auto_queue_is_visible_and_does_not_poll_models(self):
        with mock.patch("wake.subprocess.run", return_value=subprocess.CompletedProcess([], 2, b"", b"")) as run:
            self.w.auto([ADDRESS], self.who)
            self.w.auto([ADDRESS], self.who)
        self.assertEqual(run.call_count, 1)  # only the non-model capability probe
        self.assertEqual(self.w.view()[ADDRESS]["status"], "failed")
        self.assertIn("does not support native queue", self.w.view()[ADDRESS]["error"])
        self.assertFalse(self.w.queue_path.exists())

    def test_completed_queue_history_cannot_hide_running_legacy_wake(self):
        self.w.wake(ADDRESS, self.who)
        self.read()
        at = self.journal()["batches"][0]["at"]
        self.w.state[ADDRESS] = {"status": "running", "at": at}
        self.assertEqual(self.w.view()[ADDRESS]["status"], "running")

    def test_corrupt_journal_preserves_history_and_leaves_views_available(self):
        self.w.wake(ADDRESS, self.who)
        original = self.w.queue_path.read_bytes()
        damaged = original[:-5]
        self.w.queue_path.write_bytes(damaged)
        again = self.waker()  # server construction must still succeed
        self.assertIsInstance(again.view(), dict)
        self.assertIn("Cannot read queue dispatch history", again.queue_error)
        again.auto([ADDRESS], self.who)
        with self.assertRaises(wake.WakeError):
            again.wake(ADDRESS, self.who)
        self.assertEqual(again.queue_path.read_bytes(), damaged)
        self.assertEqual(len(self.calls), 1)
        again.queue_path.write_bytes(original)  # fixture repair preserves every dispatched ID
        self.assertEqual(again.view()[ADDRESS]["status"], "queued")
        self.assertEqual(again.queue_error, "")
        with self.assertRaises(wake.WakeError):
            again.wake(ADDRESS, self.who)
        self.assertEqual(len(self.calls), 1)

    def test_unreadable_journal_leaves_views_available_and_blocks_dispatch(self):
        with mock.patch.object(self.w, "queue_data", side_effect=PermissionError("denied")):
            self.assertIsInstance(self.w.view(), dict)
            self.assertEqual(self.w.queue_error, "denied")
            self.w.auto([ADDRESS], self.who)
            with self.assertRaises(wake.WakeError):
                self.w.wake(ADDRESS, self.who)
        self.assertFalse(self.w.queue_path.exists())
        self.assertEqual(self.calls, [])

    def seed_other_batches(self, status):
        import time
        data = {"version": 1, "batches": [
            {"address": "pat/other" + str(i), "thread": UUID, "ids": ["other-id" + str(i)],
             "status": status, "at": int(time.time() * 1000), "auto": False}
            for i in range(wake.MAX_RUNNING)]}
        wake.atomic_json(self.w.queue_path, data, durable=True)
        self.w = self.waker()  # reproduce persisted holds/slots after server restart

    def test_held_batches_block_only_their_addresses_not_global_capacity(self):
        self.seed_other_batches("held")
        self.assertEqual(self.w.wake(ADDRESS, self.who)["status"], "queued")
        self.assertEqual(len(self.calls), 1)
        self.read()
        self.w.view()
        self.message("new")
        with mock.patch("wake.held", return_value=False), mock.patch("wake.spawn", return_value=1) as spawn, \
                mock.patch("wake.started_at", return_value=None), mock.patch("wake.threading.Thread"):
            self.assertEqual(self.w.wake(ADDRESS, self.who)["status"], "running")
            self.assertIn("exec", spawn.call_args.args[0])
        self.assertEqual(len([s for s in self.w.view().values() if s["status"] == "held"]), wake.MAX_RUNNING)

    def test_active_queued_batches_still_limit_global_capacity(self):
        self.seed_other_batches("queued")
        for is_held in (True, False):
            with mock.patch("wake.held", return_value=is_held):
                with self.assertRaises(wake.WakeError) as error:
                    self.w.wake(ADDRESS, self.who)
                self.assertEqual(error.exception.code, 429)
        self.assertEqual(self.calls, [])

    def test_completed_unread_id_with_new_id_blocks_every_queue_and_exec_path(self):
        self.w.wake(ADDRESS, self.who)
        self.read()
        self.assertEqual(self.w.view()[ADDRESS]["status"], "done")
        self.connection.execute("update messages set read_at=null where id='m1'")
        self.connection.commit()
        self.message("new")
        for w in (self.w, self.waker()):
            for is_held in (True, False):
                with mock.patch("wake.held", return_value=is_held), mock.patch("wake.AUTO_GAP", 0):
                    with self.assertRaises(wake.WakeError) as error:
                        w.wake(ADDRESS, self.who)
                    self.assertEqual(error.exception.code, 409)
                    w.auto([ADDRESS], self.who)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.journal()["batches"]), 1)


if __name__ == "__main__":
    unittest.main()
