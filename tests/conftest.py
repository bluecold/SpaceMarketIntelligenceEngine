import os
import pytest

# 1. Force testing environment before importing application modules
os.environ["ENVIRONMENT"] = "testing"

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEST_DATA_DIR = os.path.join(_ROOT_DIR, "data")
os.makedirs(_TEST_DATA_DIR, exist_ok=True)
_TEST_DB_PATH = os.path.join(_TEST_DATA_DIR, "test_space_sentiment.db")
_TEST_DB_URL = f"sqlite:///{_TEST_DB_PATH.replace(os.sep, '/')}"

from app.config import settings
from app.database.connection import rebind_engine, engine, init_db, SessionLocal
from app.database.repository import ensure_tickers_seeded

# 2. Configure mock providers and disable background scheduler
settings.ENVIRONMENT = "testing"
settings.DATABASE_URL = _TEST_DB_URL
settings.ALLOW_MOCK_FALLBACK = True
settings.X_PROVIDER = "mock"
settings.NEWS_PROVIDER = "mock"
settings.POLYMARKET_PROVIDER = "mock"
settings.ENABLE_SCHEDULER = False

# 3. Explicitly rebind database engine to dedicated test DB
rebind_engine(_TEST_DB_URL)

# 4. Strict Production Protection Guard
assert "test_space_sentiment.db" in str(engine.url) or "space_sentiment.db" not in str(engine.url), (
    f"SECURITY VIOLATION: Test suite attempted to run against production database ({engine.url})!"
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_session():
    """Session-level fixture: initialize test database and remove test artifacts on teardown."""
    # Pre-clean stale test SQLite files if any exist from previous runs
    for p in [_TEST_DB_PATH, _TEST_DB_PATH + "-wal", _TEST_DB_PATH + "-shm", _TEST_DB_PATH + "-journal"]:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    rebind_engine(_TEST_DB_URL)
    init_db()

    db = SessionLocal()
    try:
        ensure_tickers_seeded(db)
    finally:
        db.close()

    yield

    # Clean up test SQLite database files
    try:
        if os.path.exists(_TEST_DB_PATH):
            os.remove(_TEST_DB_PATH)
        for ext in ["-wal", "-shm", "-journal"]:
            wal_f = _TEST_DB_PATH + ext
            if os.path.exists(wal_f):
                os.remove(wal_f)
    except Exception:
        pass


@pytest.fixture(autouse=True)
def ensure_test_database_seeded():
    """Per-test fixture ensuring database schema is initialized and seeded for test cases."""
    init_db()
    db = SessionLocal()
    try:
        ensure_tickers_seeded(db)
    finally:
        db.close()

