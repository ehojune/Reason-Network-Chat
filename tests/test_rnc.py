"""rnc.py, the worker CLI: python -m unittest discover tests"""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rnc  # noqa: E402


class RncTest(unittest.TestCase):
    def test_usage(self):
        for argv in (["worker", "restart"], ["worker", "start", "x", "--folder", "C:/"], ["worker", "fly", "x"]):
            with self.assertRaises(SystemExit) as e, mock.patch("sys.stderr"):
                rnc.parse(argv)
            self.assertEqual(e.exception.code, 2)
        a = rnc.parse(["worker", "start", "x", "--folder", "C:/w", "--agent", "codex", "--full-access"])
        self.assertEqual((a.action, a.name, a.agent, a.full_access), ("start", "x", "codex", True))

    def test_goes_through_the_running_server(self):
        calls = []
        with mock.patch.object(rnc, "server_token", return_value="tok"), \
                mock.patch.object(rnc, "call", side_effect=lambda tok, path, body=None: calls.append((tok, path, body)) or {"ok": True}), \
                mock.patch("sys.stdout"):
            self.assertEqual(rnc.main(["worker", "restart", "lead-codex"]), 0)
            self.assertEqual(rnc.main(["worker", "adopt", "lead-codex", "--model", "gpt-6.1-sol", "--effort", "high"]), 0)
            self.assertEqual(rnc.main(["worker", "start", "w", "--folder", "C:/w", "--agent", "claude"]), 0)
        self.assertEqual(calls[0], ("tok", "/api/workers/reboot", {"name": "lead-codex"}))
        self.assertEqual(calls[1][1:], ("/api/workers/adopt", {"name": "lead-codex", "model": "gpt-6.1-sol", "effort": "high"}))
        self.assertEqual(calls[2][1], "/api/launch")
        self.assertEqual(calls[2][2]["mode"], "worker")

    def test_a_refusal_exits_1(self):
        def refuse(*a, **k):
            raise rnc.Refused("It is restarting already.")
        with mock.patch.object(rnc, "server_token", return_value="tok"), mock.patch.object(rnc, "call", side_effect=refuse), \
                mock.patch("sys.stderr"):
            self.assertEqual(rnc.main(["worker", "stop", "lead-codex"]), 1)


if __name__ == "__main__":
    unittest.main()
