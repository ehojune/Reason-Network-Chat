"""Room validation and storage: python -m unittest discover tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rooms  # noqa: E402

ME = "pat/terminal"
KNOWN = {"pat/api-claude", "pat/web-codex", "kim/docs-agent", ME}


class RoomsTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.r = rooms.Rooms(self.home)

    def bad(self, code=400, **req):
        with self.assertRaises(rooms.RoomError) as e:
            self.r.upsert(req, KNOWN, ME)
        self.assertEqual(e.exception.code, code, str(e.exception))

    def test_create_edit_delete_persist(self):
        room = self.r.upsert({"name": "  team   one ", "members": ["pat/api-claude", "pat/web-codex", "pat/api-claude"]}, KNOWN, ME)
        self.assertEqual(room["name"], "team one")
        self.assertEqual(room["members"], ["pat/api-claude", "pat/web-codex"])
        self.r.upsert({"id": room["id"], "name": "team", "members": ["kim/docs-agent"]}, KNOWN, ME)
        again = rooms.Rooms(self.home).get(room["id"])
        self.assertEqual((again["name"], again["members"]), ("team", ["kim/docs-agent"]))
        self.r.delete(room["id"])
        self.assertEqual(rooms.Rooms(self.home).list(), [])
        with self.assertRaises(rooms.RoomError):
            self.r.delete(room["id"])

    def test_validation(self):
        self.bad(name="", members=["pat/api-claude"])
        self.bad(name="x" * 61, members=["pat/api-claude"])
        self.bad(name="t", members=[])
        self.bad(name="t", members="pat/api-claude")
        self.bad(name="t", members=["pat/unknown"])
        self.bad(name="t", members=[ME])  # not the page's own address
        self.bad(name="t", members=["--help"])
        self.bad(404, id="r-00000000", name="t", members=["pat/api-claude"])

    def test_failed_write_changes_nothing(self):
        room = self.r.upsert({"name": "t", "members": ["pat/api-claude"]}, KNOWN, ME)
        self.r.path = Path(self.home, "missing-dir", "x", "rooms.json")
        Path(self.home, "missing-dir").write_text("a file where a folder must go", encoding="utf-8")
        for req in ({"name": "new", "members": ["pat/web-codex"]}, {"id": room["id"], "name": "renamed", "members": ["pat/web-codex"]}):
            with self.assertRaises(rooms.RoomError) as e:
                self.r.upsert(req, KNOWN, ME)
            self.assertEqual(e.exception.code, 500)
        with self.assertRaises(rooms.RoomError):
            self.r.delete(room["id"])
        self.assertEqual([(x["name"], x["members"]) for x in self.r.list()], [("t", ["pat/api-claude"])])

    def test_bad_file_is_ignored(self):
        Path(self.home, "rooms.json").write_text('[{"id": "x", "name": "t", "members": ["a/b"]}, 5, "z"]', encoding="utf-8")
        self.assertEqual(rooms.Rooms(self.home).list(), [])


if __name__ == "__main__":
    unittest.main()
