# Receipts: a morning audio briefing where every number is checked against its source

Team GRUPPE REBAZA · MAIN AI Hackathon 2026 · Sourcera track
One-line pitch: "A briefing you can trust by ear, at a cost a newsroom can carry every morning."

## Current state

The Thursday 19 November demo is live on GitHub Pages. The pipeline ingested 1,740 articles and grouped the 145 English articles in the demo window into 128 stories. Each listener has a mastered MP3, a word-timed transcript and a receipt for every spoken figure. [Open Morning Edition](https://santiagocisnerosu.github.io/GRUPPE-REBAZA/)

| Listener | Editorial angle | Spoken figures verified |
|---|---|---:|
| Mara | What moves rates and currencies before the London desk opens? | 21/21 |
| Jordan | What do tech earnings and crypto prices mean for his holdings? | 15/15 |
| Priya | How do trade, fuel and currency moves affect her UK retail business? | 6/6 |

- **Morning Edition** lets listeners switch editions, jump between chapters and follow the audio with word-by-word karaoke. The active sentence links to its sources. Presentation mode is ready for recording. [Jordan in presentation mode](https://santiagocisnerosu.github.io/GRUPPE-REBAZA/?present=1&listener=jordan)
- **Trust panel.** In Jordan’s Bitcoin draft, the checker blocked $64,000 because it was absent from the cited facts. The audio uses the verified Coinbase price of $63,465. “See full audit” shows rejected material and disagreements between sources.
- **Shared meanings.** “One fact, different meanings” pairs Mara’s market reading with Priya’s business consequence for three figures they both use, including 33.2% motor fuel inflation. Each reading comes from that listener’s sourced narration. [Shared facts](docs/out/shared_facts.json)
- **Costs.** Recorded API usage for the demo run cost at least $1.8544. One log entry was unreadable. At 10,000 listeners, the projection is $0.8958 per listener per month with story audio reused per voice, or $8.0846 with full synthesis per listener. [Published cost report](docs/out/costs.json)

### Key decisions

Use the English feeds for 18 November and include the previous evening from 18:00 UTC. Extract and verify figures against each article once, then share the verified stories across listeners. Keep editorial pins, narration rules and voices in `profiles.yaml`. Reserve the large model for writing and repairing scripts. Reuse cached API responses and ElevenLabs alignments so mastering preserves karaoke timing. Publish the checked demo assets from `main` under `docs/`. Keep the licensed feeds and credentials local.

### Regenerate the demo

From the repository root, use PowerShell and Python 3.11+. Put the licensed JSONL feeds in `data/raw/`, configure the OpenAI and ElevenLabs keys and models in `.env`, and keep `data/cache/` for repeat runs. Capture the cost-log position before the first pipeline step. A fully cached replay of this edition reuses its published cost report.

```powershell
python -m pip install -r requirements.txt
$costLog = 'data/cache/costs.jsonl'
$startRecord = @(Get-Content $costLog -ErrorAction SilentlyContinue).Count
python -m src.ingest
python -m src.extract --date 2026-11-18 --overnight
python -m src.verify --date 2026-11-18 --overnight
python -m src.cluster --date 2026-11-18 --overnight --threshold 0.45
python -m src.script --date 2026-11-18 --overnight --listener all --regenerate
python -m src.audio --listener all
if (@(Get-Content $costLog -ErrorAction SilentlyContinue).Count -gt $startRecord) {
    python -m src.cost_report --since-record $startRecord
} else {
    Copy-Item docs/out/costs.json out/costs.json
}
python -m src.publish_site
```

The last command checks the narration against the licensed articles, builds the Pages site and generates [the jury QR code](docs/qr.png). Preview the packaged demo with `python -m http.server 8000 --directory docs` and open [Morning Edition locally](http://localhost:8000/).

### Still to deliver

Record the **3-minute pitch video** using the frozen demo. Finish the **8-slide presentation** with the observed cost, scaling assumptions, newsroom workflow and buyer. Submit the project name, matching code version and video to BuilderBase by **10:00 on Saturday 21 November**, ahead of the 10:30 hard deadline.

## ⏰ Real deadlines (do not trust any other timeline)
- **Saturday 21 Nov 10:30 hard deadline on BuilderBase** (form closes on the dot). We submit by **10:00**.
- MAIN asks every team for: project name, code (same version as the demo), **3-minute pitch video**.
- Sourcera asks for: working prototype + short presentation with costs.
- Saturday 11:00–11:45 mandatory re-check-in at Sint Janskerk. Finals from 15:00.
- **Code/scope freeze Saturday 07:30.** 07:30–09:00 record the video. 09:00–10:00 deck + submit.

## The challenge and jury criteria
"How might AI turn a day of news into a personal audio briefing that fits each listener, and that they can trust?"
1. Trust & accuracy: every figure and claim links to its source article, and the numbers are right.
2. Fit to the listener: two listeners get clearly different story choice, depth, length or language.
3. Making sense of the news: stories grouped, duplicates merged, key facts and figures extracted.
4. Scalability & cost: could run daily at a newsroom's volume, large models only where needed.
5. Listening experience: would you listen to it tomorrow morning?
6. Path to product: who pays, and how it fits a newsroom's day.

## Why we win
Most teams will build "ChatGPT summary → ElevenLabs voice". We win on trust with something we can show:
- a live counter "52 of 52 figures verified, 0 invented";
- **the caught mistake**: a wrong number the AI wrote, caught by code and cut before it reached the audio;
- **one story, three angles**: Nvidia told three completely different ways to three listeners.

## Ground rules
- **Licence:** data is for this hackathon only. Never commit `data/`. Never read article text aloud or republish it; scripts are in our own words, quotes under ~10 words and name the source. Delete data after the event.
- **English only** for the core: ActionForex, Invezz EN, IBTimes UK, Zacks. Invezz DE/NL are translations of Invezz EN (linked via `translation_of` in ingest). *Stretch only if all 3 English briefings work by Fri 21:00:* one listener also in Dutch or German (criterion 2 literally says "or language").
- **Demo day = news of 18 Nov** (use `--overnight` on extract, verify, cluster and script to include the prior day from 18:00 UTC), presented as "your briefing for the morning of Thursday 19 November" (~122 English articles after filters).
- Zacks: only articles from 13 Nov onward.
- Ignore POSITIVE/NEGATIVE tags (unreliable, organisers confirm) and `company_tickers` (almost always empty).
- Every sentence in a script carries its source article IDs. **No ID, no sentence.**
- Develop on 10 articles; run the full day only once prompts work. Cache every API answer to disk; never pay twice.
- Strong model only for the scripts. Everything else: small model or no model.
- Model names, voices and prices come from `.env` / `prices.yaml`, never hardcoded. Log tokens/characters for every call (`src/costs.py`).

## Pipeline (Python, run in order)
| Step | File | Model | What it does | Done when |
|---|---|---|---|---|
| 0 | `src/ingest.py` ✅ | none | All feeds → `data/cache/articles.parquet` (id, outlet, language, date, day, headline, author, excerpt, text, categories, provider_categories, link, translation_of, story_seed…) | done: 1,740 articles |
| 1 | `src/extract.py` | small | Per English article of the day (text cut to first 6,000 chars): JSON with topic, one-line summary in our words, up to 5 key figures each with the **exact phrase** it came from. Once per article, shared by all listeners. | `data/cache/extracted/<article_id>.json` |
| 2 | `src/verify.py` | none | Each figure must appear in the source text inside its exact phrase (after number normalisation: `$1.2bn`/`1.2 billion`, `3,6 %`/`3.6%`, thousands separators). Found figures go to `data/cache/verified.json`, with `kind: word` for supported numbers written in words; rejected figures go to `data/cache/rejected.json` with a reason (our "caught mistakes" demo). | verification rate printed |
| 3 | `src/cluster.py` | embeddings + small | Cluster extracted articles by headline + summary using average-linkage cosine distance. Refine multi-article groups into distinct events with the small model. Cache vectors in `data/cache/embeddings.parquet` and partitions by story ID, then write `data/cache/stories.json` with verified figures and source links. | gold story = 3 articles, 2 outlets merged |
| 4 | `src/script.py` | small + strong | Cache per-listener fit and urgency by story ID. Rank by twice fit, outlet diversity, verified figures and urgency, with one slot per topic. Add five points for editor pins and apply article inclusions, exclusions, and narration rules from `profiles.yaml`. Screen Priya's stories for a concrete business consequence and a verified figure. Extract and check qualitative source claims only for selected articles. Detect competing readings with `src/conflicts.py` and log which figures were spoken in `data/cache/conflicts.json`. Write `out/<listener>/script.json` with sentences, fact IDs and article IDs. Check cited numbers, reject repeats and number-led sentences, cap each sentence at two figures, check repeated meanings and copied runs of 8 words, and target the profile budget within 10%. Repair once or drop; log issues in `out/<listener>/caught.json`. Export shared spoken facts to `out/shared_facts.json` and Mara's source ledger to `out/mara/facts_for_agent.md`. | 3 scripts, every retained sentence passes the checks |
| 5 | `src/audio.py` | ElevenLabs | Use the cached original audio and character alignment for the submitted voice, settings, model and text. Master the delivery MP3 to −16 LUFS and at most −1.5 dBTP, preserving its decoded sample count. Each sentence in `transcript.json` includes `words: [{w, start, end}]` with original printed words and absolute audio times in seconds. | MP3 and karaoke stay synchronized |
| – | `web/player.html` | none | Listener switcher, audio, current sentence highlighted, clickable source chips (outlet + headline → link), counter "X of X figures verified", panel with the caught mistakes. Must look good on a projector. | demo-ready |
| – | `src/costs.py` | none | Report: one briefing, full 1,740-article dataset, 10× volume. Extraction is per article, scripts/audio per listener; at scale, audio segments per story are recorded once per tone and stitched, so audio grows with stories, not listeners. Run `python -m src.cost_report --since-record N`, where N is the cost-log record count before the run. Read rates from `prices.yaml` and write `out/costs.json` and `out/costs.md`. | table for the deck |

## Who does what
- **Builder (Santiago):** runs the pipeline with the coding agent; keys in `.env`; token/character logging; player page.
- **Editor (Vasco):** profile prompts for step 4; 3 clearly different ElevenLabs voices; check merges vs target lineups; listen to every briefing ("would I listen tomorrow?"); hand-check 15 figures; pick the caught mistake. Fix prompts, not code.
- **Pitch lead (Sousa):** deck (8 slides), cost model, newsroom-day + who-pays slides, the 3-minute video, rehearsals.

## Checkpoints
- Fri 16:30: verified facts exist for 18 Nov (steps 1–2).
- Fri 19:00: stories grouped; first Mara MP3 plays (steps 3–5).
- Fri 23:00: all 3 briefings play with sources linked; player page works; cost draft.
- Then sleep. Sat 06:30–07:30 fixes and real costs in. **07:30 freeze.** 07:30–09:00 video. **Submit by 10:00.**
- Running out of time: two polished listeners (Mara + Jordan) beat three half-done. Priya is cut first.

## Working rules for coding agents
- Small steps; run on the 10-article sample after each change and show the output.
- Never print full article text (headline + 200 chars max for debugging).
- No secrets in code; read `.env`. Never commit `data/`, `.env`, or root `out/` audio. The GitHub Pages demo may commit its checked MP3s and transcriptions, shared spoken facts and cost report under `docs/out/`, plus the player and QR.
- Commit small and often; `git pull` before starting.
