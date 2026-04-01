import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import mplfinance as mpf
import pandas as pd
import seaborn as sns

import analysis as ana
from config import CHARTS_DIR as _CHARTS_DIR

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

CHARTS_DIR = Path(_CHARTS_DIR)
DPI = 150
PRIMARY = "#2563EB"
NEGATIVE = "#DC2626"
POS_GREEN = "#16A34A"

sns.set_theme(style="whitegrid")


def _out(symbol: str, name: str) -> Path:
    """Return the output path for a chart PNG, creating the directory if needed."""
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    return CHARTS_DIR / f"{symbol}_{name}.png"


def _save(fig, path: Path) -> str:
    """Save a matplotlib figure to disk, close it, and return the path string."""
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", path)
    return str(path)


# ---------------------------------------------------------------------------
# 1. Candlestick
# ---------------------------------------------------------------------------

def _candlestick(config: dict, analysis: dict) -> str:
    df = analysis["price_series"].copy()

    # mplfinance requires a DatetimeIndex and title-cased OHLCV columns.
    col_map = {c: c.title() for c in df.columns if c.lower() in ("open", "high", "low", "close", "volume")}
    df = df.rename(columns=col_map)
    df.index = pd.to_datetime(df.index)
    df = df.tail(90)

    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(df.columns):
        raise ValueError("price_series missing OHLC columns for candlestick.")

    has_volume = bool("Volume" in df.columns and df["Volume"].sum() > 0)
    name = config["name"]
    symbol = config["symbol"]
    path = _out(symbol, "candlestick")

    mc = mpf.make_marketcolors(up=POS_GREEN, down=NEGATIVE, inherit=True)
    style = mpf.make_mpf_style(base_mpf_style="default", marketcolors=mc)

    fig, _ = mpf.plot(
        df,
        type="candle",
        volume=has_volume,
        title=f"{name} — Candlestick Chart",
        style=style,
        figsize=(12, 6),
        returnfig=True,
    )
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved %s", path)
    return str(path)


# ---------------------------------------------------------------------------
# 2. Price & Moving Averages
# ---------------------------------------------------------------------------

def _price_ma(config: dict, analysis: dict) -> str:
    ma_df = analysis["moving_averages"]
    name = config["name"]
    symbol = config["symbol"]

    close_col = "close" if "close" in ma_df.columns else "Close"
    close = ma_df[close_col]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(close.index, close, color=PRIMARY, linewidth=1.2, label="Close", zorder=3)

    ma_styles = {
        "ma_20":  ("#F59E0B", "MA 20"),
        "ma_50":  ("#8B5CF6", "MA 50"),
        "ma_200": (NEGATIVE,  "MA 200"),
    }
    for col, (color, label) in ma_styles.items():
        if col in ma_df.columns and ma_df[col].notna().any():
            ax.plot(ma_df.index, ma_df[col], color=color, linewidth=1, linestyle="--", label=label, alpha=0.85)

    ax.set_title(f"{name} — Price & Moving Averages", fontsize=13, fontweight="bold")
    ax.set_xlabel("")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:,.2f}"))
    ax.legend(frameon=True)
    fig.tight_layout()

    path = _out(symbol, "price_ma")
    return _save(fig, path)


# ---------------------------------------------------------------------------
# 3. Cumulative Return
# ---------------------------------------------------------------------------

def _cumulative_return(config: dict, analysis: dict) -> str:
    df = analysis["price_series"]
    col = "cumulative_return" if "cumulative_return" in df.columns else None
    if col is None:
        raise ValueError("No cumulative_return column in price_series.")

    series = df[col].dropna()
    name = config["name"]
    symbol = config["symbol"]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(series.index, series, color=PRIMARY, linewidth=1.5)
    ax.axhline(0, color="#6B7280", linewidth=0.8, linestyle="--")

    ax.fill_between(series.index, series, 0,
                    where=(series >= 0), alpha=0.15, color=POS_GREEN, label="Gain")
    ax.fill_between(series.index, series, 0,
                    where=(series < 0),  alpha=0.15, color=NEGATIVE,  label="Loss")

    ax.set_title(f"{name} — Cumulative Return (%)", fontsize=13, fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))
    ax.legend(frameon=True)
    fig.tight_layout()

    path = _out(symbol, "cumulative_return")
    return _save(fig, path)


# ---------------------------------------------------------------------------
# 4. Drawdown
# ---------------------------------------------------------------------------

def _drawdown(config: dict, analysis: dict) -> str:
    series = analysis["drawdown_series"].dropna()
    name = config["name"]
    symbol = config["symbol"]

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.fill_between(series.index, series, 0, color=NEGATIVE, alpha=0.4)
    ax.plot(series.index, series, color=NEGATIVE, linewidth=0.8)
    ax.axhline(0, color="#6B7280", linewidth=0.6, linestyle="--")

    ax.set_title(f"{name} — Drawdown from Peak (%)", fontsize=13, fontweight="bold")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.1f}%"))
    fig.tight_layout()

    path = _out(symbol, "drawdown")
    return _save(fig, path)


# ---------------------------------------------------------------------------
# 5. Monthly Returns Heatmap
# ---------------------------------------------------------------------------

def _monthly_returns(config: dict, analysis: dict) -> str:
    pivot = analysis["monthly_returns"]
    name = config["name"]
    symbol = config["symbol"]

    fig, ax = plt.subplots(figsize=(13, max(3, len(pivot) * 0.7 + 1.5)))
    sns.heatmap(
        pivot,
        ax=ax,
        cmap=sns.diverging_palette(10, 130, as_cmap=True),  # red → green
        center=0,
        annot=True,
        fmt=".2f",
        linewidths=0.4,
        linecolor="#E5E7EB",
        cbar_kws={"label": "Avg Daily Return (%)"},
    )
    ax.set_title(f"{name} — Monthly Returns (%)", fontsize=13, fontweight="bold")
    ax.set_xlabel("")
    ax.set_ylabel("Year")
    fig.tight_layout()

    path = _out(symbol, "monthly_returns")
    return _save(fig, path)


# ---------------------------------------------------------------------------
# 6. Summary Stats Table
# ---------------------------------------------------------------------------

_PCT_KEYS = {
    "total_return_pct", "annualised_return_pct", "volatility_pct",
    "max_drawdown_pct", "best_day_pct", "worst_day_pct",
}
_LABELS = {
    "start_date":            "Start Date",
    "end_date":              "End Date",
    "total_return_pct":      "Total Return",
    "annualised_return_pct": "Annualised Return",
    "volatility_pct":        "Volatility (ann.)",
    "sharpe_ratio":          "Sharpe Ratio",
    "max_drawdown_pct":      "Max Drawdown",
    "best_day_pct":          "Best Day",
    "worst_day_pct":         "Worst Day",
    "avg_daily_volume":      "Avg Daily Volume",
}


def _fmt_value(key: str, val) -> str:
    if val is None:
        return "N/A"
    if key in _PCT_KEYS:
        return f"{val:+.2f}%"
    if key == "sharpe_ratio":
        return f"{val:.2f}"
    if key == "avg_daily_volume":
        return f"{val:,.0f}"
    return str(val)


def _summary_table(config: dict, analysis: dict) -> str:
    stats = analysis["summary_stats"]
    name = config["name"]
    symbol = config["symbol"]

    rows = [(_LABELS.get(k, k), _fmt_value(k, v)) for k, v in stats.items()]

    fig, ax = plt.subplots(figsize=(7, len(rows) * 0.52 + 1.2))
    ax.axis("off")

    tbl = ax.table(
        cellText=rows,
        colLabels=["Metric", "Value"],
        cellLoc="left",
        loc="center",
        colWidths=[0.58, 0.38],
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(10)
    tbl.scale(1, 1.5)

    # Style header
    for col in (0, 1):
        cell = tbl[0, col]
        cell.set_facecolor("#1E3A5F")
        cell.set_text_props(color="white", fontweight="bold")

    # Alternate row shading; colour Value column by positive/negative
    for row_idx, (key, val) in enumerate(stats.items(), start=1):
        bg = "#F8FAFC" if row_idx % 2 == 0 else "white"
        tbl[row_idx, 0].set_facecolor(bg)
        val_cell = tbl[row_idx, 1]
        val_cell.set_facecolor(bg)
        if isinstance(val, (int, float)):
            if key in _PCT_KEYS and val < 0:
                val_cell.set_text_props(color=NEGATIVE)
            elif key in _PCT_KEYS and val > 0:
                val_cell.set_text_props(color=POS_GREEN)

    ax.set_title(f"{name} — Summary Statistics", fontsize=12,
                 fontweight="bold", pad=12)
    fig.tight_layout()

    path = _out(symbol, "summary_stats_table")
    return _save(fig, path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_charts(config: dict, analysis: dict) -> list:
    """Generate all charts and return a list of successfully saved file paths."""
    symbol = config["name"]
    generators = [
        ("candlestick",       _candlestick,       True),
        ("price_ma",          _price_ma,          analysis.get("moving_averages") is not None),
        ("cumulative_return", _cumulative_return,  True),
        ("drawdown",          _drawdown,           analysis.get("drawdown_series") is not None),
        ("monthly_returns",   _monthly_returns,    analysis.get("monthly_returns") is not None),
        ("summary_stats",     _summary_table,      analysis.get("summary_stats") is not None),
    ]

    saved = []
    for chart_name, fn, enabled in generators:
        if not enabled:
            logger.info("Skipping %s for %s (data not available).", chart_name, symbol)
            continue
        try:
            path = fn(config, analysis)
            saved.append(path)
        except Exception as exc:
            logger.warning("Failed to generate %s: %s", chart_name, exc)

    return saved


# ---------------------------------------------------------------------------
# Main guard
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import cleaner
    import explorer
    import fetcher
    config = explorer.interactive_select()
    fetcher.fetch_data(config)
    cleaner.clean_data(config)
    results = ana.run_analysis(config)
    paths = generate_charts(config, results)

    print(f"\nGenerated {len(paths)} chart(s):")
    for p in paths:
        print(f"  {p}")
