"""Launcher checks that need no agent installed: python -m unittest discover tests"""
import json
import os
import subprocess
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
                                 "modelsWhy": None if worker_models else "no shim", "fullAccess": worker},
                      "window": {"ok": True, "why": None, "models": True, "modelsWhy": None,
                                 "fullAccess": fid != "antigravity"}}}


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
        fam, mode, cwd, entry, model, effort, name, full = self.l.check(self.req(model="gpt-6.1-sol", effort="high"), set())
        self.assertEqual((mode, model, effort, name, full), ("worker", "gpt-6.1-sol", "high", "t-codex", False))
        self.assertEqual(Path(cwd), Path(FOLDER).resolve())

    def test_full_access(self):
        self.assertTrue(self.l.check(self.req(fullAccess=True), set())[-1])
        self.assertTrue(self.l.check(self.req(mode="window", fullAccess=True), set())[-1])
        self.bad(fullAccess="yes")
        self.bad(fullAccess=1)
        self.bad(agent="antigravity", mode="window", fullAccess=True)  # this fake agy has no such flag

    def test_fast_is_codex_only_and_strictly_boolean_or_inherited(self):
        self.l.check(self.req(fast=True), set())
        self.l.check(self.req(fast=False), set())
        self.l.check(self.req(fast=None), set())
        for value in ('true', 1, 0, []):
            self.bad(fast=value)
        self.bad(agent='claude', fast=True)
        self.bad(agent='claude', fast=False)
        self.assertIn('service_tier=fast', launcher.window_args('codex', '', '', False, True))
        self.assertIn('features.fast_mode=true', launcher.model_args('codex', '', '', True))
        self.assertIn('service_tier=default', launcher.model_args('codex', '', '', False))
        self.assertEqual(launcher.model_args('codex', '', '', None), [])

    def test_catalog_whitelist(self):
        self.bad(model="gpt-6.1-sol; calc")
        self.bad(model="gpt-6.1-sol", effort="ultra")
        self.bad(effort="--help")
        self.bad(agent="bash")
        self.bad(mode="shell")
        self.bad(model=5)

    def test_unknown_default_allows_only_common_efforts(self):
        fam = family("codex", [SOL, dict(SOL, id="gpt-x", efforts=["low", "high", "xhigh"])])
        self.assertEqual(launcher.efforts_for(fam, None), ["low", "high"])

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
        for keep in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY",
                     "CLAUDE_CODE_SKIP_BEDROCK_AUTH", "CLAUDE_CODE_GIT_BASH_PATH", "CLAUDE_CODE_CLIENT_CERT"):
            self.assertFalse(launcher.is_session_var(keep, in_claude=True), keep)

    def test_shim_is_stable(self):
        for kind in launcher.SHIM_AGENTS:
            a = launcher.shim_dir(kind)
            if a is None:
                self.skipTest("no pip launcher in this Python")
            self.assertTrue(launcher.shim_current(kind))
            exe = Path(a) / (f"{kind}.exe" if launcher.WIN else kind)
            first = exe.read_bytes()
            launcher.shim_dir(kind)
            self.assertEqual(exe.read_bytes(), first)


SHOW = ["-c", "import sys; print(sys.argv[1:])"]  # this Python stands in for the agent CLI


class ShimTest(unittest.TestCase):
    """The shim's own script, run with this Python as the "real" CLI."""
    def run_shim(self, **env):
        e = {k: v for k, v in os.environ.items() if not k.startswith("REASON_CHAT_")}
        e.update(env)
        out = subprocess.run([sys.executable, "-c", launcher.SHIM_MAIN.decode(), "tail"], env=e,
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip()

    def test_arguments_come_from_the_settings_file(self):
        settings = Path(tempfile.mkdtemp()) / "w.json"
        launcher.write_settings(settings, SHOW + ["from-file"])
        env = dict(REASON_CHAT_SHIM_REAL=sys.executable, REASON_CHAT_SHIM_SETTINGS=str(settings),
                   REASON_CHAT_SHIM_ARGS=json.dumps(SHOW + ["from-env"]))
        self.assertEqual(self.run_shim(**env), str(["from-file", "tail"]))
        settings.unlink()  # unreadable file: the arguments given at start
        self.assertEqual(self.run_shim(**env), str(["from-env", "tail"]))

    def test_workers_from_before_keep_working(self):
        self.assertEqual(self.run_shim(REASON_CHAT_CODEX_REAL=sys.executable,
                                       REASON_CHAT_CODEX_ARGS=json.dumps(SHOW + ["old"])), str(["old", "tail"]))

    def test_fast_switch_reaches_the_next_cli_invocation(self):
        settings = Path(tempfile.mkdtemp()) / 'fast.json'
        env = dict(REASON_CHAT_SHIM_REAL=sys.executable, REASON_CHAT_SHIM_SETTINGS=str(settings))
        for fast, tier in ((True, 'fast'), (False, 'default'), (None, None)):
            args = launcher.model_args('codex', 'gpt-6.1-sol', 'high', fast)
            launcher.write_settings(settings, SHOW + args)
            received = self.run_shim(**env)
            self.assertEqual(received, str(args + ['tail']))
            self.assertEqual('service_tier=' in received, tier is not None)

    def test_arguments_per_agent(self):
        self.assertEqual(launcher.model_args("claude", "claude-opus-5-5", "high"),
                         ["--model", "claude-opus-5-5", "--effort", "high"])
        self.assertEqual(launcher.model_args("codex", "gpt-6.1-sol", "high"),
                         ["-c", "model=gpt-6.1-sol", "-c", "model_reasoning_effort=high"])
        self.assertEqual(launcher.model_args("codex", "", ""), [])
        self.assertEqual(launcher.serve_args("reason", "codex", "w", "C:/x", True)[-1], "--full-access")
        self.assertNotIn("--full-access", launcher.serve_args("reason", "codex", "w", "C:/x", False))
        for fid, flag in (("claude", "bypassPermissions"), ("codex", "--dangerously-bypass-approvals-and-sandbox"),
                          ("antigravity", "--dangerously-skip-permissions")):
            self.assertEqual(launcher.window_args(fid, "", "", True)[-1], flag)
            self.assertNotIn(flag, launcher.window_args(fid, "", "", False))


class ConfigureTest(unittest.TestCase):
    """Changing a running worker, with its processes faked."""
    def setUp(self):
        self.l = launcher.Launcher("reason", FakeCatalog())
        self.restarts = []
        self.alive = launcher.Launcher.__dict__["alive"]  # the staticmethod itself, so it is restored as one
        launcher.Launcher.alive = staticmethod(lambda w: True)
        self.l.halt = lambda w: None
        self.l.settle = lambda w: None

        def start(fam, cwd, model, effort, name, full, fast=None):
            self.restarts.append((fam["id"], model, effort, full))
            return {"name": name, "pid": 1, "started": "x", "family": fam["id"], "model": model or None,
                    "effort": effort or None, "cwd": cwd, "log": "", "fullAccess": full, "fast": fast, "settings": None}
        self.l.start_worker = start
        self.settings = Path(tempfile.mkdtemp()) / "c.json"
        launcher.write_settings(self.settings, [])
        self.l.workers = {
            "live-codex": {"name": "live-codex", "pid": 1, "started": "x", "family": "codex", "model": None,
                           "effort": None, "cwd": FOLDER, "log": "", "fullAccess": False,
                           "settings": str(self.settings)},
            "old-codex": {"name": "old-codex", "pid": 2, "started": "y", "family": "codex", "model": "gpt-6.1-sol",
                          "effort": "high", "cwd": FOLDER, "log": "", "fullAccess": True},  # before settings files
            "a-claude": {"name": "a-claude", "pid": 3, "started": "z", "family": "claude", "model": None,
                         "effort": None, "cwd": FOLDER, "log": ""},
        }

    def tearDown(self):
        launcher.Launcher.alive = self.alive

    def conf(self, busy=False, **req):
        return self.l.configure(req, busy)

    def bad(self, code, busy=False, **req):
        with self.assertRaises(launcher.LaunchError) as e:
            self.conf(busy, **req)
        self.assertEqual(e.exception.code, code, str(e.exception))

    def test_codex_model_changes_without_a_restart(self):
        r = self.conf(name="live-codex", model="gpt-6.1-sol", effort="high", busy=True)
        self.assertEqual(r, {"ok": True, "restarted": False})
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8"))["args"],
                         ["-c", "model=gpt-6.1-sol", "-c", "model_reasoning_effort=high"])
        self.assertEqual(self.l.workers["live-codex"]["effort"], "high")
        self.assertEqual(self.restarts, [])

    def test_permission_change_restarts_and_waits_for_a_busy_worker(self):
        self.bad(409, busy=True, name="live-codex", fullAccess=True)
        self.assertEqual(self.restarts, [])
        self.assertTrue(self.conf(busy=True, name="live-codex", fullAccess=True, force=True)["restarted"])
        self.assertEqual(self.restarts, [("codex", "", "", True)])
        self.assertTrue(self.l.workers["live-codex"]["fullAccess"])

    def test_fast_changes_live_and_omission_preserves_the_current_setting(self):
        self.assertFalse(self.conf(name='live-codex', fast=True, busy=True)['restarted'])
        self.assertEqual(self.l.workers['live-codex']['pid'], 1)
        self.assertTrue(self.l.records['live-codex']['fast'])
        self.assertIn('service_tier=fast', json.loads(self.settings.read_text(encoding='utf-8'))['args'])
        self.conf(name='live-codex', model='gpt-6.1-sol')
        self.assertTrue(self.l.workers['live-codex']['fast'])
        self.conf(name='live-codex', model='gpt-6.1-sol', fast=False)
        self.assertIn('service_tier=default', json.loads(self.settings.read_text(encoding='utf-8'))['args'])
        self.conf(name='live-codex', model='gpt-6.1-sol', fast=None)
        self.assertNotIn('service_tier=default', json.loads(self.settings.read_text(encoding='utf-8'))['args'])
        self.assertIsNone(self.l.records['live-codex']['fast'])
        self.assertEqual(self.restarts, [])

    def test_workers_without_a_settings_file_restart(self):
        self.assertTrue(self.conf(name="old-codex", model="gpt-6.1-sol", effort="low", fullAccess=True)["restarted"])
        self.assertEqual(self.restarts, [("codex", "gpt-6.1-sol", "low", True)])

    def test_unchanged_and_refusals(self):
        self.assertTrue(self.conf(name="old-codex", model="gpt-6.1-sol", effort="high", fullAccess=True)["unchanged"])
        self.bad(404, name="someone-else")
        self.bad(400, name="live-codex", model="gpt-6.1-sol; calc")
        self.bad(400, name="live-codex", effort="ultra")
        self.bad(400, name="a-claude", model="x")  # this fake Claude has no worker model choice
        self.bad(400, name="live-codex", fullAccess="yes")
        self.bad(400, name="live-codex", force="yes")
        self.assertEqual(self.restarts, [])

    def test_claude_restarts(self):
        self.assertTrue(self.conf(name="a-claude", fullAccess=True)["restarted"])
        self.assertEqual(self.restarts, [("claude", "", "", True)])

    def test_during_a_restart(self):
        seen = {}

        def halt(w):  # what the rest of the server sees while the worker is down
            seen["record kept"] = "a-claude" in self.l.workers
            for call in (lambda: self.conf(name="a-claude", fullAccess=False), lambda: self.l.stop("a-claude")):
                try:
                    call()
                except launcher.LaunchError as e:
                    seen.setdefault("refused", []).append(e.code)
            self.l.workers.update({f"w{i}": dict(self.l.workers["live-codex"], name=f"w{i}") for i in range(5)})
            try:  # 3 + 5 = 8 workers, one of them restarting: no room for a ninth
                self.l.launch({"agent": "codex", "mode": "worker", "folder": FOLDER, "name": "ninth"}, set())
            except launcher.LaunchError as e:
                seen["ninth"] = e.code
            for i in range(5):
                del self.l.workers[f"w{i}"]
        self.l.halt = halt
        self.assertTrue(self.conf(name="a-claude", fullAccess=True)["restarted"])
        self.assertEqual(seen, {"record kept": True, "refused": [409, 409], "ninth": 429})
        self.assertNotIn("a-claude", self.l.restarting)


class StuckWorkerTest(unittest.TestCase):
    """A stuck worker's processes, its restart, and adopting one started elsewhere, with processes faked."""
    PROCS = [(10, 1, "reason.exe", ["reason", "network", "serve", "codex", "--name", "lead-codex"]),
             (11, 10, "codex.exe", ["codex", "exec", "--json"]),  # the hung turn
             (12, 11, "node.exe", ["node", "server.js"]),          # what the turn started
             (13, 10, "conhost.exe", ["conhost"]),
             (99, 12, "late.exe", ["late"]),                        # pid 12 reused? no: born after its parent
             (20, 1, "other.exe", ["other"])]

    def setUp(self):
        self.l = launcher.Launcher("reason", FakeCatalog())
        self.saved = {k: launcher.__dict__[k] for k in ("list_processes", "started_at", "started_epoch", "kill_pid")}
        self.alive = launcher.Launcher.__dict__["alive"]
        born = {10: "100", 11: "110", 12: "120", 13: "101", 99: "130", 20: "5"}
        launcher.started_at = lambda pid: born.get(pid, "")
        launcher.started_epoch = lambda s: float(s) if s else None  # creation times in seconds
        launcher.list_processes = lambda: list(self.PROCS)
        self.killed, self.halted, self.started = [], [], []
        launcher.kill_pid = lambda pid: self.killed.append(pid)
        launcher.Launcher.alive = staticmethod(lambda w: True)
        self.l.halt = lambda w: self.halted.append(w["name"])
        self.l.settle = lambda w: None

        def start(fam, cwd, model, effort, name, full, fast=None):
            self.started.append((name, model, effort, full))
            return {"name": name, "pid": 50, "started": "500", "family": fam["id"], "model": model or None,
                    "effort": effort or None, "cwd": cwd, "log": "", "fullAccess": full, "fast": fast, "settings": None}
        self.l.start_worker = start
        self.l.workers = {"lead-codex": {"name": "lead-codex", "pid": 10, "started": "100", "family": "codex",
                                         "model": "gpt-6.1-sol", "effort": "high", "cwd": FOLDER, "log": "",
                                         "fullAccess": True}}
        self.l.records = {"lead-codex": dict(self.l.workers["lead-codex"])}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(launcher, k, v)
        launcher.Launcher.alive = self.alive

    def test_descendants_follow_parents_but_not_reused_pids(self):
        self.assertEqual([r[0] for r in launcher.descendants(self.PROCS, 10)], [11, 13, 12, 99])
        launcher.started_at = lambda pid: {10: "100", 11: "90"}.get(pid, "")  # 11 is older than 10: pid reuse
        self.assertEqual([r[0] for r in launcher.descendants(self.PROCS, 10)], [13])

    def test_ancestors_stop_at_a_reused_pid(self):
        self.assertEqual(launcher.ancestors(self.PROCS, 12), [11, 10, 1])
        launcher.started_at = lambda pid: {12: "120", 11: "130"}.get(pid, "")  # 11 started after 12: a reused pid
        self.assertEqual(launcher.ancestors(self.PROCS, 12), [])

    def test_tree_lists_the_serve_and_what_runs_under_it(self):
        tree = self.l.tree("lead-codex")
        self.assertTrue(tree["managed"])
        self.assertEqual([p["pid"] for p in tree["procs"]], [10, 11, 13, 12, 99])
        self.assertEqual(tree["procs"][1]["cmd"], "codex exec --json")
        with self.assertRaises(launcher.LaunchError):
            self.l.tree("nobody")

    def test_pending_requests_read_from_reason(self):
        home = Path(tempfile.mkdtemp())
        (home / ".reason" / "ask-workers").mkdir(parents=True)
        (home / ".reason" / "ask-workers" / "lead-codex.json").write_text(json.dumps([
            {"request": {"id": "m1", "from": "p/terminal", "body": "restart the workers"}},
            {"request": {"id": "m2", "from": "p/terminal", "body": "x"}, "reply": "done"}]), encoding="utf-8")
        saved, launcher.HOME = launcher.HOME, home
        try:
            got = launcher.pending_requests("lead-codex")
        finally:
            launcher.HOME = saved
        self.assertEqual([(p["id"], p["answered"]) for p in got], [("m1", False), ("m2", True)])
        self.assertEqual(launcher.pending_requests("nobody-here"), [])

    def test_relaunch_stops_kills_leftovers_and_starts_with_the_record(self):
        self.assertEqual(self.l.relaunch("lead-codex"), {"ok": True, "restarted": True})
        self.assertEqual(self.halted, ["lead-codex"])
        self.assertEqual(sorted(self.killed), [11, 12, 13, 99])  # the hung turn and what it started
        self.assertEqual(self.started, [("lead-codex", "gpt-6.1-sol", "high", True)])
        self.assertEqual(self.l.workers["lead-codex"]["pid"], 50)
        self.assertNotIn("lead-codex", self.l.restarting)
        with self.assertRaises(launcher.LaunchError) as e:
            self.l.relaunch("not-here")
        self.assertEqual(e.exception.code, 404)

    def test_adopt_records_the_settings_it_is_said_to_run_with(self):
        self.l.workers = {}
        self.l.foreign = {"lead-codex": {"name": "lead-codex", "pid": 10, "started": "100", "family": "codex",
                                         "model": None, "effort": None, "cwd": FOLDER, "log": "",
                                         "fullAccess": True, "settings": None, "adopted": True}}
        with self.assertRaises(launcher.LaunchError):
            self.l.adopt("lead-codex", "gpt-6.1-sol; calc", None)
        self.assertEqual(self.l.running_here("lead-codex"), "foreign")
        self.l.adopt("lead-codex", "gpt-6.1-sol", "high")
        w = self.l.workers["lead-codex"]
        self.assertEqual((w["model"], w["effort"], w["external"]), ("gpt-6.1-sol", "high", True))
        self.assertEqual(self.l.records["lead-codex"]["model"], "gpt-6.1-sol")
        self.assertEqual(self.l.running_here("lead-codex"), "managed")


class StartWorkerTest(unittest.TestCase):
    """What a worker process is given, with spawning faked."""
    def setUp(self):
        self.saved = launcher.spawn, launcher.find_codex, launcher.started_at, launcher.shim_current
        self.spawned = []
        launcher.spawn = lambda args, cwd, env, flags, log=None: self.spawned.append((args, env)) or 4242
        launcher.find_codex = lambda: sys.executable
        launcher.started_at = lambda pid: "t"
        self.l = launcher.Launcher("reason", FakeCatalog())
        if launcher.shim_dir("codex") is None:
            self.skipTest("no pip launcher in this Python")

    def tearDown(self):
        launcher.spawn, launcher.find_codex, launcher.started_at, launcher.shim_current = self.saved

    def test_current_shim_gets_a_settings_file(self):
        w = self.l.start_worker(FakeCatalog().family("codex"), FOLDER, "gpt-6.1-sol", "high", "s-codex", True)
        args, env = self.spawned[-1]
        self.assertEqual(args[-1], "--full-access")
        self.assertTrue(w["settings"] and env["REASON_CHAT_SHIM_SETTINGS"] == w["settings"])
        self.assertEqual(json.loads(Path(w["settings"]).read_text(encoding="utf-8"))["args"],
                         ["-c", "model=gpt-6.1-sol", "-c", "model_reasoning_effort=high"])
        self.assertEqual(env["REASON_CHAT_CODEX_REAL"], env["REASON_CHAT_SHIM_REAL"])  # an older shim works too
        self.assertTrue(env["PATH"].startswith(launcher.shim_dir("codex")))
        self.assertTrue(launcher.Launcher.live_settings(w))

    def test_an_older_shim_still_runs_but_changes_restart(self):
        launcher.shim_current = lambda kind: False  # the old .exe is held open by a running turn
        w = self.l.start_worker(FakeCatalog().family("codex"), FOLDER, "gpt-6.1-sol", "", "o-codex", False)
        args, env = self.spawned[-1]
        self.assertIsNone(w["settings"])
        self.assertNotIn("REASON_CHAT_SHIM_SETTINGS", env)
        self.assertEqual(json.loads(env["REASON_CHAT_CODEX_ARGS"]), ["-c", "model=gpt-6.1-sol"])
        self.assertFalse(launcher.Launcher.live_settings(w))

    def test_new_fast_worker_saves_the_requested_tier_and_cli_settings(self):
        self.l.settle = lambda worker: None
        self.l.launch({'agent':'codex','mode':'worker','folder':FOLDER,'name':'fast-codex',
                       'model':'gpt-6.1-sol','effort':'high','fast':True}, set())
        worker = self.l.workers['fast-codex']
        self.assertTrue(worker['fast'])
        self.assertTrue(self.l.records['fast-codex']['fast'])
        self.assertTrue(self.l.list()[0]['fast'])
        self.assertIn('service_tier=fast', json.loads(Path(worker['settings']).read_text(encoding='utf-8'))['args'])


REASON = r"C:\Users\pat\AppData\Local\Reason\bin\reason.exe"


class DiscoverTest(unittest.TestCase):
    """Taking back `serve` workers that workers.json lost, with the process list faked."""
    def setUp(self):
        self.saved = launcher.started_at, launcher.Launcher.__dict__["alive"]
        launcher.started_at = lambda pid: f"t{pid}"
        launcher.Launcher.alive = staticmethod(lambda w: True)
        launcher.STATE.mkdir(parents=True, exist_ok=True)
        (launcher.STATE / "workers.json").write_text("[]", encoding="utf-8")  # the folder is shared by the tests
        self.l = launcher.Launcher("reason", FakeCatalog())
        logs = launcher.STATE / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        launcher.ledger_path().write_text("", encoding="utf-8")
        launcher.record_spawn("lost-claude", 100, "t100")  # this page started process 100
        (logs / "their-codex.log").write_text("x", encoding="utf-8")  # a leftover log proves nothing
        self.procs = [
            (100, 1, "reason.exe", [REASON, "network", "serve", "claude", "--name", "lost-claude", "--cwd", FOLDER,
                                    "--full-access"]),
            (101, 100, "claude.exe", ["claude", "-p"]),  # the shim in front of the agent
            (102, 101, "claude.exe", [r"C:\x\claude.exe", "--model", "claude-opus-5-5", "--effort", "high", "-p"]),
            (200, 1, "reason.exe", [REASON, "network", "serve", "codex", "--name", "their-codex", "--cwd", FOLDER]),
            (300, 1, "reason.exe", [REASON, "network", "who", "--json"]),
            (400, 1, "python.exe", ["python", "server.py", "network", "serve", "--name", "x"]),
        ]

    def tearDown(self):
        launcher.started_at, launcher.Launcher.alive = self.saved

    def test_parse_serve(self):
        self.assertEqual(launcher.parse_serve([REASON, "network", "serve", "codex", "--name", "w", "--cwd", "C:/x"]),
                         {"family": "codex", "name": "w", "cwd": "C:/x", "fullAccess": False})
        self.assertEqual(launcher.parse_serve([REASON, "network", "serve", "--name", "w"])["family"], "claude")
        for bad in ([REASON, "network", "who"], [REASON, "network", "serve", "grok", "--name", "w"],
                    [REASON, "network", "serve", "codex", "--name", "Bad Name"], [REASON, "network", "serve", "codex"]):
            self.assertIsNone(launcher.parse_serve(bad), bad)

    def test_model_from_args(self):
        self.assertEqual(launcher.model_from_args("claude", ["claude", "--model", "opus", "--effort", "high"]), ("opus", "high"))
        self.assertEqual(launcher.model_from_args("codex", ["codex", "-c", "model=gpt-6.1-sol", "-c",
                                                            "model_reasoning_effort=high", "exec"]), ("gpt-6.1-sol", "high"))
        self.assertEqual(launcher.model_from_args("codex", ["codex", "-c", "model=a b"]), (None, None))

    @unittest.skipUnless(launcher.WIN, "Windows command lines")
    def test_split_cmdline(self):
        self.assertEqual(launcher.split_cmdline('"C:\\Program Files\\r.exe" network serve --cwd "C:\\a b"'),
                         ["C:\\Program Files\\r.exe", "network", "serve", "--cwd", "C:\\a b"])

    def test_takes_back_its_own_and_lists_the_others(self):
        self.l.discover(self.procs)
        w = self.l.workers["lost-claude"]
        self.assertEqual((w["pid"], w["family"], w["model"], w["effort"], w["fullAccess"], w["settings"]),
                         (100, "claude", "claude-opus-5-5", "high", True, None))
        self.assertNotIn("their-codex", self.l.workers)  # no log here: not started by this page
        self.assertEqual([f["name"] for f in self.l.list_foreign()], ["their-codex"])
        self.l.discover(self.procs)  # again: nothing doubles
        self.assertEqual(sorted(self.l.workers), ["lost-claude"])
        self.assertEqual(self.l.adopt("their-codex"), {"ok": True})  # the user asked to manage it
        self.assertIn("their-codex", self.l.workers)
        with self.assertRaises(launcher.LaunchError):
            self.l.adopt("their-codex")

    def test_foreign_worker_does_not_inherit_an_older_workers_speed(self):
        self.l.records['their-codex'] = {'fast': True}
        self.l.discover(self.procs)
        self.assertIsNone(self.l.foreign['their-codex']['fast'])

    def test_same_name_new_process_is_not_ours(self):
        launcher.ledger_path().write_text("", encoding="utf-8")
        launcher.record_spawn("lost-claude", 999, "t999")  # an earlier process of that name, long gone
        self.l.discover(self.procs)
        self.assertNotIn("lost-claude", self.l.workers)
        self.assertIn("lost-claude", [f["name"] for f in self.l.list_foreign()])

    def test_adopted_outside_worker_is_not_stopped_through_its_console(self):
        self.l.discover(self.procs)
        self.l.adopt("their-codex")
        calls = []
        saved = launcher.interrupt, launcher.subprocess.run, launcher.list_processes, launcher.os.kill
        launcher.interrupt = lambda pid: calls.append(("ctrl-c", pid))
        launcher.subprocess.run = lambda args, **kw: calls.append(tuple(args[:2]))
        launcher.list_processes = lambda: self.procs
        active = {"value": True}
        launcher.os.kill = lambda pid, sig: (calls.append(("signal", pid)), active.update(value=False))[0]
        launcher.Launcher.alive = staticmethod(lambda w: active["value"])
        try:
            self.l.stop("their-codex")
        finally:
            launcher.interrupt, launcher.subprocess.run, launcher.list_processes, launcher.os.kill = saved
        self.assertNotIn(("ctrl-c", 200), calls)
        if launcher.WIN:
            self.assertIn(("taskkill", "/PID"), calls)

    def test_unknown_folder_is_not_restarted(self):
        procs = [(500, 1, "reason.exe", [REASON, "network", "serve", "codex", "--name", "no-cwd"])]
        launcher.record_spawn("no-cwd", 500, "t500")
        self.l.discover(procs)
        with self.assertRaises(launcher.LaunchError) as e:
            self.l.configure({"name": "no-cwd", "fullAccess": True}, False)
        self.assertEqual(e.exception.code, 409)

    def test_a_log_written_since_the_process_started_proves_it_is_ours(self):
        import os as _os
        launcher.ledger_path().write_text("", encoding="utf-8")
        log = launcher.STATE / "logs" / "their-codex.log"
        saved = launcher.started_at
        if launcher.WIN:
            ft = int(1700000000 * 1e7) + 116444736000000000  # process started at epoch 1_700_000_000
            launcher.started_at = lambda pid: str(ft)
        else:
            launcher.started_at = lambda pid: "Tue Nov 14 22:13:20 2023"
        try:
            _os.utime(log, (1600000000, 1600000000))  # written long before: an older worker's log
            self.l.discover(self.procs)
            self.assertNotIn("their-codex", self.l.workers)
            _os.utime(log, None)  # written now, after the process started
            self.l.discover(self.procs)
            self.assertIn("their-codex", self.l.workers)
        finally:
            launcher.started_at = saved

    def test_save_keeps_live_workers_another_writer_recorded(self):
        self.l.workers = {"mine": {"name": "mine", "pid": 1, "started": "t1", "family": "codex"}}
        launcher.STATE.mkdir(parents=True, exist_ok=True)
        self.l.reg.write_text(json.dumps([{"name": "theirs", "pid": 2, "started": "t2", "family": "claude"},
                                          {"name": "stopped-here", "pid": 3, "started": "t3", "family": "claude"}]),
                              encoding="utf-8")
        self.l.stopped.add("stopped-here")
        with self.l.lock:
            self.l.save()
        names = sorted(w["name"] for w in json.loads(self.l.reg.read_text(encoding="utf-8")))
        self.assertEqual(names, ["mine", "theirs"])


class RecordsTest(unittest.TestCase):
    """Settings kept for workers that died (a reboot), and starting them again."""
    def setUp(self):
        self.saved = launcher.started_at, launcher.Launcher.__dict__["alive"]
        launcher.started_at = lambda pid: f"t{pid}"
        launcher.Launcher.alive = staticmethod(lambda w: w["pid"] < 1000)  # pids from 1000 on are dead
        launcher.STATE.mkdir(parents=True, exist_ok=True)
        for f in ("workers.json", "worker-records.json", "spawned.jsonl"):
            (launcher.STATE / f).write_text("[]" if f == "workers.json" else "", encoding="utf-8")
        (launcher.STATE / "workers.json").write_text(json.dumps([
            {"name": "lead-codex", "pid": 5, "started": "t5", "family": "codex", "model": "gpt-6.1-sol",
             "effort": "high", "cwd": FOLDER, "fullAccess": True}]), encoding="utf-8")
        self.l = launcher.Launcher("reason", FakeCatalog())
        self.started = []

        def start(fam, cwd, model, effort, name, full, fast=None):
            self.started.append((name, fam["id"], cwd, model, effort, full))
            return {"name": name, "pid": 7, "started": "t7", "family": fam["id"], "model": model or None,
                    "effort": effort or None, "cwd": cwd, "log": "", "fullAccess": full, "fast": fast, "settings": None}
        self.l.start_worker = start
        self.l.settle = lambda w: None

    def tearDown(self):
        launcher.started_at, launcher.Launcher.alive = self.saved

    def test_seeded_from_the_running_registry(self):
        r = self.l.records["lead-codex"]
        self.assertEqual((r["family"], r["model"], r["effort"], r["fullAccess"]), ("codex", "gpt-6.1-sol", "high", True))
        self.assertIn((5, "t5"), launcher.spawned_here())  # and its start proof
        self.assertIn("lead-codex", json.loads((launcher.STATE / "worker-records.json").read_text(encoding="utf-8")))

    def test_record_outlives_the_process_and_starts_it_again(self):
        self.l.workers["lead-codex"]["pid"] = 1001  # the reboot
        with self.l.lock:
            self.l.save()  # on disk too, as after a real reboot
        self.l.list()  # prunes the registry
        self.assertNotIn("lead-codex", self.l.workers)
        self.assertIn("lead-codex", [r["name"] for r in self.l.list_records()])
        out = self.l.restart(["lead-codex"], blocked=set())
        self.assertEqual(out["results"], [{"name": "lead-codex", "ok": True}])
        self.assertEqual(self.started, [("lead-codex", "codex", FOLDER, "gpt-6.1-sol", "high", True)])

    def test_fast_record_survives_a_reboot(self):
        self.l.records['lead-codex']['fast'] = True
        self.l.save_records()
        self.l.workers['lead-codex']['pid'] = 1001
        self.l.save()
        self.l.list()
        self.l.restart(['lead-codex'], blocked=set())
        self.assertTrue(self.l.workers['lead-codex']['fast'])
        self.assertTrue(self.l.records['lead-codex']['fast'])

    def test_restart_refuses(self):
        res = lambda names, online=set(): self.l.restart(names, online)["results"]
        self.assertEqual(res(["lead-codex"])[0]["code"], 409)  # still running
        self.l.workers["lead-codex"]["pid"] = 1001
        with self.l.lock:
            self.l.save()
        self.assertEqual(res(["lead-codex"], {"lead-codex"})[0]["code"], 409)  # running here, or online elsewhere
        self.assertEqual(res(["nobody"])[0]["code"], 404)
        self.l.records["moved"] = dict(self.l.records["lead-codex"], name="moved", cwd=str(Path(FOLDER) / "gone"))
        with self.l.lock:
            self.l.save_records()
        self.assertIn("folder", res(["moved"])[0]["error"])
        self.l.records["odd"] = dict(self.l.records["lead-codex"], name="odd", model="no-such-model")
        with self.l.lock:
            self.l.save_records()
        self.assertIn("catalog", res(["odd"])[0]["error"])
        with self.assertRaises(launcher.LaunchError):
            self.l.restart("lead-codex", set())
        self.assertEqual(self.started, [])
        self.assertTrue(self.l.restart(["nobody"], set())["ok"])  # handled; the failure is in results

    def test_stale_name(self):
        who = {"person": "pat", "machine": "box", "sessions": [
            {"address": "pat/lead-codex", "status": "idle", "machine": "box"}]}
        self.assertTrue(self.l.stale("lead-codex", who, procs=[]))  # shown idle, but no serve process here
        running = [(9, 1, "reason.exe", ["reason", "network", "serve", "codex", "--name", "lead-codex", "--cwd", FOLDER])]
        self.assertFalse(self.l.stale("lead-codex", who, procs=running))
        elsewhere = {"person": "pat", "machine": "box", "sessions": [
            {"address": "pat/lead-codex", "status": "idle", "machine": "laptop"}]}
        self.assertFalse(self.l.stale("lead-codex", elsewhere, procs=[]))
        self.assertFalse(self.l.stale("not-ours", who, procs=[]))  # neither a record nor a log here
        saved = launcher.list_processes
        launcher.list_processes = lambda: None  # processes cannot be read (e.g. macOS): never free the name
        try:
            self.assertFalse(self.l.stale("lead-codex", who))
            self.assertIsNone(self.l.running_serve_names())
        finally:
            launcher.list_processes = saved

    def test_stale_names_after_discovery(self):
        self.assertEqual(self.l.stale_names(), set())  # nothing known before a discovery pass
        self.l.workers["lead-codex"]["pid"] = 1001  # killed
        with self.l.lock:
            self.l.save()
        self.l.discover([])  # no serve processes here
        self.assertEqual(self.l.stale_names(), {"lead-codex"})
        saved = launcher.list_processes
        launcher.list_processes = lambda: None
        try:
            self.l.discover()
            self.assertEqual(self.l.stale_names(), set())  # unknown again: claim nothing
        finally:
            launcher.list_processes = saved

    def test_newer_record_wins(self):
        path = launcher.STATE / "worker-records.json"
        newer = dict(self.l.records["lead-codex"], effort="low", started=10**15)
        path.write_text(json.dumps({"lead-codex": newer}), encoding="utf-8")  # another server's later change
        with self.l.lock:
            self.l.save_records()
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["lead-codex"]["effort"], "low")

    def test_inner_sessions(self):
        workers = {"claude-worker1", "lead-codex"}
        self.assertEqual(launcher.inner_of("claude-worker1-claude", workers), "claude-worker1")
        self.assertEqual(launcher.inner_of("claude-worker1-claude-3", workers), "claude-worker1")
        self.assertIsNone(launcher.inner_of("claude-worker1", workers))
        self.assertIsNone(launcher.inner_of("someone-else-claude", workers))
        self.assertIsNone(launcher.inner_of("helper-claude", {"helper", "helper-claude"}))  # a worker of its own

    def test_live_change_is_remembered(self):
        self.l.workers["lead-codex"]["settings"] = str(Path(tempfile.mkdtemp()) / "s.json")
        self.l.configure({"name": "lead-codex", "model": "gpt-6.1-sol", "effort": "low", "fullAccess": True}, False)
        self.assertEqual(self.l.records["lead-codex"]["effort"], "low")


if __name__ == "__main__":
    unittest.main()
