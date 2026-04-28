"""
Polygon.io (Massive) API client for real-time and historical market data.
Uses POLYGON_API_KEY from environment. Falls back to yfinance when no key.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional, List, Any
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import requests
except ImportError:
    requests = None

BASE_URL = "https://api.polygon.io"


def get_api_key() -> Optional[str]:
    """API key from environment (never hardcode)."""
    return os.environ.get("POLYGON_API_KEY", "").strip() or None


def _get(url: str, params: Optional[dict] = None) -> Optional[dict]:
    if not requests:
        return None
    key = get_api_key()
    if not key:
        return None
    params = dict(params or {})
    params.setdefault("apiKey", key)
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def snapshot(ticker: str) -> Optional[dict]:
    """
    Real-time snapshot for one ticker.
    Returns latest quote, trade, and day aggregate from Polygon.
    """
    url = f"{BASE_URL}/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}"
    return _get(url)


def previous_close(ticker: str) -> Optional[dict]:
    """Previous trading day OHLCV."""
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker.upper()}/prev"
    return _get(url)


def daily_bars(
    ticker: str,
    from_date: str,
    to_date: str,
) -> Optional[dict]:
    """Daily OHLCV bars. from_date/to_date: YYYY-MM-DD."""
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker.upper()}/range/1/day/{from_date}/{to_date}"
    return _get(url)


def snapshot_to_quote(snap: Optional[dict]) -> dict:
    """
    Normalize Polygon snapshot to a simple quote dict for the frontend.
    """
    if not snap or "ticker" not in snap:
        return {}
    t = snap.get("ticker", {})
    day = t.get("day", {})
    min_ = t.get("min", {})
    prev = t.get("prevDay", {})
    # Prefer latest trade/quote, then day bar
    close = (
        (min_.get("c") or day.get("c") or prev.get("c")) if (min_ or day or prev) else None
    )
    open_ = (day.get("o") or prev.get("o")) or close
    high = (day.get("h") or prev.get("h")) or close
    low = (day.get("l") or prev.get("l")) or close
    volume = (day.get("v") or prev.get("v")) or 0
    return {
        "ticker": t.get("ticker", ""),
        "name": t.get("name", ""),
        "close": close,
        "open": open_,
        "high": high,
        "low": low,
        "volume": int(volume) if volume is not None else 0,
        "updated": datetime.utcnow().isoformat() + "Z",
    }


def previous_close_to_quote(data: Optional[dict]) -> dict:
    """Normalize Polygon previous-close response to quote dict."""
    if not data or "results" not in data or not data["results"]:
        return {}
    r = data["results"][0]
    return {
        "ticker": data.get("ticker", ""),
        "close": r.get("c"),
        "open": r.get("o"),
        "high": r.get("h"),
        "low": r.get("l"),
        "volume": r.get("v", 0),
        "updated": datetime.utcnow().isoformat() + "Z",
    }


def daily_bars_to_ohlcv_list(data: Optional[dict]) -> List[dict]:
    """Convert Polygon range response to list of { date, open, high, low, close, volume }."""
    if not data or "results" not in data:
        return []
    out = []
    for r in data.get("results", []):
        ts = r.get("t", 0)
        if ts:
            try:
                dt = datetime.utcfromtimestamp(ts / 1000.0)
                date_str = dt.strftime("%Y-%m-%d")
            except Exception:
                date_str = str(ts)
        else:
            date_str = ""
        out.append({
            "date": date_str,
            "open": r.get("o"),
            "high": r.get("h"),
            "low": r.get("l"),
            "close": r.get("c"),
            "volume": r.get("v", 0),
        })
    return out
