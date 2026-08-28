import json
import logging
import re
from typing import List, Optional
from datetime import datetime, timezone
import httpx
from app.config import settings, INITIAL_TICKERS, DEFAULT_EVENT_COMPANY_MAPPINGS
from app.collectors.base import PredictionMarketProvider, PredictionMarketData, MarketProbabilityPoint
from app.collectors.mock_polymarket_provider import MockPolymarketProvider
from app.prediction.quality import calculate_market_quality

logger = logging.getLogger("SMIE.PolymarketProvider")


def match_ticker_from_text(text: str) -> Optional[str]:
    """
    Matches a space sector ticker symbol from text (title, slug, description)
    using word boundaries to prevent substring false positives.
    """
    if not text:
        return None
    for cfg in INITIAL_TICKERS:
        patterns = [
            rf"\b{re.escape(cfg.symbol)}\b",
            rf"\${re.escape(cfg.symbol)}\b"
        ]
        for alias in cfg.aliases:
            clean = alias.lstrip("$")
            patterns.append(rf"\b{re.escape(clean)}\b")
            patterns.append(rf"\${re.escape(clean)}\b")

        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                return cfg.symbol
    return None


def match_event_key_from_text(text: str) -> Optional[str]:
    """
    Matches an event_key from DEFAULT_EVENT_COMPANY_MAPPINGS using semantic keyword signatures.
    """
    if not text:
        return None
    text_lower = text.lower()

    # 1. Starlink direct-to-cell / FCC approval
    if ("starlink" in text_lower and any(w in text_lower for w in ["cell", "fcc", "direct", "t-mobile", "broadband"])) or "direct-to-cell" in text_lower:
        return "spacex_starlink_direct_to_cell_fcc_approval"

    # 2. Starship orbital / flight tests / upper stage catch
    if any(w in text_lower for w in ["starship", "super heavy", "starbase", "orbital catch", "orbital flight"]):
        return "spacex_starship_orbital_success"

    # 3. NASA Artemis / Moon contract expansion
    if any(w in text_lower for w in ["artemis", "lunar gateway", "moon lander", "hls", "artemis contract", "nasa moon"]):
        return "nasa_artemis_moon_contract_expansion"

    # 4. US Space Force SDA defense contracts
    if any(w in text_lower for w in ["space force", "space development agency", "sda", "defense space", "nssl", "tranche 3", "tranche 2", "tranche 1"]):
        return "us_space_force_sda_defense_contracts"

    # 5. Commercial launch cadence records
    if any(w in text_lower for w in ["launch cadence", "orbital launches", "annual launches", "launch record", "cadence record"]):
        return "commercial_launch_cadence_record"

    # 6. Direct key match if event_key or slug matches any key in DEFAULT_EVENT_COMPANY_MAPPINGS
    for k in DEFAULT_EVENT_COMPANY_MAPPINGS.keys():
        if k in text_lower or k.replace("_", "-") in text_lower:
            return k

    return None


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
                        if ticker:
                            ticker_up = ticker.upper()
                            filtered = [
                                m for m in markets_list
                                if (m.ticker and m.ticker.upper() == ticker_up)
                                or (m.event_key and m.event_key in DEFAULT_EVENT_COMPANY_MAPPINGS and ticker_up in DEFAULT_EVENT_COMPANY_MAPPINGS[m.event_key])
                            ]
                            return filtered if filtered else markets_list
                        return markets_list
                        
                if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                    logger.warning(f"Polymarket Gamma API returned status {resp.status_code}. Using fallback mock data.")
                    return await self._fallback_provider.get_markets(query=query, ticker=ticker)
                logger.warning(f"Polymarket Gamma API returned status {resp.status_code}. ALLOW_MOCK_FALLBACK=False, returning empty dataset.")
                return []

        except Exception as e:
            if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                logger.warning(f"Error connecting to Polymarket Gamma API ({e}). Using mock provider fallback.")
                return await self._fallback_provider.get_markets(query=query, ticker=ticker)
            logger.error(f"Error connecting to Polymarket Gamma API ({e}). ALLOW_MOCK_FALLBACK=False, returning empty dataset.")
            return []

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
                        p_val = max(0.0, min(1.0, float(item.get("p", 0.5))))
                        v_val = float(item.get("v", 0.0))
                        dt = datetime.fromtimestamp(t_val, tz=timezone.utc) if t_val else datetime.now(timezone.utc)
                        points.append(MarketProbabilityPoint(
                            timestamp=dt,
                            yes_probability=round(p_val, 4),
                            no_probability=round(1.0 - p_val, 4),
                            volume=round(v_val, 2)
                        ))
                    if points:
                        return points
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Network error fetching CLOB price history for {market_id} ({e}). Using mock provider fallback.")
        except Exception as e:
            logger.error(f"Error parsing Polymarket CLOB price history for {market_id} ({e}). Using mock provider fallback.", exc_info=True)
        return await self._fallback_provider.get_history(market_id)

    def _parse_gamma_market(self, event: dict, m: dict, ticker: Optional[str]) -> Optional[PredictionMarketData]:
        try:
            outcomes = m.get("outcomes", [])
            outcome_prices = m.get("outcomePrices", [])
            
            if isinstance(outcomes, str):
                try:
                    outcomes = json.loads(outcomes)
                except Exception:
                    outcomes = []

            if isinstance(outcome_prices, str):
                try:
                    outcome_prices = json.loads(outcome_prices)
                except Exception:
                    outcome_prices = []

            # Dynamically locate index for "Yes" outcome (supports ["Yes", "No"] or ["No", "Yes"])
            yes_idx = 0
            if isinstance(outcomes, list):
                for idx, out_name in enumerate(outcomes):
                    if str(out_name).strip().lower() == "yes":
                        yes_idx = idx
                        break

            yes_prob = 0.50
            if isinstance(outcome_prices, list) and len(outcome_prices) > yes_idx:
                try:
                    yes_prob = float(outcome_prices[yes_idx])
                except Exception:
                    yes_prob = 0.50
            elif isinstance(outcome_prices, list) and len(outcome_prices) > 0:
                try:
                    yes_prob = float(outcome_prices[0])
                except Exception:
                    yes_prob = 0.50

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

            title_text = m.get("question") or event.get("title", "Space Market Event")
            desc_text = m.get("description") or event.get("description", "")
            slug_text = event.get("slug", "") or m.get("slug", "")
            combined_text = f"{title_text} {slug_text} {desc_text}"

            # Semantic polarity heuristic for negatively framed questions (e.g. failure, delay, cancellation)
            negative_keywords = [
                r"\bdelay(ed)?\b",
                r"\bfail(ure|s|ed)?\b",
                r"\bcancel(led|lation)?\b",
                r"\bcrash(ed)?\b",
                r"\bloss\b",
                r"\bbankrupt(cy)?\b",
                r"\bground(ed)?\b",
                r"\bpostpone(d)?\b",
                r"\banomaly\b",
                r"\blost\b"
            ]
            polarity = 1
            for pat in negative_keywords:
                if re.search(pat, combined_text, re.IGNORECASE):
                    polarity = -1
                    break

            resolved_ticker = ticker or match_ticker_from_text(combined_text)
            resolved_event_key = match_event_key_from_text(combined_text)

            return PredictionMarketData(
                external_id=str(m.get("id") or m.get("conditionId") or event.get("id")),
                ticker=resolved_ticker,
                event_key=resolved_event_key,
                title=title_text,
                description=desc_text if desc_text else None,
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
                url=f"https://polymarket.com/event/{event.get('slug', '')}" if event.get("slug") else None,
                polarity=polarity
            )
        except Exception as e:
            logger.debug(f"Failed parsing market: {e}")
            return None
