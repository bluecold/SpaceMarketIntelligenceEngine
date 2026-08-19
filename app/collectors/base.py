from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel


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


class MarketData(BaseModel):
    ticker: str
    timestamp: datetime
    price: Optional[float]
    volume: Optional[float]
    status: str = "AVAILABLE"  # "AVAILABLE", "DATA_UNAVAILABLE", "ERROR"
    raw_df: Optional[Any] = None  # DataFrame of historical OHLCV


class MarketProbabilityPoint(BaseModel):
    timestamp: datetime
    yes_probability: float
    no_probability: float
    volume: float = 0.0


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
    
    probability_change_1h: float = 0.0
    probability_change_6h: float = 0.0
    probability_change_24h: float = 0.0
    
    url: Optional[str] = None
    event_key: Optional[str] = None  # Mapping key if linked to cross-company event


class XProvider(ABC):
    @abstractmethod
    async def search(self, query: str, ticker: str, max_results: int = 100) -> List[SocialPostData]:
        """Search recent X/Twitter posts for a ticker query."""
        pass


class MarketProviderInterface(ABC):
    @abstractmethod
    async def get_market_data(self, ticker: str) -> MarketData:
        """Fetch market data and historical price candles for a ticker."""
        pass


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
    async def get_history(self, market_id: str) -> List[MarketProbabilityPoint]:
        """Fetch historical probability points for a market."""
        pass
