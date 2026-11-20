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

The small model creates the profile and scores the cached stories against its interests and exclusions. The automatic script stage checks cited facts, numbers, repeats, conflicting readings and eight-word overlaps. German and Dutch figures are checked against the original verified ledger. A linked Invezz translation is included alongside its original when available. The resulting profile is saved in `profiles_wildcard.yaml`. Selection scores, the script and validation details are in `out/<id>/`. Only the playable audio, public transcript and listener manifest go to `docs/out/`.

## Run options

- `--dry-run` checks the script, skips ElevenLabs and prints a file URL for `out/<id>/dry-run/script.json`. The player roster and any previously published edition stay intact.
- `--no-publish` builds the playable edition under `out/<id>/`. Serve the repository root with `python -m http.server 8001 --bind 127.0.0.1` to open the local player URL it prints.

## Rehearsal results

| Listener | Final build | Final build cost | All rehearsal attempts | Total rehearsal cost | Audio | Verified figures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Noor, Dutch retail investor | 25.5 s | $0.1526 | 92.2 s | $0.3312 | 1:44 | 8/8 |
| Lena, German exporter | 19.8 s | $0.0000 | 101.6 s | $0.2188 | 1:51 | 4/4 |

Both initial runs stopped at a timestamp conversion during story ranking. The retries reused the profile and fit responses. The first complete runs took 47.5 s ($0.1674) for Dutch and 64.6 s ($0.2079) for German. After the number checker was refined, the final Dutch build synthesized revised narration and the German build reused its cached recording. The table sums processing time and recorded costs through delivery, including the failed attempts.

As a final check, the two commands above reproduced every published file byte for byte. Measured from process launch to exit, the fully cached replays took 26.4 s for Dutch and 26.8 s for German at $0.0000 each. A new judge-supplied description will need fresh profile, fit, script and voice calls.

[Play Noor’s Dutch briefing](https://santiagocisnerosu.github.io/GRUPPE-REBAZA/?listener=wildcard-nl-d652f44272a8) · [Play Lena’s German briefing](https://santiagocisnerosu.github.io/GRUPPE-REBAZA/?listener=wildcard-de-ca762d040743)
