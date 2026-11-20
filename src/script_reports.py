"""Export only spoken figures and their source metadata."""
from collections import defaultdict

from .conflicts import figure_key
from .costs import write_json


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

    if "mara" in scripts:
        lines = ["# Mara: spoken figures", ""]
        for raw, matches, _ in spoken_citations(scripts["mara"]):
            fact = matches[0]
            source = sources[fact["article_id"]]
            fields = [fact["measures"], raw, source["outlet"], source["headline"], source["link"]]
            lines.append("- " + " | ".join(" ".join(value.split()) for value in fields))
        path = out / "mara" / "facts_for_agent.md"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return shared
