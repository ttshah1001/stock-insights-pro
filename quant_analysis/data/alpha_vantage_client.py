"""
Alpha Vantage API client for daily time series and global quote.
Uses ALPHA_VANTAGE_API_KEY from environment. Complements Polygon/yfinance.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import requests
except ImportError:
    requests = None

BASE_URL = "https://www.alphavantage.co/query"


def get_api_key() -> Optional[str]:
    return os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip() or None


def _get(params: dict) -> Optional[dict]:
    if not requests:
        return None
    key = get_api_key()
    if not key:
        return None
    params = dict(params)
    params.setdefault("apikey", key)
    params.setdefault("datatype", "json")
    try:
        r = requests.get(BASE_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        if "Error Message" in data or "Note" in data:
            return None
        return data
    except Exception:
        return None


def global_quote(ticker: str) -> Optional[dict]:
    """Latest quote. Returns dict with 05. price, 02. open, 03. high, 04. low, 06. volume, 07. latest day."""
    data = _get({"function": "GLOBAL_QUOTE", "symbol": ticker.upper()})
    if not data or "Global Quote" not in data:
        return None
    q = data["Global Quote"]
    if not q:
        return None
    return q


def symbol_search(keywords: str) -> Optional[list]:
    """Search for symbols by keyword. Returns list of {symbol, name, ...}."""
    data = _get({"function": "SYMBOL_SEARCH", "keywords": keywords.strip()})
    if not data or "bestMatches" not in data:
        return None
    matches = data["bestMatches"]
    if not matches:
        return None
    out = []
    for m in matches:
        sym = (m.get("1. symbol") or "").strip()
        name = (m.get("2. name") or "").strip()
        if sym:
            out.append({"symbol": sym, "name": name})
    return out


def time_series_daily(ticker: str, outputsize: str = "full") -> Optional[dict]:
    """Daily OHLCV. outputsize: 'compact' (100 days) or 'full' (20+ years)."""
    data = _get({
        "function": "TIME_SERIES_DAILY",
        "symbol": ticker.upper(),
        "outputsize": outputsize,
    })
    if not data or "Time Series (Daily)" not in data:
        return None
    return data["Time Series (Daily)"]


def quote_to_dict(q: Optional[dict]) -> dict:
    """Normalize Alpha Vantage Global Quote to our quote shape."""
    if not q:
        return {}
    # Keys are like "01. symbol", "05. price", "02. open", "03. high", "04. low", "06. volume", "07. latest trading day"
    def get(k):
        for key in q:
            if key.strip().endswith(k):
                return q[key]
        return None
    price = get("price")
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None
    return {
        "ticker": get("symbol") or "",
        "close": price,
        "open": _float(get("open")),
        "high": _float(get("high")),
        "low": _float(get("low")),
        "volume": _int(get("volume")),
        "updated": datetime.utcnow().isoformat() + "Z",
    }


def _float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v):
    if v is None:
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _row_val(row: dict, key: str):
    """Get value from Alpha Vantage row; keys can be '1. open' or '1.open'."""
    v = row.get(key)
    if v is not None:
        return v
    alt = key.replace(". ", ".")  # "1. open" -> "1.open"
    return row.get(alt)


def time_series_to_bars(ts: Optional[dict], max_days: int = 365) -> List[dict]:
    """Convert Time Series (Daily) to list of { date, open, high, low, close, volume }."""
    if not ts:
        return []
    out = []
    for date_str, row in sorted(ts.items(), reverse=True)[:max_days]:
        try:
            o = _float(_row_val(row, "1. open"))
            h = _float(_row_val(row, "2. high"))
            l_ = _float(_row_val(row, "3. low"))
            c = _float(_row_val(row, "4. close"))
            v = _int(_row_val(row, "5. volume"))
            if c is None:
                continue
        except Exception:
            continue
        out.append({
            "date": date_str,
            "open": o if o is not None else c,
            "high": h if h is not None else c,
            "low": l_ if l_ is not None else c,
            "close": c,
            "volume": v or 0,
        })
    out.reverse()
    return out


def fetch_ohlcv_dataframe(ticker: str, max_days: int = 365):
    """
    Fetch daily OHLCV from Alpha Vantage and return a DataFrame compatible with
    MarketDataLoader format: DatetimeIndex, columns Open, High, Low, Close, Volume.
    Returns None if no data or API unavailable.
    """
    try:
        import pandas as pd
    except ImportError:
        return None
    ts = time_series_daily(ticker, outputsize="full" if max_days > 100 else "compact")
    if not ts:
        return None
    bars = time_series_to_bars(ts, max_days=max_days)
    if not bars:
        return None
    df = pd.DataFrame(bars)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"
    })
    return df
