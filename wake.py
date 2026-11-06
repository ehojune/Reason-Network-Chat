"""Wake local Codex conversations with a fixed inbox prompt.

Idle writer-held threads receive one native queue command, without --resume or a second writer.
queue-wakes.json persists exact message IDs before dispatch, retains completed IDs and holds uncertain
deliveries across restart. Queue receipts never prove reading: only original messages' read_at does.
Unlocked threads retain the detached exec-resume path and wakes.json recovery. Auto-wake remains
opt-in with persistent gap/hourly limits. See docs/reference/queue-wakes.md.
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from launcher import NOWIN, STATE, base_env, find_codex, kill_tree, spawn, started_at
from storage import atomic_json, file_lock

WAKE_PROMPT = ("You have unread Reason Network messages. Read them with check_inbox and reply to each sender "
               "with send_message. Do nothing else.")
TIMEOUT = 600  # seconds for one woken turn
MAX_RUNNING = 3
AUTO_GAP = 60  # seconds between two auto-wakes of one session: messages arriving close together share a turn
AUTO_BUDGET, AUTO_WINDOW = 12, 3600  # at most this many auto-wakes per session per window (seconds)
AUTO_RETRY = 600  # seconds before an auto-wake that failed is tried again
HELD_TTL = 10  # seconds a lock check is reused
QUEUE_TIMEOUT = 20
QUEUE_PENDING = {"intent", "queued", "held"}
QUEUE_ACTIVE = {"intent", "queued"}  # uncertain holds block their address, not unrelated wake capacity
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
        self.auto_path = Path(home) / "autowake.json" if home else None
        self.queue_path = Path(home) / "queue-wakes.json" if home else None
        self.queue_support = {}
        self.queue_error = ""
        self.running = {}  # address -> {"pid", "started", "at", "ids", "log"}
        now = time.time()
        for address, a in self.load(self.auto_path).items():  # auto-wake limits from before a restart
            if not isinstance(a, dict):
                continue
            starts = [t for t in a.get("starts") or [] if isinstance(t, (int, float)) and 0 <= now - t < AUTO_WINDOW]
            if starts:
                self.auto_starts[address] = starts
            f = a.get("failed")
            if isinstance(f, dict) and isinstance(f.get("at"), int):
                self.state[address] = {"status": "failed", "at": f["at"], "error": str(f.get("error") or "")[:300],
                                       "auto": True}
        for address, w in self.load().items():
            if not (isinstance(w, dict) and isinstance(w.get("pid"), int) and isinstance(w.get("cutoff"), int)):
                continue
            w["address"] = address
            self.running[address] = w
            self.state[address] = {"status": "running", "at": int(w.get("at") or 0), "error": "",
                                   "auto": bool(w.get("auto"))}
            threading.Thread(target=self.watch, args=(address, w), daemon=True).start()  # alive or not: it judges
        self.refresh_queue(strict=False)

    def queue_data(self):
        """Fail closed: losing dispatch history must never silently enable a replay."""
        if not self.queue_path:
            return {"version": 1, "batches": []}
        try:
            data = json.loads(self.queue_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("batches"), list):
                raise ValueError("invalid journal")
            seen = set()
            for b in data["batches"]:
                if not (isinstance(b, dict) and isinstance(b.get("address"), str)
                        and isinstance(b.get("at"), int) and isinstance(b.get("auto"), bool)
                        and isinstance(b.get("thread"), str) and UUID_RE.fullmatch(b["thread"])
                        and isinstance(b.get("status"), str) and b["status"] in QUEUE_PENDING | {"done"}
                        and isinstance(b.get("ids"), list) and b["ids"]
                        and all(isinstance(i, str) and i for i in b["ids"])):
                    raise ValueError("invalid dispatch batch")
                for id_ in b["ids"]:
                    pair = (b["address"], id_)
                    if pair in seen:
                        raise ValueError("duplicate dispatch ID")
                    seen.add(pair)
            return data
        except FileNotFoundError:
            return {"version": 1, "batches": []}
        except (OSError, ValueError) as e:
            raise WakeError(f"Cannot read queue dispatch history; no wake was sent: {e}", 503)

    def reconcile_queue(self, data):
        """Only exact original IDs with read_at set prove consumption; a receipt does not."""
        changed = False
        for b in data["batches"]:
            if b["status"] in QUEUE_PENDING:
                read = set()
                for start in range(0, len(b["ids"]), 400):
                    ids = b["ids"][start:start + 400]
                    rows = self.db_rows("select id, read_at from messages where recipient = ? and id in ("
                                        + ",".join("?" for _ in ids) + ")", (b["address"], *ids))
                    read.update(r["id"] for r in rows if r["read_at"] is not None)
                if set(b["ids"]) <= read:
                    b.update(status="done", error="")
                    changed = True
                elif b["status"] == "intent" or (b["status"] == "queued"
                        and time.time() * 1000 - b["at"] > TIMEOUT * 1000):
                    b.update(status="held", error="Delivery uncertain or still unread; automatic resend is blocked.")
                    changed = True
            current = self.state.get(b["address"], {})
            if current.get("status") != "running" and current.get("at", -1) <= b["at"]:
                self.state[b["address"]] = {"status": b["status"], "at": b["at"], "mode": "queue",
                                            "error": b.get("error", ""), "auto": bool(b.get("auto"))}
            if b.get("auto") and 0 <= time.time() - b["at"] / 1000 < AUTO_WINDOW:
                starts = self.auto_starts.setdefault(b["address"], [])
                if b["at"] / 1000 not in starts:
                    starts.append(b["at"] / 1000)
                    starts.sort()
        if changed:
            atomic_json(self.queue_path, data, durable=True)

    def refresh_queue(self, strict=True):
        if not self.queue_path:
            return {"version": 1, "batches": []}
        try:
            with self.lock, file_lock(self.queue_path.with_suffix(".lock")):
                data = self.queue_data()
                self.reconcile_queue(data)
                self.queue_error = ""
                return data
        except (WakeError, OSError) as e:
            self.queue_error = str(e)
            if strict:
                raise WakeError(f"Queue dispatch history unavailable; wake held: {e}", 503) from e
            return None  # keep chats/controls available while dispatch fails closed

    def supports_queue(self, codex):
        if Path(codex).suffix.lower() in {".cmd", ".bat"}:
            raise WakeError("Queue wake requires a native Codex executable, not a batch shim.")
        try:
            stat = Path(codex).stat()
        except OSError as e:
            raise WakeError(f"Cannot inspect native Codex executable: {e}", 503)
        key = (codex, stat.st_mtime_ns, stat.st_size)
        if key not in self.queue_support:
            try:
                result = subprocess.run([codex, "queue", "--help"], capture_output=True, timeout=QUEUE_TIMEOUT,
                                        stdin=subprocess.DEVNULL, env=base_env(), creationflags=NOWIN)
                self.queue_support[key] = (result.returncode == 0 and b"--thread" in result.stdout
                                           and b"--message" in result.stdout)
            except (OSError, subprocess.TimeoutExpired):
                self.queue_support[key] = False
        if not self.queue_support[key]:
            raise WakeError("This Codex executable does not support native queue; no wake was sent.", 503)

    def queue_wake(self, address, who, codex, auto):
        """Persist intent before the single native enqueue. Never retry an uncertain side effect."""
        if not self.queue_path:
            raise WakeError("A durable queue dispatch journal is required.", 503)
        self.supports_queue(codex)
        with self.lock, file_lock(self.queue_path.with_suffix(".lock")):
            data = self.queue_data()
            self.reconcile_queue(data)
            if any(b["address"] == address and b["status"] in QUEUE_PENDING for b in data["batches"]):
                raise WakeError("A queued or uncertain wake is outstanding; it will not be resent.", 409)
            if self.state.get(address, {}).get("status") == "running":
                raise WakeError("Already waking it.", 409)
            uuid, cwd = self.target(address, who)
            live = next((s for s in who.get("sessions") or [] if s.get("address") == address), {})
            if live.get("status") != "idle" or not held(uuid, self.codex_dir):
                raise WakeError("Queue wake requires an idle local conversation with an existing writer.", 409)
            used = {i for b in data["batches"] if b["address"] == address for i in b["ids"]}
            rows = self.db_rows("select id, wake, held from messages where recipient = ? and read_at is null",
                                (address,))
            if any(r["id"] in used for r in rows):
                # The fixed prompt reads the entire inbox, not just the fresh journal batch.
                raise WakeError("Previously queued message IDs remain unread; no second wake was sent.", 409)
            fresh = [r for r in rows if r["id"] not in used]
            if not fresh or (auto and not any(r["wake"] and not r["held"] for r in fresh)):
                raise WakeError("No new eligible message IDs; previous wakes will not be repeated.", 409)
            now = time.time()
            starts = [t for t in self.auto_starts.get(address, []) if now - t < AUTO_WINDOW]
            if auto and (len(starts) >= AUTO_BUDGET or starts and now - starts[-1] < AUTO_GAP):
                raise WakeError("Auto-wake limit reached; wait for the next window.", 429)
            outstanding = sum(v.get("status") in QUEUE_ACTIVE | {"running"} for v in self.state.values())
            if outstanding >= MAX_RUNNING:
                raise WakeError(f"Already waking {MAX_RUNNING} sessions; wait for one to finish.", 429)
            b = {"address": address, "thread": uuid, "ids": [r["id"] for r in fresh], "status": "intent",
                 "at": int(now * 1000), "auto": auto, "error": ""}
            data["batches"].append(b)
            atomic_json(self.queue_path, data, durable=True)  # BEFORE any possible enqueue
            if auto:
                self.auto_starts.setdefault(address, []).append(b["at"] / 1000)
                self.save_auto()
            try:
                result = subprocess.run([codex, "queue", "--thread", uuid, "--message", WAKE_PROMPT],
                                        cwd=cwd, env=base_env(), stdin=subprocess.DEVNULL,
                                        capture_output=True, timeout=QUEUE_TIMEOUT, creationflags=NOWIN)
                b["receipt"] = result.stdout.decode("utf-8", "replace")[:2000]
                b["status"] = "queued" if result.returncode == 0 else "held"
                if result.returncode:
                    b["error"] = "Queue command failed; delivery is uncertain and resend is blocked."
            except (OSError, subprocess.TimeoutExpired) as e:
                b.update(status="held", error=f"Queue delivery uncertain; resend is blocked: {e}"[:300])
            atomic_json(self.queue_path, data, durable=True)
            self.state[address] = {"status": b["status"], "at": b["at"], "mode": "queue",
                                   "error": b["error"], "auto": auto}
            return {"ok": True, "status": b["status"], "mode": "queue"}

    # ---------- the record of running wakes ----------
    def load(self, path=None):
        path = path or self.path
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path else {}
        except (OSError, ValueError):
            data = {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def write(path, data):
        if not path:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass

    def save(self):
        self.write(self.path, self.running)

    def save_auto(self):
        """Keep the auto-wake limits (recent starts, a recent failure) across restarts; call with self.lock held."""
        now = time.time()
        data = {}
        for a in set(self.auto_starts) | set(self.state):
            starts = [t for t in self.auto_starts.get(a, []) if now - t < AUTO_WINDOW]
            st = self.state.get(a, {})
            failed = ({"at": st["at"], "error": st.get("error", "")} if st.get("status") == "failed" and st.get("auto")
                      and now * 1000 - st["at"] < AUTO_RETRY * 1000 else None)
            if starts or failed:
                data[a] = {"starts": starts, "failed": failed}
        self.write(self.auto_path, data)

    def view(self):
        self.refresh_queue(strict=False)
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
        return uuid, str(cwd)

    def auto(self, addresses, who):
        """One auto-wake pass over the sessions in the autoWake setting; `who` is a recent `who --all --json`."""
        if self.refresh_queue(strict=False) is None:
            return
        now = time.time()
        for address in addresses:
            with self.lock:
                st = self.state.get(address, {})
                starts = [t for t in self.auto_starts.get(address, []) if now - t < AUTO_WINDOW]
                self.auto_starts[address] = starts
            if st.get("status") in QUEUE_PENDING | {"running"} or len(starts) >= AUTO_BUDGET:
                continue
            if starts and now - starts[-1] < AUTO_GAP:
                continue
            if st.get("status") == "failed" and now * 1000 - st.get("at", 0) < AUTO_RETRY * 1000:
                continue
            # Only a message that asked to wake it does: an FYI (`--fyi`) or a held one waits for its next turn.
            fresh = self.db_rows("select count(*) as n from messages where recipient = ? and read_at is null"
                                 " and wake = 1 and held = 0", (address,))
            if not fresh or not fresh[0]["n"]:
                continue
            try:
                self.wake(address, who, auto=True)
            except WakeError as e:
                if e.code == 503:  # unsupported queue must also be visible for unattended auto-wake
                    with self.lock:
                        self.state[address] = {"status": "failed", "at": int(time.time() * 1000),
                                               "error": str(e)[:300], "auto": True}
                        self.save_auto()
                continue  # busy, unavailable or no new eligible IDs: no dispatch on this pass

    def wake(self, address, who, auto=False):
        history = self.refresh_queue()
        if any(b["address"] == address and b["status"] in QUEUE_PENDING for b in history["batches"]):
            raise WakeError("A queued or uncertain wake is outstanding; it will not be resent.", 409)
        uuid, cwd = self.target(address, who)
        codex = find_codex()
        if not codex:
            raise WakeError("Codex is not installed on this computer.")
        if held(uuid, self.codex_dir):
            return self.queue_wake(address, who, codex, auto)
        used = {i for b in history["batches"] if b["address"] == address for i in b["ids"]}
        if used:
            unread = self.db_rows("select id, wake, held from messages where recipient = ? and read_at is null", (address,))
            if any(r["id"] in used for r in unread):
                raise WakeError("Previously queued message IDs remain unread; no second wake was sent.", 409)
        # Everything unread now is what this wake is for: remember the newest such message's time, not a list.
        last = self.db_rows("select max(sent_at) as t from messages where recipient = ? and read_at is null", (address,))
        cutoff = last[0]["t"] if last and last[0]["t"] is not None else 0
        with self.lock:
            if self.state.get(address, {}).get("status") == "running":
                raise WakeError("Already waking it.", 409)
            if sum(v["status"] in QUEUE_ACTIVE | {"running"} for v in self.state.values()) >= MAX_RUNNING:
                raise WakeError(f"Already waking {MAX_RUNNING} sessions; wait for one to finish.", 429)
            self.state[address] = {"status": "running", "at": int(time.time() * 1000), "error": "", "auto": auto}
            if auto:
                self.auto_starts.setdefault(address, []).append(time.time())
                self.save_auto()
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
            if auto:
                self.save_auto()
