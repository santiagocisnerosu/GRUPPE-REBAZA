# Receipts: a morning audio briefing where every number is checked against its source

Team GRUPPE REBAZA · MAIN AI Hackathon 2026 · Sourcera track
One-line pitch: "A briefing you can trust by ear, at a cost a newsroom can carry every morning."

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
| 4 | `src/script.py` | small + strong | Cache per-listener fit and urgency by story ID. Rank by twice fit, outlet diversity, verified figures and urgency, with one slot per topic. Add five points for editor pins in `profiles.yaml` and report unmatched pin components. Screen Priya's stories for a concrete business consequence and a verified figure. Extract and check qualitative source claims only for selected articles. Detect competing readings with `src/conflicts.py` and log which figures were spoken in `data/cache/conflicts.json`. Write `out/<listener>/script.json` with sentences, fact IDs and article IDs. Check cited numbers, reject repeats and number-led sentences, cap each sentence at three figures, check repeated meanings and copied runs of 8 words, and target the profile budget within 10%. Repair once or drop; log issues in `out/<listener>/caught.json`. Export shared spoken facts to `out/shared_facts.json` and Mara's source ledger to `out/mara/facts_for_agent.md`. | 3 scripts, every retained sentence passes the checks |
| 5 | `src/audio.py` | ElevenLabs | Text-to-speech **with timestamps**, one voice per listener (see profiles). Output `out/<listener>/briefing.mp3` + `transcript.json` (sentences, start/end, source ids, headline, outlet, link). Cache by script hash. | MP3 plays |
| – | `web/player.html` | none | Listener switcher, audio, current sentence highlighted, clickable source chips (outlet + headline → link), counter "X of X figures verified", panel with the caught mistakes. Must look good on a projector. | demo-ready |
| – | `src/costs.py` | none | Report: one briefing, full 1,740-article dataset, 10× volume. Extraction is per article, scripts/audio per listener; at scale, audio segments per story are recorded once per tone and stitched, so audio grows with stories, not listeners. Prices from `prices.yaml` (from our dashboards). | table for the deck |

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
- No secrets in code; read `.env`. Never commit `data/`, `.env`, `out/` audio.
- Commit small and often; `git pull` before starting.
