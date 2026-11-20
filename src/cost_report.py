"""Price observed API usage and model profile-segment reuse."""
import argparse
import json
import os
from collections import defaultdict
from decimal import Decimal

import yaml
from dotenv import load_dotenv

from .audio import story_paragraphs
from .costs import CACHE_DIR, write_json
from .script import LISTENERS, ROOT

PREPARATION_STAGES = {"extract", "cluster", "cluster_refine", "story_score", "story_conflicts"}


def priced(entry, prices, model_types):
    if entry["stage"] == "tts":
        return Decimal(entry["tts_chars"]) * prices["elevenlabs"]["tts_per_1k_chars"] / 1000
    model = entry["model"]
    rates = prices["openai"][model_types[model]]
    return (Decimal(entry["input_tokens"]) * rates["input_per_1m"]
            + Decimal(entry["output_tokens"]) * rates.get("output_per_1m", 0)) / 1_000_000


def audio_characters(scripts):
    measures = {}
    for listener, script in scripts.items():
        lines = script["sentences"]
        total = len(story_paragraphs(lines)[0])
        personal = len(story_paragraphs([
            line for line in lines if any(line.get(key) for key in (
                "editor_opener", "editor_closer", "receipt_closing"
            ))
        ])[0])
        measures[listener] = {"total": total, "personal": personal, "shared": total - personal}
    return measures


def report(start_record):
    load_dotenv(ROOT / ".env", override=True)
    models = {os.environ[f"OPENAI_{name}_MODEL"]: rate for name, rate in (
        ("SMALL", "small_model"), ("LARGE", "large_model"), ("EMBEDDING", "embeddings")
    )}
    config = yaml.safe_load((ROOT / "prices.yaml").read_text(encoding="utf-8"))
    prices = dict(config)
    prices["openai"] = {
        group: {name: Decimal(str(value)) for name, value in rates.items()}
        for group, rates in prices["openai"].items()
    }
    prices["elevenlabs"] = {k: Decimal(str(v)) for k, v in prices["elevenlabs"].items()}
    lines = (CACHE_DIR / "costs.jsonl").read_text(encoding="utf-8").splitlines()
    if not 0 <= start_record < len(lines):
        raise ValueError("The starting record must precede at least one observed call")
    observations = []
    malformed = []
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            malformed.append(index)
            continue
        observations.append((index, row, priced(row, prices, models)))
    priced_log = [(row, cost) for _, row, cost in observations]
    recent = [(row, cost) for index, row, cost in observations if index >= start_record]
    lost_in_run = sum(index >= start_record for index in malformed)
    actual = sum(cost for _, cost in recent)
    by_stage = defaultdict(Decimal)
    usage = dict(input_tokens=0, output_tokens=0, tts_chars=0)
    for row, cost in recent:
        by_stage[row["stage"]] += cost
        for name in usage:
            usage[name] += row[name]
    scripts = {listener: json.loads(
        (ROOT / "out" / listener / "script.json").read_text(encoding="utf-8")
    ) for listener in LISTENERS}
    stories = json.loads((CACHE_DIR / "stories.json").read_text(encoding="utf-8"))
    baseline = len({i for story in stories for i in story["article_ids"]})
    assumptions = config["assumptions"]
    volume = int(assumptions.get("articles_per_day_full_dataset") or 1740)
    listeners = int(assumptions["listeners_scenario"])
    days = int(assumptions.get("days_per_month", 30))
    chars = audio_characters(scripts)
    profiles = len(chars)
    prep = sum(cost for row, cost in priced_log if row["stage"] in PREPARATION_STAGES)
    editorial = sum(cost for row, cost in recent
                    if row["stage"] not in PREPARATION_STAGES | {"tts"})
    unit = prices["elevenlabs"]["tts_per_1k_chars"] / 1000
    shared = sum(x["shared"] for x in chars.values())
    personal_average = Decimal(sum(x["personal"] for x in chars.values())) / profiles
    full_average = Decimal(sum(x["total"] for x in chars.values())) / profiles

    def day(articles, audience):
        fixed = prep * articles / baseline + editorial
        return (fixed + unit * (shared + personal_average * audience),
                fixed + unit * (full_average * audience))

    def scenario(label, costs):
        return dict(scenario=label, with_segment_cache=float(costs[0]),
                    without_segment_cache=float(costs[1]))

    monthly = tuple(x * days for x in day(volume, listeners))
    rows = [
        scenario("This run (recorded API usage; lower bound)" if lost_in_run
                 else "This run (actual API usage)", (actual, actual)),
        scenario(f"Full dataset ({volume:,} articles, one day, three profile versions)", day(volume, profiles)),
        scenario(f"10x ({volume * 10:,} articles, one day, three profile versions)", day(volume * 10, profiles)),
        scenario(f"Per listener per month at {listeners:,} listeners", tuple(x / listeners for x in monthly)),
        scenario(f"{listeners:,} listeners per month", monthly),
    ]
    output = {
        "currency": "USD", "start_record": start_record, "api_calls": len(recent), "unpriced_records": lost_in_run,
        "malformed_log_lines": [index + 1 for index in malformed], "usage": usage,
        "actual_by_stage": {k: float(v) for k, v in sorted(by_stage.items())},
        "assumptions": {
            "observed_articles": baseline, "articles_daily_full_dataset": volume,
            "days_per_month": days, "listeners": listeners,
            "profile_count": profiles, "equal_profile_mix": True,
            "audio_characters": chars, "shared_preparation_cost_observed": float(prep),
            "three_profile_editorial_cost_observed": float(editorial),
        },
        "scenarios": rows,
    }
    notes = (
        f"Rates come from prices.yaml. Dataset preparation scales from {baseline} observed "
        f"articles; three profile drafts are generated daily. The monthly model assumes "
        f"{days} days, one briefing per listener per day, and an equal profile mix.",
        "Segment reuse is a projection. Each voice and settings combination synthesizes its "
        "story segments once daily. Greetings and sign-offs are charged per listener; "
        "without reuse every listener incurs the full audio cost. The actual run uses "
        "the existing whole-briefing cache and is shown as observed in both columns.",
    )
    if lost_in_run:
        notes += (f"{lost_in_run} unreadable usage-log line(s) in this run were excluded; "
                  "the observed total and projections may slightly understate costs.",)
    output["notes"] = notes
    out = ROOT / "out"
    write_json(out / "costs.json", output)
    lines = [
        "# Receipts API costs (USD)", "",
        "| Scenario | With segment cache | Without segment cache |", "|---|---:|---:|",
        *[f"| {r['scenario']} | ${r['with_segment_cache']:,.4f} | ${r['without_segment_cache']:,.4f} |"
          for r in rows],
        "", *notes,
    ]
    markdown = "\n".join(lines) + "\n"
    (out / "costs.md").write_text(markdown, encoding="utf-8")
    print(markdown, end="")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since-record", required=True, type=int,
                        help="Number of existing cost-log records before the run")
    report(parser.parse_args().since_record)


if __name__ == "__main__":
    main()
