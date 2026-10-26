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

    def test_side_width(self):
        p = prefs.Prefs(tempfile.mkdtemp())
        self.assertEqual(p.get()["sideWidth"], 260)
        self.assertEqual(p.set("sideWidth", 320)["sideWidth"], 320)
        for bad in (179, 901, 300.5, "300", True, None):
            with self.assertRaises(prefs.PrefError):
                p.set("sideWidth", bad)

    def test_sidebar_order_validation_and_persistence(self):
        home = tempfile.mkdtemp()
        p = prefs.Prefs(home)
        order = {"now": ["pat/b", "pat/a"], "favorites": ["room:r-0123abcd", "pat/a"], "offline": []}
        self.assertEqual(p.set("sidebarOrder", order)["sidebarOrder"], order)
        self.assertEqual(prefs.Prefs(home).get()["sidebarOrder"], order)
        self.assertEqual(p.get()["favorites"], [])  # rankings never grant membership
        for bad in ([], None, {"new-group": []}, {"now": "pat/a"}, {"now": ["pat/a", "pat/a"]},
                    {"now": ["<script>"]}, {"now": [5]}, {"rooms": ["room:bad"]},
                    {"now": [f"pat/s{i}" for i in range(prefs.MAX_ORDERED + 1)]}):
            with self.subTest(value=bad):
                with self.assertRaises(prefs.PrefError):
                    p.set("sidebarOrder", bad)
        self.assertEqual(p.get()["sidebarOrder"], order)

    def test_auto_wake(self):
        p = prefs.Prefs(tempfile.mkdtemp())
        self.assertEqual(p.get()["autoWake"], [])
        self.assertEqual(p.set("autoWake", ["pat/labhq-codex"])["autoWake"], ["pat/labhq-codex"])
        for bad in ("pat/x", ["pat/a", "pat/a"], ["room:r-0123abcd"], ["x"], [5], [f"pat/s{i}" for i in range(51)]):
            with self.assertRaises(prefs.PrefError):
                p.set("autoWake", bad)

    def test_sections_migrate_and_persist_independently(self):
        home = tempfile.mkdtemp()
        p = prefs.Prefs(home)
        self.assertEqual(p.get()["collapsedSections"], ["offline", "history"])
        self.assertEqual(p.set("hideOffline", False)["collapsedSections"], [])
        self.assertEqual(p.set("collapsedSections", ["now", "favorites"])["collapsedSections"], ["now", "favorites"])
        self.assertEqual(prefs.Prefs(home).get()["collapsedSections"], ["now", "favorites"])
        self.assertEqual(p.set("hideOffline", True)["collapsedSections"], ["now", "favorites"])
        self.assertEqual(p.set("collapsedSections", [])["collapsedSections"], [])
        for bad in ("now", ["now", "now"], ["unknown"], [None], [["now"]], ["rooms"] * 7):
            with self.assertRaises(prefs.PrefError):
                p.set("collapsedSections", bad)

    def test_bad_file_and_failed_write(self):
        home = tempfile.mkdtemp()
        Path(home, "prefs.json").write_text(json.dumps({"hideOffline": "x", "evil": 1}), encoding="utf-8")
        p = prefs.Prefs(home)
        self.assertEqual(p.get(), {"hideOffline": True, "favorites": [], "sideWidth": 260, "autoWake": [],
                                   "collapsedSections": ["offline", "history"]})
        Path(home, "blocked").write_text("a file where a folder must go", encoding="utf-8")
        p.path = Path(home, "blocked", "prefs.json")
        with self.assertRaises(prefs.PrefError) as e:
            p.set("hideOffline", False)
        self.assertEqual(e.exception.code, 500)
        self.assertIs(p.get()["hideOffline"], True)


if __name__ == "__main__":
    unittest.main()
