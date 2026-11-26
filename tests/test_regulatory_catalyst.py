"""REGULATORY_APPROVAL catalyst (v2.2.4): FCC licences and authorizations, denials, and what is not a decision."""
import pytest

from app.sentiment.weighting import calculate_news_score, detect_catalysts, reconcile_sentiment_with_catalyst


def _reg(text, ticker):
    hits = [c for c in detect_catalysts(text, ticker=ticker) if c["category"] == "REGULATORY_APPROVAL"]
    return hits[0]["direction"] if hits else None


@pytest.mark.parametrize("ticker, text", [
    ("SPCX", "SpaceX stock pares losses following FCC approval for data centers in space - Yahoo Finance"),
    ("SPCX", "SpaceX Stock Rebounds as FCC Approves Starmind Data Center Satellites - Benzinga"),
    ("SPCX", "FCC approves Starlink Gen2 upgrade"),
    ("ASTS", "AST SpaceMobile receives FCC approval for commercial service"),
    ("ASTS", "AST SpaceMobile wins FCC nod for SCS"),
    ("ASTS", "FCC grants AST SpaceMobile authority to launch"),
    ("ASTS", "AST SpaceMobile Stock Gets FCC Approval for Direct to Device Service - Yahoo Finance"),
    ("ASTS", "Approval from the FCC lifts AST SpaceMobile"),
    ("ASTS", "AST SpaceMobile receives FCC approval after 2024 application"),
])
def test_granted_approval_is_bullish(ticker, text):
    assert _reg(text, ticker) == "BULLISH"


@pytest.mark.parametrize("ticker, text", [
    ("SPCX", "FCC denies SpaceX request for more Starlink satellites"),
    ("SATL", "FCC rejects Satellogic license"),
    ("ASTS", "FCC denies AST SpaceMobile waiver"),
])
def test_denial_is_bearish(ticker, text):
    assert _reg(text, ticker) == "BEARISH"


@pytest.mark.parametrize("ticker, text", [
    ("ASTS", "AST SpaceMobile seeks FCC approval for 248 satellites"),           # sought
    ("ASTS", "Investors await FCC decision on AST SpaceMobile"),                 # awaited
    ("ASTS", "AST SpaceMobile files for FCC approval"),                          # requested
    ("ASTS", "FCC chair says agency will review spectrum rules"),                # no decision
    ("ASTS", "ASTS Stock Slips Overnight: Viasat Urges FCC To Reject AST SpaceMobile's Overseas Spectrum"),
    ("RKLB", "AST SpaceMobile Partner Challenges Iridium Deal - Claims Rival Uses FCC To Block Competitors"),
    ("ASTS", "ASTS Stock Slips Overnight As FCC Clears Amazon's $11.5B Globalstar Deal"),  # another company
    ("ASTS", "FCC approves Starlink Gen2 upgrade"),                              # SpaceX's, not ASTS's
])
def test_not_a_decision_for_this_ticker(ticker, text):
    assert _reg(text, ticker) is None


def test_fcc_license_no_longer_counts_as_satellite_deployment():
    cats = {c["category"] for c in detect_catalysts("AST SpaceMobile secures FCC license for BlueBird", ticker="ASTS")}
    assert "REGULATORY_APPROVAL" in cats
    assert "SATELLITE_DEPLOYMENT" not in cats


def test_reconcile_corrects_finbert_on_the_25_11_headlines():
    """FinBERT read 'pares losses' as bearish (-0.78) and 'Rebounds as FCC Approves' as neutral."""
    pares = detect_catalysts("SpaceX stock pares losses following FCC approval for data centers in space", "SPCX")[0]
    assert reconcile_sentiment_with_catalyst(-0.78, "BEARISH", 0.82, pares)[1] == "NEUTRAL"
    rebound = detect_catalysts("SpaceX Stock Rebounds as FCC Approves Starmind Data Center Satellites", "SPCX")[0]
    score, label, _ = reconcile_sentiment_with_catalyst(-0.16, "NEUTRAL", 0.51, rebound)
    assert label == "BULLISH" and score > 0


def test_recap_with_regulatory_catalyst_keeps_direction():
    """The price-recap filter drops headlines that only restate the move, unless they also name a catalyst."""
    from types import SimpleNamespace
    from datetime import datetime, timezone
    now = datetime(2026, 11, 25, 20, 0, tzinfo=timezone.utc)
    item = SimpleNamespace(title="SpaceX Stock Rebounds Wednesday as FCC Approves Starmind Satellites",
                           sentiment_label="BULLISH", sentiment_score=0.4, sentiment_confidence=0.7,
                           relevance_score=0.85, catalyst="REGULATORY_APPROVAL", catalyst_importance="HIGH",
                           published_at=now, url="u1", source="Benzinga")
    res = calculate_news_score([item], analysis_timestamp=now)
    assert res.get("price_recap_news_count", 0) == 0
