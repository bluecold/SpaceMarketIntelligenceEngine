from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.database.models import (
    TickerModel, SocialPostModel, NewsItemModel,
    MarketSnapshotModel, SSISnapshotModel, JobRunModel,
    PredictionMarketModel, PredictionMarketSnapshotModel, DivergenceModel,
    AlertModel
)
from app.config import INITIAL_TICKERS, DEFAULT_EVENT_COMPANY_MAPPINGS
from app.collectors.base import PredictionMarketData


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_tickers_seeded(db: Session):
    """Seed initial universe of aerospace stocks if table is empty or update metadata."""
    existing_tickers = {t.symbol: t for t in db.query(TickerModel).all()}
    if not existing_tickers:
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
    else:
        # Backfill metadata (sector, is_private_or_test) for existing records
        cfg_map = {t.symbol: t for t in INITIAL_TICKERS}
        updated = False
        for symbol, t_rec in existing_tickers.items():
            if symbol in cfg_map:
                cfg = cfg_map[symbol]
                if not t_rec.sector or t_rec.sector == "Space Technology":
                    t_rec.sector = cfg.sector
                    updated = True
                if t_rec.is_private_or_test is None:
                    t_rec.is_private_or_test = cfg.is_private_or_test
                    updated = True
                if not t_rec.name and cfg.name:
                    t_rec.name = cfg.name
                    updated = True
        if updated:
            db.commit()


def save_social_posts(db: Session, posts_data: List[Dict[str, Any]]) -> int:
    """
    Save social posts deduplicating by tweet_id.
    Batches lookup to eliminate N+1 queries, updates engagement metrics on existing posts,
    and returns number of newly added posts.
    """
    if not posts_data:
        return 0

    tweet_ids = [str(d["tweet_id"]) for d in posts_data if "tweet_id" in d]
    existing_posts = {
        p.tweet_id: p
        for p in db.query(SocialPostModel).filter(SocialPostModel.tweet_id.in_(tweet_ids)).all()
    }

    new_count = 0
    for data in posts_data:
        tweet_id = str(data["tweet_id"])
        existing = existing_posts.get(tweet_id)
        if existing:
            # Update engagement metrics for posts that went viral / gained engagement
            existing.likes = data.get("likes", existing.likes)
            existing.reposts = data.get("reposts", existing.reposts)
            existing.replies = data.get("replies", existing.replies)
            existing.views = data.get("views", existing.views)
            if "engagement_score" in data:
                existing.engagement_score = data["engagement_score"]
        else:
            created_at = data.get("created_at", utc_now())
            if hasattr(created_at, "tzinfo") and created_at.tzinfo is not None:
                created_at = created_at.astimezone(timezone.utc).replace(tzinfo=None)

            post = SocialPostModel(
                tweet_id=tweet_id,
                ticker=data["ticker"].upper(),
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
            existing_posts[tweet_id] = post
            new_count += 1

    db.commit()
    return new_count


def get_recent_social_posts(db: Session, ticker: str, hours: int = 24) -> List[SocialPostModel]:
    """Retrieve social posts for a ticker within the specified lookback window."""
    since = utc_now() - timedelta(hours=hours)
    ticker_up = ticker.upper()
    return (
        db.query(SocialPostModel)
        .filter(SocialPostModel.ticker == ticker_up)
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
                polarity=getattr(m, "polarity", 1),
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
            existing.polarity = getattr(m, "polarity", 1)
            existing.collected_at = now
            market_id = existing.id

        # Compute 24h probability delta from SQLite snapshot history if not already set by provider
        if (m.probability_change_24h == 0.0 or m.probability_change_24h is None) and existing:
            window_start = now - timedelta(hours=30)
            window_end = now - timedelta(hours=18)
            snap_24h = (
                db.query(PredictionMarketSnapshotModel)
                .filter(PredictionMarketSnapshotModel.market_id == market_id)
                .filter(PredictionMarketSnapshotModel.timestamp >= window_start)
                .filter(PredictionMarketSnapshotModel.timestamp <= window_end)
                .order_by(desc(PredictionMarketSnapshotModel.timestamp))
                .first()
            )

            if snap_24h:
                delta_24h = round((m.yes_probability - snap_24h.yes_probability) * 100.0, 2)
                m.probability_change_24h = delta_24h
            else:
                m.probability_change_24h = 0.0

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
    """
    Get active prediction markets, filtered and prioritized:
    1. Direct contracts for the specified ticker (top priority).
    2. Sector & Macro events with an impact mapping on the ticker.
    """
    query = db.query(PredictionMarketModel).filter(PredictionMarketModel.status == "ACTIVE")
    all_active = query.order_by(desc(PredictionMarketModel.quality_score)).all()
    
    if not ticker:
        return all_active

    ticker_up = ticker.upper()
    event_maps = mappings or DEFAULT_EVENT_COMPANY_MAPPINGS

    direct_markets = []
    sector_markets = []

    for m in all_active:
        # 1. Direct market for this ticker
        if m.ticker and m.ticker.upper() == ticker_up:
            direct_markets.append(m)
        # 2. Sector event market with an impact mapping on this ticker
        elif m.event_key and m.event_key in event_maps and ticker_up in event_maps[m.event_key]:
            sector_markets.append(m)
        # 3. Macro / unmapped global market with no ticker and no event_key
        elif not m.ticker and not m.event_key:
            sector_markets.append(m)

    # Return direct company markets first, followed by relevant sector events
    return direct_markets + sector_markets


def save_divergences(db: Session, ticker: str, divergences_data: List[Dict[str, Any]]) -> int:
    """
    Save or update active divergence episodes for a ticker.
    Maintains stateful divergence episodes:
    - Ongoing episodes: updates last_seen, strength, confidence, and description without duplicating.
    - New episodes: inserts a new active DivergenceModel row.
    - Ceased episodes: sets resolved_at = now to mark them as resolved.
    """
    now = utc_now()
    ticker_sym = ticker.upper()
    
    # 1. Fetch currently active (unresolved) episodes for this ticker
    active_episodes = (
        db.query(DivergenceModel)
        .filter(DivergenceModel.ticker == ticker_sym, DivergenceModel.resolved_at == None)
        .all()
    )
    active_map = {ep.type: ep for ep in active_episodes}
    detected_types = set()
    count = 0

    # 2. Update existing active episodes or create new ones
    for d in divergences_data:
        div_type = d["type"]
        detected_types.add(div_type)
        if div_type in active_map:
            ep = active_map[div_type]
            ep.last_seen = now
            ep.strength = d.get("strength", 1.0)
            ep.confidence = d.get("confidence", 0.5)
            ep.description = d["description"]
        else:
            new_ep = DivergenceModel(
                ticker=ticker_sym,
                timestamp=now,
                last_seen=now,
                type=div_type,
                source_a=d["source_a"],
                source_b=d["source_b"],
                source_c=d.get("source_c"),
                direction=d["direction"],
                strength=d.get("strength", 1.0),
                confidence=d.get("confidence", 0.5),
                description=d["description"],
                resolved_at=None
            )
            db.add(new_ep)
        count += 1

    # 3. Resolve episodes that ceased in this execution
    for div_type, ep in active_map.items():
        if div_type not in detected_types:
            ep.resolved_at = now

    db.commit()
    return count


def get_active_divergences(db: Session, ticker: Optional[str] = None, hours: int = 48) -> List[DivergenceModel]:
    """Retrieve currently active divergence episodes."""
    query = db.query(DivergenceModel).filter(DivergenceModel.resolved_at == None)
    if ticker:
        query = query.filter(DivergenceModel.ticker == ticker.upper())
    return query.order_by(desc(DivergenceModel.last_seen)).all()


def save_alerts(db: Session, ticker: str, alerts_data: List[Dict[str, Any]]) -> int:
    """
    Stateful persistence for trading signals, catalysts, and divergences.
    Updates active episodes without creating duplicates, and resolves ceased alerts.
    """
    now = utc_now()
    all_alerts = db.query(AlertModel).filter(
        AlertModel.ticker == ticker.upper()
    ).all()
    alert_map = {a.alert_id: a for a in all_alerts}
    detected_ids = set()

    for item in alerts_data:
        al_type = item.get("type", "UNKNOWN")
        al_level = item.get("level", "INFO")
        al_category = item.get("category")
        if not al_category:
            if "BUY" in al_type or "AVOID" in al_type:
                al_category = "SIGNAL"
            elif "CATALYST" in al_type:
                al_category = "CATALYST"
            elif "DIVERGENCE" in al_type or "CONFIRMATION" in al_type or "REVERSAL" in al_type:
                al_category = "DIVERGENCE"
            else:
                al_category = "SIGNAL"

        alert_id = item.get("id") or f"{ticker.upper()}:{al_category}:{al_type}"
        detected_ids.add(alert_id)

        if alert_id in alert_map:
            existing = alert_map[alert_id]
            if existing.resolved_at is not None:
                # Reopen resolved alert
                existing.resolved_at = None
                existing.timestamp = now
            existing.last_seen = now
            existing.level = al_level
            existing.message = item.get("message", existing.message)
            existing.category = al_category
        else:
            new_alert = AlertModel(
                alert_id=alert_id,
                ticker=ticker.upper(),
                type=al_type,
                category=al_category,
                level=al_level,
                message=item.get("message", ""),
                timestamp=now,
                last_seen=now,
                resolved_at=None
            )
            db.add(new_alert)
            alert_map[alert_id] = new_alert

    # Resolve active alerts that ceased in this run
    for al_id, existing in alert_map.items():
        if al_id not in detected_ids and existing.resolved_at is None:
            existing.resolved_at = now

    db.commit()
    return len(detected_ids)


def get_active_alerts_batch(db: Session, tickers: Optional[List[str]] = None) -> List[AlertModel]:
    """Retrieve all active alerts across all or specified tickers."""
    query = db.query(AlertModel).filter(AlertModel.resolved_at == None)
    if tickers:
        query = query.filter(AlertModel.ticker.in_([t.upper() for t in tickers]))
    return query.order_by(desc(AlertModel.last_seen)).all()


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
        post_count=data.get("post_count"),
        news_count=data.get("news_count"),
        prediction_count=data.get("prediction_count"),
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
    """Retrieve active divergence episodes grouped by ticker in a single consolidated batch query."""
    query = db.query(DivergenceModel).filter(DivergenceModel.resolved_at == None)
    if tickers:
        query = query.filter(DivergenceModel.ticker.in_([t.upper() for t in tickers]))
    
    divs = query.order_by(desc(DivergenceModel.last_seen)).all()
    res: Dict[str, List[DivergenceModel]] = defaultdict(list)
    for d in divs:
        res[d.ticker].append(d)
    return res


def get_history_series(db: Session, ticker: str, limit: int = 100) -> List[Dict[str, Any]]:
    # Retrieve the latest `limit` snapshots in descending order and reverse for chronological display
    snaps = (
        db.query(SSISnapshotModel)
        .filter(SSISnapshotModel.ticker == ticker)
        .order_by(desc(SSISnapshotModel.timestamp))
        .limit(limit)
        .all()
    )
    snaps_chronological = list(reversed(snaps))
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
        for s in snaps_chronological
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
