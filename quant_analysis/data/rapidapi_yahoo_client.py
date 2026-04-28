"""
RapidAPI Yahoo Finance API client for real-time quotes.
Uses RAPIDAPI_KEY (and optional RAPIDAPI_YAHOO_HOST) from environment.
This is the third-party "Yahoo Finance" API on RapidAPI, not the official Yahoo API.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:
    import requests
except ImportError:
    requests = None

BASE_URL = "https://apidojo-yahoo-finance-v1.p.rapidapi.com"
DEFAULT_HOST = "apidojo-yahoo-finance-v1.p.rapidapi.com"


def get_api_key() -> Optional[str]:
    return os.environ.get("RAPIDAPI_KEY", "").strip() or os.environ.get("YAHOO_FINANCE_API_KEY", "").strip() or None


def get_host() -> str:
    return os.environ.get("RAPIDAPI_YAHOO_HOST", "").strip() or DEFAULT_HOST


def get_quote(ticker: str) -> Optional[dict]:
    """
    Fetch real-time quote from RapidAPI Yahoo Finance.
    Tries get-summary first, then market get-quotes. Returns raw response or None.
    """
    if not requests:
        return None
    key = get_api_key()
    if not key:
        return None
    headers = {
        "X-RapidAPI-Key": key,
        "X-RapidAPI-Host": get_host(),
    }
    sym = ticker.upper()
    # Try get-summary (single ticker)
    try:
        r = requests.get(
            f"{BASE_URL}/stock/v2/get-summary",
            headers=headers,
            params={"symbol": sym},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data and (data.get("price") or data.get("quoteResponse")):
            return data
    except Exception:
        pass
    # Try market get-quotes (some plans use this)
    try:
        r = requests.get(
            f"{BASE_URL}/market/v2/get-quotes",
            headers=headers,
            params={"symbols": sym},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        if data and data.get("quoteResponse", {}).get("result"):
            return data
    except Exception:
        pass
    return None


def quote_to_dict(data: Optional[dict]) -> dict:
    """Normalize RapidAPI Yahoo response to our quote format (get-summary or quote list)."""
    if not data:
        return {}
    # Try get-summary style: price, summaryDetail
    price = data.get("price", {})
    summary = data.get("summaryDetail", {})
    quote_type = data.get("quoteType", {})

    def p(key: str, default=None):
        return price.get(key) or summary.get(key) or default

    # Also support market/get-quotes style: quoteResponse.result[0]
    result = data.get("quoteResponse", {}).get("result", [])
    if result and not price:
        first = result[0]
        price = first
        summary = first
        quote_type = first

    try:
        close = float(
            p("regularMarketPrice") or p("regularMarketPreviousClose")
            or p("regularMarketClose") or price.get("regularMarketPrice") or 0
        )
        if close == 0:
            return {}
        open_ = float(p("regularMarketOpen") or close)
        high = float(p("regularMarketDayHigh") or p("dayHigh") or close)
        low = float(p("regularMarketDayLow") or p("dayLow") or close)
        vol = p("regularMarketVolume") or summary.get("volume") or price.get("volume")
        volume = int(float(vol)) if vol is not None else 0
    except (TypeError, ValueError):
        return {}
    symbol = (price.get("symbol") or quote_type.get("symbol") or data.get("symbol") or "").upper()
    return {
        "ticker": symbol,
        "close": close,
        "open": open_,
        "high": high,
        "low": low,
        "volume": volume,
        "updated": datetime.utcnow().isoformat() + "Z",
    }
