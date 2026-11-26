from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any, Set
from pydantic import BaseModel


class SourceError(RuntimeError):
    """A collector failure whose cause the provider could identify. `kind` drives the operator alert
    (app/monitoring/source_health.py): AUTH needs new credentials, INCOMPATIBLE needs a code/library update."""
    kind = "ERROR"


class SourceAuthError(SourceError):
    """The source rejected or never received credentials (expired cookies, missing token, locked account)."""
    kind = "AUTH"


class SourceIncompatibleError(SourceError):
    """The source accepted the credentials but changed its protocol, so the client library can no longer talk to it."""
    kind = "INCOMPATIBLE"


class SocialPostData(BaseModel):
    tweet_id: str
    ticker: str
    username: str
    text: str
    created_at: datetime
    url: Optional[str] = None
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    views: int = 0
    source: str = "LIVE"  # "LIVE", "MOCK", "DEGRADED"
    lang: Optional[str] = None  # Language detected by X (e.g. "en", "ja", "und"); None when unknown


class SocialSearchMeta(BaseModel):
    """How far one X search reached. complete=False means the page cap or a rate limit cut it short, so the
    posts are only the newest slice of the window and mention counts understate the real volume."""
    pages: int = 0
    complete: bool = True
    stop_reason: str = ""  # "exhausted", "reached_known", "reached_since", "page_cap", "rate_limited"


class MarketData(BaseModel):
    ticker: str
    timestamp: datetime  # Query / collection time
    observed_at: Optional[datetime] = None  # Underlying candle timestamp
    candle_date: Optional[str] = None  # Date string of the candle (e.g. "2026-09-04")
    market_session: Optional[str] = None  # "REGULAR", "CLOSED", "WEEKEND"
    price: Optional[float]
    volume: Optional[float]
    status: str = "AVAILABLE"  # "AVAILABLE", "DATA_UNAVAILABLE", "ERROR"
    raw_df: Optional[Any] = None  # DataFrame of historical OHLCV
    source: str = "LIVE"


class MarketProbabilityPoint(BaseModel):
    timestamp: datetime
    yes_probability: float
    no_probability: float
    volume: float = 0.0
    source: str = "LIVE"


class PredictionMarketData(BaseModel):
    external_id: str
    ticker: Optional[str] = None  # Specific ticker or None for general sector event
    title: str
    description: Optional[str] = None
    category: str = "SPACE"
    status: str = "ACTIVE"
    created_at: datetime
    end_date: Optional[datetime] = None
    resolution_date: Optional[datetime] = None
    
    yes_probability: float  # 0.0 to 1.0 (e.g., 0.72 = 72%)
    no_probability: float   # 0.0 to 1.0
    volume: float = 0.0     # USD total volume
    liquidity: float = 0.0  # USD liquidity pool
    spread: float = 0.0     # Bid-Ask spread
    quality_score: float = 50.0 # 0 to 100
    
    probability_change_1h: Optional[float] = None
    probability_change_6h: Optional[float] = None
    probability_change_24h: Optional[float] = None
    
    url: Optional[str] = None
    event_key: Optional[str] = None  # Mapping key if linked to cross-company event
    clob_token_id: Optional[str] = None  # 256-bit asset token ID for CLOB prices-history
    condition_id: Optional[str] = None   # Polymarket condition ID
    polarity: int = 1  # +1 = Bullish when YES occurs, -1 = Bearish when YES occurs (e.g. failure/delay)
    baseline_probability: Optional[float] = None  # Expected prior base-rate anchor (defaults to PMS_DEFAULT_BASE_RATE e.g. 0.20)
    source: str = "LIVE"  # "LIVE", "MOCK"
    # Polymarket event id when the market is one outcome of a mutually exclusive (negRisk) event, and that outcome's label
    outcome_group: Optional[str] = None
    outcome_label: Optional[str] = None

    @property
    def is_range_bucket(self) -> bool:
        """One numeric bucket of an exclusive set ('<5', '5-6', '200+'): a YES on it carries no direction by itself."""
        return bool(self.outcome_group and self.outcome_label and any(ch.isdigit() for ch in self.outcome_label))


class XProvider(ABC):
    # Set by search(): how far the last search reached
    last_search_meta: Optional[SocialSearchMeta] = None

    @abstractmethod
    async def search(
        self,
        query: str,
        ticker: str,
        max_results: int = 100,
        since: Optional[datetime] = None,
        known_ids: Optional[Set[str]] = None
    ) -> List[SocialPostData]:
        """Search recent X/Twitter posts for a ticker query, newest first, stopping at `since` or at the
        first already-stored tweet in `known_ids`."""
        pass


class MarketProviderInterface(ABC):
    @abstractmethod
    async def get_market_data(self, ticker: str) -> MarketData:
        """Fetch market data and historical price candles for a ticker."""
        pass

    async def fetch_market_data(self, ticker: str) -> MarketData:
        """Fetch market data alias."""
        return await self.get_market_data(ticker)


class PredictionMarketProvider(ABC):
    @abstractmethod
    async def get_markets(self, query: Optional[str] = None, ticker: Optional[str] = None) -> List[PredictionMarketData]:
        """Fetch relevant prediction markets for space sector or specific ticker."""
        pass

    @abstractmethod
    async def get_market(self, market_id: str) -> Optional[PredictionMarketData]:
        """Fetch details of a specific prediction market by ID."""
        pass

    @abstractmethod
    async def get_history(
        self,
        market_id: str,
        clob_token_id: Optional[str] = None,
        interval: str = "1w",
        fidelity: int = 60,
    ) -> List[MarketProbabilityPoint]:
        """Fetch historical probability points for a market over `interval`, one point per `fidelity` minutes."""
        pass


class SecFilingData(BaseModel):
    """One tracked EDGAR filing (see app/collectors/sec_forms.py for the categories)."""
    ticker: str
    cik: str
    accession_number: str
    form: str
    items: Optional[str] = None          # 8-K item codes, e.g. "1.01,2.03,3.02"
    category: str
    filed_date: str                      # YYYY-MM-DD as reported by EDGAR
    accepted_at: Optional[datetime] = None
    primary_document: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    source: str = "LIVE"                 # "LIVE", "MOCK"


class SecFetchResult(BaseModel):
    """status: OK (index read), NOT_APPLICABLE (no CIK for the symbol), DISABLED (no SEC_USER_AGENT set)."""
    status: str = "OK"
    cik: Optional[str] = None
    filings: List[SecFilingData] = []
    detail: str = ""


class SecFilingsProvider(ABC):
    @abstractmethod
    async def fetch_filings(self, ticker: str, cik: Optional[str] = None) -> SecFetchResult:
        """Tracked filings (offerings, shelves, financing 8-Ks) from the company's EDGAR submissions index.
        Raises on a network or parsing failure so the caller can keep FILING alerts open."""
        pass
