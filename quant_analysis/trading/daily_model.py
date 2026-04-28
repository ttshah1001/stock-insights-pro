"""
Daily trading model: analyzes market patterns and produces BUY/SELL/HOLD
recommendations with conviction, reasoning, and risk-based stop/target levels.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config
from quant_analysis.technical.indicators import TechnicalAnalyzer


@dataclass
class TradeRecommendation:
    """Single ticker recommendation from the daily model."""

    ticker: str
    action: str  # "BUY" | "SELL" | "HOLD"
    conviction: float  # 0–100 (strength of signal)
    reasoning: List[str] = field(default_factory=list)
    current_price: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_level: str = "MEDIUM"  # LOW | MEDIUM | HIGH
    trend_strength: Optional[float] = None  # ADX
    rsi: Optional[float] = None
    atr_pct: Optional[float] = None  # ATR as % of price (volatility)
    signal_rsi: int = 0
    signal_macd: int = 0
    signal_sma: int = 0


class DailyTradingModel:
    """
    Analyzes daily market patterns using technical indicators and produces
    actionable trade recommendations: BUY, SELL, or HOLD with conviction,
    reasoning, and suggested stop-loss/take-profit levels.
    """

    def __init__(
        self,
        buy_threshold: float = 55.0,   # conviction above this -> BUY
        sell_threshold: float = 45.0,  # conviction below this -> SELL
        atr_stop_mult: float = 2.0,    # stop = entry ± atr_stop_mult * ATR
        atr_target_mult: float = 3.0,  # target = entry ± atr_target_mult * ATR
        min_adx_trend: float = 20.0,   # ADX above this = trending (stronger signal)
        technical_params: Optional[dict] = None,
    ):
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.atr_stop_mult = atr_stop_mult
        self.atr_target_mult = atr_target_mult
        self.min_adx_trend = min_adx_trend
        self.analyzer = TechnicalAnalyzer(params=technical_params or config.TECHNICAL_PARAMS)

    def _conviction_from_signals(
        self,
        signal_rsi: int,
        signal_macd: int,
        signal_sma: int,
        rsi: float,
        macd_hist: float,
        adx: float,
    ) -> Tuple[float, List[str]]:
        """
        Map technical signals to a 0–100 conviction score (bullish).
        Higher = more bullish, lower = more bearish.
        Returns (conviction, list of reasoning strings).
        """
        reasons = []
        # Discrete signals: -1, 0, 1 -> contribute to score
        votes = [signal_rsi, signal_macd, signal_sma]
        vote_sum = sum(votes)
        # Base: map [-3, 3] to [0, 100] with 50 neutral
        base = 50.0 + (vote_sum / 3.0) * 25.0  # each vote ± ~8.3

        # RSI tilt: oversold (RSI<30) -> boost bullish, overbought (RSI>70) -> boost bearish
        if not np.isnan(rsi):
            if rsi < 35:
                base += 8
                reasons.append(f"RSI oversold ({rsi:.0f})")
            elif rsi > 65:
                base -= 8
                reasons.append(f"RSI overbought ({rsi:.0f})")
            elif rsi < 45:
                base += 3
            elif rsi > 55:
                base -= 3

        # MACD histogram direction (momentum)
        if not np.isnan(macd_hist):
            if macd_hist > 0:
                base += 5
                reasons.append("MACD bullish momentum")
            else:
                base -= 5
                reasons.append("MACD bearish momentum")

        # ADX: strong trend reinforces signal
        if not np.isnan(adx) and adx >= self.min_adx_trend:
            if vote_sum > 0:
                base += 5
                reasons.append(f"Strong uptrend (ADX {adx:.0f})")
            elif vote_sum < 0:
                base -= 5
                reasons.append(f"Strong downtrend (ADX {adx:.0f})")

        conviction = float(np.clip(base, 0.0, 100.0))
        return conviction, reasons

    def _action_from_conviction(self, conviction: float) -> str:
        if conviction >= self.buy_threshold:
            return "BUY"
        if conviction <= self.sell_threshold:
            return "SELL"
        return "HOLD"

    def _risk_level(self, atr_pct: Optional[float], volatility_annual: Optional[float]) -> str:
        """Classify risk as LOW / MEDIUM / HIGH from volatility."""
        vol = atr_pct or (volatility_annual or 0) * 0.1  # rough daily vol proxy
        if vol is None or vol <= 0:
            return "MEDIUM"
        if vol > 0.03:  # >3% daily move
            return "HIGH"
        if vol < 0.015:
            return "LOW"
        return "MEDIUM"

    def analyze(
        self,
        ohlcv: pd.DataFrame,
        ticker: str = "UNKNOWN",
        use_forecast_direction: bool = False,
        forecast_return_1d: Optional[float] = None,
    ) -> TradeRecommendation:
        """
        Run daily pattern analysis on OHLCV and return one TradeRecommendation.

        Parameters
        ----------
        ohlcv : DataFrame with OHLCV (and optional Volume)
        ticker : symbol for the recommendation
        use_forecast_direction : if True, use forecast_return_1d to nudge conviction
        forecast_return_1d : expected 1-day return from a forecaster (e.g. positive = bullish)
        """
        if ohlcv.empty or len(ohlcv) < 2:
            return TradeRecommendation(
                ticker=ticker,
                action="HOLD",
                conviction=50.0,
                reasoning=["Insufficient data for analysis."],
            )

        tech_df = self.analyzer.signals(ohlcv)
        last = tech_df.iloc[-1]
        close = last["Close"] if "Close" in tech_df.columns else tech_df["Close"].iloc[-1]
        current_price = float(close)

        # Latest indicator values
        rsi_val = last.get("rsi", np.nan)
        macd_hist = last.get("macd_hist", np.nan)
        adx_val = last.get("adx", np.nan)
        atr_val = last.get("atr", np.nan)
        signal_rsi = int(np.nan_to_num(last.get("signal_rsi", 0)))
        signal_macd = int(np.nan_to_num(last.get("signal_macd", 0)))
        signal_sma = int(np.nan_to_num(last.get("signal_sma", 0)))

        conviction, reasons = self._conviction_from_signals(
            signal_rsi, signal_macd, signal_sma, rsi_val, macd_hist, adx_val
        )

        if use_forecast_direction and forecast_return_1d is not None:
            if forecast_return_1d > 0.005:
                conviction = min(100, conviction + 5)
                reasons.append("Model forecast: bullish short-term")
            elif forecast_return_1d < -0.005:
                conviction = max(0, conviction - 5)
                reasons.append("Model forecast: bearish short-term")

        action = self._action_from_conviction(conviction)
        atr_pct = (float(atr_val) / current_price) if (atr_val and current_price) else None

        # Stop-loss and take-profit from ATR
        stop_loss = None
        take_profit = None
        if atr_val and current_price:
            atr_f = float(atr_val)
            if action == "BUY":
                stop_loss = current_price - self.atr_stop_mult * atr_f
                take_profit = current_price + self.atr_target_mult * atr_f
            elif action == "SELL":
                stop_loss = current_price + self.atr_stop_mult * atr_f
                take_profit = current_price - self.atr_target_mult * atr_f

        risk_level = self._risk_level(atr_pct, None)

        return TradeRecommendation(
            ticker=ticker,
            action=action,
            conviction=conviction,
            reasoning=reasons if reasons else [f"Composite signal: {action} (conviction {conviction:.0f})"],
            current_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_level=risk_level,
            trend_strength=float(adx_val) if not np.isnan(adx_val) else None,
            rsi=float(rsi_val) if not np.isnan(rsi_val) else None,
            atr_pct=atr_pct,
            signal_rsi=signal_rsi,
            signal_macd=signal_macd,
            signal_sma=signal_sma,
        )

    def analyze_watchlist(
        self,
        ohlcv_by_ticker: dict[str, pd.DataFrame],
        use_forecast: bool = False,
        forecast_returns: Optional[dict[str, float]] = None,
    ) -> List[TradeRecommendation]:
        """Run analysis for multiple tickers. Returns list of TradeRecommendation."""
        forecast_returns = forecast_returns or {}
        out = []
        for ticker, ohlcv in ohlcv_by_ticker.items():
            rec = self.analyze(
                ohlcv,
                ticker=ticker,
                use_forecast_direction=use_forecast,
                forecast_return_1d=forecast_returns.get(ticker),
            )
            out.append(rec)
        return out
