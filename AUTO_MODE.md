# Automatic mode (`--auto`): any day, no pins

`python -m src.script ... --auto` turns off everything we hand-wrote for 18 Nov:
- `editor_pins` (the regex lists of headlines) and Priya's `target_lineup`
- `include_articles`, `exclude_articles`, `lead_story`, `max_sentences` and `style_notes`
- the day-specific prompt lines (Anthropic as lead, Waller's 50bps, 33.2%, Bitcoin/XRP, Fed minutes, "Nvidia fell on Wednesday") and the checks that enforced them

These stay on, because they're general rules and not tied to a particular day:
- profiles (who, question, never, tone, words, voice settings), plus each listener's opener and closer
- scoring: `2*fit + 2*(extra outlets) + has verified figure + changes today`, with one story per topic and the `never` list excluded
- Priya's test: a story needs a concrete business consequence plus a verified figure
- every number checker, the repair-or-drop step, and the conflicts check

What's new in the output:
- `out/<listener>/selection.json`: **every** story with its score split into parts, and whether it was picked. That's the proof it's an algorithm.
- `script.json` now includes `"mode": "auto"` and `validation_warnings`. In auto mode, if the length comes out a bit short, the script is written with a warning rather than stopping the run.

## Run 17 Nov (in a COPY, so the 18 Nov demo stays as it is)
```sh
cp -r receipts receipts-auto        # Windows: copy the folder in Explorer
cd receipts-auto
wc -l data/cache/costs.jsonl         # write down this number = N
python -m src.extract --date 2026-11-17 --overnight
python -m src.verify  --date 2026-11-17 --overnight
python -m src.cluster --date 2026-11-17 --threshold 0.45 --overnight
python -m src.script  --date 2026-11-17 --overnight --listener all --auto --regenerate
python -m src.audio   --listener all
python -m src.cost_report --since-record N
```
For the pitch, also run 18 Nov with `--auto` in the same copy. Put it next to the editor version: same news, no human choices.

Estimated cost for one day, based on the run log and `prices.yaml`: about $1 in OpenAI and about $0.80 in ElevenLabs (around 8,000 characters).
