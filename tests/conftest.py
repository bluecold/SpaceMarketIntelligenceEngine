import os
import pytest
from app.config import settings

# Force test configuration
os.environ["ENVIRONMENT"] = "testing"
settings.ALLOW_MOCK_FALLBACK = True

@pytest.fixture(autouse=True)
def ensure_test_database_seeded():
    """Ensure database schema is initialized and seeded for test cases."""
    from app.database.connection import init_db, SessionLocal
    from app.database.repository import ensure_tickers_seeded
    
    init_db()
    db = SessionLocal()
    try:
        ensure_tickers_seeded(db)
    finally:
        db.close()
