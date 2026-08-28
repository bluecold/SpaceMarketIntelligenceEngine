import os
import logging
from sqlite3 import Connection as SQLiteConnection
from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

logger = logging.getLogger(__name__)

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

# Parse database URL
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 30.0}
else:
    connect_args = {}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    echo=False,
    pool_pre_ping=True
)


# Enable SQLite WAL (Write-Ahead Logging) mode for concurrent read/write safety
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, SQLiteConnection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all database tables and perform auto-migrations for missing columns."""
    # Import models so that Base.metadata knows about all tables
    import app.database.models  # noqa: F401
    
    Base.metadata.create_all(bind=engine)

    # SQLite column auto-migrations with schema introspection and precise error logging
    with engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        columns_to_check = [
            ("tickers", "sector", "VARCHAR(100) DEFAULT 'Space Technology'"),
            ("tickers", "is_private_or_test", "BOOLEAN DEFAULT 0"),
            ("social_posts", "catalyst", "VARCHAR(50)"),
            ("social_posts", "catalyst_direction", "VARCHAR(20)"),
            ("social_posts", "catalyst_importance", "VARCHAR(20) DEFAULT 'MEDIUM'"),
            ("social_posts", "source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("news_items", "catalyst", "VARCHAR(50)"),
            ("news_items", "catalyst_direction", "VARCHAR(20)"),
            ("news_items", "catalyst_importance", "VARCHAR(20) DEFAULT 'MEDIUM'"),
            ("prediction_markets", "event_key", "VARCHAR(100)"),
            ("prediction_markets", "polarity", "INTEGER DEFAULT 1"),
            ("prediction_markets", "url", "VARCHAR(500)"),
            ("prediction_markets", "source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("market_snapshots", "technical_score", "FLOAT"),
            ("market_snapshots", "atr", "FLOAT"),
            ("market_snapshots", "volume_ratio", "FLOAT"),
            ("market_snapshots", "volume_ma20", "FLOAT"),
            ("ssi_snapshots", "news_score", "FLOAT"),
            ("ssi_snapshots", "momentum_score", "FLOAT"),
            ("ssi_snapshots", "risk_score", "FLOAT"),
            ("ssi_snapshots", "prediction_score", "FLOAT"),
            ("ssi_snapshots", "fundamental_score", "FLOAT"),
            ("ssi_snapshots", "technical_score", "FLOAT"),
            ("ssi_snapshots", "smi", "FLOAT"),
            ("ssi_snapshots", "base_signal", "VARCHAR(30)"),
            ("ssi_snapshots", "signal_modifier", "VARCHAR(50)"),
            ("ssi_snapshots", "data_quality", "FLOAT DEFAULT 100.0"),
            ("ssi_snapshots", "volume", "FLOAT"),
            ("ssi_snapshots", "post_count", "INTEGER"),
            ("ssi_snapshots", "news_count", "INTEGER"),
            ("ssi_snapshots", "prediction_count", "INTEGER"),
            ("ssi_snapshots", "data_source", "VARCHAR(30) DEFAULT 'LIVE'"),
            ("ssi_snapshots", "social_source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("ssi_snapshots", "prediction_source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("ssi_snapshots", "news_source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("ssi_snapshots", "market_source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("divergences", "last_seen", "DATETIME"),
            ("alerts", "data_source", "VARCHAR(20) DEFAULT 'LIVE'"),
        ]

        # Relax NOT NULL constraint on ssi_snapshots.social_score and ssi if present from older schema
        if "ssi_snapshots" in existing_tables:
            cols = inspector.get_columns("ssi_snapshots")
            not_null_targets = [
                c["name"] for c in cols
                if c["name"] in ["social_score", "ssi"] and not c.get("nullable", True)
            ]
            if not_null_targets:
                logger.info("Migrating ssi_snapshots table to make social_score and ssi nullable...")
                try:
                    conn.execute(text("ALTER TABLE ssi_snapshots RENAME TO _ssi_snapshots_old;"))
                    # Recreate new table from Base.metadata
                    Base.metadata.tables["ssi_snapshots"].create(conn)
                    # Copy matching columns
                    old_col_names = [c["name"] for c in cols]
                    new_col_names = [c["name"] for c in inspect(conn).get_columns("ssi_snapshots")]
                    shared_cols = [c for c in old_col_names if c in new_col_names]
                    cols_str = ", ".join(shared_cols)
                    conn.execute(text(f"INSERT INTO ssi_snapshots ({cols_str}) SELECT {cols_str} FROM _ssi_snapshots_old;"))
                    conn.execute(text("DROP TABLE _ssi_snapshots_old;"))
                    conn.commit()
                    logger.info("Successfully migrated ssi_snapshots table to nullable social_score/ssi schema.")
                except Exception as mig_err:
                    logger.warning(f"Error during ssi_snapshots nullable migration: {mig_err}")

        for table, col, col_type in columns_to_check:
            if table not in existing_tables:
                logger.warning(f"Auto-migration skipped: Table '{table}' does not exist in database.")
                continue

            existing_cols = {c["name"] for c in inspector.get_columns(table)}
            if col not in existing_cols:
                try:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};"))
                    conn.commit()
                    logger.info(f"Auto-migrated database schema: added column '{col}' ({col_type}) to table '{table}'.")
                except Exception as e:
                    err_str = str(e).lower()
                    if "duplicate column name" in err_str:
                        # Benign race condition where column was concurrently added
                        pass
                    else:
                        logger.error(f"Critical auto-migration error while adding '{col}' to '{table}': {e}", exc_info=True)
                        raise

        # Purge legacy mock data if live strict governance (ALLOW_MOCK_FALLBACK=False) is enforced
        if not getattr(settings, "ALLOW_MOCK_FALLBACK", False):
            try:
                conn.execute(text("DELETE FROM social_posts WHERE tweet_id LIKE 'mock_%' OR source = 'MOCK';"))
                conn.execute(text("DELETE FROM news_items WHERE url LIKE 'mock_%' OR source = 'Mock News';"))
                conn.execute(text("DELETE FROM prediction_markets WHERE external_id LIKE 'mock_%' OR external_id LIKE 'poly-%-flight-2026';"))
                conn.commit()
                logger.info("Purged synthetic mock data from database under strict LIVE data governance.")
            except Exception as purge_err:
                logger.warning(f"Note on mock data purge: {purge_err}")
