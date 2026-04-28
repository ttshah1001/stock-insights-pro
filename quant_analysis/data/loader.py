"""
Market data loading and preprocessing.
Fetches OHLCV and fundamental data with caching and normalization.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Union

try:
    import yfinance as yf
except ImportError:
    yf = None

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config


class MarketDataLoader:
    """
    Load and preprocess market data from Yahoo Finance.
    Supports OHLCV, dividends, and fundamental data with optional caching.
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        use_cache: bool = True,
    ):
        self.cache_dir = cache_dir or config.DATA_DIR
        self.use_cache = use_cache
        if use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_ohlcv(
        self,
        tickers: Union[str, List[str]],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        period: Optional[str] = None,
        interval: str = "1d",
        auto_adjust: bool = True,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data. Returns MultiIndex (ticker, date) if multiple tickers.

        Parameters
        ----------
        tickers : str or list of str
        start, end : optional datetime
        period : optional str, e.g. '1y', '2y', '5y'
        interval : '1d', '1wk', '1mo'
        auto_adjust : adjust for splits/dividends
        """
        if yf is None:
            raise ImportError("yfinance is required. Install with: pip install yfinance")

        if end is None:
            end = datetime.now()
        if start is None and period is None:
            start = end - timedelta(days=config.DEFAULT_LOOKBACK_DAYS)
        if period is None and start is not None:
            period = None  # use start/end

        ticker_list = [tickers] if isinstance(tickers, str) else list(tickers)
        all_data = []

        for ticker in ticker_list:
            cache_key = f"{start.date() if start else 'na'}_{end.date() if end else 'na'}"
            cache_path = (
                self.cache_dir / f"ohlcv_{ticker}_{interval}_{cache_key}.csv"
                if (start or period) and self.use_cache
                else None
            )
            df = pd.DataFrame()
            if cache_path and cache_path.exists():
                df = pd.read_csv(cache_path, parse_dates=["date"])
                # Normalize column names (yfinance uses Open, High, Low, Close, Volume)
                col_map = {c: c.capitalize() for c in df.columns if c.lower() in ("open", "high", "low", "close", "volume")}
                if col_map:
                    df = df.rename(columns=col_map)
                if len(df) < 30:
                    cache_path.unlink(missing_ok=True)
                    df = pd.DataFrame()
            if df.empty:
                obj = yf.Ticker(ticker)
                if period:
                    df = obj.history(period=period, interval=interval, auto_adjust=auto_adjust)
                else:
                    df = obj.history(start=start, end=end, interval=interval, auto_adjust=auto_adjust)
                if df.empty and not period:
                    df = obj.history(period="1y", interval=interval, auto_adjust=auto_adjust)
                if df.empty and not period:
                    df = obj.history(period="2y", interval=interval, auto_adjust=auto_adjust)
                if df.empty:
                    continue
                df = df.rename_axis("date").reset_index()
                df["ticker"] = ticker
                if cache_path and self.use_cache:
                    df.to_csv(cache_path, index=False)
                all_data.append(df)
            else:
                df["ticker"] = ticker
                all_data.append(df)

        if not all_data:
            return pd.DataFrame()

        combined = pd.concat(all_data, ignore_index=True)
        combined["date"] = pd.to_datetime(combined["date"]).dt.tz_localize(None)
        combined = combined.set_index(["ticker", "date"]).sort_index()

        if len(ticker_list) == 1:
            combined = combined.droplevel("ticker")
        return combined

    def fetch_fundamentals(self, ticker: str) -> pd.Series:
        """Fetch key fundamental metrics for a single ticker."""
        if yf is None:
            raise ImportError("yfinance is required.")
        t = yf.Ticker(ticker)
        info = t.info
        # Map to standard names and numeric where possible
        mapping = {
            "marketCap": "market_cap",
            "trailingPE": "pe_ratio",
            "forwardPE": "forward_pe",
            "priceToBook": "pb_ratio",
            "trailingEps": "eps",
            "forwardEps": "forward_eps",
            "dividendYield": "dividend_yield",
            "payoutRatio": "payout_ratio",
            "returnOnEquity": "roe",
            "returnOnAssets": "roa",
            "debtToEquity": "debt_to_equity",
            "currentRatio": "current_ratio",
            "quickRatio": "quick_ratio",
            "revenueGrowth": "revenue_growth",
            "earningsGrowth": "earnings_growth",
            "profitMargins": "profit_margin",
            "operatingMargins": "operating_margin",
            "beta": "beta",
            "52WeekHigh": "high_52w",
            "52WeekLow": "low_52w",
        }
        out = {}
        for k, v in mapping.items():
            val = info.get(k)
            if val is not None and isinstance(val, (int, float)):
                out[v] = val
            elif val is not None:
                out[v] = val
        return pd.Series(out)

    def returns(
        self,
        prices: pd.DataFrame,
        field: str = "Close",
        log_returns: bool = False,
    ) -> pd.DataFrame:
        """Compute period returns from price series."""
        if field not in prices.columns:
            field = "Close" if "Close" in prices.columns else prices.columns[0]
        p = prices[field] if field in prices.columns else prices.iloc[:, 0]
        if log_returns:
            return np.log(p / p.shift(1))
        return p.pct_change()

    def volatility_annualized(
        self,
        returns: pd.Series,
        trading_days: int = config.TRADING_DAYS_PER_YEAR,
    ) -> float:
        """Annualized volatility (std of returns * sqrt(trading_days))."""
        return returns.std() * np.sqrt(trading_days)
