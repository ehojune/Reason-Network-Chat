"""The 1:1 note: python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("REASON_CHAT_HOME", tempfile.mkdtemp())
os.environ.setdefault("REASON_BIN", sys.executable)  # any real program: importing server only looks it up
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402

ROOMS = [{"id": "r-1", "members": ["pat/a-codex", "pat/b-claude"], "group": True},
         {"id": "r-2", "members": ["pat/c-codex"], "group": False}]


class DmNoteTest(unittest.TestCase):
    def test_only_members_of_a_group_room_get_the_note(self):
        with mock.patch.object(server.ROOMS, "list", return_value=ROOMS), \
                mock.patch.object(server, "my_address", return_value="pat/terminal"):
            note = server.dm_note("pat/a-codex")
            self.assertTrue(note.startswith("\n\n(1:1 message from pat, not from a group room"))
            self.assertIn("unless pat forwards it to the room.)", note)
            self.assertEqual(server.dm_note("pat/c-codex"), "")  # a plain room relays nothing
            self.assertEqual(server.dm_note("pat/d-codex"), "")


class StuckTest(unittest.TestCase):
    def test_quiet_since_takes_the_latest_seen_progress(self):
        q = server.quiet_since
        self.assertEqual(q(None, None, 500), 500)  # nothing known: from now
        self.assertEqual(q({"at": 100, "changed": False}, None, 500), 100)  # first sight only
        self.assertEqual(q({"at": 100, "changed": False}, 40, 500), 40)  # its log was last written earlier
        self.assertEqual(q({"at": 300, "changed": True}, 200, 500), 300)  # a step changed after the last log line
        self.assertEqual(q({"at": 300, "changed": True}, 450, 500), 450)

    def test_activity_notes_changes_of_status_or_step(self):
        server._activity.clear()
        server.note_activity({"sessions": [{"address": "p/w", "status": "busy", "doing": "step 1"}]})
        first = dict(server._activity["p/w"])
        self.assertFalse(first["changed"])
        server.note_activity({"sessions": [{"address": "p/w", "status": "busy", "doing": "step 1"}]})
        self.assertEqual(server._activity["p/w"], first)  # nothing new
        server.note_activity({"sessions": [{"address": "p/w", "status": "busy", "doing": "step 2"}]})
        self.assertTrue(server._activity["p/w"]["changed"])


class PostProofTest(unittest.TestCase):
    ROOM = {"id": "r-1", "members": ["pat/lead-codex", "pat/b-claude", "kim/b-claude"], "group": True,
            "allowPost": ["pat/b-claude"]}

    def test_who_may_post_as_a_member(self):
        self.assertEqual(server.member_of(self.ROOM, "lead-codex"), "pat/lead-codex")
        self.assertIsNone(server.member_of(self.ROOM, "b-claude"))  # two members share the name: give the address
        self.assertEqual(server.member_of(self.ROOM, "kim/b-claude"), "kim/b-claude")
        self.assertEqual(server.post_proof(self.ROOM, "pat/lead-codex", "lead-codex", "pat"), "session")
        self.assertIsNone(server.post_proof(self.ROOM, "pat/lead-codex", "other-codex", "pat"))  # another worker
        self.assertIsNone(server.post_proof(self.ROOM, "pat/lead-codex", None, "pat"))  # an unknown caller
        self.assertEqual(server.post_proof(self.ROOM, "pat/b-claude", None, "pat"), "allowed")
        self.assertIsNone(server.post_proof(self.ROOM, "kim/b-claude", "b-claude", "pat"))  # someone else's session


if __name__ == "__main__":
    unittest.main()
