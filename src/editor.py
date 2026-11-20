"""Apply article-level editorial instructions to ranked story material."""
from collections import Counter
import re

FILLERS = {
    "separate": re.compile(r"\bseparate(?:ly)?\b", re.I),
    "if you hold": re.compile(r"\bif you hold\b", re.I),
    "for your holdings": re.compile(r"\bfor your [\w -]{1,30} holdings\b", re.I),
}
OUTLETS = re.compile(r"\b(?:ActionForex|Invezz|Zacks(?: Investment Research)?|"
                     r"International Business Times(?: UK)?|IBTimes(?: UK)?)\b", re.I)


def article_policy(stories, editor):
    blocked = set(editor.get("exclude_articles", []))
    inventory = {}
    prepared = []
    for story in stories:
        current = dict(story)
        links = []
        for article_id, link in zip(story["article_ids"], story["links"], strict=True):
            if article_id in blocked:
                continue
            figures = [f for f in story["verified_figures"] if f["article_id"] == article_id]
            inventory[article_id] = (link, figures, story["story_id"])
            links.append((article_id, link, figures))
        current["article_ids"] = [i for i, _, _ in links]
        current["links"] = [link for _, link, _ in links]
        current["verified_figures"] = [f for _, _, fs in links for f in fs]
        current["outlets"] = sorted({link["outlet"] for link in current["links"]})
        current["n_sources"] = len(links)
        prepared.append(current)
    return prepared, inventory


def apply_inclusions(story, pin, editor, inventory, occupied):
    story["article_ids"] = list(story["article_ids"])
    story["links"] = list(story["links"])
    story["verified_figures"] = list(story["verified_figures"])
    for article_id in editor.get("include_articles", {}).get(pin["id"], []):
        if article_id not in inventory:
            print(f"Editor article missing | {pin['id']} | {article_id}")
            continue
        link, figures, original_story = inventory[article_id]
        occupied.add(original_story)
        if article_id not in story["article_ids"]:
            story["article_ids"].append(article_id)
            story["links"].append(link)
            story["verified_figures"].extend(figures)
    story["n_sources"] = len(story["article_ids"])
    story["outlets"] = sorted({link["outlet"] for link in story["links"]})
    story["pin"] = {**pin, "lead": pin.get("lead", False) or pin["id"] == editor.get("lead_story")}
    return story


def editorial_errors(text, previous, story_id):
    errors = []
    spoken = "\n".join(line["text"] for line in previous)
    for label, pattern in FILLERS.items():
        if len(pattern.findall(text)) + len(pattern.findall(spoken)) > 1:
            errors.append({"cifra": None, "motivo": f"repeated_filler: {label}"})
    named = OUTLETS.findall(text)
    prior = sum(len(OUTLETS.findall(line["text"])) for line in previous if line["story_id"] == story_id)
    if named and len(named) + prior > 1:
        errors.append({"cifra": None, "motivo": "outlet_named_more_than_once_in_story"})
    return errors


def overfull_stories(lines, stories):
    counts = Counter(line["story_id"] for line in lines)
    return [f"{s['title']}: at most {s['max_sentences']} sentences"
            for s in stories if s["max_sentences"] and counts[s["story_id"]] > s["max_sentences"]]


def name_companies(text, editor):
    for pattern, name in editor.get("entity_names", {}).items():
        text = re.sub(pattern, name, text, flags=re.I)
    return text
