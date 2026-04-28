"""
Configuration for the Quant Stock Analysis framework.
Centralizes parameters used across modules for reproducibility.
"""

from pathlib import Path
from datetime import datetime, timedelta

# -----------------------------------------------------------------------------
# Paths
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data_cache"
OUTPUT_DIR = PROJECT_ROOT / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"

for d in (DATA_DIR, OUTPUT_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# -----------------------------------------------------------------------------
# Data parameters
# -----------------------------------------------------------------------------
DEFAULT_LOOKBACK_DAYS = 252 * 2  # ~2 years of daily data
DEFAULT_RISK_FREE_RATE = 0.04  # Annualized (e.g., 10Y Treasury proxy)
TRADING_DAYS_PER_YEAR = 252

# -----------------------------------------------------------------------------
# Technical analysis
# -----------------------------------------------------------------------------
TECHNICAL_PARAMS = {
    "rsi_period": 14,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "bollinger_period": 20,
    "bollinger_std": 2.0,
    "atr_period": 14,
    "adx_period": 14,
    "sma_short": 20,
    "sma_long": 50,
    "ema_short": 12,
    "ema_long": 26,
}

# -----------------------------------------------------------------------------
# Risk metrics
# -----------------------------------------------------------------------------
VAR_CONFIDENCE_LEVELS = (0.95, 0.99)
CVAR_CONFIDENCE_LEVELS = (0.95, 0.99)

# -----------------------------------------------------------------------------
# Backtesting
# -----------------------------------------------------------------------------
DEFAULT_TRANSACTION_COST_BPS = 10  # basis points per trade
DEFAULT_SLIPPAGE_BPS = 5

# -----------------------------------------------------------------------------
# Forecasting
# -----------------------------------------------------------------------------
FORECAST_HORIZON_DAYS = 5
ARIMA_ORDER = (2, 1, 2)  # (p, d, q) - tune per ticker
TRAIN_TEST_SPLIT = 0.8  # 80% train, 20% test for ML

# -----------------------------------------------------------------------------
# Factor model (Fama-French style)
# -----------------------------------------------------------------------------
FACTOR_LOOKBACK_MONTHS = 60
MOMENTUM_LOOKBACK_MONTHS = 12
VALUE_LOOKBACK_MONTHS = 1  # use latest fundamentals

# -----------------------------------------------------------------------------
# Daily trading model
# -----------------------------------------------------------------------------
# Default watchlist for daily pattern analysis (customize in run_daily_analysis.py)
DEFAULT_WATCHLIST = [
    "SPY",   # S&P 500
    "QQQ",   # Nasdaq 100
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
]
DAILY_MODEL_LOOKBACK_DAYS = 126  # ~6 months for indicators
