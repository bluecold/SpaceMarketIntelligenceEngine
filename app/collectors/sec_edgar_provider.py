"""
SEC EDGAR collector for the dilution monitor.

Reads the public submissions index (data.sec.gov/submissions/CIK##########.json): form type, 8-K item codes,
filing date and acceptance time of every recent filing. No document text is downloaded. The SEC requires a
User-Agent that identifies the requester with a contact (https://www.sec.gov/os/accessing-edgar-data); it comes
from settings.SEC_USER_AGENT and the collector stays disabled while that setting is empty. The fair-access limit
is 10 requests/second; one run makes at most one request per ticker plus one daily ticker->CIK lookup.

This source never falls back to mock data: a fabricated offering would be worse than no data.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx

from app.collectors.base import SecFetchResult, SecFilingData, SecFilingsProvider
from app.collectors.sec_forms import SHELF, classify_filing
from app.config import settings

logger = logging.getLogger(__name__)

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{document}"
CIK_MAP_TTL_SECONDS = 24 * 3600


def _parse_acceptance(value: Optional[str]) -> Optional[datetime]:
    """EDGAR acceptanceDateTime ('2026-09-22T16:05:12.000Z') as a naive datetime, as stored by the rest of the DB."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def parse_submissions(payload: Dict, ticker: str, cik: str, history_days: int,
                      today: Optional[datetime] = None) -> List[SecFilingData]:
    """Tracked filings from a submissions JSON payload, filed within the last `history_days` days."""
    recent = (payload.get("filings") or {}).get("recent") or {}
    accessions = recent.get("accessionNumber") or []
    today = today or datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = (today - timedelta(days=history_days)).date().isoformat()

    def col(name: str, i: int):
        values = recent.get(name) or []
        return values[i] if i < len(values) else None

    out: List[SecFilingData] = []
    for i, accession in enumerate(accessions):
        filed = col("filingDate", i) or ""
        if not accession or filed < cutoff:
            continue
        form = col("form", i) or ""
        items = col("items", i) or None
        category = classify_filing(form, items)
        if category is None:
            continue
        document = col("primaryDocument", i) or None
        url = None
        if document:
            url = ARCHIVE_URL.format(cik_int=int(cik), accession_nodash=accession.replace("-", ""), document=document)
        out.append(SecFilingData(
            ticker=ticker,
            cik=cik,
            accession_number=accession,
            form=form,
            items=items,
            category=category,
            filed_date=filed,
            accepted_at=_parse_acceptance(col("acceptanceDateTime", i)),
            primary_document=document,
            description=col("primaryDocDescription", i) or None,
            url=url,
            source="LIVE",
        ))
    return out


class EdgarSecProvider(SecFilingsProvider):
    # Shared across instances: the ticker->CIK map is ~1 MB and changes rarely
    _cik_map: Dict[str, str] = {}
    _cik_map_loaded_at: float = 0.0

    def __init__(self, user_agent: Optional[str] = None, timeout: float = 15.0):
        self.user_agent = (user_agent if user_agent is not None else getattr(settings, "SEC_USER_AGENT", "")).strip()
        self.timeout = timeout

    @property
    def enabled(self) -> bool:
        return bool(self.user_agent)

    def _headers(self) -> Dict[str, str]:
        return {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}

    async def _resolve_cik(self, client: httpx.AsyncClient, ticker: str) -> Optional[str]:
        cls = EdgarSecProvider
        if not cls._cik_map or time.monotonic() - cls._cik_map_loaded_at > CIK_MAP_TTL_SECONDS:
            resp = await client.get(COMPANY_TICKERS_URL, headers=self._headers())
            resp.raise_for_status()
            data = resp.json()
            rows = data.values() if isinstance(data, dict) else data
            cls._cik_map = {str(r["ticker"]).upper(): str(int(r["cik_str"])).zfill(10) for r in rows
                            if r.get("ticker") and r.get("cik_str") is not None}
            cls._cik_map_loaded_at = time.monotonic()
        return cls._cik_map.get(ticker.upper())

    async def fetch_filings(self, ticker: str, cik: Optional[str] = None) -> SecFetchResult:
        if not self.enabled:
            return SecFetchResult(status="DISABLED", detail="SEC_USER_AGENT is not set")
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            cik = str(cik).zfill(10) if cik else await self._resolve_cik(client, ticker)
            if not cik:
                return SecFetchResult(status="NOT_APPLICABLE", detail=f"no SEC registrant for {ticker}")
            resp = await client.get(SUBMISSIONS_URL.format(cik=cik), headers=self._headers())
            resp.raise_for_status()
            payload = resp.json()
        history_days = int(getattr(settings, "SEC_HISTORY_DAYS", 400))
        filings = parse_submissions(payload, ticker, cik, history_days)
        logger.info(f"EDGAR: {len(filings)} tracked filings for {ticker} (CIK {cik}) in the last {history_days} days.")
        return SecFetchResult(status="OK", cik=cik, filings=filings)


class MockSecProvider(SecFilingsProvider):
    """Deterministic test double: one old shelf registration, outside any alert window."""

    async def fetch_filings(self, ticker: str, cik: Optional[str] = None) -> SecFetchResult:
        filed = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
        mock_cik = "0000000000"
        return SecFetchResult(status="OK", cik=mock_cik, filings=[SecFilingData(
            ticker=ticker,
            cik=mock_cik,
            accession_number=f"mock-{ticker.lower()}-shelf",
            form="S-3",
            category=SHELF,
            filed_date=filed.date().isoformat(),
            accepted_at=filed,
            description="Mock shelf registration",
            source="MOCK",
        )])
