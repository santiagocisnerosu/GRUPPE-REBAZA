"""Build the allowlisted GitHub Pages demo from verified local outputs."""
import json
import shutil

import pandas as pd
import qrcode

from .costs import CACHE_DIR, write_json
from .script import LISTENERS, ROOT, WORD, normalize_text, word_windows

PAGES_URL = "https://santiagocisnerosu.github.io/GRUPPE-REBAZA/"
PUBLIC_FILES = {"briefing.mp3", "transcript.json"}


def redact_sentence(text, overlaps):
    original = text
    text = normalize_text(text)
    tokens = list(WORD.finditer(text))
    words = [match.group().casefold() for match in tokens]
    spans = []
    for index in range(len(words) - 7):
        if tuple(words[index:index + 8]) in overlaps:
            start, end = tokens[index].start(), tokens[index + 7].end()
            if spans and start <= spans[-1][1]:
                spans[-1] = (spans[-1][0], end)
            else:
                spans.append((start, end))
    for start, end in reversed(spans):
        text = text[:start] + "[licensed wording removed]" + text[end:]
    return (text, True) if spans else (original, False)


def build():
    docs = ROOT / "docs"
    output = ROOT / "out"
    shared = json.loads((output / "shared_facts.json").read_text(encoding="utf-8"))
    costs = output / "costs.json"
    expected = {"index.html", "qr.png", "out/shared_facts.json"}
    if costs.is_file():
        expected.add("out/costs.json")
    elif (docs / "out/costs.json").is_file():
        (docs / "out/costs.json").unlink()
    expected.update(f"out/{listener}/{name}" for listener in LISTENERS for name in PUBLIC_FILES)
    unexpected = {p.relative_to(docs).as_posix() for p in docs.rglob("*") if p.is_file()} - expected
    if unexpected:
        raise SystemExit("Unexpected files in docs/: " + ", ".join(sorted(unexpected)))

    transcripts = {}
    candidates = set()
    for listener in LISTENERS:
        folder = ROOT / "out" / listener
        if not all((folder / name).is_file() for name in PUBLIC_FILES):
            raise SystemExit(f"Missing audio or transcript for {listener}")
        data = json.loads((folder / "transcript.json").read_text(encoding="utf-8"))
        if data["audio"] != "briefing.mp3":
            raise SystemExit(f"Unexpected audio path for {listener}")
        transcripts[listener] = data
        candidates.update(word_windows(" ".join(line["text"] for line in data["sentences"])))
        for item in data["caught"]:
            candidates.update(word_windows(item["sentence"]))
        for item in (*data["receipt"], *data["conflicts"]):
            candidates.update(word_windows(item.get("measures", item.get("measure", ""))))

    for fact in shared:
        candidates.update(word_windows(fact["measure"]))
        for listener, entry in fact["listeners"].items():
            sentences = transcripts[listener]["sentences"]
            if not any(line["text"] == entry["sentence"]
                       and any(s["link"] == fact["link"] for s in line["sources"])
                       for line in sentences):
                raise SystemExit(f"Shared fact does not match {listener}'s sourced narration")

    articles = pd.read_parquet(CACHE_DIR / "articles.parquet", columns=["text"])
    overlap = set()
    for article in articles["text"].dropna():
        overlap.update(window for window in word_windows(article) if window in candidates)

    redacted = 0
    redacted_measures = 0
    for listener, data in transcripts.items():
        narration = " ".join(line["text"] for line in data["sentences"])
        if any(window in overlap for window in word_windows(narration)):
            raise SystemExit(f"Licensed wording found in {listener} narration; publication stopped")
        for item in (*data["receipt"], *data["conflicts"]):
            key = "measures" if "measures" in item else "measure"
            _, changed = redact_sentence(item[key], overlap)
            if changed:
                item[key] = "Measurement described in the linked source."
                redacted_measures += 1
        for item in data["caught"]:
            if item["kind"] == "copied":
                item["sentence"] = "Licensed wording withheld."
                redacted += 1
            else:
                item["sentence"], changed = redact_sentence(item["sentence"], overlap)
                redacted += changed

    html = (ROOT / "web" / "player.html").read_text(encoding="utf-8")
    if html.count('"../out/"') != 1:
        raise SystemExit("Could not identify the player's data path")
    docs.mkdir(exist_ok=True)
    (docs / "index.html").write_text(html.replace('"../out/"', '"./out/"'), encoding="utf-8")
    (docs / "out").mkdir(exist_ok=True)
    for fact in shared:
        _, changed = redact_sentence(fact["measure"], overlap)
        if changed:
            fact["measure"] = "Measurement described in the linked source."
            redacted_measures += 1
    write_json(docs / "out/shared_facts.json", shared)
    if costs.is_file():
        shutil.copyfile(costs, docs / "out/costs.json")
    for listener, transcript in transcripts.items():
        destination = docs / "out" / listener
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "out" / listener / "briefing.mp3", destination / "briefing.mp3")
        write_json(destination / "transcript.json", transcript)
    qrcode.make(PAGES_URL).save(docs / "qr.png")
    print(f"Pages package ready: {len(expected)} files; {redacted} caught fragments withheld or redacted")
    print(f"Replaced {redacted_measures} measure labels containing licensed wording.")
    print(f"Checked narration against {len(articles)} licensed articles. QR: {PAGES_URL}")


if __name__ == "__main__":
    build()
