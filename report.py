import logging
from datetime import date
from pathlib import Path

from fpdf import FPDF, XPos, YPos

import analysis as ana
import charts
import cleaner
import explorer
import fetcher

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Colours ──────────────────────────────────────────────────────────────────
C_NAVY   = (30,  58,  95)   # header backgrounds
C_WHITE  = (255, 255, 255)
C_GREEN  = (22,  163, 74)
C_RED    = (220, 38,  38)
C_LIGHT  = (248, 250, 252)  # alternate row
C_BORDER = (203, 213, 225)
C_TEXT   = (30,  30,  30)
C_MUTED  = (100, 116, 139)

# ── Field labels ─────────────────────────────────────────────────────────────
_STAT_LABELS = {
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
_PCT_KEYS = {
    "total_return_pct", "annualised_return_pct", "volatility_pct",
    "max_drawdown_pct", "best_day_pct", "worst_day_pct",
}
_INFO_FIELDS = [
    ("sector",          "Sector"),
    ("industry",        "Industry"),
    ("marketCap",       "Market Cap"),
    ("trailingPE",      "Trailing P/E"),
    ("fiftyTwoWeekHigh","52-Week High"),
    ("fiftyTwoWeekLow", "52-Week Low"),
    ("dividendYield",   "Dividend Yield"),
]
_CHART_CAPTIONS = {
    "candlestick":       "Candlestick chart (last 90 trading days) with volume bars.",
    "price_ma":          "Close price with 20-day, 50-day, and 200-day moving averages.",
    "cumulative_return": "Cumulative return (%) from the start of the report period.",
    "drawdown":          "Rolling drawdown from the all-time high within the period.",
    "monthly_returns":   "Heatmap of average daily returns by month and year.",
    "summary_stats_table": "Summary statistics table.",
}
_CHART_ORDER = [
    "candlestick", "price_ma", "cumulative_return",
    "drawdown", "monthly_returns", "summary_stats_table",
]


def _fmt_stat(key: str, val) -> str:
    if val is None:
        return "N/A"
    if key in _PCT_KEYS:
        return f"{val:+.2f}%"
    if key == "sharpe_ratio":
        return f"{val:.2f}"
    if key == "avg_daily_volume":
        return f"{val:,.0f}"
    return str(val)


def _fmt_info(key: str, val) -> str:
    if val is None:
        return "N/A"
    if key == "marketCap":
        v = float(val)
        if v >= 1e12:
            return f"${v/1e12:.2f}T"
        if v >= 1e9:
            return f"${v/1e9:.2f}B"
        return f"${v:,.0f}"
    if key == "dividendYield" and isinstance(val, (int, float)):
        return f"{float(val)*100:.2f}%"
    if isinstance(val, float):
        return f"{val:,.2f}"
    return str(val)


# ── PDF class ─────────────────────────────────────────────────────────────────

class FinancialReport(FPDF):

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self.set_auto_page_break(auto=True, margin=20)
        self.set_margins(18, 18, 18)

    # -- Footer ---------------------------------------------------------------

    def footer(self):
        self.set_y(-14)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*C_MUTED)
        self.cell(0, 5, f"Page {self.page_no()}", align="L")
        self.cell(0, 5, "Source: Yahoo Finance via yfinance", align="R")

    # -- Helpers --------------------------------------------------------------

    def _h_line(self, color=C_BORDER):
        self.set_draw_color(*color)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())

    def _section_title(self, text: str):
        self.ln(6)
        self.set_font("Helvetica", "B", 12)
        self.set_text_color(*C_NAVY)
        self.cell(0, 8, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self._h_line(C_NAVY)
        self.ln(3)

    def _two_col_row(self, label: str, value: str, shade: bool = False,
                     val_color=None):
        col_w = (self.w - self.l_margin - self.r_margin) / 2
        x = self.get_x()
        y = self.get_y()
        row_h = 7

        if shade:
            self.set_fill_color(*C_LIGHT)
            self.rect(x, y, col_w * 2, row_h, style="F")

        self.set_draw_color(*C_BORDER)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*C_TEXT)
        self.set_xy(x, y)
        self.cell(col_w, row_h, f"  {label}", border="B",
                  new_x=XPos.RIGHT, new_y=YPos.TOP)

        if val_color:
            self.set_text_color(*val_color)
        self.set_font("Helvetica", "B", 9)
        self.cell(col_w, row_h, value, border="B",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_text_color(*C_TEXT)

    # -- Pages ----------------------------------------------------------------

    def title_page(self, analysis: dict):
        self.add_page()
        cfg = self.config
        stats = analysis.get("summary_stats") or {}

        # Navy banner
        self.set_fill_color(*C_NAVY)
        self.rect(0, 0, self.w, 68, style="F")

        self.set_y(14)
        self.set_font("Helvetica", "B", 22)
        self.set_text_color(*C_WHITE)
        self.cell(0, 10, f"{cfg['name']} ({cfg['symbol']})", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_font("Helvetica", "", 11)
        self.set_text_color(180, 210, 255)
        self.cell(0, 7, "Automated Financial Report", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.set_font("Helvetica", "", 9)
        self.set_text_color(200, 220, 255)
        details = (
            f"{cfg.get('asset_type', '')}  -  "
            f"Currency: {cfg.get('currency', 'N/A')}  -  "
            f"Period: {cfg.get('period', '')}  -  "
            f"Interval: {cfg.get('interval', '')}"
        )
        self.cell(0, 6, details, align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Move below the navy banner before rendering body content
        self.set_y(76)

        # Date generated
        self.set_font("Helvetica", "I", 9)
        self.set_text_color(*C_MUTED)
        self.cell(0, 6, f"Generated: {date.today().isoformat()}", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Quick-glance return pill
        ret = stats.get("total_return_pct")
        if ret is not None:
            self.ln(4)
            color = C_GREEN if ret >= 0 else C_RED
            self.set_font("Helvetica", "B", 15)
            self.set_text_color(*color)
            self.cell(0, 8, f"Period Return: {ret:+.2f}%", align="C",
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Period bar
        if stats.get("start_date") and stats.get("end_date"):
            self.set_font("Helvetica", "", 9)
            self.set_text_color(*C_MUTED)
            self.cell(0, 6,
                      f"{stats['start_date']}  to  {stats['end_date']}",
                      align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def metrics_page(self, analysis: dict):
        self.add_page()
        self._section_title("Key Performance Metrics")

        stats = analysis.get("summary_stats") or {}

        # Table header
        col_w = (self.w - self.l_margin - self.r_margin) / 2
        self.set_fill_color(*C_NAVY)
        self.set_text_color(*C_WHITE)
        self.set_font("Helvetica", "B", 9)
        self.cell(col_w, 8, "  Metric", fill=True, border=0,
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(col_w, 8, "Value", fill=True, border=0,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        for i, (key, label) in enumerate(_STAT_LABELS.items()):
            val = stats.get(key)
            fmt = _fmt_stat(key, val)
            shade = (i % 2 == 0)

            val_color = None
            if key in _PCT_KEYS and isinstance(val, (int, float)):
                val_color = C_GREEN if val >= 0 else C_RED

            self._two_col_row(label, fmt, shade=shade, val_color=val_color)

    def asset_info_page(self, analysis: dict):
        info = analysis.get("asset_info") or {}
        rows = [
            (label, _fmt_info(key, info[key]))
            for key, label in _INFO_FIELDS
            if key in info and info[key] not in (None, "", 0)
        ]
        if not rows:
            return

        self.add_page()
        self._section_title("Asset Information")

        col_w = (self.w - self.l_margin - self.r_margin) / 2
        self.set_fill_color(*C_NAVY)
        self.set_text_color(*C_WHITE)
        self.set_font("Helvetica", "B", 9)
        self.cell(col_w, 8, "  Field", fill=True, border=0,
                  new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.cell(col_w, 8, "Value", fill=True, border=0,
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        for i, (label, value) in enumerate(rows):
            self._two_col_row(label, value, shade=(i % 2 == 0))

    def charts_pages(self, chart_paths: list):
        # Build lookup: stem keyword → path
        path_map = {}
        for p in chart_paths:
            stem = Path(p).stem          # e.g. "AAPL_candlestick"
            for key in _CHART_ORDER:
                if stem.endswith(key):
                    path_map[key] = p
                    break

        for key in _CHART_ORDER:
            p = path_map.get(key)
            if not p or not Path(p).exists():
                continue

            self.add_page()
            caption = _CHART_CAPTIONS.get(key, key.replace("_", " ").title())

            # Caption bar
            self.set_fill_color(*C_NAVY)
            self.set_text_color(*C_WHITE)
            self.set_font("Helvetica", "B", 10)
            self.cell(0, 8, f"  {caption}", fill=True,
                      new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.ln(3)

            # Image — fit within usable width, max height 170mm
            usable_w = self.w - self.l_margin - self.r_margin
            self.image(p, x=self.l_margin, y=self.get_y(),
                       w=usable_w, h=0)   # h=0 → preserve aspect ratio

    def disclaimer_page(self):
        self.add_page()
        self._section_title("Disclaimer")
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*C_TEXT)
        text = (
            "This report is generated automatically from Yahoo Finance data "
            "for educational and portfolio tracking purposes only. It does not "
            "constitute financial advice."
        )
        self.multi_cell(0, 7, text)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_report(config: dict, analysis: dict, chart_paths: list) -> str:
    """Build and save the PDF report. Returns the saved file path."""
    symbol = config["symbol"]
    out_path = Path("data") / f"{symbol}_report.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = FinancialReport(config)
    pdf.title_page(analysis)
    pdf.metrics_page(analysis)
    pdf.asset_info_page(analysis)
    pdf.charts_pages(chart_paths)
    pdf.disclaimer_page()

    pdf.output(str(out_path))
    logger.info("Report saved to %s", out_path)
    return str(out_path)


# ── Main guard ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    config = explorer.interactive_select()
    fetcher.fetch_data(config)
    cleaner.clean_data(config)
    results = ana.run_analysis(config)
    chart_files = charts.generate_charts(config, results)
    path = generate_report(config, results, chart_files)
    print(f"\nReport saved: {path}")
