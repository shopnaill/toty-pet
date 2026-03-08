"""
Atomic JSON persistence — write to temp then os.replace to avoid corruption.
"""
import json
import os
import tempfile


def safe_json_save(data, path: str, **kwargs):
    """Write *data* as JSON to *path* atomically (temp + rename)."""
    kwargs.setdefault("indent", 2)
    kwargs.setdefault("ensure_ascii", False)
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, **kwargs)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
