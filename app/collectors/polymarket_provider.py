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

    def has_any(words) -> bool:
        # Word boundaries: a bare substring check matched "sda" inside "Wednesday"/"Thursday" and mapped
        # geomagnetic-storm markets to Space Force contracts
        return any(re.search(rf"\b{re.escape(w)}\b", text_lower) for w in words)

    # 1. Starlink direct-to-cell / FCC approval
    if ("starlink" in text_lower and has_any(["cell", "fcc", "direct", "t-mobile", "broadband"])) or "direct-to-cell" in text_lower:
        return "spacex_starlink_direct_to_cell_fcc_approval"

    # 2. Starship orbital / flight tests / upper stage catch
    if has_any(["starship", "starships", "super heavy", "starbase", "orbital catch", "orbital flight"]):
        return "spacex_starship_orbital_success"

    # 3. NASA Artemis / Moon contract expansion
    if has_any(["artemis", "lunar gateway", "moon lander", "hls", "artemis contract", "nasa moon"]):
        return "nasa_artemis_moon_contract_expansion"

    # 4. US Space Force SDA defense contracts
    if has_any(["space force", "space development agency", "sda", "defense space", "nssl", "tranche 3", "tranche 2", "tranche 1"]):
        return "us_space_force_sda_defense_contracts"

    # 5. Commercial launch cadence records
    if has_any(["launch cadence", "orbital launches", "annual launches", "launch record", "cadence record"]):
        return "commercial_launch_cadence_record"

    # 6. Direct key match if event_key or slug matches any key in DEFAULT_EVENT_COMPANY_MAPPINGS
    for k in DEFAULT_EVENT_COMPANY_MAPPINGS.keys():
        if k in text_lower or k.replace("_", "-") in text_lower:
            return k

    return None


# Reviewable explicit polarity overlays for known Polymarket event keys / slugs / IDs
# +1 = Bullish when YES occurs, -1 = Bearish when YES occurs
PMS_EXPLICIT_POLARITY_MAP: dict = {}


def determine_market_polarity(
    question: str,
    slug: str = "",
    description: str = "",
    external_id: Optional[str] = None,
    event_key: Optional[str] = None
) -> int:
    """
    Determines whether a YES outcome is Bullish (+1) or Bearish (-1) for the target space entity.
    
    1. Checks reviewable explicit mappings (PMS_EXPLICIT_POLARITY_MAP).
    2. Isolates resolution conditions ('Resolves No in case of launch failure') from description
       so that negative failure criteria describing the NO outcome do not invert a positive YES question.
    3. Evaluates affirmative vs negative framing in question/title and slug:
       - Success/positive affirmations ('launch successfully', 'reach orbit', 'win') -> +1
       - Negative predicates ('will ... delay', 'fail to', 'file for bankruptcy', 'crash') -> -1
    """
    # 1. Check explicit reviewable mapping
    for key in [external_id, slug, event_key]:
        if key and key in PMS_EXPLICIT_POLARITY_MAP:
            return PMS_EXPLICIT_POLARITY_MAP[key]

    q_clean = (question or "").lower().strip()
    slug_clean = (slug or "").lower().strip()

    # 2. Positive affirmations in the question
    positive_affirmation_patterns = [
        r"\bsuccess(ful|fully)?\b",
        r"\breach(es|ed)?\s+orbit\b",
        r"\bland(s|ed|ing)?\s+(?:on|successfully)\b",
        r"\bdeploy(ed|ment)?\s+complete\b",
        r"\bwin(s|ning)?\b",
        r"\bawarded\b",
        r"\bbeat(s)?\b"
    ]
    has_positive_affirmation = any(re.search(pat, q_clean) for pat in positive_affirmation_patterns)

    # 3. Negative predicates in the question itself
    negative_question_patterns = [
        r"\bdelay(ed|ing|s)?\b",
        r"\bfail(ure|s|ed|ing)?\b",
        r"\bcancel(led|lation|s|ing)?\b",
        r"\bcrash(ed|ing|es)?\b",
        r"\bbankrupt(cy)?\b",
        r"\bground(ed|ing)?\b",
        r"\bpostpone(d|ing|s)?\b",
        r"\banomaly\b",
        r"\blost\b"
    ]
    has_negative_in_question = False
    for pat in negative_question_patterns:
        m = re.search(pat, q_clean)
        if m:
            # Check for negation: e.g. "will not fail", "without delay"
            start_idx = max(0, m.start() - 25)
            preceding = q_clean[start_idx:m.start()]
            if re.search(r"\b(not|no|without|never)\s+(?:to\s+)?$", preceding.strip()):
                continue
            has_negative_in_question = True
            break

    # If question has positive affirmation and no negative predicate -> +1
    if has_positive_affirmation and not has_negative_in_question:
        return 1

    # If question explicitly asks if a negative event occurs -> -1
    if has_negative_in_question:
        return -1

    # 4. If question is neutral, inspect slug
    has_negative_in_slug = any(re.search(pat, slug_clean) for pat in negative_question_patterns)
    if has_negative_in_slug:
        return -1

    # 5. If question and slug are neutral, check description
    # CRITICAL: Isolate and strip resolution conditions that specify resolution to "No"
    # Examples: "Resolves No in case of launch failure", "Resolves to 'No' if delayed or cancelled"
    if description:
        stripped_desc = re.sub(
            r'(?:resolves?\s+(?:to\s+)?["\']?no["\']?\s+(?:if|in case of|upon|should)\b[^.]*|'
            r'\b(?:if|in case of)\s+[^.,;]+\bresolves?\s+(?:to\s+)?["\']?no["\']?|'
            r'\bresolves?\s+(?:to\s+)?["\']?no["\']?\b[^.\n]*)',
            ' ',
            description,
            flags=re.IGNORECASE
        )
        # Check if remaining description frames YES on a negative event
        yes_resolves_on_negative = re.search(
            r'resolves?\s+(?:to\s+)?["\']?yes["\']?\s+(?:if|in case of|upon)\s+[^.]*\b(?:delay|fail|cancel|crash|bankrupt)',
            stripped_desc,
            flags=re.IGNORECASE
        )
        if yes_resolves_on_negative:
            return -1

    return 1


class PolymarketGammaProvider(PredictionMarketProvider):
    """
    Polymarket Provider interacting with Polymarket's public Gamma API.
    Gracefully handles rate limits, connection errors, and falls back if network is unreachable.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.POLYMARKET_API_URL
        self._fallback_provider = MockPolymarketProvider()

    async def get_markets(
        self,
        query: Optional[str] = None,
        ticker: Optional[str] = None,
        max_pages: int = 3,
        page_limit: int = 50
    ) -> List[PredictionMarketData]:
        """Fetch space-related markets from Polymarket Gamma API using official parameters and pagination."""
        try:
            markets_list: List[PredictionMarketData] = []
            seen_external_ids = set()

            async with httpx.AsyncClient(timeout=10.0) as client:
                for page in range(max_pages):
                    params = {
                        "tag_slug": "space",
                        "limit": page_limit,
                        "offset": page * page_limit,
                        "active": "true",
                        "closed": "false"
                    }
                    if query:
                        params["title"] = query

                    resp = await client.get(f"{self.base_url}/events", params=params)
                    if resp.status_code != 200:
                        # Fallback for API variances if tag_slug is rejected
                        if page == 0 and resp.status_code in (400, 422):
                            fallback_params = {"limit": page_limit, "active": "true", "closed": "false"}
                            if query:
                                fallback_params["title"] = query
                            resp = await client.get(f"{self.base_url}/events", params=fallback_params)
                        if resp.status_code != 200:
                            err_msg = f"Polymarket Gamma API returned status {resp.status_code} for query '{query}'"
                            logger.warning(err_msg)
                            raise RuntimeError(err_msg)

                    events = resp.json()
                    if not isinstance(events, list) or len(events) == 0:
                        break

                    for event in events:
                        for m in event.get("markets", []):
                            market_data = self._parse_gamma_market(event, m, ticker)
                            if market_data and market_data.external_id not in seen_external_ids:
                                seen_external_ids.add(market_data.external_id)
                                markets_list.append(market_data)

                    if len(events) < page_limit:
                        break

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
                logger.warning("Polymarket Gamma API returned 0 markets. Using fallback mock data.")
                return await self._fallback_provider.get_markets(query=query, ticker=ticker)
            logger.info("Polymarket Gamma API returned 0 markets legitimately.")
            return []

        except Exception as e:
            if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                logger.warning(f"Error connecting to Polymarket Gamma API ({e}). Using mock provider fallback.")
                return await self._fallback_provider.get_markets(query=query, ticker=ticker)
            logger.error(f"Error connecting to Polymarket Gamma API ({e}). ALLOW_MOCK_FALLBACK=False, propagating exception.")
            raise

    async def get_market(self, market_id: str) -> Optional[PredictionMarketData]:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(f"{self.base_url}/markets/{market_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    return self._parse_gamma_market({}, data, None)
        except Exception:
            pass
        if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
            return await self._fallback_provider.get_market(market_id)
        return None

    async def get_history(self, market_id: str, clob_token_id: Optional[str] = None) -> List[MarketProbabilityPoint]:
        """Fetch historical probability curve from Polymarket CLOB prices-history or fallback."""
        target_token = clob_token_id
        if not target_token:
            # Check if market_id looks like a CLOB token ID (typically >30 digits)
            if market_id and len(str(market_id)) >= 30:
                target_token = str(market_id)
            else:
                # Gamma short ID: resolve clobTokenId via Gamma /markets/{market_id}
                try:
                    async with httpx.AsyncClient(timeout=6.0) as client:
                        resp = await client.get(f"{self.base_url}/markets/{market_id}")
                        if resp.status_code == 200:
                            market_json = resp.json()
                            parsed = self._parse_gamma_market({}, market_json, None)
                            if parsed and parsed.clob_token_id:
                                target_token = parsed.clob_token_id
                except Exception as e:
                    logger.debug(f"Could not resolve CLOB token for Gamma ID {market_id}: {e}")

        target_token = target_token or market_id
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(
                    "https://clob.polymarket.com/prices-history",
                    params={"interval": "1d", "market": target_token}
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
                            volume=round(v_val, 2),
                            source="LIVE"
                        ))
                    if points:
                        return points
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            logger.warning(f"Network error fetching CLOB price history for {target_token} ({e}).")
        except Exception as e:
            logger.error(f"Error parsing Polymarket CLOB price history for {target_token} ({e}).", exc_info=True)
        if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
            return await self._fallback_provider.get_history(market_id, clob_token_id)
        return []

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

            # Extract clobTokenIds (JSON string or list) and match to yes_idx
            clob_tokens_raw = m.get("clobTokenIds") or []
            if isinstance(clob_tokens_raw, str):
                try:
                    clob_tokens_raw = json.loads(clob_tokens_raw)
                except Exception:
                    clob_tokens_raw = []

            clob_token_id = None
            if isinstance(clob_tokens_raw, list) and len(clob_tokens_raw) > yes_idx:
                clob_token_id = str(clob_tokens_raw[yes_idx]).strip()
            elif isinstance(clob_tokens_raw, list) and len(clob_tokens_raw) > 0:
                clob_token_id = str(clob_tokens_raw[0]).strip()

            condition_id = str(m.get("conditionId") or m.get("condition_id") or "").strip() or None

            vol_raw = m.get("volumeNum") if m.get("volumeNum") is not None else m.get("volume")
            volume = float(vol_raw) if vol_raw is not None else 0.0

            liq_raw = m.get("liquidityNum") if m.get("liquidityNum") is not None else m.get("liquidity")
            liquidity = float(liq_raw) if liq_raw is not None else 0.0

            spread = float(m.get("spread") or 0.02)
            
            # Extract 24h price/probability delta from Gamma API if present (do not inherit event delta)
            raw_delta_24h = (
                m.get("oneDayPriceChange")
                if m.get("oneDayPriceChange") is not None
                else (m.get("priceChange24h") if m.get("priceChange24h") is not None else m.get("priceChange"))
            )
            prob_delta_24h = None
            if raw_delta_24h is not None:
                try:
                    delta_val = float(raw_delta_24h)
                    prob_delta_24h = delta_val * 100.0 if abs(delta_val) <= 1.0 else delta_val
                except Exception:
                    prob_delta_24h = None

            end_date_str = m.get("endDate") or event.get("endDate") or m.get("end_date")
            end_date = None
            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(str(end_date_str).replace("Z", "+00:00"))
                except Exception:
                    pass

            res_date_str = m.get("resolutionDate") or event.get("resolutionDate") or m.get("resolution_date")
            resolution_date = None
            if res_date_str:
                try:
                    resolution_date = datetime.fromisoformat(str(res_date_str).replace("Z", "+00:00"))
                except Exception:
                    pass

            # Dynamically infer market status from flags and expiration
            is_closed = (
                bool(m.get("closed"))
                or bool(event.get("closed"))
                or bool(m.get("resolved"))
                or bool(event.get("resolved"))
            )
            is_active = (
                bool(m.get("active", True))
                and bool(event.get("active", True))
                and not is_closed
            )
            now_utc = datetime.now(timezone.utc)

            if is_closed or m.get("resolved") or event.get("resolved"):
                status = "RESOLVED" if (m.get("resolved") or event.get("resolved") or resolution_date is not None) else "CLOSED"
            elif not is_active:
                status = "CLOSED"
            elif end_date and end_date < now_utc:
                status = "CLOSED"
            else:
                status = "ACTIVE"

            qual = calculate_market_quality(liquidity=liquidity, volume=volume, spread=spread, end_date=end_date)

            title_text = m.get("question") or event.get("title", "Space Market Event")
            desc_text = m.get("description") or event.get("description", "")
            slug_text = event.get("slug", "") or m.get("slug", "")
            combined_text = f"{title_text} {slug_text} {desc_text}"

            resolved_ticker = ticker or match_ticker_from_text(combined_text)
            resolved_event_key = match_event_key_from_text(combined_text)
            external_id = str(m.get("id") or m.get("conditionId") or event.get("id"))

            polarity = determine_market_polarity(
                question=title_text,
                slug=slug_text,
                description=desc_text,
                external_id=external_id,
                event_key=resolved_event_key
            )

            return PredictionMarketData(
                external_id=external_id,
                ticker=resolved_ticker,
                event_key=resolved_event_key,
                clob_token_id=clob_token_id,
                condition_id=condition_id,
                title=title_text,
                description=desc_text if desc_text else None,
                category="SPACE",
                status=status,
                created_at=datetime.now(timezone.utc),
                end_date=end_date,
                resolution_date=resolution_date,
                yes_probability=round(yes_prob, 4),
                no_probability=round(1.0 - yes_prob, 4),
                volume=volume,
                liquidity=liquidity,
                spread=spread,
                quality_score=qual,
                probability_change_1h=0.0,
                probability_change_6h=0.0,
                probability_change_24h=round(prob_delta_24h, 2) if prob_delta_24h is not None else None,
                url=f"https://polymarket.com/event/{event.get('slug', '')}" if event.get("slug") else None,
                polarity=polarity,
                source="LIVE",
                outcome_group=str(event.get("id")) if (event.get("negRisk") or m.get("negRisk")) and event.get("id") else None,
                outcome_label=(m.get("groupItemTitle") or None)
            )
        except Exception as e:
            logger.debug(f"Failed parsing market: {e}")
            return None
