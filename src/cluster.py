"""Group the day's extracted articles using cosine distance."""
import argparse
import hashlib
import json
import os
from collections import defaultdict
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering

from .costs import CACHE_DIR, log_call, write_json
from .extract import cache_path, selected_articles

EMBEDDINGS_PATH = CACHE_DIR / "embeddings.parquet"
EMBEDDING_COLUMNS = ["article_id", "model", "input_hash", "embedding"]


def embeddings_for(inputs, model):
    existing = (pd.read_parquet(EMBEDDINGS_PATH) if EMBEDDINGS_PATH.exists()
                else pd.DataFrame(columns=EMBEDDING_COLUMNS))
    cached = existing.set_index("article_id").to_dict("index")
    pending = []
    for article_id, content in inputs.items():
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        row = cached.get(article_id, {})
        if row.get("model") != model or row.get("input_hash") != digest:
            pending.append((article_id, digest, content))

    if pending:
        from openai import APIError, OpenAI

        client = OpenAI(max_retries=0)
        for start in range(0, len(pending), 100):
            batch = pending[start:start + 100]
            try:
                response = client.embeddings.create(
                    model=model, input=[content for _, _, content in batch],
                )
            except APIError as exc:
                log_call("cluster", model)
                raise SystemExit(
                    f"Embeddings failed: {type(exc).__name__} "
                    f"(HTTP {getattr(exc, 'status_code', None)})"
                ) from None
            log_call("cluster", model, input_tokens=response.usage.prompt_tokens)
            for item in response.data:
                article_id, digest, _ = batch[item.index]
                cached[article_id] = dict(model=model, input_hash=digest, embedding=item.embedding)
            snapshot = pd.DataFrame.from_dict(cached, orient="index")
            with NamedTemporaryFile(dir=CACHE_DIR, suffix=".parquet", delete=False) as stream:
                temp = Path(stream.name)
            try:
                snapshot.rename_axis("article_id").reset_index().to_parquet(temp, index=False)
                temp.replace(EMBEDDINGS_PATH)
            finally:
                temp.unlink(missing_ok=True)
    print(f"Embeddings: {len(inputs)} | New: {len(pending)} | Cached: {len(inputs) - len(pending)}")
    return np.asarray([cached[article_id]["embedding"] for article_id in inputs])


def cluster_labels(embeddings, threshold):
    if len(embeddings) < 2:
        return np.zeros(len(embeddings), dtype=int)
    return AgglomerativeClustering(
        metric="cosine", linkage="average", distance_threshold=threshold, n_clusters=None,
    ).fit_predict(embeddings)


def stories_for(articles, labels, figures_by_article, day):
    groups = defaultdict(list)
    for article, label in zip(articles, labels, strict=True):
        groups[label].append(article)

    stories = []
    for members in groups.values():
        ids = [article.id for article in members]
        story_key = hashlib.sha256(json.dumps(ids).encode("utf-8")).hexdigest()[:16]
        stories.append({
            "story_id": f"{day}-{story_key}",
            "title": members[0].headline,
            "article_ids": ids,
            "outlets": sorted({article.outlet for article in members}),
            "n_sources": len(ids),
            "verified_figures": [
                figure for article_id in ids for figure in figures_by_article[article_id]
            ],
            "links": [
                dict(headline=article.headline, outlet=article.outlet, link=article.link)
                for article in members
            ],
        })
    return sorted(stories, key=lambda story: (-story["n_sources"], story["story_id"]))


def main():
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--threshold", required=True, type=float)
    args = parser.parse_args()
    if not 0 < args.threshold <= 2:
        parser.error("--threshold must be greater than 0 and at most 2")

    load_dotenv(CACHE_DIR.parents[1] / ".env", override=True)
    model = os.getenv("OPENAI_EMBEDDING_MODEL")
    if not model:
        raise SystemExit("OPENAI_EMBEDDING_MODEL is required")

    figures_by_article = defaultdict(list)
    verified_path = CACHE_DIR / "verified.json"
    if not verified_path.exists():
        raise SystemExit("Missing verified.json. Run src.verify first.")
    for figure in json.loads(verified_path.read_text(encoding="utf-8")):
        figures_by_article[figure["article_id"]].append(figure)

    articles = []
    inputs = {}
    for article in selected_articles(args.date, None).itertuples(index=False):
        path = cache_path(article.id)
        if path.exists():
            summary = json.loads(path.read_text(encoding="utf-8"))["summary"]
            inputs[article.id] = f"{article.headline}\n{summary}"
            articles.append(article)
    if not articles:
        raise SystemExit(f"No extracted articles for {args.date}. Run src.extract first.")

    labels = cluster_labels(embeddings_for(inputs, model), args.threshold)
    stories = stories_for(articles, labels, figures_by_article, args.date)
    write_json(CACHE_DIR / "stories.json", stories)
    print(f"Stories: {len(stories)} | Articles: {len(articles)} | Threshold: {args.threshold:g}")
    for story in stories[:20]:
        print(f"{story['n_sources']} | {', '.join(story['outlets'])}")
        for source in story["links"]:
            print(f"  - {source['headline'][:90]}")


if __name__ == "__main__":
    main()
