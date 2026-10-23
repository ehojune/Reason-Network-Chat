"""Two servers cannot share a port, and a stopped one frees it at once: python -m unittest discover tests"""
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
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

    def test_port_is_free_right_after_serving(self):
        # Exclusive binding must not keep the port after the server answered requests and stopped (each answer
        # closes its connection: the handler speaks HTTP/1.0).
        first = server.bind("127.0.0.1", 0)
        port = first.server_address[1]
        try:
            for _ in range(3):
                t = threading.Thread(target=first.handle_request)
                t.start()
                with self.assertRaises(urllib.error.HTTPError):  # an unknown path: a 404 is still a full answer
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/nothing-here", timeout=10)
                t.join(10)
        finally:
            first.server_close()
        again = server.bind("127.0.0.1", port)
        again.server_close()


if __name__ == "__main__":
    unittest.main()
