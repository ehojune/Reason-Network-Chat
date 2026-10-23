"""reason-chat: a chat-room view of Reason Network traffic on this computer.

Localhost only, Python standard library only. Reads the daemon's SQLite database read-only
(mode=ro) and `reason network who --all --json`; sends with `reason network send`.
It never writes the database.
"""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HOST = "127.0.0.1"
PORT = int(os.environ.get("REASON_CHAT_PORT", "8765"))
HOME = Path.home()
DB = Path(os.environ.get("REASON_CHAT_DB", HOME / ".reason" / "network" / "network.db"))
STATIC = Path(__file__).with_name("index.html")
POLL_WHO = 3  # seconds between `who` refreshes
MAX_MESSAGES = 2000  # newest rows sent to the page per poll
MAX_BODY = 64 * 1024  # bytes accepted by /api/send
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


def run_reason(*args, timeout=30):
    # Behind a TLS-inspecting proxy the CLI needs NODE_EXTRA_CA_CERTS; it is inherited from os.environ.
    p = subprocess.run([REASON, "network", *args], capture_output=True, timeout=timeout,
                       creationflags=NOWIN)
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
            "whoError": who_err, "now": int(time.time() * 1000)}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
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
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self.reply(200, STATIC.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/state":
            try:
                self.send_json(state())
            except Exception as e:
                self.send_json({"error": str(e)}, 500)
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.host_ok():
            return
        if urlsplit(self.path).path != "/api/send":
            return self.send_error(404)
        # Only same-origin JSON: a cross-site form cannot set this content type without a preflight.
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.send_json({"error": "json only"}, 415)
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.send_json({"error": "Content-Length required"}, 411)
        if not 0 < n <= MAX_BODY:
            return self.send_json({"error": "body too large"}, 413)
        try:
            req = json.loads(self.rfile.read(n).decode("utf-8"))
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
        except Exception as e:
            self.send_json({"error": str(e)}, 500)


def main():
    if not DB.exists():
        sys.exit(f"Reason Network database not found: {DB}\nInstall and start Reason Network first.")
    threading.Thread(target=who_loop, daemon=True).start()
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"reason-chat on http://{HOST}:{PORT}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
