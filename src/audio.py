"""Synthesize complete briefings and publish sentence-aligned transcripts."""
import argparse
import base64
import hashlib
import json
import os
import re
from collections import defaultdict
from decimal import Decimal

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
PERCENT_RANGE = re.compile(rf"({NUMBER})\s*[-\u2013\u2014]\s*({NUMBER})\s*%")
YEN = re.compile(rf"(?:\u00a5|JPY\s*)\s*({NUMBER}(?:\s+(?:thousand|million|billion|trillion))?)", re.I)


def spoken_text(text):
    def percent_range(match):
        a, b = (format(Decimal(value.replace(",", "")).normalize(), "f") for value in match.groups())
        return f"{a} to {b} percent"

    text = PERCENT_RANGE.sub(percent_range, text)
    text = YEN.sub(r"\1 yen", text)
    text = re.sub(r"(?<=\d)\s*bps?\b", " basis points", text, flags=re.I)
    text = re.sub(r"(?<=\d)\s*%", " percent", text)
    return " ".join(text.split())


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
    (out / "briefing.mp3").write_bytes(base64.b64decode(response["audio_base64"], validate=True))
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
