#!/usr/bin/env bash
# Sequential MO repair for windows 19-21 only. Do not run alongside build_windowed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source Normal/bin/activate

BATCH="data_store/quality/MO/batch_10d"
LOG="$BATCH/repair_w19_21_resume.log"
WORKERS="${WORKERS:-3}"

exec > >(tee -a "$LOG") 2>&1
echo "=== MO windows 19-21 repair resume $(date -Iseconds) workers=$WORKERS ==="

echo "=== Window 19: repair plan (remaining 16 symbols) ==="
python scripts/repair_minute_quotes_from_plan.py \
  --plan "$BATCH/window19_repair_plan_remaining.csv" \
  --workers "$WORKERS" \
  --report-prefix MO_20230118_20230127_repair2 \
  --output-dir "$BATCH"

echo "=== Window 20: retry 5 symbols ==="
python scripts/build_month_four_term_minute_quotes.py \
  --start 2023-01-28 --end 2023-02-06 \
  --product MO \
  --symbols-file "$BATCH/window20_repair_remaining.txt" \
  --workers "$WORKERS" \
  --no-skip-complete \
  --retry-attempts 3 \
  --retry-sleep-seconds 3.0 \
  --report-prefix MO_20230128_20230206_retry2 \
  --output-dir "$BATCH" \
  --first-valid-date-cache data_store/contracts/MO/first_valid_dates.json

echo "=== Window 21: retry 9 symbols ==="
python scripts/build_month_four_term_minute_quotes.py \
  --start 2023-02-07 --end 2023-02-16 \
  --product MO \
  --symbols-file "$BATCH/window21_repair_remaining.txt" \
  --workers "$WORKERS" \
  --no-skip-complete \
  --retry-attempts 3 \
  --retry-sleep-seconds 3.0 \
  --report-prefix MO_20230207_20230216_retry2 \
  --output-dir "$BATCH" \
  --first-valid-date-cache data_store/contracts/MO/first_valid_dates.json

echo "=== Done $(date -Iseconds) ==="
