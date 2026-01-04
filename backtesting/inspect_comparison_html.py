from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path
from typing import TypeGuard


def _finite_number(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not (math.isnan(value) or math.isinf(value))


def _extract_trace_y(html: str, trace_name: str) -> list[object] | None:
    """Extract the y-array for a Plotly trace by its name from an HTML file.

    This is a lightweight parser that avoids needing Plotly installed.
    """
    # Common encodings we might see in the HTML payload.
    needles = [
        f'"name":"{trace_name}"',
        f'\\"name\\":\\"{trace_name}\\"',
    ]

    idx = -1
    for needle in needles:
        idx = html.find(needle)
        if idx != -1:
            break
    if idx == -1:
        return None

    y_key = html.find('"y":', idx)
    if y_key == -1:
        y_key = html.find('\\"y\\":', idx)
        if y_key == -1:
            return None

    start = html.find('[', y_key)
    if start == -1:
        return None

    depth = 0
    end = None
    for i in range(start, len(html)):
        c = html[i]
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        return None

    raw = html[start:end]

    # Normalize JavaScript literals to JSON where needed.
    # Plotly payloads typically already use JSON ('null' not 'None'), but keep this safe.
    raw = raw.replace('NaN', 'null').replace('Infinity', 'null').replace('-Infinity', 'null')

    try:
        parsed = json.loads(raw)
    except Exception:
        return None

    return parsed if isinstance(parsed, list) else None


def main() -> None:
    html_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('backtest_charts/comparison_highbudget_100.html')
    html = html_path.read_text(encoding='utf-8', errors='ignore')

    # Collect trace names that look like hb_*, v3_*, meta_* or the default Meta label
    # (both escaped/unescaped versions).
    name_patterns = [
        r'"name"\s*:\s*"((?:hb_|v3_|meta_)[^"]+)"',
        r'\\"name\\"\s*:\s*\\"((?:hb_|v3_|meta_)[^\\"]+)\\"',
        r'"name"\s*:\s*"(Algo 3: Regime Switcher \(Meta\))"',
        r'\\"name\\"\s*:\s*\\"(Algo 3: Regime Switcher \(Meta\))\\"',
    ]

    found: set[str] = set()
    for pat in name_patterns:
        found.update(re.findall(pat, html))

    # Base strategy traces are hb_* or v3_*; daily returns are "{name} daily %".
    strategies = sorted({n for n in found if not n.endswith(' daily %')})

    rows: list[tuple[str, float, int, int, int, int]] = []
    for strat in strategies:
        equity = _extract_trace_y(html, strat)
        daily = _extract_trace_y(html, f'{strat} daily %')
        if not equity or not daily:
            continue

        final_equity = next((v for v in reversed(equity) if _finite_number(v)), None)
        if final_equity is None:
            continue

        pos = sum(1 for v in daily if _finite_number(v) and v > 0)
        neg = sum(1 for v in daily if _finite_number(v) and v < 0)
        zero = sum(1 for v in daily if _finite_number(v) and v == 0)
        tot = pos + neg + zero
        rows.append((strat, float(final_equity), pos, neg, zero, tot))

    if not rows:
        raise SystemExit('No hb_/v3_ traces parsed from HTML (unexpected format?).')

    rows_by_final = sorted(rows, key=lambda t: t[1], reverse=True)
    rows_by_pos = sorted(rows, key=lambda t: (t[2], t[1]), reverse=True)

    print('Final equity ranking (from existing HTML):')
    for strat, final_eq, pos, neg, zero, tot in rows_by_final:
        print(
            f'  {strat:14s} final=${final_eq:8.2f} | +days={pos:2d} -days={neg:2d} 0days={zero:2d} (n={tot})'
        )

    best_final = rows_by_final[0]
    best_pos = rows_by_pos[0]

    print('\nWinners:')
    print(f'  Best final equity: {best_final[0]} (${best_final[1]:.2f})')
    print(f'  Most +daily days:  {best_pos[0]} ({best_pos[2]}/{best_pos[5]} positive days; final=${best_pos[1]:.2f})')


if __name__ == '__main__':
    main()
