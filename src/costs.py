"""Append API usage records for the pipeline."""
import json
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "cache"


def log_call(stage, model, input_tokens=0, output_tokens=0, tts_chars=0):
    record = dict(stage=stage, model=model, input_tokens=input_tokens,
                  output_tokens=output_tokens, tts_chars=tts_chars)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
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
