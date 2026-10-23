"""Group-room relay with a fake database and sender: python -m unittest discover tests"""
import itertools
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import relay  # noqa: E402

ME, A, B, C = "pat/terminal", "pat/a-codex", "pat/b-claude", "pat/c-codex"


class FakeRooms:
    def __init__(self, room):
        self.room = room

    def get(self, rid):
        return self.room if rid == self.room["id"] else None


class RelayTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("create table messages (id text, sender text, recipient text, reply_to text, body text, sent_at int)")
        self.ids, self.clock = itertools.count(1), itertools.count(10**12, 1000)
        self.room = {"id": "r-00000001", "name": "team", "members": [A, B, C], "group": True}
        self.r = relay.Relay(tempfile.mkdtemp(), FakeRooms(self.room), self.rows, self.send)
        self.r.since = 0

    def rows(self, sql, params=()):
        return [dict(r) for r in self.db.execute(sql, params)]

    def insert(self, sender, recipient, body, reply_to=None):
        mid = f"m{next(self.ids)}"
        self.db.execute("insert into messages values (?,?,?,?,?,?)", (mid, sender, recipient, reply_to, body, next(self.clock)))
        return mid

    def send(self, to, body, fyi):
        self.insert(ME, to, body)
        return 0, "", ""

    def sent_to(self, member):
        return [r["body"] for r in self.rows("select body from messages where sender = ? and recipient = ? order by sent_at", (ME, member))]

    def last_id_to(self, member):
        return self.rows("select id from messages where sender = ? and recipient = ? order by sent_at desc limit 1", (ME, member))[0]["id"]

    def test_post_reaches_everyone_or_only_mentions(self):
        self.r.post(self.room, ME, "hello all")
        self.assertEqual([len(self.sent_to(m)) for m in (A, B, C)], [1, 1, 1])
        self.assertTrue(self.sent_to(A)[0].endswith("---\npat: hello all"))
        self.r.post(self.room, ME, "@b-claude only you")
        self.assertEqual([len(self.sent_to(m)) for m in (A, B, C)], [1, 2, 1])

    def test_missed_lines_are_included_once(self):
        self.r.post(self.room, ME, "q1")
        self.insert(A, ME, "a answers q1", reply_to=self.last_id_to(A))
        self.r.post(self.room, ME, "@b-claude what do you think?")
        body = self.sent_to(B)[-1]
        self.assertIn("a-codex: a answers q1", body)
        self.assertNotIn("pat: q1", body)  # b got q1 itself
        self.r.post(self.room, ME, "@b-claude and now?")
        self.assertNotIn("a answers q1", self.sent_to(B)[-1])  # already given

    def test_mention_is_passed_on_with_hop_limit(self):
        self.r.post(self.room, ME, "@a-codex start")
        prev = self.last_id_to(A)
        for hop, (who, nxt) in enumerate([(A, B), (B, A), (A, B), (B, A)], start=1):
            self.insert(who, ME, f"@{relay.short(nxt)} your turn", reply_to=prev)
            self.r.scan(ME)
            if hop <= relay.MAX_HOPS:
                prev = self.last_id_to(nxt)
                self.assertEqual(self.r.sent[prev]["hop"], hop)
        self.assertEqual(len(self.sent_to(A)) + len(self.sent_to(B)), 1 + relay.MAX_HOPS)
        self.assertEqual(self.r.paused.get(self.room["id"]), "hops")
        self.r.post(self.room, ME, "@c-codex reset")
        self.assertNotIn(self.room["id"], self.r.paused)

    def test_handed_off_reply_appears_once(self):
        self.r.post(self.room, ME, "@a-codex start")
        self.insert(A, ME, "@b-claude please check retry.ts", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        body = self.sent_to(B)[-1]
        self.assertEqual(body.count("please check retry.ts"), 1, body)
        self.assertTrue(body.endswith("---\na-codex: @b-claude please check retry.ts"))

    def test_broadcast_is_not_repeated_as_context(self):
        self.r.post(self.room, ME, "hello all")
        for m in (A, B, C):
            self.assertEqual(self.sent_to(m)[-1].count("hello all"), 1, m)

    def test_same_session_name_needs_the_full_address(self):
        twin = "kim/a-codex"
        self.room["members"] = [A, twin, B]
        self.r.post(self.room, ME, "@a-codex who am I?")  # ambiguous: wakes nobody in particular, so everyone
        self.assertEqual(len(self.sent_to(twin)), 1)
        self.r.post(self.room, ME, "@kim/a-codex only you")
        self.assertEqual((len(self.sent_to(A)), len(self.sent_to(twin)), len(self.sent_to(B))), (1, 2, 1))
        self.assertIn("Members: pat (person), pat/a-codex, kim/a-codex, b-claude.", self.sent_to(twin)[-1])

    def test_no_mention_no_wake_and_self_mention_ignored(self):
        self.r.post(self.room, ME, "@a-codex hi")
        self.insert(A, ME, "done, nothing for @a-codex or @pat", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.assertEqual([len(self.sent_to(m)) for m in (A, B, C)], [1, 0, 0])

    def test_budget_pauses_until_you_write(self):
        old = relay.BUDGET
        relay.BUDGET = 1
        try:
            self.r.post(self.room, ME, "@a-codex go")
            self.insert(A, ME, "@b-claude @c-codex look", reply_to=self.last_id_to(A))
            self.r.scan(ME)
            self.assertEqual(len(self.sent_to(B)) + len(self.sent_to(C)), 1)
            self.assertEqual(self.r.paused.get(self.room["id"]), "budget")
            self.r.post(self.room, ME, "@a-codex again")  # your message clears the pause and the budget
            self.insert(A, ME, "@b-claude look", reply_to=self.last_id_to(A))
            self.r.scan(ME)
            self.assertEqual(len(self.sent_to(B)) + len(self.sent_to(C)), 2)
        finally:
            relay.BUDGET = old

    def test_reply_landing_during_a_send_is_not_lost(self):
        self.r.post(self.room, ME, "q1")
        real = self.send

        def send_and_reply(to, body, fyi):  # c answers while b's copy is being sent
            if to == B and "q2" in body:
                self.insert(C, ME, "c answers q1", reply_to=self.last_id_to(C))
            return real(to, body, fyi)

        self.r.send_one = send_and_reply
        self.r.post(self.room, ME, "@b-claude q2")
        self.assertNotIn("c answers q1", self.sent_to(B)[-1])
        self.r.post(self.room, ME, "@b-claude q3")
        self.assertIn("c-codex: c answers q1", self.sent_to(B)[-1])

    def test_failed_hand_off_is_retried_then_reported(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude please check", reply_to=self.last_id_to(A))
        calls = []
        self.r.send_one = lambda to, body, fyi: (calls.append(to), (1, "", "network down"))[1]
        for _ in range(relay.RETRIES + 2):
            self.r.scan(ME)
        self.assertEqual(calls, [B] * relay.RETRIES)
        _, _, notice = self.r.view(set())
        self.assertIn("network down", notice[self.room["id"]])

    def test_long_missed_reply_is_clipped_not_dropped(self):
        self.r.post(self.room, ME, "q1")
        self.insert(A, ME, "x" * 5000, reply_to=self.last_id_to(A))
        self.r.post(self.room, ME, "@b-claude your view?")
        self.assertIn("a-codex: " + "x" * (relay.LINE_CHARS - 1) + "…", self.sent_to(B)[-1])

    def test_scan_cursor_moves_and_waits_for_retries(self):
        self.r.post(self.room, ME, "@a-codex go")
        quiet = self.insert(A, ME, "done, no mention", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        at = self.rows("select sent_at from messages where id = ?", (quiet,))[0]["sent_at"]
        self.assertEqual(self.r.since, at)
        self.r.post(self.room, ME, "@a-codex again")
        self.insert(A, ME, "@b-claude look", reply_to=self.last_id_to(A))
        real = self.r.send_one
        self.r.send_one = lambda to, body, fyi: (1, "", "down")
        self.r.scan(ME)
        self.assertEqual(self.r.since, at)  # a pending retry holds the cursor
        self.r.send_one = real
        self.r.scan(ME)
        self.assertGreater(self.r.since, at)
        self.assertEqual(self.r.done and min(self.r.done.values()) >= self.r.since, True)

    def test_plain_rooms_are_not_relayed(self):
        self.room["group"] = False
        self.r.post(self.room, ME, "@a-codex hi")
        self.insert(A, ME, "@b-claude look", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.assertEqual(self.sent_to(B), [])


if __name__ == "__main__":
    unittest.main()
