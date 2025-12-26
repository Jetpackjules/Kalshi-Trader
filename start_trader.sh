#!/bin/bash
while true; do
    echo "Starting Live Trader V4..." >> live_trader_v4.log
    /home/jetpackjules/venv/bin/python -u /home/jetpackjules/live_trader_v4.py >> /home/jetpackjules/live_trader_v4.log 2>&1
    EXIT_CODE=$?
    echo "Trader exited with code=$EXIT_CODE. Restarting in 5s..." >> live_trader_v4.log
    sleep 5
done
