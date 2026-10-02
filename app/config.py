import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TickerConfig(BaseModel):
    symbol: str
    name: str
    narrative_entity: str
    aliases: List[str]
    sector: str = "Space Technology"
    is_private_or_test: bool = False
    is_tradable: bool = True
    market_symbol: Optional[str] = None
    exchange: str = "NASDAQ"
    validation_status: str = "VALIDATED"


# Core initial space stocks specified for SMIE v2.0
INITIAL_TICKERS = [
    TickerConfig(
        symbol="ASTS",
        name="AST SpaceMobile",
        narrative_entity="AST SpaceMobile",
        aliases=["$ASTS", "AST SpaceMobile", "ASTSpaceMobile", "ASTS_SpaceMobile", "BlueBird"],
        sector="Direct-to-Cell / Satellite Telecom",
        is_private_or_test=False,
        is_tradable=True,
        market_symbol="ASTS",
        exchange="NASDAQ",
        validation_status="VALIDATED"
    ),
    TickerConfig(
        symbol="RKLB",
        name="Rocket Lab",
        narrative_entity="Rocket Lab",
        aliases=["$RKLB", "Rocket Lab", "RocketLab", "Neutron rocket", "Electron rocket"],
        sector="Launch Vehicles & Space Systems",
        is_private_or_test=False,
        is_tradable=True,
        market_symbol="RKLB",
        exchange="NASDAQ",
        validation_status="VALIDATED"
    ),
    TickerConfig(
        symbol="SATL",
        name="Satellogic",
        narrative_entity="Satellogic",
        aliases=["$SATL", "Satellogic", "Aleph-1"],
        sector="Geospatial & Earth Observation",
        is_private_or_test=False,
        is_tradable=True,
        market_symbol="SATL",
        exchange="NASDAQ",
        validation_status="VALIDATED"
    ),
    TickerConfig(
        symbol="SPCE",
        name="Virgin Galactic",
        narrative_entity="Virgin Galactic",
        aliases=["$SPCE", "Virgin Galactic", "VirginGalactic", "VSS Unity", "Delta Class"],
        sector="Commercial Spaceflight & Tourism",
        is_private_or_test=False,
        is_tradable=True,
        market_symbol="SPCE",
        exchange="NYSE",
        validation_status="VALIDATED"
    ),
    TickerConfig(
        symbol="SPCX",
        name="SpaceX",
        narrative_entity="SpaceX",
        aliases=["$SPCX", "SpaceX", "Space X", "Starship", "Starlink"],
        sector="Launch Vehicles & Satellite Infrastructure",
        is_private_or_test=False,
        is_tradable=True,
        market_symbol="SPCX",
        exchange="NASDAQ",
        validation_status="VALIDATED"
    )
]

# Baseline Event Mapping: Global Space & Defense Events -> Company Impact Matrix
# Impact range: -1.0 (strongly negative) to +1.0 (strongly positive)
DEFAULT_EVENT_COMPANY_MAPPINGS: Dict[str, Dict[str, float]] = {
    "spacex_starship_orbital_success": {
        "SPCX": 0.50,
        "ASTS": 0.25,  # Benefits from Starship launch capacity for large BlueBird satellites
        "RKLB": 0.15,  # Validates commercial space economy, though competitive
        "SATL": 0.10,
        "SPCE": 0.05
    },
    "spacex_starlink_direct_to_cell_fcc_approval": {
        "SPCX": 0.40,
        "ASTS": -0.20, # Direct competitor to ASTS cellular broadband, but validates market
        "RKLB": 0.05
    },
    "nasa_artemis_moon_contract_expansion": {
        "RKLB": 0.35,  # Lunar CAPSTONE & exploration contracts
        "ASTS": 0.10,
        "SPCX": 0.30,
        "SATL": 0.15
    },
    "us_space_force_sda_defense_contracts": {
        "RKLB": 0.30,  # Space Systems spacecraft / buses
        "SATL": 0.30,  # Geospatial intelligence imaging contracts
        "ASTS": 0.15,  # Government secure cellular comms
        "SPCX": 0.25
    },
    "commercial_launch_cadence_record": {
        "RKLB": 0.30,
        "SPCX": 0.40,
        "ASTS": 0.10,
        "SATL": 0.10
    }
}


class Settings(BaseSettings):
    APP_NAME: str = "Space Market Intelligence Engine"
    APP_VERSION: str = "2.2.0"
    RULES_VERSION: str = "2.2.0"  # Stored per snapshot: 2.2.0 = opinion-only SSI + baseline, FinTwitBERT, mirrored bands, v2.2 weights
    ENVIRONMENT: str = "development"  # "development", "testing", "production"
    DEBUG: bool = True
    DATABASE_URL: str = "sqlite:///./data/space_sentiment.db"
    TIMEZONE: str = "America/Argentina/Cordoba"
    
    # CORS Origins
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ]
    
    # Data Provenance and Mock Governance
    ALLOW_MOCK_FALLBACK: bool = False  # If False, unauthenticated/failing live collectors return empty datasets instead of generating fake mock data
    
    # X / Social Provider Settings
    X_PROVIDER: str = "twikit"  # "twikit" or "mock"
    X_AUTH_INFO_1: str = ""
    X_AUTH_INFO_2: str = ""
    X_PASSWORD: str = ""
    X_AUTH_TOKEN: str = ""
    X_CT0: str = ""
    X_COOKIES_FILE: str = "data/x_cookies.json"
    
    # Social Collector Params
    SOCIAL_LOOKBACK_HOURS: int = 24
    SOCIAL_MAX_POSTS_PER_TICKER: int = 100
    SOCIAL_MIN_RELEVANCE: float = 0.40
    # Sentiment models are English-only; other languages are excluded from the SSI (~6.5% of relevant posts)
    SOCIAL_ALLOWED_LANGUAGES: List[str] = ["en"]
    SOCIAL_EXCLUDE_SPAM: bool = True  # Drop stock-promo bot posts (group invites, paid signals, hashtag campaigns)
    NEWS_MIN_RELEVANCE: float = 0.40
    # SSI baseline: X polarity is measured against the ticker's own trailing norm (excluding the lookback window)
    SOCIAL_BASELINE_DAYS: int = 14
    SOCIAL_BASELINE_PRIOR_WEIGHT: float = 10.0  # Pseudo-weight (~10-15 posts) shrinking thin baselines towards neutral
    SOCIAL_BASELINE_MIN_DAYS: float = 3.0       # History needed before mention_volume_ratio is reported
    SOCIAL_ATTENTION_SPIKE_RATIO: float = 2.0   # Mentions >= 2x the ticker's normal daily rate -> ATTENTION_SPIKE alert
    ENGAGEMENT_SCALE_DIVISOR: float = 10.0  # Scales log1p engagement: ln(1 + ~22,000) ≈ 10.0 maps high engagement to ~2.0x weight
    
    # Prediction Market (Polymarket) Settings
    POLYMARKET_ENABLED: bool = True
    POLYMARKET_PROVIDER: str = "polymarket"  # "polymarket" or "mock"
    POLYMARKET_API_URL: str = "https://gamma-api.polymarket.com"
    POLYMARKET_MIN_QUALITY: float = 30.0  # Quality threshold below which weight becomes 0
    POLYMARKET_LOOKBACK_HOURS: int = 24

    # News Provider
    NEWS_PROVIDER: str = "rss"  # "rss" or "mock"
    
    # Sentiment Model
    SENTIMENT_MODEL: str = "heuristic"  # News model: "heuristic" or "ProsusAI/finbert"
    USE_FINBERT: bool = False           # Enables local transformer models (news and X posts)
    # X/Twitter model. FinTwitBERT understands trading slang but is overconfident and bullish-biased, so only
    # |P(bull) - P(bear)| >= 0.90 counts as an opinion (blind review of 137 tweets: opinion precision 64% vs 17%
    # for FinBERT, polarity flips 0.5% vs 2.8%). Revert with "ProsusAI/finbert" and 0.20.
    SOCIAL_SENTIMENT_MODEL: str = "StephanAkkerman/FinTwitBERT-sentiment"
    SOCIAL_SENTIMENT_THRESHOLD: float = 0.90
    
    # SMIE v2.2 Scoring Weights (Total 100%): sentiment pillars drive the index (80%), technicals frame it.
    # Before v2.2 momentum weighed 0.25 and explained ~58% of SMI movement while social explained ~4%.
    WEIGHT_SOCIAL: float = 0.35        # SSI (Social Sentiment)
    WEIGHT_PREDICTION: float = 0.15    # PMS (Prediction Market Score)
    WEIGHT_NEWS: float = 0.30          # News & Catalysts
    WEIGHT_MOMENTUM: float = 0.10      # Technical context: no momentum variant predicted forward returns on 2y of prices
    WEIGHT_FUNDAMENTALS: float = 0.10  # Fundamentals
    WEIGHT_RISK: float = 0.0           # Decoupled from directional SMI (used as Capital Preservation Gate)
    
    # Dynamic Backtesting Weight Feedback (Closed-Loop Optimization)
    ENABLE_DYNAMIC_WEIGHT_FEEDBACK: bool = False
    DYNAMIC_WEIGHT_MIN_TRADES: int = 30
    DYNAMIC_WEIGHT_PRED_MIN: float = 0.05
    DYNAMIC_WEIGHT_PRED_MAX: float = 0.25
    
    # Signal thresholds: bands mirrored around 50.0. Bullish bands use >=, bearish bands use <=.
    #   STRONG BUY >= 85 | BUY [70, 85) | WATCH [55, 70) | HOLD (45, 55) | CAUTION (30, 45] | AVOID (15, 30] | STRONG AVOID <= 15
    THRESHOLD_STRONG_BUY: float = 85.0    # SMI >= 85.0 (+35 over 50.0)
    THRESHOLD_BUY: float = 70.0           # SMI >= 70.0 (+20 over 50.0)
    THRESHOLD_WATCH: float = 55.0         # SMI >= 55.0 (+5 over 50.0)
    THRESHOLD_HOLD: float = 45.0          # SMI <= 45.0 leaves HOLD for CAUTION (-5 under 50.0)
    THRESHOLD_AVOID: float = 30.0         # SMI <= 30.0 (-20 under 50.0, mirror of BUY)
    THRESHOLD_STRONG_AVOID: float = 15.0  # SMI <= 15.0 (-35 under 50.0, mirror of STRONG BUY)
    
    # Divergence Engine thresholds
    DIVERGENCE_EARLY_REVERSAL_DELTA: float = 15.0  # 24h probability change threshold (+/- 15 pp)
    
    # Prediction Market Score (PMS) Calibration
    PMS_WEIGHT_MOMENTUM: float = 0.60       # Probability Momentum (24h) weight (real-time smart money alpha)
    PMS_WEIGHT_LEVEL: float = 0.40          # Calibrated probability level weight
    PMS_DEFAULT_BASE_RATE: float = 0.20     # Calibrated base-rate anchor for aerospace innovation milestones
    
    # Strategy & Volume Thresholds (Option A - Institutional Quality)
    VOLUME_RATIO_INSTITUTIONAL_BUY: float = 1.2  # +20% volume threshold for institutional confirmation
    VOLUME_RATIO_MIN_CONFIRMATION: float = 1.0   # Baseline 20-period average volume
    VOLUME_RATIO_WEAKNESS: float = 0.8           # -20% volume threshold indicating lack of conviction
    CLOSE_POSITION_MIN_BULLISH: float = 0.60     # Top third close for bullish candle control
    ATR_NORMALIZED_K: float = 0.08               # Scale-invariant volatility multiplier (8% of ATR)
    
    # Scheduler
    ENABLE_SCHEDULER: bool = False
    JOB_INTERVAL_MINUTES: int = 60

    # API Security
    API_SECRET_KEY: Optional[str] = None  # Optional API Key for protected endpoints (POST /api/jobs/run)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
