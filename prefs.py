"""Viewer preferences kept by the server in REASON_CHAT_HOME/prefs.json.

The Browser pane can lose localStorage, so settings the user expects to stick live here; the page falls back to
localStorage only when saving fails. Every key is whitelisted and validated.
"""
import json
import os
import threading
from pathlib import Path

CHECKS = {
    "hideOffline": lambda v: isinstance(v, bool),
}
DEFAULTS = {"hideOffline": True}


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
