"""The public player roster. Update it only after a complete delivery is ready."""
import json
import os
import re
from contextlib import contextmanager

from .costs import CACHE_DIR, write_json

CORE = [
    {"id": "mara", "name": "Mara", "role": "Rates & FX", "language": "en"},
    {"id": "jordan", "name": "Jordan", "role": "Tech investor", "language": "en"},
    {"id": "priya", "name": "Priya", "role": "UK retailer", "language": "en"},
]


@contextmanager
def roster_lock():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with (CACHE_DIR / "listeners.lock").open("a+b") as lock:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def roster(folder):
    path = folder / "listeners.json"
    entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else CORE.copy()
    if entries[:len(CORE)] != CORE or any(
        not re.fullmatch(r"wildcard-(en|nl|de)-[a-f0-9]{12}", e["id"])
        for e in entries[len(CORE):]
    ):
        raise ValueError(f"Invalid listener manifest in {folder}")
    return entries


def register(folder, entry=None):
    entries = roster(folder)
    if entry:
        existing = next((i for i, e in enumerate(entries) if e["id"] == entry["id"]), len(entries))
        entries[existing:existing + 1] = [entry]
    write_json(folder / "listeners.json", entries)
