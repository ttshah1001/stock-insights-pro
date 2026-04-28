"""
Risk metrics: VaR, CVaR, Sharpe, Sortino, drawdown, beta.
Institutional-grade calculations for portfolio and single-asset risk.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional, Union, Tuple, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config


def _ensure_returns(returns: Union[pd.Series, pd.DataFrame]) -> pd.Series:
    if isinstance(returns, pd.DataFrame):
        if "returns" in returns.columns:
            return returns["returns"]
        return returns.iloc[:, 0]
    return returns


class RiskAnalyzer:
    """
    Compute risk and performance metrics for return series.
    Used for risk reporting, attribution, and position sizing.
    """

    def __init__(
        self,
        risk_free_rate: float = config.DEFAULT_RISK_FREE_RATE,
        trading_days: int = config.TRADING_DAYS_PER_YEAR,
    ):
        self.risk_free_rate = risk_free_rate
        self.trading_days = trading_days
        self.rf_per_period = risk_free_rate / trading_days

    def annualized_return(self, returns: pd.Series) -> float:
        """Geometric annualized return."""
        r = _ensure_returns(returns).dropna()
        if len(r) < 2:
            return np.nan
        total = (1 + r).prod()
        n_years = len(r) / self.trading_days
        return total ** (1 / n_years) - 1 if n_years > 0 else np.nan

    def annualized_volatility(self, returns: pd.Series) -> float:
        """Annualized standard deviation of returns."""
        r = _ensure_returns(returns).dropna()
        return r.std() * np.sqrt(self.trading_days) if len(r) > 1 else np.nan

    def sharpe_ratio(
        self,
        returns: pd.Series,
        risk_free_rate: Optional[float] = None,
    ) -> float:
        """Sharpe ratio (annualized)."""
        r = _ensure_returns(returns).dropna()
        if len(r) < 2:
            return np.nan
        rf = (risk_free_rate or self.risk_free_rate) / self.trading_days
        excess = r - rf
        vol = r.std() * np.sqrt(self.trading_days)
        if vol <= 0:
            return np.nan
        return (excess.mean() * self.trading_days) / vol

    def sortino_ratio(
        self,
        returns: pd.Series,
        risk_free_rate: Optional[float] = None,
    ) -> float:
        """Sortino ratio (downside deviation)."""
        r = _ensure_returns(returns).dropna()
        if len(r) < 2:
            return np.nan
        rf = (risk_free_rate or self.risk_free_rate) / self.trading_days
        excess = r - rf
        downside = r[r < 0]
        if len(downside) == 0:
            return np.nan
        downside_std = downside.std() * np.sqrt(self.trading_days)
        if downside_std <= 0:
            return np.nan
        return (excess.mean() * self.trading_days) / downside_std

    def max_drawdown(self, returns: pd.Series) -> float:
        """Maximum drawdown (peak-to-trough decline)."""
        r = _ensure_returns(returns).dropna()
        if len(r) == 0:
            return np.nan
        cum = (1 + r).cumprod()
        running_max = cum.cummax()
        dd = (cum - running_max) / running_max
        return dd.min()

    def max_drawdown_duration(self, returns: pd.Series) -> int:
        """Length of the longest drawdown period (in periods)."""
        r = _ensure_returns(returns).dropna()
        if len(r) == 0:
            return 0
        cum = (1 + r).cumprod()
        running_max = cum.cummax()
        in_dd = cum < running_max
        # Count consecutive True
        groups = in_dd.ne(in_dd.shift()).cumsum()
        if not in_dd.any():
            return 0
        return in_dd.groupby(groups).sum().max()

    def var_historical(
        self,
        returns: pd.Series,
        confidence: float = 0.95,
    ) -> float:
        """Historical Value at Risk (negative of the (1-confidence) quantile)."""
        r = _ensure_returns(returns).dropna()
        if len(r) == 0:
            return np.nan
        return -np.quantile(r, 1 - confidence)

    def cvar_historical(
        self,
        returns: pd.Series,
        confidence: float = 0.95,
    ) -> float:
        """Conditional VaR (expected shortfall): average loss when VaR is exceeded."""
        r = _ensure_returns(returns).dropna()
        if len(r) == 0:
            return np.nan
        var = -np.quantile(r, 1 - confidence)
        tail = r[r <= -var]
        if len(tail) == 0:
            return var
        return -tail.mean()

    def var_parametric(
        self,
        returns: pd.Series,
        confidence: float = 0.95,
    ) -> float:
        """Parametric (Gaussian) VaR."""
        r = _ensure_returns(returns).dropna()
        if len(r) < 2:
            return np.nan
        mu = r.mean()
        sigma = r.std()
        from scipy import stats
        z = stats.norm.ppf(1 - confidence)
        return -(mu + z * sigma)

    def beta(
        self,
        asset_returns: pd.Series,
        market_returns: pd.Series,
    ) -> float:
        """Market beta (CAPM)."""
        a = _ensure_returns(asset_returns).dropna()
        m = _ensure_returns(market_returns).dropna()
        common_idx = a.index.intersection(m.index)
        if len(common_idx) < 2:
            return np.nan
        a_aligned = a.reindex(common_idx).dropna()
        m_aligned = m.reindex(common_idx).dropna()
        common_idx = a_aligned.index.intersection(m_aligned.index)
        a_aligned = a_aligned.loc[common_idx]
        m_aligned = m_aligned.loc[common_idx]
        cov = np.cov(a_aligned, m_aligned)
        var_m = cov[1, 1]
        if var_m <= 0:
            return np.nan
        return cov[0, 1] / var_m

    def calmar_ratio(
        self,
        returns: pd.Series,
        lookback_periods: Optional[int] = None,
    ) -> float:
        """Calmar ratio: annualized return / abs(max drawdown)."""
        r = _ensure_returns(returns).dropna()
        if len(r) < 2:
            return np.nan
        ann_ret = self.annualized_return(r)
        mdd = self.max_drawdown(r)
        if mdd >= 0 or mdd == 0:
            return np.nan
        return ann_ret / abs(mdd)

    def full_report(
        self,
        returns: pd.Series,
        confidence_levels: Optional[List[float]] = None,
    ) -> pd.Series:
        """
        Single return series: full set of risk/performance metrics.
        """
        r = _ensure_returns(returns).dropna()
        confidence_levels = confidence_levels or list(config.VAR_CONFIDENCE_LEVELS)
        out = {
            "annualized_return": self.annualized_return(r),
            "annualized_volatility": self.annualized_volatility(r),
            "sharpe_ratio": self.sharpe_ratio(r),
            "sortino_ratio": self.sortino_ratio(r),
            "max_drawdown": self.max_drawdown(r),
            "max_drawdown_duration": self.max_drawdown_duration(r),
            "calmar_ratio": self.calmar_ratio(r),
        }
        for c in confidence_levels:
            out[f"var_historical_{int(c*100)}"] = self.var_historical(r, c)
            out[f"cvar_historical_{int(c*100)}"] = self.cvar_historical(r, c)
        out["var_parametric_95"] = self.var_parametric(r, 0.95)
        return pd.Series(out)
