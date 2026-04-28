"""
Factor model: value, momentum, size, volatility (Fama-French style).
Used for alpha decomposition and risk attribution.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional, List, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quant_analysis.data.loader import MarketDataLoader
import config


class FactorModel:
    """
    Build and expose factor exposures and factor returns for a single name or universe.
    Simplified Fama-French style: Value (e.g. E/P, B/P proxy), Momentum, Size (market cap), Volatility.
    """

    def __init__(self, data_loader: Optional[MarketDataLoader] = None):
        self.loader = data_loader or MarketDataLoader()

    def value_factor_proxy(self, ticker: str) -> Optional[float]:
        """
        Value factor proxy: inverse of P/E (earnings yield). Higher = more value.
        """
        m = self.loader.fetch_fundamentals(ticker)
        pe = m.get("pe_ratio")
        if pe is None or pe <= 0 or not np.isfinite(pe):
            return None
        return 1.0 / pe

    def momentum_factor(
        self,
        prices: pd.Series,
        lookback_months: int = 12,
        trading_days_per_month: int = 21,
    ) -> float:
        """
        Momentum: total return over lookback period. Annualized for comparability.
        """
        if prices is None or len(prices) < lookback_months * trading_days_per_month:
            return np.nan
        lookback = lookback_months * trading_days_per_month
        start_price = prices.iloc[-lookback]
        end_price = prices.iloc[-1]
        if start_price <= 0:
            return np.nan
        total_ret = (end_price / start_price) - 1
        # Annualize
        years = lookback / config.TRADING_DAYS_PER_YEAR
        return (1 + total_ret) ** (1 / years) - 1 if years > 0 else total_ret

    def size_factor_proxy(self, ticker: str) -> Optional[float]:
        """
        Size factor: log market cap. Smaller cap = higher size factor exposure (small-cap premium).
        """
        m = self.loader.fetch_fundamentals(ticker)
        mc = m.get("market_cap")
        if mc is None or mc <= 0 or not np.isfinite(mc):
            return None
        return np.log1p(mc)

    def volatility_factor(
        self,
        returns: pd.Series,
        trading_days: int = config.TRADING_DAYS_PER_YEAR,
    ) -> float:
        """
        Volatility factor: annualized return volatility. Higher vol = low vol factor exposure.
        """
        if returns is None or len(returns.dropna()) < 20:
            return np.nan
        return returns.std() * np.sqrt(trading_days)

    def factor_exposures_single(
        self,
        ticker: str,
        prices: Optional[pd.Series] = None,
        returns: Optional[pd.Series] = None,
    ) -> pd.Series:
        """
        Single-ticker factor exposures: value, momentum, size, volatility.
        Prices/returns can be passed from existing OHLCV pipeline.
        """
        if prices is None and returns is None:
            ohlcv = self.loader.fetch_ohlcv(ticker, period="2y")
            if ohlcv.empty:
                return pd.Series(dtype=float)
            prices = ohlcv["Close"] if "Close" in ohlcv.columns else ohlcv.iloc[:, 0]
            returns = prices.pct_change()
        elif prices is not None and returns is None:
            returns = prices.pct_change()
        elif returns is not None and prices is None:
            prices = (1 + returns).cumprod()

        exposures = {}
        v = self.value_factor_proxy(ticker)
        if v is not None:
            exposures["value_earnings_yield"] = v
        exposures["momentum_12m"] = self.momentum_factor(prices)
        s = self.size_factor_proxy(ticker)
        if s is not None:
            exposures["size_log_mcap"] = s
        exposures["volatility_ann"] = self.volatility_factor(returns)
        return pd.Series(exposures)
