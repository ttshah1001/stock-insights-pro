# Quant Stock Market Analysis

A **quantitative stock market prediction and analysis framework** for investment bankers, traders, and quant traders. It provides institutional-style analytics: technical and fundamental analysis, factor exposures, risk metrics, time-series and ML forecasting, backtesting, and report generation.

## Features

- **Data**: OHLCV and fundamental data via Yahoo Finance with optional caching
- **Technical analysis**: RSI, MACD, Bollinger Bands, ATR, ADX, Stochastic, OBV, VWAP; rule-based signals
- **Fundamental analysis**: Valuation (P/E, P/B, dividend yield), profitability (ROE, ROA, margins), leverage (D/E, current/quick ratio), growth
- **Factor model**: Value (earnings yield), momentum (12m), size (log market cap), volatility (annualized)
- **Risk metrics**: Sharpe, Sortino, Calmar, max drawdown, VaR/CVaR (historical & parametric), beta
- **Forecasting**: ARIMA, exponential smoothing (ETS), Random Forest on lagged returns
- **Backtesting**: Signal-based backtester with transaction costs and slippage
- **Reporting**: Markdown and Excel export with consolidated metrics
- **Daily trading model**: Pattern-based BUY/SELL/HOLD recommendations with conviction, stop-loss/targets, and risk level

## Installation

```bash
cd quant-stock-analysis
pip install -r requirements.txt
pip install .   # optional native matching engine
```

Requires Python 3.9+ (and a C++17 compiler for the optional native module).

## Quick Start

**Daily trading analysis (how to invest / trade today):**

```bash
# Run daily pattern analysis on default watchlist (SPY, QQQ, AAPL, MSFT, etc.)
python run_daily_analysis.py

# Custom tickers
python run_daily_analysis.py AAPL MSFT GOOGL NVDA

# Save Markdown report and JSON
python run_daily_analysis.py --output output/daily_report.md --json
```

**Full pipeline (single or multiple tickers):**

```bash
# Analyze AAPL, write report and Excel to output/reports
python run_analysis.py AAPL --period 2y --report

# Multiple tickers, 1 year, no backtest
python run_analysis.py AAPL MSFT GOOGL --period 1y --report --no-backtest
```

**Programmatic usage:**

```python
from quant_analysis import (
    MarketDataLoader,
    TechnicalAnalyzer,
    FundamentalAnalyzer,
    RiskAnalyzer,
    PriceForecaster,
    BacktestEngine,
    ReportGenerator,
)

# Load data
loader = MarketDataLoader()
ohlcv = loader.fetch_ohlcv("AAPL", period="2y")
returns = loader.returns(ohlcv, field="Close")

# Technical indicators + signals
tech = TechnicalAnalyzer()
tech_df = tech.signals(ohlcv)  # RSI, MACD, SMA cross, composite signal

# Risk
risk = RiskAnalyzer()
metrics = risk.full_report(returns)  # Sharpe, Sortino, VaR, max DD, etc.

# Fundamentals
fund = FundamentalAnalyzer(loader)
fund_df = fund.full_report("AAPL")

# Factor exposures (value, momentum, size, volatility)
from quant_analysis.fundamental import FactorModel
factors = FactorModel(loader)
exposures = factors.factor_exposures_single("AAPL", prices=ohlcv["Close"], returns=returns)

# Forecast (ARIMA / ETS / RF)
forecaster = PriceForecaster(horizon=5)
forecaster.fit(ohlcv["Close"], methods=["arima", "ets", "rf"])
pred_arima = forecaster.predict(method="arima", steps=5)

# Backtest technical composite signal
backtest = BacktestEngine(transaction_cost_bps=10)
result = backtest.run(ohlcv["Close"], tech_df["signal_composite"])
summary = backtest.summary(result)
```

## Project Structure

```
quant-stock-analysis/
├── config.py              # Central parameters (lookback, risk-free rate, etc.)
├── run_analysis.py        # CLI pipeline runner
├── requirements.txt
├── data_cache/            # Cached OHLCV (created on first run)
├── output/
│   └── reports/           # Generated Markdown and Excel
└── quant_analysis/
    ├── data/              # Market data loading
    ├── technical/         # Indicators and signals
    ├── fundamental/       # Ratios and factor model
    ├── risk/              # VaR, Sharpe, drawdown, beta
    ├── models/            # ARIMA, ETS, RF forecaster
    ├── backtest/          # Backtest engine
    ├── trading/           # Daily trading model (BUY/SELL/HOLD)
    └── report/            # Markdown/Excel report generator
```

**Daily model programmatic usage:**

```python
from quant_analysis import MarketDataLoader, DailyTradingModel

loader = MarketDataLoader()
model = DailyTradingModel()
ohlcv = loader.fetch_ohlcv("AAPL", period="6mo")
rec = model.analyze(ohlcv, ticker="AAPL")
print(rec.action)       # BUY | SELL | HOLD
print(rec.conviction)   # 0-100
print(rec.reasoning)    # list of reasons
print(rec.stop_loss, rec.take_profit)  # ATR-based levels
```

## Configuration

Edit `config.py` to set:

- `DEFAULT_LOOKBACK_DAYS`, `DEFAULT_RISK_FREE_RATE`, `TRADING_DAYS_PER_YEAR`
- Technical periods (RSI, MACD, Bollinger, ATR, ADX)
- VaR/CVaR confidence levels
- Backtest transaction cost and slippage (bps)
- Forecast horizon and ARIMA order

## Web app (Flask)

A local web UI provides **real-time market data**, **technical analysis**, and **quant trading advice**.

1. **Set your Polygon.io API key** (for real-time data; optional—falls back to Yahoo Finance):
   ```bash
   cp .env.example .env
   # Edit .env and set POLYGON_API_KEY=your_key
   ```

2. **Install and run**:
   ```bash
   pip install -r requirements.txt
   python app.py
   ```
   Then open **http://127.0.0.1:5000** in your browser.

3. **Tabs**:
   - **Market Data**: Enter a ticker, get latest quote (Polygon real-time or yfinance), and view a price history chart.
   - **Analysis**: Technical indicators (RSI, MACD, Bollinger, ATR, ADX, etc.) and risk metrics (Sharpe, Sortino, max drawdown, VaR).
   - **Quant & Advice**: Daily BUY/SELL/HOLD recommendations with conviction, stop-loss/targets, and reasoning. Use the default watchlist or enter comma-separated tickers.

## Disclaimer

This framework is for **research and education**. It is not investment advice. Past performance does not guarantee future results. Use at your own risk.
