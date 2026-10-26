"""Start, restart, stop and adopt Reason Network workers the way the page does; post first in a group room.

    python rnc.py room list
    python rnc.py room send ROOM --as MEMBER "@name message"
    python rnc.py worker list
    python rnc.py worker start NAME [--folder DIR --agent codex|claude] [--model M] [--effort E] [--full-access]
    python rnc.py worker restart NAME
    python rnc.py worker stop NAME
    python rnc.py worker adopt NAME [--model M] [--effort E]
    python rnc.py text check --file UTF8_FILE

For agents this is the only supported way to (re)start a worker. Never run `reason network serve` yourself, and
never inside your own turn: a serve started from your shell inherits the turn's output handles, so the turn cannot
end and every message to the new worker waits on it (2026-10-24); and a `codex.cmd` ahead of codex.exe on your PATH
makes every Codex turn fail with "contains a cmd.exe special character". This goes through the running Reason
Network Chat server, which starts the worker outside your process tree with the page's recipe (the real CLI and the
model shim first on PATH, the stored user environment such as NODE_EXTRA_CA_CERTS, a log under logs/). When the
server is not running it uses the same launcher code here. Either way the worker stays managed by the page.

`start` with --folder and --agent starts a new worker; without them it starts a recorded one with its last
settings. `restart` stops a running worker (Ctrl+C, then whatever was left under it) and starts it again with its
recorded settings: the cure for a stuck one. `adopt` makes a worker started elsewhere managed here; --model and
--effort say what it runs with, for later restarts. Exit status 0 on success, 1 on a refusal, 2 on bad usage.

`room send` lets a member start a message in a group room instead of only answering. ROOM is a room id or name,
MEMBER the member's session name. It goes out like the member's answer: to the members it @mentions, with the room
envelope, within the room's limits, and answers come back to the member. It needs the running server, which takes
it only from the member's own session (this command running inside that worker's turn on this computer) or when the
room's settings allow the member to post first.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path
import urllib.error
import urllib.request
from text_guard import TextEncodingError, require_text

PORT = int(os.environ.get("REASON_CHAT_PORT", "8765"))
BASE = f"http://127.0.0.1:{PORT}"


class Refused(Exception):
    pass


# ---------- through the running server ----------
def server_token():
    """The page's token, or None when no Reason Network Chat server answers on PORT."""
    try:
        with urllib.request.urlopen(BASE + "/", timeout=5) as r:
            page = r.read().decode("utf-8", "replace")
    except (OSError, urllib.error.URLError):
        return None
    m = re.search(r'<meta name="reason-chat-token" content="([^"]+)"', page)
    return m.group(1) if m and m.group(1) != "{{TOKEN}}" else None


def call(token, path, body=None):
    req = urllib.request.Request(BASE + path, method="GET" if body is None else "POST",
                                 data=None if body is None else json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "Origin": BASE,
                                          "X-Reason-Chat-Token": token})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read() or b"{}").get("error")
        except ValueError:
            err = None
        raise Refused(err or f"HTTP {e.code}")


class ViaServer:
    def __init__(self, token):
        self.token = token

    def list(self):
        st = call(self.token, "/api/state")
        return st.get("launched") or [], st.get("foreignWorkers") or [], st.get("workerRecords") or []

    def start(self, name, a):
        if a.folder or a.agent:
            return call(self.token, "/api/launch", {"folder": a.folder, "agent": a.agent, "mode": "worker",
                                                    "model": a.model or "", "effort": a.effort or "", "name": name,
                                                    "fullAccess": a.full_access})
        r = call(self.token, "/api/workers/restart", {"names": [name]})["results"][0]
        if not r["ok"]:
            raise Refused(r.get("error") or "not started")
        return r

    def restart(self, name):
        return call(self.token, "/api/workers/reboot", {"name": name})

    def stop(self, name):
        return call(self.token, "/api/stop", {"name": name})

    def adopt(self, name, a):
        return call(self.token, "/api/workers/adopt", {"name": name, "model": a.model, "effort": a.effort})


# ---------- the same launcher code, here, when no server runs ----------
class Local:
    def __init__(self):
        import server  # finds the Reason CLI and builds the launcher over REASON_CHAT_HOME, starts nothing
        self.s = server
        self.L = server.LAUNCHER
        self.L.discover()  # our running workers back into the registry, the others listed as foreign

    def who(self):
        who = self.s.fresh_who()
        if not who:
            raise Refused("Reason Network is not answering (`reason network who` failed).")
        return who

    def list(self):
        return self.L.list(), self.L.list_foreign(), self.L.list_records()

    def start(self, name, a):
        if a.folder or a.agent:
            who = self.who()
            live = {s["name"] for s in who.get("sessions") or [] if s.get("status") != "offline"}
            if name in live and self.L.stale(name, who):
                live.discard(name)  # only a killed worker of ours holds the name
            return self.L.launch({"folder": a.folder, "agent": a.agent, "mode": "worker", "model": a.model or "",
                                  "effort": a.effort or "", "name": name, "fullAccess": a.full_access}, live)
        r = self.L.restart([name], self.s.restart_blocked(self.who()))["results"][0]
        if not r["ok"]:
            raise Refused(r.get("error") or "not started")
        return r

    def restart(self, name):
        where = self.L.running_here(name)
        if where == "managed":
            return self.L.relaunch(name)
        if where == "foreign":
            raise Refused("It was started outside the page: adopt it first (python rnc.py worker adopt NAME).")
        r = self.L.restart([name], self.s.restart_blocked(self.who()))["results"][0]
        if not r["ok"]:
            raise Refused(r.get("error") or "not started")
        return r

    def stop(self, name):
        self.L.stop(name)
        return {"ok": True}

    def adopt(self, name, a):
        return self.L.adopt(name, a.model, a.effort)


def find_room(rooms, key):
    """A room by id, else by its exact name (refused when two rooms share it)."""
    by_id = [r for r in rooms if r.get("id") == key]
    by_name = [r for r in rooms if r.get("name") == key]
    if by_id:
        return by_id[0]
    if len(by_name) == 1:
        return by_name[0]
    raise Refused("Two rooms have that name: use the room id (python rnc.py room list)." if by_name
                  else f"No room {key!r} (python rnc.py room list).")


def room_main(a, token):
    if not token:
        raise Refused(f"Reason Network Chat is not running on port {PORT}; group rooms are relayed by its server.")
    rooms = call(token, "/api/state").get("rooms") or []
    if a.action == "list":
        for r in rooms:
            names = ", ".join(m.split("/", 1)[-1] for m in r.get("members") or [])
            first = ", ".join(m.split("/", 1)[-1] for m in r.get("allowPost") or [])
            print(f"{r['id']}  {'group' if r.get('group') else 'plain'}  {r['name']}  [{names}]"
                  + (f"  may post without proof: {first}" if first else ""))
        return 0
    room = find_room(rooms, a.room)
    r = call(token, "/api/rooms/post", {"id": room["id"], "as": a.as_, "body": a.message})
    print(f"posted to {room['name']} as {a.as_} -> {', '.join(t.split('/', 1)[-1] for t in r.get('to') or [])}")
    return 0


def parse(argv):
    p = argparse.ArgumentParser(prog="rnc.py", description="Manage Reason Network workers the way the page does.")
    sub = p.add_subparsers(dest="what", required=True)
    tx = sub.add_parser("text", help="check a UTF-8 file before a message or an external post")
    tx.add_argument("action", choices=["check"])
    tx.add_argument("--file", required=True, help="UTF-8 text file; - reads UTF-8 bytes from stdin")
    rm = sub.add_parser("room", help="list group rooms, or post first in one as a member")
    rm.add_argument("action", choices=["list", "send"])
    rm.add_argument("room", nargs="?", help="room id or name")
    rm.add_argument("message", nargs="?", help="the message; name who should get it with @name")
    rm.add_argument("--as", dest="as_", help="the member you are (your own session's name)")
    w = sub.add_parser("worker", help="start, restart, stop, adopt or list workers")
    w.add_argument("action", choices=["list", "start", "restart", "stop", "adopt"])
    w.add_argument("name", nargs="?")
    w.add_argument("--folder", help="absolute folder the worker works in (new workers)")
    w.add_argument("--agent", choices=["codex", "claude", "antigravity"], help="agent of a new worker")
    w.add_argument("--model")
    w.add_argument("--effort")
    w.add_argument("--full-access", action="store_true", help="run without approvals (dangerous by design)")
    a = p.parse_args(argv)
    if a.what == "text":
        return a
    if a.what == "room":
        if a.action == "send" and not (a.room and a.message and a.as_):
            p.error('room send needs ROOM, --as MEMBER and "MESSAGE"')
        a.name = a.room
        return a
    if a.action != "list" and not a.name:
        p.error(f"worker {a.action} needs a NAME")
    if a.action == "start" and bool(a.folder) != bool(a.agent):
        p.error("a new worker needs both --folder and --agent (without them a recorded worker is started)")
    return a


def main(argv=None):
    a = parse(sys.argv[1:] if argv is None else argv)
    if a.what == "text":
        try:
            data = sys.stdin.buffer.read() if a.file == "-" else Path(a.file).read_bytes()
            require_text(data.decode("utf-8-sig"))
        except (OSError, UnicodeError, TextEncodingError) as e:
            print(f"Text check failed: {e}", file=sys.stderr)
            return 1
        print("UTF-8 text check passed (heuristic; compare the published text with the original too).")
        return 0
    token = server_token()
    try:
        if a.what == "room":
            return room_main(a, token)
        via = ViaServer(token) if token else Local()
        where = f"via the server on port {PORT}" if token else "here (no server running)"
        if a.action == "list":
            launched, foreign, records = via.list()
            running = {w["name"] for w in launched}
            for w in launched:
                print(f"managed  {w['name']:<24} {w.get('family') or '?':<7} {w.get('model') or '-'} / "
                      f"{w.get('effort') or '-'}{' / full access' if w.get('fullAccess') else ''}  {w.get('cwd') or ''}")
            for w in foreign:
                print(f"outside  {w['name']:<24} {w.get('family') or '?':<7} (adopt to manage)  {w.get('cwd') or ''}")
            for r in records:
                if r["name"] not in running and r["name"] not in {w["name"] for w in foreign}:
                    print(f"stopped  {r['name']:<24} {r.get('family') or '?':<7} {r.get('model') or '-'} / "
                          f"{r.get('effort') or '-'}  {r.get('cwd') or ''}")
            return 0
        getattr(via, a.action)(a.name, a) if a.action in ("start", "adopt") else getattr(via, a.action)(a.name)
        print(f"{a.action} {a.name}: ok ({where})")
        return 0
    except Refused as e:
        print(f"{a.action} {a.name or ''}: refused: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # LaunchError and the like from the local launcher
        if type(e).__name__ == "LaunchError":
            print(f"{a.action} {a.name or ''}: refused: {e}", file=sys.stderr)
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
