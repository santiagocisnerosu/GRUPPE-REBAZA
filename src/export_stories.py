"""Export the clustering evidence for the saved, narrated edition. No API calls."""
import json

import pandas as pd

from .costs import CACHE_DIR, write_json
from .script import LISTENERS, ROOT


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def export_stories():
    clusters = read_json(CACHE_DIR / "stories.json")
    by_id = {c["story_id"]: c for c in clusters}
    cluster_of = {i: c["story_id"] for c in clusters for i in c["article_ids"]}
    if len(cluster_of) != sum(len(c["article_ids"]) for c in clusters):
        raise ValueError("An article occurs more than once in the cluster output")
    dates = pd.read_parquet(CACHE_DIR / "articles.parquet", columns=["id", "date"]).set_index("id")["date"]
    days = {c["story_id"][:10] for c in clusters}
    if len(days) != 1:
        raise ValueError("Expected one news day in the saved cluster output")
    day = days.pop()
    output = ROOT / "out"
    stories = {}
    used = {}
    for listener in LISTENERS:
        script = read_json(output / listener / "script.json")
        transcript = read_json(output / listener / "transcript.json")
        if script["date"] != day or transcript["date"] != day:
            raise ValueError(f"{listener}: scripts, transcripts and clusters must be from the same run")
        titles = {s["story_id"]: s["title"] for s in script["selected_stories"]}
        # A published transcript has chapter titles but no IDs. Use its actual
        # playback order, matching each news sentence to the source-linked script.
        spoken = {
            (line["text"], tuple(line["article_ids"])): line["story_id"]
            for line in script["sentences"] if line["article_ids"]
        }
        heard = set()
        for index, line in enumerate(transcript["sentences"]):
            ids = tuple(source["article_id"] for source in line["sources"])
            if not ids:
                continue
            story_id = spoken.pop((line["text"], ids))
            headline = titles[story_id]
            if headline != line["story"]:
                raise ValueError(f"{listener}: transcript chapter differs from script for {story_id}")
            if story_id not in by_id and not story_id.startswith(f"{day}-pin-"):
                raise ValueError(f"{listener}: story {story_id} is missing from the saved clusters")
            story = stories.setdefault(story_id, {
                "story_id": story_id, "headline": headline, "listeners": {}, "articles": [],
            })
            story["listeners"][listener] = {"last_sentence_index": index}
            heard.add(story_id)
            # An editor can combine several saved event clusters into one chapter.
            # Expand each contributing cluster in full, including uncited members.
            group_ids = dict.fromkeys(cluster_of[i] for i in ids)
            if story_id in by_id:
                group_ids[story_id] = None
            existing = {a["cluster_id"] for a in story["articles"]}
            for group_id in group_ids:
                if group_id in existing:
                    continue
                group = by_id[group_id]
                for article_id, source in zip(group["article_ids"], group["links"], strict=True):
                    story["articles"].append({
                        "article_id": article_id, "cluster_id": group_id,
                        "outlet": source["outlet"], "title": source["headline"],
                        "published_at": dates.at[article_id].isoformat(),
                        "link": source.get("link"),
                    })
        if spoken:
            raise ValueError(f"{listener}: transcript is missing sourced script sentences")
        used[listener] = len(heard)

    catalog = {"date": day, "articles_in": len(cluster_of), "stories_formed": len(clusters),
               "stories_used": used, "stories": list(stories.values())}
    for folder in (output, ROOT / "docs" / "out"):
        write_json(folder / "stories.json", catalog)
    print(f"{day}: {len(cluster_of)} articles, {len(clusters)} clusters, "
          f"{len(stories)} distinct briefing stories. Used per listener: {used}")


if __name__ == "__main__":
    export_stories()
