#!/usr/bin/env python3
"""
Quant Stock Market Analysis — Full pipeline runner.
Usage:
  python run_analysis.py AAPL
  python run_analysis.py AAPL MSFT GOOGL --period 1y --report
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Project root
ROOT = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT))

import pandas as pd
import config
from quant_analysis.data.loader import MarketDataLoader
from quant_analysis.technical.indicators import TechnicalAnalyzer
from quant_analysis.fundamental.ratios import FundamentalAnalyzer
from quant_analysis.fundamental.factors import FactorModel
from quant_analysis.risk.metrics import RiskAnalyzer
from quant_analysis.models.forecaster import PriceForecaster
from quant_analysis.backtest.engine import BacktestEngine
from quant_analysis.report.generator import ReportGenerator


def run_single_ticker(
    ticker: str,
    period: str = "2y",
    generate_report: bool = True,
    run_backtest: bool = True,
):
    """Run full quantitative analysis for one ticker."""
    loader = MarketDataLoader(use_cache=True)
    tech = TechnicalAnalyzer()
    fund = FundamentalAnalyzer(loader)
    factors = FactorModel(loader)
    risk = RiskAnalyzer(
        risk_free_rate=config.DEFAULT_RISK_FREE_RATE,
        trading_days=config.TRADING_DAYS_PER_YEAR,
    )
    forecaster = PriceForecaster(horizon=config.FORECAST_HORIZON_DAYS)
    backtest = BacktestEngine(
        transaction_cost_bps=config.DEFAULT_TRANSACTION_COST_BPS,
        initial_capital=1_000_000,
    )
    reporter = ReportGenerator(config.REPORTS_DIR)

    # 1) OHLCV
    ohlcv = loader.fetch_ohlcv(ticker, period=period)
    if ohlcv.empty:
        print(f"No data for {ticker}. Skip.")
        return None
    if isinstance(ohlcv.index, pd.MultiIndex):
        ohlcv = ohlcv.loc[ticker]
    close = ohlcv["Close"] if "Close" in ohlcv.columns else ohlcv.iloc[:, 0]
    returns = loader.returns(ohlcv, field="Close")

    # 2) Technical
    tech_df = tech.signals(ohlcv)

    # 3) Risk
    risk_metrics = risk.full_report(returns)

    # 4) Fundamental
    try:
        fund_df = fund.full_report(ticker)
    except Exception:
        fund_df = None

    # 5) Factor exposures
    try:
        exposures = factors.factor_exposures_single(ticker, prices=close, returns=returns)
    except Exception:
        exposures = None

    # 6) Forecasts
    forecasts = {}
    try:
        forecaster.fit(close, methods=["arima", "ets", "rf"])
        for m in ["arima", "ets", "rf"]:
            try:
                forecasts[m] = forecaster.predict(method=m, steps=config.FORECAST_HORIZON_DAYS)
            except Exception:
                pass
    except Exception:
        pass

    # 7) Backtest (composite technical signal)
    backtest_summary = None
    if run_backtest and "signal_composite" in tech_df.columns:
        res = backtest.run(close, tech_df["signal_composite"])
        backtest_summary = backtest.summary(res)

    # 8) Report
    if generate_report:
        md = reporter.generate_markdown(
            ticker,
            technical_df=tech_df,
            fundamental_df=fund_df,
            factor_exposures=exposures,
            risk_metrics=risk_metrics,
            forecasts=forecasts or None,
            backtest_summary=backtest_summary,
        )
        path = reporter.save_markdown(md, filename=f"report_{ticker}.md")
        print(f"Report saved: {path}")
        try:
            reporter.export_tables_excel(
                ticker,
                technical_df=tech_df,
                fundamental_df=fund_df,
                risk_metrics=risk_metrics,
                forecasts=forecasts,
            )
            print(f"Excel export in {reporter.output_dir}")
        except Exception as e:
            print(f"Excel export skipped: {e}")

    return {
        "ticker": ticker,
        "ohlcv": ohlcv,
        "technical": tech_df,
        "risk": risk_metrics,
        "fundamental": fund_df,
        "factor_exposures": exposures,
        "forecasts": forecasts,
        "backtest_summary": backtest_summary,
    }


def main():
    import pandas as pd  # for MultiIndex check

    parser = argparse.ArgumentParser(description="Quant Stock Analysis Pipeline")
    parser.add_argument("tickers", nargs="+", help="Ticker symbols (e.g. AAPL MSFT)")
    parser.add_argument("--period", default="2y", help="Data period (e.g. 1y, 2y, 5y)")
    parser.add_argument("--report", action="store_true", help="Generate Markdown + Excel report")
    parser.add_argument("--no-backtest", action="store_true", help="Skip backtest")
    args = parser.parse_args()

    for ticker in args.tickers:
        run_single_ticker(
            ticker,
            period=args.period,
            generate_report=args.report,
            run_backtest=not args.no_backtest,
        )


if __name__ == "__main__":
    main()
