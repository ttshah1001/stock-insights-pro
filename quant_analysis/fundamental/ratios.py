"""
Fundamental analysis: valuation ratios, profitability, leverage, and growth.
Used for equity screening and factor construction.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional, Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quant_analysis.data.loader import MarketDataLoader
import config


class FundamentalAnalyzer:
    """
    Compute and interpret fundamental metrics from raw data or yfinance info.
    Suitable for equity research and quantitative screening.
    """

    def __init__(self, data_loader: Optional[MarketDataLoader] = None):
        self.loader = data_loader or MarketDataLoader()

    def get_metrics(self, ticker: str) -> pd.Series:
        """Fetch and return fundamental metrics for a ticker."""
        return self.loader.fetch_fundamentals(ticker)

    def valuation_scores(self, metrics: pd.Series) -> Dict[str, Any]:
        """
        Normalize valuation metrics into comparable scores (e.g. lower P/E = better value).
        Returns dict of raw values and percentile-style scores if benchmarks were available.
        """
        out = {}
        if "pe_ratio" in metrics.index and pd.notna(metrics.get("pe_ratio")):
            pe = metrics["pe_ratio"]
            out["pe_ratio"] = pe
            # Inverse: lower PE = higher value score (0-100 scale, arbitrary without cross-section)
            out["pe_score"] = 100 / (1 + pe) if pe and pe > 0 else np.nan
        if "pb_ratio" in metrics.index and pd.notna(metrics.get("pb_ratio")):
            pb = metrics["pb_ratio"]
            out["pb_ratio"] = pb
            out["pb_score"] = 100 / (1 + pb) if pb and pb > 0 else np.nan
        if "dividend_yield" in metrics.index and pd.notna(metrics.get("dividend_yield")):
            dy = metrics["dividend_yield"]
            out["dividend_yield"] = dy if dy is None or dy <= 1 else dy  # sometimes yfinance gives decimal
            out["yield_score"] = min(100, (dy or 0) * 100)  # higher yield = better for income
        return out

    def profitability_scores(self, metrics: pd.Series) -> Dict[str, Any]:
        """ROE, ROA, margins -> scores (higher = better)."""
        out = {}
        for key, name in [("roe", "roe"), ("roa", "roa"), ("profit_margin", "profit_margin"), ("operating_margin", "operating_margin")]:
            if key in metrics.index and pd.notna(metrics.get(key)):
                v = metrics[key]
                if isinstance(v, (int, float)) and v is not None:
                    out[name] = v
                    # Scale to 0-100 for display (e.g. ROE 0.2 -> 20)
                    out[f"{name}_score"] = min(100, max(0, v * 100))
        return out

    def leverage_scores(self, metrics: pd.Series) -> Dict[str, Any]:
        """Debt/equity, current ratio, quick ratio (lower D/E = safer, higher CR/QR = safer)."""
        out = {}
        if "debt_to_equity" in metrics.index and pd.notna(metrics.get("debt_to_equity")):
            dte = metrics["debt_to_equity"]
            out["debt_to_equity"] = dte
            out["debt_to_equity_score"] = 100 / (1 + dte) if dte is not None and dte >= 0 else np.nan
        if "current_ratio" in metrics.index and pd.notna(metrics.get("current_ratio")):
            cr = metrics["current_ratio"]
            out["current_ratio"] = cr
            out["current_ratio_score"] = min(100, (cr or 0) * 25)  # 4+ = cap at 100
        if "quick_ratio" in metrics.index and pd.notna(metrics.get("quick_ratio")):
            qr = metrics["quick_ratio"]
            out["quick_ratio"] = qr
            out["quick_ratio_score"] = min(100, (qr or 0) * 25)
        return out

    def growth_scores(self, metrics: pd.Series) -> Dict[str, Any]:
        """Revenue and earnings growth (higher = better)."""
        out = {}
        for key in ["revenue_growth", "earnings_growth"]:
            if key in metrics.index and pd.notna(metrics.get(key)):
                v = metrics[key]
                if v is not None:
                    out[key] = v
                    # Often reported as decimal (0.15 = 15%)
                    pct = v * 100 if abs(v) <= 2 else v
                    out[f"{key}_score"] = min(100, max(-100, pct + 50))  # shift so 0% -> 50
        return out

    def full_report(self, ticker: str) -> pd.DataFrame:
        """
        Single-ticker fundamental report: all metrics and derived scores
        in a flat structure for export or display.
        """
        metrics = self.get_metrics(ticker)
        rows = []
        for name, func in [
            ("valuation", self.valuation_scores),
            ("profitability", self.profitability_scores),
            ("leverage", self.leverage_scores),
            ("growth", self.growth_scores),
        ]:
            d = func(metrics)
            for k, v in d.items():
                rows.append({"category": name, "metric": k, "value": v})
        return pd.DataFrame(rows)
