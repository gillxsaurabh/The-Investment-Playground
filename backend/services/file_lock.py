"""Atomic JSON file operations with advisory locking.

Prevents data corruption from concurrent reads/writes to state files
when running under Gunicorn with threads.
"""

import fcntl
import json
import os
from pathlib import Path
from typing import Any


def locked_json_read(path: str | Path, default: Any = None) -> Any:
    """Read a JSON file with an advisory shared lock.

    Returns *default* if the file does not exist or cannot be parsed.
    """
    path = Path(path)
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path, "r") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


def atomic_json_write(path: str | Path, data: Any, **json_kwargs) -> None:
    """Write JSON atomically: write to .tmp, fsync, then rename.

    The rename (os.replace) is atomic on POSIX, so readers never see
    a partially-written file.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, **json_kwargs)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(path))
