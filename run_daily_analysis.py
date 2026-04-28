#!/usr/bin/env python3
"""
Daily Quant Trading Analysis — Run pattern analysis and get BUY/SELL/HOLD recommendations.

Usage:
  python run_daily_analysis.py
  python run_daily_analysis.py AAPL MSFT GOOGL
  python run_daily_analysis.py --watchlist my_stocks.txt --output report.md
  python run_daily_analysis.py --json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Optional

ROOT = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(ROOT))

import pandas as pd
import config
from quant_analysis.data.loader import MarketDataLoader
from quant_analysis.trading.daily_model import DailyTradingModel, TradeRecommendation


def load_watchlist(args: argparse.Namespace) -> List[str]:
    """Resolve watchlist from args: either CLI tickers or --watchlist file or config default."""
    if args.tickers:
        return args.tickers
    if args.watchlist:
        path = Path(args.watchlist)
        if path.exists():
            return [s.strip() for s in path.read_text().splitlines() if s.strip()]
    return config.DEFAULT_WATCHLIST


def recommendation_to_dict(rec: TradeRecommendation) -> dict:
    return {
        "ticker": rec.ticker,
        "action": rec.action,
        "conviction": round(rec.conviction, 1),
        "reasoning": rec.reasoning,
        "current_price": rec.current_price,
        "stop_loss": rec.stop_loss,
        "take_profit": rec.take_profit,
        "risk_level": rec.risk_level,
        "trend_strength": rec.trend_strength,
        "rsi": rec.rsi,
        "atr_pct": round(rec.atr_pct * 100, 2) if rec.atr_pct else None,
    }


def print_report(recommendations: List[TradeRecommendation], title: str = "Daily Trading Analysis") -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    buys = [r for r in recommendations if r.action == "BUY"]
    sells = [r for r in recommendations if r.action == "SELL"]
    holds = [r for r in recommendations if r.action == "HOLD"]

    print("\n--- ACTIONS SUMMARY ---")
    print(f"  BUY:  {len(buys)}  |  SELL: {len(sells)}  |  HOLD: {len(holds)}")
    if buys:
        print(f"  BUY  tickers: {', '.join(r.ticker for r in sorted(buys, key=lambda x: -x.conviction))}")
    if sells:
        print(f"  SELL tickers: {', '.join(r.ticker for r in sorted(sells, key=lambda x: x.conviction))}")

    print("\n--- RECOMMENDATIONS ---")
    for rec in sorted(recommendations, key=lambda r: (-r.conviction if r.action == "BUY" else r.conviction)):
        icon = "🟢" if rec.action == "BUY" else "🔴" if rec.action == "SELL" else "⚪"
        print(f"\n  {icon} {rec.ticker} — {rec.action} (conviction: {rec.conviction:.0f})")
        print(f"      Price: ${rec.current_price:.2f}  |  Risk: {rec.risk_level}")
        if rec.stop_loss is not None:
            print(f"      Stop: ${rec.stop_loss:.2f}  |  Target: ${rec.take_profit:.2f}")
        if rec.rsi is not None:
            adx_display = rec.trend_strength
            if adx_display is None or (isinstance(adx_display, float) and (adx_display < 0 or adx_display > 100)):
                adx_display = 0
            print(f"      RSI: {rec.rsi:.0f}  |  ADX: {adx_display:.0f}")
        for reason in rec.reasoning[:5]:
            print(f"      • {reason}")
    print("\n" + "=" * 60)


def run_daily_analysis(
    tickers: List[str],
    lookback_days: int = None,
    output_path: Optional[Path] = None,
    output_json_path: Optional[Path] = None,
) -> List[TradeRecommendation]:
    lookback_days = lookback_days or config.DAILY_MODEL_LOOKBACK_DAYS
    end = datetime.now()
    start = end - timedelta(days=lookback_days + 30)  # buffer for indicator warmup

    loader = MarketDataLoader(use_cache=True)
    model = DailyTradingModel()

    ohlcv_by_ticker = {}
    for ticker in tickers:
        try:
            df = loader.fetch_ohlcv(ticker, start=start, end=end, interval="1d")
            if df.empty:
                continue
            if isinstance(df.index, pd.MultiIndex):
                df = df.loc[ticker]
            if len(df) >= 30:  # need enough for indicators
                ohlcv_by_ticker[ticker] = df
        except Exception as e:
            print(f"Warning: Could not load {ticker}: {e}")

    if not ohlcv_by_ticker:
        print("No data loaded for any ticker. Check symbols and network.")
        return []

    recommendations = model.analyze_watchlist(ohlcv_by_ticker, use_forecast=False)

    print_report(recommendations)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Daily Quant Trading Analysis",
            f"\nGenerated: {datetime.now().isoformat()}\n",
            "| Ticker | Action | Conviction | Price | Stop | Target | Risk |",
            "|--------|--------|------------|-------|------|--------|------|",
        ]
        for rec in recommendations:
            stop = f"${rec.stop_loss:.2f}" if rec.stop_loss else "—"
            target = f"${rec.take_profit:.2f}" if rec.take_profit else "—"
            lines.append(
                f"| {rec.ticker} | {rec.action} | {rec.conviction:.0f} | ${rec.current_price:.2f} | {stop} | {target} | {rec.risk_level} |"
            )
        lines.append("\n## Reasoning\n")
        for rec in recommendations:
            lines.append(f"### {rec.ticker} — {rec.action}\n")
            for r in rec.reasoning:
                lines.append(f"- {r}")
            lines.append("")
        output_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Report saved: {output_path}")

    if output_json_path:
        output_json_path = Path(output_json_path)
        output_json_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "generated": datetime.now().isoformat(),
            "tickers": [rec.ticker for rec in recommendations],
            "recommendations": [recommendation_to_dict(rec) for rec in recommendations],
        }
        output_json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"JSON saved: {output_json_path}")

    return recommendations


def main():
    parser = argparse.ArgumentParser(
        description="Daily quant trading analysis: market pattern analysis and BUY/SELL/HOLD recommendations."
    )
    parser.add_argument(
        "tickers",
        nargs="*",
        help="Ticker symbols (e.g. AAPL MSFT). If omitted, uses config watchlist.",
    )
    parser.add_argument(
        "--watchlist",
        "-w",
        type=str,
        help="Path to text file with one ticker per line (overrides default watchlist).",
    )
    parser.add_argument(
        "--lookback",
        type=int,
        default=config.DAILY_MODEL_LOOKBACK_DAYS,
        help=f"Days of history for indicators (default: {config.DAILY_MODEL_LOOKBACK_DAYS}).",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Save Markdown report to this path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Save JSON report to output/daily_analysis_<date>.json",
    )
    args = parser.parse_args()

    tickers = load_watchlist(args)
    if not tickers:
        print("No tickers specified. Use: run_daily_analysis.py AAPL MSFT ... or set DEFAULT_WATCHLIST in config.")
        return

    json_path = None
    if args.json:
        json_path = config.OUTPUT_DIR / f"daily_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

    run_daily_analysis(
        tickers=tickers,
        lookback_days=args.lookback,
        output_path=args.output,
        output_json_path=json_path,
    )


if __name__ == "__main__":
    main()
