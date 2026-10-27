"""Managed listeners must be visible and invitable before their first message."""
import os
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

os.environ.setdefault("REASON_CHAT_HOME", tempfile.mkdtemp())
os.environ.setdefault("REASON_BIN", sys.executable)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class ManagedSessionsTest(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.worker = {"name": "argon", "family": "antigravity", "cwd": "folder"}
        self.who = {"person": "pat", "machine": "pc", "sessions": []}
        self.stack.enter_context(mock.patch.dict(server._who, {"data": self.who, "error": None}))
        for obj, name, value in [
            (server, "db_rows", []), (server.LAUNCHER, "list", [self.worker]),
            (server.LAUNCHER, "list_records", [self.worker]),
            (server.LAUNCHER, "stale_names", set()), (server.LAUNCHER, "list_foreign", []),
            (server.RELAY, "view", ({}, {}, {})), (server.RELAY, "forwarded_view", {}),
            (server.RELAY, "settled_view", {}), (server.ROOMS, "list", []),
            (server.PREFS, "get", {}), (server.WAKER, "view", {}),
        ]:
            self.stack.enter_context(mock.patch.object(obj, name, return_value=value))

    def test_new_listener_is_visible_and_invitable_without_history(self):
        rows = server.state()["sessions"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["address"], "pat/argon")
        self.assertEqual(rows[0]["agent"], "gemini")
        self.assertTrue(rows[0]["live"])
        self.assertTrue(rows[0]["worker"])
        self.assertIn("pat/argon", server.me_and_known()[1])

    def test_saved_stopped_record_does_not_create_live_session(self):
        with mock.patch.object(server.LAUNCHER, "list", return_value=[]):
            self.assertEqual(server.state()["sessions"], [])
            self.assertNotIn("pat/argon", server.me_and_known()[1])

    def test_network_session_is_not_overwritten_or_duplicated(self):
        self.who["sessions"] = [{"address": "pat/argon", "name": "argon", "person": "pat",
                                 "machine": "remote", "status": "busy", "agent": "gemini"}]
        rows = server.state()["sessions"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "busy")
        self.assertEqual(rows[0]["machine"], "remote")

    def test_unknown_person_does_not_invent_address(self):
        self.who.pop("person")
        self.assertEqual(server.state()["sessions"], [])
        self.assertEqual(server.me_and_known(), (None, set()))
