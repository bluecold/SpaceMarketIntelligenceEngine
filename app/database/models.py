from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from app.database.connection import Base


class TickerModel(Base):
    __tablename__ = "tickers"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(10), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    social_posts = relationship("SocialPostModel", back_populates="ticker_rel")
    news_items = relationship("NewsItemModel", back_populates="ticker_rel")
    ssi_snapshots = relationship("SSISnapshotModel", back_populates="ticker_rel")


class SocialPostModel(Base):
    __tablename__ = "social_posts"

    id = Column(Integer, primary_key=True, index=True)
    tweet_id = Column(String(64), unique=True, index=True, nullable=False)
    ticker = Column(String(10), ForeignKey("tickers.symbol"), index=True, nullable=False)
    username = Column(String(100), nullable=False)
    text = Column(Text, nullable=False)
    url = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, index=True)
    collected_at = Column(DateTime, default=datetime.utcnow)

    # Metrics
    likes = Column(Integer, default=0)
    reposts = Column(Integer, default=0)
    replies = Column(Integer, default=0)
    views = Column(Integer, default=0)

    # Derived NLP & Scoring fields
    sentiment_score = Column(Float, nullable=False)  # -1.0 to +1.0
    sentiment_label = Column(String(20), nullable=False)  # BULLISH, BEARISH, NEUTRAL
    sentiment_confidence = Column(Float, default=1.0)  # 0.0 to 1.0
    relevance_score = Column(Float, default=1.0)  # 0.0 to 1.0
    engagement_score = Column(Float, default=0.0)
    recency_weight = Column(Float, default=1.0)
    
    catalyst = Column(String(50), nullable=True)
    catalyst_direction = Column(String(20), nullable=True)
    catalyst_importance = Column(String(20), default="MEDIUM")  # LOW, MEDIUM, HIGH, CRITICAL

    ticker_rel = relationship("TickerModel", back_populates="social_posts")


class NewsItemModel(Base):
    __tablename__ = "news_items"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), ForeignKey("tickers.symbol"), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    source = Column(String(100), nullable=True)
    url = Column(String(500), unique=True, index=True, nullable=False)
    published_at = Column(DateTime, nullable=False, index=True)
    collected_at = Column(DateTime, default=datetime.utcnow)

    sentiment_score = Column(Float, default=0.0)  # -1.0 to +1.0
    sentiment_label = Column(String(20), default="NEUTRAL")
    sentiment_confidence = Column(Float, default=1.0)
    relevance_score = Column(Float, default=1.0)
    catalyst = Column(String(50), nullable=True)
    catalyst_direction = Column(String(20), nullable=True)
    catalyst_importance = Column(String(20), default="MEDIUM")

    ticker_rel = relationship("TickerModel", back_populates="news_items")


class PredictionMarketModel(Base):
    __tablename__ = "prediction_markets"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(128), unique=True, index=True, nullable=False)
    ticker = Column(String(10), ForeignKey("tickers.symbol"), index=True, nullable=True)  # Null if broad sector event
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), default="SPACE")
    status = Column(String(20), default="ACTIVE")  # ACTIVE, CLOSED, RESOLVED
    created_at = Column(DateTime, default=datetime.utcnow)
    end_date = Column(DateTime, nullable=True)
    resolution_date = Column(DateTime, nullable=True)
    
    yes_probability = Column(Float, nullable=False)  # 0.0 to 1.0
    no_probability = Column(Float, nullable=False)   # 0.0 to 1.0
    volume = Column(Float, default=0.0)             # USD Volume
    liquidity = Column(Float, default=0.0)          # USD Liquidity
    spread = Column(Float, default=0.0)             # Bid-Ask spread
    quality_score = Column(Float, default=50.0)     # 0 to 100
    
    url = Column(String(500), nullable=True)
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)

    snapshots = relationship("PredictionMarketSnapshotModel", back_populates="market_rel")


class PredictionMarketSnapshotModel(Base):
    __tablename__ = "prediction_market_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    market_id = Column(Integer, ForeignKey("prediction_markets.id"), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    yes_probability = Column(Float, nullable=False)
    no_probability = Column(Float, nullable=False)
    volume = Column(Float, default=0.0)
    liquidity = Column(Float, default=0.0)
    spread = Column(Float, default=0.0)
    quality_score = Column(Float, default=50.0)
    
    probability_change_1h = Column(Float, default=0.0)
    probability_change_6h = Column(Float, default=0.0)
    probability_change_24h = Column(Float, default=0.0)

    market_rel = relationship("PredictionMarketModel", back_populates="snapshots")


class PredictionMarketEventModel(Base):
    __tablename__ = "prediction_market_events"

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String(128), unique=True, index=True, nullable=False)
    event_title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    probability = Column(Float, default=0.5)
    company_mappings = Column(Text, nullable=True)  # JSON string: {"ASTS": 0.20, "RKLB": 0.30, ...}
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DivergenceModel(Base):
    __tablename__ = "divergences"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), ForeignKey("tickers.symbol"), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    type = Column(String(50), nullable=False)  # BULLISH_DIVERGENCE, BEARISH_DIVERGENCE, BULLISH_CONFIRMATION, BEARISH_CONFIRMATION, EARLY_REVERSAL
    source_a = Column(String(30), nullable=False)  # e.g., "X_SOCIAL"
    source_b = Column(String(30), nullable=False)  # e.g., "POLYMARKET"
    source_c = Column(String(30), nullable=True)   # e.g., "PRICE"
    direction = Column(String(20), nullable=False) # "BULLISH", "BEARISH", "NEUTRAL"
    strength = Column(Float, default=1.0)          # 0.0 to 1.0
    confidence = Column(Float, default=0.5)        # 0.0 to 1.0
    description = Column(Text, nullable=False)
    resolved_at = Column(DateTime, nullable=True)


class MarketSnapshotModel(Base):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    price = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    market_status = Column(String(30), default="AVAILABLE")  # AVAILABLE, DATA_UNAVAILABLE, ERROR

    # Indicators
    ema200 = Column(Float, nullable=True)
    rsi14 = Column(Float, nullable=True)
    bollinger_upper = Column(Float, nullable=True)
    bollinger_middle = Column(Float, nullable=True)
    bollinger_lower = Column(Float, nullable=True)
    macd_line = Column(Float, nullable=True)
    macd_signal = Column(Float, nullable=True)
    macd_histogram = Column(Float, nullable=True)
    volume_ma20 = Column(Float, nullable=True)
    volume_ratio = Column(Float, nullable=True)
    atr = Column(Float, nullable=True)

    technical_score = Column(Float, nullable=True)  # 0 to 40


class SSISnapshotModel(Base):
    __tablename__ = "ssi_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String(10), ForeignKey("tickers.symbol"), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # Individual Pillar Scores (0 - 100)
    social_score = Column(Float, nullable=False)       # Pure Social SSI
    prediction_score = Column(Float, nullable=True)   # PMS Score
    news_score = Column(Float, nullable=True)         # News Score
    momentum_score = Column(Float, nullable=True)     # Momentum Score
    fundamental_score = Column(Float, nullable=True)  # Fundamental Score
    risk_score = Column(Float, nullable=True)         # Risk Score
    technical_score = Column(Float, nullable=True)    # Technical Score (out of 40)
    
    # Composite Indices (0 - 100)
    ssi = Column(Float, nullable=False)               # Social Sentiment Index
    smi = Column(Float, nullable=True)                # Space Market Intelligence Index
    
    ssi_momentum_1d = Column(Float, default=0.0)
    ssi_momentum_3d = Column(Float, default=0.0)
    ssi_momentum_5d = Column(Float, default=0.0)

    signal = Column(String(30), nullable=False)       # STRONG BUY, BUY, WATCH, HOLD, AVOID, STRONG AVOID, N/A
    confidence = Column(Float, nullable=False)        # 0 to 100 %
    data_completeness = Column(Float, nullable=False) # 0 to 100 %
    data_quality = Column(Float, default=100.0)       # 0 to 100 %
    
    price = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    explanation = Column(Text, nullable=True)

    ticker_rel = relationship("TickerModel", back_populates="ssi_snapshots")


class JobRunModel(Base):
    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, index=True)
    job_name = Column(String(100), nullable=False, index=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(20), nullable=False)  # SUCCESS, ERROR, RUNNING
    records_processed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
