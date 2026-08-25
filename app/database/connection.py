import os
from sqlite3 import Connection as SQLiteConnection
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

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

    # SQLite column auto-migrations for backward compatibility
    with engine.connect() as conn:
        columns_to_check = [
            ("social_posts", "catalyst_importance", "VARCHAR(20) DEFAULT 'MEDIUM'"),
            ("ssi_snapshots", "news_score", "FLOAT"),
            ("ssi_snapshots", "momentum_score", "FLOAT"),
            ("ssi_snapshots", "risk_score", "FLOAT"),
            ("ssi_snapshots", "prediction_score", "FLOAT"),
            ("ssi_snapshots", "fundamental_score", "FLOAT"),
            ("ssi_snapshots", "smi", "FLOAT"),
            ("ssi_snapshots", "base_signal", "VARCHAR(30)"),
            ("ssi_snapshots", "signal_modifier", "VARCHAR(50)"),
            ("ssi_snapshots", "data_quality", "FLOAT DEFAULT 100.0"),
            ("ssi_snapshots", "volume", "FLOAT"),
            ("prediction_markets", "event_key", "VARCHAR(100)"),
        ]
        for table, col, col_type in columns_to_check:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};"))
                conn.commit()
            except Exception:
                pass  # Column already exists
