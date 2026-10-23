"""Viewer preferences kept by the server in REASON_CHAT_HOME/prefs.json.

The Browser pane can lose localStorage, so settings the user expects to stick live here; the page falls back to
localStorage only when saving fails. Every key is whitelisted and validated.
"""
import json
import os
import re
import threading
from pathlib import Path

FAV_RE = re.compile(r"^(room:r-[0-9a-f]{8}|[A-Za-z0-9._-]{1,64}/[A-Za-z0-9._-]{1,128})$")
ADDR_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}/[A-Za-z0-9._-]{1,128}$")
MAX_FAVORITES = 100
MAX_AUTO_WAKE = 50
SIDE_MIN, SIDE_MAX = 180, 900
CHECKS = {
    "hideOffline": lambda v: isinstance(v, bool),
    # session addresses and room keys, pinned to the top of the list in this order
    "favorites": lambda v: isinstance(v, list) and len(v) <= MAX_FAVORITES
    and all(isinstance(x, str) and FAV_RE.match(x) for x in v) and len(set(v)) == len(v),
    # width of the session list in CSS pixels; the page also keeps it inside the window
    "sideWidth": lambda v: isinstance(v, int) and not isinstance(v, bool) and SIDE_MIN <= v <= SIDE_MAX,
    # Codex sessions woken automatically when a message arrives (wake.py checks each one at wake time)
    "autoWake": lambda v: isinstance(v, list) and len(v) <= MAX_AUTO_WAKE
    and all(isinstance(x, str) and ADDR_RE.match(x) for x in v) and len(set(v)) == len(v),
}
DEFAULTS = {"hideOffline": True, "favorites": [], "sideWidth": 260, "autoWake": []}


class PrefError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


class Prefs:
    def __init__(self, home):
        self.path = Path(home) / "prefs.json"
        self.lock = threading.Lock()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.data = {k: v for k, v in data.items() if k in CHECKS and CHECKS[k](v)} if isinstance(data, dict) else {}

    def get(self):
        with self.lock:
            return dict(DEFAULTS, **self.data)

    def set(self, key, value):
        if key not in CHECKS:
            raise PrefError("Unknown setting.")
        if not CHECKS[key](value):
            raise PrefError(f"Bad value for {key}.")
        with self.lock:
            data = dict(self.data, **{key: value})
            try:  # write first, then adopt: a failed write changes nothing
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
                os.replace(tmp, self.path)
            except OSError as e:
                raise PrefError(f"Could not save settings: {e}", 500)
            self.data = data
            return dict(DEFAULTS, **data)
