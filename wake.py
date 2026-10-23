"""Wake a sleeping Codex session: run one headless turn in its own conversation so it reads its inbox and replies.

A Codex app or CLI session does not wake on a Reason message: it reads its inbox only when it takes a turn.
`codex exec resume <thread> <prompt>` takes that turn in the same conversation (same thread id, so the same Reason
session), with the Reason Network MCP server and hooks from ~/.codex/config.toml: it reads the inbox with
check_inbox and answers with send_message. Checked on a throwaway thread: the reply arrived with reply_to set, the
message was marked read, and the turn was appended to the thread's own rollout file.

Everything that decides what runs comes from this computer, never from the page: the thread id from the Reason
database row, the folder from that row, the prompt from WAKE_PROMPT. One wake per session at a time, with a timeout.

A wake starts detached (launcher.spawn), like a worker, so stopping or restarting this server does not kill it, and
its outcome is read from the database rather than from an exit code: it is done when the messages that were unread
at the start have been read. Running wakes are recorded in wakes.json, so a restarted server watches them to the end
and judges the ones that ended while it was down.

The Codex app keeps every conversation it has opened locked for writing until the app exits
(CODEX_HOME/thread-writer-locks/<thread>.lock); `codex exec resume` is then refused with "already has an active
writer". Checked with `codex app-server` on a throwaway thread: refused while loaded (also after thread/unsubscribe),
accepted once the app-server exited. So a wake first checks that lock and says so instead of failing.

Auto-wake (the `autoWake` setting): the server calls Waker.auto() every few seconds; a session on that list is woken
when it has unread messages, at most AUTO_BUDGET times per AUTO_WINDOW and not within AUTO_GAP of its last wake, so
two agents answering each other cannot run up turns without end.
"""
import json
import os
import re
import sys
import threading
import time
from pathlib import Path

from launcher import NOWIN, STATE, base_env, find_codex, kill_tree, spawn, started_at

WAKE_PROMPT = ("You have unread Reason Network messages. Read them with check_inbox and reply to each sender "
               "with send_message. Do nothing else.")
TIMEOUT = 600  # seconds for one woken turn
MAX_RUNNING = 3
AUTO_GAP = 60  # seconds between two auto-wakes of one session: messages arriving close together share a turn
AUTO_BUDGET, AUTO_WINDOW = 12, 3600  # at most this many auto-wakes per session per window (seconds)
AUTO_RETRY = 600  # seconds before an auto-wake that failed is tried again
HELD_TTL = 10  # seconds a lock check is reused
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def codex_home():
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def held(uuid, home=None):
    """True while a Codex process (the desktop app, a CLI, a running wake) holds this conversation for writing.

    The check takes the lock for an instant and gives it back at once; a missing lock file means nobody holds it.
    """
    path = Path(home or codex_home()) / "thread-writer-locks" / f"{uuid}.lock"
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return False
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)


class WakeError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


class Waker:
    def __init__(self, db_rows, home=None, poll=2.0, codex_dir=None):
        self.db_rows = db_rows
        self.poll = poll
        self.codex_dir = codex_dir  # CODEX_HOME override, for tests
        self.held_seen = {}  # thread id -> (checked at, held)
        self.auto_starts = {}  # address -> start times (s) of its auto-wakes inside AUTO_WINDOW
        self.lock = threading.Lock()
        self.state = {}  # address -> {"status": "running" | "done" | "failed", "at": ms, "error": str}
        self.path = Path(home) / "wakes.json" if home else None
        self.running = {}  # address -> {"pid", "started", "at", "ids", "log"}
        for address, w in self.load().items():
            if not (isinstance(w, dict) and isinstance(w.get("pid"), int) and isinstance(w.get("cutoff"), int)):
                continue
            w["address"] = address
            self.running[address] = w
            self.state[address] = {"status": "running", "at": int(w.get("at") or 0), "error": ""}
            threading.Thread(target=self.watch, args=(address, w), daemon=True).start()  # alive or not: it judges

    # ---------- the record of running wakes ----------
    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8")) if self.path else {}
        except (OSError, ValueError):
            data = {}
        return data if isinstance(data, dict) else {}

    def save(self):
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.running), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def view(self):
        with self.lock:
            out = {a: dict(v) for a, v in self.state.items()}
            now = time.time()
            for a, starts in self.auto_starts.items():
                recent = [t for t in starts if now - t < AUTO_WINDOW]
                if len(recent) >= AUTO_BUDGET:  # resting until the oldest of them leaves the window
                    out.setdefault(a, {"status": "done", "at": 0, "error": ""})["limitUntil"] =                         int((min(recent) + AUTO_WINDOW) * 1000)
            return out

    def is_held(self, uuid, address=None):
        """held(), reused for HELD_TTL seconds: the page asks every few seconds for every Codex session.

        A session this server is waking holds its own lock; that is not the app having it open.
        """
        with self.lock:
            if address and self.state.get(address, {}).get("status") == "running":
                return False
        now = time.time()
        seen = self.held_seen.get(uuid)
        if seen and now - seen[0] < HELD_TTL:
            return seen[1]
        h = held(uuid, self.codex_dir)
        self.held_seen[uuid] = (now, h)
        return h

    @staticmethod
    def resumable(key):
        """The Codex thread id in a Reason session key (codex:<uuid>), or None for any other agent."""
        if isinstance(key, str) and key.startswith("codex:") and UUID_RE.match(key[6:]):
            return key[6:]
        return None

    def target(self, address, who):
        """Check that a session can be woken; returns (thread id, folder). `who` is `reason network who --json`."""
        if not isinstance(address, str) or address.count("/") != 1:
            raise WakeError("Pick a session.")
        person, name = address.split("/")
        if person != who.get("person") or not NAME_RE.match(name):
            raise WakeError("Only sessions of yours on this computer can be woken.")
        live = next((s for s in who.get("sessions") or [] if s.get("address") == address), None)
        if live and live.get("machine") != who.get("machine"):
            raise WakeError("Only sessions on this computer can be woken.")
        if live and live.get("status") == "busy":
            raise WakeError("It is busy; it reads its messages when this turn ends.", 409)
        rows = self.db_rows("select key, agent, cwd from sessions where name = ?", (name,))
        if not rows:
            raise WakeError("This session is not on this computer.", 404)
        uuid = self.resumable(rows[0]["key"])
        if not uuid:
            raise WakeError("This agent cannot be woken from here; only Codex sessions can.")
        cwd = Path(rows[0]["cwd"] or "").expanduser()
        if not rows[0]["cwd"] or not cwd.is_dir():
            raise WakeError("The session's folder no longer exists.")
        unread = self.db_rows("select count(*) as n from messages where recipient = ? and read_at is null", (address,))
        if not unread or not unread[0]["n"]:
            raise WakeError("It has no unread messages.")
        if held(uuid, self.codex_dir):
            self.held_seen[uuid] = (time.time(), True)
            raise WakeError("The Codex app has this conversation open, so it cannot be woken from here: type in it in "
                            "the app. The app lets go of it when the app is closed.", 423)
        return uuid, str(cwd)

    def auto(self, addresses, who):
        """One auto-wake pass over the sessions in the autoWake setting; `who` is a recent `who --all --json`."""
        now = time.time()
        for address in addresses:
            with self.lock:
                st = self.state.get(address, {})
                starts = [t for t in self.auto_starts.get(address, []) if now - t < AUTO_WINDOW]
                self.auto_starts[address] = starts
            if st.get("status") == "running" or len(starts) >= AUTO_BUDGET:
                continue
            if starts and now - starts[-1] < AUTO_GAP:
                continue
            if st.get("status") == "failed" and now * 1000 - st.get("at", 0) < AUTO_RETRY * 1000:
                continue
            try:
                self.wake(address, who, auto=True)
            except WakeError:
                continue  # nothing unread, busy, open in the app, gone: try again on a later pass

    def wake(self, address, who, auto=False):
        uuid, cwd = self.target(address, who)
        codex = find_codex()
        if not codex:
            raise WakeError("Codex is not installed on this computer.")
        # Everything unread now is what this wake is for: remember the newest such message's time, not a list.
        last = self.db_rows("select max(sent_at) as t from messages where recipient = ? and read_at is null", (address,))
        cutoff = last[0]["t"] if last and last[0]["t"] is not None else 0
        with self.lock:
            if self.state.get(address, {}).get("status") == "running":
                raise WakeError("Already waking it.", 409)
            if sum(v["status"] == "running" for v in self.state.values()) >= MAX_RUNNING:
                raise WakeError(f"Already waking {MAX_RUNNING} sessions; wait for one to finish.", 429)
            self.state[address] = {"status": "running", "at": int(time.time() * 1000), "error": "", "auto": auto}
            if auto:
                self.auto_starts.setdefault(address, []).append(time.time())
        env = base_env()
        env["PATH"] = os.pathsep.join([str(Path(codex).parent), env.get("PATH", "")])  # ahead of any codex.cmd shim
        logs = STATE / "logs"
        try:
            logs.mkdir(parents=True, exist_ok=True)
            log = str(logs / f"wake-{address.split('/')[1]}.log")
            pid = spawn([codex, "exec", "--skip-git-repo-check", "resume", uuid, WAKE_PROMPT], cwd, env, NOWIN, log)
        except Exception as e:
            self.finish(address, f"could not start codex: {e}")
            raise WakeError(f"Could not start Codex: {e}", 500)
        w = {"pid": pid, "started": started_at(pid) or "", "at": int(time.time() * 1000), "address": address,
             "cutoff": cutoff, "log": log, "auto": auto}
        with self.lock:
            self.running[address] = w
            self.save()
        threading.Thread(target=self.watch, args=(address, w), daemon=True).start()
        return {"ok": True, "status": "running"}

    def watch(self, address, w):
        """Wait for the woken turn to end (or cut it off), then judge it by whether its messages were read."""
        timed_out = False
        while w["started"] and started_at(w["pid"]) == w["started"]:
            if time.time() * 1000 - w["at"] > TIMEOUT * 1000:
                kill_tree(w["pid"])
                timed_out = True
                break
            time.sleep(self.poll)
        self.finish(address, self.judge(w, timed_out))

    def judge(self, w, timed_out):
        """'' when every message that was unread at the start has been read, else why not."""
        left = self.db_rows("select count(*) as n from messages where recipient = ? and read_at is null and sent_at <= ?",
                            (w.get("address"), w["cutoff"]))
        if not left or not left[0]["n"]:
            return ""
        if timed_out:
            return f"no answer within {TIMEOUT} s"
        try:  # the end of codex's own output says what went wrong
            tail = Path(w["log"]).read_bytes()[-2000:].decode("utf-8", "replace").strip().splitlines()[-2:]
        except (OSError, KeyError, TypeError):
            tail = []
        return "messages still unread after the wake" + (": " + " / ".join(tail) if tail else "")

    def finish(self, address, error):
        with self.lock:
            self.held_seen.clear()  # the woken turn has let go of its lock
            self.running.pop(address, None)
            self.save()
            auto = self.state.get(address, {}).get("auto", False)
            self.state[address] = {"status": "failed" if error else "done", "at": int(time.time() * 1000),
                                   "error": error[:300], "auto": auto}
