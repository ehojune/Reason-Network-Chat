"""Rooms for Reason Network Chat: a saved set of sessions with its own timeline and a send that reaches all of them.

Stored in REASON_CHAT_HOME/rooms.json. Reason Network has no room concept: a room is a filter in this page plus a
fan-out of `reason network send`, one message per member.
"""
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path

ADDR_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}/[A-Za-z0-9._-]{1,128}$")
ID_RE = re.compile(r"^r-[0-9a-f]{8}$")
MAX_MEMBERS = 12
MAX_ROOMS = 100
MAX_NAME = 60


class RoomError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def clean_name(name):
    if not isinstance(name, str):
        raise RoomError("name must be a string.")
    name = " ".join(name.split())
    if not 0 < len(name) <= MAX_NAME:
        raise RoomError(f"Room name: 1 to {MAX_NAME} characters.")
    return name


class Rooms:
    def __init__(self, home):
        self.path = Path(home) / "rooms.json"
        self.lock = threading.Lock()
        self.rooms = []
        self.load()

    def load(self):
        try:
            items = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            items = []
        for r in items if isinstance(items, list) else []:
            try:
                room = {"id": r["id"], "name": clean_name(r["name"]), "created": int(r.get("created") or 0),
                        "members": [m for m in r["members"] if isinstance(m, str) and ADDR_RE.match(m)][:MAX_MEMBERS]}
            except (KeyError, TypeError, ValueError, RoomError):
                continue
            if ID_RE.match(str(room["id"])) and room["members"]:
                self.rooms.append(room)

    def commit(self, rooms):
        """Write the new list, then adopt it: a failed write leaves memory and disk as they were."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(rooms, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            raise RoomError(f"Could not save rooms: {e}", 500)
        self.rooms = rooms

    def list(self):
        with self.lock:
            return [dict(r, members=list(r["members"])) for r in self.rooms]

    def get(self, rid):
        with self.lock:
            r = next((r for r in self.rooms if r["id"] == rid), None)
            return dict(r, members=list(r["members"])) if r else None

    def upsert(self, req, known, me):
        """Create a room (no id) or rename / change the members of one."""
        name = clean_name(req.get("name"))
        members = req.get("members")
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members):
            raise RoomError("members must be a list of session addresses.")
        members = list(dict.fromkeys(m.strip() for m in members))
        if not 0 < len(members) <= MAX_MEMBERS:
            raise RoomError(f"Pick 1 to {MAX_MEMBERS} sessions.")
        rid = req.get("id")
        old = next((r for r in self.rooms if r["id"] == rid), None) if rid is not None else None
        kept = set(old["members"]) if old else set()  # a saved member may have left and never sent anything
        for m in members:
            if not ADDR_RE.match(m) or m == me or (m not in known and m not in kept):
                raise RoomError(f"Unknown session: {m}")
        with self.lock:
            if rid is None:
                if len(self.rooms) >= MAX_ROOMS:
                    raise RoomError(f"At most {MAX_ROOMS} rooms.", 429)
                room = {"id": f"r-{secrets.token_hex(4)}", "name": name, "members": members,
                        "created": int(time.time() * 1000)}
                rooms = self.rooms + [room]
            else:
                old = next((r for r in self.rooms if r["id"] == rid), None)
                if not old:
                    raise RoomError("No such room.", 404)
                room = dict(old, name=name, members=members)
                rooms = [room if r is old else r for r in self.rooms]
            self.commit(rooms)
            return dict(room, members=list(room["members"]))

    def delete(self, rid):
        with self.lock:
            rooms = [r for r in self.rooms if r["id"] != rid]
            if len(rooms) == len(self.rooms):
                raise RoomError("No such room.", 404)
            self.commit(rooms)
