import os
import socket
import struct
import sys
import unittest
import threading
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launcher


class PlatformProofTest(unittest.TestCase):
    def test_spoofed_ancestor_without_trusted_worker_record_is_not_proof(self):
        l = launcher.Launcher.__new__(launcher.Launcher)
        l.lock, l.workers = threading.Lock(), {}
        procs = [(10, 1, 'reason-fake', ['reason-fake', 'network', 'serve', 'codex', '--name', 'victim']),
                 (20, 10, 'python', ['python', 'rnc.py'])]
        with mock.patch.object(launcher, 'connection_owner', return_value=20), mock.patch.object(launcher, 'list_processes', return_value=procs), mock.patch.object(launcher, 'started_at', return_value='t10'):
            self.assertIsNone(l.caller_worker(50000, 8765))
            l.workers['victim'] = dict(pid=11, started='t10')
            self.assertIsNone(l.caller_worker(50000, 8765))
            l.workers['victim'] = dict(pid=10, started='older')
            self.assertIsNone(l.caller_worker(50000, 8765))
            l.workers['victim'] = dict(pid=10, started='t10')
            self.assertEqual(l.caller_worker(50000, 8765), 'victim')
    def test_darwin_arg_boundaries(self):
        blob = struct.pack("=i", 6) + b'/Applications/Reason CLI/reason\0\0reason\0network\0serve\0--name\0lead\0a b\0ENV=x\0'
        self.assertEqual(launcher.parse_darwin_argv(blob), ['reason', 'network', 'serve', '--name', 'lead', 'a b'])
        self.assertEqual(launcher.parse_darwin_argv(b'bad'), [])

    def test_lsof_requires_exact_connection_direction_and_unique_owner(self):
        text = 'p10\nn127.0.0.1:8765->127.0.0.1:54321\np20\nn127.0.0.1:54321->127.0.0.1:8765\n'
        self.assertEqual(launcher.lsof_owner(text, 54321, 8765), 20)
        self.assertIsNone(launcher.lsof_owner(text + 'p30\nn127.0.0.1:54321->127.0.0.1:8765\n', 54321, 8765))
        self.assertIsNone(launcher.lsof_owner(text, 54322, 8765))

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS process and socket APIs')
    def test_actual_darwin_process_and_socket_owner(self):
        procs = launcher.list_processes()
        mine = next(p for p in procs if p[0] == os.getpid())
        self.assertTrue(mine[3])
        with socket.socket() as listener, socket.socket() as client:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            client.connect(listener.getsockname())
            conn, _ = listener.accept()
            with conn:
                self.assertEqual(launcher.connection_owner(client.getsockname()[1], listener.getsockname()[1]), os.getpid())
