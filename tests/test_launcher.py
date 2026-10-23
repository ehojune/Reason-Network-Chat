"""Launcher checks that need no agent installed: python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["REASON_CHAT_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import launcher  # noqa: E402

FOLDER = tempfile.mkdtemp()
SOL = {"id": "gpt-6.1-sol", "label": "GPT-6.1-Sol", "efforts": ["low", "high"], "defaultEffort": "low"}
ARGON = {"id": "gemini-4-argon", "label": "Gemini 4 Argon", "efforts": ["low", "high"], "defaultEffort": None,
         "ids": ["gemini-4-argon-low", "gemini-4-argon-high"]}


def family(fid, models, worker=True, worker_models=True, default=None):
    return {"id": fid, "label": fid, "installed": True, "models": models, "efforts": ["low", "high", "xhigh"],
            "defaultModel": default, "defaultEffort": None, "note": None,
            "modes": {"worker": {"ok": worker, "why": None if worker else "no serve", "models": worker_models,
                                 "modelsWhy": None if worker_models else "no shim"},
                      "window": {"ok": True, "why": None, "models": True, "modelsWhy": None}}}


class FakeCatalog:
    families = [family("codex", [SOL], default="gpt-6.1-sol"),
                family("antigravity", [ARGON], worker=False, worker_models=False),
                family("claude", [], worker_models=False)]

    def family(self, fid):
        return next((f for f in self.families if f["id"] == fid), None)


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.l = launcher.Launcher("reason", FakeCatalog())

    def req(self, **kw):
        r = {"agent": "codex", "mode": "worker", "folder": FOLDER, "model": "", "effort": "", "name": "t-codex"}
        r.update(kw)
        return r

    def bad(self, code=400, **kw):
        with self.assertRaises(launcher.LaunchError) as e:
            self.l.check(self.req(**kw), {"taken"})
        self.assertEqual(e.exception.code, code, str(e.exception))

    def test_ok(self):
        fam, mode, cwd, entry, model, effort, name = self.l.check(self.req(model="gpt-6.1-sol", effort="high"), set())
        self.assertEqual((mode, model, effort, name), ("worker", "gpt-6.1-sol", "high", "t-codex"))
        self.assertEqual(Path(cwd), Path(FOLDER).resolve())

    def test_catalog_whitelist(self):
        self.bad(model="gpt-6.1-sol; calc")
        self.bad(model="gpt-6.1-sol", effort="ultra")
        self.bad(effort="--help")
        self.bad(agent="bash")
        self.bad(mode="shell")
        self.bad(model=5)

    def test_default_model_limits_effort(self):
        self.bad(effort="xhigh")  # another model has it, the default model (gpt-6.1-sol) does not
        self.assertEqual(self.l.check(self.req(effort="high"), set())[5], "high")

    def test_models_need_a_capable_mode(self):
        self.bad(agent="claude", model="opus")  # no shim/models for this worker
        self.bad(agent="antigravity")  # serve cannot run it

    def test_folder(self):
        self.bad(folder="")
        self.bad(folder="relative/dir")
        self.bad(folder=os.path.join(FOLDER, "missing"))
        self.bad(folder=FOLDER + "\n")
        self.bad(folder="\\\\server\\share" if launcher.WIN else "//server/share")

    def test_name(self):
        self.bad(name="--help")
        self.bad(name="Upper")
        self.bad(name="x" * 49)
        self.bad(409, name="taken")

    def test_antigravity_effort_is_part_of_the_id(self):
        r = self.l.check(self.req(agent="antigravity", mode="window", model="gemini-4-argon", name=""), set())
        self.assertEqual(r[5], "low")  # no default effort: the first one the catalog lists
        self.bad(agent="antigravity", mode="window", effort="high", name="")  # effort without a model


class CatalogParsingTest(unittest.TestCase):
    def test_claude_help(self):
        text = """Options:
  --effort <level>                      Effort level for the current session
                                        (low, medium, high, xhigh, max)
  --model <model>                       Model for the current session. Provide
                                        an alias for the latest model (e.g.
                                        'fable', 'opus', or 'sonnet') or a
                                        model's full name.
  -n, --name <name>                     Set a display name
"""
        self.assertEqual(launcher.re.findall(r"'([a-z][a-z0-9-]*)'", launcher.option_block(text, "--model")),
                         ["fable", "opus", "sonnet"])
        self.assertIn("(low, medium, high, xhigh, max)", launcher.option_block(text, "--effort"))

    def test_agy_models(self):
        out = ("Fetching available models...\ngemini-4-argon-high\tGemini 4 Argon (High)\n"
               "gemini-4-argon-low\tGemini 4 Argon (Low)\ngpt-oss-120b-medium\tGPT-OSS 120B (Medium)\n")
        old = launcher.run_text
        launcher.run_text = lambda args, timeout: out
        try:
            cat = launcher.agy_catalog("agy")
        finally:
            launcher.run_text = old
        argon = cat["models"][0]
        self.assertEqual((argon["id"], argon["label"], argon["efforts"]), ("gemini-4-argon", "Gemini 4 Argon", ["low", "high"]))
        self.assertEqual(cat["models"][1]["efforts"], ["medium"])

    def test_session_markers_dropped(self):
        self.assertTrue(launcher.is_session_var("CLAUDECODE"))
        self.assertTrue(launcher.is_session_var("CODEX_THREAD_ID"))
        self.assertTrue(launcher.is_session_var("CODEX_SANDBOX_NETWORK_DISABLED"))
        self.assertFalse(launcher.is_session_var("CODEX_HOME"))
        self.assertFalse(launcher.is_session_var("CODEX_API_KEY"))
        self.assertFalse(launcher.is_session_var("PATH"))
        # Claude host settings go only when this server itself runs inside Claude Code.
        self.assertFalse(launcher.is_session_var("CLAUDE_CODE_USE_BEDROCK"))
        self.assertTrue(launcher.is_session_var("CLAUDE_CODE_SESSION_ID", in_claude=True))

    def test_shim_is_stable(self):
        a = launcher.shim_dir()
        if a is None:
            self.skipTest("no pip launcher in this Python")
        exe = Path(a) / ("codex.exe" if launcher.WIN else "codex")
        first = exe.read_bytes()
        launcher.shim_dir()
        self.assertEqual(exe.read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
