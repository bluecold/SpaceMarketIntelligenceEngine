import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from app.config import settings, INITIAL_TICKERS
from app.database.connection import SessionLocal, init_db
from app.database.repository import (
    ensure_tickers_seeded, save_social_posts, get_recent_social_posts,
    save_news_items, get_recent_news_items,
    save_prediction_markets, get_recent_prediction_markets,
    save_divergences, save_alerts, save_market_snapshot, get_latest_market_snapshot,
    save_ssi_snapshot, get_latest_ssi_snapshot, get_historical_ssi_snapshot,
    create_job_run, finish_job_run, utc_now,
    acquire_pipeline_job_lock, update_job_heartbeat
)
from app.collectors.mock_x_provider import MockXProvider
from app.collectors.twikit_provider import TwikitProvider
from app.collectors.market_provider import YFinanceMarketProvider
from app.collectors.news_provider import GoogleRSSNewsProvider, MockNewsProvider
from app.collectors.mock_polymarket_provider import MockPolymarketProvider
from app.collectors.polymarket_provider import PolymarketGammaProvider
from app.sentiment.classifier import get_sentiment_classifier
from app.sentiment.weighting import (
    calculate_engagement_score, calculate_recency_weight,
    calculate_relevance_score, detect_catalysts, calculate_news_score
)
from app.technical.indicators import calculate_technical_indicators
from app.technical.scorer import calculate_technical_score
from app.scoring.social import calculate_social_score, apply_bayesian_shrinkage
from app.scoring.prediction import calculate_prediction_market_score
from app.scoring.momentum import calculate_momentum_score
from app.scoring.risk import calculate_risk_score
from app.scoring.fundamentals import calculate_fundamental_score, get_fundamental_runway_info
from app.scoring.smi import calculate_smi
from app.scoring.signal import generate_signal_and_explanation
from app.divergence.detector import detect_divergences

logger = logging.getLogger("SMIE.Runner")


def get_x_provider():
    if settings.X_PROVIDER.lower() == "twikit":
        try:
            return TwikitProvider()
        except Exception:
            if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                return MockXProvider()
            return TwikitProvider()
    if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
        return MockXProvider()
    return TwikitProvider()


def get_news_provider():
    if getattr(settings, "NEWS_PROVIDER", "rss").lower() == "mock":
        return MockNewsProvider()
    return GoogleRSSNewsProvider()


def get_polymarket_provider():
    if settings.POLYMARKET_PROVIDER.lower() == "polymarket":
        return PolymarketGammaProvider()
    if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
        return MockPolymarketProvider()
    return PolymarketGammaProvider()


async def ingest_prediction_markets(db: SessionLocal, poly_provider=None) -> List[Any]:
    """Ingest and persist Polymarket prediction markets."""
    if not getattr(settings, "POLYMARKET_ENABLED", True):
        return []
    if poly_provider is None:
        poly_provider = get_polymarket_provider()
    logger.info("Ingesting Polymarket prediction markets...")
    poly_markets = await poly_provider.get_markets()
    if poly_markets:
        save_prediction_markets(db, poly_markets)
    return poly_markets or []


async def ingest_social_posts_for_ticker(
    db: SessionLocal,
    ticker_config,
    x_provider=None,
    sentiment_classifier=None
) -> tuple[int, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Ingest and persist social posts for a specific ticker with NLP feature extraction."""
    if x_provider is None:
        x_provider = get_x_provider()
    if sentiment_classifier is None:
        sentiment_classifier = get_sentiment_classifier()

    ticker = ticker_config.symbol
    query = f"${ticker} OR \"{ticker_config.name}\""
    posts_data = await x_provider.search(
        query=query, ticker=ticker, max_results=settings.SOCIAL_MAX_POSTS_PER_TICKER
    )

    texts = [p.text for p in posts_data]
    sentiments = sentiment_classifier.analyze_batch(texts) if texts else []
    processed_posts = []
    catalysts_found = []

    for i, p in enumerate(posts_data):
        sent_res = sentiments[i] if i < len(sentiments) else sentiment_classifier.analyze(p.text)
        rel_score = calculate_relevance_score(p.text, ticker, ticker_config.aliases)
        rec_weight = calculate_recency_weight(p.created_at)
        eng_score = calculate_engagement_score(p.likes, p.reposts, p.replies, p.views)

        post_cats = detect_catalysts(p.text, ticker=ticker)
        if rel_score >= 0.30:
            for c in post_cats:
                catalysts_found.append({"category": c["category"], "direction": c["direction"], "importance": c["importance"]})

        top_cat = post_cats[0] if post_cats else None
        cat_type = top_cat["category"] if top_cat else None
        cat_dir = top_cat["direction"] if top_cat else None
        cat_imp = top_cat["importance"] if top_cat else "MEDIUM"

        processed_posts.append({
            "tweet_id": p.tweet_id,
            "ticker": ticker,
            "username": p.username,
            "text": p.text,
            "url": p.url,
            "created_at": p.created_at,
            "likes": p.likes,
            "reposts": p.reposts,
            "replies": p.replies,
            "views": p.views,
            "sentiment_score": sent_res.score,
            "sentiment_label": sent_res.label,
            "sentiment_confidence": sent_res.confidence,
            "relevance_score": rel_score,
            "engagement_score": eng_score,
            "recency_weight": rec_weight,
            "catalyst": cat_type,
            "catalyst_direction": cat_dir,
            "catalyst_importance": cat_imp,
            "source": getattr(p, "source", "LIVE")
        })

    saved_count = 0
    if processed_posts:
        saved_count = save_social_posts(db, processed_posts)
    return saved_count, processed_posts, catalysts_found


async def ingest_news_for_ticker(
    db: SessionLocal,
    ticker_config,
    news_provider=None,
    sentiment_classifier=None
) -> tuple[int, List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Ingest and persist news items for a specific ticker with NLP feature extraction."""
    if news_provider is None:
        news_provider = get_news_provider()
    if sentiment_classifier is None:
        sentiment_classifier = get_sentiment_classifier()

    ticker = ticker_config.symbol
    news_items = await news_provider.fetch_news(query=f"{ticker} {ticker_config.name}", ticker=ticker, max_results=20)
    processed_news = []
    catalysts_found = []
    now_utc = utc_now()

    for n in news_items:
        text_content = f"{n.title}. {n.summary}"
        sent_res = sentiment_classifier.analyze(text_content)
        rel_score = calculate_relevance_score(text_content, ticker, ticker_config.aliases)
        news_cats = detect_catalysts(text_content, ticker=ticker)

        # Recency Gate (P1.5 audit fix): Only recent articles (<= 3 days) generate active alerts
        is_recent_news = True
        if n.published_at:
            pub_dt = n.published_at.replace(tzinfo=None) if n.published_at.tzinfo is not None else n.published_at
            is_recent_news = (now_utc - pub_dt).total_seconds() <= (3 * 86400)

        if rel_score >= 0.30 and is_recent_news:
            for c in news_cats:
                catalysts_found.append({"category": c["category"], "direction": c["direction"], "importance": c["importance"]})

        top_cat = news_cats[0] if news_cats else None
        cat_type = top_cat["category"] if top_cat else None
        cat_dir = top_cat["direction"] if top_cat else None
        cat_imp = top_cat["importance"] if top_cat else "MEDIUM"

        processed_news.append({
            "ticker": ticker,
            "title": n.title,
            "summary": n.summary,
            "source": n.source,
            "url": n.url,
            "published_at": n.published_at,
            "sentiment_score": sent_res.score,
            "sentiment_label": sent_res.label,
            "sentiment_confidence": sent_res.confidence,
            "relevance_score": rel_score,
            "catalyst": cat_type,
            "catalyst_direction": cat_dir,
            "catalyst_importance": cat_imp
        })

    saved_count = 0
    if processed_news:
        saved_count = save_news_items(db, processed_news)
    return saved_count, processed_news, catalysts_found


async def ingest_market_for_ticker(
    db: SessionLocal,
    ticker_config,
    market_provider=None
) -> tuple[Dict[str, Any], Optional[Any]]:
    """Fetch market data, calculate technical indicators & score, and persist snapshot."""
    if market_provider is None:
        market_provider = YFinanceMarketProvider()
    ticker = ticker_config.symbol
    indicators = {
        "status": "AVAILABLE" if not ticker_config.is_private_or_test else "DATA_UNAVAILABLE",
        "price": None, "volume": None, "ema200": None, "rsi14": None, "technical_score": None
    }
    raw_market_df = None
    mkt_data = await market_provider.fetch_market_data(ticker)
    raw_market_df = mkt_data.raw_df
    if mkt_data.status == "AVAILABLE" and raw_market_df is not None:
        indicators = calculate_technical_indicators(
            raw_market_df,
            market_session=mkt_data.market_session,
            as_of=mkt_data.timestamp or utc_now()
        )
        indicators["price"] = mkt_data.price
        indicators["volume"] = mkt_data.volume
        indicators["status"] = "AVAILABLE"
        if len(raw_market_df) >= 2 and mkt_data.price is not None:
            prev_close = float(raw_market_df['Close'].iloc[-2])
            if prev_close > 0:
                indicators["price_change_1d"] = round(((mkt_data.price - prev_close) / prev_close) * 100.0, 2)
        tech_score_raw = calculate_technical_score(indicators)
        indicators["technical_score"] = tech_score_raw
    else:
        indicators["status"] = mkt_data.status
        indicators["price"] = mkt_data.price
        indicators["volume"] = mkt_data.volume

    mkt_snap_data = {
        "ticker": ticker,
        "observed_at": mkt_data.observed_at,
        "candle_date": mkt_data.candle_date,
        "market_session": mkt_data.market_session,
        **indicators,
    }
    save_market_snapshot(db, mkt_snap_data)
    return indicators, raw_market_df


# Centralized Mutex Lock preventing concurrent pipeline execution races
PIPELINE_LOCK = asyncio.Lock()


async def _pipeline_heartbeat_worker(job_id: int, stop_event: asyncio.Event, interval: float = 30.0):
    """
    Background worker that periodically refreshes the job heartbeat in the database
    every `interval` seconds (default 30s) while the pipeline is executing.
    Prevents false timeout expiration during long ticker computations (FinBERT, rate limits, network timeouts).
    """
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass

        try:
            def _touch():
                with SessionLocal() as db_hb:
                    update_job_heartbeat(db_hb, job_id)
            await asyncio.to_thread(_touch)
        except Exception as hb_err:
            logger.debug(f"Heartbeat worker tick failed for job {job_id}: {hb_err}")


async def _run_full_pipeline_internal(existing_job_id: Optional[int] = None) -> Dict[str, Any]:
    """Core pipeline execution logic."""
    db = SessionLocal()
    if existing_job_id is not None:
        job_id = existing_job_id
    else:
        job_run = create_job_run(db, "smie_full_pipeline")
        job_id = job_run.id

    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(_pipeline_heartbeat_worker(job_id, stop_heartbeat, interval=30.0))

    records_processed = 0
    results = {}
    collected_alerts = []
    has_persist_error = False

    try:
        ensure_tickers_seeded(db)
        x_provider = get_x_provider()
        news_provider = get_news_provider()
        market_provider = YFinanceMarketProvider()
        poly_provider = get_polymarket_provider()
        sentiment_classifier = get_sentiment_classifier()

        # Step 0: Ingest Polymarket Prediction Markets globally for the sector (if enabled)
        poly_markets = []
        poly_success = False
        if getattr(settings, "POLYMARKET_ENABLED", True):
            try:
                poly_markets = await ingest_prediction_markets(db, poly_provider=poly_provider)
                records_processed += len(poly_markets)
                poly_success = True
            except Exception as e:
                logger.error(f"Polymarket collection error (isolated): {e}")
                poly_success = False
        else:
            logger.info("Polymarket collection is disabled (POLYMARKET_ENABLED=False).")
            poly_success = True
            
        update_job_heartbeat(db, job_id)

        # Process each configured ticker
        for ticker_config in INITIAL_TICKERS:
            ticker = ticker_config.symbol
            logger.info(f"Processing SMIE analysis for {ticker}...")

            # --- STEP 1: SOCIAL COLLECTION (X / TWITTER) ---
            social_success = False
            posts_data = []
            catalysts_found = []
            try:
                saved_count, posts_data, soc_cats = await ingest_social_posts_for_ticker(
                    db, ticker_config, x_provider=x_provider, sentiment_classifier=sentiment_classifier
                )
                catalysts_found.extend(soc_cats)
                records_processed += len(posts_data)
                social_success = True
            except Exception as e:
                logger.error(f"Social collection error for {ticker} (isolated): {e}")

            # --- STEP 2: PREDICTION MARKET SCORE (PMS) ---
            pms_score = None
            pms_confidence = 0.0
            pms_quality = 50.0
            pms_breakdown = {}
            prediction_count = 0
            direct_markets = []
            sector_events = []
            if getattr(settings, "POLYMARKET_ENABLED", True):
                try:
                    # Filter directly from in-memory poly_markets (single network fetch for the entire sector)
                    direct_markets = [m for m in poly_markets if m.ticker and m.ticker.upper() == ticker.upper()]
                    sector_events = [m for m in poly_markets if m.event_key is not None and (not m.ticker or m.ticker.upper() != ticker.upper())]
                    
                    pms_score, pms_confidence, pms_quality, pms_breakdown = calculate_prediction_market_score(
                        ticker=ticker,
                        direct_markets=direct_markets,
                        sector_events=sector_events
                    )
                    prediction_count = pms_breakdown.get("market_count", len(pms_breakdown.get("markets", [])))
                except Exception as e:
                    logger.error(f"Prediction market scoring error for {ticker} (isolated): {e}")
            else:
                pms_breakdown = {"status": "DISABLED", "reason": "POLYMARKET_ENABLED=False"}

            # --- STEP 3: NEWS COLLECTION & CATALYSTS ---
            news_success = False
            try:
                saved_count, processed_news, news_cats = await ingest_news_for_ticker(
                    db, ticker_config, news_provider=news_provider, sentiment_classifier=sentiment_classifier
                )
                catalysts_found.extend(news_cats)
                records_processed += len(processed_news)
                news_success = True
            except Exception as e:
                logger.error(f"News collection error for {ticker} (isolated): {e}")

            # --- STEP 4: MARKET DATA & TECHNICAL SCORING ---
            indicators = {
                "status": "AVAILABLE" if not ticker_config.is_private_or_test else "DATA_UNAVAILABLE",
                "price": None, "volume": None, "ema200": None, "rsi14": None, "technical_score": None
            }
            raw_market_df = None
            try:
                indicators, raw_market_df = await ingest_market_for_ticker(
                    db, ticker_config, market_provider=market_provider
                )
                records_processed += 1
            except Exception as e:
                logger.error(f"Market data error for {ticker} (isolated): {e}")
                indicators["status"] = "ERROR"
                try:
                    err_snap_data = {
                        "ticker": ticker,
                        "observed_at": utc_now(),
                        "candle_date": None,
                        "market_session": "UNKNOWN",
                        "market_status": "ERROR",
                        "status": "ERROR",
                        "price": None,
                        "volume": None,
                        "technical_score": None
                    }
                    save_market_snapshot(db, err_snap_data)
                except Exception as snap_err:
                    logger.error(f"Failed to record error market snapshot for {ticker}: {snap_err}")

            # --- STEP 5: COMPUTE SCORES, SMI, CONFIDENCE & SIGNALS ---
            now_eval = utc_now()
            recent_posts = get_recent_social_posts(db, ticker, hours=settings.SOCIAL_LOOKBACK_HOURS)
            social_res = calculate_social_score(recent_posts, analysis_timestamp=now_eval)
            social_score = social_res["social_score"]

            recent_news = get_recent_news_items(db, ticker, days=3)
            news_res = calculate_news_score(recent_news, analysis_timestamp=now_eval)
            news_score = news_res.get("news_score") if isinstance(news_res, dict) else news_res

            momentum_score = calculate_momentum_score(indicators, raw_df=raw_market_df)
            risk_score = calculate_risk_score(indicators, raw_df=raw_market_df)
            tech_score_raw = indicators.get("technical_score")

            # Extract fundamental data (Cash runway, solvency, growth, margins)
            fundamental_score = None
            fund_raw = None
            fund_success = False
            try:
                if hasattr(market_provider, "get_fundamentals"):
                    fund_raw = await market_provider.get_fundamentals(ticker)
                    # Verify whether genuine financial statement metrics were retrieved
                    if fund_raw and any(v is not None for v in [fund_raw.get("total_cash"), fund_raw.get("free_cashflow"), fund_raw.get("total_debt")]):
                        fund_success = True
                        fundamental_score = calculate_fundamental_score(fund_raw)
                    elif ticker_config.is_private_or_test:
                        # Private or test tickers have no SEC filings; consider fundamental eval clean
                        fund_success = True
                    else:
                        fund_success = False
                else:
                    fund_success = True
            except Exception as e:
                logger.warning(f"Could not compute fundamentals for {ticker}: {e}")
                fund_success = False

            # Extract 1d price return from indicators or raw OHLCV DataFrame
            price_change_1d = indicators.get("price_change_1d")
            if price_change_1d is None and raw_market_df is not None and len(raw_market_df) >= 2 and 'Close' in raw_market_df.columns:
                close_series = raw_market_df['Close']
                prev_c = float(close_series.iloc[-2])
                curr_c = float(close_series.iloc[-1])
                if prev_c > 0:
                    price_change_1d = round(((curr_c - prev_c) / prev_c) * 100.0, 2)

            # Historical previous snapshots for genuine 1D, 3D, 5D momentum calculation
            snap_1d = get_historical_ssi_snapshot(db, ticker, target_hours_ago=24.0, tolerance_hours=6.0)
            snap_3d = get_historical_ssi_snapshot(db, ticker, target_hours_ago=72.0, tolerance_hours=18.0)
            snap_5d = get_historical_ssi_snapshot(db, ticker, target_hours_ago=120.0, tolerance_hours=24.0)

            def _build_snap_dict(snap):
                if not snap:
                    return None
                pillars = []
                scores = {}
                # Social: reconstruct effective score using prior sample size (R2-02 audit fix)
                if snap.social_score is not None:
                    p_cnt = getattr(snap, "post_count", None)
                    if p_cnt is None:
                        eff_s = snap.social_score
                        pillars.append("social")
                        scores["social"] = eff_s
                    elif p_cnt > 0:
                        eff_s = apply_bayesian_shrinkage(snap.social_score, p_cnt)
                        pillars.append("social")
                        scores["social"] = eff_s
                # Reconstruct technical momentum fallback when momentum_score is None (R2-02 audit consistency)
                snap_mom = snap.momentum_score
                if snap_mom is None and getattr(snap, "technical_score", None) is not None:
                    snap_mom = (snap.technical_score / 40.0) * 100.0

                for k, v in [
                    ("prediction", snap.prediction_score),
                    ("news", snap.news_score),
                    ("momentum", snap_mom),
                    ("fundamental", snap.fundamental_score),
                    ("risk", snap.risk_score if getattr(settings, "WEIGHT_RISK", 0.0) > 0 else None)
                ]:
                    if v is not None:
                        pillars.append(k)
                        scores[k] = v
                val = snap.smi if snap.smi is not None else (snap.ssi if snap.ssi is not None else None)
                return {
                    "smi": val,
                    "active_pillars": pillars,
                    "active_scores": scores
                }

            prev_1d_dict = _build_snap_dict(snap_1d)
            prev_3d_dict = _build_snap_dict(snap_3d)
            prev_5d_dict = _build_snap_dict(snap_5d)

            smi_dict = calculate_smi(
                social_score=social_score,
                prediction_score=pms_score,
                prediction_quality=pms_quality,
                news_score=news_score,
                momentum_score=momentum_score,
                technical_score_raw=tech_score_raw,
                fundamental_score=fundamental_score,
                risk_score=risk_score,
                previous_smi_1d=prev_1d_dict,
                previous_smi_3d=prev_3d_dict,
                previous_smi_5d=prev_5d_dict,
                post_count=social_res.get("effective_sample_size", len(recent_posts)),
                news_count=len(recent_news),
                prediction_count=prediction_count
            )

            # Signal & Explanation generation
            signal_res = generate_signal_and_explanation(
                ticker=ticker,
                smi=smi_dict["smi"],
                social_score=social_score,
                technical_score_raw=tech_score_raw,
                indicators=indicators,
                social_stats=social_res,
                catalysts_found=catalysts_found,
                smi_mom_1d=smi_dict["smi_momentum_1d"],
                price_change_1d=price_change_1d,
                prediction_score=pms_score,
                prediction_delta_24h=pms_breakdown.get("pms_delta_24h"),
                prediction_data=pms_breakdown,
                news_score=news_score,
                source_agreement=smi_dict.get("source_agreement"),
                data_quality=smi_dict.get("data_quality"),
                fundamentals=fund_raw,
                fundamental_score=fundamental_score,
                risk_score=risk_score,
                momentum_score=momentum_score,
                is_mom_comparable_1d=smi_dict.get("is_mom_comparable_1d", True)
            )

            # --- STEP 6: DETERMINE DATA PROVENANCE & SAVE STATEFUL DATA ---
            # 1. Social Provenance from actual posts in window
            if not social_success:
                soc_src = "ERROR"
            elif len(recent_posts) == 0:
                soc_src = "EXCLUDED"
            else:
                is_mock_p = lambda p: getattr(p, "source", "") == "MOCK" or str(p.tweet_id).startswith("mock_")
                mock_p_count = sum(1 for p in recent_posts if is_mock_p(p))
                if mock_p_count == len(recent_posts) or settings.X_PROVIDER.lower() == "mock":
                    soc_src = "MOCK"
                elif mock_p_count > 0:
                    soc_src = "DEGRADED"
                else:
                    soc_src = "LIVE"

            # 2. Prediction Market Provenance from actual markets in window
            if not getattr(settings, "POLYMARKET_ENABLED", True):
                pred_src = "EXCLUDED"
            elif not poly_success:
                pred_src = "ERROR"
            elif prediction_count == 0 or pms_score is None:
                pred_src = "EXCLUDED"
            else:
                relevant_markets = direct_markets + sector_events
                is_mock_m = lambda m: getattr(m, "source", "") == "MOCK" or str(getattr(m, "external_id", "")).startswith("mock_")
                mock_m_count = sum(1 for m in relevant_markets if is_mock_m(m))
                if mock_m_count == len(relevant_markets) or settings.POLYMARKET_PROVIDER.lower() == "mock":
                    pred_src = "MOCK"
                elif mock_m_count > 0:
                    pred_src = "DEGRADED"
                else:
                    pred_src = "LIVE"

            # 3. News Provenance from actual news in window
            if not news_success:
                news_src = "ERROR"
            elif len(recent_news) == 0:
                news_src = "EXCLUDED"
            else:
                is_mock_n = lambda n: getattr(n, "source", "") in ["Mock News", "MOCK"] or str(getattr(n, "url", "")).startswith("mock_")
                mock_n_count = sum(1 for n in recent_news if is_mock_n(n))
                if mock_n_count == len(recent_news) or settings.NEWS_PROVIDER.lower() == "mock":
                    news_src = "MOCK"
                elif mock_n_count > 0:
                    news_src = "DEGRADED"
                else:
                    news_src = "LIVE"

            # 4. Market Data Provenance
            if indicators["status"] == "DATA_UNAVAILABLE":
                mkt_src = "EXCLUDED"
            elif indicators["status"] in ["DEGRADED", "STALE"]:
                mkt_src = "DEGRADED"
            elif indicators["status"] == "AVAILABLE":
                mkt_src = "LIVE"
            else:
                mkt_src = "DEGRADED"

            # 5. Overall Pipeline Snapshot Provenance
            if soc_src == "MOCK" or pred_src == "MOCK" or news_src == "MOCK":
                overall_data_src = "MOCK"
            elif soc_src in ["EXCLUDED", "DEGRADED"] or pred_src in ["EXCLUDED", "DEGRADED"] or news_src in ["EXCLUDED", "DEGRADED"] or mkt_src in ["EXCLUDED", "DEGRADED"]:
                overall_data_src = "DEGRADED"
            else:
                overall_data_src = "LIVE"

            runway_info = get_fundamental_runway_info(fund_raw)
            eff_runway = runway_info.get("runway_months")

            snapshot_data = {
                "ticker": ticker,
                "social_score": social_score,
                "prediction_score": pms_score,
                "news_score": news_score,
                "momentum_score": momentum_score,
                "fundamental_score": fundamental_score,
                "risk_score": risk_score,
                "technical_score": tech_score_raw,
                "ssi": social_score,  # Pure Social
                "smi": smi_dict["smi"],  # Integrated Space Market Intelligence Index
                "ssi_momentum_1d": smi_dict["smi_momentum_1d"],
                "ssi_momentum_3d": smi_dict["smi_momentum_3d"],
                "ssi_momentum_5d": smi_dict["smi_momentum_5d"],
                "signal": signal_res["signal"],
                "base_signal": signal_res.get("base_signal"),
                "signal_modifier": signal_res.get("signal_modifier"),
                "confidence": smi_dict["confidence"],
                "data_completeness": smi_dict["data_quality"],
                "data_quality": smi_dict["data_quality"],
                "prediction_quality": pms_quality,
                "post_count": social_res.get("effective_sample_size", len(recent_posts)),
                "raw_post_count": social_res.get("raw_post_count", len(recent_posts)),
                "relevant_post_count": social_res.get("relevant_post_count", len(recent_posts)),
                "unique_post_count": social_res.get("unique_post_count", len(recent_posts)),
                "author_count": social_res.get("author_count", 0),
                "news_count": len(recent_news),
                "prediction_count": prediction_count,
                "data_source": overall_data_src,
                "social_source": soc_src,
                "prediction_source": pred_src,
                "news_source": news_src,
                "market_source": mkt_src,
                "price": indicators.get("price"),
                "volume": indicators.get("volume"),
                "rsi14": indicators.get("rsi14"),
                "market_status": indicators.get("status", "AVAILABLE"),
                "runway_months": eff_runway,
                "fundamentals": fund_raw,
                "effective_weights": smi_dict.get("effective_weights"),
                "rules_version": getattr(settings, "RULES_VERSION", "2.0.0"),
                "explanation": signal_res["explanation"]
            }

            # Determine health of divergence sources (tripartite: X / Polymarket / Price)
            mkt_success = indicators.get("status") in ["AVAILABLE", "DEGRADED"]
            poly_active = getattr(settings, "POLYMARKET_ENABLED", True)
            div_sources_success = social_success and mkt_success and (poly_success if poly_active else True)

            # Atomic Unit of Work (R2-04 & R2-05 audit fix): Persist divergences, alerts & snapshot together
            try:
                save_divergences(
                    db,
                    ticker,
                    signal_res.get("active_divergences", []),
                    resolve_missing=div_sources_success,
                    commit=False
                )

                alerts_to_save = signal_res.get("alerts", [])
                for al in alerts_to_save:
                    al["data_source"] = overall_data_src

                # Condition alert category resolution strictly on source collection health to eliminate alert flapping
                resolve_categories = set()
                if mkt_success:
                    resolve_categories.add("SIGNAL")
                if news_success and social_success:
                    resolve_categories.add("CATALYST")
                if fund_success:
                    resolve_categories.add("FUNDAMENTAL")
                if div_sources_success:
                    resolve_categories.add("DIVERGENCE")

                save_alerts(
                    db,
                    ticker,
                    alerts_to_save,
                    resolve_missing=True,
                    resolve_categories=resolve_categories,
                    commit=False
                )

                save_ssi_snapshot(db, snapshot_data, commit=False)
                db.commit()
                records_processed += 1
            except Exception as persist_err:
                db.rollback()
                has_persist_error = True
                logger.error(f"Error persisting snapshot and alerts for {ticker}: {persist_err}")

            if signal_res.get("alerts"):
                collected_alerts.extend(signal_res["alerts"])

            results[ticker] = {
                "smi": smi_dict["smi"],
                "ssi": social_score,
                "pms": pms_score,
                "signal": signal_res["signal"],
                "confidence": smi_dict["confidence"],
                "data_quality": smi_dict["data_quality"],
                "divergence": signal_res["divergence"],
                "post_count": len(recent_posts),
                "news_count": len(recent_news),
                "prediction_count": prediction_count
            }
            update_job_heartbeat(db, job_id)

        pipeline_status = "PARTIAL" if has_persist_error else "SUCCESS"
        finish_job_run(db, job_id, status=pipeline_status, records=records_processed)
        logger.info(f"SMIE pipeline completed with status {pipeline_status}.")
        return {
            "status": pipeline_status,
            "records_processed": records_processed,
            "results": results,
            "alerts": collected_alerts
        }

    except Exception as e:
        logger.exception(f"Fatal error in SMIE pipeline: {e}")
        finish_job_run(db, job_id, status="ERROR", error=str(e))
        return {"status": "ERROR", "error": str(e)}
    finally:
        stop_heartbeat.set()
        try:
            await heartbeat_task
        except Exception:
            pass
        db.close()


async def run_full_pipeline(
    existing_job_id: Optional[int] = None,
    source: str = "CLI",
    lock_already_acquired: bool = False
) -> Dict[str, Any]:
    """
    Executes the complete SMIE v2.0 Modular Pipeline.
    Protected by PIPELINE_LOCK (in-memory process lock) and acquire_pipeline_job_lock (atomic distributed DB lock)
    across all entrypoints (API, Scheduler, CLI).
    If lock_already_acquired is True (e.g. from API endpoint), proceeds directly to execution.
    """
    if lock_already_acquired:
        return await _run_full_pipeline_internal(existing_job_id=existing_job_id)

    if PIPELINE_LOCK.locked():
        logger.warning(f"Pipeline execution rejected: process lock held. Source: {source}")
        return {"status": "CONFLICT", "error": "A pipeline execution is already in progress in this process."}

    async with PIPELINE_LOCK:
        job_id = existing_job_id
        if job_id is None:
            init_db()
            db = SessionLocal()
            try:
                job_run, conflict_err = acquire_pipeline_job_lock(db, source=source)
                if not job_run:
                    logger.warning(f"Pipeline execution rejected by database lock: {conflict_err}")
                    return {"status": "CONFLICT", "error": conflict_err}
                job_id = job_run.id
            finally:
                db.close()

        return await _run_full_pipeline_internal(existing_job_id=job_id)
