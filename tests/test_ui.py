"""Run the shipped JavaScript regression checks when Node is installed."""
import shutil
import subprocess
import unittest
from pathlib import Path


class UiTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is needed for UI regression checks")
    def test_ui(self):
        result = subprocess.run([shutil.which("node"), str(Path(__file__).with_suffix(".js"))],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
