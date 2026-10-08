import os
import logging
from sqlite3 import Connection as SQLiteConnection
from typing import Annotated
from fastapi import Depends
from sqlalchemy import create_engine, event, text, inspect
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from app.config import settings

logger = logging.getLogger(__name__)

# Ensure data directory exists
os.makedirs("data", exist_ok=True)

Base = declarative_base()


def resolve_database_url(url: str = None) -> str:
    target_url = url or settings.DATABASE_URL
    env = os.environ.get("ENVIRONMENT", getattr(settings, "ENVIRONMENT", "development")).lower()

    # Explicit Production Isolation: If in testing mode and pointing to production db, redirect to test db
    if env == "testing":
        if target_url == "sqlite:///./data/space_sentiment.db" or target_url.endswith("/space_sentiment.db") or target_url.endswith("\\space_sentiment.db"):
            logger.warning("[TEST ISOLATION] Redirecting test execution from production database to isolated test DB (sqlite:///./data/test_space_sentiment.db)")
            return "sqlite:///./data/test_space_sentiment.db"
    return target_url


def _create_engine_for_url(target_url: str):
    if target_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30.0}
    else:
        connect_args = {}

    new_engine = create_engine(
        target_url,
        connect_args=connect_args,
        echo=False,
        pool_pre_ping=True
    )

    if target_url.startswith("sqlite"):
        @event.listens_for(new_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            if isinstance(dbapi_connection, SQLiteConnection):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL;")
                cursor.execute("PRAGMA synchronous=NORMAL;")
                cursor.execute("PRAGMA foreign_keys=ON;")
                cursor.close()

    return new_engine


db_url = resolve_database_url()
engine = _create_engine_for_url(db_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def rebind_engine(custom_url: str):
    """Dynamically rebinds engine and SessionLocal to a new database URL (e.g. for testing isolation)."""
    global engine, SessionLocal, db_url
    db_url = custom_url
    engine = _create_engine_for_url(custom_url)
    SessionLocal.configure(bind=engine)
    logger.info(f"Database engine re-bound to: {custom_url}")
    return engine


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def init_db(target_engine=None):
    """Create all database tables and perform auto-migrations for missing columns."""
    active_engine = target_engine or engine

    # Import models so that Base.metadata knows about all tables
    import app.database.models  # noqa: F401

    Base.metadata.create_all(bind=active_engine)

    # SQLite column auto-migrations with schema introspection and precise error logging
    with active_engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())

        columns_to_check = [
            ("tickers", "sector", "VARCHAR(100) DEFAULT 'Space Technology'"),
            ("tickers", "is_private_or_test", "BOOLEAN DEFAULT 0"),
            ("social_posts", "catalyst", "VARCHAR(50)"),
            ("social_posts", "catalyst_direction", "VARCHAR(20)"),
            ("social_posts", "catalyst_importance", "VARCHAR(20) DEFAULT 'MEDIUM'"),
            ("social_posts", "source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("social_posts", "lang", "VARCHAR(10)"),
            ("social_posts", "sentiment_model", "VARCHAR(80)"),
            ("news_items", "catalyst", "VARCHAR(50)"),
            ("news_items", "catalyst_direction", "VARCHAR(20)"),
            ("news_items", "catalyst_importance", "VARCHAR(20) DEFAULT 'MEDIUM'"),
            ("prediction_markets", "event_key", "VARCHAR(100)"),
            ("prediction_markets", "clob_token_id", "VARCHAR(128)"),
            ("prediction_markets", "condition_id", "VARCHAR(128)"),
            ("prediction_markets", "polarity", "INTEGER DEFAULT 1"),
            ("prediction_markets", "baseline_probability", "FLOAT"),
            ("prediction_markets", "url", "VARCHAR(500)"),
            ("prediction_markets", "source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("market_snapshots", "technical_score", "FLOAT"),
            ("market_snapshots", "atr", "FLOAT"),
            ("market_snapshots", "volume_ratio", "FLOAT"),
            ("market_snapshots", "volume_ma20", "FLOAT"),
            ("market_snapshots", "observed_at", "DATETIME"),
            ("market_snapshots", "candle_date", "VARCHAR(20)"),
            ("market_snapshots", "market_session", "VARCHAR(20)"),
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
            ("ssi_snapshots", "prediction_quality", "FLOAT DEFAULT 50.0"),
            ("ssi_snapshots", "volume", "FLOAT"),
            ("ssi_snapshots", "post_count", "INTEGER"),
            ("ssi_snapshots", "social_polarity_raw", "FLOAT"),
            ("ssi_snapshots", "social_baseline", "FLOAT"),
            ("ssi_snapshots", "mention_volume_ratio", "FLOAT"),
            ("ssi_snapshots", "raw_post_count", "INTEGER"),
            ("ssi_snapshots", "relevant_post_count", "INTEGER"),
            ("ssi_snapshots", "unique_post_count", "INTEGER"),
            ("ssi_snapshots", "author_count", "INTEGER"),
            ("ssi_snapshots", "news_count", "INTEGER"),
            ("ssi_snapshots", "prediction_count", "INTEGER"),
            ("ssi_snapshots", "data_source", "VARCHAR(30) DEFAULT 'LIVE'"),
            ("ssi_snapshots", "social_source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("ssi_snapshots", "prediction_source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("ssi_snapshots", "news_source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("ssi_snapshots", "market_source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("ssi_snapshots", "rsi14", "FLOAT"),
            ("ssi_snapshots", "market_status", "VARCHAR(30) DEFAULT 'AVAILABLE'"),
            ("ssi_snapshots", "runway_months", "FLOAT"),
            ("ssi_snapshots", "fundamentals_data", "TEXT"),
            ("ssi_snapshots", "effective_weights", "TEXT"),
            ("ssi_snapshots", "rules_version", "VARCHAR(20) DEFAULT '2.0.0'"),
            ("divergences", "last_seen", "DATETIME"),
            ("alerts", "data_source", "VARCHAR(20) DEFAULT 'LIVE'"),
            ("job_runs", "heartbeat_at", "DATETIME"),
            ("job_runs", "source", "VARCHAR(50) DEFAULT 'API'"),
        ]

        # Clean up or recover orphaned _old tables from previous interrupted migrations
        for tbl in ["ssi_snapshots", "social_posts", "news_items"]:
            old_tbl = f"_{tbl}_old"
            if old_tbl in existing_tables:
                try:
                    if tbl in existing_tables:
                        count_target = conn.execute(text(f"SELECT COUNT(*) FROM {tbl};")).scalar() or 0
                        count_old = conn.execute(text(f"SELECT COUNT(*) FROM {old_tbl};")).scalar() or 0
                        if count_target == 0 and count_old > 0:
                            old_cols = [c["name"] for c in inspect(conn).get_columns(old_tbl)]
                            new_cols = [c["name"] for c in inspect(conn).get_columns(tbl)]
                            shared_cols = [c for c in new_cols if c in old_cols]
                            if shared_cols:
                                cols_str = ", ".join(shared_cols)
                                conn.execute(text(f"INSERT OR IGNORE INTO {tbl} ({cols_str}) SELECT {cols_str} FROM {old_tbl};"))
                    conn.execute(text(f"DROP TABLE IF EXISTS {old_tbl};"))
                    conn.commit()
                except Exception as rec_err:
                    logger.warning(f"Error cleaning up orphaned {old_tbl}: {rec_err}")

        def _has_single_column_unique(table_name: str, target_col: str) -> bool:
            try:
                idx_list = conn.execute(text(f"PRAGMA index_list({table_name});")).fetchall()
                for idx_row in idx_list:
                    is_uniq = bool(idx_row[2])
                    idx_name = str(idx_row[1])
                    if is_uniq:
                        cols = [r[2] for r in conn.execute(text(f"PRAGMA index_info('{idx_name}');")).fetchall()]
                        if cols == [target_col]:
                            return True
            except Exception:
                pass

            try:
                uniques = inspector.get_unique_constraints(table_name)
                indexes = inspector.get_indexes(table_name)
                for u in uniques:
                    if u.get("column_names") == [target_col]:
                        return True
                for idx in indexes:
                    if idx.get("column_names") == [target_col] and bool(idx.get("unique")):
                        return True
            except Exception:
                pass
            return False

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
                    conn.execute(text("DROP TABLE IF EXISTS _ssi_snapshots_old;"))
                    for idx in inspector.get_indexes("ssi_snapshots"):
                        idx_name = idx.get("name")
                        if idx_name and not idx_name.startswith("sqlite_autoindex_"):
                            conn.execute(text(f"DROP INDEX IF EXISTS {idx_name};"))
                    for uq in inspector.get_unique_constraints("ssi_snapshots"):
                        uq_name = uq.get("name")
                        if uq_name and not uq_name.startswith("sqlite_autoindex_"):
                            conn.execute(text(f"DROP INDEX IF EXISTS {uq_name};"))

                    conn.execute(text("ALTER TABLE ssi_snapshots RENAME TO _ssi_snapshots_old;"))
                    Base.metadata.tables["ssi_snapshots"].create(conn)
                    old_col_names = [c["name"] for c in inspect(conn).get_columns("_ssi_snapshots_old")]
                    new_col_names = [c["name"] for c in inspect(conn).get_columns("ssi_snapshots")]
                    shared_cols = [c for c in new_col_names if c in old_col_names]
                    cols_str = ", ".join(shared_cols)
                    conn.execute(text(f"INSERT OR IGNORE INTO ssi_snapshots ({cols_str}) SELECT {cols_str} FROM _ssi_snapshots_old;"))
                    conn.execute(text("DROP TABLE _ssi_snapshots_old;"))
                    conn.commit()
                    logger.info("Successfully migrated ssi_snapshots table to nullable social_score/ssi schema.")
                except Exception as mig_err:
                    conn.rollback()
                    logger.error(f"Error during ssi_snapshots nullable migration: {mig_err}", exc_info=True)

        # Migrate social_posts if it has legacy single-column UNIQUE on tweet_id
        if "social_posts" in existing_tables:
            single_tweet_unique = _has_single_column_unique("social_posts", "tweet_id")
            if single_tweet_unique:
                logger.info("Migrating social_posts table to composite (tweet_id, ticker) unique schema...")
                try:
                    conn.execute(text("DROP TABLE IF EXISTS _social_posts_old;"))
                    for idx in inspector.get_indexes("social_posts"):
                        idx_name = idx.get("name")
                        if idx_name and not idx_name.startswith("sqlite_autoindex_"):
                            conn.execute(text(f"DROP INDEX IF EXISTS {idx_name};"))
                    for uq in inspector.get_unique_constraints("social_posts"):
                        uq_name = uq.get("name")
                        if uq_name and not uq_name.startswith("sqlite_autoindex_"):
                            conn.execute(text(f"DROP INDEX IF EXISTS {uq_name};"))

                    conn.execute(text("ALTER TABLE social_posts RENAME TO _social_posts_old;"))
                    Base.metadata.tables["social_posts"].create(conn)
                    new_cols = [c["name"] for c in inspect(conn).get_columns("social_posts")]
                    old_cols = [c["name"] for c in inspect(conn).get_columns("_social_posts_old")]
                    shared_cols = [c for c in new_cols if c in old_cols]
                    cols_str = ", ".join(shared_cols)
                    conn.execute(text(f"INSERT OR IGNORE INTO social_posts ({cols_str}) SELECT {cols_str} FROM _social_posts_old;"))
                    conn.execute(text("DROP TABLE _social_posts_old;"))
                    conn.commit()
                    logger.info("Successfully migrated social_posts table to composite (tweet_id, ticker) schema.")
                except Exception as mig_err:
                    conn.rollback()
                    logger.error(f"Error during social_posts migration: {mig_err}", exc_info=True)

        # Migrate news_items if it has legacy single-column UNIQUE on url
        if "news_items" in existing_tables:
            single_url_unique = _has_single_column_unique("news_items", "url")
            if single_url_unique:
                logger.info("Migrating news_items table to composite (url, ticker) unique schema...")
                try:
                    conn.execute(text("DROP TABLE IF EXISTS _news_items_old;"))
                    for idx in inspector.get_indexes("news_items"):
                        idx_name = idx.get("name")
                        if idx_name and not idx_name.startswith("sqlite_autoindex_"):
                            conn.execute(text(f"DROP INDEX IF EXISTS {idx_name};"))
                    for uq in inspector.get_unique_constraints("news_items"):
                        uq_name = uq.get("name")
                        if uq_name and not uq_name.startswith("sqlite_autoindex_"):
                            conn.execute(text(f"DROP INDEX IF EXISTS {uq_name};"))

                    conn.execute(text("ALTER TABLE news_items RENAME TO _news_items_old;"))
                    Base.metadata.tables["news_items"].create(conn)
                    new_cols = [c["name"] for c in inspect(conn).get_columns("news_items")]
                    old_cols = [c["name"] for c in inspect(conn).get_columns("_news_items_old")]
                    shared_cols = [c for c in new_cols if c in old_cols]
                    cols_str = ", ".join(shared_cols)
                    conn.execute(text(f"INSERT OR IGNORE INTO news_items ({cols_str}) SELECT {cols_str} FROM _news_items_old;"))
                    conn.execute(text("DROP TABLE _news_items_old;"))
                    conn.commit()
                    logger.info("Successfully migrated news_items table to composite (url, ticker) schema.")
                except Exception as mig_err:
                    conn.rollback()
                    logger.error(f"Error during news_items migration: {mig_err}", exc_info=True)

        # Migrate prediction_market_snapshots to support ON DELETE CASCADE if created under older schema
        if "prediction_market_snapshots" in existing_tables:
            snap_sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='prediction_market_snapshots';")).scalar() or ""
            if "ON DELETE CASCADE" not in snap_sql.upper():
                logger.info("Migrating prediction_market_snapshots table to ON DELETE CASCADE schema...")
                try:
                    conn.execute(text("DROP TABLE IF EXISTS _prediction_market_snapshots_old;"))
                    for idx in inspector.get_indexes("prediction_market_snapshots"):
                        idx_name = idx.get("name")
                        if idx_name and not idx_name.startswith("sqlite_autoindex_"):
                            conn.execute(text(f"DROP INDEX IF EXISTS {idx_name};"))

                    conn.execute(text("ALTER TABLE prediction_market_snapshots RENAME TO _prediction_market_snapshots_old;"))
                    Base.metadata.tables["prediction_market_snapshots"].create(conn)
                    new_cols = [c["name"] for c in inspect(conn).get_columns("prediction_market_snapshots")]
                    old_cols = [c["name"] for c in inspect(conn).get_columns("_prediction_market_snapshots_old")]
                    shared_cols = [c for c in new_cols if c in old_cols]
                    cols_str = ", ".join(shared_cols)
                    conn.execute(text(f"INSERT OR IGNORE INTO prediction_market_snapshots ({cols_str}) SELECT {cols_str} FROM _prediction_market_snapshots_old;"))
                    conn.execute(text("DROP TABLE _prediction_market_snapshots_old;"))
                    conn.commit()
                    logger.info("Successfully migrated prediction_market_snapshots table to ON DELETE CASCADE schema.")
                except Exception as mig_err:
                    conn.rollback()
                    logger.error(f"Error during prediction_market_snapshots cascade migration: {mig_err}", exc_info=True)

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

        # Ensure composite unique indexes exist on social_posts and news_items for multi-ticker documents
        if "social_posts" in existing_tables:
            try:
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_social_posts_tweet_ticker ON social_posts (tweet_id, ticker);"))
                conn.commit()
            except Exception as idx_err:
                logger.debug(f"Note on social_posts composite index: {idx_err}")

        if "news_items" in existing_tables:
            try:
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_news_items_url_ticker ON news_items (url, ticker);"))
                conn.commit()
            except Exception as idx_err:
                logger.debug(f"Note on news_items composite index: {idx_err}")

        # Ensure partial unique index on job_runs to guarantee atomic mutual exclusion
        if "job_runs" in existing_tables:
            try:
                conn.execute(text("""
                    UPDATE job_runs 
                    SET status = 'ERROR', error_message = 'Recovered during startup schema index migration'
                    WHERE status = 'RUNNING' AND id NOT IN (
                        SELECT id FROM job_runs WHERE status = 'RUNNING' ORDER BY started_at DESC LIMIT 1
                    );
                """))
                conn.commit()
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_job_runs_single_running ON job_runs (job_name, status) WHERE status = 'RUNNING';"))
                conn.commit()
            except Exception as idx_err:
                logger.debug(f"Note on job_runs partial index: {idx_err}")

        # One-time migration: Purge legacy orphaned snapshots and historical mock data atomically
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(100) PRIMARY KEY,
                    applied_at DATETIME
                );
            """))
            conn.commit()

            migrated = conn.execute(text("SELECT 1 FROM schema_migrations WHERE version = 'v2_mock_data_and_orphan_purge';")).scalar()
            if not migrated:
                # 1. Clean any existing orphaned snapshots whose parent prediction market was removed
                conn.execute(text("DELETE FROM prediction_market_snapshots WHERE market_id NOT IN (SELECT id FROM prediction_markets);"))
                
                # 2. If strict governance is active, delete synthetic mock data atomically (children first, then parents)
                if not getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                    conn.execute(text("DELETE FROM prediction_market_snapshots WHERE market_id IN (SELECT id FROM prediction_markets WHERE external_id LIKE 'mock_%' OR external_id LIKE 'poly-%-2026' OR source = 'MOCK');"))
                    conn.execute(text("DELETE FROM prediction_markets WHERE external_id LIKE 'mock_%' OR external_id LIKE 'poly-%-2026' OR source = 'MOCK';"))
                    conn.execute(text("DELETE FROM social_posts WHERE tweet_id LIKE 'mock_%' OR source = 'MOCK';"))
                    conn.execute(text("DELETE FROM news_items WHERE url LIKE 'mock_%' OR source = 'Mock News' OR source = 'MOCK';"))
                
                conn.execute(text("INSERT INTO schema_migrations (version, applied_at) VALUES ('v2_mock_data_and_orphan_purge', CURRENT_TIMESTAMP);"))
                conn.commit()
                logger.info("Successfully executed one-time schema migration 'v2_mock_data_and_orphan_purge'.")
        except Exception as purge_err:
            logger.warning(f"Note on schema migration v2_mock_data_and_orphan_purge: {purge_err}")
