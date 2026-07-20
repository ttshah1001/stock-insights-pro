"""
Flask backend: real-time market data, analysis, and quant trading advice.
Run: flask run  (or python app.py)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

import math
import pandas as pd
from flask import Flask, render_template, jsonify, request

import config


def _json_safe(val):
    """Convert nan/inf to None for JSON serialization."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return None
    return val
from quant_analysis.data.loader import MarketDataLoader
from quant_analysis.data.polygon_client import (
    get_api_key,
    snapshot,
    previous_close,
    daily_bars,
    snapshot_to_quote,
    previous_close_to_quote,
    daily_bars_to_ohlcv_list,
)
from quant_analysis.data.alpha_vantage_client import (
    get_api_key as get_av_key,
    global_quote as av_quote,
    time_series_daily,
    symbol_search as av_symbol_search,
    quote_to_dict as av_quote_to_dict,
    time_series_to_bars as av_series_to_bars,
    fetch_ohlcv_dataframe as av_fetch_ohlcv_df,
)
from quant_analysis.data.rapidapi_yahoo_client import (
    get_api_key as get_yahoo_key,
    get_quote as yahoo_quote,
    quote_to_dict as yahoo_quote_to_dict,
)
from quant_analysis.data.marketstack_client import (
    get_api_key as get_ms_key,
    latest_quote as ms_latest_quote,
    quote_to_dict as ms_quote_to_dict,
    eod_ohlcv as ms_eod_ohlcv,
)
from quant_analysis.technical.indicators import TechnicalAnalyzer
from quant_analysis.trading.daily_model import DailyTradingModel, TradeRecommendation
from quant_analysis.risk.metrics import RiskAnalyzer
from quant_analysis.market import MarketSimulator, benchmark as market_benchmark

app = Flask(__name__, static_folder="static", template_folder="templates")

# Common company name -> ticker for resolve (lowercase key)
COMPANY_TO_TICKER = {
    "apple": "AAPL", "apple inc": "AAPL", "microsoft": "MSFT", "google": "GOOGL", "alphabet": "GOOGL",
    "amazon": "AMZN", "meta": "META", "facebook": "META", "tesla": "TSLA",
    "nvidia": "NVDA", "netflix": "NFLX", "amd": "AMD", "intel": "INTC",
    "jpmorgan": "JPM", "jp morgan": "JPM", "bank of america": "BAC", "visa": "V",
    "mastercard": "MA", "berkshire": "BRK.B", "berkshire hathaway": "BRK.B",
    "johnson & johnson": "JNJ", "johnson and johnson": "JNJ", "procter gamble": "PG",
    "walmart": "WMT", "disney": "DIS", "walt disney": "DIS", "coca cola": "KO", "coca-cola": "KO",
    "pepsi": "PEP", "mcdonalds": "MCD", "nike": "NKE", "adobe": "ADBE",
    "salesforce": "CRM", "oracle": "ORCL", "ibm": "IBM", "spy": "SPY", "qqq": "QQQ",
    "costco": "COST", "home depot": "HD", "pfizer": "PFE", "merck": "MRK", "exxon": "XOM",
    "chevron": "CVX", "uber": "UBER", "lyft": "LYFT", "spotify": "SPOT", "zoom": "ZM",
}


def _resolve_ticker(query: str) -> Optional[tuple]:
    """Resolve 'Apple' or 'AAPL' to (ticker, name). Returns None if not found."""
    q = (query or "").strip()
    if not q:
        return None
    q_upper = q.upper()
    q_lower = q.lower()
    # Already looks like a ticker (short, no spaces)
    if len(q) <= 6 and q.isalpha():
        if q_lower in COMPANY_TO_TICKER:
            ticker = COMPANY_TO_TICKER[q_lower]
            return (ticker, q_upper)
        return (q_upper, q_upper)
    # Company name: static map first
    if q_lower in COMPANY_TO_TICKER:
        ticker = COMPANY_TO_TICKER[q_lower]
        return (ticker, q.strip())
    # Alpha Vantage symbol search
    if get_av_key():
        try:
            matches = av_symbol_search(q)
            if matches:
                first = matches[0]
                return (first["symbol"], first.get("name") or first["symbol"])
        except Exception:
            pass
    return None


def _get_ohlcv_for_analysis(ticker: str, start: datetime, end: datetime, min_rows: int = 26) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV for analysis/quant: try yfinance first, then Alpha Vantage if insufficient.
    Returns DataFrame with date index and Open, High, Low, Close, Volume (or None).
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return None
    loader = MarketDataLoader(use_cache=True)
    df = None
    try:
        df = loader.fetch_ohlcv(ticker, start=start, end=end, interval="1d")
        if df is not None and not df.empty:
            if isinstance(df.index, pd.MultiIndex):
                df = df.loc[ticker].copy()
            if len(df) >= min_rows:
                return df
    except Exception:
        pass
    try:
        df = loader.fetch_ohlcv(ticker, period="2y", interval="1d")
        if df is not None and not df.empty:
            if isinstance(df.index, pd.MultiIndex):
                df = df.loc[ticker].copy()
            if len(df) >= min_rows:
                return df
    except Exception:
        pass
    # Fallback: Alpha Vantage
    if get_av_key():
        try:
            days = min(365, max((end - start).days + 60, 100))
            df = av_fetch_ohlcv_df(ticker, max_days=days)
            if df is not None and not df.empty and len(df) >= min_rows:
                return df
        except Exception:
            pass
    # Fallback: Marketstack EOD
    if get_ms_key():
        try:
            from pandas import DataFrame, to_datetime

            bars = ms_eod_ohlcv(ticker, limit=max(min_rows * 3, 90))
            if bars:
                df_ms = DataFrame(bars)
                df_ms["date"] = to_datetime(df_ms["date"])
                df_ms = df_ms.set_index("date").sort_index()
                if len(df_ms) >= min_rows:
                    return df_ms
        except Exception:
            pass
    return None


def _get_realtime_quote(ticker: str) -> dict:
    """Real-time or latest quote: Polygon -> Alpha Vantage -> Marketstack -> RapidAPI Yahoo -> yfinance."""
    key = get_api_key()
    if key:
        snap = snapshot(ticker)
        if snap and "ticker" in snap:
            return snapshot_to_quote(snap)
        prev = previous_close(ticker)
        if prev:
            return previous_close_to_quote(prev)
    if get_av_key():
        q = av_quote(ticker)
        if q:
            return av_quote_to_dict(q)
    if get_ms_key():
        q = ms_latest_quote(ticker)
        if q:
            d = ms_quote_to_dict(q)
            if d:
                return d
    if get_yahoo_key():
        data = yahoo_quote(ticker)
        if data:
            q = yahoo_quote_to_dict(data)
            if q:
                return q
    # Fallback: yfinance (no API key; uses public data)
    loader = MarketDataLoader(use_cache=False)
    end = datetime.now()
    start = end - timedelta(days=5)
    try:
        df = loader.fetch_ohlcv(ticker, start=start, end=end, interval="1d")
        if df is None or df.empty:
            return {}
        if isinstance(df.index, pd.MultiIndex):
            df = df.loc[ticker]
        last = df.iloc[-1]
        return {
            "ticker": ticker.upper(),
            "close": float(last.get("Close", last.iloc[0])),
            "open": float(last.get("Open", last.iloc[0])),
            "high": float(last.get("High", last.iloc[0])),
            "low": float(last.get("Low", last.iloc[0])),
            "volume": int(last.get("Volume", 0)),
            "updated": datetime.utcnow().isoformat() + "Z",
        }
    except Exception:
        return {}


def _get_daily_bars(ticker: str, days: int = 252) -> list:
    """Historical daily bars for charts. Polygon -> Alpha Vantage -> yfinance."""
    to_d = datetime.now()
    from_d = to_d - timedelta(days=min(days + 30, 400))
    from_str = from_d.strftime("%Y-%m-%d")
    to_str = to_d.strftime("%Y-%m-%d")
    if get_api_key():
        data = daily_bars(ticker, from_str, to_str)
        if data:
            bars = daily_bars_to_ohlcv_list(data)
            if bars:
                return bars[-days:] if len(bars) > days else bars
    if get_av_key():
        ts = time_series_daily(ticker, outputsize="full" if days > 100 else "compact")
        if ts:
            bars = av_series_to_bars(ts, max_days=days)
            if bars:
                return bars
    loader = MarketDataLoader(use_cache=True)
    try:
        df = loader.fetch_ohlcv(ticker, start=from_d, end=to_d, interval="1d")
        if df is None or df.empty:
            return []
        if isinstance(df.index, pd.MultiIndex):
            df = df.loc[ticker]
        df = df.reset_index()
        if "date" not in df.columns and df.index.name == "date":
            df = df.reset_index()
        if "Date" in df.columns:
            df = df.rename(columns={"Date": "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        return [
            {
                "date": row["date"],
                "open": float(row.get("Open", row.iloc[0])),
                "high": float(row.get("High", row.iloc[0])),
                "low": float(row.get("Low", row.iloc[0])),
                "close": float(row.get("Close", row.iloc[0])),
                "volume": int(row.get("Volume", 0)),
            }
            for _, row in df.iterrows()
        ]
    except Exception:
        return []


def _recommendation_to_dict(rec: TradeRecommendation, extra: Optional[dict] = None) -> dict:
    def safe_float(x):
        if x is None:
            return None
        try:
            f = float(x)
            return _json_safe(round(f, 2)) if not math.isnan(f) else None
        except (TypeError, ValueError):
            return None
    d = {
        "ticker": rec.ticker,
        "action": rec.action,
        "conviction": _json_safe(round(rec.conviction, 1)),
        "reasoning": rec.reasoning,
        "current_price": safe_float(rec.current_price),
        "stop_loss": safe_float(rec.stop_loss),
        "take_profit": safe_float(rec.take_profit),
        "risk_level": rec.risk_level,
        "trend_strength": safe_float(rec.trend_strength),
        "rsi": safe_float(rec.rsi),
        "atr_pct": safe_float(rec.atr_pct * 100 if rec.atr_pct else None),
    }
    if extra:
        d.update({k: _json_safe(v) for k, v in extra.items()})
    # One-line advice summary
    advice = rec.action or "HOLD"
    if rec.action == "BUY":
        advice += " — " + (f"Target ${rec.take_profit:.2f}" if rec.take_profit is not None else "bullish signals")
    elif rec.action == "SELL":
        advice += " — " + (f"Stop ${rec.stop_loss:.2f}" if rec.stop_loss is not None else "bearish signals")
    else:
        advice += " — wait for clearer signal"
    d["advice_summary"] = advice
    return d


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/resolve")
def api_resolve():
    """Resolve ticker or company name to ticker + name. Query: ?q=Apple or ?q=AAPL"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Missing query"}), 400
    result = _resolve_ticker(q)
    if result is None:
        return jsonify({"error": "Could not resolve symbol or company name"}), 404
    ticker, name = result
    return jsonify({"ticker": ticker, "name": name})


@app.route("/api/quote/<ticker>")
def api_quote(ticker):
    """Real-time (or latest) quote for one ticker."""
    q = _get_realtime_quote(ticker)
    body = q if q else {"error": "No data"}
    status = 200 if q else 404
    return jsonify(body), status


@app.route("/api/quotes")
def api_quotes():
    """Quotes for multiple tickers. Query: ?symbols=AAPL,MSFT,GOOGL"""
    symbols = request.args.get("symbols", config.DEFAULT_WATCHLIST[0])
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    quotes = []
    for t in symbols[:20]:
        q = _get_realtime_quote(t)
        if q:
            quotes.append(q)
    return jsonify(quotes)


@app.route("/api/bars/<ticker>")
def api_bars(ticker):
    """Daily OHLCV bars for charting. Query: ?days=90 (max 365)"""
    days = min(365, max(5, int(request.args.get("days", 252))))
    bars = _get_daily_bars(ticker, days=days)
    return jsonify(bars)


@app.route("/api/analysis/<ticker>")
def api_analysis(ticker):
    """Technical analysis for one ticker: indicators + latest values."""
    end = datetime.now()
    start = end - timedelta(days=config.DAILY_MODEL_LOOKBACK_DAYS + 30)
    df = _get_ohlcv_for_analysis(ticker, start, end, min_rows=26)
    if df is None or df.empty or len(df) < 26:
        return jsonify({"error": "Insufficient data (try again or check ticker symbol)"}), 400
    tech = TechnicalAnalyzer()
    df = tech.run(df)
    last = df.iloc[-1]
    cols = [
        "Close", "Open", "High", "Low", "Volume",
        "rsi", "macd", "macd_signal", "macd_hist",
        "sma_short", "sma_long", "ema_short", "ema_long",
        "bb_upper", "bb_lower", "bb_mid", "bb_width", "bb_position",
        "atr", "adx", "di_plus", "di_minus",
        "stoch_k", "stoch_d", "obv",
    ]
    out = {}
    for c in cols:
        if c in last.index:
            v = last[c]
            if pd.isna(v):
                out[c] = None
            elif isinstance(v, (int, float)):
                vf = round(float(v), 4)
                out[c] = _json_safe(vf)
            else:
                out[c] = str(v)
    out["ticker"] = ticker.upper()
    out["date"] = str(df.index[-1])[:10]
    out["bars_count"] = len(df)
    return jsonify(out)


@app.route("/api/analysis_series/<ticker>")
def api_analysis_series(ticker):
    """Full indicator time series for charting: bars + RSI, MACD, etc. over time."""
    days = min(365, max(30, int(request.args.get("days", 180))))
    end = datetime.now()
    start = end - timedelta(days=days + 60)
    df = _get_ohlcv_for_analysis(ticker, start, end, min_rows=26)
    if df is None or df.empty or len(df) < 26:
        return jsonify({"error": "Insufficient data"}), 400
    tech = TechnicalAnalyzer()
    df = tech.run(df)
    df = df.tail(days)
    dates = [str(d)[:10] for d in df.index]
    bars = [
        {
            "date": dates[i],
            "open": float(df.iloc[i]["Open"]) if "Open" in df.columns else None,
            "high": float(df.iloc[i]["High"]) if "High" in df.columns else None,
            "low": float(df.iloc[i]["Low"]) if "Low" in df.columns else None,
            "close": float(df.iloc[i]["Close"]),
            "volume": int(df.iloc[i].get("Volume", 0)),
        }
        for i in range(len(df))
    ]
    series = {
        "rsi": [round(float(x), 2) if pd.notna(x) else None for x in df["rsi"].tolist()],
        "macd": [round(float(x), 4) if pd.notna(x) else None for x in df["macd"].tolist()],
        "macd_signal": [round(float(x), 4) if pd.notna(x) else None for x in df["macd_signal"].tolist()],
        "macd_hist": [round(float(x), 4) if pd.notna(x) else None for x in df["macd_hist"].tolist()],
        "sma_short": [round(float(x), 2) if pd.notna(x) else None for x in df["sma_short"].tolist()],
        "sma_long": [round(float(x), 2) if pd.notna(x) else None for x in df["sma_long"].tolist()],
        "bb_upper": [round(float(x), 2) if pd.notna(x) else None for x in df["bb_upper"].tolist()],
        "bb_lower": [round(float(x), 2) if pd.notna(x) else None for x in df["bb_lower"].tolist()],
        "atr": [round(float(x), 2) if pd.notna(x) else None for x in df["atr"].tolist()],
        "adx": [round(float(x), 2) if pd.notna(x) else None for x in df["adx"].tolist()],
    }
    return jsonify({
        "ticker": ticker.upper(),
        "dates": dates,
        "bars": bars,
        "series": series,
    })


@app.route("/api/quant")
def api_quant():
    """Quant tab: daily trading recommendations for watchlist."""
    symbols = request.args.get("symbols", "")
    if not symbols:
        tickers = config.DEFAULT_WATCHLIST
    else:
        tickers = [s.strip() for s in symbols.split(",") if s.strip()]
    tickers = tickers[:25]
    model = DailyTradingModel()
    end = datetime.now()
    start = end - timedelta(days=config.DAILY_MODEL_LOOKBACK_DAYS + 30)
    recommendations = []
    for ticker in tickers:
        try:
            df = _get_ohlcv_for_analysis(ticker, start, end, min_rows=26)
            # If we truly can't get history, still return a neutral HOLD with explanation
            if df is None or df.empty or len(df) < 2:
                fallback_rec = TradeRecommendation(
                    ticker=ticker,
                    action="HOLD",
                    conviction=50.0,
                    reasoning=[
                        "No reliable price history available from data providers.",
                        "Defaulting to HOLD until more data is available.",
                    ],
                    current_price=0.0,
                    risk_level="MEDIUM",
                )
                recommendations.append(_recommendation_to_dict(fallback_rec, {}))
                continue

            # If we have some data but less than full indicator warmup, keep it conservative
            if len(df) >= 26:
                rec = model.analyze(df, ticker=ticker)
            else:
                # Limited data: construct a cautious HOLD with last close
                last_close = float(df["Close"].iloc[-1]) if "Close" in df.columns else float(df.iloc[-1, 0])
                rec = TradeRecommendation(
                    ticker=ticker,
                    action="HOLD",
                    conviction=50.0,
                    reasoning=[
                        "Limited recent history available; indicators may be unreliable.",
                        "Holding until clearer technical pattern emerges.",
                    ],
                    current_price=last_close,
                    risk_level="MEDIUM",
                )

            # Extra stats: 5d return, 20d vol (best-effort)
            extra = {}
            try:
                close = df["Close"] if "Close" in df.columns else df.iloc[:, 0]
                ret = close.pct_change()
                ret_5d = (close.iloc[-1] / close.iloc[-6] - 1) if len(close) >= 6 else None
                vol_20 = ret.tail(20).std() * (252 ** 0.5) if len(ret) >= 20 else None
                if ret_5d is not None and not (isinstance(ret_5d, float) and math.isnan(ret_5d)):
                    extra["return_5d_pct"] = _json_safe(round(float(ret_5d) * 100, 2))
                if vol_20 is not None and not (isinstance(vol_20, float) and math.isnan(vol_20)):
                    extra["volatility_annual_pct"] = _json_safe(round(float(vol_20) * 100, 2))
            except Exception:
                pass

            recommendations.append(_recommendation_to_dict(rec, extra))
        except Exception:
            # As a last resort, always include a neutral HOLD row so the UI never shows an empty table
            fallback_rec = TradeRecommendation(
                ticker=ticker,
                action="HOLD",
                conviction=50.0,
                reasoning=["Unexpected error during analysis. Defaulting to HOLD."],
                current_price=0.0,
                risk_level="MEDIUM",
            )
            recommendations.append(_recommendation_to_dict(fallback_rec, {}))
    return jsonify(recommendations)


@app.route("/api/risk/<ticker>")
def api_risk(ticker):
    """Risk metrics for one ticker."""
    loader = MarketDataLoader(use_cache=True)
    end = datetime.now()
    start = end - timedelta(days=252 * 2)
    try:
        df = loader.fetch_ohlcv(ticker, start=start, end=end, interval="1d")
        if df is None or df.empty:
            return jsonify({"error": "No data"}), 400
        if isinstance(df.index, pd.MultiIndex):
            df = df.loc[ticker]
        ret = loader.returns(df, field="Close")
        risk = RiskAnalyzer(
            risk_free_rate=config.DEFAULT_RISK_FREE_RATE,
            trading_days=config.TRADING_DAYS_PER_YEAR,
        )
        report = risk.full_report(ret)
        return jsonify({k: (round(float(v), 6) if isinstance(v, (int, float)) else v) for k, v in report.items()})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/market_sim")
def api_market_sim():
    """Run a short order-book / matching simulation around a mid price."""
    try:
        mid = float(request.args.get("mid", 100))
        buy_qty = float(request.args.get("buy_qty", 25))
        sell_qty = float(request.args.get("sell_qty", 15))
        slippage_bps = float(request.args.get("slippage_bps", 1.0))
        if mid <= 0 or buy_qty < 0 or sell_qty < 0:
            return jsonify({"error": "Invalid parameters"}), 400
        sim = MarketSimulator(slippage_bps=slippage_bps)
        result = sim.run_demo(mid=mid, buy_qty=buy_qty, sell_qty=sell_qty)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/market_sim/benchmark")
def api_market_sim_benchmark():
    """Throughput check for the matching path."""
    try:
        n = int(request.args.get("n", 5000))
        n = max(100, min(n, 50_000))
        mid = float(request.args.get("mid", 100))
        return jsonify(market_benchmark(n_orders=n, mid=mid))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
