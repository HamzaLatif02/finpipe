"""
Comparison PDF report: cover, correlation summary, metrics table,
comparison charts, and disclaimer.
"""
import logging
import os
from datetime import date
from pathlib import Path

from fpdf import FPDF, XPos, YPos

from report import (
    FONTS_DIR,
    C_BG_BASE, C_BG_SURFACE, C_BG_RAISED,
    C_BORDER_S, C_BORDER_D, C_BORDER_B,
    C_ACCENT, C_POSITIVE, C_NEGATIVE,
    C_TEXT_1, C_TEXT_2, C_TEXT_3, C_TEXT_4,
    MARGIN, PAGE_W, PAGE_H, USABLE_W,
)
from chart_analyst import analyse_chart

logger = logging.getLogger(__name__)

# Asset A = blue, Asset B = orange
C_ASSET_A = (37,  99, 235)
C_ASSET_B = (234, 88,  12)

_METRIC_LABELS = {
    "total_return_pct":      "Total Return",
    "annualised_return_pct": "Annualised Return",
    "volatility_pct":        "Volatility (Ann.)",
    "sharpe_ratio":          "Sharpe Ratio",
    "max_drawdown_pct":      "Max Drawdown",
    "best_day_pct":          "Best Day",
    "worst_day_pct":         "Worst Day",
}

_PCT_KEYS = {
    "total_return_pct", "annualised_return_pct", "volatility_pct",
    "max_drawdown_pct", "best_day_pct", "worst_day_pct",
}

_CHART_KEY_ORDER = ["cumulative_return", "price_performance", "correlation", "drawdown"]
_CHART_LABELS = {
    "cumulative_return":  "Cumulative Return (%)",
    "price_performance":  "Normalised Price Performance (base 100)",
    "correlation":        "Daily Return Correlation",
    "drawdown":           "Drawdown from Peak (%)",
}


def _fmt(key: str, val) -> str:
    if val is None:
        return "N/A"
    if key in _PCT_KEYS:
        return f"{val:+.2f}%"
    if key == "sharpe_ratio":
        return f"{val:.2f}"
    return str(val)


class ComparisonReport(FPDF):

    def __init__(self, config_a: dict, config_b: dict):
        super().__init__()
        self.config_a = config_a
        self.config_b = config_b
        self.sym_a = config_a["symbol"]
        self.sym_b = config_b["symbol"]
        self.add_font("DejaVu",      fname=os.path.join(FONTS_DIR, "DejaVuSans.ttf"),         uni=True)
        self.add_font("DejaVu", "B", fname=os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf"),    uni=True)
        self.add_font("DejaVu", "I", fname=os.path.join(FONTS_DIR, "DejaVuSans-Oblique.ttf"), uni=True)
        self.set_auto_page_break(auto=False)
        self.set_margins(MARGIN, MARGIN, MARGIN)

    # ── Recurring elements ────────────────────────────────────────────────────

    def header(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(*C_BG_SURFACE)
        self.rect(0, 0, PAGE_W, 12, style="F")
        self.set_fill_color(*C_ACCENT)
        self.rect(0, 11.5, PAGE_W, 0.5, style="F")
        self.set_xy(MARGIN, 3)
        self.set_font("DejaVu", "B", 7)
        self.set_text_color(*C_ACCENT)
        self.cell(USABLE_W / 2, 6, "FINPIPE  /  COMPARISON REPORT", align="L")
        self.set_font("DejaVu", "B", 7)
        self.set_text_color(*C_TEXT_3)
        self.set_xy(MARGIN, 3)
        self.cell(USABLE_W, 6,
                  f"{self.sym_a} vs {self.sym_b}  ·  "
                  f"{self.config_a.get('period', '')}  ·  {self.config_a.get('interval', '')}",
                  align="R")

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_fill_color(*C_BG_SURFACE)
        self.rect(0, PAGE_H - 11, PAGE_W, 11, style="F")
        self.set_fill_color(*C_BORDER_S)
        self.rect(0, PAGE_H - 11, PAGE_W, 0.4, style="F")
        self.set_xy(MARGIN, PAGE_H - 10)
        self.set_font("DejaVu", "I", 7)
        self.set_text_color(*C_TEXT_3)
        self.cell(USABLE_W / 2, 5, f"Page {self.page_no()}", align="L")
        self.cell(USABLE_W / 2, 5,
                  f"{self.sym_a} vs {self.sym_b}  ·  Financial Pipeline", align="R")

    # ── Drawing primitives ────────────────────────────────────────────────────

    def _fill_page_bg(self, color=None):
        self.set_fill_color(*(color or C_BG_BASE))
        self.rect(0, 0, PAGE_W, PAGE_H, style="F")

    def _accent_divider(self, y=None, width=None, color=None):
        y = y if y is not None else self.get_y()
        self.set_fill_color(*(color or C_BORDER_D))
        self.rect(MARGIN, y, width or USABLE_W, 0.4, style="F")

    def _section_heading(self, text: str, y_gap: float = 8):
        self.ln(y_gap)
        y = self.get_y()
        self.set_fill_color(*C_ACCENT)
        self.rect(MARGIN, y, 2.5, 6, style="F")
        self.set_font("DejaVu", "B", 9)
        self.set_text_color(*C_ACCENT)
        self.set_xy(MARGIN + 6, y)
        self.cell(USABLE_W - 6, 6, text.upper(), align="L",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self._accent_divider(color=C_BORDER_D)
        self.ln(5)

    # ── Cover page ────────────────────────────────────────────────────────────

    def cover_page(self, comparison: dict):
        self.add_page()
        self._fill_page_bg(C_BG_BASE)

        # Top accent strip
        self.set_fill_color(*C_ACCENT)
        self.rect(0, 0, PAGE_W, 1.5, style="F")

        # Banner
        self.set_fill_color(*C_BG_SURFACE)
        self.rect(0, 0, PAGE_W, 130, style="F")

        # App label
        self.set_xy(0, 16)
        self.set_font("DejaVu", "B", 8)
        self.set_text_color(*C_ACCENT)
        self.cell(PAGE_W, 5, "FINPIPE", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(1)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(*C_TEXT_3)
        self.cell(PAGE_W, 5, "COMPARISON REPORT", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(4)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(*C_TEXT_4)
        self.cell(PAGE_W, 4, "·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·  ·",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Asset A
        self.ln(8)
        self.set_font("DejaVu", "B", 20)
        self.set_text_color(*C_ASSET_A)
        self.cell(PAGE_W, 11,
                  f"{comparison['name_a']} ({comparison['symbol_a']})",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # vs
        self.ln(2)
        self.set_font("DejaVu", "", 11)
        self.set_text_color(*C_TEXT_3)
        self.cell(PAGE_W, 7, "vs", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Asset B
        self.ln(2)
        self.set_font("DejaVu", "B", 20)
        self.set_text_color(*C_ASSET_B)
        self.cell(PAGE_W, 11,
                  f"{comparison['name_b']} ({comparison['symbol_b']})",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Divider
        self.ln(8)
        self._accent_divider(color=C_BORDER_B)

        # Period / interval / overlap
        self.ln(6)
        self.set_font("DejaVu", "", 9)
        self.set_text_color(*C_TEXT_2)
        self.cell(PAGE_W, 5,
                  f"Period: {comparison.get('period', '')}     "
                  f"Interval: {comparison.get('interval', '')}     "
                  f"Overlap: {comparison.get('overlap_days', 0)} trading days",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(3)
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(*C_TEXT_4)
        self.cell(PAGE_W, 4, f"Generated  {date.today().strftime('%B %d, %Y')}",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        self.ln(2)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(*C_TEXT_4)
        self.cell(PAGE_W, 4, "Source: Yahoo Finance  ·  Not financial advice",
                  align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # ── Correlation page ──────────────────────────────────────────────────────

    def correlation_page(self, comparison: dict):
        self.add_page()
        self._fill_page_bg()
        self.set_y(16)
        self._section_heading("Correlation Analysis")

        corr = comparison["correlation"]
        r_val = corr["value"]
        r_label = corr["label"]
        sym_a = comparison["symbol_a"]
        sym_b = comparison["symbol_b"]
        overlap = comparison["overlap_days"]

        # Large r value
        self.set_font("DejaVu", "B", 40)
        if "positive" in r_label.lower():
            self.set_text_color(*C_POSITIVE)
        elif "negative" in r_label.lower():
            self.set_text_color(*C_NEGATIVE)
        else:
            self.set_text_color(*C_TEXT_2)
        self.set_x(MARGIN)
        self.cell(USABLE_W, 20, f"r = {r_val}", align="C",
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        # Coloured label pill
        self.ln(4)
        lbl_lower = r_label.lower()
        if "strong positive" in lbl_lower:
            pill_bg, pill_fg = C_POSITIVE, (7, 9, 15)
        elif "positive" in lbl_lower:
            pill_bg, pill_fg = (20, 83, 45), (74, 222, 128)
        elif "strong negative" in lbl_lower:
            pill_bg, pill_fg = C_NEGATIVE, (7, 9, 15)
        elif "negative" in lbl_lower:
            pill_bg, pill_fg = (69, 10, 10), (252, 165, 165)
        else:
            pill_bg, pill_fg = C_BG_RAISED, C_TEXT_2

        pill_w = self.get_string_width(r_label) + 22
        pill_x = (PAGE_W - pill_w) / 2
        pill_y = self.get_y()
        self.set_fill_color(*pill_bg)
        self.rect(pill_x, pill_y, pill_w, 9, style="F")
        self.set_font("DejaVu", "B", 9)
        self.set_text_color(*pill_fg)
        self.set_xy(pill_x, pill_y + 1.5)
        self.cell(pill_w, 6, r_label, align="C")
        self.set_y(pill_y + 12)

        # Plain-English interpretation
        self.ln(8)
        lbl = r_label.lower()
        if "strong positive" in lbl:
            interp = (
                f"{sym_a} and {sym_b} show a strong positive correlation of {r_val}, meaning they tend "
                f"to move in the same direction on most trading days. This suggests limited "
                f"diversification benefit from holding both assets simultaneously."
            )
        elif "moderate positive" in lbl:
            interp = (
                f"{sym_a} and {sym_b} show a moderate positive correlation of {r_val}. They often "
                f"move together but with notable divergences, offering partial diversification "
                f"benefit compared to highly correlated assets."
            )
        elif "weak positive" in lbl:
            interp = (
                f"{sym_a} and {sym_b} have a weak positive correlation of {r_val}. Their price "
                f"movements are loosely related, providing reasonable diversification benefit "
                f"when held together in a portfolio."
            )
        elif "uncorrelated" in lbl:
            interp = (
                f"{sym_a} and {sym_b} are effectively uncorrelated (r = {r_val}). Their price "
                f"movements are largely independent, making this pair a strong candidate for "
                f"portfolio diversification."
            )
        else:
            interp = (
                f"{sym_a} and {sym_b} show a negative correlation of {r_val}. They tend to move "
                f"in opposite directions, which can provide a natural hedging effect and strong "
                f"diversification benefits in a combined portfolio."
            )

        self.set_x(MARGIN)
        self.set_font("DejaVu", "", 10)
        self.set_text_color(*C_TEXT_2)
        self.multi_cell(USABLE_W, 6, interp)

        self.ln(6)
        self.set_font("DejaVu", "I", 8)
        self.set_text_color(*C_TEXT_3)
        self.set_x(MARGIN)
        self.cell(USABLE_W, 5,
                  f"Based on {overlap} overlapping trading days.", align="C")

    # ── Metrics table page ────────────────────────────────────────────────────

    def metrics_page(self, comparison: dict):
        self.add_page()
        self._fill_page_bg()
        self.set_y(16)
        self._section_heading("Performance Metrics")

        metrics = comparison["metrics"]
        sym_a = comparison["symbol_a"]
        sym_b = comparison["symbol_b"]

        col_widths = [62, 37, 37, 32]
        total_w = sum(col_widths)
        start_x = MARGIN + (USABLE_W - total_w) / 2
        row_h = 12

        # Header
        hdr_y = self.get_y()
        self.set_fill_color(*C_BG_SURFACE)
        self.rect(start_x, hdr_y, total_w, row_h, style="F")
        self.set_fill_color(*C_ACCENT)
        self.rect(start_x, hdr_y, total_w, 0.5, style="F")
        self.rect(start_x, hdr_y + row_h, total_w, 0.5, style="F")

        headers = ["Metric", sym_a, sym_b, "Winner"]
        header_fg = [C_TEXT_1, C_ASSET_A, C_ASSET_B, C_TEXT_1]
        x = start_x
        for hdr, cw, hfg in zip(headers, col_widths, header_fg):
            self.set_xy(x + 4, hdr_y + 3.5)
            self.set_font("DejaVu", "B", 8)
            self.set_text_color(*hfg)
            align = "L" if hdr == "Metric" else "C"
            self.cell(cw - 8, 5, hdr, align=align)
            x += cw
        self.set_y(hdr_y + row_h + 1)

        # Rows
        wins_a = wins_b = 0
        for idx, (key, label) in enumerate(_METRIC_LABELS.items()):
            row_y = self.get_y()
            data = metrics.get(key, {})
            val_a = data.get("a")
            val_b = data.get("b")
            winner = data.get("winner", "tie")

            if winner == "a":   wins_a += 1
            elif winner == "b": wins_b += 1

            bg = C_BG_RAISED if idx % 2 == 0 else C_BG_BASE
            self.set_fill_color(*bg)
            self.rect(start_x, row_y, total_w, row_h, style="F")
            self.set_draw_color(*C_BORDER_S)
            self.rect(start_x, row_y, total_w, row_h, style="D")

            col_x = start_x

            # Metric label
            self.set_xy(col_x + 4, row_y + 3.5)
            self.set_font("DejaVu", "", 8)
            self.set_text_color(*C_TEXT_2)
            self.cell(col_widths[0] - 8, 5, label)
            col_x += col_widths[0]

            def _val_color(k, v):
                if v is None:               return C_TEXT_1
                if k in _PCT_KEYS and v >= 0: return C_POSITIVE
                if k in _PCT_KEYS and v < 0:  return C_NEGATIVE
                if k == "sharpe_ratio":
                    return C_POSITIVE if v >= 0 else C_NEGATIVE
                return C_TEXT_1

            # Value A
            self.set_xy(col_x + 4, row_y + 3.5)
            self.set_font("DejaVu", "B" if winner == "a" else "", 8)
            self.set_text_color(*_val_color(key, val_a))
            self.cell(col_widths[1] - 8, 5, _fmt(key, val_a), align="C")
            col_x += col_widths[1]

            # Value B
            self.set_xy(col_x + 4, row_y + 3.5)
            self.set_font("DejaVu", "B" if winner == "b" else "", 8)
            self.set_text_color(*_val_color(key, val_b))
            self.cell(col_widths[2] - 8, 5, _fmt(key, val_b), align="C")
            col_x += col_widths[2]

            # Winner
            self.set_xy(col_x + 4, row_y + 3.5)
            if winner == "a":
                self.set_font("DejaVu", "B", 8)
                self.set_text_color(*C_POSITIVE)
                self.cell(col_widths[3] - 8, 5, sym_a, align="C")
            elif winner == "b":
                self.set_font("DejaVu", "B", 8)
                self.set_text_color(*C_POSITIVE)
                self.cell(col_widths[3] - 8, 5, sym_b, align="C")
            else:
                self.set_font("DejaVu", "", 8)
                self.set_text_color(*C_TEXT_3)
                self.cell(col_widths[3] - 8, 5, "Tie", align="C")

            self.set_y(row_y + row_h)

        # Score summary
        self.ln(8)
        self.set_x(MARGIN)
        n = len(_METRIC_LABELS)
        self.set_font("DejaVu", "B", 9)
        if wins_a > wins_b:
            self.set_text_color(*C_POSITIVE)
            summary = f"{sym_a} wins {wins_a} of {n} metrics  ·  {sym_b} wins {wins_b} of {n} metrics"
        elif wins_b > wins_a:
            self.set_text_color(*C_POSITIVE)
            summary = f"{sym_b} wins {wins_b} of {n} metrics  ·  {sym_a} wins {wins_a} of {n} metrics"
        else:
            self.set_text_color(*C_TEXT_2)
            summary = f"Tied  —  {sym_a}: {wins_a}/{n}  ·  {sym_b}: {wins_b}/{n}"
        self.cell(USABLE_W, 6, summary, align="C")

    # ── Chart pages ───────────────────────────────────────────────────────────

    def chart_pages(self, chart_paths: list, comparison: dict):
        sym_a = comparison["symbol_a"]
        sym_b = comparison["symbol_b"]
        name_a = comparison["name_a"]
        name_b = comparison["name_b"]

        a_stats = (comparison.get("analysis_a") or {}).get("summary_stats") or {}
        b_stats = (comparison.get("analysis_b") or {}).get("summary_stats") or {}  # noqa: F841

        path_map = {}
        for p in chart_paths:
            stem = Path(p).stem
            for key in _CHART_KEY_ORDER:
                if stem.endswith(key):
                    path_map[key] = p
                    break

        for key in _CHART_KEY_ORDER:
            p = path_map.get(key)
            if not p or not Path(p).exists():
                continue

            self.add_page()
            self._fill_page_bg()

            caption = _CHART_LABELS.get(key, key.replace("_", " ").title())

            # Header strip
            header_h = 14
            self.set_fill_color(*C_BG_SURFACE)
            self.rect(MARGIN, 16, USABLE_W, header_h, style="F")
            self.set_fill_color(*C_ACCENT)
            self.rect(MARGIN, 16, 3, header_h, style="F")
            self.set_xy(MARGIN + 8, 16 + (header_h - 5) / 2)
            self.set_font("DejaVu", "B", 9)
            self.set_text_color(*C_TEXT_1)
            self.cell(USABLE_W - 8, 5, caption)

            # Chart image
            img_y = 16 + header_h + 4
            img_h = (PAGE_H - img_y - 14) * 0.60
            self.image(p, x=MARGIN, y=img_y, w=USABLE_W, h=img_h)
            self.set_draw_color(*C_BORDER_S)
            self.rect(MARGIN, img_y, USABLE_W, img_h, style="D")

            # AI description
            combined_stats = {
                **a_stats,
                "start_date": a_stats.get("start_date"),
                "end_date":   a_stats.get("end_date"),
            }
            description = analyse_chart(
                chart_type=key,
                symbol=f"{sym_a}_vs_{sym_b}",
                name=f"{name_a} vs {name_b}",
                summary_stats=combined_stats,
            )
            text_y = img_y + img_h + 5
            self.set_xy(MARGIN, text_y)
            self.set_font("DejaVu", "B", 9)
            self.set_text_color(37, 99, 235)
            self.cell(0, 5, "AI Analysis", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            self.set_font("DejaVu", "I", 10)
            self.set_text_color(80, 80, 80)
            self.ln(2)
            self.set_x(MARGIN)
            self.multi_cell(USABLE_W, 6, description)

    # ── Disclaimer ────────────────────────────────────────────────────────────

    def disclaimer_page(self):
        self.add_page()
        self._fill_page_bg()
        self.set_y(16)
        self._section_heading("Disclaimer")

        self.set_font("DejaVu", "", 9)
        self.set_text_color(*C_TEXT_2)
        text = (
            "This comparison report is generated automatically from Yahoo Finance data via the "
            "yfinance library for educational and portfolio tracking purposes only. It does not "
            "constitute financial advice, a solicitation, or a recommendation to buy or sell any "
            "security.\n\n"
            "Past performance is not indicative of future results. All data is sourced from public "
            "market feeds and may be subject to delays or inaccuracies. Correlation and other "
            "computed metrics are based on the overlapping date range of both assets and may not "
            "reflect future relationships. The user assumes full responsibility for any investment "
            "decisions made using this information.\n\n"
            "Finpipe is an open-source project and is not affiliated with Yahoo Finance, "
            "any brokerage, or financial institution."
        )
        self.set_x(MARGIN)
        self.multi_cell(USABLE_W, 6, text)

        self.ln(8)
        bx, by = MARGIN, self.get_y()
        bw, bh = USABLE_W, 18
        self.set_fill_color(*C_BG_RAISED)
        self.set_draw_color(*C_BORDER_D)
        self.rect(bx, by, bw, bh, style="FD")
        self.set_fill_color(*C_ACCENT)
        self.rect(bx, by, 2, bh, style="F")
        self.set_xy(bx + 8, by + 3)
        self.set_font("DejaVu", "B", 8)
        self.set_text_color(*C_ACCENT)
        self.cell(bw - 12, 4, "NOT FINANCIAL ADVICE")
        self.set_xy(bx + 8, by + 8)
        self.set_font("DejaVu", "", 7.5)
        self.set_text_color(*C_TEXT_3)
        self.cell(bw - 12, 4,
                  "For personal research and tracking only. Always consult a qualified financial advisor.")


# ── Public API ────────────────────────────────────────────────────────────────

def generate_comparison_report(
    config_a: dict, config_b: dict, comparison: dict, chart_paths: list
) -> str:
    sym_a = config_a["symbol"]
    sym_b = config_b["symbol"]

    from config import DATA_DIR
    out_path = Path(DATA_DIR) / f"{sym_a}_vs_{sym_b}_comparison_report.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = ComparisonReport(config_a, config_b)
    pdf.cover_page(comparison)
    pdf.correlation_page(comparison)
    pdf.metrics_page(comparison)
    pdf.chart_pages(chart_paths, comparison)
    pdf.disclaimer_page()

    pdf.output(str(out_path))
    logger.info("Comparison report saved to %s", out_path)
    return str(out_path)
