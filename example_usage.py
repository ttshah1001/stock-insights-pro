#!/usr/bin/env python3
"""
Minimal example: run quant analysis for one ticker and print key metrics.
Run from project root: python example_usage.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from quant_analysis.data.loader import MarketDataLoader
from quant_analysis.technical.indicators import TechnicalAnalyzer
from quant_analysis.risk.metrics import RiskAnalyzer
from quant_analysis.fundamental.ratios import FundamentalAnalyzer
from quant_analysis.fundamental.factors import FactorModel

def main():
    ticker = "AAPL"
    loader = MarketDataLoader()
    ohlcv = loader.fetch_ohlcv(ticker, period="1y")
    if ohlcv.empty:
        print(f"No data for {ticker}")
        return
    returns = loader.returns(ohlcv, field="Close")

    # Technical
    tech = TechnicalAnalyzer()
    tech_df = tech.signals(ohlcv)
    last = tech_df.iloc[-1]
    print(f"--- {ticker} Technical (latest) ---")
    print(f"  RSI: {last.get('rsi', 0):.1f}  MACD: {last.get('macd', 0):.4f}  ADX: {last.get('adx', 0):.1f}")
    print(f"  Signal (composite): {last.get('signal_composite', 0)}")

    # Risk
    risk = RiskAnalyzer()
    m = risk.full_report(returns)
    print(f"\n--- Risk & Performance ---")
    print(f"  Ann. return: {m.get('annualized_return', 0)*100:.2f}%  Vol: {m.get('annualized_volatility', 0)*100:.2f}%")
    print(f"  Sharpe: {m.get('sharpe_ratio', 0):.2f}  Max DD: {m.get('max_drawdown', 0)*100:.2f}%")
    print(f"  VaR 95%: {m.get('var_historical_95', 0)*100:.2f}%")

    # Fundamental
    try:
        fund = FundamentalAnalyzer(loader)
        metrics = fund.get_metrics(ticker)
        print(f"\n--- Fundamentals ---")
        print(f"  P/E: {metrics.get('pe_ratio', 'N/A')}  P/B: {metrics.get('pb_ratio', 'N/A')}  ROE: {metrics.get('roe', 'N/A')}")
    except Exception as e:
        print(f"\nFundamentals skipped: {e}")

    # Factor exposures
    try:
        factors = FactorModel(loader)
        exp = factors.factor_exposures_single(ticker, prices=ohlcv["Close"], returns=returns)
        print(f"\n--- Factor Exposures ---")
        print(exp.to_string())
    except Exception as e:
        print(f"\nFactors skipped: {e}")

    print("\nDone.")

if __name__ == "__main__":
    main()
