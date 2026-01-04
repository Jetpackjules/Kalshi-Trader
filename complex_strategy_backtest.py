"""Compatibility shim.

The backtesting engine moved to backtesting/engine.py.

- New import path (preferred): `from backtesting.engine import ComplexBacktester`
- Old import path (kept for compatibility): `import complex_strategy_backtest`

This file intentionally contains no backtesting logic.
"""

from __future__ import annotations

from backtesting.engine import *  # noqa: F403
