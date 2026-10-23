"""Wake a sleeping Codex session: run one headless turn in its own conversation so it reads its inbox and replies.

A Codex app or CLI session does not wake on a Reason message: it reads its inbox only when it takes a turn.
`codex exec resume <thread> <prompt>` takes that turn in the same conversation (same thread id, so the same Reason
session), with the Reason Network MCP server and hooks from ~/.codex/config.toml: it reads the inbox with
check_inbox and answers with send_message. Checked on a throwaway thread: the reply arrived with reply_to set, the
message was marked read, and the turn was appended to the thread's own rollout file.

Everything that decides what runs comes from this computer, never from the page: the thread id from the Reason
database row, the folder from that row, the prompt from WAKE_PROMPT. One wake per session at a time, with a timeout.
"""
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

from launcher import NOWIN, base_env, find_codex, kill_tree, started_at

WAKE_PROMPT = ("You have unread Reason Network messages. Read them with check_inbox and reply to each sender "
               "with send_message. Do nothing else.")
TIMEOUT = 600  # seconds for one woken turn
MAX_RUNNING = 3
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class WakeError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


class Waker:
    def __init__(self, db_rows, home=None):
        self.db_rows = db_rows
        self.lock = threading.Lock()
        self.state = {}  # address -> {"status": "running" | "done" | "failed", "at": ms, "error": str}
        # Running wakes on disk (pid + creation time): a restarted server still knows them, keeps their timeout
        # and does not start a second turn in the same conversation.
        self.path = Path(home) / "wakes.json" if home else None
        self.running = {}  # address -> {"pid", "started", "at"}
        for address, w in self.load().items():
            if isinstance(w, dict) and isinstance(w.get("pid"), int) and w.get("started") \
                    and started_at(w["pid"]) == w["started"]:
                self.running[address] = w
                self.state[address] = {"status": "running", "at": int(w.get("at") or 0), "error": ""}
                threading.Thread(target=self.adopt, args=(address, w), daemon=True).start()
        self.save()

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

    def adopt(self, address, w):
        """Watch a wake a previous server started: same timeout, then mark it finished."""
        error = ""
        while started_at(w["pid"]) == w["started"]:
            if time.time() * 1000 - w["at"] > TIMEOUT * 1000:
                kill_tree(w["pid"])
                error = f"no answer within {TIMEOUT} s"
                break
            time.sleep(2)
        self.finish(address, error)

    def finish(self, address, error):
        with self.lock:
            self.running.pop(address, None)
            self.save()
            self.state[address] = {"status": "failed" if error else "done", "at": int(time.time() * 1000),
                                   "error": error[:300]}

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
        with self.lock:
            if self.state.get(address, {}).get("status") == "running":
                raise WakeError("Already waking it.", 409)
            if sum(v["status"] == "running" for v in self.state.values()) >= MAX_RUNNING:
                raise WakeError(f"Already waking {MAX_RUNNING} sessions; wait for one to finish.", 429)
            self.state[address] = {"status": "running", "at": int(time.time() * 1000), "error": ""}
        env = base_env()
        env["PATH"] = os.pathsep.join([str(Path(codex).parent), env.get("PATH", "")])  # ahead of any codex.cmd shim
        args = [codex, "exec", "--skip-git-repo-check", "resume", uuid, WAKE_PROMPT]
        threading.Thread(target=self.run, args=(address, args, cwd, env), daemon=True).start()
        return {"ok": True, "status": "running"}

    def run(self, address, args, cwd, env):
        error = ""
        try:
            p = subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, creationflags=NOWIN,
                                 start_new_session=os.name != "nt")  # its own group, so kill_tree reaches it all
            with self.lock:
                self.running[address] = {"pid": p.pid, "started": started_at(p.pid) or "", "at": int(time.time() * 1000)}
                self.save()
            try:
                out, err = p.communicate(timeout=TIMEOUT)
                if p.returncode != 0:
                    tail = err.decode("utf-8", "replace").strip().splitlines()[-3:]
                    error = f"codex exited with {p.returncode}: " + " / ".join(tail)
            except subprocess.TimeoutExpired:
                kill_tree(p.pid)
                p.communicate()
                error = f"no answer within {TIMEOUT} s"
        except OSError as e:
            error = str(e)
        self.finish(address, error)
