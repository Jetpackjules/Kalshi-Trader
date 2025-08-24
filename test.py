import React, { useEffect, useRef, useState } from "react";
import { ResponsiveContainer, ComposedChart, Line, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ErrorBar } from "recharts";

/**
 * Kalshi NYC Max Temp – Jul 27 Market Viewer (v5, LOCKED + Charts + Dark UI)
 * ----------------------------------------------------------------
 * Adds intraday charts for each market:
 *  - Line chart from trade tape (price over time)
 *  - Candlestick chart from OHLC candles (1‑minute or 1‑hour)
 *
 * Notes:
 *  - Uses public endpoints; still CORS-fallback capable.
 *  - Event is LOCKED to KXHIGHNY-25JUL27 as requested.
 */

// ---- CONFIG ----
const LOCKED_EVENT_TICKER = "KXHIGHNY-25JUL27"; // always lock, per user preference
const LOCKED_SERIES = "KXHIGHNY";

// Official public API bases (both serve ALL markets)
const API_BASES = [
  "https://api.elections.kalshi.com/trade-api/v2",
  "https://trading-api.kalshi.com/trade-api/v2",
];

// Known generic CORS relays to try as fallbacks (best-effort)
const RELAYS = [
  (url) => `https://cors.isomorphic-git.org/${url}`,
  (url) => `https://thingproxy.freeboard.io/fetch/${url}`,
  (url) => `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`,
  (url) => `https://api.allorigins.workers.dev/raw?url=${encodeURIComponent(url)}`,
  (url) => `https://corsproxy.io/?${encodeURIComponent(url)}`,
  (url) => `https://yacdn.org/serve/${encodeURIComponent(url)}`,
  (url) => `https://r.jina.ai/http://${url.replace(/^https?:\/\//, "")}`,
  (url) => `https://r.jina.ai/https://${url.replace(/^https?:\/\//, "")}`,
];

// Proxy presets for quick testing
const PROXY_PRESETS = [
  { label: "(none)", value: "" },
  { label: "cors.isomorphic-git.org", value: "https://cors.isomorphic-git.org/" },
  { label: "thingproxy.freeboard.io", value: "https://thingproxy.freeboard.io/fetch/" },
  { label: "corsproxy.io", value: "https://corsproxy.io/?" },
  { label: "allorigins (workers)", value: "https://api.allorigins.workers.dev/raw?url=" },
  { label: "yacdn", value: "https://yacdn.org/serve/" },
  { label: "r.jina.ai (http)", value: "https://r.jina.ai/http://" },
  { label: "r.jina.ai (https)", value: "https://r.jina.ai/https://" },
];

function parseRangeOrder(title) {
  try {
    const t = String(title || "").replaceAll(",", "").toUpperCase();
    const m1 = t.match(/(\d+)\s*°?F\s*OR\s*HIGHER/);
    if (m1) return { low: Number(m1[1]), high: Infinity };
    const m2 = t.match(/(\d+)\s*-\s*(\d+)\s*°?F/);
    if (m2) return { low: Number(m2[1]), high: Number(m2[2]) };
    const m3 = t.match(/(\d+)\s*°?F\s*OR\s*BELOW/);
    if (m3) return { low: -Infinity, high: Number(m3[1]) };
  } catch {}
  return { low: Number.NEGATIVE_INFINITY, high: Number.NEGATIVE_INFINITY };
}

function formatUSDcents(c) {
  if (c == null || Number.isNaN(c)) return "—";
  return `${c}¢`;
}

function downloadCSV(filename, rows) {
  if (!rows.length) return;
  const header = Object.keys(rows[0] || {}).join(",");
  const body = rows
    .map((r) =>
      Object.values(r)
        .map((v) => {
          const s = String(v ?? "");
          if (s.includes(",") || s.includes("\n") || s.includes('"')) {
            return '"' + s.replaceAll('"', '""') + '"';
          }
          return s;
        })
        .join(",")
    )
    .join("\n");
  const csv = header + "\n" + body;
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function unique(arr) { return Array.from(new Set(arr)); }

function buildCandidates(path, userProxy) {
  const rawUrls = API_BASES.map((b) => `${b}${path}`);
  const urls = [...rawUrls];
  const proxy = (userProxy || "").trim();
  if (proxy) {
    rawUrls.forEach((u) => {
      if (proxy.endsWith("/")) urls.unshift(proxy + u);
      else urls.unshift(proxy + (proxy.includes("?") ? "&url=" : "?url=") + encodeURIComponent(u));
    });
  }
  rawUrls.forEach((u) => RELAYS.forEach((fn) => urls.push(fn(u))));
  return unique(urls);
}

async function fetchJSONWithFallback(path, { proxyHint, timeoutMs = 12000, diagCollector } = {}) {
  const candidates = buildCandidates(path, proxyHint);
  const errors = [];
  for (const candidate of candidates) {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort("timeout"), timeoutMs);
      const res = await fetch(candidate, {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "omit",
        mode: "cors",
        signal: ctrl.signal,
      });
      clearTimeout(t);
      if (!res.ok) { errors.push(`${candidate} → HTTP ${res.status}`); continue; }
      const text = await res.text();
      try {
        const json = JSON.parse(text);
        if (diagCollector) diagCollector(`OK ${candidate}`);
        return json;
      } catch (e) {
        if (text && text.trim().startsWith("{")) {
          const json = JSON.parse(text);
          if (diagCollector) diagCollector(`OK(text) ${candidate}`);
          return json;
        }
        errors.push(`${candidate} → Invalid JSON`);
      }
    } catch (err) {
      errors.push(`${candidate} → ${err?.name || "Error"}${err?.message ? ": " + err.message : ""}`);
    }
  }
  const error = new Error("All fetch attempts failed");
  error.details = errors;
  throw error;
}

// --- Time helpers ---
const MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
function parseLockedEventDate(ticker) {
  // KXHIGHNY-25JUL27 -> 2025-07-27 UTC bounds
  const m = ticker.match(/-(\d{2})([A-Z]{3})(\d{2})$/);
  if (!m) return null;
  const yy = Number(m[1]);
  const y = 2000 + yy;
  const mon = MONTHS.indexOf(m[2]);
  const dd = Number(m[3]);
  if (mon < 0) return null;
  const start = Date.UTC(y, mon, dd, 0, 0, 0) / 1000;
  const end = Date.UTC(y, mon, dd, 23, 59, 59) / 1000;
  return { start_ts: start, end_ts: end };
}

// --- OFFLINE SNAPSHOT SUPPORT ---
function tryParseJSON(s) { try { return JSON.parse(s); } catch { return null; } }

export default function KalshiNYCJul27Viewer() {
  // --- UI State ---
  const [proxyPreset, setProxyPreset] = useState(PROXY_PRESETS[0].value);
  const [proxyHint, setProxyHint] = useState(PROXY_PRESETS[0].value);

  // --- Data State ---
  const [series, setSeries] = useState(null);
  const [event, setEvent] = useState(null);
  const [markets, setMarkets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [expanded, setExpanded] = useState({}); // orderbooks
  const [chartState, setChartState] = useState({}); // ticker -> {loading, err, mode, candles[], trades[]}
  const [diag, setDiag] = useState({ attempts: [], lastOK: "" });

  // Offline mode inputs
  const [offlineMarketsJSON, setOfflineMarketsJSON] = useState("");
  const [offlineEventJSON, setOfflineEventJSON] = useState("");
  const [offlineSeriesJSON, setOfflineSeriesJSON] = useState("");

  const firstLoadRef = useRef(false);

  const eventTicker = LOCKED_EVENT_TICKER;

  async function loadAll() {
    setLoading(true);
    setErr("");
    setDiag({ attempts: [], lastOK: "" });

    const pushAttempt = (a) => setDiag((d) => ({ ...d, attempts: [a, ...d.attempts] }));

    try {
      // Probe exchange status first to find a working base/relay
      await fetchJSONWithFallback(`/exchange/status`, { proxyHint, diagCollector: pushAttempt });

      const [seriesData, eventData, marketsData] = await Promise.all([
        fetchJSONWithFallback(`/series/${LOCKED_SERIES}`, { proxyHint, diagCollector: pushAttempt }),
        fetchJSONWithFallback(`/events/${encodeURIComponent(eventTicker)}`, { proxyHint, diagCollector: pushAttempt }),
        fetchJSONWithFallback(`/markets?event_ticker=${encodeURIComponent(eventTicker)}&limit=1000`, { proxyHint, diagCollector: pushAttempt }),
      ]);

      setSeries(seriesData?.series || null);
      setEvent(eventData?.event || null);

      const withSort = (marketsData?.markets || [])
        .map((m) => ({ ...m, __range: parseRangeOrder(m.title || m.subtitle || "") }))
        .sort((a, b) => (a.__range.low - b.__range.low) || (a.__range.high - b.__range.high));

      setMarkets(withSort);
      setDiag((d) => ({ ...d, lastOK: "Loaded markets successfully" }));
    } catch (e) {
      const details = Array.isArray(e.details) ? e.details : [String(e.message || e)];
      setErr("Failed to load market data. Likely a CORS/network restriction. Try a Proxy preset or paste JSON in Offline Mode.");
      setDiag((d) => ({ ...d, attempts: [...details, ...d.attempts] }));
      setMarkets([]);
    } finally { setLoading(false); }
  }

  // --- Orderbook ---
  async function toggleOrderbook(ticker) {
    setExpanded((prev) => ({ ...prev, [ticker]: { ...(prev[ticker] || {}), loading: true, err: "" } }));
    try {
      const data = await fetchJSONWithFallback(`/markets/${encodeURIComponent(ticker)}/orderbook?depth=25`, {
        proxyHint,
        diagCollector: (a) => setDiag((d) => ({ ...d, attempts: [a, ...d.attempts] })),
      });
      setExpanded((prev) => ({ ...prev, [ticker]: { loading: false, data: data?.orderbook, err: "" } }));
    } catch (e) {
      const details = Array.isArray(e.details) ? e.details.join(" | ") : String(e.message || e);
      setExpanded((prev) => ({ ...prev, [ticker]: { loading: false, data: null, err: details } }));
    }
  }

  // --- Charts ---
  function getBoundsForTicker(market) {
    // Prefer market-provided open/close. Fallback to UTC day bounds parsed from ticker.
    const fallback = parseLockedEventDate(eventTicker) || { start_ts: 0, end_ts: Math.floor(Date.now()/1000) };
    const open = market?.open_time ? Math.floor(new Date(market.open_time).getTime()/1000) : fallback.start_ts;
    const close = market?.close_time ? Math.floor(new Date(market.close_time).getTime()/1000) : fallback.end_ts;
    // Slight padding to include last candle
    return { start_ts: open, end_ts: Math.max(close, open + 3600) };
  }

  // Dark theme palette for charts
  const theme = {
    grid: "#262626",          // neutral-800
    axis: "#d4d4d4",          // neutral-300
    tick: "#a3a3a3",          // neutral-400
    text: "#e5e5e5",          // neutral-200
    textMuted: "#9ca3af",      // slate-400
    line: "#60a5fa",           // sky-400
    wick: "#cbd5e1",           // slate-300
    candleUp: "#22c55e",       // green-500
    candleDown: "#ef4444",     // red-500
    tooltipBg: "rgba(15,23,42,0.96)", // slate-900 at ~96%
    tooltipBorder: "#334155",   // slate-700
  };

  // Custom tooltips for dark mode
  function TooltipBox({ title, rows }) {
    return (
      <div style={{ background: theme.tooltipBg, border: `1px solid ${theme.tooltipBorder}`, borderRadius: 8, padding: 10, color: theme.text, boxShadow: "0 6px 24px rgba(0,0,0,.4)" }}>
        <div style={{ fontSize: 12, color: theme.textMuted, marginBottom: 6 }}>{title}</div>
        <div style={{ display: "grid", gridTemplateColumns: "auto auto", gap: "4px 12px", fontSize: 12 }}>
          {rows.map(([k,v], i) => (
            <React.Fragment key={i}>
              <div style={{ color: theme.textMuted }}>{k}</div>
              <div style={{ color: theme.text }}>{v}</div>
            </React.Fragment>
          ))}
        </div>
      </div>
    );
  }

  const CandleTooltip = ({ active, payload }) => {
    if (!active || !payload || !payload.length) return null;
    const d = payload[0].payload || {};
    const time = new Date(d.t).toLocaleString();
    return (
      <TooltipBox
        title={time}
        rows={[["Open", `${d.open}¢`],["High", `${d.high}¢`],["Low", `${d.low}¢`],["Close", `${d.close}¢`],["Volume", d.vol ?? "—"],["Open Int.", d.oi ?? "—"]]}
      />
    );
  };

  const LineTooltip = ({ active, payload, label }) => {
    if (!active || !payload || !payload.length) return null;
    const p = payload[0].payload || {};
    return (
      <TooltipBox
        title={new Date(label || p.t).toLocaleString()}
        rows={[["Price", `${p.price}¢`], ["Qty", p.qty ?? "—"]]}
      />
    );
  };

  async function loadCandles(ticker, market, period = 1) {
    setChartState((s) => ({ ...s, [ticker]: { ...(s[ticker] || {}), loading: true, err: "", mode: "candles", period } }));
    try {
      const { start_ts, end_ts } = getBoundsForTicker(market);
      const path = `/series/${LOCKED_SERIES}/markets/${encodeURIComponent(ticker)}/candlesticks?start_ts=${start_ts}&end_ts=${end_ts}&period_interval=${period}`;
      const data = await fetchJSONWithFallback(path, { proxyHint, diagCollector: (a) => setDiag((d) => ({ ...d, attempts: [a, ...d.attempts] })) });
      const rows = (data?.candlesticks || []).map((c) => ({
        t: c.end_period_ts * 1000,
        open: c.price?.open,
        high: c.price?.high,
        low: c.price?.low,
        close: c.price?.close,
        vol: c.volume,
        oi: c.open_interest,
      })).filter((r) => Number.isFinite(r.close));
      setChartState((s) => ({ ...s, [ticker]: { ...(s[ticker] || {}), loading: false, err: "", mode: "candles", period, candles: rows } }));
    } catch (e) {
      setChartState((s) => ({ ...s, [ticker]: { ...(s[ticker] || {}), loading: false, err: String(e?.details?.join?.(" | ") || e?.message || e) } }));
    }
  }

  async function loadTrades(ticker, market) {
    setChartState((s) => ({ ...s, [ticker]: { ...(s[ticker] || {}), loading: true, err: "", mode: "line" } }));
    try {
      const { start_ts, end_ts } = getBoundsForTicker(market);
      let cursor = ""; const all = [];
      for (let i = 0; i < 5; i++) {
        const qp = new URLSearchParams({ ticker, min_ts: String(start_ts), max_ts: String(end_ts), limit: "1000" });
        if (cursor) qp.set("cursor", cursor);
        const data = await fetchJSONWithFallback(`/markets/trades?${qp.toString()}`, { proxyHint, diagCollector: (a) => setDiag((d) => ({ ...d, attempts: [a, ...d.attempts] })) });
        const trades = data?.trades || [];
        all.push(...trades);
        cursor = data?.cursor || "";
        if (!cursor || trades.length === 0) break;
      }
      const rows = all
        .filter((tr) => tr?.yes_price != null)
        .map((tr) => ({ t: new Date(tr.created_time).getTime(), price: tr.yes_price, qty: tr.count }))
        .sort((a, b) => a.t - b.t);
      setChartState((s) => ({ ...s, [ticker]: { ...(s[ticker] || {}), loading: false, err: "", mode: "line", trades: rows } }));
    } catch (e) {
      setChartState((s) => ({ ...s, [ticker]: { ...(s[ticker] || {}), loading: false, err: String(e?.details?.join?.(" | ") || e?.message || e) } }));
    }
  }

  function ChartPane({ ticker, market }) {
    const st = chartState[ticker] || {};
    const mode = st.mode || "candles";
    const period = st.period || 1;
    const dataCandles = st.candles || [];
    const dataTrades = st.trades || [];

    const formatter = (ts) => {
      const d = new Date(ts);
      return d.toISOString().slice(11, 19); // HH:MM:SS UTC
    };

    return (
      <div className="mt-3 rounded-xl border border-neutral-800 p-3 bg-neutral-950">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-xs text-neutral-400">Chart:</span>
          <button onClick={() => loadCandles(ticker, market, 1)} className={`text-xs px-2 py-1 rounded-lg ${mode === "candles" && period === 1 ? "bg-white/20" : "bg-white/10 hover:bg-white/20"}`}>Candles (1m)</button>
          <button onClick={() => loadCandles(ticker, market, 60)} className={`text-xs px-2 py-1 rounded-lg ${mode === "candles" && period === 60 ? "bg-white/20" : "bg-white/10 hover:bg-white/20"}`}>Candles (1h)</button>
          <button onClick={() => loadTrades(ticker, market)} className={`text-xs px-2 py-1 rounded-lg ${mode === "line" ? "bg-white/20" : "bg-white/10 hover:bg-white/20"}`}>Line (trades)</button>
          {st.loading && <span className="text-xs text-neutral-400 ml-2">Loading…</span>}
          {st.err && <span className="text-xs text-red-300 ml-2">{st.err}</span>}
        </div>
        <div className="h-56">
          {mode === "line" && (
            <ResponsiveContainer>
              <ComposedChart data={dataTrades} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
                <XAxis dataKey="t" tickFormatter={formatter} type="number" domain={["auto", "auto"]} tick={{ fill: theme.tick, fontSize: 11 }} axisLine={{ stroke: theme.axis }} tickLine={{ stroke: theme.axis }} />
                <YAxis width={44} domain={[0, 100]} tick={{ fill: theme.tick, fontSize: 11 }} axisLine={{ stroke: theme.axis }} tickLine={{ stroke: theme.axis }} />
                <Tooltip content={<LineTooltip />} wrapperStyle={{ outline: "none" }} />
                <Line type="monotone" dataKey="price" dot={false} strokeWidth={2} stroke={theme.line} activeDot={{ r: 3 }} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
          {mode !== "line" && (
            <ResponsiveContainer>
              <ComposedChart data={dataCandles} margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.grid} />
                <XAxis dataKey="t" tickFormatter={formatter} type="number" domain={["auto", "auto"]} tick={{ fill: theme.tick, fontSize: 11 }} axisLine={{ stroke: theme.axis }} tickLine={{ stroke: theme.axis }} />
                <YAxis width={44} domain={[0, 100]} tick={{ fill: theme.tick, fontSize: 11 }} axisLine={{ stroke: theme.axis }} tickLine={{ stroke: theme.axis }} />
                <Tooltip content={<CandleTooltip />} wrapperStyle={{ outline: "none" }} />
                {/* Wicks */}
                <ErrorBar dataKey="high" width={0} stroke={theme.wick} data={dataCandles.map((d) => ({ x: d.t, value: d.close, low: d.low, high: d.high }))} xAxisId={0} yAxisId={0} direction="y" />
                {/* Bodies */}
                <Bar dataKey={"close"} shape={(props) => {
                  const { x, width, payload } = props;
                  const o = payload.open; const c = payload.close;
                  const up = c >= o;
                  // props.y & props.height map baseline->close; approximate body with same height and color for readability
                  const yTop = Math.min(props.y, props.y + props.height);
                  const yBottom = Math.max(props.y, props.y + props.height);
                  const rectY = yTop + 1;
                  const rectH = Math.max(2, yBottom - yTop - 2);
                  return <rect x={x + 1} y={rectY} width={Math.max(1, width - 2)} height={rectH} rx={2} fill={up ? theme.candleUp : theme.candleDown} />;
                }} />
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>
    );
  }

  function exportCSV() {
    const rows = markets.map((m) => ({
      ticker: m.ticker,
      title: m.title,
      status: m.status,
      yes_bid: m.yes_bid,
      yes_ask: m.yes_ask,
      no_bid: m.no_bid,
      no_ask: m.no_ask,
      last_price: m.last_price,
      volume: m.volume,
      volume_24h: m.volume_24h,
      open_interest: m.open_interest,
      result: m.result ?? "",
      settlement_value: m.settlement_value ?? "",
      rules_primary: String(m.rules_primary || "").replaceAll("\n", " "),
    }));
    if (rows.length) downloadCSV(`${eventTicker}-markets.csv`, rows);
  }

  // OFFLINE MODE: apply pasted JSON
  function applyOffline() {
    const m = tryParseJSON(offlineMarketsJSON);
    const e = tryParseJSON(offlineEventJSON);
    const s = tryParseJSON(offlineSeriesJSON);

    if (s?.series) setSeries(s.series);
    if (e?.event) setEvent(e.event);
    if (m?.markets?.length) {
      const withSort = m.markets
        .map((mk) => ({ ...mk, __range: parseRangeOrder(mk.title || mk.subtitle || "") }))
        .sort((a, b) => (a.__range.low - b.__range.low) || (a.__range.high - b.__range.high));
      setMarkets(withSort);
      setErr("");
      setDiag((d) => ({ ...d, lastOK: "Loaded offline snapshot" }));
    }
  }

  // Load once on mount
  useEffect(() => {
    if (!firstLoadRef.current) {
      firstLoadRef.current = true;
      loadAll();
    }
  }, []);

  const linkAnchor = `#${eventTicker.toLowerCase()}`;
  const kalshiLink = `https://kalshi.com/markets/kxhighny/highest-temperature-in-nyc${linkAnchor}`;

  return (
    <div className="min-h-screen w-full bg-neutral-950 text-neutral-100 p-6">
      <div className="mx-auto max-w-6xl">
        <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight">NYC Max Temp – July 27 Market Data</h1>
            <p className="text-sm text-neutral-400">
              Locked to <span className="font-mono">{eventTicker}</span> in the <span className="font-mono">{LOCKED_SERIES}</span> series.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <label className="text-xs text-neutral-400">Proxy preset</label>
            <select
              value={proxyPreset}
              onChange={(e) => { setProxyPreset(e.target.value); setProxyHint(e.target.value); }}
              className="bg-neutral-900 border border-neutral-700 rounded-xl px-3 py-2 text-sm"
            >
              {PROXY_PRESETS.map(p => (<option key={p.value || "none"} value={p.value}>{p.label}</option>))}
            </select>
            <input
              type="text"
              value={proxyHint}
              onChange={(e) => setProxyHint(e.target.value)}
              placeholder="Or paste a custom proxy base"
              className="bg-neutral-900 border border-neutral-700 rounded-xl px-3 py-2 text-sm w-[360px]"
              title="If your browser blocks cross-origin requests, add a proxy base URL here."
            />
            <button onClick={loadAll} className="rounded-xl bg-white/10 hover:bg-white/20 px-4 py-2 text-sm">
              Load
            </button>
            <button
              onClick={exportCSV}
              className="rounded-xl bg-white/10 hover:bg-white/20 px-4 py-2 text-sm"
              disabled={!markets.length}
            >
              Export CSV
            </button>
          </div>
        </header>

        <section className="mb-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="rounded-2xl border border-neutral-800 p-4">
            <div className="text-xs uppercase tracking-wide text-neutral-400 mb-1">Event</div>
            <div className="font-mono text-lg">{eventTicker}</div>
            <div className="text-neutral-400 text-sm mt-1">{event?.title || "Highest temperature in NYC?"}</div>
            <div className="mt-2 text-sm">
              <a
                href={kalshiLink}
                target="_blank"
                rel="noreferrer"
                className="underline decoration-dotted underline-offset-4"
              >
                Open on Kalshi
              </a>
            </div>
          </div>
          <div className="rounded-2xl border border-neutral-800 p-4">
            <div className="text-xs uppercase tracking-wide text-neutral-400 mb-1">Series</div>
            <div className="font-mono text-lg">{LOCKED_SERIES}</div>
            <div className="text-neutral-400 text-sm mt-1">{series?.title || "Highest temperature in NYC today?"}</div>
            {event?.status && (
              <div className="mt-2 text-xs text-neutral-400">
                Event status: <span className="text-neutral-200">{event.status}</span>
              </div>
            )}
          </div>
        </section>

        {err && (
          <div className="mb-4 rounded-2xl border border-red-800 bg-red-950/20 p-4 text-red-200">
            <div className="font-semibold">Error</div>
            <div className="text-sm opacity-90">{err}</div>
          </div>
        )}

        {/* Diagnostics & Offline */}
        <section className="mb-4 rounded-2xl border border-neutral-800 overflow-hidden">
          <div className="px-4 py-3 bg-neutral-900/60 text-sm text-neutral-300">Diagnostics</div>
          <div className="p-4 text-sm text-neutral-300 space-y-3">
            <div>API bases:
              <ul className="list-disc pl-6 text-neutral-400">
                {API_BASES.map((b) => (
                  <li key={b} className="font-mono">{b}</li>
                ))}
              </ul>
            </div>
            <div>Proxy preset: <span className="font-mono text-neutral-200">{proxyPreset || "(none)"}</span></div>
            <div>Custom proxy: <span className="font-mono text-neutral-200">{proxyHint || "(none)"}</span></div>
            {diag.lastOK && <div className="text-green-300">{diag.lastOK}</div>}
            {!!diag.attempts.length && (
              <div>
                <div className="text-neutral-400 mb-1">Attempt log (most recent first):</div>
                <ul className="list-disc pl-6 space-y-1">
                  {diag.attempts.map((a, i) => (
                    <li key={i} className="font-mono break-all text-neutral-400">{a}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="mt-4">
              <div className="text-neutral-300 mb-2 font-medium">Offline mode</div>
              <p className="text-neutral-400 mb-2">If fetch is blocked, paste JSON from the API here and click <span className="text-neutral-200">Load Offline</span>.</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div>
                  <div className="text-xs text-neutral-400 mb-1 font-mono">/markets?event_ticker=... (object with "markets": [...])</div>
                  <textarea value={offlineMarketsJSON} onChange={(e) => setOfflineMarketsJSON(e.target.value)} placeholder="Paste markets JSON" className="w-full h-32 bg-neutral-900 border border-neutral-800 rounded-xl p-2 font-mono text-xs"/>
                </div>
                <div>
                  <div className="text-xs text-neutral-400 mb-1 font-mono">/events/{"{event_ticker}"} (object with "event": {"{ ... }"})</div>
                  <textarea value={offlineEventJSON} onChange={(e) => setOfflineEventJSON(e.target.value)} placeholder="Paste event JSON (optional)" className="w-full h-32 bg-neutral-900 border border-neutral-800 rounded-xl p-2 font-mono text-xs"/>
                </div>
                <div>
                  <div className="text-xs text-neutral-400 mb-1 font-mono">/series/KXHIGHNY (object with "series": {"{ ... }"})</div>
                  <textarea value={offlineSeriesJSON} onChange={(e) => setOfflineSeriesJSON(e.target.value)} placeholder="Paste series JSON (optional)" className="w-full h-32 bg-neutral-900 border border-neutral-800 rounded-xl p-2 font-mono text-xs"/>
                </div>
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <button onClick={applyOffline} className="rounded-xl bg-white/10 hover:bg-white/20 px-3 py-2 text-sm">Load Offline</button>
                <details>
                  <summary className="cursor-pointer text-neutral-400 text-sm">cURL helpers</summary>
                  <div className="mt-2 text-xs font-mono text-neutral-400 space-y-1">
                    <div># Markets</div>
                    <div>curl -s "https://api.elections.kalshi.com/trade-api/v2/markets?event_ticker={eventTicker}&limit=1000"</div>
                    <div># Event</div>
                    <div>curl -s "https://api.elections.kalshi.com/trade-api/v2/events/{eventTicker}"</div>
                    <div># Series</div>
                    <div>curl -s "https://api.elections.kalshi.com/trade-api/v2/series/{LOCKED_SERIES}"</div>
                    <div># Candles (1m)</div>
                    <div>curl -s "https://api.elections.kalshi.com/trade-api/v2/series/{LOCKED_SERIES}/markets/{"{ticker}"}/candlesticks?start_ts=...&end_ts=...&period_interval=1"</div>
                    <div># Trades (with ticker & ts filters)</div>
                    <div>curl -s "https://api.elections.kalshi.com/trade-api/v2/markets/trades?ticker={"{ticker}"}&min_ts=...&max_ts=...&limit=1000"</div>
                  </div>
                </details>
              </div>
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-neutral-800 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 bg-neutral-900/60">
            <div className="text-sm text-neutral-300">{loading ? "Loading markets…" : `${markets.length} markets`}</div>
            <div className="text-xs text-neutral-500">Prices in cents</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-neutral-900/40 text-neutral-300">
                <tr className="text-left">
                  <th className="px-4 py-2">Range</th>
                  <th className="px-2 py-2">Yes Bid</th>
                  <th className="px-2 py-2">Yes Ask</th>
                  <th className="px-2 py-2">No Bid</th>
                  <th className="px-2 py-2">No Ask</th>
                  <th className="px-2 py-2">Last</th>
                  <th className="px-2 py-2">Vol</th>
                  <th className="px-2 py-2">24h Vol</th>
                  <th className="px-2 py-2">OI</th>
                  <th className="px-2 py-2">Result</th>
                  <th className="px-2 py-2">Orderbook</th>
                  <th className="px-2 py-2">Charts</th>
                </tr>
              </thead>
              <tbody>
                {markets.map((m) => {
                  const exp = expanded[m.ticker] || {};
                  const hasOB = !!exp.data || exp.loading || exp.err;
                  const st = chartState[m.ticker] || {};
                  const hasChart = (st.candles?.length || st.trades?.length || st.loading || st.err);
                  return (
                    <React.Fragment key={m.ticker}>
                      <tr className="border-t border-neutral-800 hover:bg-neutral-900/30 align-top">
                        <td className="px-4 py-2">
                          <div className="font-medium text-neutral-100">{m.title || m.subtitle}</div>
                          <div className="text-xs text-neutral-500 font-mono">{m.ticker}</div>
                        </td>
                        <td className="px-2 py-2">{formatUSDcents(m.yes_bid)}</td>
                        <td className="px-2 py-2">{formatUSDcents(m.yes_ask)}</td>
                        <td className="px-2 py-2">{formatUSDcents(m.no_bid)}</td>
                        <td className="px-2 py-2">{formatUSDcents(m.no_ask)}</td>
                        <td className="px-2 py-2">{formatUSDcents(m.last_price)}</td>
                        <td className="px-2 py-2">{m.volume ?? "—"}</td>
                        <td className="px-2 py-2">{m.volume_24h ?? "—"}</td>
                        <td className="px-2 py-2">{m.open_interest ?? "—"}</td>
                        <td className="px-2 py-2">{m.result ?? (m.status === "settled" ? "—" : "")}</td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <button onClick={() => toggleOrderbook(m.ticker)} className="rounded-lg bg-white/10 hover:bg-white/20 px-3 py-1 text-xs">
                            {exp.loading ? "Loading…" : hasOB ? "Refresh" : "View"}
                          </button>
                        </td>
                        <td className="px-2 py-2 whitespace-nowrap">
                          <div className="flex gap-1">
                            <button onClick={() => loadCandles(m.ticker, m, 1)} className="rounded-lg bg-white/10 hover:bg-white/20 px-3 py-1 text-xs">Candles</button>
                            <button onClick={() => loadTrades(m.ticker, m)} className="rounded-lg bg-white/10 hover:bg-white/20 px-3 py-1 text-xs">Line</button>
                          </div>
                        </td>
                      </tr>
                      {(hasOB || hasChart) && (
                        <tr className="border-t border-neutral-900/60">
                          <td colSpan={12} className="px-4 py-3 bg-neutral-950/60">
                            {/* Charts */}
                            {hasChart && <ChartPane ticker={m.ticker} market={m} />}
                            {/* Orderbook */}
                            {exp.err && <div className="text-red-300 text-sm mt-3">Orderbook error: {exp.err}</div>}
                            {!exp.err && hasOB && (
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3">
                                <div>
                                  <div className="text-xs uppercase tracking-wide text-neutral-400 mb-1">YES bids</div>
                                  <div className="max-h-48 overflow-auto rounded-xl border border-neutral-800">
                                    <table className="w-full text-xs">
                                      <thead className="bg-neutral-900/40 text-neutral-300"><tr><th className="px-2 py-1">Price</th><th className="px-2 py-1">Qty</th></tr></thead>
                                      <tbody>
                                        {(exp.data?.yes || []).slice().reverse().map((row, i) => (
                                          <tr key={i} className="border-t border-neutral-800"><td className="px-2 py-1">{row[0]}¢</td><td className="px-2 py-1">{row[1]}</td></tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                                <div>
                                  <div className="text-xs uppercase tracking-wide text-neutral-400 mb-1">NO bids</div>
                                  <div className="max-h-48 overflow-auto rounded-xl border border-neutral-800">
                                    <table className="w-full text-xs">
                                      <thead className="bg-neutral-900/40 text-neutral-300"><tr><th className="px-2 py-1">Price</th><th className="px-2 py-1">Qty</th></tr></thead>
                                      <tbody>
                                        {(exp.data?.no || []).slice().reverse().map((row, i) => (
                                          <tr key={i} className="border-t border-neutral-800"><td className="px-2 py-1">{row[0]}¢</td><td className="px-2 py-1">{row[1]}</td></tr>
                                        ))}
                                      </tbody>
                                    </table>
                                  </div>
                                </div>
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <section className="mt-6 rounded-2xl border border-neutral-800 overflow-hidden">
          <div className="px-4 py-3 bg-neutral-900/60 text-sm text-neutral-300">Tests</div>
          <div className="p-4 text-sm">
            <ul className="space-y-1">
              <li className="text-green-300">✔ Locked event: {eventTicker}</li>
              <li className="text-neutral-400">Diagnostics shows which URL succeeded.</li>
            </ul>
          </div>
        </section>

        <footer className="mt-6 text-xs text-neutral-500">
          <div>Locked to <span className="font-mono">{eventTicker}</span>. Use a proxy preset if fetch is blocked, or paste JSON in Offline Mode.</div>
        </footer>
      </div>
    </div>
  );
}
