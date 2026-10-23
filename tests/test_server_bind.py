"""Two servers cannot share a port: python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["REASON_CHAT_HOME"] = tempfile.mkdtemp()
os.environ.setdefault("REASON_BIN", sys.executable)  # any real program: importing server only looks it up
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server  # noqa: E402


class BindTest(unittest.TestCase):
    def test_second_server_on_the_same_port_fails(self):
        first = server.bind("127.0.0.1", 0)
        try:
            port = first.server_address[1]
            with self.assertRaises(SystemExit) as e:
                server.bind("127.0.0.1", port)
            self.assertIn(f"Port {port} is in use", str(e.exception))
        finally:
            first.server_close()
        again = server.bind("127.0.0.1", port)  # free again once the first one is closed
        again.server_close()


if __name__ == "__main__":
    unittest.main()
