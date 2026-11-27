"""
Adanos X/Twitter stock sentiment API (https://api.adanos.com), used in shadow mode only.

Free plan: 250 requests/month, 100/minute, 30 days of history, non-commercial use (private tools are allowed).
One request per ticker returns the daily series for the requested window: mentions, the provider's sentiment
score and its bullish/bearish shares. Adanos collects the posts itself (twscrape) and classifies them with its
own model, so this is a different instrument from our X pillar: it is stored and measured, never scored.
"""
import logging
from datetime import date
from typing import Any, Dict, List, Optional

import httpx

from app.collectors.base import SourceAuthError, SourceError, SourceIncompatibleError
from app.config import settings

logger = logging.getLogger(__name__)

STOCK_PATH = "/x/stocks/v1/stock/{ticker}"


class SourceRateLimitedError(SourceError):
    kind = "RATE_LIMITED"


def _num(row: Dict[str, Any], key: str) -> Optional[float]:
    v = row.get(key)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def parse_daily_trend(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Daily rows from a /stock/{ticker} response, oldest first. `found: false` means no qualifying data."""
    if not isinstance(payload, dict):
        raise SourceIncompatibleError("Adanos: unexpected response shape")
    if payload.get("found") is False:
        return []
    rows = payload.get("daily_trend")
    if not isinstance(rows, list):
        raise SourceIncompatibleError("Adanos: response has no daily_trend list")
    out = []
    for r in rows:
        day = str(r.get("date") or "")[:10]
        if len(day) != 10:
            continue
        mentions = _num(r, "mentions")
        out.append({
            "date": day,
            "mentions": int(mentions) if mentions is not None else None,
            "sentiment_score": _num(r, "sentiment_score"),
            "bullish_pct": _num(r, "bullish_pct"),
            "bearish_pct": _num(r, "bearish_pct"),
            "buzz_score": _num(r, "buzz_score"),
        })
    return sorted(out, key=lambda x: x["date"])


class AdanosXProvider:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, timeout: float = 20.0):
        self.api_key = api_key if api_key is not None else settings.ADANOS_API_KEY
        self.base_url = (base_url or settings.ADANOS_BASE_URL).rstrip("/")
        self.timeout = timeout

    async def fetch_daily(self, ticker: str, start: date, end: date) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise SourceAuthError("Adanos: ADANOS_API_KEY is not set")
        url = self.base_url + STOCK_PATH.format(ticker=ticker.upper())
        params = {"from": start.isoformat(), "to": end.isoformat()}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params=params, headers={"X-API-Key": self.api_key})
        if resp.status_code in (401, 403):
            raise SourceAuthError(f"Adanos: HTTP {resp.status_code} (key rejected or plan does not allow this call)")
        if resp.status_code == 429:
            raise SourceRateLimitedError("Adanos: HTTP 429 (monthly or per-minute quota exhausted)")
        if resp.status_code == 404:
            return []  # Ticker not supported by the provider
        resp.raise_for_status()
        return parse_daily_trend(resp.json())
