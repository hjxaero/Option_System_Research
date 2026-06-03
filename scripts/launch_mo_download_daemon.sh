#!/usr/bin/env bash
# Thin wrapper: delegate to the Python launcher which fully detaches the
# download/watchdog/orphan-monitor into a new session (macOS has no setsid).
# Pass --restart to kill existing download + orphan workers before relaunch.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/Normal/bin/python" "$ROOT/scripts/launch_mo_download_daemon.py" "$@"
