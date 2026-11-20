# A live wildcard briefing

**Finals: run `python -m src.live_server` and open http://localhost:8000.**

From the repository root on the finals laptop, leave the server running. Click **New listener**, paste the judges’ description, choose a language or leave **Auto** selected, and click **Create**. The panel shows the current step, elapsed time and API cost. When the edition is ready the player selects its tab and starts playback. If the browser asks for a gesture, press **Play**.

The public player contains Mara, Jordan and Priya. The finals server starts with those three and adds editions created with **New listener**. It stores the live editions and profiles under `out/live/` and loads them again on a normal restart. The server listens only on the laptop and runs one creation job at a time. The API keys come from its `.env`.

For a clean session, stop the process using port 8000 and run `python -m src.live_server --reset`. This moves the entire previous session, including its profiles and roster, into `out/live-archive/<UTC timestamp>/` and starts the server with an empty `out/live/`.

If voicing fails, the panel shows the error. Submit the same description and language again to reuse the profile, checked script and any saved ElevenLabs recording and timing. Mastering retries from that original recording, adjusting gain for loudness and the limiter for measured peak overshoot. A wildcard MP3 passes at −17 to −15 LUFS with a true peak below −1 dBTP and the original decoded sample count.

## PowerShell fallback

Stop the live server with Ctrl+C before using port 8000 for the static player. Start the player in one terminal from the repository root.

```powershell
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

For a separate command-line rehearsal, generate a local edition with `--no-publish`. The profile model infers the language from the description and defaults to English. Add `--language en`, `--language de` or `--language nl` to choose it explicitly.

```powershell
python -m src.wildcard "Dutch retail investor in Utrecht, holds ASML and some Bitcoin, wants a short briefing in Dutch" --language nl --no-publish
```

Use the local preview command under **Run options** to play this CLI edition. Each edition includes its transcript, figure receipts, article links, story groups and word-aligned audio. The command prints elapsed seconds and the cost of API calls for that invocation at the rates in `prices.yaml`.

## What to have on the laptop

Use the configured project environment and the licensed 18 November overnight cache in `data/cache/`. The checkout on GitHub contains the three core editions. Generating a new listener also requires the local article index, clusters, verified ledger, story scores, saved conflict checks and available source claims. Keep the existing small and large model settings in `.env` and set `ELEVENLABS_MODEL=eleven_multilingual_v2`. A new description needs working OpenAI and ElevenLabs credentials. The selected multilingual voice receives the requested language code. Optional `WILDCARD_VOICE_EN`, `WILDCARD_VOICE_DE` and `WILDCARD_VOICE_NL` settings accept a voice ID for that language.

The small model creates the profile and scores the cached stories against its interests and exclusions. The automatic script stage checks cited facts, numbers, repeats, conflicting readings and eight-word overlaps. Each figure carries its receipt’s time window in the sentence that speaks it. Language-specific rules and a separate small-model review check the window, trading advice and claims that buyers will return at a given price. A flagged sentence gets one repair and must pass again to reach the audio. German and Dutch figures are checked against the original verified ledger. A linked Invezz translation is included alongside its original when available.

The greeting and AI-voice disclosure each have their own karaoke line before the sourced news begins. For form submissions, the profile is saved in `out/live/profiles_wildcard.yaml`. Selection scores, script, validation details, playable audio and transcript are in `out/live/<id>/`.

## Run options

- `--dry-run` checks the script, skips ElevenLabs and prints a file URL for `out/<id>/dry-run/script.json`. The player roster and any previously published edition stay intact.
- `--no-publish` builds the playable edition under `out/<id>/`. Serve the repository root with `python -m http.server 8001 --bind 127.0.0.1` to open the local player URL it prints.

## Rehearsal results

All three editions below played through the local **New listener** form. Times are server job times. Costs are the recorded API charges for that submission.

| Listener | Form language | Job time | API cost | Verified figures |
| --- | --- | ---: | ---: | ---: |
| Maastricht pensioner, inflation and energy prices | Auto → Dutch | 19.0 s | $0.0000 | 6/6 |
| Same Dutch submission, completed edition cached | Auto → Dutch | <0.1 s | $0.0000 | 6/6 |
| Aachen bakery owner, energy bills and imported ingredients | German | 105.5 s | $0.2127 | 3/3 |
| Manchester bus operator, fuel prices, inflation and rates | English | 92.6 s | $0.2094 | 3/3 |

The Dutch recovery reused the recording from the original $0.2133 attempt and delivered it at −16.96 LUFS and −2.06 dBTP. The German and English runs generated fresh recordings. The German script finished eight words below its target minimum. The English script omitted its requested closing lead-in.

The local browser rehearsal used **Auto** and “Retired teacher in Leeds with a small pension in index funds, no crypto, calm, plain English”. It produced Anne’s English edition with 4/4 verified figures. The job took **81.3 s and $0.1759**. Playback started **81.9 s** after clicking Create.

| Listener | Published build | Cost of published build | All runs for this revision | Total API cost | Player duration | Verified figures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Noor, Dutch retail investor | 61.2 s | $0.1886 | 61.2 s | $0.1886 | 1:44 | 6/6 |
| Lena, German exporter | 24.9 s | $0.1582 | 166.3 s | $0.5574 | 1:42 | 3/3 |

Both runs reused the November 18 newsroom cache and the listener profiles and scores. Noor’s build generated a new script and recording. Her two Nvidia figures explicitly refer to the fourth quarter, her Bitcoin indicator to the daily chart, and her gold figure to the past week.

Lena’s first build took 86.8 s ($0.2094) and fell nine words below the profile minimum. The second took 54.6 s ($0.1898) and lost her sign-off when validation dropped the last draft sentence. The published build reused the checked news, restored the neutral sign-off and synthesized the final recording. Its 0.54% dollar-index gain is explicitly measured over the past five days, the tariff refund per share refers to the reported quarter, and the gold loss refers to the past week. Both published scripts passed without validation warnings. Each individual run came in under $0.50. The three German runs together cost $0.5574.
