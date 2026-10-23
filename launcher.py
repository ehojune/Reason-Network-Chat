"""Start new agent sessions for Reason Network Chat.

Two ways to start one:
- worker: `reason network serve claude|codex` — a headless agent that answers network messages right away.
- window: the agent's own CLI in a new terminal window (Windows only) — interactive; it joins the network
  through the agent's Reason Network MCP server like any other session.

Model and effort lists come from each agent's own catalog, never from a list kept here:
Codex `models_cache.json`, `claude --help` (+ `~/.claude.json` extras), `agy models`.
Arguments always go to subprocess as a list; nothing is built into a shell string.
"""
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

HOME = Path.home()
WIN = sys.platform == "win32"
NOWIN = 0x08000000 if WIN else 0  # CREATE_NO_WINDOW
NEW_CONSOLE = 0x00000010  # CREATE_NEW_CONSOLE
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", HOME / "AppData" / "Local"))
STATE = Path(os.environ.get("REASON_CHAT_HOME", HOME / ".reason-network-chat"))

MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:\[\]-]{0,79}$")
EFFORT_RE = re.compile(r"^[a-z]{2,12}$")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")
EFFORT_ORDER = ["minimal", "low", "medium", "high", "xhigh", "max", "ultra"]
MAX_WORKERS = 8
CATALOG_TTL = 600  # seconds
# Variables an agent session sets for itself and its tools. A server started from inside one (the Claude desktop
# preview, a Codex shell command) inherits them; a new agent must not, or it thinks it is nested in that session.
# Settings and credentials (CODEX_API_KEY, CODEX_HOME, CLAUDE_CODE_USE_BEDROCK, …) are kept.
SESSION_VARS = {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "AI_AGENT",
                "CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_TOOL_CALL_ID"}
SESSION_PREFIX = ("CODEX_SANDBOX", "CODEX_NETWORK_", "CODEX_INTERNAL_", "REASON_NETWORK_", "TINCAN_")
# Set by a Claude host for the session it runs; only dropped when this server runs inside Claude Code.
CLAUDE_HOST_PREFIX = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK_", "CLAUDE_PREVIEW_")


# ---------- environment ----------

def user_env():
    """The Windows user and machine environment as stored, not as this process inherited it.
    Fills in variables set after the server started (NODE_EXTRA_CA_CERTS behind TLS-inspecting proxies)
    and tells deliberate settings apart from agent-session markers."""
    if not WIN:
        return {}
    import winreg
    out = {}
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(root, key) as k:
                for i in range(winreg.QueryInfoKey(k)[1]):
                    name, value, kind = winreg.EnumValue(k, i)
                    if isinstance(value, str):
                        out[name.upper()] = os.path.expandvars(value) if kind == winreg.REG_EXPAND_SZ else value
        except OSError:
            continue
    return out


def is_session_var(name, in_claude=False):
    n = name.upper()
    return n in SESSION_VARS or n.startswith(SESSION_PREFIX) or (in_claude and n.startswith(CLAUDE_HOST_PREFIX))


def base_env():
    """Environment for every child process: CA bundle filled in, agent-session markers removed
    unless the user set the same variable on purpose."""
    stored = user_env()
    in_claude = "CLAUDECODE" in os.environ
    env = {k: v for k, v in os.environ.items() if not is_session_var(k, in_claude) or k.upper() in stored}
    if not env.get("NODE_EXTRA_CA_CERTS") and stored.get("NODE_EXTRA_CA_CERTS"):
        env["NODE_EXTRA_CA_CERTS"] = stored["NODE_EXTRA_CA_CERTS"]
    return env


# ---------- executables ----------

def which_exe(name):
    """An executable on PATH. On Windows only a real .exe: a .cmd/.bat shim would let cmd.exe re-parse arguments."""
    if not WIN:
        return shutil.which(name)
    for d in os.environ.get("PATH", "").split(os.pathsep):
        d = d.strip().strip('"')
        if d and (Path(d) / f"{name}.exe").is_file():
            return str(Path(d) / f"{name}.exe")
    return None


def from_env(var):
    p = os.environ.get(var)
    return p if p and Path(p).is_file() else None


def find_claude():
    p = HOME / ".local" / "bin" / ("claude.exe" if WIN else "claude")
    return from_env("REASON_CHAT_CLAUDE") or (str(p) if p.is_file() else None) or which_exe("claude")


def find_codex():
    if from_env("REASON_CHAT_CODEX"):
        return from_env("REASON_CHAT_CODEX")
    if WIN:  # the Codex app keeps the CLI in a hashed folder; the newest one with codex.exe wins
        found = sorted((LOCALAPPDATA / "OpenAI" / "Codex" / "bin").glob("*/codex.exe"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if found:
            return str(found[0])
    return which_exe("codex")


def find_agy():
    p = LOCALAPPDATA / "agy" / "bin" / "agy.exe"
    return from_env("REASON_CHAT_AGY") or (str(p) if WIN and p.is_file() else None) or which_exe("agy")


def run_text(args, timeout):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           env=base_env(), creationflags=NOWIN)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return p.stdout.decode("utf-8", "replace") + "\n" + p.stderr.decode("utf-8", "replace")


# ---------- catalogs ----------

def toml_top(path, keys):
    """Top-level string values from a TOML file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        import tomllib  # Python 3.11+
        data = tomllib.loads(text)
        return {k: data[k] for k in keys if isinstance(data.get(k), str)}
    except ImportError:
        pass
    except ValueError:
        return {}
    out = {}
    for line in text.splitlines():
        if line.lstrip().startswith("["):
            break
        m = re.match(r'\s*([A-Za-z_]+)\s*=\s*"([^"]*)"', line)
        if m and m.group(1) in keys:
            out[m.group(1)] = m.group(2)
    return out


def sort_efforts(efforts):
    seen = []
    for e in efforts:
        if e and EFFORT_RE.match(e) and e not in seen:
            seen.append(e)
    return sorted(seen, key=lambda e: EFFORT_ORDER.index(e) if e in EFFORT_ORDER else len(EFFORT_ORDER))


def codex_catalog(exe):
    home = Path(os.environ.get("CODEX_HOME") or HOME / ".codex")
    try:
        data = json.loads((home / "models_cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    models = []
    for m in sorted(data.get("models") or [], key=lambda m: m.get("priority", 999)):
        slug = str(m.get("slug", ""))
        if m.get("visibility") != "list" or not MODEL_RE.match(slug):
            continue
        levels = m.get("supported_reasoning_levels") or []
        efforts = sort_efforts([str(x.get("effort", "")) for x in levels if isinstance(x, dict)])
        default = m.get("default_reasoning_level")
        models.append({"id": slug, "label": str(m.get("display_name") or slug), "efforts": efforts,
                       "defaultEffort": default if default in efforts else None})
    cfg = toml_top(home / "config.toml", ("model", "model_reasoning_effort"))
    note = None if models else "models_cache.json not found: start Codex once to fill it."
    return {"models": models, "defaultModel": cfg.get("model"), "defaultEffort": cfg.get("model_reasoning_effort"),
            "efforts": sort_efforts(e for m in models for e in m["efforts"]), "note": note}


def option_block(help_text, flag):
    """The help text of one CLI option, up to the next option line."""
    m = re.search(r"^\s+" + re.escape(flag) + r"\b(.*?)(?=^\s+-|\Z)", help_text, re.S | re.M)
    return m.group(1) if m else ""


def claude_catalog(exe):
    text = run_text([exe, "--help"], 30)
    aliases = re.findall(r"'([a-z][a-z0-9-]*)'", option_block(text, "--model"))
    levels = re.search(r"\(([a-z]+(?:,\s*[a-z]+)+)\)", option_block(text, "--effort"))
    efforts = sort_efforts(re.split(r",\s*", levels.group(1))) if levels else []
    models = [{"id": a, "label": a, "efforts": efforts, "defaultEffort": None} for a in aliases if MODEL_RE.match(a)]
    try:  # extra models this account can pick in Claude Code's /model menu
        extra = json.loads((HOME / ".claude.json").read_text(encoding="utf-8")).get("additionalModelOptionsCache") or []
    except (OSError, ValueError, AttributeError):
        extra = []
    for o in extra:
        v = o.get("value") if isinstance(o, dict) else None
        if isinstance(v, str) and MODEL_RE.match(v) and all(m["id"] != v for m in models):
            models.append({"id": v, "label": f'{o.get("label") or v} ({v})', "efforts": efforts, "defaultEffort": None})
    try:
        settings = json.loads((HOME / ".claude" / "settings.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
    dm, de = settings.get("model"), settings.get("effortLevel")
    note = None if models else "Could not read the model list from `claude --help`."
    return {"models": models, "defaultModel": dm if isinstance(dm, str) else None,
            "defaultEffort": de if isinstance(de, str) else None, "efforts": efforts, "note": note}


def agy_catalog(exe):
    """`agy models` prints `id<TAB>label`; ids end in their effort (gemini-4-argon-high)."""
    groups = {}
    for line in run_text([exe, "models"], 60).splitlines():
        if "\t" not in line:
            continue
        mid, label = (s.strip() for s in line.split("\t", 1))
        if not MODEL_RE.match(mid):
            continue
        m = re.match(r"^(.*)-(" + "|".join(EFFORT_ORDER) + r")$", mid)
        base, effort = (m.group(1), m.group(2)) if m else (mid, None)
        g = groups.setdefault(base, {"id": base, "label": re.sub(r"\s*\([^)]*\)$", "", label) or base,
                                     "efforts": [], "defaultEffort": None, "ids": []})
        g["ids"].append(mid)
        if effort:
            g["efforts"].append(effort)
    models = []
    for g in groups.values():
        g["efforts"] = sort_efforts(g["efforts"])
        if "medium" in g["efforts"]:
            g["defaultEffort"] = "medium"
        models.append(g)
    note = None if models else "`agy models` returned nothing: sign in to Antigravity first."
    return {"models": models, "defaultModel": None, "defaultEffort": None,
            "efforts": sort_efforts(e for m in models for e in m["efforts"]), "note": note}


FAMILIES = [  # id, label, finder, catalog, Reason `serve` agent name or None
    ("claude", "Claude Code", find_claude, claude_catalog, "claude"),
    ("codex", "Codex", find_codex, codex_catalog, "codex"),
    ("antigravity", "Antigravity", find_agy, agy_catalog, None),
]


# ---------- Codex model shim ----------
# `reason network serve codex` runs `codex exec …` with no way to pass a model. A worker that should use a
# different model or effort gets a PATH entry whose `codex` adds `-c model=… -c model_reasoning_effort=…`
# (from REASON_CHAT_CODEX_ARGS) and runs the real CLI (REASON_CHAT_CODEX_REAL). On Windows it is an .exe made
# from pip's script launcher, because Bun refuses to pass message text to a .cmd file.

SHIM_MAIN = b'''import json, os, subprocess, sys
real = os.environ.get("REASON_CHAT_CODEX_REAL")
if not real:
    sys.exit("REASON_CHAT_CODEX_REAL is not set")
extra = json.loads(os.environ.get("REASON_CHAT_CODEX_ARGS") or "[]")
sys.exit(subprocess.call([real] + extra + sys.argv[1:]))
'''


def shim_dir():
    """Folder holding the Codex shim, built on first use; None when it cannot be built."""
    d = STATE / "codex-shim"
    target = d / ("codex.exe" if WIN else "codex")
    exe = sys.executable.encode("utf-8")
    if WIN:
        try:
            from pip._vendor.distlib.scripts import ScriptMaker
            launcher = ScriptMaker(None, None)._get_launcher("t")
        except Exception:
            return None
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:  # fixed timestamp: the same Python gives the same bytes
            z.writestr(zipfile.ZipInfo("__main__.py", date_time=(1980, 1, 1, 0, 0, 0)), SHIM_MAIN)
        data = launcher + b"#!" + (b'"' + exe + b'"' if b" " in exe else exe) + b"\n" + buf.getvalue()
    else:
        data = b"#!" + exe + b"\n" + SHIM_MAIN
    try:
        d.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != data:
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, target)
        if not WIN:
            target.chmod(0o755)
    except OSError:  # e.g. a running worker holds the old shim open; it still works
        return str(d) if target.is_file() else None
    return str(d)


# ---------- catalog cache ----------

class Catalog:
    def __init__(self, reason):
        self.reason = reason
        self.data = None
        self.at = 0
        self.lock = threading.Lock()

    def get(self, refresh=False):
        with self.lock:
            if refresh or self.data is None or time.time() - self.at > CATALOG_TTL:
                self.data = self.build()
                self.at = time.time()
            return self.data

    def build(self):
        shim = shim_dir() is not None
        out = []
        for fid, label, finder, catalog, serve in FAMILIES:
            exe = finder()
            fam = {"id": fid, "label": label, "installed": bool(exe), "models": [], "efforts": [],
                   "defaultModel": None, "defaultEffort": None, "note": None, "modes": {}}
            if exe:
                fam.update(catalog(exe))
            missing = None if exe else f"{label} is not installed on this computer."
            fam["modes"]["worker"] = {
                "ok": bool(exe and serve and self.reason),
                "why": missing or (None if serve else "`reason network serve` runs only Claude Code and Codex."),
                # A Codex worker can only use another model through the shim.
                "models": bool(serve) and (fid != "codex" or shim),
                "modelsWhy": None if fid != "codex" or shim else
                "This Python has no pip launcher, so a Codex worker uses your Codex default model.",
            }
            fam["modes"]["window"] = {"ok": bool(exe and WIN), "models": True, "modelsWhy": None,
                                      "why": missing or (None if WIN else "Terminal windows open on Windows only.")}
            out.append(fam)
        return out

    def family(self, fid):
        return next((f for f in self.get() if f["id"] == fid), None)


# ---------- process start time (to recognise our own workers after a restart) ----------

def started_at(pid):
    """Creation time of a running process, or None if it is gone."""
    if WIN:
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        k.CloseHandle.argtypes = (wintypes.HANDLE,)
        h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            code = wintypes.DWORD()
            if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:  # STILL_ACTIVE
                return None
            t = [wintypes.FILETIME() for _ in range(4)]
            if not k.GetProcessTimes(h, *[ctypes.byref(x) for x in t]):
                return None
            return str((t[0].dwHighDateTime << 32) | t[0].dwLowDateTime)
        finally:
            k.CloseHandle(h)
    try:
        out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.decode("utf-8", "replace").strip() or None


# A worker reports "stopped" to the network only when it exits on Ctrl+C; killed, it stays "idle" for good.
# Each worker runs in its own hidden console: CREATE_NO_WINDOW still gives a console process a console, only
# without a window, so AttachConsole(pid) works (checked: the helper exits 0, the worker exits at once and the
# network shows it stopped). The helper attaches to that console and sends Ctrl+C there, so the server's own
# console (if any) is never touched.
CTRL_C_HELPER = """import ctypes, sys
k = ctypes.windll.kernel32
k.FreeConsole()
if not k.AttachConsole(int(sys.argv[1])):
    sys.exit(1)
k.SetConsoleCtrlHandler(None, True)
sys.exit(0 if k.GenerateConsoleCtrlEvent(0, 0) else 1)
"""


def allow_ctrl_c():
    """Children inherit "ignore Ctrl+C" from their parent; clear it so workers can be stopped gracefully."""
    if WIN:
        import ctypes
        ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)


def interrupt(pid):
    if WIN:
        subprocess.run([sys.executable, "-c", CTRL_C_HELPER, str(pid)], capture_output=True, timeout=10,
                       creationflags=NOWIN)
    else:
        try:
            os.killpg(pid, signal.SIGINT)  # workers start in their own session: pgid == pid
        except OSError:
            pass


def kill_tree(pid):
    if WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=NOWIN)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except OSError:
            pass


# ---------- launching ----------
# Workers and windows must not be children of this server: the Claude desktop app stops a preview by killing its
# whole process tree, which would take every worker with it and leave it showing "idle" on the network for good.
# A short-lived spawner starts the process and exits, so the process has no living parent to be found through.
SPAWNER = """import json, subprocess, sys
spec = json.loads(sys.stdin.read())
kw = {"cwd": spec["cwd"], "env": spec["env"]}
if spec["log"]:
    kw.update(stdin=subprocess.DEVNULL, stdout=open(spec["log"], "ab"), stderr=subprocess.STDOUT)
try:  # also leave any job object the server runs in, when the job allows it
    p = subprocess.Popen(spec["args"], creationflags=spec["flags"] | 0x01000000, **kw)
except OSError:
    p = subprocess.Popen(spec["args"], creationflags=spec["flags"], **kw)
print(p.pid)
"""


def spawn(args, cwd, env, flags, log=None):
    """Start a process detached from this server; returns its pid."""
    if not WIN:  # its own session: not in this server's process group
        with open(log or os.devnull, "ab") as out:
            return subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=subprocess.STDOUT, start_new_session=True).pid
    spec = {"args": args, "cwd": cwd, "env": env, "flags": flags, "log": log}
    r = subprocess.run([sys.executable, "-c", SPAWNER], input=json.dumps(spec).encode("utf-8"), capture_output=True,
                       timeout=30, creationflags=NOWIN)
    try:
        return int(r.stdout.strip())
    except ValueError:
        raise LaunchError("Could not start it: " + r.stderr.decode("utf-8", "replace").strip()[-300:], 500)


class LaunchError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


class Launcher:
    def __init__(self, reason, catalog):
        self.reason = reason
        self.catalog = catalog
        self.lock = threading.Lock()
        self.reg = STATE / "workers.json"
        self.workers = {}  # name -> {name, pid, started, family, model, effort, cwd, log}
        self.load()

    # Registry on disk, so a restarted server can still stop the workers it started.
    def load(self):
        try:
            items = json.loads(self.reg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            items = []
        for w in items if isinstance(items, list) else []:
            if isinstance(w, dict) and isinstance(w.get("pid"), int) and w.get("started") \
                    and started_at(w["pid"]) == w["started"] and NAME_RE.match(str(w.get("name", ""))):
                self.workers[w["name"]] = w
        self.save()

    def save(self):
        try:
            STATE.mkdir(parents=True, exist_ok=True)
            tmp = self.reg.with_suffix(".tmp")
            tmp.write_text(json.dumps(list(self.workers.values()), ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.reg)
        except OSError:
            pass

    @staticmethod
    def alive(w):
        return started_at(w["pid"]) == w["started"]

    def list(self):
        with self.lock:
            gone = [n for n, w in self.workers.items() if not self.alive(w)]
            for n in gone:
                del self.workers[n]
            if gone:
                self.save()
            return [{k: w[k] for k in ("name", "family", "model", "effort", "cwd")} for w in self.workers.values()]

    def stop(self, name):
        with self.lock:
            w = self.workers.pop(name, None)
            if not w:
                raise LaunchError("Not a worker started here.", 404)
            self.save()
        if not self.alive(w):
            return
        try:
            interrupt(w["pid"])
        except (OSError, subprocess.TimeoutExpired):
            pass
        for _ in range(100):  # serve tells the network "stopped", then exits
            if not self.alive(w):
                return
            time.sleep(0.1)
        kill_tree(w["pid"])

    def check(self, req, live_names):
        """Validate a launch request against the catalogs; returns the cleaned values."""
        fid, mode = req.get("agent"), req.get("mode")
        folder, model, effort, name = req.get("folder"), req.get("model") or "", req.get("effort") or "", req.get("name") or ""
        if not all(isinstance(v, str) for v in (fid, mode, folder, model, effort, name)):
            raise LaunchError("agent, mode, folder, model, effort and name must be strings.")
        fam = self.catalog.family(fid)
        if not fam:
            raise LaunchError("Unknown agent.")
        m = fam["modes"].get(mode)
        if not m:
            raise LaunchError("mode must be worker or window.")
        if not m["ok"]:
            raise LaunchError(m["why"] or "Not available.")
        if (model or effort) and not m["models"]:
            raise LaunchError(m["modelsWhy"] or "This agent cannot pick a model here.")
        entry = None
        if model:
            entry = next((x for x in fam["models"] if x["id"] == model), None)
            if not entry:
                raise LaunchError("That model is not in the agent's catalog.")
        if effort:  # with no model chosen, the agent's default model decides which efforts exist
            default = next((x for x in fam["models"] if x["id"] == fam["defaultModel"]), None)
            allowed = (entry or default or fam)["efforts"]
            if effort not in allowed:
                raise LaunchError("That effort is not offered for this model.")
        if fid == "antigravity":  # agy model ids carry the effort: gemini-4-argon-high
            if effort and not entry:
                raise LaunchError("Pick a model to pick an effort.")
            if entry and entry["efforts"] and not effort:
                effort = entry.get("defaultEffort") or entry["efforts"][0]
            if entry and (f"{model}-{effort}" if effort else model) not in entry["ids"]:
                raise LaunchError("That model is not in the agent's catalog.")
        if not folder or len(folder) > 1024 or any(c in folder for c in "\r\n\0"):
            raise LaunchError("Pick a folder.")
        path = Path(os.path.expandvars(folder.strip())).expanduser()
        if not path.is_absolute():
            raise LaunchError("Use a full folder path.")
        if str(path).startswith(("\\\\", "//")):
            raise LaunchError("Network folders are not supported.")
        if not path.is_dir():
            raise LaunchError("That folder does not exist.")
        if mode == "worker":
            if not NAME_RE.match(name):
                raise LaunchError("Name: lowercase letters, digits and dashes, up to 48.")
            if name in live_names or name in self.workers:
                raise LaunchError("A session with that name is already on the network.", 409)
        return fam, mode, str(path.resolve()), entry, model, effort, name

    def launch(self, req, live_names):
        with self.lock:
            fam, mode, cwd, entry, model, effort, name = self.check(req, live_names)
            if mode == "window":
                return self.open_window(fam, cwd, model, effort)
            if len([w for w in self.workers.values() if self.alive(w)]) >= MAX_WORKERS:
                raise LaunchError(f"Already {MAX_WORKERS} workers started here; stop one first.", 429)
            w = self.start_worker(fam, cwd, model, effort, name)
            self.workers[name] = w
            self.save()
        for _ in range(30):  # a bad setup fails within a few seconds
            if not self.alive(w):
                with self.lock:
                    self.workers.pop(name, None)
                    self.save()
                tail = Path(w["log"]).read_bytes()[-600:].decode("utf-8", "replace").strip()
                raise LaunchError(f"The worker exited: {tail}", 502)
            time.sleep(0.1)
        return {"ok": True, "mode": "worker", "name": name}

    def start_worker(self, fam, cwd, model, effort, name):
        env = base_env()
        fid = fam["id"]
        if fid == "claude":
            exe = find_claude()
            env["PATH"] = os.pathsep.join([str(Path(exe).parent), env.get("PATH", "")])
            if model:
                env["ANTHROPIC_MODEL"] = model
            if effort:
                env["CLAUDE_CODE_EFFORT_LEVEL"] = effort
        else:
            real = find_codex()
            dirs = [str(Path(real).parent)]  # ahead of any codex.cmd shim on PATH
            if model or effort:
                shim = shim_dir()
                if not shim:
                    raise LaunchError("Could not build the Codex model shim.", 500)
                dirs.insert(0, shim)
                env["REASON_CHAT_CODEX_REAL"] = real
                env["REASON_CHAT_CODEX_ARGS"] = json.dumps(
                    (["-c", f"model={model}"] if model else []) + (["-c", f"model_reasoning_effort={effort}"] if effort else []))
            env["PATH"] = os.pathsep.join(dirs + [env.get("PATH", "")])
        logs = STATE / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        log_path = logs / f"{name}.log"
        args = [self.reason, "network", "serve", fid, "--name", name, "--cwd", cwd]
        pid = spawn(args, cwd, env, NOWIN, str(log_path))
        return {"name": name, "pid": pid, "started": started_at(pid) or "", "family": fid,
                "model": model or None, "effort": effort or None, "cwd": cwd, "log": str(log_path)}

    def open_window(self, fam, cwd, model, effort):
        fid = fam["id"]
        if fid == "claude":
            args = [find_claude()] + (["--model", model] if model else []) + (["--effort", effort] if effort else [])
        elif fid == "codex":
            args = [find_codex()] + (["-m", model] if model else []) + \
                   (["-c", f"model_reasoning_effort={effort}"] if effort else [])
        else:
            mid = f"{model}-{effort}" if model and effort else model
            args = [find_agy()] + (["--model", mid] if mid else [])
        spawn(args, cwd, base_env(), NEW_CONSOLE)
        return {"ok": True, "mode": "window"}
