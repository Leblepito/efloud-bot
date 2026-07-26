"""Trade-chart renderer — Lane D real pixels (entry/SL/TP overlay).

Turns a Lane A ``content_job`` signal (symbol, direction, entry, sl, tp1, tp2)
plus cached OHLCV candles into a **branded annotated chart PNG**: candlesticks,
horizontal entry / SL / TP1 / TP2 levels, a shaded risk band (entry→SL) and
reward band (entry→TP1), and the u²Algo brand frame.

Design constraints (deliberate):

- **matplotlib only** — already a project dependency (``mplfinance`` is NOT
  installed; candles are drawn manually with bar/vlines primitives so the
  renderer has no new native deps).
- **Offline-first** — candles come from the local parquet cache
  (``cache/ohlcv/{SYMBOL}/{tf}.parquet`` via ``data.cache.OHLCVCache``). A live
  Binance fetch is opt-in (``allow_fetch=True``) so cron/CI never hits network.
- **No absolute money on the canvas** — only price levels, R:R and risk-%,
  matching ``scripts/content_compliance.py`` decision #5. Price axis labels are
  chart context, never PnL.
- **Draft-only** — writes files, posts nothing, touches no trade state.

Two output geometries mirror Lane D's ``VISUAL_FORMATS``:
  ``still``    1080×1350 (IG/X portrait post)
  ``vertical`` 1080×1920 (Reels / Shorts / Stories)

Used by ``scripts/lane_d_visual.py`` via ``chart_renderer`` (the Lane D
``Renderer`` protocol) and by ``scripts/lane_g_publish.py`` for the video path.
"""
from __future__ import annotations

import logging
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger("efloud.chart_render")

# ── brand palette (u2algo-site/brand-kit/BRAND.md §2, canonical) ─────────────
BRAND = {
    "bg": "#050510",
    "panel": "#0c1224",
    "grid": "#141c33",
    "cyan": "#00f0ff",
    "blue": "#0080ff",
    "purple": "#a855f7",
    "ink": "#f8fafc",
    "muted": "#94a3b8",
    "dim": "#64748b",
    "up": "#00ff88",
    "down": "#ff3366",
    "warn": "#fbbf24",
}

# (width_px, height_px) — mirrors lane_d_visual.VISUAL_FORMATS.
CHART_FORMATS: dict[str, tuple[int, int]] = {
    "still": (1080, 1350),
    "vertical": (1080, 1920),
}

DEFAULT_CANDLES = 120
_DPI = 100


class ChartRenderError(Exception):
    """Chart could not be produced (no candles, bad levels)."""


@dataclass
class TradeLevels:
    """The annotated levels for one signal."""

    symbol: str
    timeframe: str
    direction: str          # LONG | SHORT
    entry: float
    sl: float
    tp1: float
    tp2: Optional[float] = None
    confluence: Optional[int] = None

    @property
    def rr_tp1(self) -> Optional[float]:
        risk = abs(self.entry - self.sl)
        if risk <= 0:
            return None
        return abs(self.tp1 - self.entry) / risk

    @property
    def risk_pct(self) -> Optional[float]:
        if not self.entry:
            return None
        return abs(self.entry - self.sl) / abs(self.entry) * 100

    @classmethod
    def from_signal(cls, signal: dict) -> "TradeLevels":
        """Build from a Lane A ``content_job`` ``signal`` block."""
        try:
            entry = float(signal["entry"])
            sl = float(signal["sl"])
            tp1 = float(signal["tp1"])
        except (KeyError, TypeError, ValueError) as e:
            raise ChartRenderError(f"signal missing/invalid entry|sl|tp1: {e}") from e
        tp2_raw = signal.get("tp2")
        try:
            tp2 = float(tp2_raw) if tp2_raw not in (None, "", 0, 0.0) else None
        except (TypeError, ValueError):
            tp2 = None
        conf_raw = signal.get("confluence")
        try:
            conf = int(conf_raw) if conf_raw is not None else None
        except (TypeError, ValueError):
            conf = None
        return cls(
            symbol=str(signal.get("symbol") or "?"),
            timeframe=str(signal.get("timeframe") or "?"),
            direction=str(signal.get("direction") or "?").upper(),
            entry=entry, sl=sl, tp1=tp1, tp2=tp2, confluence=conf,
        )


# ── candles ─────────────────────────────────────────────────────────────────

def load_candles(symbol: str, timeframe: str, *, limit: int = DEFAULT_CANDLES,
                 cache_dir: str | Path = "cache/ohlcv", allow_fetch: bool = False):
    """Return the last ``limit`` OHLCV rows for (symbol, timeframe).

    Cache-first (parquet, sha256-verified by ``OHLCVCache``). ``allow_fetch``
    opts into a live Binance public REST pull when the cache misses — off by
    default so cron/CI stays offline and deterministic.
    """
    from data.cache import OHLCVCache

    df = None
    try:
        df = OHLCVCache(cache_dir).get(symbol, timeframe)
    except Exception as e:  # a broken cache must not kill the render path
        log.warning("chart_cache_read_failed symbol=%s tf=%s err=%s", symbol, timeframe, e)

    if (df is None or df.empty) and allow_fetch:
        df = _fetch_candles(symbol, timeframe, limit=limit)

    if df is None or df.empty:
        raise ChartRenderError(
            f"no OHLCV for {symbol} {timeframe} "
            f"(cache={cache_dir}, allow_fetch={allow_fetch})"
        )
    return df.tail(limit)


def _fetch_candles(symbol: str, timeframe: str, *, limit: int):  # pragma: no cover - network
    """Live Binance public klines (opt-in path)."""
    import time

    from data.fetcher import OHLCVFetcher
    from data.timeframes import tf_to_minutes

    tf_ms = tf_to_minutes(timeframe) * 60_000
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - tf_ms * (limit + 5)
    try:
        return OHLCVFetcher().fetch_ohlcv_range(
            symbol, timeframe, start_ms, end_ms, max_gap_pct=100.0
        ).df
    except Exception as e:
        log.warning("chart_fetch_failed symbol=%s tf=%s err=%s", symbol, timeframe, e)
        return None


# ── drawing ─────────────────────────────────────────────────────────────────

def _fmt_price(p: float) -> str:
    """Price label with a sane precision for both BTC (5 digits) and micro-caps."""
    a = abs(p)
    if a >= 1000:
        return f"{p:,.1f}"
    if a >= 100:
        return f"{p:,.2f}"
    if a >= 1:
        return f"{p:,.3f}"
    if a >= 0.01:
        return f"{p:,.5f}"
    return f"{p:,.7f}"


def _draw_candles(ax, df) -> None:
    """Manual candlestick draw (no mplfinance dependency)."""
    o = df["open"].to_numpy(dtype=float)
    h = df["high"].to_numpy(dtype=float)
    lo = df["low"].to_numpy(dtype=float)
    c = df["close"].to_numpy(dtype=float)
    x = range(len(df))
    for i in x:
        up = c[i] >= o[i]
        colour = BRAND["up"] if up else BRAND["down"]
        # wick
        ax.vlines(i, lo[i], h[i], color=colour, linewidth=0.9, alpha=0.85, zorder=2)
        # body (a doji still needs a visible sliver)
        body_lo, body_hi = min(o[i], c[i]), max(o[i], c[i])
        height = body_hi - body_lo
        if height <= 0:
            height = (h[i] - lo[i]) * 0.02 or abs(c[i]) * 1e-5
        ax.bar(i, height, bottom=body_lo, width=0.68, color=colour,
               edgecolor=colour, linewidth=0.4, alpha=0.95, zorder=3)


def _level_label(ax, x_right: float, price: float, text: str, colour: str) -> None:
    ax.annotate(
        f" {text} {_fmt_price(price)} ",
        xy=(x_right, price), xycoords="data",
        va="center", ha="left", fontsize=11, color=BRAND["bg"], weight="bold",
        bbox=dict(boxstyle="round,pad=0.32", facecolor=colour, edgecolor="none"),
        annotation_clip=False, zorder=8,
    )


def render_trade_chart(
    levels: TradeLevels,
    out_path: str | Path,
    *,
    fmt: str = "still",
    candles=None,
    cache_dir: str | Path = "cache/ohlcv",
    allow_fetch: bool = False,
    limit: int = DEFAULT_CANDLES,
    watermark: str = "u\u00b2Algo · @u2algo",
) -> Path:
    """Render one annotated trade chart PNG. Returns the written path."""
    import matplotlib
    matplotlib.use("Agg")  # headless: no display on VPS/CI
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    if fmt not in CHART_FORMATS:
        raise ChartRenderError(f"unknown format {fmt!r} (have {sorted(CHART_FORMATS)})")
    w_px, h_px = CHART_FORMATS[fmt]

    df = candles if candles is not None else load_candles(
        levels.symbol, levels.timeframe,
        limit=limit, cache_dir=cache_dir, allow_fetch=allow_fetch,
    )
    if df is None or len(df) == 0:
        raise ChartRenderError(f"empty candle frame for {levels.symbol}")

    fig = plt.figure(figsize=(w_px / _DPI, h_px / _DPI), dpi=_DPI,
                     facecolor=BRAND["bg"])
    # Leave headroom for the title block, a footer strip for the disclaimer, and
    # a right gutter wide enough for the level price pills (they are drawn
    # outside the axes at x_right and would otherwise clip on the canvas edge).
    ax = fig.add_axes([0.085, 0.115, 0.72, 0.72])
    ax.set_facecolor(BRAND["panel"])
    for spine in ax.spines.values():
        spine.set_color(BRAND["grid"])
    ax.grid(True, color=BRAND["grid"], linewidth=0.6, alpha=0.6)
    ax.tick_params(colors=BRAND["dim"], labelsize=9)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _p: _fmt_price(v)))

    _draw_candles(ax, df)

    n = len(df)
    ax.set_xlim(-1, n + max(2, n * 0.06))
    x_right = n + 0.4

    # price window must contain every annotated level, with breathing room
    prices = [float(df["low"].min()), float(df["high"].max()),
              levels.entry, levels.sl, levels.tp1]
    if levels.tp2 is not None:
        prices.append(levels.tp2)
    p_lo, p_hi = min(prices), max(prices)
    pad = (p_hi - p_lo) * 0.06 or abs(p_hi) * 0.01 or 1.0
    ax.set_ylim(p_lo - pad, p_hi + pad)

    # Sanity signal: entry should sit near the last close. A large gap means the
    # candle cache is stale (or the wrong symbol/tf was requested) — the chart
    # still renders (levels must always be visible) but the candles get squashed
    # into a corner, so surface it instead of shipping a silently bad visual.
    last_close = float(df["close"].iloc[-1])
    candle_span = float(df["high"].max()) - float(df["low"].min())
    if candle_span > 0 and abs(levels.entry - last_close) > candle_span:
        log.warning(
            "chart_levels_far_from_price symbol=%s tf=%s entry=%s last_close=%s "
            "— candle cache may be stale",
            levels.symbol, levels.timeframe, levels.entry, last_close,
        )

    # risk band (entry→SL) and reward band (entry→TP1)
    ax.axhspan(min(levels.entry, levels.sl), max(levels.entry, levels.sl),
               color=BRAND["down"], alpha=0.10, zorder=1)
    ax.axhspan(min(levels.entry, levels.tp1), max(levels.entry, levels.tp1),
               color=BRAND["up"], alpha=0.10, zorder=1)

    band = [
        (levels.entry, "ENTRY", BRAND["cyan"], "-"),
        (levels.sl, "SL", BRAND["down"], "--"),
        (levels.tp1, "TP1", BRAND["up"], "--"),
    ]
    if levels.tp2 is not None:
        band.append((levels.tp2, "TP2", BRAND["purple"], ":"))
    for price, tag, colour, style in band:
        ax.axhline(price, color=colour, linewidth=1.6, linestyle=style,
                   alpha=0.95, zorder=6)
        _level_label(ax, x_right, price, tag, colour)

    # x labels: sparse dates, never crowded
    idx = df.index
    step = max(1, n // 6)
    ticks = list(range(0, n, step))
    try:
        labels = [idx[i].strftime("%d.%m %H:%M") for i in ticks]
    except (AttributeError, ValueError):
        labels = [str(i) for i in ticks]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=0, fontsize=8, color=BRAND["dim"])

    _draw_header(fig, levels)
    _draw_footer(fig, watermark)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=BRAND["bg"], edgecolor="none")
    plt.close(fig)
    log.info("chart_rendered symbol=%s tf=%s fmt=%s path=%s",
             levels.symbol, levels.timeframe, fmt, out)
    return out


def _draw_header(fig, levels: TradeLevels) -> None:
    """Symbol · TF · direction pill + R:R / risk-% metric strip."""
    dir_colour = BRAND["up"] if levels.direction == "LONG" else BRAND["down"]
    fig.text(0.085, 0.945, f"{levels.symbol}", fontsize=30, weight="bold",
             color=BRAND["ink"], va="top", ha="left")
    fig.text(0.085, 0.902, f"{levels.timeframe} · SMC setup", fontsize=13,
             color=BRAND["muted"], va="top", ha="left")
    fig.text(0.915, 0.945, levels.direction, fontsize=22, weight="bold",
             color=dir_colour, va="top", ha="right",
             bbox=dict(boxstyle="round,pad=0.38", facecolor=BRAND["panel"],
                       edgecolor=dir_colour, linewidth=1.6))

    # Ratio/risk metrics only — never absolute money (compliance decision #5).
    bits = []
    if levels.risk_pct is not None:
        bits.append(f"Risk ~{levels.risk_pct:.1f}%")
    if levels.rr_tp1 is not None:
        bits.append(f"R:R 1:{levels.rr_tp1:.1f} (TP1)")
    if levels.confluence is not None:
        bits.append(f"Confluence {levels.confluence}/100")
    if bits:
        fig.text(0.915, 0.902, "  ·  ".join(bits), fontsize=12,
                 color=BRAND["cyan"], va="top", ha="right")


def _draw_footer(fig, watermark: str) -> None:
    from engine.content_jobs import COMPLIANCE_TR

    fig.text(0.085, 0.055, COMPLIANCE_TR, fontsize=11, color=BRAND["muted"],
             va="center", ha="left")
    fig.text(0.915, 0.055, watermark, fontsize=12, weight="bold",
             color=BRAND["cyan"], va="center", ha="right")


# ── Lane D Renderer adapter ─────────────────────────────────────────────────

def chart_renderer(spec: dict, fmt: str, base: Path) -> Path:
    """Lane D ``Renderer``-compatible callable: spec + fmt + base → PNG path.

    Reads the levels from ``spec['levels']`` (injected by Lane D from the Lane C
    copy draft). Falls back to ``lane_d_visual.manifest_renderer`` when levels
    are absent or the chart cannot be produced, so a missing candle cache
    degrades a batch to manifests instead of crashing it.
    """
    from scripts.lane_d_visual import manifest_renderer

    raw = spec.get("levels") or {}
    if not raw:
        return manifest_renderer(spec, fmt, base)
    try:
        levels = TradeLevels.from_signal(raw)
        out = Path(str(base) + f".{fmt}.png")
        return render_trade_chart(
            levels, out, fmt=fmt,
            cache_dir=spec.get("cache_dir") or "cache/ohlcv",
            allow_fetch=bool(spec.get("allow_fetch")),
        )
    except Exception as e:
        log.warning("chart_renderer_fallback event_id=%s err=%s",
                    spec.get("event_id"), e)
        return manifest_renderer(spec, fmt, base)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI: render one annotated chart from explicit levels (manual/QA use)."""
    import argparse

    ap = argparse.ArgumentParser(description="Render an annotated trade chart PNG")
    ap.add_argument("--symbol", required=True, help="e.g. BTC/USDT")
    ap.add_argument("--timeframe", default="15m")
    ap.add_argument("--direction", default="LONG", choices=["LONG", "SHORT", "long", "short"])
    ap.add_argument("--entry", type=float, required=True)
    ap.add_argument("--sl", type=float, required=True)
    ap.add_argument("--tp1", type=float, required=True)
    ap.add_argument("--tp2", type=float, default=None)
    ap.add_argument("--confluence", type=int, default=None)
    ap.add_argument("--out", required=True, help="output PNG path (or prefix with --all-formats)")
    ap.add_argument("--format", default="still", choices=sorted(CHART_FORMATS))
    ap.add_argument("--all-formats", action="store_true", help="render every format")
    ap.add_argument("--candles", type=int, default=DEFAULT_CANDLES)
    ap.add_argument("--cache-dir", default="cache/ohlcv")
    ap.add_argument("--allow-fetch", action="store_true", help="live Binance pull on cache miss")
    args = ap.parse_args(argv)

    levels = TradeLevels(
        symbol=args.symbol, timeframe=args.timeframe,
        direction=args.direction.upper(), entry=args.entry, sl=args.sl,
        tp1=args.tp1, tp2=args.tp2, confluence=args.confluence,
    )
    formats = sorted(CHART_FORMATS) if args.all_formats else [args.format]
    for fmt in formats:
        out = Path(args.out)
        if args.all_formats:
            out = out.with_name(f"{out.stem}.{fmt}{out.suffix or '.png'}")
        p = render_trade_chart(
            levels, out, fmt=fmt, limit=args.candles,
            cache_dir=args.cache_dir, allow_fetch=args.allow_fetch,
        )
        print(p)
    return 0


__all__ = [
    "BRAND", "CHART_FORMATS", "TradeLevels", "ChartRenderError",
    "load_candles", "render_trade_chart", "chart_renderer", "main",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
