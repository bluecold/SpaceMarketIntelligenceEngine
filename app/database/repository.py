from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.database.models import (
    TickerModel, SocialPostModel, NewsItemModel,
    MarketSnapshotModel, SSISnapshotModel, JobRunModel,
    PredictionMarketModel, PredictionMarketSnapshotModel, DivergenceModel
)
from app.config import INITIAL_TICKERS, DEFAULT_EVENT_COMPANY_MAPPINGS
from app.collectors.base import PredictionMarketData


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_tickers_seeded(db: Session):
    """Seed initial universe of aerospace stocks if table is empty."""
    count = db.query(TickerModel).count()
    if count == 0:
        for t in INITIAL_TICKERS:
            ticker_record = TickerModel(
                symbol=t.symbol,
                name=t.name,
                sector=t.sector,
                is_active=True,
                is_private_or_test=t.is_private_or_test
            )
            db.add(ticker_record)
        db.commit()


def save_social_posts(db: Session, posts_data: List[Dict[str, Any]]) -> int:
    """Save social posts deduplicating by tweet_id. Returns number of newly added posts."""
    new_count = 0
    for data in posts_data:
        tweet_id = str(data["tweet_id"])
        existing = db.query(SocialPostModel).filter(SocialPostModel.tweet_id == tweet_id).first()
        if not existing:
            created_at = data.get("created_at", utc_now())
            if hasattr(created_at, "tzinfo") and created_at.tzinfo is not None:
                created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)

            post = SocialPostModel(
                tweet_id=tweet_id,
                ticker=data["ticker"],
                username=data.get("username", "unknown"),
                text=data["text"],
                created_at=created_at,
                url=data.get("url"),
                likes=data.get("likes", 0),
                reposts=data.get("reposts", 0),
                replies=data.get("replies", 0),
                views=data.get("views", 0),
                sentiment_score=data.get("sentiment_score", 0.0),
                sentiment_label=data.get("sentiment_label", "NEUTRAL"),
                sentiment_confidence=data.get("sentiment_confidence", 1.0),
                relevance_score=data.get("relevance_score", 1.0),
                engagement_score=data.get("engagement_score", 0.0),
                recency_weight=data.get("recency_weight", 1.0),
                catalyst=data.get("catalyst"),
                catalyst_direction=data.get("catalyst_direction"),
                catalyst_importance=data.get("catalyst_importance", "MEDIUM")
            )
            db.add(post)
            new_count += 1
    db.commit()
    return new_count


def get_recent_social_posts(db: Session, ticker: str, hours: int = 24) -> List[SocialPostModel]:
    """Retrieve social posts for a ticker within the specified lookback window."""
    since = utc_now() - timedelta(hours=hours)
    return (
        db.query(SocialPostModel)
        .filter(SocialPostModel.ticker == ticker)
        .filter(SocialPostModel.created_at >= since)
        .order_by(desc(SocialPostModel.created_at))
        .all()
    )


def save_news_items(db: Session, news_data: List[Dict[str, Any]]) -> int:
    """Save news items deduplicating by URL. Returns number of newly added items."""
    new_count = 0
    for data in news_data:
        url = data.get("url")
        if not url:
            continue
        existing = db.query(NewsItemModel).filter(NewsItemModel.url == url).first()
        if not existing:
            pub_at = data.get("published_at", utc_now())
            if hasattr(pub_at, "tzinfo") and pub_at.tzinfo is not None:
                pub_at = pub_at.astimezone(timezone.utc).replace(tzinfo=None)
                
            news = NewsItemModel(
                ticker=data["ticker"],
                title=data["title"],
                summary=data.get("summary"),
                source=data.get("source"),
                url=url,
                published_at=pub_at,
                sentiment_score=data.get("sentiment_score", 0.0),
                sentiment_label=data.get("sentiment_label", "NEUTRAL"),
                sentiment_confidence=data.get("sentiment_confidence", 1.0),
                relevance_score=data.get("relevance_score", 1.0),
                catalyst=data.get("catalyst"),
                catalyst_direction=data.get("catalyst_direction"),
                catalyst_importance=data.get("catalyst_importance", "MEDIUM")
            )
            db.add(news)
            new_count += 1
    db.commit()
    return new_count


def get_recent_news_items(db: Session, ticker: str, days: int = 3) -> List[NewsItemModel]:
    """Retrieve news items for a ticker within the specified lookback window."""
    since = utc_now() - timedelta(days=days)
    return (
        db.query(NewsItemModel)
        .filter(NewsItemModel.ticker == ticker)
        .filter(NewsItemModel.published_at >= since)
        .order_by(desc(NewsItemModel.published_at))
        .all()
    )


def save_prediction_markets(db: Session, markets: List[PredictionMarketData]) -> int:
    """Upsert prediction markets and append timestamped snapshot."""
    count = 0
    now = utc_now()
    for m in markets:
        existing = db.query(PredictionMarketModel).filter(PredictionMarketModel.external_id == m.external_id).first()
        
        end_d = m.end_date
        if end_d and end_d.tzinfo is not None:
            end_d = end_d.astimezone(timezone.utc).replace(tzinfo=None)
            
        if not existing:
            market_db = PredictionMarketModel(
                external_id=m.external_id,
                ticker=m.ticker,
                title=m.title,
                description=m.description,
                category=m.category,
                status=m.status,
                created_at=now,
                end_date=end_d,
                yes_probability=m.yes_probability,
                no_probability=m.no_probability,
                volume=m.volume,
                liquidity=m.liquidity,
                spread=m.spread,
                quality_score=m.quality_score,
                event_key=m.event_key,
                url=m.url,
                collected_at=now
            )
            db.add(market_db)
            db.flush()
            market_id = market_db.id
            count += 1
        else:
            existing.yes_probability = m.yes_probability
            existing.no_probability = m.no_probability
            existing.volume = m.volume
            existing.liquidity = m.liquidity
            existing.spread = m.spread
            existing.quality_score = m.quality_score
            existing.event_key = m.event_key
            existing.collected_at = now
            market_id = existing.id

        # Compute 24h probability delta from SQLite snapshot history if not already set by provider
        if (m.probability_change_24h == 0.0 or m.probability_change_24h is None) and existing:
            snap_24h = (
                db.query(PredictionMarketSnapshotModel)
                .filter(PredictionMarketSnapshotModel.market_id == market_id)
                .filter(PredictionMarketSnapshotModel.timestamp <= now - timedelta(hours=18))
                .order_by(desc(PredictionMarketSnapshotModel.timestamp))
                .first()
            )
            if not snap_24h:
                # Fallback to the latest prior snapshot
                snap_24h = (
                    db.query(PredictionMarketSnapshotModel)
                    .filter(PredictionMarketSnapshotModel.market_id == market_id)
                    .order_by(desc(PredictionMarketSnapshotModel.id))
                    .first()
                )

            if snap_24h:
                delta_24h = round((m.yes_probability - snap_24h.yes_probability) * 100.0, 2)
                m.probability_change_24h = delta_24h

        # Append snapshot
        snap = PredictionMarketSnapshotModel(
            market_id=market_id,
            timestamp=now,
            yes_probability=m.yes_probability,
            no_probability=m.no_probability,
            volume=m.volume,
            liquidity=m.liquidity,
            spread=m.spread,
            quality_score=m.quality_score,
            probability_change_1h=m.probability_change_1h,
            probability_change_6h=m.probability_change_6h,
            probability_change_24h=m.probability_change_24h
        )
        db.add(snap)
    db.commit()
    return count


def get_recent_prediction_markets(
    db: Session,
    ticker: Optional[str] = None,
    mappings: Optional[Dict[str, Dict[str, float]]] = None
) -> List[PredictionMarketModel]:
    """Get active prediction markets, filtered by ticker and relevant cross-company event mappings."""
    query = db.query(PredictionMarketModel).filter(PredictionMarketModel.status == "ACTIVE")
    all_active = query.order_by(desc(PredictionMarketModel.quality_score)).all()
    
    if not ticker:
        return all_active

    ticker_up = ticker.upper()
    event_maps = mappings or DEFAULT_EVENT_COMPANY_MAPPINGS

    filtered = []
    for m in all_active:
        # 1. Direct market for this ticker
        if m.ticker and m.ticker.upper() == ticker_up:
            filtered.append(m)
            continue
        # 2. Sector event market with an impact mapping on this ticker
        if m.event_key and m.event_key in event_maps and ticker_up in event_maps[m.event_key]:
            filtered.append(m)
            continue
        # 3. Macro / unmapped global market with no ticker and no event_key
        if not m.ticker and not m.event_key:
            filtered.append(m)

    return filtered


def save_divergences(db: Session, ticker: str, divergences_data: List[Dict[str, Any]]) -> int:
    """Save detected divergences for a ticker."""
    count = 0
    now = utc_now()
    for d in divergences_data:
        div = DivergenceModel(
            ticker=ticker,
            timestamp=now,
            type=d["type"],
            source_a=d["source_a"],
            source_b=d["source_b"],
            source_c=d.get("source_c"),
            direction=d["direction"],
            strength=d.get("strength", 1.0),
            confidence=d.get("confidence", 0.5),
            description=d["description"]
        )
        db.add(div)
        count += 1
    db.commit()
    return count


def get_active_divergences(db: Session, ticker: Optional[str] = None, hours: int = 48) -> List[DivergenceModel]:
    """Retrieve recent active divergences."""
    since = utc_now() - timedelta(hours=hours)
    query = db.query(DivergenceModel).filter(DivergenceModel.timestamp >= since)
    if ticker:
        query = query.filter(DivergenceModel.ticker == ticker.upper())
    return query.order_by(desc(DivergenceModel.timestamp)).all()


def save_market_snapshot(db: Session, data: Dict[str, Any]) -> MarketSnapshotModel:
    snapshot = MarketSnapshotModel(
        ticker=data["ticker"],
        timestamp=utc_now(),
        price=data.get("price"),
        volume=data.get("volume"),
        market_status=data.get("status", "AVAILABLE"),
        ema200=data.get("ema200"),
        rsi14=data.get("rsi14"),
        bollinger_upper=data.get("bollinger_upper"),
        bollinger_middle=data.get("bollinger_middle"),
        bollinger_lower=data.get("bollinger_lower"),
        macd_line=data.get("macd_line"),
        macd_signal=data.get("macd_signal"),
        macd_histogram=data.get("macd_histogram"),
        volume_ma20=data.get("volume_ma20"),
        volume_ratio=data.get("volume_ratio"),
        atr=data.get("atr"),
        technical_score=data.get("technical_score")
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_latest_market_snapshot(db: Session, ticker: str) -> Optional[MarketSnapshotModel]:
    return (
        db.query(MarketSnapshotModel)
        .filter(MarketSnapshotModel.ticker == ticker)
        .order_by(desc(MarketSnapshotModel.timestamp))
        .first()
    )


def save_ssi_snapshot(db: Session, data: Dict[str, Any]) -> SSISnapshotModel:
    sig_val = data["signal"]
    base_sig = data.get("base_signal", sig_val)
    mod_sig = data.get("signal_modifier")

    snapshot = SSISnapshotModel(
        ticker=data["ticker"],
        timestamp=utc_now(),
        social_score=data["social_score"],
        prediction_score=data.get("prediction_score"),
        news_score=data.get("news_score"),
        momentum_score=data.get("momentum_score"),
        fundamental_score=data.get("fundamental_score"),
        risk_score=data.get("risk_score"),
        technical_score=data.get("technical_score"),
        ssi=data["ssi"],
        smi=data.get("smi", data["ssi"]),
        ssi_momentum_1d=data.get("ssi_momentum_1d", 0.0),
        ssi_momentum_3d=data.get("ssi_momentum_3d", 0.0),
        ssi_momentum_5d=data.get("ssi_momentum_5d", 0.0),
        signal=sig_val,
        base_signal=base_sig,
        signal_modifier=mod_sig,
        confidence=data["confidence"],
        data_completeness=data["data_completeness"],
        data_quality=data.get("data_quality", data["data_completeness"]),
        price=data.get("price"),
        volume=data.get("volume"),
        explanation=data.get("explanation")
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get_latest_ssi_snapshot(db: Session, ticker: str) -> Optional[SSISnapshotModel]:
    return (
        db.query(SSISnapshotModel)
        .filter(SSISnapshotModel.ticker == ticker.upper())
        .order_by(desc(SSISnapshotModel.timestamp))
        .first()
    )


def get_historical_ssi_snapshot(
    db: Session,
    ticker: str,
    target_hours_ago: float = 24.0,
    tolerance_hours: float = 6.0,
    max_lookback_multiplier: float = 2.5
) -> Optional[SSISnapshotModel]:
    """
    Retrieves the closest historical snapshot within a bounded quantitative window
    around target_hours_ago (e.g. 24h for 1D momentum, 72h for 3D, 120h for 5D).
    
    Window constraints:
    - min_time: now - tolerance_hours (e.g. at least 6h old to avoid intra-hour noise).
    - target_time: now - target_hours_ago (e.g. ~24h ago).
    - max_time: now - (target_hours_ago * max_lookback_multiplier) (e.g. at most 60h ago for 1D).
    
    If no snapshot exists within [max_time, min_time], returns None so momentum is 0.0
    rather than computed against stale data from weeks ago.
    """
    now = utc_now()
    min_time = now - timedelta(hours=tolerance_hours)
    target_time = now - timedelta(hours=target_hours_ago)
    max_time = now - timedelta(hours=target_hours_ago * max_lookback_multiplier)

    # 1. Best match: Latest snapshot on or before target_time within max lookback [max_time, target_time]
    snap = (
        db.query(SSISnapshotModel)
        .filter(SSISnapshotModel.ticker == ticker.upper())
        .filter(SSISnapshotModel.timestamp <= target_time)
        .filter(SSISnapshotModel.timestamp >= max_time)
        .order_by(desc(SSISnapshotModel.timestamp))
        .first()
    )
    if snap:
        return snap

    # 2. Secondary match: Earliest snapshot in the tolerance window [target_time, min_time]
    snap_tolerance = (
        db.query(SSISnapshotModel)
        .filter(SSISnapshotModel.ticker == ticker.upper())
        .filter(SSISnapshotModel.timestamp > target_time)
        .filter(SSISnapshotModel.timestamp <= min_time)
        .order_by(SSISnapshotModel.timestamp.asc())
        .first()
    )
    if snap_tolerance:
        return snap_tolerance

    # 3. No snapshot found within the valid bounded window [max_time, min_time] -> return None
    return None


def get_latest_ssi_snapshots_batch(db: Session, tickers: Optional[List[str]] = None) -> Dict[str, SSISnapshotModel]:
    """Retrieve the latest SSI/SMI snapshot for each ticker in a single consolidated batch query."""
    subquery = db.query(
        SSISnapshotModel.ticker,
        func.max(SSISnapshotModel.id).label("max_id")
    )
    if tickers:
        subquery = subquery.filter(SSISnapshotModel.ticker.in_([t.upper() for t in tickers]))
    subquery = subquery.group_by(SSISnapshotModel.ticker).subquery()

    records = (
        db.query(SSISnapshotModel)
        .join(subquery, SSISnapshotModel.id == subquery.c.max_id)
        .all()
    )
    return {r.ticker: r for r in records}


def get_latest_market_snapshots_batch(db: Session, tickers: Optional[List[str]] = None) -> Dict[str, MarketSnapshotModel]:
    """Retrieve the latest market snapshot for each ticker in a single consolidated batch query."""
    subquery = db.query(
        MarketSnapshotModel.ticker,
        func.max(MarketSnapshotModel.id).label("max_id")
    )
    if tickers:
        subquery = subquery.filter(MarketSnapshotModel.ticker.in_([t.upper() for t in tickers]))
    subquery = subquery.group_by(MarketSnapshotModel.ticker).subquery()

    records = (
        db.query(MarketSnapshotModel)
        .join(subquery, MarketSnapshotModel.id == subquery.c.max_id)
        .all()
    )
    return {r.ticker: r for r in records}


def get_active_divergences_batch(db: Session, hours: int = 48, tickers: Optional[List[str]] = None) -> Dict[str, List[DivergenceModel]]:
    """Retrieve active divergences grouped by ticker in a single consolidated batch query."""
    since = utc_now() - timedelta(hours=hours)
    query = db.query(DivergenceModel).filter(DivergenceModel.timestamp >= since)
    if tickers:
        query = query.filter(DivergenceModel.ticker.in_([t.upper() for t in tickers]))
    
    divs = query.order_by(desc(DivergenceModel.timestamp)).all()
    res: Dict[str, List[DivergenceModel]] = defaultdict(list)
    for d in divs:
        res[d.ticker].append(d)
    return res


def get_history_series(db: Session, ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
    snaps = (
        db.query(SSISnapshotModel)
        .filter(SSISnapshotModel.ticker == ticker)
        .order_by(SSISnapshotModel.timestamp.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "timestamp": s.timestamp.isoformat() + "Z" if s.timestamp else "",
            "price": s.price,
            "smi": s.smi if s.smi is not None else s.ssi,
            "ssi": s.social_score,
            "pms": s.prediction_score,
            "social_score": s.social_score,
            "news_score": s.news_score,
            "momentum_score": s.momentum_score,
            "risk_score": s.risk_score,
            "volume": s.volume,
            "signal": s.signal
        }
        for s in snaps
    ]


def create_job_run(db: Session, job_name: str) -> JobRunModel:
    job = JobRunModel(job_name=job_name, started_at=utc_now(), status="RUNNING")
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def finish_job_run(db: Session, job_id: int, status: str = "SUCCESS", records: int = 0, error: Optional[str] = None):
    job = db.query(JobRunModel).filter(JobRunModel.id == job_id).first()
    if job:
        job.finished_at = utc_now()
        job.status = status
        job.records_processed = records
        job.error_message = error
        db.commit()
