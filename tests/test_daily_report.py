from app.reports.daily_report import generate_daily_report
from app.database.connection import SessionLocal, init_db


def test_generate_daily_report_structure():
    init_db()
    db = SessionLocal()
    try:
        report = generate_daily_report(db)
        
        assert "date" in report
        assert "sector_sentiment" in report
        assert "average_smi" in report
        assert "top_bullish" in report
        assert "top_bearish" in report
        assert "ticker_summaries" in report
        assert "markdown_report" in report
        assert len(report["ticker_summaries"]) >= 5
        
        # Check text report structure
        text = report["markdown_report"]
        assert "SPACE MARKET INTELLIGENCE DAILY REPORT" in text
        assert "SECTOR REGIME:" in text
        assert "ASSET SIGNALS & MULTIVARIATE BREAKDOWN:" in text
    finally:
        db.close()
