# Verbatim: personal audio news briefings you can trust

Team GRUPPE REBAZA · MAIN AI Hackathon 2026 · Sourcera challenge
**Hard deadline: Saturday 21 Nov, 10:30 (submit on BuilderBase by 10:00). Code freeze: Saturday 07:30.**

## The challenge (from Sourcera)
"How might AI turn a day of news into a personal audio briefing that fits each listener, and that they can trust?"

**Hand in:** (1) a working prototype that generates audio briefings from the dataset, with at least two clearly different listener profiles and every claim linked to its source article; (2) a short presentation covering the problem and who pays, how it fits a newsroom's day, and the cost for the full dataset and at 10x the volume; (3) for MAIN: project name, code, and a 3-minute pitch video.

**Jury criteria (6):**
1. Trust & accuracy: every figure and claim in the audio links to its source article, and the numbers are right.
2. Fit to the listener: two listeners get clearly different story choice, depth, length or language.
3. Making sense of the news: stories grouped, duplicates merged, key facts and figures extracted.
4. Scalability & cost: could run daily at a newsroom's volume, with large models only where needed.
5. Listening experience: would you listen to it tomorrow morning?
6. Path to product: who pays for it, and how it fits a newsroom's day.

## ⚠️ Data license rules (non-negotiable)
- The Newstex dataset is licensed for this hackathon only. **Never commit it.** It lives in `data/raw/` (gitignored).
- **Never republish article text.** Outputs may contain headline + link + our own summaries, never copied paragraphs.
- Delete the data after the event.

## Our differentiators (what makes us better than every other team)
1. **Number lock:** every figure is extracted with its source article and character span, then checked by code (not by an LLM) to appear in the source text. The script may only use verified facts, cited by ID. A final check rejects any sentence that contains a number not in the verified fact ledger. The UI shows "N claims · N verified · M sources".
2. **Shared segments, cheap per listener:** story audio is generated once per (story, language, depth) and reused across all listeners. Per listener we only generate a short intro, transitions and outro. Cost report compares with and without this cache.
3. **Model routing:** embeddings for clustering, the small model for per-story extraction, the large model only for the final script. Every API call is logged with tokens/characters and cost.
4. **Real listening:** two-voice podcast format (host + analyst) with ElevenLabs, a web player with synced transcript where every sentence links to its sources, and **one podcast RSS feed per profile** so judges can subscribe on their phone.
5. **Three very different profiles** from the same day (see `profiles.yaml`): Dutch retail investor (NL, 3 min, simple), London portfolio manager (EN, 7 min, dense), German FX trader (DE, 2 min, EUR/USD).

## Stack
- Python 3.11+, one script per pipeline stage under `src/`, orchestrated by `src/pipeline.py`.
- `openai` SDK (Responses API, embeddings), `elevenlabs` SDK, `pandas`, `numpy`, `scikit-learn` (clustering), `pydantic` (schemas), `pyyaml`, `python-dotenv`.
- Web player: static `web/` (single `index.html` + JS, no framework) that reads JSON/MP3 from `out/`. Deployable as static files (Vercel).
- Model names, voices and prices come from `.env` / `prices.yaml`, never hardcoded.

## Repo layout
```
data/raw/            # Newstex JSONL (gitignored)
data/cache/          # embeddings, extractions, audio segments (gitignored)
src/
  ingest.py          # load + normalize all feeds -> data/cache/articles.parquet
  cluster.py         # embeddings + clustering -> stories.json
  extract.py         # per story: facts with figures + source spans -> facts.json
  verify.py          # deterministic number check -> facts_verified.json + flagged.json
  select.py          # rank stories per profile
  script.py          # per profile: script segments citing fact IDs
  check.py           # reject sentences with unverified numbers / missing citations
  tts.py             # ElevenLabs audio per segment (cached) + stitch per profile, with timestamps
  publish.py         # out/<profile>/<date>/{briefing.mp3, transcript.json}, RSS feeds
  costs.py           # cost logger + report (run, full dataset, 10x, per listener/month)
  pipeline.py        # CLI: python -m src.pipeline --date YYYY-MM-DD --profiles all [--sample 100]
web/index.html       # player: profile switcher, audio, synced transcript, source links, stats
profiles.yaml
prices.yaml
out/                 # generated (gitignored except a small demo sample if needed)
```

## Pipeline spec and acceptance criteria
**Always develop on `--sample 100` first, then run on the full day.** Every stage caches its output and is idempotent (re-running does not re-pay).

1. **ingest** ✅ DONE (`src/ingest.py`, run `python -m src.ingest`). Output `data/cache/articles.parquet` with columns `id, feed, outlet, language, date, day, headline, author, excerpt, text, categories, provider_categories, tickers, link, char_count, has_figure, translation_of, story_seed`. Invezz DE/NL translations are linked to their English original (same author, ≤15 min; 238/240 matched) and share a `story_seed`, so they are processed once and every language version is kept as a source.
   **Facts about the data:** 1,740 articles; weekdays have 172–190 articles (16–18 Nov), weekends 42–60. Zacks is 1,000 articles but only 71 from 13 Nov onward. ActionForex = FX and central banks; IBTimes UK = general news; Invezz = stocks, crypto, AI; Zacks = equity and ETF research. `company_tickers` is almost always empty (30 articles) and the POSITIVE/NEGATIVE categories are unreliable, so do not use them. **Default briefing day: `2026-11-18`** (window: 17–18 Nov).
2. **cluster**: Work on `story_seed` (one row per seed, use the English version when it exists). Embed `headline + excerpt` (multilingual embeddings so the same event from different outlets/languages merges). Restrict to the briefing window (date and the previous day). Agglomerative clustering with a cosine distance threshold (start around 0.2, tune by inspecting results). Accept: print the 15 largest stories with headlines from each member; same event in two languages lands in one story.
3. **extract** (small model, one call per story, not per article): structured output, a list of facts `{fact_id, story_id, claim, figure_raw, figure_value, unit, entity, source_article_id, source_quote}`. `source_quote` must be a short exact substring of the source text containing the figure. Plus a story title, a summary, importance (number of sources/outlets), tickers and assets.
4. **verify** (pure code, no LLM): the fact passes only if `source_quote` is found in the source text (whitespace-normalized) AND the figure appears inside it after number normalization (handle `1.5%`/`1,5 %`, `$2.3bn`/`2.3 billion`/`2,3 Mrd.`, thousands separators). Failed facts go to `flagged.json` (shown in an editor-review panel). Accept: verification rate printed and a few flagged examples inspected by a human.
5. **select**: score stories per profile = topic and asset match + importance + recency; respect the profile's minute budget (~150 spoken words/min). Accept: the three profiles get visibly different story lists.
6. **script** (large model): per story segment and per (language, depth), a 2-voice dialogue (HOST/ANALYST) using ONLY verified facts, each sentence tagged with the fact IDs it uses, e.g. `[F12,F14]`. Numbers written as digits. Plus a per-profile intro (greets by profile name, date, what's coming) and an outro. Accept: JSON segments, every sentence has ≥1 fact ID.
7. **check** (code): for every sentence, every number it contains must match (normalized) a figure of a fact it cites. Violations: regenerate that segment once, otherwise drop the sentence. Accept: 0 unverified numbers in final scripts; stats saved.
8. **tts**: ElevenLabs with two voices (from `.env`), using the endpoint with timestamps. Cache audio per segment key `(story_id, language, depth, script_hash)`. Stitch intro + segments + outro per profile. Accept: MP3 per profile and a transcript with start/end times per sentence.
9. **publish**: `out/<profile>/<date>/briefing.mp3` + `transcript.json` (sentences, times, speaker, fact IDs, source headline + link, outlet). One RSS 2.0 podcast feed per profile in `out/feeds/<profile>.xml` (absolute URLs from `PUBLIC_BASE_URL`).
10. **costs**: log every API call (stage, model, input/output tokens, TTS characters) to `data/cache/costs.jsonl`; prices from `prices.yaml`. The report prints: this run; the full dataset; 10x volume; per listener per day and per month; 10,000 listeners per month, **with and without segment caching**. Output `out/costs.json` and a markdown table for the slides.

## Web player (`web/index.html`)
Profile switcher (3 cards) · audio player · transcript that highlights the current sentence · each sentence shows clickable source chips (outlet + headline → link) · top stats: "N claims · N verified · M sources · K languages · €X per listener/month" · "Subscribe" button with the RSS link · editor panel listing flagged facts. Clean and calm design; must look good on a projector.

## Working rules for coding agents
- Small, testable steps; run the stage on the sample after every change and show the output.
- Do not print or log full article texts (headline + 200 chars is fine for debugging).
- No secrets in code; read from `.env`. Never commit `data/`, `.env`, or large audio.
- Do not change file formats between stages without updating this file.
- Commit small and often with clear messages; `git pull` before starting a task.

## Who does what
- **Santiago:** ingest, cluster, extract, verify, costs.
- **Vasco:** profiles, select, script, check, tts, RSS.
- **Sousa:** web player, business model, presentation, pitch video.

## Milestones
- Fri 15:00: ingest + clustering on the sample; ElevenLabs voices chosen; player skeleton.
- Fri 18:00: **first ugly end-to-end briefing** for 1 profile (sample).
- Fri 21:00: 3 profiles on the full day, number lock working, player playing real output.
- Fri 00:30: costs report, RSS feeds live, polish. Then sleep.
- Sat 07:30: code freeze · 07:30–09:00 record video · submit by 10:00 · re-check-in 11:00–11:45.
