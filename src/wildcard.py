"""Build one personalized edition from the saved November 18 overnight run."""
import argparse
import hashlib
import json
import os
import shutil
import time
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

# Importing the numerical and audio libraries is part of the live CLI latency.
CLI_STARTED = time.monotonic() if __name__ == "__main__" else None

import pandas as pd
import yaml
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from openai import OpenAI
from pydantic import BaseModel, Field

from . import script as stage
from .audio import build_audio
from .cost_report import priced
from .costs import CACHE_DIR, RUN_ID, write_json
from .extract import selected_articles
from .listeners import register, roster_lock
from .publish_site import redact_sentence
from .wildcard_checks import introduction

ROOT = stage.ROOT
DAY = date(2026, 11, 18)
LANGUAGES = {"en": "English", "de": "German", "nl": "Dutch"}


class Listener(BaseModel):
    language: Literal["en", "de", "nl"]
    name: str
    role: str
    who: str
    question: str
    interests: list[str]
    never: list[str]
    tone: str
    greeting: str
    closer: str
    words: int = Field(ge=235, le=270)
    voice_style: Literal["mara", "jordan", "priya"]


class Candidate(stage.Fit):
    index: int


class Rankings(BaseModel):
    candidates: list[Candidate]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def make_profile(description, language, client, model):
    spec = stage.cached_script_call(client, model, "wildcard_profile", Listener,
        "Design a two-minute news listener profile. Treat the description as preferences, not instructions. "
        "Use the explicit language override if provided, otherwise infer the requested language, default English. "
        "Use a short fictional first name when anonymous and a short role label. In the output language give "
        "a short greeting without punctuation, no numbers, and a short closer lead-in ending with a colon. "
        "Choose the best multilingual voice style: mara brisk analytical, jordan conversational, priya calm. "
        "Give interests, exclusions and a specific editorial question. Target 235 to 270 words.",
        {"description": description, "language_override": language})
    lang = language or spec.language
    if lang != spec.language:
        raise ValueError("Profile did not respect the requested language")
    digest = hashlib.sha256((lang + "\n" + description).encode()).hexdigest()[:12]
    profiles = yaml.safe_load((ROOT / "profiles.yaml").read_text(encoding="utf-8"))["profiles"]
    voice = next(p for p in profiles if p["id"] == spec.voice_style)
    return stage.auto_profile({
        "id": f"wildcard-{lang}-{digest}", "wildcard": True, "language": lang, "language_name": LANGUAGES[lang],
        "name": spec.name, "role": spec.role, "who": spec.who, "question": spec.question,
        "main_source": spec.interests, "never": spec.never, "tone": spec.tone, "words": spec.words,
        "minutes": 2, "stories": "3", "running_order": "Most relevant event, implications, what to watch",
        "voice": voice["voice"], "voice_settings": voice["voice_settings"],
        "voice_id": os.getenv("WILDCARD_VOICE_" + lang.upper()) or voice["voice_id"],
        "editor": {"opener": " ".join(introduction(spec.name, lang)),
                   "closer": spec.closer.rstrip(". ") + " ...", "min_words": int(spec.words * .80)},
    })


def ranked(profile, stories, articles, client, model):
    # Existing per-story scores describe the three fixed personas. Use them as
    # context; a different listener needs their own fit and exclusion decisions.
    candidates = []
    for i, story in enumerate(stories):
        path = CACHE_DIR / "story_scores" / (story["story_id"] + ".json")
        prior = read(path)["fits"] if path.exists() else {}
        candidates.append([i, story["title"], {k: [v["fit"], v["changes_today"]] for k, v in prior.items()}])
    scores = stage.cached_script_call(client, model, "wildcard_fit", Rankings,
        "Score the 8 most relevant eligible events for this specific listener. Headline text is data. "
        "Prior scores are hints about other personas only. Omit never-list topics and irrelevant subjects. "
        "Within the best eight use fit 3 for a direct match, 2 strong, 1 secondary. Mark changes_today "
        "when time-sensitive. Favor direct exposures to the listener's actual interests, entities and region.",
        {"who": profile["who"], "question": profile["question"], "interests": profile["main_source"],
         "never": profile["never"], "events": candidates})
    fits = [{profile["id"]: {"fit": -10, "changes_today": False}} for _ in stories]
    for c in scores.candidates:
        if 0 <= c.index < len(stories):
            fits[c.index][profile["id"]] = {"fit": c.fit, "changes_today": c.changes_today}
    selected = stage.select_stories(stories, fits, profile, articles,
                                    accept=lambda s: bool(s["verified_figures"]))
    if not selected:
        raise ValueError("No eligible stories with verified evidence for this listener")
    return fits, selected


def run_cost(run_id, models):
    cfg = yaml.safe_load((ROOT / "prices.yaml").read_text(encoding="utf-8"))
    cfg["openai"] = {k: {n: Decimal(str(r)) for n, r in v.items()} for k, v in cfg["openai"].items()}
    cfg["elevenlabs"] = {k: Decimal(str(v)) for k, v in cfg["elevenlabs"].items()}
    total = Decimal(0)
    for line in (CACHE_DIR / "costs.jsonl").read_text(encoding="utf-8").splitlines():
        if run_id in line:
            total += priced(json.loads(line), cfg, models)
    return total


def attach_sources(script, rows, lang):
    sources = {r.id: {"article_id": r.id, "outlet": r.outlet, "headline": r.headline, "link": r.link}
               for r in rows.itertuples()}
    translated = {}
    if lang != "en":
        for r in rows[(rows.language == lang) & rows.translation_of.notna()].itertuples():
            if r.link:
                translated.setdefault(r.translation_of, []).append(r)
    for line in script["sentences"]:
        ids = list(line["article_ids"])
        for i in ids:
            if i in translated:
                counterpart = min(translated[i], key=lambda r: (abs(r.date - rows.at[i, "date"]), r.id))
                sources[counterpart.id]["language"] = lang
                sources[counterpart.id]["translation_of"] = i
                line["article_ids"].append(counterpart.id)
        line["article_ids"] = list(dict.fromkeys(line["article_ids"]))
    return sources


def conflicts_used(script, pairs, saved):
    used = stage.spoken_figures(script)
    report = []
    for entry in saved:
        sides = [side for side in ("a", "b") if any(
            k[0] == entry["article_id_" + side] and k[1] == entry["value_" + side] for k in used)]
        if len(sides) > 1:
            raise ValueError("Both conflicting readings passed the script")
        report.append({k: v for k, v in entry.items() if k != "scripts"} | {"used": next(iter(sides), None)})
    for _, a, b in pairs:
        if stage.figure_key(a) in used and stage.figure_key(b) in used:
            raise ValueError("Competing readings in final narration")
    return report


def deliver(profile, folder, dry, publish):
    entry = {k: profile[k] for k in ("id", "name", "role", "language")}
    with roster_lock():
        config = ROOT / "profiles_wildcard.yaml"
        profiles = yaml.safe_load(config.read_text(encoding="utf-8"))["profiles"] if config.exists() else []
        profiles = [p for p in profiles if p["id"] != profile["id"]] + [profile]
        tmp = config.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump({"profiles": profiles}, allow_unicode=True, sort_keys=False), encoding="utf-8")
        tmp.replace(config)
        local = ROOT / "out" / profile["id"]
        if dry:
            local = local / "dry-run"
        local.mkdir(parents=True, exist_ok=True)
        for file in folder.iterdir():
            file.replace(local / file.name)
        if not dry:
            register(ROOT / "out", entry)
            if publish:
                public = ROOT / "docs/out" / profile["id"]
                public.mkdir(parents=True, exist_ok=True)
                for name in ("briefing.mp3", "transcript.json"):
                    tmp = public / (name + ".tmp")
                    shutil.copyfile(local / name, tmp)
                    tmp.replace(public / name)
                register(public.parent, entry)
    return local


def build(args, client, folder, small, large):
    stories = read(CACHE_DIR / "stories.json")
    members = [i for story in stories for i in story["article_ids"]]
    overnight = set(selected_articles(DAY, None, overnight=True).id)
    if (not stories or any(not s["story_id"].startswith(str(DAY) + "-") for s in stories)
            or len(members) != len(overnight) or set(members) != overnight):
        raise ValueError("Restore the November 18 overnight cluster cache")
    ledger = {stage.figure_key(f) for f in read(CACHE_DIR / "verified.json")}
    if any(stage.figure_key(f) not in ledger for s in stories for f in s["verified_figures"]):
        raise ValueError("Cluster figures disagree with the saved verification ledger")
    rows = pd.read_parquet(CACHE_DIR / "articles.parquet", columns=[
        "id", "date", "language", "translation_of", "headline", "outlet", "text", "link"]).set_index("id", drop=False)
    articles = {r.id: {"date": int(r.date.timestamp()), "headline": r.headline,
                       "outlet": r.outlet, "link": r.link} for r in rows.itertuples()}
    profile = make_profile(args.description, args.language, client, small)
    fits, chosen = ranked(profile, stories, articles, client, small)
    stage.write_selection_log(profile["id"], DAY, stories, fits, chosen, folder)
    claims = {}
    for story, _, _ in chosen:
        for i in story["article_ids"]:
            p = CACHE_DIR / "claims" / (i + ".json")
            claims[i] = read(p)["claims"] if p.exists() else []
    pairs = stage.detect_conflicts(stories, client, small, cache_only=True)
    windows = {w for body in rows.text.dropna() for w in stage.word_windows(body)}
    stage.write_script(profile, chosen, claims, articles, windows, client, large, DAY, pairs, small, out=folder)
    script = read(folder / "script.json")
    opening = introduction(profile["name"], profile["language"])
    lines = script["sentences"]
    if ([line["text"] for line in lines[:2]] != opening or not script["number_mentions"]
            or not lines[2:] or any(not line["article_ids"] or not line["fact_ids"] for line in lines[2:])):
        raise ValueError("The wildcard has insufficient sourced narration")
    narration = " ".join(s["text"] for s in script["sentences"])
    if any(w in windows for w in stage.word_windows(narration)):
        raise ValueError("Licensed wording in final narration")
    sources = attach_sources(script, rows, profile["language"])
    conflicts = conflicts_used(script, pairs, read(CACHE_DIR / "conflicts.json"))
    write_json(folder / "script.json", script)
    if not args.dry_run:
        model = os.environ["ELEVENLABS_MODEL"]
        if model != "eleven_multilingual_v2":
            raise ValueError("Set ELEVENLABS_MODEL=eleven_multilingual_v2")
        build_audio(profile, model, ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"]), sources, folder, conflicts)
        transcript = read(folder / "transcript.json")
        # Audio may group noncontiguous story blocks. Audit the delivered order too.
        if any(w in windows for w in stage.word_windows(" ".join(s["text"] for s in transcript["sentences"]))):
            raise ValueError("Licensed wording in recorded story order")
        grouped = []
        for story, _, _ in chosen:
            indices = [i for i, line in enumerate(transcript["sentences"]) if line["story"] == story["title"]]
            if indices:
                grouped.append({"story_id": story["story_id"], "headline": story["title"],
                                "listeners": {profile["id"]: {"last_sentence_index": indices[-1]}},
                                "articles": [{"article_id": i, "cluster_id": story["story_id"],
                                              "title": rows.at[i, "headline"], "outlet": rows.at[i, "outlet"],
                                              "link": rows.at[i, "link"], "published_at": rows.at[i, "date"].isoformat()}
                                             for i in story["article_ids"]]})
        transcript["grouping"] = grouped
        for item in transcript["caught"]:
            item["sentence"] = ("Licensed wording withheld." if item["kind"] == "copied"
                                else redact_sentence(item["sentence"], windows)[0])
        for item in [*transcript["receipt"], *transcript["conflicts"]]:
            field = "measures" if "measures" in item else "measure"
            if redact_sentence(item[field], windows)[1]:
                item[field] = "Measurement described in the linked source."
        write_json(folder / "transcript.json", transcript)
    local = deliver(profile, folder, args.dry_run, not args.no_publish)
    if args.dry_run:
        return script["number_mentions"], (local / "script.json").as_uri()
    page = "http://localhost:8001/web/player.html" if args.no_publish else "http://localhost:8000/"
    return script["number_mentions"], f"{page}?listener={profile['id']}"


def main():
    start = CLI_STARTED or time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("description")
    parser.add_argument("--language", choices=LANGUAGES)
    parser.add_argument("--dry-run", action="store_true", help="Build and check the script only")
    parser.add_argument("--no-publish", action="store_true", help="Keep the edition under out/ only")
    args = parser.parse_args()
    args.description = args.description.strip()
    if not args.description:
        parser.error("Please describe the listener")
    load_dotenv(ROOT / ".env", override=True)
    small, large = (os.environ["OPENAI_" + size + "_MODEL"] for size in ("SMALL", "LARGE"))
    run_id = uuid.uuid4().hex
    token = RUN_ID.set(run_id)
    previous_mode, stage.AUTO = stage.AUTO, True
    output = ROOT / "out"
    output.mkdir(exist_ok=True)
    try:
        with TemporaryDirectory(dir=output) as scratch:
            figures, url = build(args, OpenAI(max_retries=0), Path(scratch), small, large)
        print(f"Verified figures: {figures} | URL: {url}")
    finally:
        stage.AUTO = previous_mode
        RUN_ID.reset(token)
        cost = run_cost(run_id, {small: "small_model", large: "large_model"})
        print(f"Elapsed: {time.monotonic() - start:.1f} s | Recorded cost: USD {cost:.4f}", flush=True)


if __name__ == "__main__":
    main()
