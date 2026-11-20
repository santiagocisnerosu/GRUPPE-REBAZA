# A live wildcard briefing

Start the player in one terminal on the finals laptop, from the repository root. Leave it running while the judges describe their listener.

```powershell
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

In a second terminal at the same location, paste the judge’s paragraph between the quotes. The profile model infers the language from the description and defaults to English. Add `--language en`, `--language de` or `--language nl` to choose it explicitly.

```powershell
python -m src.wildcard "Dutch retail investor in Utrecht, holds ASML and some Bitcoin, wants a short briefing in Dutch" --language nl
```

Open the URL printed at the end. It goes directly to the listener and works as soon as the command finishes. Refresh an already-open player to load the updated roster. Each published edition includes its transcript, figure receipts, article links, story groups and word-aligned audio. The command prints elapsed seconds and the cost of API calls for that invocation at the rates in `prices.yaml`. Publishing a new live edition to GitHub Pages requires deploying the updated `docs/` tree.

The second rehearsal used this command.

```powershell
python -m src.wildcard "German Mittelstand exporter worried about the dollar and tariffs, in German" --language de
```

## What to have on the laptop

Use the configured project environment and the licensed 18 November overnight cache in `data/cache/`. The checkout on GitHub contains the five playable editions. Generating a new listener also requires the local article index, clusters, verified ledger, story scores, saved conflict checks and available source claims. Keep the existing small and large model settings in `.env` and set `ELEVENLABS_MODEL=eleven_multilingual_v2`. A new description needs working OpenAI and ElevenLabs credentials. The selected multilingual voice receives the requested language code. Optional `WILDCARD_VOICE_EN`, `WILDCARD_VOICE_DE` and `WILDCARD_VOICE_NL` settings accept a voice ID for that language.

The small model creates the profile and scores the cached stories against its interests and exclusions. The automatic script stage checks cited facts, numbers, repeats, conflicting readings and eight-word overlaps. Each figure carries its receipt’s time window in the sentence that speaks it. Language-specific rules and a separate small-model review check the window, trading advice and claims that buyers will return at a given price. A flagged sentence gets one repair and must pass again to reach the audio. German and Dutch figures are checked against the original verified ledger. A linked Invezz translation is included alongside its original when available.

The greeting and AI-voice disclosure each have their own karaoke line before the sourced news begins. The profile is saved in `profiles_wildcard.yaml`. Selection scores, the script and validation details are in `out/<id>/`. The playable audio, public transcript and listener manifest go to `docs/out/`.

## Run options

- `--dry-run` checks the script, skips ElevenLabs and prints a file URL for `out/<id>/dry-run/script.json`. The player roster and any previously published edition stay intact.
- `--no-publish` builds the playable edition under `out/<id>/`. Serve the repository root with `python -m http.server 8001 --bind 127.0.0.1` to open the local player URL it prints.

## Rehearsal results

| Listener | Published build | Cost of published build | All runs for this revision | Total API cost | Player duration | Verified figures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Noor, Dutch retail investor | 61.2 s | $0.1886 | 61.2 s | $0.1886 | 1:44 | 6/6 |
| Lena, German exporter | 24.9 s | $0.1582 | 166.3 s | $0.5574 | 1:42 | 3/3 |

Both runs reused the November 18 newsroom cache and the listener profiles and scores. Noor’s build generated a new script and recording. Her two Nvidia figures explicitly refer to the fourth quarter, her Bitcoin indicator to the daily chart, and her gold figure to the past week.

Lena’s first build took 86.8 s ($0.2094) and fell nine words below the profile minimum. The second took 54.6 s ($0.1898) and lost her sign-off when validation dropped the last draft sentence. The published build reused the checked news, restored the neutral sign-off and synthesized the final recording. Its 0.54% dollar-index gain is explicitly measured over the past five days, the tariff refund per share refers to the reported quarter, and the gold loss refers to the past week. Both published scripts passed without validation warnings. Each individual run came in under $0.50. The three German runs together cost $0.5574.

[Play Noor’s Dutch briefing](https://santiagocisnerosu.github.io/GRUPPE-REBAZA/?listener=wildcard-nl-d652f44272a8) · [Play Lena’s German briefing](https://santiagocisnerosu.github.io/GRUPPE-REBAZA/?listener=wildcard-de-ca762d040743)
