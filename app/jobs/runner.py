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
    save_divergences, save_market_snapshot, get_latest_market_snapshot,
    save_ssi_snapshot, get_latest_ssi_snapshot, get_historical_ssi_snapshot,
    create_job_run, finish_job_run
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
from app.scoring.social import calculate_social_score
from app.scoring.prediction import calculate_prediction_market_score
from app.scoring.momentum import calculate_momentum_score
from app.scoring.risk import calculate_risk_score
from app.scoring.smi import calculate_smi
from app.scoring.signal import generate_signal_and_explanation
from app.divergence.detector import detect_divergences

logger = logging.getLogger("SMIE.Runner")


def get_x_provider():
    if settings.X_PROVIDER.lower() == "twikit":
        try:
            return TwikitProvider()
        except Exception:
            return MockXProvider()
    return MockXProvider()


def get_news_provider():
    return GoogleRSSNewsProvider()


def get_polymarket_provider():
    if settings.POLYMARKET_PROVIDER.lower() == "polymarket":
        return PolymarketGammaProvider()
    return MockPolymarketProvider()


async def run_full_pipeline() -> Dict[str, Any]:
    """
    Executes the complete SMIE v2.0 Modular Pipeline:
    1. Collect Social Posts & analyze sentiment/catalysts (XProvider)
    2. Collect Prediction Markets & calculate PMS (PolymarketProvider)
    3. Collect News & analyze catalysts (NewsProvider)
    4. Collect Market Data & compute technical indicators (MarketProvider)
    5. Calculate Multivariable SMI, Confidence, Signals & Tripartite Divergences
    6. Save immutable snapshots and divergences to SQLite
    
    Includes strict Job Failure Isolation: failure in one provider does NOT halt the others.
    """
    init_db()
    db = SessionLocal()
    job_run = create_job_run(db, "smie_full_pipeline")
    
    records_processed = 0
    results = {}
    collected_alerts = []

    try:
        ensure_tickers_seeded(db)
        x_provider = get_x_provider()
        news_provider = get_news_provider()
        market_provider = YFinanceMarketProvider()
        poly_provider = get_polymarket_provider()
        sentiment_classifier = get_sentiment_classifier()

        # Step 0: Ingest Polymarket Prediction Markets globally for the sector
        poly_markets = []
        try:
            logger.info("Ingesting Polymarket prediction markets...")
            poly_markets = await poly_provider.get_markets()
            if poly_markets:
                save_prediction_markets(db, poly_markets)
                records_processed += len(poly_markets)
        except Exception as e:
            logger.error(f"Polymarket collection error (isolated): {e}")

        # Process each configured ticker
        for ticker_config in INITIAL_TICKERS:
            ticker = ticker_config.symbol
            logger.info(f"Processing SMIE analysis for {ticker}...")

            # --- STEP 1: SOCIAL COLLECTION (X / TWITTER) ---
            posts_data = []
            catalysts_found = []
            try:
                query = f"${ticker} OR \"{ticker_config.name}\""
                posts_data = await x_provider.search(
                    query=query, ticker=ticker, max_results=settings.SOCIAL_MAX_POSTS_PER_TICKER
                )
                
                texts = [p.text for p in posts_data]
                sentiments = sentiment_classifier.analyze_batch(texts) if texts else []
                processed_posts = []

                for i, p in enumerate(posts_data):
                    sent_res = sentiments[i] if i < len(sentiments) else sentiment_classifier.analyze(p.text)
                    rel_score = calculate_relevance_score(p.text, ticker, ticker_config.aliases)
                    rec_weight = calculate_recency_weight(p.created_at)
                    eng_score = calculate_engagement_score(p.likes, p.reposts, p.replies, p.views)
                    
                    post_cats = detect_catalysts(p.text)
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
                        "catalyst_importance": cat_imp
                    })

                if processed_posts:
                    save_social_posts(db, processed_posts)
                    records_processed += len(processed_posts)
            except Exception as e:
                logger.error(f"Social collection error for {ticker} (isolated): {e}")

            # --- STEP 2: PREDICTION MARKET SCORE (PMS) ---
            pms_score = None
            pms_confidence = 0.0
            pms_quality = 50.0
            pms_breakdown = {}
            try:
                # Filter directly from in-memory poly_markets (single network fetch for the entire sector)
                direct_markets = [m for m in poly_markets if m.ticker and m.ticker.upper() == ticker.upper()]
                sector_events = [m for m in poly_markets if m.event_key is not None and (not m.ticker or m.ticker.upper() != ticker.upper())]
                
                pms_score, pms_confidence, pms_quality, pms_breakdown = calculate_prediction_market_score(
                    ticker=ticker,
                    direct_markets=direct_markets,
                    sector_events=sector_events
                )
            except Exception as e:
                logger.error(f"Prediction market scoring error for {ticker} (isolated): {e}")

            # --- STEP 3: NEWS COLLECTION & CATALYSTS ---
            try:
                news_items = await news_provider.fetch_news(query=f"{ticker} {ticker_config.name}", ticker=ticker, max_results=20)
                processed_news = []
                for n in news_items:
                    text_content = f"{n.title}. {n.summary}"
                    sent_res = sentiment_classifier.analyze(text_content)
                    rel_score = calculate_relevance_score(text_content, ticker, ticker_config.aliases)
                    news_cats = detect_catalysts(text_content)
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

                if processed_news:
                    save_news_items(db, processed_news)
                    records_processed += len(processed_news)
            except Exception as e:
                logger.error(f"News collection error for {ticker} (isolated): {e}")

            # --- STEP 4: MARKET DATA & TECHNICAL SCORING ---
            indicators = {
                "status": "AVAILABLE" if not ticker_config.is_private_or_test else "DATA_UNAVAILABLE",
                "price": None, "volume": None, "ema200": None, "rsi14": None, "technical_score": None
            }
            tech_score_raw = None
            raw_market_df = None
            try:
                mkt_data = await market_provider.get_market_data(ticker=ticker)
                if mkt_data.status == "AVAILABLE" and mkt_data.raw_df is not None:
                    raw_market_df = mkt_data.raw_df
                    indicators = calculate_technical_indicators(raw_market_df)
                    indicators["price"] = mkt_data.price
                    indicators["volume"] = mkt_data.volume
                    indicators["status"] = "AVAILABLE"
                    
                    tech_score = calculate_technical_score(indicators)
                    indicators["technical_score"] = tech_score
                    tech_score_raw = tech_score
                else:
                    indicators["status"] = mkt_data.status

                mkt_snap_data = {"ticker": ticker, **indicators}
                save_market_snapshot(db, mkt_snap_data)
                records_processed += 1
            except Exception as e:
                logger.error(f"Market data error for {ticker} (isolated): {e}")
                indicators["status"] = "ERROR"

            # --- STEP 5: COMPUTE SCORES, SMI, CONFIDENCE & SIGNALS ---
            recent_posts = get_recent_social_posts(db, ticker, hours=settings.SOCIAL_LOOKBACK_HOURS)
            social_res = calculate_social_score(recent_posts)
            social_score = social_res["social_score"]

            recent_news = get_recent_news_items(db, ticker, days=3)
            news_res = calculate_news_score(recent_news)
            news_score = news_res.get("news_score") if isinstance(news_res, dict) else news_res

            momentum_score = calculate_momentum_score(indicators, raw_df=raw_market_df)
            risk_score = calculate_risk_score(indicators, raw_df=raw_market_df)

            # Extract 1d price return from raw OHLCV DataFrame
            price_change_1d = None
            if raw_market_df is not None and len(raw_market_df) >= 2 and 'Close' in raw_market_df.columns:
                close_series = raw_market_df['Close']
                prev_c = float(close_series.iloc[-2])
                curr_c = float(close_series.iloc[-1])
                if prev_c > 0:
                    price_change_1d = round(((curr_c - prev_c) / prev_c) * 100.0, 2)

            # Historical previous snapshots for genuine 1D, 3D, 5D momentum calculation
            snap_1d = get_historical_ssi_snapshot(db, ticker, target_hours_ago=24.0, tolerance_hours=6.0)
            snap_3d = get_historical_ssi_snapshot(db, ticker, target_hours_ago=72.0, tolerance_hours=18.0)
            snap_5d = get_historical_ssi_snapshot(db, ticker, target_hours_ago=120.0, tolerance_hours=24.0)

            prev_smi_1d = snap_1d.smi if snap_1d and snap_1d.smi is not None else (snap_1d.ssi if snap_1d else None)
            prev_smi_3d = snap_3d.smi if snap_3d and snap_3d.smi is not None else (snap_3d.ssi if snap_3d else None)
            prev_smi_5d = snap_5d.smi if snap_5d and snap_5d.smi is not None else (snap_5d.ssi if snap_5d else None)

            smi_dict = calculate_smi(
                social_score=social_score,
                prediction_score=pms_score,
                prediction_quality=pms_quality,
                news_score=news_score,
                momentum_score=momentum_score,
                technical_score_raw=tech_score_raw,
                fundamental_score=None,  # Modular for fundamental data integration
                risk_score=risk_score,
                previous_smi_1d=prev_smi_1d,
                previous_smi_3d=prev_smi_3d,
                previous_smi_5d=prev_smi_5d,
                post_count=len(recent_posts),
                news_count=len(recent_news)
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
                news_score=news_score
            )

            # Save detected divergences to database
            if signal_res.get("active_divergences"):
                save_divergences(db, ticker, signal_res["active_divergences"])

            # --- STEP 6: SAVE IMMUTABLE SMI SNAPSHOT ---
            snapshot_data = {
                "ticker": ticker,
                "social_score": social_score,
                "prediction_score": pms_score,
                "news_score": news_score,
                "momentum_score": momentum_score,
                "fundamental_score": None,
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
                "price": indicators.get("price"),
                "volume": indicators.get("volume"),
                "explanation": signal_res["explanation"]
            }

            save_ssi_snapshot(db, snapshot_data)
            records_processed += 1

            if signal_res.get("alerts"):
                collected_alerts.extend(signal_res["alerts"])

            results[ticker] = {
                "smi": smi_dict["smi"],
                "ssi": social_score,
                "pms": pms_score,
                "signal": signal_res["signal"],
                "confidence": smi_dict["confidence"],
                "data_quality": smi_dict["data_quality"],
                "divergence": signal_res["divergence"]
            }

        finish_job_run(db, job_run.id, status="SUCCESS", records=records_processed)
        logger.info("SMIE pipeline completed successfully.")
        return {
            "status": "SUCCESS",
            "records_processed": records_processed,
            "results": results,
            "alerts": collected_alerts
        }

    except Exception as e:
        logger.exception(f"Fatal error in SMIE pipeline: {e}")
        finish_job_run(db, job_run.id, status="ERROR", error=str(e))
        return {"status": "ERROR", "error": str(e)}
    finally:
        db.close()
