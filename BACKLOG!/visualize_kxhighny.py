import argparse
from pathlib import Path
from typing import List, Optional

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def make_candlestick_figure(ticker: str, df: pd.DataFrame) -> go.Figure:
    # Moving averages on close
    df = df.copy()
    df["ma20"] = df["close"].rolling(20, min_periods=1).mean()
    df["ma50"] = df["close"].rolling(50, min_periods=1).mean()

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        row_heights=[0.78, 0.22],
        vertical_spacing=0.03,
        subplot_titles=(f"{ticker} — Price", "Volume (count per candle)"),
    )

    fig.add_trace(
        go.Candlestick(
            x=df["start_dt"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            increasing_line_color="#16a34a",
            decreasing_line_color="#ef4444",
            increasing_fillcolor="#16a34a",
            decreasing_fillcolor="#ef4444",
            name="Price",
            hovertext=None,
            hoverinfo="x+y",
            showlegend=False,
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df["start_dt"],
            y=df["ma20"],
            mode="lines",
            name="MA20",
            line=dict(color="#2563eb", width=1.5),
            hovertemplate="MA20: %{y:.2f}¢<extra></extra>",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter(
            x=df["start_dt"],
            y=df["ma50"],
            mode="lines",
            name="MA50",
            line=dict(color="#7c3aed", width=1.5),
            hovertemplate="MA50: %{y:.2f}¢<extra></extra>",
        ),
        row=1,
        col=1,
    )

    # Volume bars from `count` if available
    vol = df.get("count") if "count" in df.columns else None
    if vol is not None:
        fig.add_trace(
            go.Bar(
                x=df["start_dt"],
                y=vol,
                name="Volume",
            marker_color="#94a3b8",
            hovertext=None,
            hoverinfo="x+y",
            ),
            row=2,
            col=1,
        )

    fig.update_layout(
        title=f"{ticker} — Candlesticks",
        xaxis_title="",
        xaxis2_title="Time (UTC)",
        yaxis_title="Price (¢)",
        yaxis2_title="Count",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        font=dict(size=12),
        margin=dict(l=60, r=20, t=70, b=50),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#f1f5f9")
    fig.update_yaxes(showgrid=True, gridcolor="#f1f5f9")
    return fig


def build_index_html(outdir: Path, generated_files: List[Path]) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    cards = []
    for p in generated_files:
        preview = (outdir / "previews" / (p.stem + ".png")).name
        cards.append(
            f"<a class=card href=\"{p.name}\" target=\"_blank\">"
            f"<img src=\"previews/{p.stem}.png\" alt=\"{p.stem}\"/>"
            f"<div class=title>{p.stem}</div>"
            f"</a>"
        )
    grid = "\n".join(cards)

    html = f"""
<!doctype html>
<html>
  <head>
    <meta charset="utf-8"/>
    <title>KXHIGHNY Candlestick Charts</title>
    <style>
      body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; margin: 24px; }}
      h1 {{ margin-bottom: 8px; }}
      p {{ color: #555; }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
        gap: 16px;
        margin-top: 16px;
      }}
      .card {{
        display: block;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        overflow: hidden;
        text-decoration: none;
        color: inherit;
        background: #fff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      }}
      .card img {{ width: 100%; height: 180px; object-fit: cover; background: #f8fafc; }}
      .card .title {{ padding: 10px 12px; font-weight: 600; font-size: 14px; }}
    </style>
  </head>
  <body>
    <h1>KXHIGHNY Candlestick Charts</h1>
    <p>Click a preview to open the interactive chart in a new tab.</p>
    <div class="grid">
      {grid}
    </div>
  </body>
</html>
"""
    (outdir / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Visualize KXHIGHNY candle CSV as Plotly candlesticks")
    parser.add_argument("--csv", default="data/candles/KXHIGHNY_candles_5m.csv", help="Path to candle CSV")
    parser.add_argument("--outdir", default="figures", help="Output directory for charts")
    parser.add_argument("--ticker", default=None, help="Specific ticker to plot (exact match). If not set, uses --top.")
    parser.add_argument("--top", type=int, default=12, help="If --ticker not set, plot top-N tickers by total candle count")
    parser.add_argument("--days", type=int, default=60, help="Limit to the last N days for plotting")
    args = parser.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.csv)
    if not {"ticker", "start", "open", "high", "low", "close"}.issubset(df.columns):
        raise SystemExit("CSV is missing required columns: ticker,start,open,high,low,close")

    # Parse times
    df["start_dt"] = pd.to_datetime(df["start"], utc=True)
    latest_ts = df["start_dt"].max()
    if pd.notna(latest_ts) and args.days > 0:
        cutoff = latest_ts - pd.Timedelta(days=args.days)
        df = df[df["start_dt"] >= cutoff]

    generated: List[Path] = []

    if args.ticker:
        tickers: List[str] = [args.ticker]
    else:
        # Pick top tickers by total candle count (rows) in the filtered frame
        tickers = (
            df.groupby("ticker")["start"].count().sort_values(ascending=False).head(args.top).index.tolist()
        )

    preview_dir = outdir / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)

    for ticker in tickers:
        tdf = df[df["ticker"] == ticker].sort_values("start_dt")
        if tdf.empty:
            continue
        fig = make_candlestick_figure(ticker, tdf)
        outfile_html = outdir / f"{ticker}_candles.html"
        fig.write_html(str(outfile_html), include_plotlyjs="cdn")
        generated.append(outfile_html)

        # Thumbnail preview
        try:
            png_bytes = fig.to_image(format="png", width=900, height=500, scale=2)
            (preview_dir / f"{outfile_html.stem}.png").write_bytes(png_bytes)
        except Exception as _:
            pass

    if generated:
        build_index_html(outdir, generated)
        print(f"Wrote {len(generated)} charts to {outdir}. Open index.html for links.")
    else:
        print("No charts generated (no matching tickers).")


if __name__ == "__main__":
    main()

