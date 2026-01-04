"""Compatibility wrapper.

Snapshot replay is now a mode of the modular runner (same engine, same strategy factories).

Use:
  python -m backtesting.runner --snapshot ... --strategy module:symbol
"""

from __future__ import annotations

from backtesting.runner import main


if __name__ == "__main__":
    raise SystemExit(int(main()))
