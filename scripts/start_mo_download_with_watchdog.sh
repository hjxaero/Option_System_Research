#!/usr/bin/env bash
# Start MO windowed download + self-healing watchdog together (single entrypoint).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source Normal/bin/activate

WORKERS="${WORKERS:-2}"
INTERVAL="${WATCHDOG_INTERVAL_SECONDS:-60}"
GRACE="${WATCHDOG_GRACE_SECONDS:-600}"
COOLDOWN="${WATCHDOG_RESTART_COOLDOWN_SECONDS:-60}"

BATCH_DIR="data_store/quality/MO/batch_10d"
LOG="$BATCH_DIR/full_history.log"
WATCHDOG_LOG="$BATCH_DIR/watchdog.log"

DOWNLOAD_CMD="cd $ROOT && source Normal/bin/activate && caffeinate -dims python scripts/build_windowed_four_term_minute_quotes.py \
  --start 2022-07-22 --end 2026-05-30 --window-days 10 \
  --workers $WORKERS --min-workers $WORKERS --auto-reduce-workers \
  --skip-complete --infer-first-valid \
  --first-valid-date-cache data_store/contracts/MO/first_valid_dates.json \
  2>&1 | tee -a $LOG"

mkdir -p "$BATCH_DIR"

# Avoid duplicate download/watchdog if already running.
if pgrep -f "build_windowed_four_term_minute_quotes.py" >/dev/null 2>&1; then
  echo "MO download already running; skip starting a second downloader."
else
  echo "Starting MO download (workers=$WORKERS) ..."
  nohup /bin/zsh -lc "$DOWNLOAD_CMD" >>"$LOG" 2>&1 &
  echo "download_pid=$!"
fi

if pgrep -f "monitor_mo_download_watchdog.py" >/dev/null 2>&1; then
  echo "Watchdog already running; skip starting a second watchdog."
else
  echo "Starting MO download watchdog ..."
  nohup python scripts/monitor_mo_download_watchdog.py \
    --interval-seconds "$INTERVAL" \
    --grace-seconds "$GRACE" \
    --auto-restart \
    --restart-after-window \
    --restart-cooldown-seconds "$COOLDOWN" \
    --restart-after-window-delay-seconds 2 \
    --restart-command "$DOWNLOAD_CMD" \
    >>"$WATCHDOG_LOG" 2>&1 &
  echo "watchdog_pid=$!"
fi

echo "logs: $LOG (download), $WATCHDOG_LOG (watchdog)"
