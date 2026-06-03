#!/usr/bin/env bash
# Log pool worker vs orphan (PPID=1) counts while MO download runs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="${1:-$ROOT/data_store/quality/MO/batch_10d/orphan_monitor.log}"
INTERVAL="${ORPHAN_MONITOR_INTERVAL_SECONDS:-30}"
PATTERN="${ROOT}/Normal/bin/python -c from multiprocessing"

mkdir -p "$(dirname "$LOG")"
echo "$(date '+%Y-%m-%dT%H:%M:%S%z') orphan_monitor start interval=${INTERVAL}s log=$LOG" >>"$LOG"

while true; do
  download_procs=0
  while IFS= read -r _; do
    download_procs=$((download_procs + 1))
  done < <(pgrep -f "build_windowed_four_term_minute_quotes.py|build_month_four_term_minute_quotes.py" 2>/dev/null || true)
  pool_workers=0
  orphan_workers=0
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    pid="${line%% *}"
    rest="${line#"$pid" }"
    ppid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
    pool_workers=$((pool_workers + 1))
    if [[ "$ppid" == "1" ]]; then
      orphan_workers=$((orphan_workers + 1))
      echo "  orphan pid=${pid} ${rest}" >>"$LOG"
    fi
  done < <(pgrep -fl "$PATTERN" 2>/dev/null || true)

  echo "$(date '+%Y-%m-%dT%H:%M:%S%z') download_procs=${download_procs} pool_workers=${pool_workers} orphan_workers=${orphan_workers}" >>"$LOG"
  if [[ "$orphan_workers" -gt 0 ]]; then
    pgrep -fl "$PATTERN" 2>/dev/null | while IFS= read -r line; do
      pid="${line%% *}"
      ppid="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')"
      [[ "$ppid" == "1" ]] && echo "  $line" >>"$LOG"
    done
  fi
  sleep "$INTERVAL"
done
