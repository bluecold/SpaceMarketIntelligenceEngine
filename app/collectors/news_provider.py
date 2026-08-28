import logging
import urllib.parse
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class NewsItemData(BaseModel):
    ticker: str
    title: str
    summary: Optional[str] = None
    source: Optional[str] = None
    url: str
    published_at: datetime


class BaseNewsProvider(ABC):
    @abstractmethod
    async def fetch_news(self, query: str, ticker: str, max_results: int = 15) -> List[NewsItemData]:
        pass


class GoogleRSSNewsProvider(BaseNewsProvider):
    """
    Fetches real-time financial and aerospace news from Google News RSS feed without requiring API keys.
    """
    BASE_URL = "https://news.google.com/rss/search"

    async def fetch_news(self, query: str, ticker: str, max_results: int = 15) -> List[NewsItemData]:
        encoded_q = urllib.parse.quote(f"{query} stock OR space")
        rss_url = f"{self.BASE_URL}?q={encoded_q}&hl=en-US&gl=US&ceid=US:en"

        news_items = []
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                resp = await client.get(rss_url, headers=headers)
                if resp.status_code != 200:
                    logger.warning(f"Google RSS news fetch returned status {resp.status_code} for query {query}")
                    return []

                root = ET.fromstring(resp.text)
                channel = root.find("channel")
                if channel is None:
                    return []

                for item in channel.findall("item")[:max_results]:
                    title_elem = item.find("title")
                    link_elem = item.find("link")
                    pub_elem = item.find("pubDate")
                    source_elem = item.find("source")

                    title = title_elem.text if title_elem is not None else ""
                    url = link_elem.text if link_elem is not None else ""
                    source = source_elem.text if source_elem is not None else "Google News"

                    published_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    if pub_elem is not None and pub_elem.text:
                        try:
                            dt = parsedate_to_datetime(pub_elem.text)
                            if dt.tzinfo is not None:
                                dt = dt.astimezone(timezone.utc)
                            published_at = dt.replace(tzinfo=None)
                        except Exception:
                            pass

                    if title and url:
                        news_items.append(NewsItemData(
                            ticker=ticker,
                            title=title,
                            summary=title,
                            source=source,
                            url=url,
                            published_at=published_at
                        ))

            logger.info(f"Google RSS collected {len(news_items)} news items for {ticker}.")
        except Exception as e:
            logger.error(f"Error fetching Google RSS news for {ticker}: {e}")

        return news_items


class MockNewsProvider(BaseNewsProvider):
    async def fetch_news(self, query: str, ticker: str, max_results: int = 15) -> List[NewsItemData]:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return [
            NewsItemData(
                ticker=ticker,
                title=f"{ticker} announces major satellite constellation deployment milestone",
                summary=f"Commercial aerospace firm {ticker} reaches critical orbital milestone.",
                source="SpaceNews",
                url=f"https://spacenews.com/mock-{ticker.lower()}-1",
                published_at=now
            ),
            NewsItemData(
                ticker=ticker,
                title=f"Defense agency awards government payload defense contract to {ticker}",
                summary=f"New recurring revenue partnership sealed by {ticker}.",
                source="AviationWeek",
                url=f"https://aviationweek.com/mock-{ticker.lower()}-2",
                published_at=now
            )
        ]
