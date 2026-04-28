"""
Backtesting engine: run strategy signals on historical data with transaction costs.
Produces equity curve, trade log, and performance summary.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional, Callable, Union

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config
from quant_analysis.risk.metrics import RiskAnalyzer


class BacktestEngine:
    """
    Backtest a strategy that produces signals (-1, 0, 1) from OHLCV or technical DataFrame.
    Assumes long-only or short-only positions sized by signal (no leverage scaling by default).
    """

    def __init__(
        self,
        transaction_cost_bps: float = config.DEFAULT_TRANSACTION_COST_BPS,
        slippage_bps: float = config.DEFAULT_SLIPPAGE_BPS,
        initial_capital: float = 1_000_000,
    ):
        self.tc_bps = transaction_cost_bps / 10_000
        self.slippage_bps = slippage_bps / 10_000
        self.initial_capital = initial_capital

    def run(
        self,
        prices: pd.Series,
        signals: pd.Series,
        position_size: Optional[Union[float, pd.Series]] = None,
    ) -> pd.DataFrame:
        """
        Run backtest. prices and signals must share the same index.
        signals: 1 = long, -1 = short, 0 = flat (or floats for partial exposure).
        position_size: optional scalar or series for dollar/weight exposure.
        Returns DataFrame with columns: equity, returns, position, trades, turnover.
        """
        common = prices.index.intersection(signals.index)
        prices = prices.reindex(common).ffill().dropna()
        signals = signals.reindex(common).ffill().fillna(0)
        if position_size is not None and isinstance(position_size, pd.Series):
            position_size = position_size.reindex(common).ffill().fillna(0)
        else:
            position_size = 1.0 if position_size is None else float(position_size)

        # Position: -1 to 1
        position = signals.astype(float).clip(-1, 1)
        if isinstance(position_size, pd.Series):
            position = position * position_size

        # Period returns from price
        ret = prices.pct_change()
        strategy_ret = position.shift(1) * ret  # previous period position * return

        # Transaction costs: |position change| * (tc + slippage)
        pos_change = position.diff().abs()
        cost = pos_change * (self.tc_bps + self.slippage_bps)
        strategy_ret = strategy_ret - cost
        strategy_ret = strategy_ret.fillna(0)

        # Equity curve
        equity = (1 + strategy_ret).cumprod() * self.initial_capital
        equity.iloc[0] = self.initial_capital

        # Trade count (approximate: count position sign changes that cross zero)
        pos_prev = position.shift(1).fillna(0)
        trades = ((position != 0) & (pos_prev != position)).astype(int).cumsum()

        out = pd.DataFrame(
            {
                "equity": equity,
                "returns": strategy_ret,
                "position": position,
                "turnover": pos_change,
                "trade_id": trades,
            },
            index=common,
        )
        return out

    def summary(
        self,
        backtest_result: pd.DataFrame,
        risk_free_rate: float = config.DEFAULT_RISK_FREE_RATE,
    ) -> pd.Series:
        """Performance summary from backtest result (equity and returns columns)."""
        ra = RiskAnalyzer(risk_free_rate=risk_free_rate)
        returns = backtest_result["returns"]
        total_return = (backtest_result["equity"].iloc[-1] / self.initial_capital) - 1
        n_trades = backtest_result["trade_id"].max() if "trade_id" in backtest_result.columns else 0
        s = ra.full_report(returns)
        s["total_return"] = total_return
        s["num_trades"] = n_trades
        s["final_equity"] = backtest_result["equity"].iloc[-1]
        return s
