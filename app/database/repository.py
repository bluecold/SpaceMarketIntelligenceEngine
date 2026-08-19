from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database.models import (
    TickerModel, SocialPostModel, NewsItemModel,
    MarketSnapshotModel, SSISnapshotModel, JobRunModel,
    PredictionMarketModel, PredictionMarketSnapshotModel, DivergenceModel
)
from app.config import INITIAL_TICKERS
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
            existing.collected_at = now
            market_id = existing.id

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


def get_recent_prediction_markets(db: Session, ticker: Optional[str] = None) -> List[PredictionMarketModel]:
    """Get active prediction markets, optionally filtered by ticker."""
    query = db.query(PredictionMarketModel).filter(PredictionMarketModel.status == "ACTIVE")
    if ticker:
        ticker_up = ticker.upper()
        # Direct markets or sector events without specific ticker
        query = query.filter((PredictionMarketModel.ticker == ticker_up) | (PredictionMarketModel.ticker == None))
    return query.order_by(desc(PredictionMarketModel.quality_score)).all()


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
        signal=data["signal"],
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
        .filter(SSISnapshotModel.ticker == ticker)
        .order_by(desc(SSISnapshotModel.timestamp))
        .first()
    )


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
