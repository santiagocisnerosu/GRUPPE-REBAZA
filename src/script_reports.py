"""Export only spoken figures and their source metadata."""
from collections import defaultdict

from .conflicts import figure_key
from .costs import write_json


def append_receipt_closing(script, figures_total):
    narration = [sentence for sentence in script["sentences"]
                 if not sentence.get("receipt_closing")]
    sources_total = len({i for sentence in narration for i in sentence["article_ids"]})
    text = (f"Every figure in this briefing, all {figures_total} of them, was checked "
            f"against {sources_total} source articles. Your receipts are in the app.")
    script["sentences"] = [*narration, {
        "text": text, "story_id": "receipt_closing", "article_ids": [], "fact_ids": [],
        "receipt_closing": True,
    }]
    return sources_total


def export_reports(out, scripts, sources, spoken_citations):
    by_fact = defaultdict(dict)
    for listener, script in scripts.items():
        for raw, matches, sentence in spoken_citations(script):
            for fact in matches:
                by_fact[figure_key(fact)][listener] = (raw, fact, sentence)

    shared = []
    for values in by_fact.values():
        if len(values) < 2:
            continue
        _, fact, _ = next(iter(values.values()))
        source = sources[fact["article_id"]]
        shared.append({
            "measure": fact["measures"], "value": fact["value_text"],
            "outlet": source["outlet"], "headline": source["headline"], "link": source["link"],
            "listeners": {listener: {"spoken_value": raw, "sentence": sentence}
                          for listener, (raw, _, sentence) in values.items()},
        })
    write_json(out / "shared_facts.json", shared)
    print("Shared value | Measure | Listener | Sentence")
    for item in shared:
        for listener, line in item["listeners"].items():
            print(f"{item['value']} | {item['measure']} | {listener} | {line['sentence']}")
    print(f"Shared figures: {len(shared)}")

    all_lines = ["# Spoken figures by listener", ""]
    for listener, script in scripts.items():
        lines = [f"# {listener.capitalize()}: spoken figures", ""]
        for raw, matches, _ in spoken_citations(script):
            fact = matches[0]
            source = sources[fact["article_id"]]
            fields = [fact["measures"], raw, source["outlet"], source["headline"], source["link"]]
            lines.append("- " + " | ".join(" ".join(value.split()) for value in fields))
        (out / listener / "facts_for_agent.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        all_lines.extend([f"## {listener.capitalize()}", "", *lines[2:], ""])
    (out / "facts_for_agent_all.md").write_text("\n".join(all_lines), encoding="utf-8")
    return shared
