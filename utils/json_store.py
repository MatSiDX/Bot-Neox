import json
import os
import tempfile
import threading
from copy import deepcopy


_LOCKS = {}
_LOCKS_GUARD = threading.Lock()


def _get_lock(path):
    normalized = os.path.abspath(path)
    with _LOCKS_GUARD:
        lock = _LOCKS.get(normalized)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[normalized] = lock
        return lock


def _clone_fallback(fallback):
    return deepcopy(fallback)


def _read_unlocked(path, fallback):
    if not os.path.isfile(path):
        return _clone_fallback(fallback)

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return _clone_fallback(fallback)


def read_json(path, fallback):
    lock = _get_lock(path)
    with lock:
        return _read_unlocked(path, fallback)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = _get_lock(path)
    with lock:
        fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(path),
            prefix=".tmp_json_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


def mutate_json(path, fallback, mutator):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = _get_lock(path)
    with lock:
        current = _read_unlocked(path, fallback)
        updated = mutator(current)
        if updated is None:
            updated = current

        fd, temp_path = tempfile.mkstemp(
            dir=os.path.dirname(path),
            prefix=".tmp_json_",
            suffix=".json",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                json.dump(updated, f, indent=4, ensure_ascii=False)
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        return deepcopy(updated)
