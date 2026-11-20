# Receipts: automatic run for any day. Usage (PowerShell, from the repo root):
#   powershell -ExecutionPolicy Bypass -File run_auto.ps1 2026-11-17
# It copies the repo to ..\receipts-auto so the 18 Nov demo (out\ and docs\) is never touched.
param([string]$Day = "2026-11-17")
$ErrorActionPreference = "Stop"
$src = (Get-Location).Path
$dst = Join-Path (Split-Path $src -Parent) "receipts-auto"
if (-not (Test-Path $dst)) {
  Write-Host "Copying project to $dst (once)..."
  robocopy $src $dst /E /XD .git docs /NFL /NDL /NJH /NJS | Out-Null
}
Copy-Item "$src\src\script.py" "$dst\src\script.py" -Force
Set-Location $dst
$N = if (Test-Path data\cache\costs.jsonl) { (Get-Content data\cache\costs.jsonl | Measure-Object -Line).Lines } else { 0 }
Write-Host "Cost log starts at record $N"
python -m src.extract --date $Day --overnight;                                   if ($LASTEXITCODE) { exit 1 }
python -m src.verify  --date $Day --overnight;                                   if ($LASTEXITCODE) { exit 1 }
python -m src.cluster --date $Day --threshold 0.45 --overnight;                  if ($LASTEXITCODE) { exit 1 }
python -m src.script  --date $Day --overnight --listener all --auto --regenerate; if ($LASTEXITCODE) { exit 1 }
python -m src.audio   --listener all;                                            if ($LASTEXITCODE) { exit 1 }
python -m src.cost_report --since-record $N
Write-Host "`nDONE. Send these to the Editor: out\mara\selection.json out\jordan\selection.json out\priya\selection.json out\*\script.json out\costs.md"
