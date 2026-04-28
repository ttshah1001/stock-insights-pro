"""
Marketstack API client for EOD and intraday quotes.
Uses MARKETSTACK_API_KEY from environment.
Free plan is typically end-of-day or delayed, but we normalize into the
same quote / OHLCV shapes used elsewhere in the app.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import requests
except ImportError:
    requests = None

BASE_URL = "http://api.marketstack.com/v1"


def get_api_key() -> Optional[str]:
    return os.environ.get("MARKETSTACK_API_KEY", "").strip() or None


def _get(path: str, params: Optional[dict] = None) -> Optional[dict]:
    if not requests:
        return None
    key = get_api_key()
    if not key:
        return None
    params = dict(params or {})
    params.setdefault("access_key", key)
    try:
        r = requests.get(f"{BASE_URL}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def latest_quote(ticker: str) -> Optional[dict]:
    """
    Latest (intraday or last EOD) quote for a single symbol.
    Marketstack uses symbols like 'AAPL', 'MSFT'.
    """
    data = _get("/intraday/latest", {"symbols": ticker.upper()})
    if data and data.get("data"):
        # intraday/latest returns a list
        if isinstance(data["data"], list) and data["data"]:
            return data["data"][0]
    # Fallback to EOD latest
    data = _get("/eod/latest", {"symbols": ticker.upper()})
    if data and data.get("data"):
        if isinstance(data["data"], list) and data["data"]:
            return data["data"][0]
    return None


def quote_to_dict(quote: Optional[dict]) -> dict:
    """
    Normalize Marketstack intraday/eod quote to our quote dict.
    """
    if not quote:
        return {}
    try:
        symbol = str(quote.get("symbol", "")).upper()
        close = float(quote.get("last") or quote.get("close"))
        open_ = float(quote.get("open") or close)
        high = float(quote.get("high") or close)
        low = float(quote.get("low") or close)
        vol = quote.get("volume") or 0
        volume = int(vol) if vol is not None else 0
    except Exception:
        return {}
    return {
        "ticker": symbol,
        "close": close,
        "open": open_,
        "high": high,
        "low": low,
        "volume": volume,
        "updated": datetime.utcnow().isoformat() + "Z",
    }


def eod_ohlcv(
    ticker: str,
    limit: int = 365,
) -> List[dict]:
    """
    Daily EOD OHLCV for one symbol. Returns list of
    { date, open, high, low, close, volume }.
    """
    data = _get("/eod", {"symbols": ticker.upper(), "limit": limit})
    if not data or "data" not in data:
        return []
    out: List[dict] = []
    for row in data.get("data", []):
        try:
            date_str = row.get("date")
            # Marketstack dates are ISO with time; keep date part
            if date_str:
                date_str = date_str[:10]
            o = row.get("open")
            h = row.get("high")
            l = row.get("low")
            c = row.get("close")
            v = row.get("volume") or 0
            if c is None:
                continue
            out.append(
                {
                    "date": date_str,
                    "open": float(o) if o is not None else float(c),
                    "high": float(h) if h is not None else float(c),
                    "low": float(l) if l is not None else float(c),
                    "close": float(c),
                    "volume": int(v),
                }
            )
        except Exception:
            continue
    out.sort(key=lambda x: x["date"] or "")
    return out

