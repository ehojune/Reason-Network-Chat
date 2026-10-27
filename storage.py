"""Small standard-library primitives for registries shared by local server processes."""
import contextlib
import json
import os
import tempfile
import time
from pathlib import Path


@contextlib.contextmanager
def file_lock(path, timeout=10):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            handle.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Timed out locking " + path.name)
                time.sleep(0.02)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _sync_directory_tree(path):
    """Persist the rename and any newly created ancestor directories on POSIX."""
    directory = path.resolve().parent
    while True:
        fd = os.open(str(directory), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        if directory == directory.parent:
            break
        directory = directory.parent


def _replace_write_through(source, target):
    """Windows replacement with metadata write-through before model side effects."""
    import ctypes
    from ctypes import wintypes
    move = ctypes.WinDLL("kernel32", use_last_error=True).MoveFileExW
    move.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    move.restype = wintypes.BOOL
    if not move(str(source.resolve()), str(target.resolve()), 0x1 | 0x8):
        raise ctypes.WinError(ctypes.get_last_error())


def atomic_json(path, value, durable=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as handle:
            temp = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=1)
            handle.flush()
            os.fsync(handle.fileno())
        if durable and os.name == "nt":
            _replace_write_through(temp, path)
        else:
            os.replace(temp, path)
            if durable:
                _sync_directory_tree(path)
    finally:
        if temp is not None:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass
