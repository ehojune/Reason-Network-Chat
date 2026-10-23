"""Who may be woken, with a fake database: python -m unittest discover tests"""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("REASON_CHAT_HOME", tempfile.mkdtemp())
os.environ["CODEX_HOME"] = tempfile.mkdtemp()  # thread locks of a fake Codex, never the real one
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
    "auto-codex": {"key": f"codex:{UUID}", "agent": "codex", "cwd": FOLDER},
}
UNREAD = {"pat/sleepy-codex": 2, "pat/busy-codex": 1, "pat/a-claude": 1, "pat/moved-codex": 1, "pat/odd-codex": 1,
          "pat/auto-codex": 1}
WHO = {"person": "pat", "machine": "box", "sessions": [
    {"address": "pat/sleepy-codex", "machine": "box", "status": "offline"},
    {"address": "pat/busy-codex", "machine": "box", "status": "busy"},
    {"address": "pat/far-codex", "machine": "other", "status": "idle"},
]}


STILL_UNREAD = {"n": 0}  # what a finished wake left unread, for judge()
WAKEABLE = {}  # address -> unread messages sent without --fyi, when it differs from UNREAD


def db_rows(sql, params=()):
    if "from sessions" in sql:
        row = ROWS.get(params[0])
        return [row] if row else []
    if "sent_at <= ?" in sql:
        STILL_UNREAD["asked"] = params
        return [{"n": STILL_UNREAD["n"]}]
    if "wake = 1" in sql:  # unread messages that asked to wake it
        return [{"n": WAKEABLE.get(params[0], UNREAD.get(params[0], 0))}]
    if sql.startswith("select max(sent_at)"):
        return [{"t": 1000 if UNREAD.get(params[0], 0) else None}]
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

    def adopted(self, home, child, cutoff):
        w = wake.Waker(db_rows, home)
        w.running["pat/sleepy-codex"] = {"pid": child.pid, "started": wake.started_at(child.pid) or "x",
                                         "at": int(time.time() * 1000), "cutoff": cutoff, "log": os.path.join(home, "none.log")}
        w.save()
        return wake.Waker(db_rows, home, poll=0.05)  # a restarted server

    def settle(self, w):
        for _ in range(100):
            if w.view()["pat/sleepy-codex"]["status"] != "running":
                break
            time.sleep(0.05)
        return w.view()["pat/sleepy-codex"]

    def test_running_wake_survives_a_restart(self):
        home = tempfile.mkdtemp()
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            again = self.adopted(home, child, 1000)
            self.assertEqual(again.view()["pat/sleepy-codex"]["status"], "running")
            old = wake.find_codex
            wake.find_codex = lambda: sys.executable
            try:
                with self.assertRaises(wake.WakeError) as e:
                    again.wake("pat/sleepy-codex", WHO)
                self.assertEqual(e.exception.code, 409)
            finally:
                wake.find_codex = old
        finally:
            child.kill()
            child.wait()
        STILL_UNREAD["n"] = 0
        self.assertEqual(self.settle(again)["status"], "done")  # its messages were read
        self.assertEqual(wake.Waker(db_rows, home).view(), {})

    def test_outcome_is_read_from_the_database(self):
        home = tempfile.mkdtemp()
        child = subprocess.Popen([sys.executable, "-c", "pass"])
        child.wait()  # ended while the server was down
        STILL_UNREAD["n"] = 1
        try:
            done = self.settle(self.adopted(home, child, 1000))
        finally:
            STILL_UNREAD["n"] = 0
        self.assertEqual(done["status"], "failed")
        self.assertIn("still unread", done["error"])
        # judged on every message unread at the start (recipient + time cutoff), not a capped list of ids
        self.assertEqual(STILL_UNREAD["asked"], ("pat/sleepy-codex", 1000))

    def test_conversation_open_in_the_codex_app(self):
        locks = Path(os.environ["CODEX_HOME"]) / "thread-writer-locks"
        locks.mkdir(parents=True, exist_ok=True)
        path = locks / f"{UUID}.lock"
        path.write_bytes(b"")
        self.assertFalse(wake.held(UUID))  # a lock file nobody holds
        with HeldLock(path):
            self.assertTrue(wake.held(UUID))
            self.bad("pat/sleepy-codex", 423)
            self.w.state["pat/sleepy-codex"] = {"status": "running", "at": 0, "error": ""}
            self.assertFalse(self.w.is_held(UUID, "pat/sleepy-codex"))  # our own wake holds it
            self.w.state.clear()
            self.assertTrue(self.w.is_held(UUID, "pat/sleepy-codex"))
        self.assertFalse(wake.held(UUID))
        path.unlink()
        self.assertFalse(wake.held(UUID))  # no lock file: nobody has it

    def test_prompt_is_fixed(self):
        self.assertIn("check_inbox", wake.WAKE_PROMPT)
        self.assertIn("send_message", wake.WAKE_PROMPT)


class HeldLock:
    """Hold a Codex thread lock the way another process would."""
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        self.fd = os.open(self.path, os.O_RDWR)
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def __exit__(self, *a):
        if sys.platform == "win32":
            import msvcrt
            os.lseek(self.fd, 0, 0)
            msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
        os.close(self.fd)


AUTO_WHO = {"person": "pat", "machine": "box", "sessions": [{"address": "pat/auto-codex", "machine": "box", "status": "idle"}]}


class AutoWakeTest(unittest.TestCase):
    """Waker.auto() with spawning faked: each wake ends at once and is judged from the fake database."""
    def setUp(self):
        self.spawned = []
        self.saved = (wake.find_codex, wake.spawn, wake.started_at, wake.AUTO_GAP)
        wake.find_codex = lambda: sys.executable
        wake.spawn = lambda args, *a: self.spawned.append(args) or 4242
        wake.started_at = lambda pid: None  # the woken turn is already over
        self.w = wake.Waker(db_rows, poll=0.01)
        STILL_UNREAD["n"] = 0

    def tearDown(self):
        wake.find_codex, wake.spawn, wake.started_at, wake.AUTO_GAP = self.saved
        STILL_UNREAD["n"] = 0

    def run_pass(self, who=AUTO_WHO):
        self.w.auto(["pat/auto-codex", "pat/a-claude", "pat/unknown-codex"], who)
        for _ in range(100):
            if self.w.view().get("pat/auto-codex", {}).get("status") != "running":
                return
            time.sleep(0.01)

    def test_wakes_with_the_fixed_prompt(self):
        self.run_pass()
        self.assertEqual(len(self.spawned), 1)  # the Claude and unknown sessions are skipped
        self.assertEqual(self.spawned[0][-2:], [UUID, wake.WAKE_PROMPT])
        self.assertEqual(self.w.view()["pat/auto-codex"]["status"], "done")
        self.assertTrue(self.w.view()["pat/auto-codex"]["auto"])

    def test_gap_and_hourly_budget(self):
        self.run_pass()
        self.run_pass()
        self.assertEqual(len(self.spawned), 1)  # within AUTO_GAP of the last wake
        wake.AUTO_GAP = 0
        for _ in range(wake.AUTO_BUDGET + 3):
            self.run_pass()
        self.assertEqual(len(self.spawned), wake.AUTO_BUDGET)
        self.assertGreater(self.w.view()["pat/auto-codex"]["limitUntil"], time.time() * 1000)

    def test_failed_wake_waits_before_retrying(self):
        wake.AUTO_GAP = 0
        STILL_UNREAD["n"] = 1
        self.run_pass()
        self.assertEqual(self.w.view()["pat/auto-codex"]["status"], "failed")
        self.run_pass()
        self.assertEqual(len(self.spawned), 1)

    def test_fyi_messages_do_not_auto_wake(self):
        WAKEABLE["pat/auto-codex"] = 0  # its one unread message was sent with --fyi
        try:
            self.run_pass()
        finally:
            WAKEABLE.clear()
        self.assertEqual(self.spawned, [])
        self.run_pass()
        self.assertEqual(len(self.spawned), 1)

    def test_limits_survive_a_restart(self):
        home = tempfile.mkdtemp()
        self.w = wake.Waker(db_rows, home, poll=0.01)
        wake.AUTO_GAP = 0
        for _ in range(wake.AUTO_BUDGET):
            self.run_pass()
        self.assertEqual(len(self.spawned), wake.AUTO_BUDGET)
        self.w = wake.Waker(db_rows, home, poll=0.01)  # a restarted server keeps counting
        self.run_pass()
        self.assertEqual(len(self.spawned), wake.AUTO_BUDGET)
        self.assertIn("limitUntil", self.w.view()["pat/auto-codex"])

    def test_failure_wait_survives_a_restart(self):
        home = tempfile.mkdtemp()
        self.w = wake.Waker(db_rows, home, poll=0.01)
        wake.AUTO_GAP = 0
        STILL_UNREAD["n"] = 1
        self.run_pass()
        self.assertEqual(self.w.view()["pat/auto-codex"]["status"], "failed")
        STILL_UNREAD["n"] = 0
        self.w = wake.Waker(db_rows, home, poll=0.01)
        self.assertEqual(self.w.view()["pat/auto-codex"]["status"], "failed")
        self.run_pass()
        self.assertEqual(len(self.spawned), 1)

    def test_skips_busy_and_app_open(self):
        busy = {**AUTO_WHO, "sessions": [{"address": "pat/auto-codex", "machine": "box", "status": "busy"}]}
        self.run_pass(busy)
        locks = Path(os.environ["CODEX_HOME"]) / "thread-writer-locks"
        locks.mkdir(parents=True, exist_ok=True)
        path = locks / f"{UUID}.lock"
        path.write_bytes(b"")
        try:
            with HeldLock(path):
                self.run_pass()
        finally:
            path.unlink()
        self.assertEqual(self.spawned, [])
        self.run_pass()
        self.assertEqual(len(self.spawned), 1)


if __name__ == "__main__":
    unittest.main()
