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


if __name__ == "__main__":
    unittest.main()
