"""Prepend an aligned voice credit to each existing master, without resynthesizing news."""
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import yaml
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from imageio_ffmpeg import get_ffmpeg_exe
from scipy.signal import correlate

from .audio import aligned_words, normalize_audio, synthesize, times_by_character
from .costs import CACHE_DIR, write_json
from .script import ROOT

NOTICE = "This briefing is read by an AI voice."
RATE = 44100


def decode(path, rate=RATE):
    return subprocess.check_output([get_ffmpeg_exe(), "-v", "error", "-i", str(path),
                                    "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"])


def wave_bytes(pcm):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return stream.getvalue()


def check_sync(reference, delivered, sentences):
    if len(reference) != len(delivered):
        raise ValueError("Decoded sample count changed")
    a, b = (np.frombuffer(pcm, dtype="<i2")[::4].astype(float) for pcm in (reference, delivered))
    rate = RATE / 4
    margin = int(rate / 5)
    worst = 0
    for line in sentences:
        words = line["words"]
        if [w["w"] for w in words] != line["text"].split() or not all(
            line["start"] <= w["start"] <= w["end"] <= line["end"] for w in words
        ):
            raise ValueError("Word alignment does not match the line")
        center = int(rate * (line["start"] + line["end"]) / 2)
        start = max(margin, min(center - margin, len(a) - 3 * margin))
        target = a[start:start + 2 * margin]
        search = b[start - margin:start + 3 * margin]
        energies = np.r_[0, np.cumsum(search ** 2)]
        power = energies[len(target):] - energies[:-len(target)]
        scores = correlate(search, target, mode="valid", method="fft") / np.sqrt(
            np.maximum(power, 1) * max(np.sum(target ** 2), 1))
        lag = abs(int(scores.argmax()) - margin) / rate
        if lag >= .004 or scores.max() < .85:
            raise ValueError(f"Speech sync failed at {center / rate:.3f}s ({lag*1000:.2f} ms)")
        worst = max(worst, lag)
    return worst


def prepend(profile, model, client):
    folder = ROOT / "out" / profile["id"]
    transcript_path, audio_path = folder / "transcript.json", folder / "briefing.mp3"
    transcript = json.loads(transcript_path.read_bytes())
    cache = CACHE_DIR / "disclosures" / profile["id"]
    journal = cache / "pending.json"
    if journal.exists():
        # Restore the pair if a prior process stopped between its two replaces.
        original = cache / json.loads(journal.read_bytes())["original"]
        for path in (audio_path, transcript_path):
            shutil.copyfile(original / path.name, path)
        journal.unlink()
        transcript = json.loads(transcript_path.read_bytes())
    if "voice_disclosure" in transcript:
        return
    take, _ = synthesize(NOTICE, profile, model, client)
    timing = times_by_character(NOTICE, take["alignment"])
    with TemporaryDirectory(dir=folder) as tmp:
        scratch = Path(tmp)
        clip, combined = scratch / "clip.mp3", scratch / "briefing.mp3"
        clip.write_bytes(base64.b64decode(take["audio_base64"], validate=True))
        measurement = subprocess.run([get_ffmpeg_exe(), "-hide_banner", "-i", str(clip),
            "-af", "loudnorm=print_format=json", "-f", "null", "-"], capture_output=True, check=True)
        level = json.loads(re.search(rb'\{\s*"input_i".*?\}', measurement.stderr, re.S)[0])
        gain = min(-16 - float(level["input_i"]), -1.5 - float(level["input_tp"]))
        prefix = (np.frombuffer(decode(clip), dtype="<i2") * (10 ** (gain / 20))).round().clip(
            -32768, 32767).astype("<i2").tobytes()
        shift = len(prefix) / (2 * RATE)
        reference = prefix + decode(audio_path)
        normalize_audio(wave_bytes(reference), combined)
        notice = {"text": NOTICE, "start": timing[0][0], "end": timing[len(NOTICE)-1][1],
                  "duration": shift, "words": aligned_words(NOTICE, 0, timing)}
        for line in transcript["sentences"]:
            for span in [line, *line["words"]]:
                for key in ("start", "end"):
                    span[key] += shift
        try:
            drift = check_sync(reference, decode(combined), [notice, *transcript["sentences"]])
        except ValueError as exc:
            print(f"{profile['id']}: {exc}. Keeping original delivery and visible disclosure.")
            return
        transcript["voice_disclosure"] = notice
        write_json(scratch / "transcript.json", transcript)
        digest = hashlib.sha256(audio_path.read_bytes()).hexdigest()
        original = cache / digest
        original.mkdir(parents=True, exist_ok=True)
        for path in (audio_path, transcript_path):
            shutil.copyfile(path, original / path.name)
        write_json(journal, {"original": digest})
        combined.replace(audio_path)
        (scratch / "transcript.json").replace(transcript_path)
        journal.unlink()
        print(f"{profile['id']}: pre-roll {shift:.6f}s; maximum measured drift {drift*1000:.2f} ms")


def main():
    load_dotenv(ROOT / ".env", override=True)
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    for profile in yaml.safe_load((ROOT / "profiles.yaml").read_text(encoding="utf-8"))["profiles"]:
        prepend(profile, os.environ["ELEVENLABS_MODEL"], client)


if __name__ == "__main__":
    main()
