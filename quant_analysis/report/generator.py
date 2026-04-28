"""
Report generation: aggregate technical, fundamental, risk, forecast, and backtest
into HTML/Markdown/DataFrame summaries for investment and quant use.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config


def _fmt_pct(x: float) -> str:
    if pd.isna(x):
        return "—"
    return f"{x * 100:.2f}%"


def _fmt_num(x: float) -> str:
    if pd.isna(x):
        return "—"
    if abs(x) >= 1e9:
        return f"{x / 1e9:.2f}B"
    if abs(x) >= 1e6:
        return f"{x / 1e6:.2f}M"
    if abs(x) >= 1e3:
        return f"{x / 1e3:.2f}K"
    return f"{x:.4f}"


class ReportGenerator:
    """
    Generate consolidated analysis reports from pipeline outputs.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or config.REPORTS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def risk_summary_table(self, risk_series: pd.Series) -> str:
        """Markdown table of risk metrics."""
        rows = []
        for k, v in risk_series.items():
            if isinstance(v, float):
                if "return" in k or "drawdown" in k or "var" in k or "cvar" in k:
                    rows.append((k, _fmt_pct(v)))
                else:
                    rows.append((k, _fmt_num(v)))
            else:
                rows.append((k, str(v)))
        md = "| Metric | Value |\n|--------|-------|\n"
        md += "\n".join(f"| {r[0]} | {r[1]} |" for r in rows)
        return md

    def fundamental_summary_table(self, fund_df: pd.DataFrame) -> str:
        """Markdown table of fundamental metrics."""
        if fund_df.empty:
            return "*No fundamental data.*"
        md = "| Category | Metric | Value |\n|----------|--------|-------|\n"
        for _, row in fund_df.iterrows():
            v = row.get("value", row.iloc[-1])
            if isinstance(v, float):
                v = _fmt_num(v) if abs(v) < 1 else _fmt_pct(v) if "ratio" in str(row.get("metric", "")) else _fmt_num(v)
            md += f"| {row.get('category', '')} | {row.get('metric', '')} | {v} |\n"
        return md

    def factor_exposures_table(self, exposures: pd.Series) -> str:
        """Markdown table of factor exposures."""
        if exposures.empty:
            return "*No factor data.*"
        md = "| Factor | Exposure |\n|--------|----------|\n"
        for k, v in exposures.items():
            md += f"| {k} | {_fmt_num(v)} |\n"
        return md

    def forecast_summary(self, forecast_series: pd.Series, method: str) -> str:
        """Short summary of forecast (next N days)."""
        if forecast_series.empty:
            return f"*No {method} forecast.*"
        first = forecast_series.iloc[0]
        last = forecast_series.iloc[-1]
        ret = (last / first) - 1 if first and first != 0 else np.nan
        return f"**{method}**: 1-step price = {_fmt_num(first)}, {len(forecast_series)}-step price = {_fmt_num(last)}, implied return = {_fmt_pct(ret)}"

    def generate_markdown(
        self,
        ticker: str,
        *,
        technical_df: Optional[pd.DataFrame] = None,
        fundamental_df: Optional[pd.DataFrame] = None,
        factor_exposures: Optional[pd.Series] = None,
        risk_metrics: Optional[pd.Series] = None,
        forecasts: Optional[Dict[str, pd.Series]] = None,
        backtest_summary: Optional[pd.Series] = None,
        extra_sections: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Generate a single Markdown report for one ticker.
        """
        sections = []
        sections.append(f"# Quantitative Analysis Report: {ticker}")
        sections.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")

        if risk_metrics is not None and not risk_metrics.empty:
            sections.append("## Risk & Performance")
            sections.append(self.risk_summary_table(risk_metrics))
            sections.append("")

        if fundamental_df is not None and not fundamental_df.empty:
            sections.append("## Fundamental Metrics")
            sections.append(self.fundamental_summary_table(fundamental_df))
            sections.append("")

        if factor_exposures is not None and not factor_exposures.empty:
            sections.append("## Factor Exposures")
            sections.append(self.factor_exposures_table(factor_exposures))
            sections.append("")

        if forecasts:
            sections.append("## Price Forecasts")
            for method, series in forecasts.items():
                sections.append(self.forecast_summary(series, method))
            sections.append("")

        if backtest_summary is not None and not backtest_summary.empty:
            sections.append("## Backtest Summary")
            sections.append(self.risk_summary_table(backtest_summary))
            sections.append("")

        if technical_df is not None and not technical_df.empty:
            last = technical_df.iloc[-1]
            sections.append("## Latest Technical Snapshot")
            row = last.dropna()
            for k, v in row.items():
                if k in ("Open", "High", "Low", "Close", "Volume", "rsi", "macd", "atr", "adx"):
                    sections.append(f"- **{k}**: {_fmt_num(v)}")
            sections.append("")

        if extra_sections:
            for title, content in extra_sections.items():
                sections.append(f"## {title}")
                sections.append(content)
                sections.append("")

        return "\n".join(sections)

    def save_markdown(self, content: str, filename: Optional[str] = None) -> Path:
        """Save Markdown report to output dir."""
        fname = filename or f"report_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        path = self.output_dir / fname
        path.write_text(content, encoding="utf-8")
        return path

    def export_tables_excel(
        self,
        ticker: str,
        *,
        technical_df: Optional[pd.DataFrame] = None,
        fundamental_df: Optional[pd.DataFrame] = None,
        risk_metrics: Optional[pd.Series] = None,
        forecasts: Optional[Dict[str, pd.DataFrame]] = None,
    ) -> Path:
        """Export key tables to a single Excel file (one sheet each)."""
        path = self.output_dir / f"analysis_{ticker}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            if risk_metrics is not None:
                risk_metrics.to_frame("value").to_excel(w, sheet_name="Risk")
            if fundamental_df is not None:
                fundamental_df.to_excel(w, sheet_name="Fundamentals", index=False)
            if technical_df is not None:
                technical_df.tail(252).to_excel(w, sheet_name="Technical")
            if forecasts:
                for name, df in forecasts.items():
                    if isinstance(df, pd.Series):
                        df.to_frame("forecast").to_excel(w, sheet_name=f"Forecast_{name}")
                    else:
                        df.to_excel(w, sheet_name=f"Forecast_{name}")
        return path
