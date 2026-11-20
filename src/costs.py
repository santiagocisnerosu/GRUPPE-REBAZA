"""Append API usage records for the pipeline."""
import json
import os
from contextvars import ContextVar
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"
RUN_ID = ContextVar("receipts_run_id", default=None)


def log_call(stage, model, input_tokens=0, output_tokens=0, tts_chars=0):
    record = dict(stage=stage, model=model, input_tokens=input_tokens,
                  output_tokens=output_tokens, tts_chars=tts_chars)
    if RUN_ID.get():
        record["run_id"] = RUN_ID.get()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Parallel listener processes share the usage journal.
    with (CACHE_DIR / "costs.lock").open("a+b") as lock:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        # Closing the lock file releases the lock after the write is flushed.
        with (CACHE_DIR / "costs.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")


def write_json(path, value):
    """Publish complete JSON even if a process stops during a write."""
    from tempfile import NamedTemporaryFile

    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                            delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.close()
            temporary.replace(path)
        finally:
            stream.close()
            temporary.unlink(missing_ok=True)
