import random
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from app.collectors.base import PredictionMarketProvider, PredictionMarketData, MarketProbabilityPoint
from app.prediction.quality import calculate_market_quality


class MockPolymarketProvider(PredictionMarketProvider):
    """
    Realistic Mock Provider for Polymarket Space & Defense Prediction Markets.
    Generates structured market data and synthetic historical probability series.
    """

    def __init__(self):
        self._markets: List[PredictionMarketData] = []
        self._init_mock_markets()

    def _init_mock_markets(self):
        now = datetime.now(timezone.utc)
        
        raw_definitions = [
            # Direct Ticker Markets
            {
                "external_id": "poly-asts-commercial-service-2026",
                "ticker": "ASTS",
                "title": "Will AST SpaceMobile launch commercial service before Q4 2026?",
                "description": "Resolves YES if AST SpaceMobile officially initiates commercial broadband service with AT&T or Verizon.",
                "category": "SPACE_COMMUNICATIONS",
                "yes_prob": 0.76,
                "volume": 342000.0,
                "liquidity": 85000.0,
                "spread": 0.02,
                "delta_1h": 0.5,
                "delta_6h": 2.1,
                "delta_24h": 6.8,
                "days_left": 120,
                "url": "https://polymarket.com/market/asts-commercial-broadband-2026"
            },
            {
                "external_id": "poly-rklb-neutron-flight-2026",
                "ticker": "RKLB",
                "title": "Will Rocket Lab launch Neutron rocket in 2026?",
                "description": "Resolves YES if Rocket Lab conducts an orbital test flight of Neutron from Wallops Island.",
                "category": "LAUNCH_VEHICLES",
                "yes_prob": 0.68,
                "volume": 520000.0,
                "liquidity": 115000.0,
                "spread": 0.015,
                "delta_1h": -0.2,
                "delta_6h": 1.4,
                "delta_24h": 4.5,
                "days_left": 95,
                "url": "https://polymarket.com/market/rocket-lab-neutron-launch-2026"
            },
            {
                "external_id": "poly-spce-delta-revenue-2026",
                "ticker": "SPCE",
                "title": "Will Virgin Galactic generate over $10M revenue in 2026?",
                "description": "Resolves YES if Virgin Galactic reports annual revenue exceeding $10M from Delta-class spaceships.",
                "category": "SPACE_TOURISM",
                "yes_prob": 0.38,
                "volume": 125000.0,
                "liquidity": 32000.0,
                "spread": 0.04,
                "delta_1h": -0.8,
                "delta_6h": -1.5,
                "delta_24h": -3.2,
                "days_left": 140,
                "url": "https://polymarket.com/market/virgin-galactic-delta-revenue"
            },
            {
                "external_id": "poly-satl-defense-award-2026",
                "ticker": "SATL",
                "title": "Will Satellogic secure >$20M US or NATO defense imaging contract in 2026?",
                "description": "Resolves YES if Satellogic announces a cumulative contract value >=$20M with defense agencies.",
                "category": "EARTH_OBSERVATION",
                "yes_prob": 0.55,
                "volume": 88000.0,
                "liquidity": 24000.0,
                "spread": 0.035,
                "delta_1h": 0.0,
                "delta_6h": 0.5,
                "delta_24h": 1.5,
                "days_left": 130,
                "url": "https://polymarket.com/market/satellogic-defense-contracts"
            },
            # Sector-wide Events (Cross-Company Event Mapping)
            {
                "external_id": "poly-spacex-starship-orbital-catch",
                "ticker": "SPCX",
                "event_key": "spacex_starship_orbital_success",
                "title": "Will SpaceX successfully catch Starship Upper Stage from orbit in 2026?",
                "description": "Resolves YES if SpaceX performs a successful catch of the Starship ship at Starbase.",
                "category": "HEAVY_LAUNCH",
                "yes_prob": 0.82,
                "volume": 1850000.0,
                "liquidity": 420000.0,
                "spread": 0.01,
                "delta_1h": 1.2,
                "delta_6h": 4.0,
                "delta_24h": 9.5,
                "days_left": 45,
                "url": "https://polymarket.com/market/spacex-starship-upper-stage-catch"
            },
            {
                "external_id": "poly-us-space-force-sda-tranche-awards",
                "ticker": None,
                "event_key": "us_space_force_sda_defense_contracts",
                "title": "Will US Space Force SDA award Tranche 3 satellite constellation contracts by Q3?",
                "description": "Resolves YES if the Space Development Agency awards Tranche 3 Tracking/Transport contracts.",
                "category": "DEFENSE_SPACE",
                "yes_prob": 0.74,
                "volume": 610000.0,
                "liquidity": 160000.0,
                "spread": 0.02,
                "delta_1h": 0.3,
                "delta_6h": 1.8,
                "delta_24h": 5.2,
                "days_left": 60,
                "url": "https://polymarket.com/market/us-space-force-sda-tranche-3"
            }
        ]

        self._markets = []
        for defn in raw_definitions:
            end_date = now + timedelta(days=defn["days_left"])
            qual = calculate_market_quality(
                liquidity=defn["liquidity"],
                volume=defn["volume"],
                spread=defn["spread"],
                end_date=end_date
            )
            
            market = PredictionMarketData(
                external_id=defn["external_id"],
                ticker=defn.get("ticker"),
                title=defn["title"],
                description=defn["description"],
                category=defn["category"],
                status="ACTIVE",
                created_at=now - timedelta(days=30),
                end_date=end_date,
                yes_probability=defn["yes_prob"],
                no_probability=round(1.0 - defn["yes_prob"], 4),
                volume=defn["volume"],
                liquidity=defn["liquidity"],
                spread=defn["spread"],
                quality_score=qual,
                probability_change_1h=defn["delta_1h"],
                probability_change_6h=defn["delta_6h"],
                probability_change_24h=defn["delta_24h"],
                url=defn["url"],
                event_key=defn.get("event_key")
            )
            self._markets.append(market)

    async def get_markets(self, query: Optional[str] = None, ticker: Optional[str] = None) -> List[PredictionMarketData]:
        results = self._markets
        if ticker:
            ticker_upper = ticker.upper()
            # Return direct markets or cross-company event markets
            results = [m for m in results if (m.ticker and m.ticker.upper() == ticker_upper) or m.event_key is not None]
        if query:
            q = query.lower()
            results = [m for m in results if q in m.title.lower() or (m.description and q in m.description.lower())]
        return results

    async def get_market(self, market_id: str) -> Optional[PredictionMarketData]:
        for m in self._markets:
            if m.external_id == market_id:
                return m
        return None

    async def get_history(self, market_id: str) -> List[MarketProbabilityPoint]:
        market = await self.get_market(market_id)
        if not market:
            return []
            
        points: List[MarketProbabilityPoint] = []
        now = datetime.now(timezone.utc)
        current_prob = market.yes_probability
        
        # Synthesize realistic 24-hour hourly history leading up to current probability
        d24 = market.probability_change_24h / 100.0
        start_prob = current_prob - d24
        
        for h in range(24, -1, -1):
            ts = now - timedelta(hours=h)
            progress = (24 - h) / 24.0
            # Interpolate with slight micro-noise
            noise = (random.random() - 0.5) * 0.005 if h > 0 else 0.0
            p = min(0.99, max(0.01, start_prob + progress * d24 + noise))
            points.append(MarketProbabilityPoint(
                timestamp=ts,
                yes_probability=round(p, 4),
                no_probability=round(1.0 - p, 4),
                volume=round(market.volume * (0.85 + 0.15 * progress), 2)
            ))
            
        return points
