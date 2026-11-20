"""Synthesize complete briefings and publish sentence-aligned transcripts."""
import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import yaml
from dotenv import load_dotenv
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

from .costs import CACHE_DIR, log_call, write_json
from .script import LISTENERS, ROOT, numeric_mentions, spoken_citations
from .script_reports import append_receipt_closing

OUTPUT_FORMAT = "mp3_44100_128"
NUMBER = r"\d[\d,]*(?:\.\d+)?"
SPOKEN_SUBSTITUTIONS = re.compile(
    rf"(?P<low>{NUMBER})\s*(?P<dash>[-–—])\s*(?P<high>{NUMBER})\s*%|"
    rf"(?P<yen>¥|JPY)\s*(?P<amount>{NUMBER}(?:\s+(?:thousand|million|billion|trillion))?)|"
    r"(?<=\d)\s*(?:(?P<bps>bps?\b)|(?P<percent>%))", re.I
)


def speech_parts(text):
    """Yield (spoken fragment, original character offset) before collapsing whitespace."""
    cursor = 0
    for m in SPOKEN_SUBSTITUTIONS.finditer(text):
        for i in range(cursor, m.start()):
            yield text[i], i
        if m["low"]:
            low, high = (Decimal(m[key].replace(",", "")).normalize() for key in ("low", "high"))
            yield format(low, "f"), m.start("low")
            yield " to ", m.start("dash")
            yield format(high, "f"), m.start("high")
            yield " percent", m.end() - 1
        elif m["yen"]:
            for i in range(m.start("amount"), m.end()):
                yield text[i], i
            # An attached currency sign belongs to the amount as a whole.
            prefix_separate = m.end("yen") < m.start("amount")
            yield " yen", m.start() if prefix_separate else m.end() - 1
        else:
            yield (" basis points" if m["bps"] else " percent"), m.end() - 1
        cursor = m.end()
    for i in range(cursor, len(text)):
        yield text[i], i


def spoken_text(text):
    return " ".join("".join(part for part, _ in speech_parts(text)).split())


def aligned_words(original, offset, timing):
    # Both strings can have different lengths (e.g. "3.6%" / "3.6 percent").
    # Consume the exact submitted non-space characters, retaining their printed token.
    words = list(re.finditer(r"\S+", original))
    owner = {i: k for k, w in enumerate(words) for i in range(w.start(), w.end())}
    intervals = [[] for _ in words]
    positions = (offset + i for i, char in enumerate(spoken_text(original)) if not char.isspace())
    for part, index in speech_parts(original):
        for char in part:
            if not char.isspace():
                intervals[owner[index]].append(timing[next(positions)])
    return [{"w": w[0], "start": min(t[0] for t in times), "end": max(t[1] for t in times)}
            for w, times in zip(words, intervals, strict=True)]


def story_paragraphs(sentences):
    # Preserve first appearance of each story. Subsequent sentences from
    # that story stay together in the same paragraph.
    stories = defaultdict(list)
    for sentence in sentences:
        key = "editor_closer" if sentence.get("editor_closer") else sentence.get("story_id")
        stories[key].append(sentence)

    parts, spans = [], []
    offset = 0
    for index, lines in enumerate(stories.values()):
        if index:
            parts.append("\n")
            offset += 1
        for index_in_story, sentence in enumerate(lines):
            if index_in_story:
                parts.append(" ")
                offset += 1
            spoken = spoken_text(sentence["text"])
            parts.append(spoken)
            spans.append((sentence, offset, offset + len(spoken)))
            offset += len(spoken)
    return "".join(parts), spans


def times_by_character(text, alignment):
    characters = "".join(alignment["characters"])
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    if len(characters) != len(starts) or len(starts) != len(ends):
        raise ValueError("ElevenLabs returned incomplete character alignment")
    positions = [i for i, char in enumerate(characters) if not char.isspace()]
    expected = [i for i, char in enumerate(text) if not char.isspace()]
    if "".join(text[i] for i in expected) != "".join(characters[i] for i in positions):
        raise ValueError("ElevenLabs alignment does not match the submitted narration")
    return {i: (starts[j], ends[j]) for i, j in zip(expected, positions, strict=True)}


def synthesize(text, profile, model, client):
    voice = profile["voice_id"]
    settings = VoiceSettings(**profile["voice_settings"])
    config = [text, voice, settings.model_dump(exclude_none=True), model, OUTPUT_FORMAT]
    key = hashlib.sha256(json.dumps(config, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / "tts" / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), True
    try:
        response = client.text_to_speech.convert_with_timestamps(
            voice, text=text, model_id=model, voice_settings=settings,
            output_format=OUTPUT_FORMAT,
        )
    except ApiError as exc:
        raise RuntimeError(f"ElevenLabs synthesis failed (HTTP {exc.status_code})") from None
    log_call("tts", model, tts_chars=len(text))
    if response.alignment is None:
        raise ValueError("ElevenLabs returned audio without original-text alignment")
    result = {"audio_base64": response.audio_base_64, "alignment": response.alignment.model_dump()}
    times_by_character(text, result["alignment"])
    write_json(path, result)
    return result, False


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def verified_receipt(script, sources):
    receipt = []
    for raw, matches, _ in spoken_citations(script):
        fact = matches[0]
        source = sources[fact["article_id"]]
        receipt.append({
            "figure": raw, "measures": fact["measures"], "outlet": source["outlet"],
            "headline": source["headline"], "link": source["link"],
        })
    return receipt


def normalize_audio(raw, destination):
    """Master from the cached original, then check the decoded delivery MP3."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        from imageio_ffmpeg import get_ffmpeg_exe
        ffmpeg = get_ffmpeg_exe()

    def run(path, *args):
        return subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-nostats", "-y",
                               "-i", str(path), *args], capture_output=True, check=True)

    def measure(path):
        result = run(path, "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-")
        report = re.search(rb'\{\s*"input_i".*?\}', result.stderr, re.S)
        return json.loads(report[0])

    def sample_count(path):
        # Count decoded samples, excluding the MP3 encoder's gapless delay and padding.
        return len(run(path, "-ac", "1", "-ar", "44100", "-f", "s16le", "-").stdout) // 2

    with TemporaryDirectory(dir=destination.parent) as scratch:
        original, encoded = (Path(scratch) / name for name in ("source.mp3", "master.mp3"))
        original.write_bytes(raw)
        samples = sample_count(original)
        before = measure(original)
        measured = ":".join(f"measured_{k}={before['input_' + k]}" for k in ("i", "tp", "lra", "thresh"))
        peak_target, trim_gain = -1.5, 0.0
        for _ in range(6):
            ceiling = 10 ** (peak_target / 20)
            filters = (f"loudnorm=I=-16:TP=-1.5:LRA=11:{measured}:offset={before['target_offset']},"
                       f"aresample=192000,volume={trim_gain:.2f}dB,"
                       f"alimiter=limit={ceiling:.7f}:level=0:latency=1,"
                       f"aresample=44100,atrim=end_sample={samples}")
            run(original, "-af", filters, "-c:a", "libmp3lame", "-b:a", "128k", str(encoded))
            after = measure(encoded)
            loudness, peak = float(after["input_i"]), float(after["input_tp"])
            if abs(loudness + 16) <= 0.10 and peak <= -1.5:
                break
            # Lossy encoding can introduce new intersample peaks. Re-render from the original.
            correction = -16 - loudness
            peak_target -= max(0, peak + correction + 1.5 + 0.15)
            trim_gain += correction
        else:
            raise ValueError(f"MP3 missed mastering targets: {loudness} LUFS, {peak} dBTP")
        if sample_count(encoded) != samples:
            raise ValueError("Mastering changed the decoded duration")
        encoded.replace(destination)
    print(f"{destination.parent.name}: {before['input_i']} -> {loudness:.2f} LUFS | "
          f"{before['input_tp']} -> {peak:.2f} dBTP | {samples / 44100:.3f}s before and after")


def build_audio(profile, model, client, sources):
    listener = profile["id"]
    out = ROOT / "out" / listener
    script = load_json(out / "script.json")
    if not script:
        raise SystemExit(f"No script for {listener}. Run src.script first.")
    narration = [sentence for sentence in script["sentences"] if not sentence.get("receipt_closing")]
    total = sum(len(list(numeric_mentions(sentence["text"]))) for sentence in narration)
    receipt = verified_receipt(script, sources)
    if total != len(receipt):
        raise ValueError(f"{listener} has {total - len(receipt)} unmatched spoken figures")
    sources_total = append_receipt_closing(script, total)
    script["number_mentions"] = total
    write_json(out / "script.json", script)
    text, spans = story_paragraphs(script["sentences"])
    response, cached = synthesize(text, profile, model, client)
    timing = times_by_character(text, response["alignment"])
    titles = {story["story_id"]: story["title"] for story in script["selected_stories"]}
    sentences = []
    for sentence, start, end in spans:
        story_id = sentence.get("story_id")
        sentences.append({
            "text": sentence["text"], "start": timing[start][0], "end": timing[end - 1][1],
            "words": aligned_words(sentence["text"], start, timing),
            "story": "Your receipt" if sentence.get("receipt_closing") else titles.get(story_id, "Briefing"),
            "sources": [sources[i] for i in dict.fromkeys(sentence["article_ids"])],
        })
    caught = [{"figure": entry["cifra"], "reason": entry["motivo"], "kind": entry["kind"],
               "sentence": entry.get("frase_evaluada", entry["frase_original"])}
              for entry in load_json(out / "caught.json")]
    conflicts = [
        {**{key: entry[key] for key in ("measure", "value_a", "outlet_a", "link_a", "value_b", "outlet_b", "link_b")},
         "used": entry.get("scripts", {}).get(listener, {}).get("used")}
        for entry in load_json(CACHE_DIR / "conflicts.json")
    ]
    normalize_audio(base64.b64decode(response["audio_base64"], validate=True), out / "briefing.mp3")
    write_json(out / "transcript.json", {
        "listener": listener, "name": profile["name"], "date": script["date"], "audio": "briefing.mp3",
        "figures_total": total, "figures_verified": len(receipt), "sources_total": sources_total,
        "sentences": sentences, "caught": caught, "conflicts": conflicts, "receipt": receipt,
    })
    print(f"{listener}: {sentences[-1]['end']:.2f}s aligned | {len(sentences)} lines | "
          f"{total} figures | {sources_total} sources | {'cache' if cached else 'ElevenLabs'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listener", choices=(*LISTENERS, "all"), required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=True)
    model = os.getenv("ELEVENLABS_MODEL")
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not model or not api_key:
        raise SystemExit("ELEVENLABS_MODEL and ELEVENLABS_API_KEY are required")
    profiles = {p["id"]: p for p in yaml.safe_load((ROOT / "profiles.yaml").read_text(encoding="utf-8"))["profiles"]}
    articles = pd.read_parquet(CACHE_DIR / "articles.parquet", columns=["id", "outlet", "headline", "link"])
    sources = {a.id: {"article_id": a.id, "outlet": a.outlet, "headline": a.headline, "link": a.link}
               for a in articles.itertuples(index=False)}
    client = ElevenLabs(api_key=api_key)
    for listener in LISTENERS if args.listener == "all" else (args.listener,):
        build_audio(profiles[listener], model, client, sources)


if __name__ == "__main__":
    main()
