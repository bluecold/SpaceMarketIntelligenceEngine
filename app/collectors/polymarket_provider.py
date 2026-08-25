import json
import logging
from typing import List, Optional
from datetime import datetime, timezone
import httpx
from app.config import settings
from app.collectors.base import PredictionMarketProvider, PredictionMarketData, MarketProbabilityPoint
from app.collectors.mock_polymarket_provider import MockPolymarketProvider
from app.prediction.quality import calculate_market_quality

logger = logging.getLogger("SMIE.PolymarketProvider")


class PolymarketGammaProvider(PredictionMarketProvider):
    """
    Polymarket Provider interacting with Polymarket's public Gamma API.
    Gracefully handles rate limits, connection errors, and falls back if network is unreachable.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.POLYMARKET_API_URL
        self._fallback_provider = MockPolymarketProvider()

    async def get_markets(self, query: Optional[str] = None, ticker: Optional[str] = None) -> List[PredictionMarketData]:
        """Fetch space-related markets from Polymarket Gamma API."""
        try:
            params = {
                "tag": "space",
                "limit": 50,
                "active": "true",
                "closed": "false"
            }
            if query:
                params["title"] = query

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{self.base_url}/events", params=params)
                
                if resp.status_code == 200:
                    events = resp.json()
                    markets_list: List[PredictionMarketData] = []
                    
                    for event in events:
                        for m in event.get("markets", []):
                            market_data = self._parse_gamma_market(event, m, ticker)
                            if market_data:
                                markets_list.append(market_data)
                                
                    if markets_list:
                        return markets_list
                        
                logger.warning(f"Polymarket Gamma API returned status {resp.status_code}. Using fallback mock data.")
                return await self._fallback_provider.get_markets(query=query, ticker=ticker)

        except Exception as e:
            logger.warning(f"Error connecting to Polymarket Gamma API ({e}). Using mock provider fallback.")
            return await self._fallback_provider.get_markets(query=query, ticker=ticker)

    async def get_market(self, market_id: str) -> Optional[PredictionMarketData]:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(f"{self.base_url}/markets/{market_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    return self._parse_gamma_market({}, data, None)
        except Exception:
            pass
        return await self._fallback_provider.get_market(market_id)

    async def get_history(self, market_id: str) -> List[MarketProbabilityPoint]:
        """Fetch historical probability curve from Polymarket CLOB prices-history or fallback."""
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    "https://clob.polymarket.com/prices-history",
                    params={"interval": "1d", "market": market_id}
                )
                if resp.status_code == 200:
                    data = resp.json().get("history", [])
                    points = []
                    for item in data:
                        t_val = item.get("t")
                        p_val = float(item.get("p", 0.5))
                        v_val = float(item.get("v", 0.0))
                        dt = datetime.fromtimestamp(t_val, tz=timezone.utc) if t_val else datetime.now(timezone.utc)
                        points.append(MarketProbabilityPoint(
                            timestamp=dt,
                            probability=p_val,
                            volume=v_val
                        ))
                    if points:
                        return points
        except Exception as e:
            logger.debug(f"Could not fetch CLOB price history for {market_id} ({e}). Using mock provider.")
        return await self._fallback_provider.get_history(market_id)

    def _parse_gamma_market(self, event: dict, m: dict, ticker: Optional[str]) -> Optional[PredictionMarketData]:
        try:
            outcomes = m.get("outcomes", [])
            outcome_prices = m.get("outcomePrices", [])
            
            # Polymarket outcome prices are JSON strings or lists of floats e.g. ["0.72", "0.28"]
            yes_prob = 0.50
            if outcome_prices:
                if isinstance(outcome_prices, str):
                    try:
                        parsed = json.loads(outcome_prices)
                        yes_prob = float(parsed[0])
                    except Exception:
                        pass
                elif isinstance(outcome_prices, list) and len(outcome_prices) > 0:
                    yes_prob = float(outcome_prices[0])

            volume = float(m.get("volumeNum") or m.get("volume") or event.get("volume") or 0.0)
            liquidity = float(m.get("liquidityNum") or m.get("liquidity") or event.get("liquidity") or 0.0)
            spread = float(m.get("spread") or 0.02)
            
            # Extract 24h price/probability delta from Gamma API if present
            raw_delta_24h = (
                m.get("oneDayPriceChange")
                or m.get("priceChange24h")
                or m.get("priceChange")
                or event.get("oneDayPriceChange")
                or 0.0
            )
            try:
                prob_delta_24h = float(raw_delta_24h) * 100.0 if abs(float(raw_delta_24h)) <= 1.0 else float(raw_delta_24h)
            except Exception:
                prob_delta_24h = 0.0

            end_date_str = m.get("endDate") or event.get("endDate")
            end_date = None
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            qual = calculate_market_quality(liquidity=liquidity, volume=volume, spread=spread, end_date=end_date)

            return PredictionMarketData(
                external_id=str(m.get("id") or m.get("conditionId") or event.get("id")),
                ticker=ticker,
                title=m.get("question") or event.get("title", "Space Market Event"),
                description=m.get("description") or event.get("description"),
                category="SPACE",
                status="ACTIVE",
                created_at=datetime.now(timezone.utc),
                end_date=end_date,
                yes_probability=round(yes_prob, 4),
                no_probability=round(1.0 - yes_prob, 4),
                volume=volume,
                liquidity=liquidity,
                spread=spread,
                quality_score=qual,
                probability_change_1h=0.0,
                probability_change_6h=0.0,
                probability_change_24h=round(prob_delta_24h, 2),
                url=f"https://polymarket.com/event/{event.get('slug', '')}" if event.get("slug") else None
            )
        except Exception as e:
            logger.debug(f"Failed parsing market: {e}")
            return None
