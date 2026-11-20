#!/usr/bin/env bash
# Receipts: automatic run for any day. Usage (from the repo root):  bash run_auto.sh 2026-11-17
# It copies the repo to ../receipts-auto so the 18 Nov demo (out/ and docs/) is never touched.
set -euo pipefail
DAY="${1:-2026-11-17}"
SRC="$(pwd)"; DST="$(dirname "$SRC")/receipts-auto"
[ -d "$DST" ] || { echo "Copying project to $DST (once)..."; rsync -a --exclude .git --exclude docs "$SRC/" "$DST/"; }
cp "$SRC/src/script.py" "$DST/src/script.py"
cd "$DST"
N=$( [ -f data/cache/costs.jsonl ] && wc -l < data/cache/costs.jsonl || echo 0 )
echo "Cost log starts at record $N"
python -m src.extract --date "$DAY" --overnight
python -m src.verify  --date "$DAY" --overnight
python -m src.cluster --date "$DAY" --threshold 0.45 --overnight
python -m src.script  --date "$DAY" --overnight --listener all --auto --regenerate
python -m src.audio   --listener all
python -m src.cost_report --since-record "$N"
echo; echo "DONE. Send these to the Editor: out/*/selection.json out/*/script.json out/costs.md"
