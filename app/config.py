import os
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TickerConfig(BaseModel):
    symbol: str
    name: str
    aliases: List[str]
    sector: str = "Space Technology"
    is_private_or_test: bool = False


# Core initial space stocks specified for SMIE v2.0
INITIAL_TICKERS = [
    TickerConfig(
        symbol="ASTS",
        name="AST SpaceMobile",
        aliases=["$ASTS", "AST SpaceMobile", "ASTSpaceMobile", "ASTS_SpaceMobile", "BlueBird"],
        sector="Direct-to-Cell / Satellite Telecom"
    ),
    TickerConfig(
        symbol="RKLB",
        name="Rocket Lab",
        aliases=["$RKLB", "Rocket Lab", "RocketLab", "Neutron rocket", "Electron rocket"],
        sector="Launch Vehicles & Space Systems"
    ),
    TickerConfig(
        symbol="SATL",
        name="Satellogic",
        aliases=["$SATL", "Satellogic", "Aleph-1"],
        sector="Geospatial & Earth Observation"
    ),
    TickerConfig(
        symbol="SPCE",
        name="Virgin Galactic",
        aliases=["$SPCE", "Virgin Galactic", "VirginGalactic", "VSS Unity", "Delta Class"],
        sector="Commercial Spaceflight & Tourism"
    ),
    TickerConfig(
        symbol="SPCX",
        name="SpaceX / Space ETF",
        aliases=["$SPCX", "SpaceX", "Space X", "Starship", "Starlink", "Procure Space ETF"],
        sector="Space ETF & Sector Proxy",
        is_private_or_test=False
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
    
    # X / Social Provider Settings
    X_PROVIDER: str = "mock"  # "mock" or "twikit"
    X_AUTH_INFO_1: str = ""
    X_AUTH_INFO_2: str = ""
    X_PASSWORD: str = ""
    X_COOKIES_FILE: str = "data/x_cookies.json"
    
    # Social Collector Params
    SOCIAL_LOOKBACK_HOURS: int = 24
    SOCIAL_MAX_POSTS_PER_TICKER: int = 100
    SOCIAL_MIN_RELEVANCE: float = 0.40
    ENGAGEMENT_SCALE_DIVISOR: float = 10.0  # Scales log1p engagement: ln(1 + ~22,000) ≈ 10.0 maps high engagement to ~2.0x weight
    
    # Prediction Market (Polymarket) Settings
    POLYMARKET_ENABLED: bool = True
    POLYMARKET_PROVIDER: str = "mock"  # "mock" or "polymarket"
    POLYMARKET_API_URL: str = "https://gamma-api.polymarket.com"
    POLYMARKET_MIN_QUALITY: float = 30.0  # Quality threshold below which weight becomes 0
    POLYMARKET_LOOKBACK_HOURS: int = 24
    
    # Sentiment Model
    SENTIMENT_MODEL: str = "heuristic"  # "heuristic" or "ProsusAI/finbert"
    USE_FINBERT: bool = False
    
    # SMIE v2.0 Scoring Weights (Total 100%)
    WEIGHT_SOCIAL: float = 0.30        # SSI (Social Sentiment)
    WEIGHT_PREDICTION: float = 0.15    # PMS (Prediction Market Score)
    WEIGHT_NEWS: float = 0.20          # News & Catalysts
    WEIGHT_MOMENTUM: float = 0.20      # Technical Market Momentum
    WEIGHT_FUNDAMENTALS: float = 0.10  # Fundamentals
    WEIGHT_RISK: float = 0.05          # Risk / Safety
    
    # Dynamic Backtesting Weight Feedback (Closed-Loop Optimization)
    ENABLE_DYNAMIC_WEIGHT_FEEDBACK: bool = False
    DYNAMIC_WEIGHT_MIN_TRADES: int = 30
    DYNAMIC_WEIGHT_PRED_MIN: float = 0.05
    DYNAMIC_WEIGHT_PRED_MAX: float = 0.25
    
    # Signal thresholds
    THRESHOLD_STRONG_BUY: float = 85.0
    THRESHOLD_BUY: float = 75.0
    THRESHOLD_WATCH: float = 65.0
    THRESHOLD_HOLD: float = 50.0
    THRESHOLD_AVOID: float = 35.0
    
    # Divergence Engine thresholds
    DIVERGENCE_EARLY_REVERSAL_DELTA: float = 15.0  # 24h probability change threshold (+/- 15 pp)
    
    # Scheduler
    ENABLE_SCHEDULER: bool = False
    JOB_INTERVAL_MINUTES: int = 60

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
