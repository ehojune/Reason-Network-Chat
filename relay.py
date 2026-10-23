"""Group chat for rooms: members hear each other, and an @mention passes a reply on.

Reason Network agents answer only whoever sent them a message. In a group room this server is that sender:
it sends each member your message together with the room lines that member has not seen yet, and when a
member's reply names another member (@name) it passes the reply on to that member.

Loop guards: only you and explicit @mentions wake anyone; a chain of passed-on replies stops after MAX_HOPS;
each room passes on at most BUDGET replies per BUDGET_WINDOW seconds, then pauses until you write again.
"""
import collections
import json
import os
import re
import threading
import time
from pathlib import Path

MAX_HOPS = 3
BUDGET = 20
BUDGET_WINDOW = 600
CONTEXT_LINES = 12
CONTEXT_CHARS = 4000
LINE_CHARS = 600
KEEP = 3000  # records of sent messages kept on disk
RETRIES = 3  # attempts at one hand-off before it is reported as failed
MENTION_RE = re.compile(r"(?<![\w@/])@([A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?)")  # @name or @person/name


def short(addr):
    return addr.split("/", 1)[-1]


def handle(addr, room):
    """A member's name in the room: its session name, or person/name when two members share that name."""
    name = short(addr)
    return name if sum(short(m) == name for m in room["members"]) == 1 else addr


def label(addr, me, room):
    """How a speaker is named inside the room: the person by name, members by their handle."""
    return addr.split("/", 1)[0] if addr == me else handle(addr, room)


def clip(text, n):
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


class Relay:
    def __init__(self, home, rooms, db_rows, send_one):
        self.path = Path(home) / "relay.json"
        self.rooms, self.db_rows, self.send_one = rooms, db_rows, send_one
        self.lock = threading.Lock()  # state below; never held while a CLI send runs
        self.send_lock = threading.Lock()  # one delivery batch at a time (your message, or a scan)
        self.sent = {}  # message id -> {room, hop, core, speaker, to, at}
        self.seen = {}  # "room|member" -> sent_at of the newest room line that member has been given
        self.done = set()  # (reply id, member): passed on, or given up
        self.tries = collections.Counter()  # (reply id, member) -> failed attempts
        self.passes = collections.defaultdict(collections.deque)  # room -> times a reply was passed on
        self.paused = {}  # room -> "budget" | "hops"
        self.notice = {}  # room -> the last hand-off that failed for good, shown to you
        self.since = int(time.time() * 1000)  # replies from before this server started are not passed on
        self.load()

    # ---------- what this page sent, kept so its bubbles still show the plain message after a restart ----------
    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.sent = {k: v for k, v in data["sent"].items() if isinstance(v, dict)}
            self.seen = {k: int(v) for k, v in data["seen"].items()}
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            pass

    def save(self):
        if len(self.sent) > KEEP:
            for k in sorted(self.sent, key=lambda k: self.sent[k].get("at", 0))[: len(self.sent) - KEEP]:
                del self.sent[k]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"sent": self.sent, "seen": self.seen}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def view(self, ids):
        """For the page: the relay record of each listed message, paused rooms, and failed hand-offs."""
        with self.lock:
            rel = {i: {k: self.sent[i].get(k) for k in ("room", "hop", "core", "speaker")} for i in ids if i in self.sent}
            return rel, dict(self.paused), dict(self.notice)

    # ---------- composing ----------
    def lines_for(self, room, member, me, skip=None, current=None):
        """Room lines the member has not seen yet, oldest first: (sent_at, label, text). Left out because they
        follow as the message itself: `skip`, the reply being handed off, and `current`, the (speaker, text) being
        sent, whose copies to other members may already be in the database."""
        everyone = set(room["members"]) | {me}
        since = self.seen.get(f'{room["id"]}|{member}', 0)
        rows = self.db_rows("select id, sender, recipient, body, sent_at from messages where sent_at > ?"
                            " order by sent_at desc limit 400", (since,))
        # Your messages this member already got as its own copy (a room message is one row per member).
        got = {(v["speaker"], v["core"]) for v in self.sent.values() if v.get("room") == room["id"] and v.get("to") == member}
        out, keys = [], set()
        for r in rows:
            if r["id"] == skip:
                continue
            if r["sender"] not in everyone or r["recipient"] not in everyone or member in (r["sender"], r["recipient"]):
                continue  # not room traffic, or traffic the member took part in
            rec = self.sent.get(r["id"])
            if rec and (rec.get("hop", 0) > 0 or (rec["speaker"], rec["core"]) in got
                        or (rec["speaker"], rec["core"]) == current):
                continue  # a passed-on reply (the reply itself is a line), a copy this member got, or this message
            if rec:
                who, text = label(rec["speaker"], me, room), rec["core"]
            elif r["sender"] == me:
                who, text = f'{label(me, me, room)} → {handle(r["recipient"], room)}', r["body"]
            else:
                who, text = handle(r["sender"], room), r["body"]
            if (who, text) in keys:
                continue  # one line for a message sent to several members
            keys.add((who, text))
            out.append((r["sent_at"], who, text))
            if len(out) >= CONTEXT_LINES:
                break
        out.reverse()
        while out and sum(len(t) for _, _, t in out) > CONTEXT_CHARS:
            out.pop(0)
        return out

    def compose(self, room, member, me, speaker, core, skip=None):
        """The message for one member, and the timestamp of the newest room line it includes (0 if none)."""
        names = ", ".join([f"{label(me, me, room)} (person)"] + [handle(m, room) for m in room["members"]])
        head = (f'[Group room "{room["name"]}", relayed by Reason Network Chat]\n'
                f"Members: {names}. Everyone in the room reads your reply.\n"
                "Answer here only. To ask a member, write @name in your reply and the room passes it on; "
                "do not message members with Reason Network tools. Mention nobody when no answer is needed.")
        lines = self.lines_for(room, member, me, skip, (speaker, core))
        earlier = ("\nEarlier in the room:\n" + "\n".join(f"{who}: {clip(t, LINE_CHARS)}" for _, who, t in lines)) \
            if lines else ""
        return f"{head}{earlier}\n---\n{label(speaker, me, room)}: {core}", (lines[-1][0] if lines else 0)

    def deliver(self, room, member, me, speaker, core, hop, skip=None):
        """Compose and send one relayed message. The CLI runs without self.lock, so polling never waits on it."""
        with self.lock:
            body, newest = self.compose(room, member, me, speaker, core, skip)
        rc, out, err = self.send_one(member, body, False)
        if rc != 0:
            return False, err or out or f"rc={rc}"
        rows = self.db_rows("select id, sent_at from messages where sender = ? and recipient = ? and body = ?"
                            " order by sent_at desc limit 1", (me, member, body))
        with self.lock:
            if rows:
                self.sent[rows[0]["id"]] = {"room": room["id"], "hop": hop, "core": core, "speaker": speaker,
                                            "to": member, "at": rows[0]["sent_at"]}
            key = f'{room["id"]}|{member}'
            # Only as far as the lines it was given: a reply that landed while this was sent stays "missed".
            self.seen[key] = max(self.seen.get(key, 0), newest)
            self.save()
        return True, ""

    @staticmethod
    def mentioned(room, text, exclude=None):
        """Members named with @handle or @person/name. A session name two members share matches neither."""
        names = {handle(m, room).lower(): m for m in room["members"]}
        names.update({m.lower(): m for m in room["members"]})
        found = []
        for n in MENTION_RE.findall(text):
            m = names.get(n.lower().rstrip("."))
            if m and m != exclude and m not in found:
                found.append(m)
        return found

    # ---------- your message ----------
    def post(self, room, me, body):
        """Send your message to the members it @mentions, or to every member. Clears a pause."""
        targets = self.mentioned(room, body) or room["members"]
        with self.send_lock:
            with self.lock:
                self.paused.pop(room["id"], None)
                self.notice.pop(room["id"], None)
                self.passes[room["id"]].clear()  # you are back in the conversation: a fresh budget
            results = []
            for m in targets:
                ok, err = self.deliver(room, m, me, me, body, 0)
                results.append({"to": m, "ok": ok, "err": err})
        return results

    # ---------- passing replies on ----------
    def scan(self, me):
        """Pass on member replies that @mention another member; retry a failed hand-off a few times."""
        if not me:
            return
        with self.send_lock:
            with self.lock:
                if not self.sent:
                    return
                rows = self.db_rows("select id, sender, reply_to, body, sent_at from messages where recipient = ?"
                                    " and reply_to is not null and sent_at > ? order by sent_at", (me, self.since))
                todo = []
                for r in rows:
                    rec = self.sent.get(r["reply_to"])
                    room = self.rooms.get(rec["room"]) if rec else None
                    if not room or not room.get("group") or r["sender"] not in room["members"]:
                        continue
                    todo += [(room, r, rec, m) for m in self.mentioned(room, r["body"], exclude=r["sender"])
                             if (r["id"], m) not in self.done]
            for room, r, rec, m in todo:
                key, rid = (r["id"], m), room["id"]
                with self.lock:
                    if rec["hop"] >= MAX_HOPS:
                        self.paused[rid] = "hops"  # shown to you; your next message clears it
                        self.done.add(key)
                        continue
                    q, now = self.passes[rid], time.time()
                    while q and now - q[0] > BUDGET_WINDOW:
                        q.popleft()
                    if self.paused.get(rid) == "budget" or len(q) >= BUDGET:
                        self.paused[rid] = "budget"
                        self.done.add(key)  # dropped, not queued: your next message starts afresh
                        continue
                    q.append(now)
                ok, err = self.deliver(room, m, me, r["sender"], r["body"], rec["hop"] + 1, skip=r["id"])
                with self.lock:
                    if ok:
                        self.done.add(key)
                        continue
                    if now in q:
                        q.remove(now)  # a failed send does not use up the budget
                    self.tries[key] += 1
                    if self.tries[key] >= RETRIES:
                        self.done.add(key)
                        self.notice[rid] = f"{short(r['sender'])} → {short(m)}: {err}"

    def run(self, me_fn, every=2):
        while True:
            try:
                self.scan(me_fn())
            except Exception:  # keep relaying; one bad row must not stop the loop
                pass
            time.sleep(every)
