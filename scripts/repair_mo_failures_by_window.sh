#!/usr/bin/env bash
# Retry MO download failures per 10-day window (from batch_10d/*_failures.csv).
# Do NOT run alongside build_windowed (Tq FileLock).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source Normal/bin/activate

BATCH="data_store/quality/MO/batch_10d"
LOG="${LOG:-$BATCH/repair_by_window.log}"
WORKERS="${WORKERS:-2}"
FROM_WINDOW="${FROM_WINDOW:-1}"

exec > >(tee -a "$LOG") 2>&1
echo "=== MO failures-by-window repair $(date -Iseconds) workers=$WORKERS from_window=$FROM_WINDOW ==="

WINDOW_LIST="$BATCH/repair_by_window_list.tsv"
python3 - <<'PY' >"$WINDOW_LIST"
import csv
from pathlib import Path

batch = Path("data_store/quality/MO/batch_10d")
for p in sorted(batch.glob("MO_*_failures.csv")):
    if "retry" in p.name or p.name.endswith(".resolved.csv"):
        continue
    body = p.stem.replace("_failures", "").replace("MO_", "")
    ws_raw, we_raw = body.split("_")
    ws = f"{ws_raw[:4]}-{ws_raw[4:6]}-{ws_raw[6:8]}"
    we = f"{we_raw[:4]}-{we_raw[4:6]}-{we_raw[6:8]}"
    retry = batch / f"MO_{ws_raw}_{we_raw}_retry_failures.csv"
    src = retry if retry.exists() else p
    syms = sorted(
        {(row.get("symbol") or "").strip() for row in csv.DictReader(src.open(encoding="utf-8-sig"))} - {""}
    )
    if syms:
        print(f"{ws}\t{we}\t{len(syms)}\t{src}")
PY

total=$(wc -l <"$WINDOW_LIST" | tr -d ' ')
idx=0
while IFS=$'\t' read -r START END NSYMS SRC; do
  idx=$((idx + 1))
  if (( idx < FROM_WINDOW )); then
    continue
  fi
  TAG="${START//-/}_${END//-/}"
  SYM_FILE="$BATCH/repair_symbols_${TAG}.txt"
  python3 - <<PY
import csv
from pathlib import Path
src = Path("$SRC")
out = Path("$SYM_FILE")
syms = sorted({(r.get("symbol") or "").strip() for r in csv.DictReader(src.open(encoding="utf-8-sig"))} - {""})
out.write_text("\n".join(syms) + ("\n" if syms else ""), encoding="utf-8")
print(f"symbols_file={out} count={len(syms)} source={src.name}")
PY

  echo "--- [$idx/$total] window $START .. $END ($NSYMS symbols, source=$(basename "$SRC")) ---"
  python scripts/build_month_four_term_minute_quotes.py \
    --start "$START" \
    --end "$END" \
    --product MO \
    --symbols-file "$SYM_FILE" \
    --workers "$WORKERS" \
    --no-skip-complete \
    --retry-attempts 3 \
    --retry-sleep-seconds 3.0 \
    --report-prefix "MO_${TAG}_failures_retry" \
    --output-dir "$BATCH" \
    --first-valid-date-cache data_store/contracts/MO/first_valid_dates.json

  python3 scripts/sync_mo_window_failures.py --window-tag "$TAG" --batch-dir "$BATCH"
done <"$WINDOW_LIST"

echo "=== Done $(date -Iseconds) ==="
