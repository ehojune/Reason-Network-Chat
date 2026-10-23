"""Reason Network Chat: a chat-room view of Reason Network traffic on this computer.

Localhost only, Python standard library only. Reads the daemon's SQLite database read-only
(mode=ro) and `reason network who --all --json`; sends with `reason network send`; starts new
sessions through launcher.py. It never writes the database.
"""
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from launcher import Catalog, Launcher, LaunchError, allow_ctrl_c, base_env

HOST = "127.0.0.1"
PORT = int(os.environ.get("REASON_CHAT_PORT", "8765"))
HOME = Path.home()
DB = Path(os.environ.get("REASON_CHAT_DB", HOME / ".reason" / "network" / "network.db"))
STATIC = Path(__file__).with_name("index.html")
POLL_WHO = 3  # seconds between `who` refreshes
MAX_MESSAGES = 2000  # newest rows sent to the page per poll
MAX_BODY = 64 * 1024  # bytes accepted by a POST
ORIGINS = {f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"}
# Written into the page at load; every POST must echo it. Pages on other sites cannot read it.
TOKEN = secrets.token_urlsafe(32)
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
CATALOG = Catalog(REASON)
LAUNCHER = Launcher(REASON, CATALOG)


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
                else:
                    _who["error"] = err or f"rc={rc}"
        except Exception as e:  # keep the last good snapshot
            with _lock:
                _who["error"] = str(e)
        time.sleep(POLL_WHO)


def db_rows(sql):
    con = sqlite3.connect(f"{DB.resolve().as_uri()}?mode=ro", uri=True, timeout=2)
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(sql)]
    finally:
        con.close()


def state():
    msgs = db_rows("select * from (select id, sender, sender_agent, recipient, reply_to, body, wake, sent_at,"
                   f" read_at, held from messages order by sent_at desc limit {MAX_MESSAGES}) order by sent_at")
    known = {r["name"]: r for r in db_rows("select name, agent, cwd, doing, tier from sessions")}
    with _lock:
        who, who_err = _who["data"] or {}, _who["error"]
    person = who.get("person")
    me = f"{person}/terminal" if person else None  # address `reason network send` uses from a plain process
    live = who.get("sessions") or []
    seen = {s["address"] for s in live}
    sessions = [dict(s, live=True) for s in live]
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
                         "live": False})
        seen.add(addr)
    return {"team": who.get("team"), "me": me, "sessions": sessions, "messages": msgs,
            "launched": LAUNCHER.list(), "whoError": who_err, "now": int(time.time() * 1000)}


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
            page = STATIC.read_text(encoding="utf-8").replace("{{TOKEN}}", TOKEN)
            self.reply(200, page.encode("utf-8"), "text/html; charset=utf-8")
        elif url.path == "/api/state":
            try:
                self.send_json(state())
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
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
        if path not in ("/api/send", "/api/launch", "/api/stop"):
            return self.send_error(404)
        req = self.read_json()
        if req is None:
            return
        try:
            if path == "/api/send":
                self.send_message(req)
            elif path == "/api/launch":
                self.send_json(LAUNCHER.launch(req, live_names()))
            else:
                name = req.get("name")
                if not isinstance(name, str):
                    return self.send_json({"error": "name must be a string"}, 400)
                LAUNCHER.stop(name)
                self.send_json({"ok": True})
        except LaunchError as e:
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
        # The CLI has no `--` terminator: a body like "--help" would print help and exit 0.
        if body.startswith("-"):
            body = " " + body
        rc, out, err = run_reason("send", to, body, *(["--fyi"] if fyi else []), timeout=60)
        self.send_json({"ok": rc == 0, "rc": rc, "out": out, "err": err}, 200 if rc == 0 else 502)


def main():
    if not DB.exists():
        sys.exit(f"Reason Network database not found: {DB}\nInstall and start Reason Network first.")
    allow_ctrl_c()
    threading.Thread(target=who_loop, daemon=True).start()
    threading.Thread(target=CATALOG.get, daemon=True).start()  # `agy models` takes a few seconds
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Reason Network Chat on http://{HOST}:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
