"""
Price and return forecasting: time series (ARIMA, exponential smoothing) and ML (Random Forest).
Designed for short-horizon predictions and strategy signals.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Optional, Tuple, List, Literal

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import config

try:
    from statsmodels.tsa.arima.model import ARIMA
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except ImportError:
    ARIMA = None
    ExponentialSmoothing = None

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.model_selection import TimeSeriesSplit
except ImportError:
    RandomForestRegressor = None
    StandardScaler = None
    TimeSeriesSplit = None


def _ensure_series(prices: pd.Series | pd.DataFrame) -> pd.Series:
    if isinstance(prices, pd.DataFrame):
        return prices["Close"] if "Close" in prices.columns else prices.iloc[:, 0]
    return prices


class PriceForecaster:
    """
    Multi-model forecaster for price/return series.
    Supports ARIMA, exponential smoothing, and Random Forest on lagged features.
    """

    def __init__(
        self,
        horizon: int = config.FORECAST_HORIZON_DAYS,
        train_ratio: float = config.TRAIN_TEST_SPLIT,
    ):
        self.horizon = horizon
        self.train_ratio = train_ratio
        self._arima_fit = None
        self._ets_fit = None
        self._rf_model = None
        self._rf_scaler = None
        self._last_prices = None

    def _train_test_split(
        self,
        series: pd.Series,
    ) -> Tuple[pd.Series, pd.Series]:
        n = len(series.dropna())
        train_size = int(n * self.train_ratio)
        if train_size < 30:
            train_size = min(30, n - 5)
        train = series.iloc[:train_size]
        test = series.iloc[train_size:]
        return train, test

    # -------------------------------------------------------------------------
    # ARIMA
    # -------------------------------------------------------------------------

    def fit_arima(
        self,
        prices: pd.Series | pd.DataFrame,
        order: Tuple[int, int, int] = config.ARIMA_ORDER,
    ) -> "PriceForecaster":
        """Fit ARIMA on log returns (or levels if preferred)."""
        if ARIMA is None:
            raise ImportError("statsmodels is required for ARIMA.")
        series = _ensure_series(prices).dropna()
        returns = np.log(series / series.shift(1)).dropna()
        self._arima_fit = ARIMA(returns, order=order).fit()
        self._last_prices = series
        return self

    def predict_arima(
        self,
        steps: Optional[int] = None,
    ) -> pd.Series:
        """Forecast log returns then convert to price level."""
        if self._arima_fit is None or self._last_prices is None:
            raise ValueError("Fit ARIMA first with fit_arima().")
        steps = steps or self.horizon
        fcast_returns = self._arima_fit.forecast(steps=steps)
        last_price = self._last_prices.iloc[-1]
        # Cumulative return -> price
        log_ret = fcast_returns
        if isinstance(log_ret, pd.Series):
            log_ret = log_ret.values
        prices = last_price * np.exp(np.cumsum(log_ret))
        return pd.Series(prices, index=range(1, steps + 1))

    # -------------------------------------------------------------------------
    # Exponential smoothing (ETS)
    # -------------------------------------------------------------------------

    def fit_ets(
        self,
        prices: pd.Series | pd.DataFrame,
        trend: Optional[Literal["add", "mul"]] = "add",
        seasonal: Optional[Literal["add", "mul"]] = None,
        seasonal_periods: Optional[int] = None,
    ) -> "PriceForecaster":
        """Fit Holt-Winters exponential smoothing."""
        if ExponentialSmoothing is None:
            raise ImportError("statsmodels is required for ETS.")
        series = _ensure_series(prices).dropna()
        kwargs = {"trend": trend}
        if seasonal and seasonal_periods:
            kwargs["seasonal"] = seasonal
            kwargs["seasonal_periods"] = seasonal_periods
        self._ets_fit = ExponentialSmoothing(series, **kwargs).fit()
        self._last_prices = series
        return self

    def predict_ets(self, steps: Optional[int] = None) -> pd.Series:
        if self._ets_fit is None:
            raise ValueError("Fit ETS first with fit_ets().")
        steps = steps or self.horizon
        return self._ets_fit.forecast(steps=steps)

    # -------------------------------------------------------------------------
    # Random Forest (lagged returns + volatility)
    # -------------------------------------------------------------------------

    def _build_features(self, series: pd.Series, lags: List[int]) -> Tuple[pd.DataFrame, pd.Series]:
        """Lagged returns and rolling volatility."""
        returns = series.pct_change().dropna()
        X_list = []
        for lag in lags:
            X_list.append(returns.shift(lag))
        vol = returns.rolling(20).std()
        vol = vol.shift(1)
        X_list.append(vol)
        X = pd.concat(X_list, axis=1)
        X.columns = [f"ret_lag_{l}" for l in lags] + ["vol_lag1"]
        y = returns
        common = X.dropna().index.intersection(y.dropna().index)
        X = X.loc[common]
        y = y.loc[common]
        return X, y

    def fit_rf(
        self,
        prices: pd.Series | pd.DataFrame,
        lags: Optional[List[int]] = None,
    ) -> "PriceForecaster":
        """Fit Random Forest on lagged returns and volatility."""
        if RandomForestRegressor is None or StandardScaler is None:
            raise ImportError("scikit-learn is required for RF forecaster.")
        series = _ensure_series(prices).dropna()
        lags = lags or [1, 2, 3, 5, 10]
        X, y = self._build_features(series, lags)
        if len(X) < 50:
            return self
        self._rf_scaler = StandardScaler()
        X_scaled = self._rf_scaler.fit_transform(X)
        self._rf_model = RandomForestRegressor(n_estimators=100, max_depth=5, random_state=42)
        self._rf_model.fit(X_scaled, y)
        self._last_prices = series
        self._rf_lags = lags
        self._rf_last_X = X.iloc[-1:]
        return self

    def predict_rf(self, steps: Optional[int] = None) -> pd.Series:
        """Multi-step forecast via recursive prediction (uses last known X then simulated)."""
        if self._rf_model is None or self._last_prices is None:
            raise ValueError("Fit RF first with fit_rf().")
        steps = steps or self.horizon
        series = self._last_prices
        preds = []
        for _ in range(steps):
            X, _ = self._build_features(series, self._rf_lags)
            if X.empty or X.iloc[-1].isna().any():
                break
            last = X.iloc[-1:].values
            last_scaled = self._rf_scaler.transform(last)
            r = self._rf_model.predict(last_scaled)[0]
            next_price = series.iloc[-1] * (1 + r)
            try:
                next_idx = series.index[-1] + pd.Timedelta(days=1)
            except TypeError:
                next_idx = series.index[-1] + 1
            series = pd.concat([series, pd.Series([next_price], index=[next_idx])])
            preds.append(next_price)
        return pd.Series(preds, index=range(1, len(preds) + 1))

    # -------------------------------------------------------------------------
    # Ensemble and convenience
    # -------------------------------------------------------------------------

    def fit(
        self,
        prices: pd.Series | pd.DataFrame,
        methods: Optional[List[str]] = None,
    ) -> "PriceForecaster":
        """Fit ARIMA, ETS, and RF (or subset)."""
        methods = methods or ["arima", "ets", "rf"]
        series = _ensure_series(prices).dropna()
        if "arima" in methods and ARIMA is not None:
            try:
                self.fit_arima(series)
            except Exception:
                pass
        if "ets" in methods and ExponentialSmoothing is not None:
            try:
                self.fit_ets(series)
            except Exception:
                pass
        if "rf" in methods and RandomForestRegressor is not None:
            try:
                self.fit_rf(series)
            except Exception:
                pass
        return self

    def predict(
        self,
        method: Literal["arima", "ets", "rf"] = "arima",
        steps: Optional[int] = None,
    ) -> pd.Series:
        """Single-model forecast."""
        steps = steps or self.horizon
        if method == "arima":
            return self.predict_arima(steps)
        if method == "ets":
            return self.predict_ets(steps)
        if method == "rf":
            return self.predict_rf(steps)
        raise ValueError("method must be one of arima, ets, rf.")
