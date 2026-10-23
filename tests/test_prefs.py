"""Server-side viewer preferences: python -m unittest discover tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prefs  # noqa: E402


class PrefsTest(unittest.TestCase):
    def test_defaults_set_and_persist(self):
        home = tempfile.mkdtemp()
        p = prefs.Prefs(home)
        self.assertIs(p.get()["hideOffline"], True)
        self.assertIs(p.set("hideOffline", False)["hideOffline"], False)
        self.assertIs(prefs.Prefs(home).get()["hideOffline"], False)

    def test_whitelist_and_types(self):
        p = prefs.Prefs(tempfile.mkdtemp())
        for key, value in (("theme", "dark"), ("hideOffline", "yes"), ("hideOffline", 1), (None, True)):
            with self.assertRaises(prefs.PrefError):
                p.set(key, value)

    def test_favorites(self):
        p = prefs.Prefs(tempfile.mkdtemp())
        self.assertEqual(p.get()["favorites"], [])
        self.assertEqual(p.set("favorites", ["pat/api-claude", "room:r-0123abcd"])["favorites"], ["pat/api-claude", "room:r-0123abcd"])
        for bad in ("pat/api-claude", ["pat/a", "pat/a"], ["<script>"], ["room:x"], [5], ["a/b"] * 101, [["x"]], [{"a": 1}]):
            with self.assertRaises(prefs.PrefError):
                p.set("favorites", bad)

    def test_bad_file_and_failed_write(self):
        home = tempfile.mkdtemp()
        Path(home, "prefs.json").write_text(json.dumps({"hideOffline": "x", "evil": 1}), encoding="utf-8")
        p = prefs.Prefs(home)
        self.assertEqual(p.get(), {"hideOffline": True, "favorites": []})
        Path(home, "blocked").write_text("a file where a folder must go", encoding="utf-8")
        p.path = Path(home, "blocked", "prefs.json")
        with self.assertRaises(prefs.PrefError) as e:
            p.set("hideOffline", False)
        self.assertEqual(e.exception.code, 500)
        self.assertIs(p.get()["hideOffline"], True)


if __name__ == "__main__":
    unittest.main()
