"""Group chat for rooms: members hear each other, and an @mention passes a reply on.

Reason Network agents answer only whoever sent them a message. In a group room this server is that sender:
it sends a member your message together with the room lines that member has not seen yet, and when a member's
reply names another member (@name) it passes the reply on to that member.

Who receives what: your message goes to the members it @mentions (@all / @모두 for everyone), else to the room's
default recipient, else nowhere (the page asks you to mention someone). A member's answer goes to the members it
@mentions and, without being asked, back to the member whose message it answers (one level: an answer that came back
this way does not come back again). An empty or "nothing to add" answer ("-", "(해당 없음)", "N/A": no letter or digit, or
such a placeholder) goes nowhere; a short real answer such as "4" still goes back.

A 1:1 message (sent to one session, outside the room) is not relayed, and neither is the answer to it. When such an
answer @mentions members of a group room the agent is in, you can forward it there (`forward`): it is then passed on
as if it had answered a room message, once, within the room's limits.

A worker's failure ("The Codex worker failed: …", which `serve` sends when it could not run the turn) is not an
answer: it is passed on to nobody, and never comes back to an asker. Passing failures on once made workers whose
own turns failed answer each other's failures, 36 hand-offs in half a minute (2026-10-24). You can send the
original message again (`redeliver`); `settled` remembers what you sent again or put aside.

Loop guards, per room (env defaults, each room can set its own or none): a chain of passed-on replies holds after
MAX_HOPS until you continue it; at most BUDGET hand-offs per BUDGET_WINDOW seconds, the rest wait in a queue and go
out as the window frees up. Nothing is dropped: queued hand-offs, the scan cursor and what was passed on are kept in
relay.json, so a restart neither loses nor repeats a hand-off.
"""
import collections
import contextlib
import functools
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from storage import atomic_json, file_lock


def _env_int(name, default):
    try:
        v = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return v if v > 0 else default


MAX_HOPS = _env_int("REASON_CHAT_MAX_HOPS", 100)
BUDGET = _env_int("REASON_CHAT_BUDGET", 300)
BUDGET_WINDOW = _env_int("REASON_CHAT_BUDGET_WINDOW", 600)
LIMIT_MAX = 100000  # largest per-room limit; None means no limit
RESUME_MS = 24 * 3600 * 1000  # after a restart, replies at most this old are still passed on
CONTEXT_LINES = 12
CONTEXT_CHARS = 4000
LINE_CHARS = 600
KEEP = 3000  # records of sent messages kept on disk
RETRIES = 3  # attempts at one hand-off before it is reported as failed
# @name or @person/name (ASCII, so "@codex-worker1에게" still names codex-worker1), or @모두 / @전체
# The same pattern as MENTION_RE in index.html, so the page shows who the server will send to ("안녕@b-claude" names
# b-claude; "pat@b-claude" does not).
MENTION_RE = re.compile(r"(?<![A-Za-z0-9_@/])@([A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?|모두|전체)")
EVERYONE = {"all", "everyone", "모두", "전체"}
# Placeholders that mean "nothing to say". Short real answers ("4", "no", "없음") are answers and still go back.
NO_ANSWER = {"(해당 없음)", "해당 없음", "n/a", "(n/a)", "(none)", "no answer", "(no answer)", "nothing to add"}


def no_answer(text):
    """An answer that says nothing: passed on to nobody (it would only start an acknowledgement ping-pong). That is
    text with no letter or digit ("-", "—", "...") or a placeholder phrase, never a short answer such as "4"."""
    t = " ".join(str(text or "").split()).lower()
    return not re.search(r"\w", t) or t.strip(".") in NO_ANSWER


DM_MARK = "\n\n(1:1 message from "


def dm_note(person):
    """The line the page adds to a message sent to one session that is in a group room, so the agent can tell a 1:1
    message (its answer is not relayed) from a room message (which comes in the room envelope)."""
    return (f"{DM_MARK}{person}, not from a group room: your answer reaches only {person}. "
            f"@mentions in it are not passed on to other members unless {person} forwards it to the room.)")


# What `reason network serve` (checked in 0.12.10) replies when it could not run the turn: a thrown error becomes
# "The <Codex|Claude Code|Grok> worker failed: …"; a Codex turn that failed, "Codex failed: …"; an exit with no
# output, "<codex|grok> exited with N".
FAILURE_RE = re.compile(r"^(The [A-Za-z][A-Za-z ]{0,30} worker failed: |Codex failed: |(codex|grok) exited with -?\d+\s*$|You've hit your (session|usage) limit\b)")


def worker_failure(text):
    """A worker's reply saying it could not run the turn, not an answer."""
    return bool(FAILURE_RE.match(str(text or "").lstrip()))


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


def held(room, item):
    """A queued hand-off past the room's current hop limit waits for you (unless you sent it on with "Send all now")."""
    hops = limit(room, "hops")
    return not item.get("force") and hops is not None and item["hop"] > hops


def limit(room, key):
    """A room's hop or budget limit: its own setting (None = no limit), else the default."""
    own = room.get("limits") or {}
    if key in own:
        return own[key]
    return MAX_HOPS if key == "hops" else BUDGET


class RelayError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def serialized(method):
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.transaction():
            return method(self, *args, **kwargs)
    return wrapped


class Relay:
    def __init__(self, home, rooms, db_rows, send_one):
        self.path = Path(home) / "relay.json"
        self.rooms, self.db_rows, self.send_one = rooms, db_rows, send_one
        self.lock = threading.Lock()  # state below; never held while a CLI send runs
        self.send_lock = threading.Lock()  # one delivery batch at a time (your message, or a scan)
        self.sent = {}  # message id -> {room, hop, core, speaker, to, at}
        self.seen = {}  # "room|member" -> sent_at of the newest room line that member has been given
        self.done = {}  # (reply id, member) -> reply sent_at: queued (and so settled for the cursor), or given up
        self.tries = collections.Counter()  # (reply id, member) -> failed attempts
        self.passes = collections.defaultdict(collections.deque)  # room -> times a hand-off went out
        self.queue = {}  # room -> [{reply, to, sender, body, hop, at, held, force}] in arrival order
        self.notice = {}  # room -> the last hand-off that failed for good, shown to you
        self.forwarded = {}  # message id -> {room, to, at}: 1:1 answers you forwarded into a room (once each)
        self.settled = {}  # message id -> {how: resent|dismissed, at}: unanswered or failed messages you dealt with
        self.since = None  # scan cursor (ms): replies before it are settled
        self.revision = None
        self.load()
        now = int(time.time() * 1000)
        # Resume where the last run stopped, so replies that came in while the server was down are passed on.
        self.since = max(self.since, now - RESUME_MS) if self.since is not None else now

    # ---------- relay.json: what this page sent, the cursor, settled hand-offs and the queue ----------
    def read(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def load(self):
        data = self.read()
        self.revision = data.get("revision")
        try:
            self.sent = {k: v for k, v in (data.get("sent") or {}).items() if isinstance(v, dict)}
            self.seen = {k: int(v) for k, v in (data.get("seen") or {}).items()}
            since = data.get("since")
            self.since = int(since) if isinstance(since, (int, float)) else None
            self.done = {tuple(k.split("\t", 1)): int(v) for k, v in (data.get("done") or {}).items() if "\t" in k}
            self.queue = {rid: [i for i in items if isinstance(i, dict) and {"reply", "to", "sender", "body", "hop"} <= set(i)]
                          for rid, items in (data.get("queue") or {}).items() if isinstance(items, list)}
            self.queue = {rid: items for rid, items in self.queue.items() if items}
            self.forwarded = {k: v for k, v in (data.get("forwarded") or {}).items() if isinstance(v, dict)}
            self.settled = {k: v for k, v in (data.get("settled") or {}).items() if isinstance(v, dict)}
        except (ValueError, TypeError, AttributeError):
            pass

    @contextlib.contextmanager
    def transaction(self):
        """One writer/delivery batch per home, across ports and processes. Polling stays read-only."""
        with self.send_lock:
            try:
                with file_lock(self.path.with_suffix(".delivery.lock")):
                    with self.lock:
                        if self.read().get("revision") != self.revision:
                            previous = self.since
                            self.load()
                            self.since = self.since if self.since is not None else previous
                    yield
            except TimeoutError as exc:
                raise RelayError("Another server is delivering; try again shortly.", 409) from exc

    def save(self, unsettle=(), strict=False):
        with file_lock(self.path.with_suffix(".state.lock")):
            self._save_locked(unsettle, strict)

    def _save_locked(self, unsettle=(), strict=False):
        """Read, merge, write: records another writer added since are kept (call with self.lock held). `unsettle`:
        settled records to remove, which the merge would otherwise bring back from the file."""
        disk = self.read()
        sent = {k: v for k, v in (disk.get("sent") or {}).items() if isinstance(v, dict)} if isinstance(disk.get("sent"), dict) else {}
        sent.update(self.sent)
        if len(sent) > KEEP:
            for k in sorted(sent, key=lambda k: sent[k].get("at", 0))[: len(sent) - KEEP]:
                del sent[k]
        seen = {}
        for k, v in (disk.get("seen") or {}).items() if isinstance(disk.get("seen"), dict) else ():
            try:
                seen[k] = int(v)
            except (TypeError, ValueError):
                pass
        for k, v in self.seen.items():
            seen[k] = max(seen.get(k, 0), v)
        fwd = {k: v for k, v in (disk.get("forwarded") or {}).items() if isinstance(v, dict)} \
            if isinstance(disk.get("forwarded"), dict) else {}
        fwd.update(self.forwarded)
        if len(fwd) > KEEP:
            for k in sorted(fwd, key=lambda k: fwd[k].get("at", 0))[: len(fwd) - KEEP]:
                del fwd[k]
        settled = {k: v for k, v in (disk.get("settled") or {}).items() if isinstance(v, dict)} \
            if isinstance(disk.get("settled"), dict) else {}
        settled.update(self.settled)
        for k in unsettle:
            settled.pop(k, None)
        if len(settled) > KEEP:
            for k in sorted(settled, key=lambda k: settled[k].get("at", 0))[: len(settled) - KEEP]:
                del settled[k]
        self.sent, self.seen, self.forwarded, self.settled = sent, seen, fwd, settled
        revision = uuid.uuid4().hex
        data = {"revision": revision, "sent": sent, "seen": seen, "since": self.since,
                "done": {f"{a}\t{b}": at for (a, b), at in self.done.items()}, "queue": self.queue, "forwarded": fwd,
                "settled": settled}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(self.path, data)
            self.revision = revision
        except OSError as exc:
            if strict:
                raise RelayError(f"Could not save hand-off before sending: {exc}", 500)

    def view(self, ids):
        """For the page: the relay record of each listed message, queued hand-offs per room, failed hand-offs."""
        with self.lock:
            rel = {i: {k: self.sent[i].get(k) for k in ("room", "hop", "core", "speaker")} for i in ids if i in self.sent}
            queued = {}
            for rid, items in self.queue.items():
                room = self.rooms.get(rid)
                n = sum(1 for i in items if room and held(room, i))
                if items:
                    queued[rid] = {"waiting": len(items) - n, "held": n}
            return rel, queued, dict(self.notice)

    def forwarded_view(self, ids):
        """For the page: {message id: {room, to}} for the listed 1:1 answers you forwarded into a room."""
        with self.lock:
            return {i: {"room": self.forwarded[i].get("room"), "to": self.forwarded[i].get("to") or []}
                    for i in ids if i in self.forwarded}

    def settled_view(self, ids):
        """For the page: {message id: {how, at}} for the listed messages you sent again or put aside."""
        with self.lock:
            return {i: dict(self.settled[i]) for i in ids if i in self.settled}

    @serialized
    def claim(self, mid, how):
        """Mark a message dealt with, unless it already is: one "Send again" per message, even from two clicks."""
        with self.lock:
            if mid in self.settled:
                return False
            self.settled[mid] = {"how": how, "at": int(time.time() * 1000)}
            self.save()
            return True

    @serialized
    def unclaim(self, mid):
        with self.lock:
            self.settled.pop(mid, None)
            self.save(unsettle=(mid,))

    def recipient_of(self, mid):
        """The member a relayed message went to, or None when this page did not relay it."""
        with self.lock:
            return (self.sent.get(mid) or {}).get("to")

    def redeliver(self, mid, me):
        """Send a relayed message again as it was (same room, member, speaker, text and hop): your "Send again" after
        a worker failed on it or took it without answering. None when `mid` is not a message this page relayed."""
        with self.lock:
            rec = dict(self.sent.get(mid) or {})
        if not rec:
            return None
        if rec.get("hop", 0) > 0 and worker_failure(rec.get("core")):  # a member's failure an older version passed on
            raise RelayError("That was a worker's failure passed on, not a message to send again.", 409)
        room = self.rooms.get(rec.get("room"))
        if not room or not room.get("group") or rec.get("to") not in room["members"]:
            raise RelayError("That room is gone, or the member left it.", 409)
        with self.transaction():
            ok, err = self.deliver(room, rec["to"], me, rec["speaker"], rec["core"], rec.get("hop", 0),
                                   implicit=bool(rec.get("implicit")))
        if not ok:
            raise RelayError(err or "The message could not be sent.", 502)
        return rec["to"]

    # ---------- composing ----------
    def lines_for(self, room, member, me, skip=None, current=None):
        """Room lines the member has not seen yet, oldest first: (sent_at, label, text). Left out because they
        follow as the message itself: `skip`, the reply being handed off, and `current`, the (speaker, text) being
        sent, whose copies to other members may already be in the database."""
        everyone = sorted(set(room["members"]) | {me})
        since = self.seen.get(f'{room["id"]}|{member}', 0)
        marks = ",".join("?" * len(everyone))
        # Room traffic the member was not part of, filtered in SQL so other traffic cannot crowd it out of the limit.
        rows = self.db_rows("select id, sender, recipient, body, sent_at from messages where sent_at > ?"
                            f" and sender in ({marks}) and recipient in ({marks}) and sender != ? and recipient != ?"
                            " order by sent_at desc limit 200", (since, *everyone, *everyone, member, member))
        # Your messages this member already got as its own copy (a room message is one row per member).
        got = {(v["speaker"], v["core"]) for v in self.sent.values() if v.get("room") == room["id"] and v.get("to") == member}
        out, keys = [], set()
        for r in rows:
            if r["id"] == skip or (r["sender"] != me and worker_failure(r["body"])):  # your own text is kept
                continue
            if r["sender"] not in everyone or r["recipient"] not in everyone or member in (r["sender"], r["recipient"]):
                continue  # not room traffic, or traffic the member took part in
            rec = self.sent.get(r["id"])
            if rec and (rec.get("hop", 0) > 0 or (rec["speaker"], rec["core"]) in got
                        or (rec["speaker"], rec["core"]) == current):
                continue  # a passed-on reply (the reply itself is a line), a copy this member got, or this message
            if rec:
                who, text = label(rec["speaker"], me, room), rec["core"]
            elif r["sender"] == me:  # your 1:1 message, without the note meant for its recipient
                who, text = f'{label(me, me, room)} → {handle(r["recipient"], room)}', r["body"].split(DM_MARK, 1)[0]
            else:
                who, text = handle(r["sender"], room), r["body"]
            if (who, text) in keys:
                continue  # one line for a message sent to several members
            keys.add((who, text))
            out.append((r["sent_at"], who, clip(text, LINE_CHARS)))
            if len(out) >= CONTEXT_LINES:
                break
        out.reverse()
        while out and sum(len(t) for _, _, t in out) > CONTEXT_CHARS:
            out.pop(0)
        return out

    def compose(self, room, member, me, speaker, core, skip=None, implicit=False):
        """The message for one member, and the timestamp of the newest room line it includes (0 if none).
        `implicit`: this is an answer passed back to its asker, so the member's reply does not come back by itself."""
        person, asker = label(me, me, room), label(speaker, me, room)
        names = ", ".join([f"{person} (person)"] + [handle(m, room) for m in room["members"]])
        if implicit:
            back = "This answer was passed back to you automatically. Your reply reaches only the members you @mention."
        elif speaker == me:
            back = f"Your answer goes back to {asker} automatically."
        else:
            back = (f"Your answer goes back to {asker} automatically; "
                    f"{asker}'s reply to it reaches you only if it @mentions you.")
        head = (f'[Group room "{room["name"]}", relayed by Reason Network Chat]\n'
                f"Members: {names}.\n"
                f"{back}\n"
                "To ask anyone else, @name them; their answers come back to you. Reply `-` if no answer is needed.\n"
                f"Answers to 1:1 messages are not passed on. {person} sees the whole room. "
                "Do not message members with Reason Network tools.\n"
                'The message to answer is after "---"; lines under "Earlier in the room" are clipped context.')
        lines = self.lines_for(room, member, me, skip, (speaker, core))
        earlier = ("\nEarlier in the room:\n" + "\n".join(f"{who}: {t}" for _, who, t in lines)) \
            if lines else ""
        return f"{head}{earlier}\n---\n{label(speaker, me, room)}: {core}", (lines[-1][0] if lines else 0)

    def deliver(self, room, member, me, speaker, core, hop, skip=None, skip_at=0, item=None, implicit=False):
        """Compose and send one relayed message. The CLI runs without self.lock, so polling never waits on it.
        A queued `item` leaves the queue in the same save that records the message as sent: a restart in between
        cannot send it twice."""
        with self.lock:
            flight = item.get("flight") if item is not None else None
            created = not flight
            if flight:
                body, newest = flight["body"], flight["newest"]
            else:
                body, newest = self.compose(room, member, me, speaker, core, skip, implicit)
                if item is not None:
                    # A unique envelope identifies this exact delivery in the daemon's read-only database.
                    body = body.replace("\nMembers:", f"\nDelivery: {uuid.uuid4().hex}\nMembers:", 1)
                    item["flight"] = {"body": body, "newest": newest, "me": me}
            if item is not None:
                forced = item.pop("force", None)  # consume one explicit retry durably before the side effect
                try:
                    self.save(strict=True)
                except Exception:
                    if created:
                        item.pop("flight", None)  # no send was attempted; storage recovery can retry normally
                    if forced is not None:
                        item["force"] = forced
                    raise
        try:
            rc, out, err = self.send_one(member, body, False)
        except Exception as e:  # e.g. the CLI timed out: a failed attempt like any other, so retries stay bounded
            with self.lock:
                if item is not None:
                    # An exception may have happened after delivery: retain the claim for reconciliation.
                    item.pop("force", None)  # one explicit retry is not permission to retry forever
                    self.notice[room["id"]] = "Delivery outcome unknown; inspect the queue before retrying with Send all now."
                    self.save()
            return False, f"{type(e).__name__}: {e}"
        if rc != 0:
            with self.lock:
                if item is not None:
                    item.pop("flight", None)
                    self.save()
            return False, err or out or f"rc={rc}"
        rows = self.db_rows("select id, sent_at from messages where sender = ? and recipient = ? and body = ?"
                            " order by sent_at desc limit 1", (me, member, body))
        with self.lock:
            if item is not None and not rows:
                item.pop("force", None)
                self.notice[room["id"]] = "Delivery accepted; waiting for its database receipt."
                self.save()
                return False, "Waiting for delivery receipt"
            if rows:
                self.sent[rows[0]["id"]] = {"room": room["id"], "hop": hop, "core": core, "speaker": speaker,
                                            "to": member, "at": rows[0]["sent_at"], "implicit": implicit}
            key = f'{room["id"]}|{member}'
            # Only as far as the lines it was given (a reply that landed while this was sent stays "missed"),
            # plus the handed-off reply itself, which it just got as the message.
            self.seen[key] = max(self.seen.get(key, 0), newest, skip_at)
            if item is not None:
                self.dequeue(room["id"], item)
            self.save()
        return True, ""

    def reconcile(self, room, me, item):
        """Recover a delivery whose process ended between the CLI send and saving the dequeue. Lock held."""
        flight = item.get("flight")
        if not flight:
            return False
        if flight.get("me") != me:
            return False
        rows = self.db_rows("select id, sent_at from messages where sender = ? and recipient = ? and body = ?"
                            " order by sent_at desc limit 1", (me, item["to"], flight["body"]))
        if not rows:
            return False
        row = rows[0]
        self.sent[row["id"]] = {"room": room["id"], "hop": item["hop"], "core": item["body"],
                                "speaker": item["sender"], "to": item["to"], "at": row["sent_at"],
                                "implicit": bool(item.get("implicit"))}
        key = f'{room["id"]}|{item["to"]}'
        self.seen[key] = max(self.seen.get(key, 0), flight.get("newest", 0), item.get("at", 0))
        self.dequeue(room["id"], item)
        self.notice.pop(room["id"], None)
        self.save()
        return True

    def dequeue(self, rid, item):
        """Take one item off a room's queue (call with self.lock held)."""
        items = self.queue.get(rid) or []
        if item in items:
            items.remove(item)
        if not items:
            self.queue.pop(rid, None)

    @staticmethod
    def mentioned(room, text, exclude=None, everyone=False):
        """Members named with @handle or @person/name (a session name two members share matches neither);
        with `everyone`, @all / @모두 names every member."""
        names = {handle(m, room).lower(): m for m in room["members"]}
        names.update({m.lower(): m for m in room["members"]})
        found = []
        for n in MENTION_RE.findall(text):
            n = n.lower().rstrip(".")
            for m in (room["members"] if everyone and n in EVERYONE else [names.get(n)]):
                if m and m != exclude and m not in found:
                    found.append(m)
        return found

    @classmethod
    def targets(cls, room, body):
        """Who your message goes to: the members it @mentions, else the room's default recipient, else nobody."""
        found = cls.mentioned(room, body, everyone=True)
        if found:
            return found
        default = room.get("defaultTo")
        return [default] if default in room["members"] else []

    # ---------- your message ----------
    def post(self, room, me, body):
        """Send your message to the members it @mentions (or the default recipient). A fresh hand-off budget."""
        targets = self.targets(room, body)
        if not targets:
            raise RelayError("Mention who should receive it (@name, or @all for everyone), "
                             "or set a default recipient for this room.")
        with self.transaction():
            with self.lock:
                self.notice.pop(room["id"], None)
                self.passes[room["id"]].clear()  # you are back in the conversation: a fresh budget
            results = []
            for m in targets:
                ok, err = self.deliver(room, m, me, me, body, 0)
                results.append({"to": m, "ok": ok, "err": err})
        return results

    @serialized
    def flush(self, rid):
        """Send everything queued in a room now, past its budget and hop limit (your explicit go-ahead)."""
        with self.lock:
            items = self.queue.get(rid) or []
            for i in items:
                i["force"] = True
            if items:
                self.save()
            return len(items)

    # ---------- a 1:1 answer, forwarded by you ----------
    @serialized
    def forward(self, room, me, msg):
        """Pass a member's answer to a 1:1 message of yours on to the members it @mentions, as if it had answered a
        room message: queued like any hand-off (hop 1, the member as speaker) and sent within the room's limits.
        Once per message. Returns the members it goes to."""
        if not room.get("group"):
            raise RelayError("Only a group room passes answers on.")
        if msg["recipient"] != me or msg["sender"] not in room["members"]:
            raise RelayError("Only a room member's message to you can be forwarded.")
        if worker_failure(msg["body"]):
            raise RelayError("That is the worker's failure, not an answer: send your message again instead.")
        targets = self.mentioned(room, msg["body"], exclude=msg["sender"])
        if not targets:
            raise RelayError("It mentions no other member of this room.")
        with self.lock:
            if msg.get("reply_to") in self.sent:
                raise RelayError("This answers a room message: the room passes it on by itself.", 409)
            if msg["id"] in self.forwarded:
                raise RelayError("Already forwarded.", 409)
            items = self.queue.setdefault(room["id"], [])
            for m in targets:
                items.append({"reply": msg["id"], "to": m, "sender": msg["sender"], "body": msg["body"], "hop": 1,
                              "at": msg["sent_at"], "implicit": False})
            self.forwarded[msg["id"]] = {"room": room["id"], "to": targets, "at": int(time.time() * 1000)}
            self.save()
        return targets

    # ---------- passing replies on ----------
    def take(self, room):
        """Use one hand-off of the room's budget; None when the window is full (call with self.lock held)."""
        q, now = self.passes[room["id"]], time.time()
        while q and now - q[0] > BUDGET_WINDOW:
            q.popleft()
        budget = limit(room, "budget")
        if budget is not None and len(q) >= budget:
            return None
        q.append(now)
        return now

    def scan(self, me):
        """Queue member replies that @mention another member, then send what the room's limits allow."""
        if not me:
            return
        with self.transaction():
            with self.lock:
                if not self.sent and not self.queue:
                    return
                rows = self.db_rows("select id, sender, reply_to, body, sent_at from messages where recipient = ?"
                                    " and reply_to is not null and sent_at >= ? order by sent_at", (me, self.since))
                changed = False
                for r in rows:
                    rec = self.sent.get(r["reply_to"])
                    room = self.rooms.get(rec["room"]) if rec else None
                    targets = [] if not room or not room.get("group") or r["sender"] not in room["members"] \
                        else self.answer_targets(room, rec, r)
                    for m, implicit in targets:
                        if (r["id"], m) in self.done:
                            continue
                        self.queue.setdefault(room["id"], []).append({
                            "reply": r["id"], "to": m, "sender": r["sender"], "body": r["body"], "hop": rec["hop"] + 1,
                            "at": r["sent_at"], "implicit": implicit})
                        self.done[(r["id"], m)] = r["sent_at"]  # settled: it is in the queue now
                        changed = True
                if rows and rows[-1]["sent_at"] > self.since:
                    self.since = rows[-1]["sent_at"]  # every reply up to here is queued or needs nothing
                    self.done = {k: at for k, at in self.done.items() if at >= self.since}
                    changed = True
                if changed:
                    self.save()
            self.drain(me)

    def answer_targets(self, room, rec, reply):
        """Where a member's answer goes: [(member, implicit)]. The members it @mentions, and the member whose message
        it answers (`rec`'s speaker) without being named, one level only: an answer that itself came back this way
        does not come back again. An empty answer, or a worker's failure, goes nowhere."""
        if no_answer(reply["body"]) or worker_failure(reply["body"]):
            return []
        out = [(m, False) for m in self.mentioned(room, reply["body"], exclude=reply["sender"])]
        asker = rec.get("speaker")
        if not rec.get("implicit") and asker in room["members"] and asker != reply["sender"] \
                and asker not in [m for m, _ in out]:
            out.append((asker, True))
        return out

    def drain(self, me):
        """Send queued hand-offs in order, room by room, as far as each room's budget allows."""
        for rid in list(self.queue):
            while True:
                room = self.rooms.get(rid)  # fresh before every item: the room may have been edited during a send
                with self.lock:
                    items = self.queue.get(rid) or []
                    if not room or not room.get("group"):  # the room is gone or no longer a group: nothing to pass
                        self.queue.pop(rid, None)
                        self.save()
                        break
                    # Someone who left the room gets nothing more from it, and a reply of someone who left is not passed on.
                    # A failure queued by an older version is no answer either.
                    gone = [i for i in items if i["to"] not in room["members"] or i["sender"] not in room["members"]
                            or worker_failure(i["body"])]
                    for i in gone:
                        self.dequeue(rid, i)
                    if gone:
                        self.save()
                    # Held items (past the room's current hop limit) wait for you; the others go out in order.
                    item = next((i for i in self.queue.get(rid) or [] if not held(room, i)), None)
                    if not item:
                        break
                    if item.get("flight"):
                        if item["flight"].get("me") != me:
                            self.notice[rid] = "Queued delivery belongs to a different sender; it was not retried."
                            break
                        if self.reconcile(room, me, item):
                            continue
                        if not item.get("force"):
                            self.notice[rid] = "Delivery outcome unknown; Send all now explicitly retries it."
                            break  # keep an ambiguous send; a restart must never guess and spend another turn
                    slot = self.take(room) if not item.get("force") else time.time()
                    if slot is None:
                        break  # the window is full: the rest wait for it to free up
                    if item.get("force"):
                        self.passes[rid].append(slot)
                if not self.send_item(room, me, item, slot):
                    break  # a failed send is retried on the next scan

    def send_item(self, room, me, item, slot):
        rid, key = room["id"], (item["reply"], item["to"])
        ok, err = self.deliver(room, item["to"], me, item["sender"], item["body"], item["hop"],
                               skip=item["reply"], skip_at=item.get("at", 0), item=item, implicit=bool(item.get("implicit")))
        with self.lock:
            if ok:
                self.tries.pop(key, None)
                return True
            if item.get("flight"):
                return False  # ambiguous, not a failed attempt: retain it until reconciled or explicitly retried
            if slot in self.passes[rid]:
                self.passes[rid].remove(slot)  # a failed send does not use up the budget
            self.tries[key] += 1
            if self.tries[key] >= RETRIES:
                self.dequeue(rid, item)
                self.notice[rid] = f"{short(item['sender'])} → {short(item['to'])}: {err}"
                self.tries.pop(key, None)
                self.save()
            return False

    def run(self, me_fn, every=2):
        while True:
            try:
                self.scan(me_fn())
            except Exception:  # keep relaying; one bad row must not stop the loop
                pass
            time.sleep(every)
