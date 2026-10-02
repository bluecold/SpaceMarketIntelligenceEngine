from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.database.repository import (
    get_latest_ssi_snapshot, get_latest_market_snapshot,
    get_recent_social_posts, get_recent_news_items,
    get_recent_prediction_markets, get_active_divergences,
    utc_now
)
from app.scoring.social import calculate_social_score
from app.scoring.smi import describe_engine
from app.config import INITIAL_TICKERS, DEFAULT_EVENT_COMPANY_MAPPINGS, settings

router = APIRouter(tags=["Tickers"])


@router.get("/api/tickers/{ticker}")
def get_ticker_detail(ticker: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    ticker_sym = ticker.upper()
    ticker_cfg = next((t for t in INITIAL_TICKERS if t.symbol == ticker_sym), None)

    if not ticker_cfg:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not found in configuration.")

    ssi_snap = get_latest_ssi_snapshot(db, ticker_sym)
    mkt_snap = get_latest_market_snapshot(db, ticker_sym)
    posts = get_recent_social_posts(db, ticker_sym, hours=settings.SOCIAL_LOOKBACK_HOURS)
    news_items = get_recent_news_items(db, ticker_sym, days=3)
    markets = get_recent_prediction_markets(db, ticker_sym)
    divergences = get_active_divergences(db, ticker_sym, hours=48)
    # Same pass as the SSI: every post is tagged counted/excluded with its weight, so the feed matches the score
    post_details: Dict[int, Dict[str, Any]] = {}
    social_stats = calculate_social_score(posts, post_details=post_details)

    # Post serialization
    posts_payload = []
    catalysts_payload = []
    excluded_counts: Dict[str, int] = {}

    for p in posts:
        info = post_details.get(id(p), {"status": "excluded", "reason": "low_relevance", "weight": 0.0, "vote_share": 0.0})
        if info["status"] == "excluded":
            excluded_counts[info["reason"]] = excluded_counts.get(info["reason"], 0) + 1

        # Catalysts only from posts that can raise them in the pipeline (relevant, English, not promo spam)
        if (p.catalyst and info["reason"] not in ("language", "spam") and (p.relevance_score or 0) >= 0.30
                and p.catalyst not in [c["category"] for c in catalysts_payload]):
            catalysts_payload.append({
                "category": p.catalyst,
                "direction": p.catalyst_direction,
                "importance": p.catalyst_importance or "MEDIUM"
            })

        posts_payload.append({
            "status": info["status"],
            "excluded_reason": info["reason"],
            "ssi_weight": info["weight"],
            "vote_share": info["vote_share"],
            "id": p.tweet_id,
            "username": p.username,
            "text": p.text,
            "url": p.url,
            "created_at": p.created_at.isoformat() + "Z" if p.created_at else "",
            "sentiment_score": p.sentiment_score,
            "sentiment_label": p.sentiment_label,
            "confidence": p.sentiment_confidence,
            "likes": p.likes,
            "reposts": p.reposts,
            "replies": p.replies,
            "views": p.views,
            "relevance": p.relevance_score,
            "catalyst": p.catalyst,
            "catalyst_importance": p.catalyst_importance
        })

    def _feed_rank(post: Dict[str, Any]):
        if post["status"] != "counted":
            return (2, 0.0)
        is_opinion = post["sentiment_label"] in ("BULLISH", "BEARISH")
        return (0 if is_opinion else 1, -post["ssi_weight"])

    posts_payload.sort(key=_feed_rank)
    social_stats["counted_post_count"] = sum(1 for x in posts_payload if x["status"] == "counted")
    social_stats["excluded_post_counts"] = excluded_counts

    # News serialization
    news_payload = []
    for n in news_items:
        if n.catalyst and n.catalyst not in [c["category"] for c in catalysts_payload]:
            catalysts_payload.append({
                "category": n.catalyst,
                "direction": n.catalyst_direction,
                "importance": n.catalyst_importance or "MEDIUM"
            })
            
        news_payload.append({
            "id": n.id,
            "title": n.title,
            "source": n.source,
            "url": n.url,
            "published_at": n.published_at.isoformat() + "Z" if n.published_at else "",
            "sentiment_score": n.sentiment_score,
            "sentiment_label": n.sentiment_label,
            "relevance": n.relevance_score,
            "catalyst": n.catalyst,
            "catalyst_importance": n.catalyst_importance
        })

    # Prediction Markets serialization (Direct vs Sector Event classification)
    markets_payload = []
    for m in markets:
        is_direct = bool(m.ticker and m.ticker.upper() == ticker_sym)
        impact_w = 1.0 if is_direct else (DEFAULT_EVENT_COMPANY_MAPPINGS.get(m.event_key, {}).get(ticker_sym) if m.event_key else None)
        event_role = "DIRECT" if is_direct else "SECTOR_CATALYST"
        
        markets_payload.append({
            "id": m.external_id,
            "title": m.title,
            "description": m.description,
            "category": m.category,
            "yes_probability": round(m.yes_probability * 100.0, 1),
            "no_probability": round(m.no_probability * 100.0, 1),
            "volume": m.volume,
            "liquidity": m.liquidity,
            "spread": m.spread,
            "quality_score": m.quality_score,
            "url": m.url,
            "ticker": m.ticker,
            "is_direct": is_direct,
            "event_role": event_role,
            "impact_weight": impact_w,
            "event_key": m.event_key
        })

    # Divergences serialization
    divs_payload = [
        {
            "id": d.id,
            "type": d.type,
            "direction": d.direction,
            "strength": d.strength,
            "confidence": d.confidence,
            "description": d.description,
            "timestamp": d.timestamp.isoformat() + "Z" if d.timestamp else ""
        }
        for d in divergences
    ]

    # Technical breakdown
    mod_sig = ssi_snap.signal_modifier if ssi_snap else None
    tech_payload = {
        "price": mkt_snap.price if mkt_snap else None,
        "market_status": "DATA_UNAVAILABLE" if (mod_sig and "NO MKT DATA" in mod_sig) else (
            getattr(ssi_snap, "market_status", None) or (mkt_snap.market_status if mkt_snap else "DATA_UNAVAILABLE")
        ),
        "ema200": mkt_snap.ema200 if mkt_snap else None,
        "rsi14": mkt_snap.rsi14 if mkt_snap else None,
        "bollinger_upper": mkt_snap.bollinger_upper if mkt_snap else None,
        "bollinger_middle": mkt_snap.bollinger_middle if mkt_snap else None,
        "bollinger_lower": mkt_snap.bollinger_lower if mkt_snap else None,
        "macd_line": mkt_snap.macd_line if mkt_snap else None,
        "macd_signal": mkt_snap.macd_signal if mkt_snap else None,
        "macd_histogram": mkt_snap.macd_histogram if mkt_snap else None,
        "volume_ma20": mkt_snap.volume_ma20 if mkt_snap else None,
        "volume_ratio": mkt_snap.volume_ratio if mkt_snap else None,
        "atr": mkt_snap.atr if mkt_snap else None,
        "technical_score": mkt_snap.technical_score if mkt_snap else None,
        "observed_at": mkt_snap.observed_at.isoformat() + "Z" if (mkt_snap and mkt_snap.observed_at) else None,
        "candle_date": mkt_snap.candle_date if mkt_snap else None,
        "market_session": mkt_snap.market_session if mkt_snap else None,
        "collected_at": mkt_snap.timestamp.isoformat() + "Z" if (mkt_snap and mkt_snap.timestamp) else None,
    }

    reasons = [line for line in (ssi_snap.explanation.split("\n") if ssi_snap and ssi_snap.explanation else [])]
    smi_val = ssi_snap.smi if (ssi_snap and ssi_snap.smi is not None) else (ssi_snap.ssi if ssi_snap else None)

    # Stale calculation for ticker header
    age_hours = None
    is_stale = False
    if ssi_snap and ssi_snap.timestamp:
        now_dt = utc_now()
        snap_dt = ssi_snap.timestamp
        if snap_dt.tzinfo is not None:
            snap_dt = snap_dt.replace(tzinfo=None)
        age_hours = round(max(0.0, (now_dt - snap_dt).total_seconds() / 3600.0), 1)
        is_stale = age_hours >= 6.0

    sig_str = ssi_snap.signal if ssi_snap and ssi_snap.signal else "N/A"
    base_sig = (ssi_snap.base_signal if ssi_snap else None) or sig_str
    mod_sig = ssi_snap.signal_modifier if ssi_snap else None

    return {
        "ticker": ticker_sym,
        "name": ticker_cfg.name,
        "header": {
            "smi": smi_val,
            "ssi": ssi_snap.social_score if ssi_snap else None,
            "pms": ssi_snap.prediction_score if ssi_snap else None,
            "signal": sig_str,
            "base_signal": base_sig,
            "signal_modifier": mod_sig,
            "confidence": ssi_snap.confidence if ssi_snap else 0.0,
            "data_quality": ssi_snap.data_quality if ssi_snap and ssi_snap.data_quality is not None else (ssi_snap.data_completeness if ssi_snap else 0.0),
            "data_completeness": ssi_snap.data_completeness if ssi_snap else 0.0,
            "smi_momentum_1d": ssi_snap.ssi_momentum_1d if ssi_snap else None,
            "price": ssi_snap.price if ssi_snap else None,
            "data_source": getattr(ssi_snap, "data_source", "LIVE") if ssi_snap else "LIVE",
            "social_source": getattr(ssi_snap, "social_source", "LIVE") if ssi_snap else "LIVE",
            "prediction_source": "EXCLUDED" if (ssi_snap and ssi_snap.prediction_score is None) else (getattr(ssi_snap, "prediction_source", "LIVE") if ssi_snap else "LIVE"),
            "news_source": getattr(ssi_snap, "news_source", "LIVE") if ssi_snap else "LIVE",
            "market_source": getattr(ssi_snap, "market_source", "LIVE") if ssi_snap else "LIVE",
            "timestamp": ssi_snap.timestamp.isoformat() + "Z" if ssi_snap and ssi_snap.timestamp else None,
            "data_age_hours": age_hours,
            "is_stale": is_stale
        },
        "score_breakdown": {
            "social_score": ssi_snap.social_score if ssi_snap else None,
            "prediction_score": ssi_snap.prediction_score if ssi_snap else None,
            "news_score": ssi_snap.news_score if ssi_snap else None,
            "momentum_score": ssi_snap.momentum_score if ssi_snap else None,
            "fundamental_score": ssi_snap.fundamental_score if ssi_snap else None,
            "risk_score": ssi_snap.risk_score if ssi_snap else None,
            "technical_score": ssi_snap.technical_score if ssi_snap else None,
            "scaled_technical": round((ssi_snap.technical_score / 40.0) * 100.0, 1) if ssi_snap and ssi_snap.technical_score is not None else None
        },
        "sample_counts": {
            "post_count": ssi_snap.post_count if ssi_snap and ssi_snap.post_count is not None else 0,
            "news_count": ssi_snap.news_count if ssi_snap and ssi_snap.news_count is not None else 0,
            "prediction_count": 0 if (ssi_snap and ssi_snap.prediction_score is None) else (ssi_snap.prediction_count if ssi_snap and ssi_snap.prediction_count is not None else 0)
        },
        "social_stats": social_stats,
        "technical_data": tech_payload,
        "catalysts": catalysts_payload,
        "prediction_markets": markets_payload,
        "divergences": divs_payload,
        "reasons": reasons,
        "explanation": ssi_snap.explanation if ssi_snap else "",
        "recent_posts": posts_payload,
        "recent_news": news_payload,
        "engine": describe_engine()
    }


@router.get("/api/tickers/{ticker}/prediction-markets")
def get_ticker_prediction_markets(ticker: str, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    ticker_sym = ticker.upper()
    markets = get_recent_prediction_markets(db, ticker_sym)
    return [
        {
            "id": m.external_id,
            "title": m.title,
            "description": m.description,
            "category": m.category,
            "yes_probability": round(m.yes_probability * 100.0, 1),
            "no_probability": round(m.no_probability * 100.0, 1),
            "volume": m.volume,
            "liquidity": m.liquidity,
            "spread": m.spread,
            "quality_score": m.quality_score,
            "url": m.url,
            "ticker": m.ticker,
            "is_direct": bool(m.ticker and m.ticker.upper() == ticker_sym),
            "event_role": "DIRECT" if bool(m.ticker and m.ticker.upper() == ticker_sym) else "SECTOR_CATALYST",
            "impact_weight": 1.0 if bool(m.ticker and m.ticker.upper() == ticker_sym) else (DEFAULT_EVENT_COMPANY_MAPPINGS.get(m.event_key, {}).get(ticker_sym) if m.event_key else None),
            "event_key": m.event_key
        }
        for m in markets
    ]


@router.get("/api/tickers/{ticker}/divergences")
def get_ticker_divergences(ticker: str, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    ticker_sym = ticker.upper()
    divs = get_active_divergences(db, ticker_sym, hours=72)
    return [
        {
            "id": d.id,
            "type": d.type,
            "direction": d.direction,
            "strength": d.strength,
            "confidence": d.confidence,
            "description": d.description,
            "timestamp": d.timestamp.isoformat() + "Z" if d.timestamp else ""
        }
        for d in divs
    ]
