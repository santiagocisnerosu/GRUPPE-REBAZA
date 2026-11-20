"""Stage 1 - ingest: load every Newstex JSONL feed into one normalized table.

Usage:
    python -m src.ingest                       # reads data/raw/**/*.jsonl
    python -m src.ingest --raw path/to/folder  # custom folder

Output: data/cache/articles.parquet with one row per article:
    id, feed, outlet, language, date (UTC), day, headline, author, excerpt, text,
    categories, provider_categories, tickers, link, char_count, has_figure,
    translation_of   -> id of the English original if this article is a DE/NL
                        translation of it (same author, within 15 minutes), else None
    story_seed       -> translation_of or own id (translations collapse into one seed;
                        stage 2 clusters seeds, so translations are never paid for twice)

Never prints full article text (licence: no republishing).
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

import pandas as pd

RAW_DIR = Path("data/raw")
OUT_PATH = Path("data/cache/articles.parquet")
TRANSLATION_WINDOW_MIN = 15

FIGURE_RE = re.compile(r"(?:\d[\d.,]*\s?%|[$€£]\s?\d|\d[\d.,]*\s?(?:bn|billion|million|mrd|mio|miljard|miljoen))", re.I)
TAG_RE = re.compile(r"<[^>]+>")


def _as_list(value) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _html_to_text(raw: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", raw or ""))).strip()


def normalize(record: dict, feed: str) -> dict:
    publication = record.get("publication") or {}
    text = record.get("text_content") or _html_to_text(record.get("html_content", ""))
    return {
        "id": record["$id"],
        "feed": feed,
        "outlet": publication.get("name") or feed,
        "language": (record.get("language") or "").lower(),
        "date": record.get("date"),
        "headline": (record.get("headline") or "").strip(),
        "author": (record.get("source") or "").strip(),
        "excerpt": (record.get("excerpt") or "").strip(),
        "text": text,
        "categories": _as_list(record.get("categories")),
        "provider_categories": _as_list(record.get("provider_categories")),
        "tickers": _as_list(record.get("company_tickers")),
        "link": record.get("permalink") or record.get("external_id"),
    }


def load(raw_dir: Path) -> pd.DataFrame:
    files = sorted(raw_dir.rglob("*.jsonl"))
    if not files:
        raise SystemExit(f"No .jsonl files found under {raw_dir.resolve()}")
    rows, bad = [], 0
    for path in files:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rows.append(normalize(json.loads(line), path.stem))
                except (json.JSONDecodeError, KeyError):
                    bad += 1
    if bad:
        print(f"[ingest] skipped {bad} malformed lines")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], utc=True)
    df["day"] = df["date"].dt.strftime("%Y-%m-%d")
    df["char_count"] = df["text"].str.len()
    df["has_figure"] = df["text"].str.contains(FIGURE_RE)
    before = len(df)
    df = df.drop_duplicates("id").sort_values("date").reset_index(drop=True)
    if before != len(df):
        print(f"[ingest] dropped {before - len(df)} duplicate ids")
    return df


def link_translations(df: pd.DataFrame) -> pd.DataFrame:
    """Invezz publishes the same article in EN, DE and NL by the same author within
    minutes. Link each non-English Invezz article to its English original so the
    pipeline processes the story once and keeps all language versions as sources."""
    df["translation_of"] = None
    invezz = df["outlet"].str.contains("Invezz", case=False)
    originals = df[invezz & (df["language"] == "en")]
    window = pd.Timedelta(minutes=TRANSLATION_WINDOW_MIN)
    for idx, row in df[invezz & (df["language"] != "en")].iterrows():
        cands = originals[
            (originals["author"] == row["author"]) & ((originals["date"] - row["date"]).abs() <= window)
        ]
        if not cands.empty:
            best = (cands["date"] - row["date"]).abs().idxmin()
            df.at[idx, "translation_of"] = df.at[best, "id"]
    df["story_seed"] = df["translation_of"].fillna(df["id"])
    return df


def summarize(df: pd.DataFrame) -> None:
    print(f"\n[ingest] {len(df)} articles, {df['char_count'].sum():,} characters of text")
    print("\nBy outlet and language:")
    print(df.groupby(["outlet", "language"]).size().to_string())
    print("\nArticles per day (all feeds):")
    print(df.groupby("day").size().tail(10).to_string())
    linked = df["translation_of"].notna()
    non_en_invezz = df["outlet"].str.contains("Invezz", case=False) & (df["language"] != "en")
    print(f"\nTranslations linked to English original: {linked.sum()} of {non_en_invezz.sum()} DE/NL Invezz articles")
    print(f"Unique story seeds (after collapsing translations): {df['story_seed'].nunique()}")
    print(f"Articles with at least one %/currency figure: {df['has_figure'].sum()}")
    print(f"Articles with tickers: {(df['tickers'].str.len() > 0).sum()}")
    print("\nSample (headline only):")
    for _, r in df.sample(5, random_state=1).iterrows():
        print(f"  [{r['day']} {r['language']} {r['outlet']}] {r['headline'][:90]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1: ingest Newstex JSONL feeds")
    parser.add_argument("--raw", type=Path, default=RAW_DIR)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    df = link_translations(load(args.raw))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    summarize(df)
    print(f"\n[ingest] wrote {args.out}")


if __name__ == "__main__":
    main()
