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
import shlex
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
# ...except the settings a user sets on purpose and a new Claude needs: provider, auth, client certs, shell, limits.
CLAUDE_KEEP = re.compile(r"^CLAUDE_CODE_(USE_|SKIP_\w*AUTH|CLIENT_|GIT_BASH_PATH|SHELL|MAX_|API_KEY_HELPER"
                         r"|DISABLE_NONESSENTIAL_TRAFFIC|EXTRA_BODY)")


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
    if n in SESSION_VARS or n.startswith(SESSION_PREFIX):
        return True
    return in_claude and n.startswith(CLAUDE_HOST_PREFIX) and not CLAUDE_KEEP.match(n)


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


# Each CLI's own "run without asking" flag, for a terminal window (checked in each --help: claude 2.x, codex 0.163,
# agy). A worker gets `reason network serve --full-access`, which passes the same to the agent it runs.
FULL_ACCESS = {
    "claude": ["--permission-mode", "bypassPermissions"],
    "codex": ["--dangerously-bypass-approvals-and-sandbox"],
    "antigravity": ["--dangerously-skip-permissions"],
}

FAMILIES = [  # id, label, finder, catalog, Reason `serve` agent name or None
    ("claude", "Claude Code", find_claude, claude_catalog, "claude"),
    ("codex", "Codex", find_codex, codex_catalog, "codex"),
    ("antigravity", "Antigravity", find_agy, agy_catalog, None),
]


# ---------- model shim ----------
# `reason network serve` has no model or effort flag: it runs `codex exec …` per message and keeps warm
# `claude -p …` processes, both found through PATH. (An effort in CLAUDE_CODE_EFFORT_LEVEL does not reach a
# `claude -p` stream-json child.) So a worker's PATH starts with a shim folder whose `codex` / `claude` adds the
# model and effort arguments and runs the real CLI (REASON_CHAT_SHIM_REAL). The arguments come from the worker's
# settings file (REASON_CHAT_SHIM_SETTINGS, read on every run, so a Codex worker picks up a change with its next
# message), else from REASON_CHAT_SHIM_ARGS. The REASON_CHAT_CODEX_* names are read too, for workers started
# before the shim was shared. On Windows it is an .exe made from pip's script launcher, because Bun refuses to
# pass message text to a .cmd file.

SHIM_MAIN = b'''import json, os, subprocess, sys
env = os.environ
real = env.get("REASON_CHAT_SHIM_REAL") or env.get("REASON_CHAT_CODEX_REAL")
if not real:
    sys.exit("REASON_CHAT_SHIM_REAL is not set")
extra = None
if env.get("REASON_CHAT_SHIM_SETTINGS"):
    try:
        with open(env["REASON_CHAT_SHIM_SETTINGS"], encoding="utf-8") as f:
            extra = json.load(f).get("args")
    except (OSError, ValueError, AttributeError):
        extra = None
if not isinstance(extra, list):
    extra = json.loads(env.get("REASON_CHAT_SHIM_ARGS") or env.get("REASON_CHAT_CODEX_ARGS") or "[]")
sys.exit(subprocess.call([real] + [str(a) for a in extra] + sys.argv[1:]))
'''
SHIM_AGENTS = ("codex", "claude")  # the CLI names `serve` looks up on PATH


def _shim_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:  # fixed timestamp: the same Python gives the same bytes
        z.writestr(zipfile.ZipInfo("__main__.py", date_time=(1980, 1, 1, 0, 0, 0)), SHIM_MAIN)
    return buf.getvalue()


SHIM_ZIP = _shim_zip()  # the end of the Windows shim .exe


def model_args(fid, model, effort):
    """CLI arguments that pick a model and effort for one agent family."""
    if fid == "claude":
        return (["--model", model] if model else []) + (["--effort", effort] if effort else [])
    return (["-c", f"model={model}"] if model else []) + (["-c", f"model_reasoning_effort={effort}"] if effort else [])


def write_settings(path, args):
    """The per-worker file the shim reads its model arguments from (written first, then swapped in)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"args": args}), encoding="utf-8")
    os.replace(tmp, path)


def shim_current(kind):
    """The shim on disk is this version (it can stay older while a running turn holds the old .exe open)."""
    target = STATE / f"{kind}-shim" / (f"{kind}.exe" if WIN else kind)
    if not WIN:
        target = STATE / f"{kind}-shim" / f"{kind}_shim.py"
        try:
            return target.read_bytes() == SHIM_MAIN
        except OSError:
            return False
    try:
        return target.read_bytes().endswith(SHIM_ZIP)
    except OSError:
        return False


def shim_dir(kind="codex"):
    """Folder holding the `codex` or `claude` shim, built on first use; None when it cannot be built."""
    if kind not in SHIM_AGENTS:
        raise ValueError(kind)
    d = STATE / f"{kind}-shim"
    target = d / (f"{kind}.exe" if WIN else kind)
    exe = sys.executable.encode("utf-8")
    extra = []  # (path, bytes) written next to the shim
    if WIN:
        try:
            from pip._vendor.distlib.scripts import ScriptMaker
            launcher = ScriptMaker(None, None)._get_launcher("t")
        except Exception:
            return None
        data = launcher + b"#!" + (b'"' + exe + b'"' if b" " in exe else exe) + b"\n" + SHIM_ZIP
    else:  # a shebang cannot hold a path with spaces; sh can, quoted
        q = lambda b: b"'" + b.replace(b"'", b"'\\''") + b"'"
        main = d / f"{kind}_shim.py"
        extra.append((main, SHIM_MAIN))
        data = b"#!/bin/sh\nexec " + q(exe) + b" " + q(str(main).encode("utf-8")) + b' "$@"\n'
    try:
        d.mkdir(parents=True, exist_ok=True)
        for path, content in extra + [(target, data)]:
            if not path.is_file() or path.read_bytes() != content:
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(content)
                os.replace(tmp, path)
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
        shims = {k: shim_dir(k) is not None for k in SHIM_AGENTS}
        out = []
        for fid, label, finder, catalog, serve in FAMILIES:
            exe = finder()
            fam = {"id": fid, "label": label, "installed": bool(exe), "models": [], "efforts": [],
                   "defaultModel": None, "defaultEffort": None, "note": None, "modes": {}}
            if exe:
                fam.update(catalog(exe))
            missing = None if exe else f"{label} is not installed on this computer."
            shim = shims.get(serve or "", False)
            fam["modes"]["worker"] = {
                "ok": bool(exe and serve and self.reason),
                "why": missing or (None if serve else "`reason network serve` runs only Claude Code and Codex."),
                # A worker can only use another model through the shim (`serve` has no model flag).
                "models": bool(serve) and shim,
                "modelsWhy": None if not serve or shim else
                "This Python has no pip launcher, so a worker uses the agent's default model.",
                "fullAccess": bool(serve),  # `serve --full-access`
            }
            fam["modes"]["window"] = {"ok": bool(exe and WIN), "models": True, "modelsWhy": None,
                                      "why": missing or (None if WIN else "Terminal windows open on Windows only."),
                                      "fullAccess": fid in FULL_ACCESS}
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
SPAWNER = """import json, os, subprocess, sys
spec = json.loads(sys.stdin.read())
kw = {"cwd": spec["cwd"], "env": spec["env"]}
if spec["log"]:
    kw.update(stdin=subprocess.DEVNULL, stdout=open(spec["log"], "ab"), stderr=subprocess.STDOUT)
elif os.name != "nt":  # nothing may hold this spawner's stdout pipe open
    kw.update(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if os.name != "nt":  # its own session and process group, so Ctrl+C can go to the whole group
    p = subprocess.Popen(spec["args"], start_new_session=True, **kw)
else:
    try:  # also leave any job object the server runs in, when the job allows it
        p = subprocess.Popen(spec["args"], creationflags=spec["flags"] | 0x01000000, **kw)
    except OSError:
        p = subprocess.Popen(spec["args"], creationflags=spec["flags"], **kw)
print(p.pid)
"""


def spawn(args, cwd, env, flags, log=None):
    """Start a process detached from this server (on every platform: a tree kill follows parent pids); returns its pid."""
    spec = {"args": args, "cwd": cwd, "env": env, "flags": flags, "log": log}
    r = subprocess.run([sys.executable, "-c", SPAWNER], input=json.dumps(spec).encode("utf-8"), capture_output=True,
                       timeout=30, creationflags=NOWIN if WIN else 0)
    try:
        return int(r.stdout.strip())
    except ValueError:
        raise LaunchError("Could not start it: " + r.stderr.decode("utf-8", "replace").strip()[-300:], 500)


def efforts_for(fam, entry):
    """Efforts a request may name: the chosen model's; with no model, the agent's known default model's;
    with neither, only those every listed model supports, so whatever model runs accepts it."""
    model = entry or next((x for x in fam["models"] if x["id"] == fam["defaultModel"]), None)
    if model:
        return model["efforts"]
    if not fam["models"]:
        return fam["efforts"]
    return [e for e in fam["efforts"] if all(e in m["efforts"] for m in fam["models"])]


# ---------- finding `serve` workers this page lost track of ----------
# workers.json can lose entries (two servers writing it from memory did, before exclusive binding). The processes
# keep running, so the server looks for `reason network serve` command lines and takes back those it started.

def split_cmdline(cmd):
    """A Windows command line as argv (CommandLineToArgvW)."""
    if not cmd:
        return []
    import ctypes
    from ctypes import wintypes
    f = ctypes.windll.shell32.CommandLineToArgvW
    f.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int))
    f.restype = ctypes.POINTER(wintypes.LPWSTR)
    n = ctypes.c_int()
    argv = f(cmd, ctypes.byref(n))
    if not argv:
        return []
    try:
        return [argv[i] for i in range(n.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


def list_processes():
    """[(pid, parent pid, program name, argv)] for every process on this computer, or [] when they cannot be read."""
    if WIN:
        # UTF-8 out, or a Korean/Chinese console code page garbles non-ASCII folders in the JSON.
        ps = ("[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
              "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine | ConvertTo-Json -Compress")
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                                 timeout=60, stdin=subprocess.DEVNULL, creationflags=NOWIN).stdout
            items = json.loads(out.decode("utf-8", "replace") or "[]")
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return []
        items = [items] if isinstance(items, dict) else items if isinstance(items, list) else []
        return [(p.get("ProcessId"), p.get("ParentProcessId"), str(p.get("Name") or ""),
                 split_cmdline(p.get("CommandLine") or "")) for p in items if isinstance(p, dict)]
    # Elsewhere only /proc keeps argv boundaries (`ps` joins arguments with spaces, so a folder with a space would be
    # cut); without /proc (macOS) nothing is found.
    rows = []
    for d in Path("/proc").glob("[0-9]*"):
        try:
            argv = [a.decode("utf-8", "replace") for a in (d / "cmdline").read_bytes().split(b"\0") if a]
            ppid = int((d / "stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        rows.append((int(d.name), ppid, Path(argv[0]).name if argv else "", argv))
    return rows


def parse_serve(argv):
    """{family, name, cwd, fullAccess} of a `reason network serve [claude|codex] --name N --cwd D [--full-access]`
    command line, or None."""
    for i in range(len(argv) - 1):
        if argv[i] == "network" and argv[i + 1] == "serve":
            rest = argv[i + 2:]
            break
    else:
        return None
    family = "claude"  # serve's own default
    if rest and not rest[0].startswith("-"):
        family, rest = rest[0], rest[1:]
    if family not in ("claude", "codex"):
        return None
    out = {"family": family, "name": None, "cwd": None, "fullAccess": False}
    k = 0
    while k < len(rest):
        if rest[k] in ("--name", "--cwd") and k + 1 < len(rest):
            out[rest[k][2:]] = rest[k + 1]
            k += 2
            continue
        out["fullAccess"] = out["fullAccess"] or rest[k] == "--full-access"
        k += 1
    return out if out["name"] and NAME_RE.match(out["name"]) else None


def model_from_args(family, argv):
    """(model, effort) a worker's agent runs with, read from its command line (or its shim's arguments)."""
    model = effort = None
    for k, a in enumerate(argv[:-1]):
        nxt = argv[k + 1]
        if family == "claude" and a == "--model":
            model = nxt
        elif family == "claude" and a == "--effort":
            effort = nxt
        elif family == "codex" and a == "-c":
            key, _, val = nxt.partition("=")
            val = val.strip('"')
            if key == "model":
                model = val
            elif key == "model_reasoning_effort":
                effort = val
    return (model if model and MODEL_RE.match(model) else None, effort if effort and EFFORT_RE.match(effort) else None)


def found_workers(procs):
    """The `serve` workers among `procs`, each with the model and effort its agent processes show (if any run)."""
    kids = {}
    for pid, ppid, _, _ in procs:
        kids.setdefault(ppid, []).append(pid)
    argv_of = {pid: argv for pid, _, _, argv in procs}
    out = []
    for pid, _, name, argv in procs:
        if not name.lower().startswith("reason"):
            continue
        s = parse_serve(argv)
        if not s or not isinstance(pid, int):
            continue
        model = effort = None
        todo, seen = list(kids.get(pid, [])), set()
        while todo and not (model and effort):  # a warm `claude -p` or a running `codex exec` names them
            c = todo.pop()
            if c in seen:
                continue
            seen.add(c)
            m, e = model_from_args(s["family"], argv_of.get(c) or [])
            model, effort = model or m, effort or e
            todo += kids.get(c, [])
        out.append(dict(s, pid=pid, model=model, effort=effort))
    return out


def ledger_path():
    return STATE / "spawned.jsonl"


def record_spawn(name, pid, started):
    """Append (name, pid, creation time) of a worker this page started. Lines are only appended (pruned when long),
    so the proof survives a workers.json that lost the worker."""
    try:
        STATE.mkdir(parents=True, exist_ok=True)
        with open(ledger_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps({"name": name, "pid": pid, "started": started}) + "\n")
    except OSError:
        pass


def spawned_here():
    """{(pid, creation time)} of processes this page started, dropping dead ones when the ledger grows long."""
    try:
        lines = ledger_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    out, keep = set(), []
    for line in lines:
        try:
            e = json.loads(line)
            out.add((int(e["pid"]), str(e["started"])))
            keep.append(e)
        except (ValueError, KeyError, TypeError):
            continue
    if len(keep) > 500:  # prune: only live processes need the proof
        live = [e for e in keep if started_at(int(e["pid"])) == str(e["started"])]
        try:
            tmp = ledger_path().with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(e) + "\n" for e in live), encoding="utf-8")
            os.replace(tmp, ledger_path())
        except OSError:
            pass
    return out


BADGE = {"claude": "claude-code", "codex": "codex"}  # worker family -> the agent name sessions show
INNER_RE = re.compile(r"^(?P<worker>[a-z0-9][a-z0-9-]*)-(claude|codex)(-\d+)?$")


def inner_of(name, workers):
    """The worker a session belongs to when it is that worker's own agent session registering itself
    (`<worker>-claude`, `<worker>-claude-2`, … from the warm `claude -p` children), else None."""
    if name in workers:  # a worker of its own (helper-claude next to helper), not an inner session
        return None
    m = INNER_RE.match(name or "")
    return m.group("worker") if m and m.group("worker") in workers else None


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
        # name -> {name, pid, started, family, model, effort, cwd, log, fullAccess, settings}; `settings` is the
        # shim's per-worker file (absent for workers started before it existed: those restart to change)
        self.workers = {}
        self.restarting = set()  # names of workers being restarted by configure(): still taken
        self.stopped = set()  # names stopped here: a merge must not bring their old record back
        self.foreign = {}  # name -> serve worker running on this computer that this page did not start
        # name -> {name, family, cwd, model, effort, fullAccess, started}: every worker this page started, kept when
        # the process dies (a reboot), so it can be started again with the same settings
        self.records_path = STATE / "worker-records.json"
        self.records = {}
        self.load()
        self.load_records()

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
        """Read, merge, write (call with self.lock held): a live worker another writer recorded is kept, not lost."""
        try:
            disk = json.loads(self.reg.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            disk = []
        for w in disk if isinstance(disk, list) else []:
            if isinstance(w, dict) and isinstance(w.get("pid"), int) and w.get("started") \
                    and NAME_RE.match(str(w.get("name", ""))) and w["name"] not in self.workers \
                    and w["name"] not in self.stopped and w["name"] not in self.restarting and self.alive(w):
                self.workers[w["name"]] = w
        try:
            STATE.mkdir(parents=True, exist_ok=True)
            tmp = self.reg.with_suffix(".tmp")
            tmp.write_text(json.dumps(list(self.workers.values()), ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.reg)
        except OSError:
            pass

    def halt_external(self, w):
        """Stop a worker this page did not start. It may share a console or process group with other programs (the
        user's shell), so no console-wide Ctrl+C and no group kill: SIGINT to the process itself on POSIX; on Windows,
        where Ctrl+C can only go to a whole console, a forced kill of its tree (the network may then show it idle)."""
        if not WIN:
            try:
                os.kill(w["pid"], signal.SIGINT)
            except OSError:
                return
            for _ in range(100):
                if not self.alive(w):
                    return
                time.sleep(0.1)
            try:
                os.kill(w["pid"], signal.SIGKILL)
            except OSError:
                pass
            return
        subprocess.run(["taskkill", "/PID", str(w["pid"]), "/T", "/F"], capture_output=True, creationflags=NOWIN)

    # ---------- records of workers this page started, kept across reboots ----------
    def load_records(self):
        try:
            data = json.loads(self.records_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.records = {k: v for k, v in data.items() if isinstance(v, dict) and NAME_RE.match(k)
                        and v.get("family") in BADGE} if isinstance(data, dict) else {}
        # Seed from the running registry: workers started before records existed, and their start proof.
        ours = spawned_here()
        with self.lock:
            for w in self.workers.values():
                if w["name"] not in self.records and not w.get("external"):
                    self.remember(w, save=False)
                if (w["pid"], w["started"]) not in ours and not w.get("external"):
                    record_spawn(w["name"], w["pid"], w["started"])
            self.save_records()

    def remember(self, w, save=True):
        """Keep a worker's settings for a later restart (call with self.lock held)."""
        self.records[w["name"]] = {"name": w["name"], "family": w["family"], "cwd": w.get("cwd"),
                                   "model": w.get("model"), "effort": w.get("effort"),
                                   "fullAccess": bool(w.get("fullAccess")), "started": int(time.time() * 1000)}
        if save:
            self.save_records()

    def save_records(self):
        try:
            disk = json.loads(self.records_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            disk = {}
        merged = {k: v for k, v in disk.items() if isinstance(v, dict)} if isinstance(disk, dict) else {}
        merged.update(self.records)  # ours win; another writer's records are kept
        self.records = merged
        try:
            STATE.mkdir(parents=True, exist_ok=True)
            tmp = self.records_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.records_path)
        except OSError:
            pass

    def list_records(self):
        with self.lock:
            return [dict(r) for r in self.records.values()]

    def restart(self, names, online):
        """Start recorded workers again with their last settings. `online`: names live on the network now.
        Returns one result per name; nothing already running is touched."""
        if not isinstance(names, list) or not names or len(names) > 50 or not all(isinstance(n, str) for n in names):
            raise LaunchError("names must be a list of worker names.")
        results = []
        for name in dict.fromkeys(names):
            try:
                with self.lock:
                    rec = self.records.get(name)
                    if not rec:
                        raise LaunchError("No record of this worker.", 404)
                    w = self.workers.get(name)
                    if (w and self.alive(w)) or name in online or name in self.restarting:
                        raise LaunchError("It is running already.", 409)
                    fam = self.catalog.family(rec["family"])
                    if not fam:
                        raise LaunchError("Unknown agent.")
                    m = fam["modes"]["worker"]
                    if not m["ok"]:
                        raise LaunchError(m["why"] or "Not available.")
                    entry, model, effort = self.check_model(fam, m, rec.get("model") or "", rec.get("effort") or "")
                    if not rec.get("cwd") or not Path(rec["cwd"]).is_dir():
                        raise LaunchError("Its folder no longer exists.")
                    if len({n for n, x in self.workers.items() if self.alive(x)} | self.restarting) >= MAX_WORKERS:
                        raise LaunchError(f"Already {MAX_WORKERS} workers started here; stop one first.", 429)
                    nw = self.start_worker(fam, rec["cwd"], model, effort, name, bool(rec.get("fullAccess")))
                    self.workers[name] = nw
                    self.stopped.discard(name)
                    self.save()
                    self.remember(nw)
                self.settle(nw)
                results.append({"name": name, "ok": True})
            except LaunchError as e:
                results.append({"name": name, "ok": False, "error": str(e), "code": e.code})
        # The request itself succeeded; each name's outcome is in results (the page shows the failures).
        return {"ok": True, "started": sum(r["ok"] for r in results), "results": results}

    def discover(self, procs=None):
        """Take back `serve` workers this page started (recorded in spawned.jsonl) that workers.json lost; note the others.

        Model and effort come from the agent processes under the worker when one is running, else they are unknown;
        such a worker has no settings file, so changing it restarts it.
        """
        found = found_workers(list_processes() if procs is None else procs)
        ours = spawned_here()
        with self.lock:
            known = {w["pid"] for w in self.workers.values()}
            foreign = {}
            for f in found:
                if f["pid"] in known or f["name"] in self.restarting:
                    continue
                started = started_at(f["pid"])
                if not started:
                    continue
                log = STATE / "logs" / f"{f['name']}.log"
                w = {"name": f["name"], "pid": f["pid"], "started": started, "family": f["family"],
                     "model": f["model"], "effort": f["effort"], "cwd": f["cwd"], "log": str(log),
                     "fullAccess": f["fullAccess"], "settings": None, "adopted": True}
                # This page's own only on proof that it started this very process (pid + creation time): a log
                # file outlives its worker, and an outside worker may reuse the name.
                if (f["pid"], started) in ours and f["name"] not in self.workers:
                    self.workers[f["name"]] = w
                    self.stopped.discard(f["name"])
                    self.save()
                    if f["name"] not in self.records or f["model"]:  # do not overwrite known settings with unknowns
                        self.remember(w)
                elif f["name"] not in self.workers:
                    foreign[f["name"]] = w
            self.foreign = foreign

    def adopt(self, name):
        """Manage a worker started outside this page (the user asked to, in the page)."""
        with self.lock:
            w = self.foreign.get(name)
            if not w or not self.alive(w):
                raise LaunchError("No such worker running outside this page.", 404)
            if name in self.workers:
                raise LaunchError("A worker with that name is managed here already.", 409)
            self.workers[name] = dict(w, external=True)
            self.foreign.pop(name, None)
            self.stopped.discard(name)
            self.save()
            self.remember(w)
        return {"ok": True}

    def list_foreign(self):
        with self.lock:
            return [{k: w.get(k) for k in ("name", "family", "model", "effort", "cwd", "fullAccess")}
                    for w in self.foreign.values() if self.alive(w)]

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
            return [dict({k: w.get(k) for k in ("name", "family", "model", "effort", "cwd")},
                         fullAccess=bool(w.get("fullAccess")), liveSettings=self.live_settings(w),
                         adopted=bool(w.get("adopted")))
                    for w in self.workers.values()]

    @staticmethod
    def live_settings(w):
        """A Codex worker started with a settings file takes a new model or effort with its next message."""
        return w.get("family") == "codex" and bool(w.get("settings"))

    def stop(self, name):
        with self.lock:
            if name in self.restarting:
                raise LaunchError("It is restarting; try again in a moment.", 409)
            w = self.workers.pop(name, None)
            if not w:
                raise LaunchError("Not a worker started here.", 404)
            self.stopped.add(name)
            self.save()
        self.halt(w)

    def halt(self, w):
        """Stop a worker's process: Ctrl+C so the network shows it stopped, a kill after 10 s."""
        if not self.alive(w):
            return
        if w.get("external"):
            return self.halt_external(w)
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
        full = req.get("fullAccess", False)
        if not isinstance(full, bool):
            raise LaunchError("fullAccess must be true or false.")
        fam = self.catalog.family(fid)
        if not fam:
            raise LaunchError("Unknown agent.")
        m = fam["modes"].get(mode)
        if not m:
            raise LaunchError("mode must be worker or window.")
        if not m["ok"]:
            raise LaunchError(m["why"] or "Not available.")
        if full and not m.get("fullAccess"):
            raise LaunchError("This agent cannot run with full access here.")
        entry, model, effort = self.check_model(fam, m, model, effort)
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
            if name in live_names or name in self.workers or name in self.restarting:
                raise LaunchError("A session with that name is already on the network.", 409)
        return fam, mode, str(path.resolve()), entry, model, effort, name, full

    @staticmethod
    def check_model(fam, m, model, effort):
        """Validate a model and effort against one agent's catalog for one mode; returns (entry, model, effort)."""
        fid = fam["id"]
        if (model or effort) and not m["models"]:
            raise LaunchError(m["modelsWhy"] or "This agent cannot pick a model here.")
        entry = None
        if model:
            entry = next((x for x in fam["models"] if x["id"] == model), None)
            if not entry:
                raise LaunchError("That model is not in the agent's catalog.")
        if effort:
            if fid == "antigravity" and not entry:
                raise LaunchError("Pick a model to pick an effort.")
            if effort not in efforts_for(fam, entry):
                raise LaunchError("That effort is not offered for this model.")
        if fid == "antigravity":  # agy model ids carry the effort: gemini-4-argon-high
            if entry and entry["efforts"] and not effort:
                effort = entry.get("defaultEffort") or entry["efforts"][0]
            if entry and (f"{model}-{effort}" if effort else model) not in entry["ids"]:
                raise LaunchError("That model is not in the agent's catalog.")
        return entry, model, effort

    def launch(self, req, live_names):
        with self.lock:
            fam, mode, cwd, entry, model, effort, name, full = self.check(req, live_names)
            if mode == "window":
                return self.open_window(fam, cwd, model, effort, full)
            if len({n for n, w in self.workers.items() if self.alive(w)} | self.restarting) >= MAX_WORKERS:
                raise LaunchError(f"Already {MAX_WORKERS} workers started here; stop one first.", 429)
            w = self.start_worker(fam, cwd, model, effort, name, full)
            self.workers[name] = w
            self.save()
            self.remember(w)
        self.settle(w)
        return {"ok": True, "mode": "worker", "name": name}

    def settle(self, w):
        """A bad setup fails within a few seconds: then drop it and say why."""
        for _ in range(30):
            if not self.alive(w):
                with self.lock:
                    if self.workers.get(w["name"]) is w:
                        del self.workers[w["name"]]
                        self.save()
                tail = Path(w["log"]).read_bytes()[-600:].decode("utf-8", "replace").strip()
                raise LaunchError(f"The worker exited: {tail}", 502)
            time.sleep(0.1)

    def configure(self, req, busy):
        """Change a running worker's model, effort or permission. `busy`: the worker is in a turn right now.

        A Codex worker with a settings file takes a new model or effort with its next message, without a restart.
        Anything else (permission, any Claude change, a worker from before settings files) restarts the worker
        under the same name: Ctrl+C, then `serve` again. A busy worker is restarted only with `force`.
        """
        name, model, effort = req.get("name"), req.get("model") or "", req.get("effort") or ""
        full, force = req.get("fullAccess", False), req.get("force", False)
        if not all(isinstance(v, str) for v in (name, model, effort)):
            raise LaunchError("name, model and effort must be strings.")
        if not isinstance(full, bool) or not isinstance(force, bool):
            raise LaunchError("fullAccess and force must be true or false.")
        with self.lock:
            if name in self.restarting:
                raise LaunchError("It is restarting; try again in a moment.", 409)
            w = self.workers.get(name)
            if not w or not self.alive(w):
                raise LaunchError("Not a worker started here.", 404)
            fam = self.catalog.family(w["family"])
            if not fam:
                raise LaunchError("Unknown agent.")
            m = fam["modes"]["worker"]
            if full and not m.get("fullAccess"):
                raise LaunchError("This agent cannot run with full access here.")
            entry, model, effort = self.check_model(fam, m, model, effort)
            if not w.get("cwd") or not Path(w["cwd"]).is_dir():
                raise LaunchError("Its folder is unknown, so it cannot be restarted from here. Restart it yourself.", 409)
            same_perm = bool(w.get("fullAccess")) == full
            if same_perm and (w.get("model") or "") == model and (w.get("effort") or "") == effort:
                return {"ok": True, "restarted": False, "unchanged": True}
            if same_perm and self.live_settings(w):
                try:
                    write_settings(Path(w["settings"]), model_args(w["family"], model, effort))
                except OSError as e:
                    raise LaunchError(f"Could not save the worker's settings: {e}", 500)
                w.update(model=model or None, effort=effort or None)
                self.save()
                self.remember(w)  # a later restart (after a reboot) uses these settings
                return {"ok": True, "restarted": False}
            if busy and not force:
                raise LaunchError("It is busy: restarting it now loses the turn it is in.", 409)
            # Its record stays in workers.json until the new process replaces it, so a server that stops midway
            # still knows the worker; `restarting` keeps the name taken and its place counted meanwhile.
            self.restarting.add(name)
        try:
            self.halt(w)
            time.sleep(1)  # let the network take in "stopped" before the same name comes back
            with self.lock:
                nw = self.start_worker(fam, w["cwd"], model, effort, name, full)
                self.workers[name] = nw
                self.save()
                self.remember(nw)
        finally:
            self.restarting.discard(name)
        self.settle(nw)
        return {"ok": True, "restarted": True}

    def start_worker(self, fam, cwd, model, effort, name, full=False):
        env = base_env()
        fid = fam["id"]
        real = find_claude() if fid == "claude" else find_codex()
        dirs = [str(Path(real).parent)]  # the real CLI ahead of any .cmd shim on PATH
        extra = model_args(fid, model, effort)
        settings = None
        shim = shim_dir(fid)
        if shim:  # always, so a Codex worker can change model later without a restart
            dirs.insert(0, shim)
            # The old names too: a shim from before (still held open by a running turn) reads only those.
            env.update(REASON_CHAT_SHIM_REAL=real, REASON_CHAT_SHIM_ARGS=json.dumps(extra),
                       REASON_CHAT_CODEX_REAL=real, REASON_CHAT_CODEX_ARGS=json.dumps(extra))
            if shim_current(fid):  # an older shim ignores the settings file: then changes restart the worker
                settings = STATE / "worker-settings" / f"{name}.json"
                write_settings(settings, extra)
                env["REASON_CHAT_SHIM_SETTINGS"] = str(settings)
        elif extra:
            raise LaunchError("Could not build the model shim.", 500)
        env["PATH"] = os.pathsep.join(dirs + [env.get("PATH", "")])
        logs = STATE / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        log_path = logs / f"{name}.log"
        pid = spawn(serve_args(self.reason, fid, name, cwd, full), cwd, env, NOWIN, str(log_path))
        started = started_at(pid) or ""
        record_spawn(name, pid, started)
        return {"name": name, "pid": pid, "started": started, "family": fid,
                "model": model or None, "effort": effort or None, "cwd": cwd, "log": str(log_path),
                "fullAccess": full, "settings": str(settings) if settings else None}

    def open_window(self, fam, cwd, model, effort, full=False):
        spawn(window_args(fam["id"], model, effort, full), cwd, base_env(), NEW_CONSOLE)
        return {"ok": True, "mode": "window"}


def serve_args(reason, fid, name, cwd, full):
    return [reason, "network", "serve", fid, "--name", name, "--cwd", cwd] + (["--full-access"] if full else [])


def window_args(fid, model, effort, full):
    """The command line for an agent in a terminal window."""
    if fid == "claude":
        args = [find_claude()] + (["--model", model] if model else []) + (["--effort", effort] if effort else [])
    elif fid == "codex":
        args = [find_codex()] + (["-m", model] if model else []) + \
               (["-c", f"model_reasoning_effort={effort}"] if effort else [])
    else:
        mid = f"{model}-{effort}" if model and effort else model
        args = [find_agy()] + (["--model", mid] if mid else [])
    return args + (FULL_ACCESS[fid] if full else [])
