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
"""
import json
import os
import re
import threading
import time
from pathlib import Path

from launcher import NOWIN, STATE, base_env, find_codex, kill_tree, spawn, started_at

WAKE_PROMPT = ("You have unread Reason Network messages. Read them with check_inbox and reply to each sender "
               "with send_message. Do nothing else.")
TIMEOUT = 600  # seconds for one woken turn
MAX_RUNNING = 3
MAX_IDS = 50  # unread messages remembered per wake to judge it
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class WakeError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


class Waker:
    def __init__(self, db_rows, home=None, poll=2.0):
        self.db_rows = db_rows
        self.poll = poll
        self.lock = threading.Lock()
        self.state = {}  # address -> {"status": "running" | "done" | "failed", "at": ms, "error": str}
        self.path = Path(home) / "wakes.json" if home else None
        self.running = {}  # address -> {"pid", "started", "at", "ids", "log"}
        for address, w in self.load().items():
            if not (isinstance(w, dict) and isinstance(w.get("pid"), int) and isinstance(w.get("ids"), list)):
                continue
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
            return {a: dict(v) for a, v in self.state.items()}

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
        return uuid, str(cwd)

    def wake(self, address, who):
        uuid, cwd = self.target(address, who)
        codex = find_codex()
        if not codex:
            raise WakeError("Codex is not installed on this computer.")
        ids = [r["id"] for r in self.db_rows("select id from messages where recipient = ? and read_at is null"
                                             " order by sent_at desc limit ?", (address, MAX_IDS))]
        with self.lock:
            if self.state.get(address, {}).get("status") == "running":
                raise WakeError("Already waking it.", 409)
            if sum(v["status"] == "running" for v in self.state.values()) >= MAX_RUNNING:
                raise WakeError(f"Already waking {MAX_RUNNING} sessions; wait for one to finish.", 429)
            self.state[address] = {"status": "running", "at": int(time.time() * 1000), "error": ""}
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
        w = {"pid": pid, "started": started_at(pid) or "", "at": int(time.time() * 1000), "ids": ids, "log": log}
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
        ids = w.get("ids") or []
        if ids:
            marks = ",".join("?" * len(ids))
            left = self.db_rows(f"select count(*) as n from messages where id in ({marks}) and read_at is null", tuple(ids))
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
            self.running.pop(address, None)
            self.save()
            self.state[address] = {"status": "failed" if error else "done", "at": int(time.time() * 1000),
                                   "error": error[:300]}
