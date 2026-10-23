"""Reason Network Chat: a chat-room view of Reason Network traffic on this computer.

Localhost only, Python standard library only. Reads the daemon's SQLite database read-only
(mode=ro) and `reason network who --all --json`; sends with `reason network send`; starts new
sessions through launcher.py, keeps rooms in rooms.py and relays group rooms through relay.py.
It never writes the database.
"""
import hmac
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from launcher import BADGE, STATE, Catalog, Launcher, LaunchError, allow_ctrl_c, base_env, inner_of
from prefs import PrefError, Prefs
import relay as relay_mod
from relay import Relay, RelayError
from rooms import RoomError, Rooms
from wake import WakeError, Waker

HOST = "127.0.0.1"
PORT = int(os.environ.get("REASON_CHAT_PORT", "8765"))
HOME = Path.home()
DB = Path(os.environ.get("REASON_CHAT_DB", HOME / ".reason" / "network" / "network.db"))
STATIC = Path(__file__).with_name("index.html")
POLL_WHO = 3  # seconds between `who` refreshes
# A worker busy this long with no new step and no new log line is shown as possibly stuck.
STUCK_MS = int(os.environ.get("REASON_CHAT_STUCK_MIN", "30")) * 60000
POLL_AUTO = 10  # seconds between auto-wake passes
POLL_DISCOVER = 30  # seconds between looks for serve workers this page lost track of
MAX_MESSAGES = 2000  # newest rows sent to the page per poll
MAX_BODY = 64 * 1024  # bytes accepted by a POST
ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
# Written into the page at load; every POST must echo it. Pages on other sites cannot read it.
TOKEN = secrets.token_urlsafe(32)
# Shape of /api/state and the POSTs. Bump together with API in index.html: a page that meets a server of another
# version (the server kept running across an update) asks for a restart instead of breaking.
API = 15
BOOT = secrets.token_hex(8)  # new each start: an open page that sees another one reloads to get the new token
NOWIN = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW


def find_reason():
    if os.environ.get("REASON_BIN"):
        return os.environ["REASON_BIN"]
    if sys.platform == "win32":
        p = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData" / "Local")) / "Reason" / "bin" / "reason.exe"
        if p.exists():
            return str(p)
    return shutil.which("reason") or "reason"


REASON = find_reason()
# cmd.exe would re-parse message text (&, |, %) if the CLI were a .cmd/.bat shim.
if sys.platform == "win32" and REASON.lower().endswith((".cmd", ".bat")):
    sys.exit(f"Point REASON_BIN at reason.exe, not a batch shim: {REASON}")
_who = {"data": None, "error": None}
_lock = threading.Lock()
# address -> {key: (status, doing), at, changed}: when a session's status or current step last changed. `serve`
# updates `doing` with every step of a turn, so a busy worker whose step stays the same is not getting anywhere.
_activity = {}
CATALOG = Catalog(REASON)
LAUNCHER = Launcher(REASON, CATALOG)
ROOMS = Rooms(STATE)
PREFS = Prefs(STATE)


def run_reason(*args, timeout=30):
    # Behind a TLS-inspecting proxy the CLI needs NODE_EXTRA_CA_CERTS; base_env() fills it in from the
    # stored user environment when this process started before it was set.
    p = subprocess.run([REASON, "network", *args], capture_output=True, timeout=timeout,
                       stdin=subprocess.DEVNULL, env=base_env(), creationflags=NOWIN)
    dec = lambda b: b.decode("utf-8", "replace").strip()
    return p.returncode, dec(p.stdout), dec(p.stderr)


def who_loop():
    while True:
        try:
            rc, out, err = run_reason("who", "--all", "--json", timeout=20)
            data = json.loads(out) if rc == 0 else None
            with _lock:
                if data:
                    _who.update(data=data, error=None)
                    note_activity(data)
                else:
                    _who["error"] = err or f"rc={rc}"
        except Exception as e:  # keep the last good snapshot
            with _lock:
                _who["error"] = str(e)
        time.sleep(POLL_WHO)


def note_activity(data):
    """Record when each session's (status, step) changed (call with _lock held)."""
    now = int(time.time() * 1000)
    for s in data.get("sessions") or []:
        cur, a = [s.get("status"), s.get("doing")], _activity.get(s.get("address"))
        if not a or a["key"] != cur:
            _activity[s.get("address")] = {"key": cur, "at": now, "changed": bool(a)}


def quiet_since(activity, log_at, now):
    """Since when a busy worker has shown no progress (ms): its last step change or log line, whichever is later.
    A change only counts once seen happening (the first sight after a start is not one); with nothing known yet,
    the first sight."""
    marks = [x for x in ((activity or {}).get("at") if (activity or {}).get("changed") else None, log_at) if x]
    return max(marks) if marks else (activity or {}).get("at", now)


def restart_blocked(who):
    """Names /api/workers/restart must not start: a serve with that name runs here, or the name is online on another
    computer of this person. A name shown online here only because its process was killed is free (Reason accepts it)."""
    me_ = who.get("person")
    online = [s for s in who.get("sessions") or [] if s.get("status") != "offline" and s.get("person") == me_]
    running = LAUNCHER.running_serve_names()
    if running is None:  # processes cannot be read here: anything online blocks (fail closed)
        return {s["name"] for s in online}
    return running | {s["name"] for s in online if s.get("machine") != who.get("machine")}


def discover_loop():
    """Take back workers this page started that workers.json lost (a process list every 30 s, so not per poll)."""
    while True:
        try:
            LAUNCHER.discover()
        except Exception as e:  # a bad pass must not end the loop
            print(f"worker discovery: {e}", file=sys.stderr, flush=True)
        time.sleep(POLL_DISCOVER)


def auto_loop():
    """Wake the sessions in the autoWake setting when they have unread messages (wake.py keeps the limits)."""
    while True:
        time.sleep(POLL_AUTO)
        try:
            addresses = PREFS.get().get("autoWake") or []
            with _lock:
                who = _who["data"]
            if addresses and who:
                WAKER.auto(addresses, who)
        except Exception as e:  # a bad pass must not end the loop
            print(f"auto-wake: {e}", file=sys.stderr, flush=True)


def db_rows(sql, params=()):
    con = sqlite3.connect(f"{DB.resolve().as_uri()}?mode=ro", uri=True, timeout=2)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql, params)]
    finally:
        con.close()


def state():
    msgs = db_rows("select * from (select id, sender, sender_agent, recipient, reply_to, body, wake, sent_at,"
                   f" read_at, held from messages order by sent_at desc limit {MAX_MESSAGES}) order by sent_at")
    known = {r["name"]: r for r in db_rows("select name, agent, cwd, doing, tier, key from sessions")}
    with _lock:
        who, who_err = _who["data"] or {}, _who["error"]
    person = who.get("person")
    me = f"{person}/terminal" if person else None  # address `reason network send` uses from a plain process
    live = who.get("sessions") or []
    seen = {s["address"] for s in live}
    # Codex sessions of yours on this computer can be woken (wake.py): their key in the database names the thread.
    mine = lambda person_, machine: person_ == person and machine in (None, who.get("machine"))
    can_wake = lambda name, person_, machine: mine(person_, machine) and bool(Waker.resumable(known.get(name, {}).get("key")))
    sessions = [dict(s, live=True, resumable=can_wake(s["name"], s.get("person"), s.get("machine"))) for s in live]
    # Unread counts straight from the database: the page only gets the newest MAX_MESSAGES rows.
    unread = {r["recipient"]: r["n"] for r in db_rows(
        "select recipient, count(*) as n from messages where read_at is null group by recipient")}
    # Sessions that now exist only in history: finished CLI asks, departed agents.
    for addr in sorted({m["sender"] for m in msgs} | {m["recipient"] for m in msgs}):
        if addr in seen or addr == me:
            continue
        name = addr.split("/", 1)[-1]
        k = known.get(name, {})
        agent = k.get("agent") or next((m["sender_agent"] for m in msgs
                                        if m["sender"] == addr and m["sender_agent"]), None)
        sessions.append({"address": addr, "name": name, "agent": agent or "?", "status": "gone",
                         "doing": k.get("doing"), "cwd": k.get("cwd"), "tier": k.get("tier"),
                         "live": False, "resumable": can_wake(name, addr.split("/", 1)[0], None)})
        seen.add(addr)
    records = {r["name"]: r for r in LAUNCHER.list_records()}
    stale = LAUNCHER.stale_names()
    workers = set(records) | {w["name"] for w in LAUNCHER.list()}
    for s in sessions:
        s["unread"] = unread.get(s["address"], 0)
        # A worker of this page keeps its badge when offline: the database stores serve workers as agent "cli".
        rec = records.get(s["name"]) if s["address"].split("/", 1)[0] == person else None
        if rec:
            s["worker"] = True
            if s.get("agent") not in ("claude-code", "codex"):
                s["agent"] = BADGE[rec["family"]]
            # Killed mid-turn (or forced off): the network keeps it busy/idle, but no serve process runs here.
            if s.get("status") in ("busy", "idle") and s.get("machine") in (None, who.get("machine")) \
                    and s["name"] in stale:
                s["stale"] = True
        # A worker's own agent sessions (<worker>-claude, -2, …) register themselves; the page folds them away.
        # Only this person's sessions on this computer (a teammate's helper-claude is not ours to hide).
        own = s["address"].split("/", 1)[0] == person and s.get("machine") in (None, who.get("machine"))
        s["inner"] = inner_of(s["name"], workers) if own else None
        # Possibly stuck: a worker of this computer busy for STUCK_MS with no new step and no new log line.
        # Only a `serve` worker (recorded here, or a serve process with that name runs here), not a one-off ask.
        serving = LAUNCHER.serving or set()
        if own and s.get("status") == "busy" and s.get("live") and (s.get("worker") or s["name"] in serving):
            with _lock:
                act = dict(_activity.get(s["address"]) or {})
            now_ = int(time.time() * 1000)
            s["quietSince"] = quiet_since(act, LAUNCHER.log_activity(s["name"]), now_)
            s["stuck"] = now_ - s["quietSince"] > STUCK_MS
        # The Codex app keeps the conversations it opened locked: then nothing outside the app can wake them.
        s["appOpen"] = bool(s["resumable"]) and WAKER.is_held(Waker.resumable(known[s["name"]]["key"]), s["address"])
    relays, queued, notices = RELAY.view({m["id"] for m in msgs})
    forwarded = RELAY.forwarded_view({m["id"] for m in msgs})
    settled = RELAY.settled_view({m["id"] for m in msgs})
    return {"api": API, "boot": BOOT, "team": who.get("team"), "me": me, "sessions": sessions, "messages": msgs,
            "launched": LAUNCHER.list(), "foreignWorkers": LAUNCHER.list_foreign(), "workerRecords": list(records.values()), "rooms": ROOMS.list(), "relays": relays, "queued": queued, "notices": notices, "forwarded": forwarded, "settled": settled,
            "relayDefaults": {"hops": relay_mod.MAX_HOPS, "budget": relay_mod.BUDGET, "window": relay_mod.BUDGET_WINDOW},
            "prefs": PREFS.get(), "wakes": WAKER.view(),
            "whoError": who_err, "now": int(time.time() * 1000)}


def me_and_known():
    """The page's own address and every session address it can show: live ones and those in history."""
    with _lock:
        who = _who["data"] or {}
    person = who.get("person")
    known = {s["address"] for s in who.get("sessions") or []}
    for r in db_rows("select distinct sender as a from messages union select distinct recipient from messages"):
        known.add(r["a"])
    return (f"{person}/terminal" if person else None), known


def my_address():
    with _lock:
        person = (_who["data"] or {}).get("person")
    return f"{person}/terminal" if person else None


def send_one(to, body, fyi):
    # The CLI has no `--` terminator: a body like "--help" would print help and exit 0.
    if body.startswith("-"):
        body = " " + body
    return run_reason("send", to, body, *(["--fyi"] if fyi else []), timeout=60)


def dm_note(to):
    """relay.dm_note() when `to` is a member of a group room, else nothing."""
    if not any(r.get("group") and to in r["members"] for r in ROOMS.list()):
        return ""
    return relay_mod.dm_note((my_address() or "").split("/", 1)[0] or "the user")


def fresh_who():
    """`who --all --json` now, or None."""
    rc, out, err = run_reason("who", "--all", "--json", timeout=20)
    try:
        return json.loads(out) if rc == 0 else None
    except ValueError:
        return None


def live_names():
    with _lock:
        who = _who["data"] or {}
    return {s["name"] for s in who.get("sessions") or [] if s.get("status") != "offline"}


def folders():
    """Folders of known sessions, offered as suggestions in the new-session form."""
    with _lock:
        who = _who["data"] or {}
    seen = []
    for s in who.get("sessions") or []:
        cwd = s.get("cwd")
        if isinstance(cwd, str) and cwd:
            path = str(Path(cwd).expanduser())
            if path not in seen and Path(path).is_dir():
                seen.append(path)
    return seen


RELAY = Relay(STATE, ROOMS, db_rows, send_one)
WAKER = Waker(db_rows, STATE)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        # No framing: another page must not be able to overlay this one and steal clicks.
        self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj, code=200):
        self.reply(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def host_ok(self):
        # Blocks DNS-rebinding pages from reading messages through a foreign hostname.
        if self.headers.get("Host", "") in (f"127.0.0.1:{PORT}", f"localhost:{PORT}"):
            return True
        self.send_error(403)
        return False

    def do_GET(self):
        if not self.host_ok():
            return
        url = urlsplit(self.path)
        if url.path in ("/", "/index.html"):
            page = STATIC.read_text(encoding="utf-8").replace("{{TOKEN}}", TOKEN).replace("{{BOOT}}", BOOT)
            self.reply(200, page.encode("utf-8"), "text/html; charset=utf-8")
        elif url.path == "/api/state":
            try:
                self.send_json(state())
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        elif url.path == "/api/workers/procs":
            name = (parse_qs(url.query).get("name") or [""])[0]
            try:
                self.send_json(LAUNCHER.tree(name))
            except LaunchError as e:
                self.send_json({"error": str(e)}, e.code)
        elif url.path == "/api/catalog":
            refresh = parse_qs(url.query).get("refresh") == ["1"]
            self.send_json({"families": CATALOG.get(refresh), "folders": folders()})
        else:
            self.send_error(404)

    def read_json(self):
        """The body of a POST made by this page, or None after an error response was sent."""
        # A page on another site cannot send this Origin, read the token, or post JSON without a preflight.
        if self.headers.get("Origin") not in ORIGINS:
            self.send_json({"error": "bad origin"}, 403)
            return None
        if not hmac.compare_digest(self.headers.get("X-Reason-Chat-Token", ""), TOKEN):
            self.send_json({"error": "bad token: reload the page"}, 403)
            return None
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            self.send_json({"error": "json only"}, 415)
            return None
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self.send_json({"error": "Content-Length required"}, 411)
            return None
        if not 0 < n <= MAX_BODY:
            self.send_json({"error": "body too large"}, 413)
            return None
        try:
            req = json.loads(self.rfile.read(n).decode("utf-8"))
        except ValueError:
            self.send_json({"error": "bad json"}, 400)
            return None
        if not isinstance(req, dict):
            self.send_json({"error": "expected an object"}, 400)
            return None
        return req

    def do_POST(self):
        if not self.host_ok():
            return
        path = urlsplit(self.path).path
        if path not in ("/api/send", "/api/launch", "/api/stop", "/api/rooms/save", "/api/rooms/delete",
                        "/api/rooms/send", "/api/rooms/flush", "/api/rooms/forward", "/api/resend", "/api/prefs", "/api/wake", "/api/workers/configure", "/api/workers/adopt", "/api/workers/reboot",
                        "/api/workers/restart"):
            return self.send_error(404)
        req = self.read_json()
        if req is None:
            return
        try:
            if path == "/api/send":
                self.send_message(req)
            elif path == "/api/launch":
                names = live_names()
                name = req.get("name")
                if isinstance(name, str) and name in names:  # maybe only a killed worker of ours holding the name
                    who = fresh_who()
                    if who and LAUNCHER.stale(name, who):
                        names.discard(name)
                self.send_json(LAUNCHER.launch(req, names))
            elif path == "/api/rooms/save":
                me, known = me_and_known()
                self.send_json({"ok": True, "room": ROOMS.upsert(req, known, me)})
            elif path == "/api/rooms/delete":
                ROOMS.delete(req.get("id"))
                self.send_json({"ok": True})
            elif path == "/api/rooms/send":
                self.send_room(req)
            elif path == "/api/resend":
                self.resend(req)
            elif path == "/api/rooms/forward":
                self.forward_room(req)
            elif path == "/api/rooms/flush":
                if not ROOMS.get(req.get("id")):
                    return self.send_json({"error": "No such room."}, 404)
                self.send_json({"ok": True, "released": RELAY.flush(req["id"])})
            elif path == "/api/prefs":
                self.send_json({"ok": True, "prefs": PREFS.set(req.get("key"), req.get("value"))})
            elif path == "/api/wake":
                # A fresh status, not the cached one: a session that turned busy must not get a second turn.
                who = fresh_who()
                if not who:
                    return self.send_json({"error": "Reason Network is not answering; try again."}, 503)
                self.send_json(WAKER.wake(req.get("address"), who))
            elif path == "/api/workers/restart":
                # Fresh: a worker that came back on its own must not get a second process.
                who = fresh_who()
                if not who:
                    return self.send_json({"error": "Reason Network is not answering; try again."}, 503)
                # Blocked: a serve with that name runs here, or the name is online on another computer of this
                # person. A name shown online here only because its process was killed is free (Reason accepts it).
                blocked = restart_blocked(who)
                self.send_json(LAUNCHER.restart(req.get("names"), blocked))
            elif path == "/api/workers/adopt":
                name = req.get("name")
                if not isinstance(name, str):
                    return self.send_json({"error": "name must be a string"}, 400)
                model, effort = req.get("model"), req.get("effort")
                if not all(v is None or isinstance(v, str) for v in (model, effort)):
                    return self.send_json({"error": "model and effort must be strings"}, 400)
                self.send_json(LAUNCHER.adopt(name, model, effort))
            elif path == "/api/workers/reboot":
                self.reboot(req)
            elif path == "/api/workers/configure":
                # Fresh too: restarting a worker that just took a message would lose that turn.
                who = fresh_who()
                if not who:
                    return self.send_json({"error": "Reason Network is not answering; try again."}, 503)
                me = (who.get("person") or "") + "/" + str(req.get("name"))
                busy = any(x.get("address") == me and x.get("status") == "busy" for x in who.get("sessions") or [])
                self.send_json(LAUNCHER.configure(req, busy))
            else:
                name = req.get("name")
                if not isinstance(name, str):
                    return self.send_json({"error": "name must be a string"}, 400)
                LAUNCHER.stop(name)
                self.send_json({"ok": True})
        except (LaunchError, RoomError, PrefError, WakeError, RelayError) as e:
            self.send_json({"error": str(e)}, e.code)
        except Exception as e:
            self.send_json({"error": str(e)}, 500)

    def send_message(self, req):
        to, body, fyi = req.get("to"), req.get("body"), req.get("fyi", False)
        if not (isinstance(to, str) and isinstance(body, str) and isinstance(fyi, bool)):
            return self.send_json({"error": "to and body must be strings, fyi a boolean"}, 400)
        to, body = to.strip(), body.strip()
        if not to or not body or to.startswith("-"):
            return self.send_json({"error": "to and body are required"}, 400)
        rc, out, err = send_one(to, body + dm_note(to), fyi)
        self.send_json({"ok": rc == 0, "rc": rc, "out": out, "err": err}, 200 if rc == 0 else 502)

    def reboot(self, req):
        """Restart a worker with its recorded settings: a running one managed here is stopped first (what a stuck one
        needs); a stopped recorded one is just started. One started elsewhere must be adopted first."""
        name = req.get("name")
        if not isinstance(name, str) or not name:
            return self.send_json({"error": "name must be a worker name"}, 400)
        where = LAUNCHER.running_here(name)
        if where == "managed":
            return self.send_json(LAUNCHER.relaunch(name))
        if where == "foreign":
            raise LaunchError("It was started outside this page: adopt it first (python rnc.py worker adopt NAME).", 409)
        who = fresh_who()
        if not who:
            return self.send_json({"error": "Reason Network is not answering; try again."}, 503)
        r = LAUNCHER.restart([name], restart_blocked(who))["results"][0]
        if not r["ok"]:
            raise LaunchError(r["error"], r.get("code", 400))
        self.send_json({"ok": True, "restarted": False, "started": True})

    def resend(self, req):
        """Your messages a worker failed on or took without answering: send each again as it was (a relayed one
        through the relay, a 1:1 one as is), or put them aside with `dismiss`. Once per message."""
        ids, dismiss = req.get("ids"), req.get("dismiss", False)
        if not (isinstance(ids, list) and 0 < len(ids) <= 100 and all(isinstance(i, str) and i for i in ids)
                and isinstance(dismiss, bool)):
            return self.send_json({"error": "ids must be 1-100 message ids, dismiss a boolean"}, 400)
        me = my_address()
        if not me:
            return self.send_json({"error": "Reason Network is not answering yet; try again."}, 503)
        with _lock:
            status = {s["address"]: s.get("status") for s in (_who["data"] or {}).get("sessions") or []}
        results = []
        for mid in dict.fromkeys(ids):
            if dismiss:
                ok = RELAY.claim(mid, "dismissed")
                results.append({"id": mid, "ok": ok, **({} if ok else {"err": "Already dealt with."})})
                continue
            to = RELAY.recipient_of(mid)
            row = None
            if not to:
                rows = db_rows("select sender, recipient, body from messages where id = ?", (mid,))
                if not rows or rows[0]["sender"] != me:
                    results.append({"id": mid, "ok": False, "err": "Only your own messages can be sent again."})
                    continue
                row, to = rows[0], rows[0]["recipient"]
            if status.get(to) in (None, "offline"):  # nothing would take it: start the worker first
                results.append({"id": mid, "ok": False, "to": to, "err": f"{to} is not running; start it first."})
                continue
            if not RELAY.claim(mid, "resent"):
                results.append({"id": mid, "ok": False, "to": to, "err": "Already sent again or put aside."})
                continue
            try:
                if row is None:
                    RELAY.redeliver(mid, me)
                else:
                    rc, out, err = send_one(to, row["body"], False)
                    if rc != 0:
                        raise RelayError(err or out or f"rc={rc}", 502)
                results.append({"id": mid, "ok": True, "to": to})
            except Exception as e:  # RelayError, or the CLI missing or timing out: it did not go out
                RELAY.unclaim(mid)  # so it can be sent again later
                results.append({"id": mid, "ok": False, "to": to,
                                "err": str(e) if isinstance(e, RelayError) else f"{type(e).__name__}: {e}"})
        done = sum(r["ok"] for r in results)
        self.send_json({"ok": done > 0, "done": done, "results": results,
                        **({} if done else {"error": "; ".join(r["err"] for r in results)})}, 200 if done else 409)

    def forward_room(self, req):
        """A member's answer to your 1:1 message, passed into a group room it @mentions members of."""
        room, mid = ROOMS.get(req.get("id")), req.get("message")
        if not room:
            return self.send_json({"error": "No such room."}, 404)
        if not isinstance(mid, str) or not mid:
            return self.send_json({"error": "message must be a message id"}, 400)
        me = my_address()
        if not me:
            return self.send_json({"error": "Reason Network is not answering yet; try again."}, 503)
        rows = db_rows("select id, sender, recipient, reply_to, body, sent_at from messages where id = ?", (mid,))
        if not rows:
            return self.send_json({"error": "No such message."}, 404)
        self.send_json({"ok": True, "to": RELAY.forward(room, me, dict(rows[0]))})

    def send_room(self, req):
        """One `reason network send` per member; reports each member's result."""
        room = ROOMS.get(req.get("id"))
        body, fyi = req.get("body"), req.get("fyi", False)
        if not room:
            return self.send_json({"error": "No such room."}, 404)
        if not isinstance(body, str) or not body.strip() or not isinstance(fyi, bool):
            return self.send_json({"error": "body must be a non-empty string, fyi a boolean"}, 400)
        if room.get("group"):  # members get the lines they missed; @mentions wake only those members
            me = my_address()
            if not me:
                return self.send_json({"error": "Reason Network is not answering yet; try again."}, 503)
            results = RELAY.post(room, me, body.strip())
        else:
            results = []
            for to in room["members"]:
                rc, out, err = send_one(to, body.strip() + dm_note(to), fyi)
                results.append({"to": to, "ok": rc == 0, "err": "" if rc == 0 else (err or out or f"rc={rc}")})
        sent = sum(r["ok"] for r in results)
        self.send_json({"ok": sent > 0, "sent": sent, "results": results,
                        **({} if sent else {"error": "; ".join(r["err"] for r in results)})}, 200 if sent else 502)


class ChatServer(ThreadingHTTPServer):
    """One server per port. On Windows SO_REUSEADDR (which HTTPServer sets) lets a second server bind a port that
    is in use, and then one of them silently gets every request: a stale server answers the page. Bind exclusively
    there, so the second one fails. Elsewhere SO_REUSEADDR does not allow two listeners."""
    if sys.platform == "win32":
        allow_reuse_address = False

        def server_bind(self):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()


def bind(host, port):
    try:
        return ChatServer((host, port), Handler)
    except OSError as e:
        if e.errno in (98, 48, 10048, 10013) or getattr(e, "winerror", None) in (10048, 10013):  # address in use
            sys.exit(f"Port {port} is in use: another Reason Network Chat (or another program) is already running "
                     f"there. Stop it first, or set REASON_CHAT_PORT.")
        raise


def main():
    if not DB.exists():
        sys.exit(f"Reason Network database not found: {DB}\nInstall and start Reason Network first.")
    allow_ctrl_c()
    threading.Thread(target=who_loop, daemon=True).start()
    threading.Thread(target=CATALOG.get, daemon=True).start()  # `agy models` takes a few seconds
    threading.Thread(target=RELAY.run, args=(my_address,), daemon=True).start()
    threading.Thread(target=auto_loop, daemon=True).start()
    threading.Thread(target=discover_loop, daemon=True).start()
    srv = bind(HOST, PORT)
    print(f"Reason Network Chat on http://{HOST}:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
