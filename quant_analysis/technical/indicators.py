"""
Technical analysis: indicators, overlays, and trading signals.
Quant-grade implementations for traders and systematic strategies.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config

PARAMS = config.TECHNICAL_PARAMS


def _ensure_series(df: pd.DataFrame, column: str = "Close") -> pd.Series:
    if isinstance(df, pd.Series):
        return df
    return df[column] if column in df.columns else df.iloc[:, 0]


# -----------------------------------------------------------------------------
# Moving averages
# -----------------------------------------------------------------------------

def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


# -----------------------------------------------------------------------------
# Oscillators
# -----------------------------------------------------------------------------

def rsi(series: pd.Series, period: int = PARAMS["rsi_period"]) -> pd.Series:
    """Relative Strength Index (0–100)."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(period, min_periods=period).mean()
    avg_loss = loss.rolling(period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(
    series: pd.Series,
    fast: int = PARAMS["macd_fast"],
    slow: int = PARAMS["macd_slow"],
    signal: int = PARAMS["macd_signal"],
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """MACD line, signal line, histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def bollinger_bands(
    series: pd.Series,
    period: int = PARAMS["bollinger_period"],
    num_std: float = PARAMS["bollinger_std"],
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Middle (SMA), upper, lower bands."""
    middle = sma(series, period)
    std = series.rolling(period, min_periods=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    return middle, upper, lower


# -----------------------------------------------------------------------------
# Volatility & trend
# -----------------------------------------------------------------------------

def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = PARAMS["atr_period"]) -> pd.Series:
    """Average True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = PARAMS["adx_period"],
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """ADX, +DI, -DI."""
    prev_close = close.shift(1)
    plus_dm = high.diff().where((high.diff() > low.diff().abs()) & (high.diff() > 0), 0)
    minus_dm = (-low.diff()).where((low.diff() > high.diff().abs()) & (low.diff() > 0), 0)
    tr = atr(high, low, close, period=1)
    tr_smooth = tr.rolling(period).sum()
    plus_di = 100 * plus_dm.rolling(period).sum() / tr_smooth.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(period).sum() / tr_smooth.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx_series = dx.rolling(period).mean()
    return adx_series, plus_di, minus_di


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> Tuple[pd.Series, pd.Series]:
    """Stochastic %K and %D."""
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    d = k.rolling(d_period).mean()
    return k, d


# -----------------------------------------------------------------------------
# Volume
# -----------------------------------------------------------------------------

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(close.diff())
    direction.iloc[0] = 0
    return (direction * volume).cumsum()


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
    """Volume-Weighted Average Price (typical price * volume cumsum / volume cumsum)."""
    typical = (high + low + close) / 3
    return (typical * volume).cumsum() / volume.cumsum()


# -----------------------------------------------------------------------------
# Composite analyzer
# -----------------------------------------------------------------------------

class TechnicalAnalyzer:
    """
    Compute a full set of technical indicators and optional signals
    from OHLCV data for use in quant workflows.
    """

    def __init__(self, params: Optional[dict] = None):
        self.params = params or PARAMS

    def run(
        self,
        ohlcv: pd.DataFrame,
        price_column: str = "Close",
        include_volume: bool = True,
    ) -> pd.DataFrame:
        """
        Add technical indicator columns to a copy of the OHLCV DataFrame.
        """
        df = ohlcv.copy()
        close = _ensure_series(df, price_column)
        high = df["High"] if "High" in df.columns else close
        low = df["Low"] if "Low" in df.columns else close
        volume = df["Volume"] if "Volume" in df.columns else pd.Series(1, index=df.index)

        # Moving averages
        df["sma_short"] = sma(close, self.params["sma_short"])
        df["sma_long"] = sma(close, self.params["sma_long"])
        df["ema_short"] = ema(close, self.params["ema_short"])
        df["ema_long"] = ema(close, self.params["ema_long"])

        # RSI
        df["rsi"] = rsi(close, self.params["rsi_period"])

        # MACD
        macd_line, signal_line, hist = macd(
            close,
            self.params["macd_fast"],
            self.params["macd_slow"],
            self.params["macd_signal"],
        )
        df["macd"] = macd_line
        df["macd_signal"] = signal_line
        df["macd_hist"] = hist

        # Bollinger
        bb_mid, bb_upper, bb_lower = bollinger_bands(
            close,
            self.params["bollinger_period"],
            self.params["bollinger_std"],
        )
        df["bb_mid"] = bb_mid
        df["bb_upper"] = bb_upper
        df["bb_lower"] = bb_lower
        df["bb_width"] = (bb_upper - bb_lower) / bb_mid.replace(0, np.nan)
        df["bb_position"] = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)

        # ATR & ADX
        df["atr"] = atr(high, low, close, self.params["atr_period"])
        adx_series, plus_di, minus_di = adx(high, low, close, self.params["adx_period"])
        df["adx"] = adx_series
        df["di_plus"] = plus_di
        df["di_minus"] = minus_di

        # Stochastic
        stoch_k, stoch_d = stochastic(high, low, close)
        df["stoch_k"] = stoch_k
        df["stoch_d"] = stoch_d

        if include_volume and "Volume" in ohlcv.columns:
            df["obv"] = obv(close, volume)
            df["vwap"] = vwap(high, low, close, volume)

        return df

    def signals(self, ohlcv: pd.DataFrame) -> pd.DataFrame:
        """
        Add simple rule-based signals (1 = long, -1 = short, 0 = neutral).
        Based on RSI, MACD crossover, and moving average crossover.
        """
        df = self.run(ohlcv)
        close = _ensure_series(df, "Close")

        # RSI: oversold < 30, overbought > 70
        rsi_sig = np.where(df["rsi"] < 30, 1, np.where(df["rsi"] > 70, -1, 0))

        # MACD crossover
        macd_cross = np.sign(df["macd_hist"])
        macd_sig = np.where(
            (df["macd"] > df["macd_signal"]) & (df["macd"].shift(1) <= df["macd_signal"].shift(1)),
            1,
            np.where(
                (df["macd"] < df["macd_signal"]) & (df["macd"].shift(1) >= df["macd_signal"].shift(1)),
                -1,
                0,
            ),
        )

        # SMA crossover
        sma_sig = np.where(
            df["sma_short"] > df["sma_long"],
            1,
            np.where(df["sma_short"] < df["sma_long"], -1, 0),
        )

        df["signal_rsi"] = rsi_sig
        df["signal_macd"] = macd_sig
        df["signal_sma"] = sma_sig
        # Composite: majority vote (simplified)
        votes = np.stack([np.nan_to_num(rsi_sig), np.nan_to_num(macd_sig), np.nan_to_num(sma_sig)], axis=1)
        df["signal_composite"] = np.where(votes.sum(axis=1) > 0, 1, np.where(votes.sum(axis=1) < 0, -1, 0))
        return df
