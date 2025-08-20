#!/usr/bin/env bash
# run_no_strategy_bot.sh
# Wrapper script for cron to execute no_strategy_bot.py
#
# Add the following line to your crontab (crontab -e):
# * * * * * /usr/bin/env bash /path/to/run_no_strategy_bot.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/no_strategy_bot.log"

cd "$SCRIPT_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"
$PYTHON_BIN no_strategy_bot.py >> "$LOG_FILE" 2>&1
