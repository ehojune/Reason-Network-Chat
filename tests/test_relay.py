"""Group-room relay with a fake database and sender: python -m unittest discover tests"""
import itertools
import json
import subprocess
import sqlite3
import sys
import tempfile
import time
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
        # message times near now: a restarted relay resumes only replies from the last RESUME_MS
        self.ids, self.clock = itertools.count(1), itertools.count(int(time.time() * 1000), 1000)
        self.room = {"id": "r-00000001", "name": "team", "members": [A, B, C], "group": True}
        self.home = tempfile.mkdtemp()
        self.r = self.new_relay()
        self.r.since = 0

    def new_relay(self):
        """A relay over the same folder: what a restarted server sees."""
        return relay.Relay(self.home, FakeRooms(self.room), self.rows, self.send)

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

    def counts(self):
        return [len(self.sent_to(m)) for m in (A, B, C)]

    def last_id_to(self, member):
        return self.rows("select id from messages where sender = ? and recipient = ? order by sent_at desc limit 1", (ME, member))[0]["id"]

    def queued(self):
        return self.r.view(set())[1].get(self.room["id"])

    # ---------- who your message goes to ----------
    def test_your_message_goes_only_to_mentions_or_the_default(self):
        with self.assertRaises(relay.RelayError):
            self.r.post(self.room, ME, "hello, nobody named")  # never silently to everyone
        self.assertEqual(self.counts(), [0, 0, 0])
        self.r.post(self.room, ME, "@b-claude only you")
        self.assertEqual(self.counts(), [0, 1, 0])
        self.r.post(self.room, ME, "@all hello")
        self.assertEqual(self.counts(), [1, 2, 1])
        self.r.post(self.room, ME, "@모두 안녕")
        self.assertEqual(self.counts(), [2, 3, 2])
        self.room["defaultTo"] = C
        self.r.post(self.room, ME, "no mention: the default recipient")
        self.assertEqual(self.counts(), [2, 3, 3])
        self.assertTrue(self.sent_to(C)[-1].endswith("---\npat: no mention: the default recipient"))

    def test_mention_followed_by_korean_particle(self):
        self.r.post(self.room, ME, "@b-claude에게 부탁")
        self.assertEqual(self.counts(), [0, 1, 0])

    def test_envelope_names_where_the_answer_goes(self):
        self.r.post(self.room, ME, "@a-codex hi")
        head = self.sent_to(A)[-1].split("---")[0]
        self.assertIn("Your answer goes back to pat automatically.\n", head)
        self.assertIn("To ask anyone else, @name them; their answers come back to you. Reply `-` if no answer is needed.", head)
        self.assertNotIn("Everyone in the room reads", head)

    def test_members_cannot_mention_everyone(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@all look at this", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 0, 0])

    def test_broadcast_alias_cannot_be_a_member_post_target(self):
        room = dict(self.room, members=["pat/all", "pat/everyone", A])
        self.assertEqual(self.r.mentioned(room, "@all @everyone", exclude=A), [])
        self.assertEqual(self.r.mentioned(room, "@pat/all", exclude=A), ["pat/all"])

    # ---------- context ----------
    def test_missed_lines_are_included_once(self):
        self.r.post(self.room, ME, "@all q1")
        self.insert(A, ME, "a answers q1", reply_to=self.last_id_to(A))
        self.r.post(self.room, ME, "@b-claude what do you think?")
        body = self.sent_to(B)[-1]
        self.assertIn("a-codex: a answers q1", body)
        self.assertNotIn("pat: @all q1", body)  # b got q1 itself
        self.r.post(self.room, ME, "@b-claude and now?")
        self.assertNotIn("a answers q1", self.sent_to(B)[-1])  # already given

    def test_handed_off_reply_appears_once(self):
        self.r.post(self.room, ME, "@a-codex start")
        self.insert(A, ME, "@b-claude please check retry.ts", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        body = self.sent_to(B)[-1]
        self.assertEqual(body.count("please check retry.ts"), 1, body)
        self.assertTrue(body.endswith("---\na-codex: @b-claude please check retry.ts"))

    def test_broadcast_is_not_repeated_as_context(self):
        self.r.post(self.room, ME, "@all hello all")
        for m in (A, B, C):
            self.assertEqual(self.sent_to(m)[-1].count("hello all"), 1, m)

    def test_same_session_name_needs_the_full_address(self):
        twin = "kim/a-codex"
        self.room["members"] = [A, twin, B]
        with self.assertRaises(relay.RelayError):
            self.r.post(self.room, ME, "@a-codex who am I?")  # ambiguous: names nobody
        self.r.post(self.room, ME, "@kim/a-codex only you")
        self.assertEqual((len(self.sent_to(A)), len(self.sent_to(twin)), len(self.sent_to(B))), (0, 1, 0))
        self.assertIn("Members: pat (person), pat/a-codex, kim/a-codex, b-claude.", self.sent_to(twin)[-1])

    def test_an_answer_goes_back_to_the_member_who_asked(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude what does retry.ts do?", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.assertIn("Your answer goes back to a-codex automatically; a-codex's reply to it reaches you only if it "
                      "@mentions you.", self.sent_to(B)[-1])
        self.insert(B, ME, "It retries three times with backoff.", reply_to=self.last_id_to(B))  # no @
        self.r.scan(ME)
        self.assertEqual(len(self.sent_to(A)), 2)  # came back to the asker
        self.assertTrue(self.sent_to(A)[-1].endswith("---\nb-claude: It retries three times with backoff."))
        self.assertIn("passed back to you automatically", self.sent_to(A)[-1])
        self.insert(A, ME, "Thanks, that settles it.", reply_to=self.last_id_to(A))  # one level only
        self.r.scan(ME)
        self.assertEqual((len(self.sent_to(A)), len(self.sent_to(B)), len(self.sent_to(C))), (2, 1, 0))

    def test_answer_with_mentions_also_goes_back(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude check this", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.insert(B, ME, "@c-codex please look too", reply_to=self.last_id_to(B))
        self.r.scan(ME)
        self.assertEqual((len(self.sent_to(A)), len(self.sent_to(C))), (2, 1))

    def test_empty_answers_go_nowhere(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude check this", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        for text in ("-", "(해당 없음)", "...", " N/A "):
            self.insert(B, ME, text, reply_to=self.last_id_to(B))
        self.r.scan(ME)
        self.assertEqual(len(self.sent_to(A)), 1)
        self.assertTrue(relay.no_answer("—") and relay.no_answer("Nothing to add."))
        self.assertFalse(any(relay.no_answer(t) for t in ("4", "no", "없음", "done, see #12")))

    def test_a_short_answer_still_goes_back(self):  # found live: "4" to "what is 2+2?" was dropped
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude what is 2+2?", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.insert(B, ME, "4", reply_to=self.last_id_to(B))
        self.r.scan(ME)
        self.assertTrue(self.sent_to(A)[-1].endswith("---\nb-claude: 4"))

    def test_answer_back_counts_toward_the_budget(self):
        self.room["limits"] = {"budget": 1}
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude check this", reply_to=self.last_id_to(A))
        self.r.scan(ME)  # uses the one hand-off
        self.insert(B, ME, "checked, all fine", reply_to=self.last_id_to(B))
        self.r.scan(ME)
        self.assertEqual(self.queued(), {"waiting": 1, "held": 0})

    # ---------- a 1:1 answer, forwarded ----------
    def row(self, mid):
        return self.rows("select id, sender, recipient, reply_to, body, sent_at from messages where id = ?", (mid,))[0]

    def test_a_forwarded_answer_reaches_the_members_it_mentions(self):
        q = self.insert(ME, A, "1:1: plan the release" + relay.dm_note("pat"))
        a = self.insert(A, ME, "@b-claude tag it, @c-codex write the notes", reply_to=q)
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 0, 0])  # only the 1:1 question: its answer is not relayed by itself
        self.assertEqual(self.r.forward(self.room, ME, self.row(a)), [B, C])
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 1, 1])
        body = self.sent_to(B)[-1]
        self.assertTrue(body.endswith("---\na-codex: @b-claude tag it, @c-codex write the notes"))
        self.assertIn("Your answer goes back to a-codex automatically;", body)
        self.assertIn("pat → a-codex: 1:1: plan the release\n", body)  # the 1:1 question, without its note
        self.assertNotIn("1:1 message from", body)
        self.assertEqual(self.r.forwarded_view({a}), {a: {"room": self.room["id"], "to": [B, C]}})
        self.insert(B, ME, "Tagged v1.2.", reply_to=self.last_id_to(B))  # as in the room: back to the asker
        self.r.scan(ME)
        self.assertEqual(self.counts(), [2, 1, 1])
        with self.assertRaises(relay.RelayError) as e:
            self.r.forward(self.room, ME, self.row(a))  # once
        self.assertEqual(e.exception.code, 409)
        self.assertIn(a, self.new_relay().forwarded_view({a}))  # kept across a restart

    def test_forward_refuses_what_it_cannot_pass_on(self):
        self.r.post(self.room, ME, "@a-codex go")
        in_room = self.insert(A, ME, "@b-claude check", reply_to=self.last_id_to(A))
        with self.assertRaises(relay.RelayError) as e:
            self.r.forward(self.room, ME, self.row(in_room))  # the room passes it on by itself
        self.assertEqual(e.exception.code, 409)
        for sender, recipient, body in [(A, ME, "no mention here"), (A, ME, "@a-codex only myself"),
                                        ("pat/x-codex", ME, "@b-claude not a member"), (A, B, "@c-codex not to you")]:
            with self.assertRaises(relay.RelayError):
                self.r.forward(self.room, ME, self.row(self.insert(sender, recipient, body)))
        plain = dict(self.room, group=False)
        with self.assertRaises(relay.RelayError):
            self.r.forward(plain, ME, self.row(self.insert(A, ME, "@b-claude plain room")))

    def test_a_forward_waits_for_the_room_budget(self):
        self.room["limits"] = {"budget": 1}
        a = self.insert(A, ME, "@b-claude @c-codex both of you")
        self.r.forward(self.room, ME, self.row(a))
        self.r.scan(ME)
        self.assertEqual((self.counts(), self.queued()), ([0, 1, 0], {"waiting": 1, "held": 0}))

    # ---------- worker failures and "Send again" ----------
    FAIL = "The Codex worker failed: The argument 'args[6]' contains a cmd.exe special character: @b-claude"

    def test_a_worker_failure_is_not_an_answer(self):
        self.assertTrue(all(relay.worker_failure(x) for x in (
            self.FAIL, "The Claude Code worker failed: boom", "Codex failed: rate limited", "codex exited with 1")))
        self.assertFalse(any(relay.worker_failure(x) for x in (
            "Done. The Codex worker failed: earlier, fixed now", "codex exited with 1 and then I retried", "")))
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, self.FAIL, reply_to=self.last_id_to(A))  # names @b-claude, but is a failure
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 0, 0])
        self.insert(A, ME, "@b-claude real question", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.insert(B, ME, self.FAIL.replace("@b-claude", "x"), reply_to=self.last_id_to(B))  # not back to the asker
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 1, 0])
        self.r.post(self.room, ME, "@c-codex anything?")
        self.assertNotIn("worker failed", self.sent_to(C)[-1])  # nor carried as room context

    def test_failures_queued_before_are_dropped(self):
        self.r.queue[self.room["id"]] = [{"reply": "old", "to": B, "sender": A, "body": self.FAIL, "hop": 1, "at": 1}]
        self.r.scan(ME)
        self.assertEqual((self.counts(), self.queued()), ([0, 0, 0], None))

    def test_usage_limit_reply_does_not_start_a_relay_cascade(self):
        self.r.post(self.room, ME, "@a-codex go")
        body = "You've hit your session limit · resets 4:20am (Asia/Seoul) @b-claude"
        self.insert(A, ME, body, reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 0, 0])
        self.r.post(self.room, ME, "@c-codex next")
        self.assertNotIn("You've hit", self.sent_to(C)[-1])
        self.assertTrue(relay.worker_failure("You've hit your usage limit"))
        self.assertFalse(relay.worker_failure("We fixed the You've hit your session limit issue"))

    def test_a_failure_cannot_be_forwarded(self):
        with self.assertRaises(relay.RelayError):
            self.r.forward(self.room, ME, self.row(self.insert(A, ME, self.FAIL)))

    def test_send_again_once(self):
        self.r.post(self.room, ME, "@a-codex build it")
        first = self.last_id_to(A)
        self.assertEqual(self.r.recipient_of(first), A)
        self.assertTrue(self.r.claim(first, "resent"))
        self.assertFalse(self.r.claim(first, "resent"))  # a second click does nothing
        self.assertEqual(self.r.redeliver(first, ME), A)
        self.assertEqual(len(self.sent_to(A)), 2)
        self.assertTrue(self.sent_to(A)[-1].endswith("---\npat: @a-codex build it"))
        self.assertEqual(self.r.settled_view({first})[first]["how"], "resent")
        self.assertIn(first, self.new_relay().settled_view({first}))  # kept across a restart
        self.assertIsNone(self.r.redeliver("not-relayed", ME))
        self.r.sent["old-failure"] = {"room": self.room["id"], "to": B, "speaker": A, "core": self.FAIL, "hop": 1}
        with self.assertRaises(relay.RelayError):
            self.r.redeliver("old-failure", ME)  # a failure an older version passed on is not sent again
        self.r.post(self.room, ME, "@a-codex Codex failed: rate limited. Why?")  # your own text quoting an error
        self.assertEqual(self.r.redeliver(self.last_id_to(A), ME), A)
        self.r.unclaim(first)
        self.assertEqual(self.r.settled_view({first}), {})
        self.room["members"] = [B, C]
        with self.assertRaises(relay.RelayError):
            self.r.redeliver(first, ME)  # A left the room

    # ---------- a member posts first ----------
    def test_a_member_post_goes_like_its_answer(self):
        self.r.post_cmd = 'python "rnc.py" room send {room} --as {member} "@name ..."'
        self.assertEqual(self.r.post_as(self.room, A, "@b-claude status of #12? @all", "session"), [B])  # no @all
        self.assertEqual(self.counts(), [0, 0, 0])  # queued: it goes out with the relay loop
        self.r.scan(ME)
        self.assertEqual(self.counts(), [0, 1, 0])
        body = self.sent_to(B)[-1]
        self.assertTrue(body.endswith("---\na-codex: @b-claude status of #12? @all"))
        self.assertIn("Your answer goes back to a-codex automatically;", body)
        self.assertIn('room send r-00000001 --as b-claude "@name ..."', body)
        rel = self.r.view({self.last_id_to(B)})[0][self.last_id_to(B)]
        self.assertEqual((rel["speaker"], rel["hop"], rel["post"]), (A, 1, "session"))
        self.insert(B, ME, "Merged an hour ago.", reply_to=self.last_id_to(B))  # back to the member who posted
        self.r.scan(ME)
        self.assertTrue(self.sent_to(A)[-1].endswith("---\nb-claude: Merged an hour ago."))

    def test_a_post_needs_a_mention_and_a_member(self):
        for body in ("no one named", "@all everyone please", "@a-codex only myself", "-"):
            with self.assertRaises(relay.RelayError):
                self.r.post_as(self.room, A, body, "session")
        with self.assertRaises(relay.RelayError) as e:
            self.r.post_as(self.room, "pat/x-codex", "@b-claude hi", "session")
        self.assertEqual(e.exception.code, 403)
        with self.assertRaises(relay.RelayError):
            self.r.post_as(dict(self.room, group=False), A, "@b-claude hi", "session")

    def test_a_post_counts_toward_the_room_budget(self):
        self.room["limits"] = {"budget": 1}
        self.r.post_as(self.room, A, "@b-claude @c-codex both", "allowed")
        self.r.scan(ME)
        self.assertEqual((self.counts(), self.queued()), ([0, 1, 0], {"waiting": 1, "held": 0}))

    def test_resending_preserves_first_post_provenance(self):
        self.r.post_as(self.room, A, "@b-claude report", "allowed")
        self.r.scan(ME)
        self.r.redeliver(self.last_id_to(B), ME)
        self.assertEqual(self.r.sent[self.last_id_to(B)]["post"], "allowed")

    def test_no_mention_no_wake_and_self_mention_ignored(self):
        self.r.post(self.room, ME, "@a-codex hi")
        self.insert(A, ME, "done, nothing for @a-codex or @pat", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 0, 0])

    def test_reply_landing_during_a_send_is_not_lost(self):
        self.r.post(self.room, ME, "@all q1")
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

    def test_long_missed_reply_is_clipped_not_dropped(self):
        self.r.post(self.room, ME, "@all q1")
        self.insert(A, ME, "x" * 5000, reply_to=self.last_id_to(A))
        self.r.post(self.room, ME, "@b-claude your view?")
        self.assertIn("a-codex: " + "x" * (relay.LINE_CHARS - 1) + "…", self.sent_to(B)[-1])

    def test_handed_off_reply_is_not_repeated_later(self):
        self.r.post(self.room, ME, "@a-codex start")
        self.insert(A, ME, "@b-claude please check", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.r.post(self.room, ME, "@b-claude anything else?")
        self.assertNotIn("please check", self.sent_to(B)[-1].split("---")[0])

    def test_other_traffic_does_not_crowd_out_room_lines(self):
        self.r.post(self.room, ME, "@all q1")
        self.insert(A, ME, "a answers q1", reply_to=self.last_id_to(A))
        for i in range(450):
            self.insert("pat/elsewhere", "kim/other", f"unrelated {i}")
        self.r.post(self.room, ME, "@b-claude your view?")
        self.assertIn("a-codex: a answers q1", self.sent_to(B)[-1])

    def test_plain_rooms_are_not_relayed(self):
        self.room["group"] = False
        self.r.post(self.room, ME, "@a-codex hi")
        self.insert(A, ME, "@b-claude look", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.assertEqual(self.sent_to(B), [])

    # ---------- limits: nothing is dropped ----------
    def test_hop_limit_holds_until_you_continue(self):
        self.room["limits"] = {"hops": 3}
        self.r.post(self.room, ME, "@a-codex start")
        prev = self.last_id_to(A)
        for hop, (who, nxt) in enumerate([(A, B), (B, A), (A, B), (B, A)], start=1):
            self.insert(who, ME, f"@{relay.short(nxt)} your turn", reply_to=prev)
            self.r.scan(ME)
            if hop <= 3:
                prev = self.last_id_to(nxt)
                self.assertEqual(self.r.sent[prev]["hop"], hop)
        self.assertEqual(len(self.sent_to(A)) + len(self.sent_to(B)), 1 + 3)
        self.assertEqual(self.queued(), {"waiting": 0, "held": 1})  # held, not dropped
        self.assertEqual(self.r.flush(self.room["id"]), 1)
        self.r.scan(ME)
        self.assertEqual(len(self.sent_to(A)) + len(self.sent_to(B)), 1 + 4)
        self.assertIsNone(self.queued())

    def test_budget_queues_and_sends_when_the_window_frees(self):
        self.room["limits"] = {"budget": 1}
        old = relay.BUDGET_WINDOW
        relay.BUDGET_WINDOW = 0.2
        try:
            self.r.post(self.room, ME, "@a-codex go")
            self.insert(A, ME, "@b-claude @c-codex look", reply_to=self.last_id_to(A))
            self.r.scan(ME)
            self.assertEqual(len(self.sent_to(B)) + len(self.sent_to(C)), 1)
            self.assertEqual(self.queued(), {"waiting": 1, "held": 0})
            time.sleep(0.3)
            self.r.scan(ME)
            self.assertEqual(len(self.sent_to(B)) + len(self.sent_to(C)), 2)
            self.assertIsNone(self.queued())
        finally:
            relay.BUDGET_WINDOW = old

    def test_send_all_now_and_your_message_free_the_queue(self):
        self.room["limits"] = {"budget": 1}
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude @c-codex look", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.assertEqual(self.queued(), {"waiting": 1, "held": 0})
        self.r.flush(self.room["id"])  # "send all now": past the budget
        self.r.scan(ME)
        self.assertEqual(len(self.sent_to(B)) + len(self.sent_to(C)), 2)
        self.insert(B, ME, "@c-codex next", reply_to=self.last_id_to(B))
        self.r.scan(ME)
        self.assertEqual(self.queued(), {"waiting": 2, "held": 0})  # to c-codex, and back to a-codex who asked
        self.r.post(self.room, ME, "@a-codex continue")  # your message: a fresh budget (one hand-off here)
        self.r.scan(ME)
        self.assertEqual(self.queued(), {"waiting": 1, "held": 0})
        self.r.flush(self.room["id"])
        self.r.scan(ME)
        self.assertIsNone(self.queued())

    def test_queued_hand_off_to_a_member_who_left_is_dropped(self):
        self.room["limits"] = {"budget": 1}
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude @c-codex look", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        queued_for = self.r.queue[self.room["id"]][0]["to"]
        self.room["members"] = [m for m in self.room["members"] if m != queued_for]  # edited while it waits
        self.r.post(self.room, ME, "@a-codex fresh budget")
        self.r.scan(ME)
        self.assertEqual(self.sent_to(queued_for), [])
        self.assertIsNone(self.queued())

    def test_member_removed_during_a_send_gets_nothing_after_it(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude @c-codex look", reply_to=self.last_id_to(A))
        real = self.r.send_one

        def send_then_edit(to, body, fyi):  # the room is edited while the first hand-off is being sent
            out = real(to, body, fyi)
            if self.room["members"] == [A, B, C]:
                self.room = dict(self.room, members=[A, B])
                self.r.rooms.room = self.room
            return out

        self.r.send_one = send_then_edit
        self.r.scan(ME)
        self.assertEqual((len(self.sent_to(B)), len(self.sent_to(C))), (1, 0))
        self.assertIsNone(self.queued())

    def test_a_lowered_hop_limit_holds_queued_hand_offs(self):
        self.room["limits"] = {"budget": 1}
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude @c-codex look", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.room["limits"] = {"budget": 5, "hops": 0}  # hop 1 is now past the limit
        self.r.scan(ME)
        self.assertEqual(self.queued(), {"waiting": 0, "held": 1})
        self.room["limits"] = {"budget": 5}  # raised again: it goes
        self.r.scan(ME)
        self.assertIsNone(self.queued())

    def test_a_sent_hand_off_leaves_the_queue_in_the_same_save(self):
        self.room["limits"] = {"budget": 1}
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude @c-codex look", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.r.flush(self.room["id"])
        self.r.scan(ME)
        saved = json.loads((Path(self.home) / "relay.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["queue"], {})
        self.new_relay().scan(ME)  # a restart sends nothing again
        self.assertEqual(len(self.sent_to(B)) + len(self.sent_to(C)), 2)

    def test_mention_right_after_other_text(self):
        self.r.post(self.room, ME, "안녕@b-claude 봐 줘")
        self.assertEqual(self.counts(), [0, 1, 0])
        with self.assertRaises(relay.RelayError):
            self.r.post(self.room, ME, "mail pat@b-claude is not a mention")

    def test_no_limit_room(self):
        self.room["limits"] = {"hops": None, "budget": None}
        old = relay.MAX_HOPS, relay.BUDGET
        relay.MAX_HOPS, relay.BUDGET = 2, 1
        try:
            self.r.post(self.room, ME, "@a-codex start")
            prev = self.last_id_to(A)
            for who, nxt in [(A, B), (B, A), (A, B), (B, A)]:
                self.insert(who, ME, f"@{relay.short(nxt)} your turn", reply_to=prev)
                self.r.scan(ME)
                prev = self.last_id_to(nxt)
            self.assertEqual(len(self.sent_to(A)) + len(self.sent_to(B)), 5)
        finally:
            relay.MAX_HOPS, relay.BUDGET = old

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
        self.assertIsNone(self.queued())

    def test_send_that_raises_holds_ambiguous_outcome_without_retrying(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude please check", reply_to=self.last_id_to(A))
        calls = []

        def hang(to, body, fyi):
            calls.append(to)
            raise subprocess.TimeoutExpired("reason", 60)

        self.r.send_one = hang
        for _ in range(relay.RETRIES + 3):
            self.r.scan(ME)
        self.assertEqual(calls, [B])
        self.assertIn("unknown", self.r.view(set())[2][self.room["id"]])
        self.assertEqual(self.queued(), {"waiting": 1, "held": 0})
        self.r.flush(self.room["id"])
        self.r.scan(ME)
        self.r.scan(ME)
        self.assertEqual(calls, [B, B])  # one manual retry, then held again
        self.r.send_one = self.send
        self.r.flush(self.room["id"])
        self.r.scan(ME)
        self.assertIsNone(self.queued())
        self.assertNotIn(self.room["id"], self.r.view(set())[2])
        self.assertNotIn(self.room["id"], self.new_relay().view(set())[2])

    def test_restart_reconciles_a_send_before_the_dequeue_was_saved(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude inspect", reply_to=self.last_id_to(A))
        class Crash(BaseException):
            pass
        def delivered_then_crashed(to, body, fyi):
            self.send(to, body, fyi)
            raise Crash()
        self.r.send_one = delivered_then_crashed
        with self.assertRaises(Crash):
            self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 1, 0])
        self.r = self.new_relay()
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 1, 0])
        self.assertIsNone(self.queued())

        self.assertNotIn(self.room["id"], self.r.view(set())[2])
        self.assertNotIn(self.room["id"], self.new_relay().view(set())[2])
        mid = self.last_id_to(B)
        self.assertEqual(self.r.sent[mid]["speaker"], A)
        self.insert(B, ME, "answer", reply_to=mid)
        self.r.scan(ME)
        self.assertEqual(self.counts(), [2, 1, 0])

    def test_no_send_when_the_inflight_claim_cannot_be_persisted(self):
        from unittest import mock
        self.r.post(self.room, ME, "@a-codex go")
        item = {"reply": "r", "to": B, "sender": A, "body": "question", "hop": 1, "at": 1}
        self.r.queue[self.room["id"]] = [item]
        with mock.patch.object(relay.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(relay.RelayError):
                self.r.deliver(self.room, B, ME, A, "question", 1, item=item)
        self.assertEqual(self.counts(), [1, 0, 0])
        self.assertNotIn("flight", item)
        self.r.deliver(self.room, B, ME, A, "question", 1, item=item)
        self.assertEqual(self.counts(), [1, 1, 0])

    def test_reconciliation_keeps_an_unrelated_permanent_failure_notice(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.r.notice[self.room["id"]] = "pat/b-claude → pat/c-codex: retries exhausted"
        self.insert(A, ME, "@b-claude another hand-off", reply_to=self.last_id_to(A))
        class Crash(BaseException):
            pass
        def crash(to, body, fyi):
            self.send(to, body, fyi)
            raise Crash()
        self.r.send_one = crash
        with self.assertRaises(Crash):
            self.r.scan(ME)
        self.r = self.new_relay()
        self.r.scan(ME)
        self.assertIsNone(self.queued())
        self.assertIn("retries exhausted", self.r.view(set())[2][self.room["id"]])

    def test_temporary_delivery_warning_never_overwrites_a_permanent_failure(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.r.notice[self.room["id"]] = "older retries exhausted"
        self.insert(A, ME, "@b-claude another question", reply_to=self.last_id_to(A))
        def delivered_but_timed_out(to, body, fyi):
            self.send(to, body, fyi)
            raise subprocess.TimeoutExpired("reason", 60)
        self.r.send_one = delivered_but_timed_out
        self.r.scan(ME)
        note = self.r.view(set())[2][self.room["id"]]
        self.assertIn("older retries exhausted", note)
        self.assertIn("unknown", note)
        self.r = self.new_relay()
        self.r.scan(ME)
        self.assertEqual(self.r.view(set())[2][self.room["id"]], "older retries exhausted")
        self.assertEqual(self.new_relay().view(set())[2][self.room["id"]], "older retries exhausted")

    def test_delivering_a_later_item_keeps_another_held_flights_warning(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.room["limits"] = {"hops": 2}
        self.r.queue[self.room["id"]] = [
            {"reply": "first", "to": B, "sender": A, "body": "first", "hop": 2, "at": 1},
            {"reply": "second", "to": C, "sender": A, "body": "second", "hop": 1, "at": 2}]
        with self.r.lock:
            self.r.save()
        self.r.send_one = lambda *args: (_ for _ in ()).throw(subprocess.TimeoutExpired("reason", 60))
        self.r.scan(ME)
        self.room["limits"] = {"hops": 1}  # the unknown first delivery is now held; the later item may proceed
        self.r.send_one = self.send
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 0, 1])
        self.assertEqual(self.queued(), {"waiting": 0, "held": 1})
        self.assertIn("unknown", self.r.view(set())[2][self.room["id"]])
        self.assertIn("unknown", self.new_relay().view(set())[2][self.room["id"]])
        self.r.post(self.room, ME, "@a-codex new message")
        self.assertIn("unknown", self.r.view(set())[2][self.room["id"]])

    def test_invalidated_flights_clear_only_their_temporary_warning(self):
        for invalidation in ("member-left", "group-disabled"):
            with self.subTest(invalidation=invalidation):
                home = tempfile.mkdtemp()
                room = dict(self.room, members=list(self.room["members"]), group=True)
                r = relay.Relay(home, FakeRooms(room), self.rows, self.send)
                r.since = 0
                r.post(room, ME, "@a-codex go")
                r.forward(room, ME, self.row(self.insert(A, ME, "@b-claude question")))
                r.notice[room["id"]] = "older retries exhausted"
                r.send_one = lambda *args: (_ for _ in ()).throw(subprocess.TimeoutExpired("reason", 60))
                r.scan(ME)
                self.assertIn("unknown", r.view(set())[2][room["id"]])
                if invalidation == "member-left":
                    room["members"].remove(B)
                else:
                    room["group"] = False
                r.scan(ME)
                self.assertFalse(r.queue)
                self.assertEqual(r.view(set())[2][room["id"]], "older retries exhausted")
                restarted = relay.Relay(home, FakeRooms(room), self.rows, self.send)
                self.assertEqual(restarted.view(set())[2][room["id"]], "older retries exhausted")

    def test_changed_identity_warning_preserves_history_and_clears_with_queue(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.r.forward(self.room, ME, self.row(self.insert(A, ME, "@b-claude question")))
        self.r.notice[self.room["id"]] = "older retries exhausted"
        self.r.send_one = lambda *args: (_ for _ in ()).throw(subprocess.TimeoutExpired("reason", 60))
        self.r.scan(ME)
        self.r.scan("different/identity")
        note = self.r.view(set())[2][self.room["id"]]
        self.assertIn("older retries exhausted", note)
        self.assertIn("different sender", note)
        self.r = self.new_relay()
        self.assertIn("different sender", self.r.view(set())[2][self.room["id"]])
        self.room["group"] = False
        self.r.scan("different/identity")
        self.assertFalse(self.r.queue)
        self.assertEqual(self.r.view(set())[2][self.room["id"]], "older retries exhausted")
        self.assertEqual(self.new_relay().view(set())[2][self.room["id"]], "older retries exhausted")

    def test_held_sender_mismatch_remains_visible_when_another_item_changes(self):
        for outcome in ("success", "ambiguous", "member-left"):
            with self.subTest(outcome=outcome):
                room = dict(self.room, members=list(self.room["members"]), limits={"hops": 1})
                r = relay.Relay(tempfile.mkdtemp(), FakeRooms(room), self.rows, self.send)
                rid = room["id"]
                r.queue[rid] = [
                    {"reply": "old", "to": B, "sender": A, "body": "old", "hop": 2,
                     "flight": {"me": "old/identity", "body": "claimed", "newest": 0}},
                    {"reply": "new", "to": C, "sender": A, "body": "new", "hop": 1}]
                r.notice[rid] = "older retries exhausted"
                r.transient_notice[rid] = relay.SENDER_NOTICE
                if outcome == "ambiguous":
                    r.send_one = lambda *args: (_ for _ in ()).throw(subprocess.TimeoutExpired("reason", 60))
                elif outcome == "member-left":
                    room["members"].remove(C)
                r.save()
                r.scan(ME)
                self.assertIn("older retries exhausted", r.view(set())[2][rid])
                self.assertEqual(r.transient_notice[rid], relay.SENDER_NOTICE)
                restarted = relay.Relay(r.path.parent, FakeRooms(room), self.rows, self.send)
                self.assertEqual(restarted.transient_notice[rid], relay.SENDER_NOTICE)

    def test_crash_during_manual_retry_does_not_authorize_a_second_retry(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude question", reply_to=self.last_id_to(A))
        self.r.send_one = lambda *args: (_ for _ in ()).throw(subprocess.TimeoutExpired("reason", 60))
        self.r.scan(ME)
        self.r.flush(self.room["id"])
        class Crash(BaseException):
            pass
        self.r.send_one = lambda *args: (_ for _ in ()).throw(Crash())
        with self.assertRaises(Crash):
            self.r.scan(ME)
        self.r = self.new_relay()
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 0, 0])
        self.assertEqual(self.queued(), {"waiting": 1, "held": 0})

    def test_storage_failure_releases_an_unused_rate_slot(self):
        from unittest import mock
        self.room["limits"] = {"budget": 1}
        self.r.post(self.room, ME, "@a-codex go")
        self.r.forward(self.room, ME, self.row(self.insert(A, ME, "@b-claude question")))
        with mock.patch.object(relay, "atomic_json", side_effect=OSError("disk full")):
            with self.assertRaises(relay.NotSentError):
                self.r.scan(ME)
        self.assertEqual(list(self.r.passes[self.room["id"]]), [])
        self.assertEqual(self.counts(), [1, 0, 0])
        self.r.scan(ME)  # storage recovered: no full-window wait for an attempt that never happened
        self.assertEqual(self.counts(), [1, 1, 0])
        self.assertIsNone(self.queued())
        self.assertNotIn(self.room["id"], self.r.view(set())[2])
        self.assertNotIn(self.room["id"], self.new_relay().view(set())[2])

    def test_nonzero_manual_retry_does_not_reopen_automatic_retries(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude question", reply_to=self.last_id_to(A))
        self.r.send_one = lambda *args: (_ for _ in ()).throw(subprocess.TimeoutExpired("reason", 60))
        self.r.scan(ME)
        self.r.flush(self.room["id"])
        calls = []
        self.r.send_one = lambda to, body, fyi: (calls.append(to), (1, "", "network down"))[1]
        for _ in range(5):
            self.r.scan(ME)
        self.assertEqual(calls, [B])
        self.r = self.new_relay()
        self.r.scan(ME)
        self.assertEqual(self.counts(), [1, 0, 0])
        self.assertTrue(self.r.queue[self.room["id"]][0].get("flight"))

    def test_recovered_storage_notice_is_not_left_after_a_known_network_failure(self):
        from unittest import mock
        self.r.post(self.room, ME, "@a-codex go")
        self.r.forward(self.room, ME, self.row(self.insert(A, ME, "@b-claude question")))
        with mock.patch.object(relay, "atomic_json", side_effect=OSError("disk full")):
            with self.assertRaises(relay.NotSentError):
                self.r.scan(ME)
        self.r.send_one = lambda *args: (1, "", "network down")
        for _ in range(relay.RETRIES):
            self.r.scan(ME)
        self.assertIsNone(self.queued())
        note = self.r.view(set())[2][self.room["id"]]
        self.assertIn("network down", note)
        self.assertNotIn("storage recovery", note)

    def test_endpoint_resend_reloads_another_servers_relay_record(self):
        import server
        from unittest import mock
        writer = self.new_relay()
        writer.post(self.room, ME, "@a-codex question")
        mid = self.last_id_to(A)
        self.assertNotIn(mid, self.r.sent)  # the serving instance predates the other writer's message
        h = server.Handler.__new__(server.Handler)
        h.send_json = mock.Mock()
        with mock.patch.object(server, "RELAY", self.r), mock.patch.object(server, "db_rows", self.rows), \
                mock.patch.object(server, "my_address", return_value=ME), \
                mock.patch.dict(server._who, {"data": {"sessions": [{"address": A, "status": "idle"}]}}), \
                mock.patch.object(server.LAUNCHER, "stale_names", return_value=set()):
            h.resend({"ids": [mid]})
        self.assertEqual(h.send_json.call_args.args[0]["done"], 1)
        resent = self.last_id_to(A)
        self.assertNotEqual(resent, mid)
        self.assertEqual(self.r.sent[resent]["core"], "@a-codex question")
        self.assertEqual(self.r.sent[resent]["room"], self.room["id"])

    # ---------- restarts ----------
    def test_cursor_moves_past_queued_hand_offs(self):
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
        self.assertGreater(self.r.since, at)  # the failed hand-off waits in the queue, not behind the cursor
        self.assertEqual(self.queued(), {"waiting": 1, "held": 0})
        self.r.send_one = real
        self.r.scan(ME)
        self.assertEqual(len(self.sent_to(B)), 1)

    def test_replies_while_the_server_was_down_are_passed_on_once(self):
        self.r.post(self.room, ME, "@a-codex go")
        self.r.scan(ME)  # the cursor is saved
        self.insert(A, ME, "@b-claude written while the server was stopped", reply_to=self.last_id_to(A))
        again = self.new_relay()  # restarted: resumes from the saved cursor, not from "now"
        again.scan(ME)
        self.assertEqual(len(self.sent_to(B)), 1)
        self.new_relay().scan(ME)  # and a further restart does not send it twice
        self.assertEqual(len(self.sent_to(B)), 1)

    def test_queue_survives_a_restart(self):
        self.room["limits"] = {"budget": 1}
        self.r.post(self.room, ME, "@a-codex go")
        self.insert(A, ME, "@b-claude @c-codex look", reply_to=self.last_id_to(A))
        self.r.scan(ME)
        self.assertEqual(self.queued(), {"waiting": 1, "held": 0})
        again = self.new_relay()  # a restart must not reset the room's rate window
        again.scan(ME)
        self.assertEqual(len(self.sent_to(B)) + len(self.sent_to(C)), 1)
        self.assertTrue(again.queue[self.room["id"]])
        again.flush(self.room["id"])
        again.scan(ME)
        self.assertEqual(len(self.sent_to(B)) + len(self.sent_to(C)), 2)

    def test_save_keeps_records_written_by_another_server(self):
        self.r.post(self.room, ME, "@a-codex go")
        path = Path(self.home) / "relay.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["sent"]["other-id"] = {"room": "r-x", "hop": 0, "core": "theirs", "speaker": ME, "to": B, "at": 1}
        path.write_text(json.dumps(data), encoding="utf-8")
        self.r.post(self.room, ME, "@b-claude more")
        merged = json.loads(path.read_text(encoding="utf-8"))["sent"]
        self.assertIn("other-id", merged)
        self.assertEqual(len(merged), 3)


if __name__ == "__main__":
    unittest.main()
