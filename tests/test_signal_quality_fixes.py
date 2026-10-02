from app.sentiment.classifier import HeuristicSentimentClassifier
from app.sentiment.weighting import detect_catalysts, reconcile_sentiment_with_catalyst
from app.scoring.signal import generate_signal_and_explanation


def _categories(text, ticker=None):
    return {(c["category"], c["direction"]) for c in detect_catalysts(text, ticker=ticker)}


def test_classifier_counts_nested_keywords_once():
    """
    Nested keywords must not double count:
    - 'cash burn' must not also count 'burn'
    - 'failed' acting as the negator of 'beat' must not also count as a bearish keyword
    A single bearish hit yields tanh(-0.5) = -0.462.
    """
    classifier = HeuristicSentimentClassifier()

    res_burn = classifier.analyze("$RKLB cash burn continues")
    assert res_burn.score == -0.462, f"Expected one bearish hit for 'cash burn', got {res_burn.score}"

    res_failed = classifier.analyze("Rocket Lab failed to beat estimates")
    assert res_failed.score == -0.462, f"Expected one bearish hit for 'failed to beat', got {res_failed.score}"

    res_short = classifier.analyze("Short selling keeps rising")
    assert res_short.score == -0.462, f"'short selling' must not also count 'selling', got {res_short.score}"


def test_classifier_short_squeeze_and_slang():
    """'short squeeze' and FinTwit slang are scored; decorative emojis are not."""
    classifier = HeuristicSentimentClassifier()

    assert classifier.analyze("$ASTS short squeeze incoming").label == "BULLISH"
    assert classifier.analyze("$ASTS LFG").label == "BULLISH"
    assert classifier.analyze("$SPCE bagholders everywhere").label == "BEARISH"

    # Rocket emojis are mostly decoration (watchlists, promos, literal launches): not a sentiment signal
    assert classifier.analyze("Today's watchlist \U0001F680 $SPCE $WMT").label == "NEUTRAL"


def test_classifier_offering_only_bearish_for_financing():
    """Bare 'offering' (products, seats, services) is neutral; financing offerings stay bearish."""
    classifier = HeuristicSentimentClassifier()

    res_product = classifier.analyze("Virgin Galactic is offering new seats for spaceflight")
    assert res_product.label == "NEUTRAL", f"Product offering must be NEUTRAL, got {res_product.label}"

    res_financing = classifier.analyze("AST SpaceMobile prices $500M public offering")
    assert res_financing.label == "BEARISH"


def test_classifier_explosions_literal_vs_figurative():
    """Literal explosions are bearish; figurative surges ('shares exploded higher') are not."""
    classifier = HeuristicSentimentClassifier()

    assert classifier.analyze("Starship explodes during test flight").label == "BEARISH"
    assert classifier.analyze("Shares exploded higher after the update").score >= 0.0
    assert classifier.analyze("Explosion of demand for direct to cell service").score >= 0.0


def test_catalyst_explodes_is_launch_failure_not_launch():
    """'Starship explodes' must be a CRITICAL LAUNCH_FAILURE and suppress the bullish LAUNCH catalyst."""
    cats = detect_catalysts("SpaceX Starship explodes during test flight", ticker="SPCX")
    names = [c["category"] for c in cats]
    assert "LAUNCH_FAILURE" in names
    assert "LAUNCH" not in names
    assert cats[0]["category"] == "LAUNCH_FAILURE" and cats[0]["importance"] == "CRITICAL"

    assert ("LAUNCH_FAILURE", "BEARISH") in _categories("Rocket Lab Electron blew up shortly after liftoff", "RKLB")
    assert ("LAUNCH_FAILURE", "BEARISH") not in _categories("Demand explodes for AST SpaceMobile service", "ASTS")


def test_catalyst_rivalry_requires_companies_and_award_context():
    """
    'X beats Y' only counts as a contract rivalry when both sides are known space companies
    and the text has agency/contract context.
    """
    assert _categories("Rocket Lab stock beats the street this week", "RKLB") == set()
    assert _categories("Rocket Lab beats the market in September", "RKLB") == set()

    cats = _categories("Rocket Lab beats SpaceX for SDA launch contract", "RKLB")
    assert ("GOVERNMENT_CONTRACT", "BULLISH") in cats

    cats_loser = _categories("Rocket Lab beats SpaceX for SDA launch contract", "SPCX")
    assert ("GOVERNMENT_CONTRACT", "BEARISH") in cats_loser

    # Selection without agency/contract context is not a government contract
    assert not any(c[0] == "GOVERNMENT_CONTRACT" for c in _categories("Retail traders pick Rocket Lab over SpaceX", "RKLB"))


def test_catalyst_generic_delay_requires_launch_context():
    """Corporate delays are not LAUNCH_DELAY; launch/flight delays still are."""
    assert not any(c[0] == "LAUNCH_DELAY" for c in _categories("Rocket Lab delays earnings report to next week", "RKLB"))
    assert not any(c[0] == "LAUNCH_DELAY" for c in _categories("AST SpaceMobile annual meeting postponed", "ASTS"))

    assert ("LAUNCH_DELAY", "BEARISH") in _categories("SpaceX delays Starship flight after inspection", "SPCX")
    assert ("LAUNCH_DELAY", "BEARISH") in _categories("Rocket Lab Neutron debut delayed to 2027", "RKLB")
    assert ("LAUNCH_DELAY", "BEARISH") in _categories("Rocket Lab suffers launch abort", "RKLB")


def test_catalyst_partnership_excludes_settlements_and_financing():
    """Generic 'agreement'/'partner' in settlement, financing or job-title context is not a partnership."""
    assert not any(c[0] == "PARTNERSHIP" for c in _categories("AST SpaceMobile signs agreement to settle lawsuit", "ASTS"))
    assert not any(c[0] == "PARTNERSHIP" for c in _categories("Rocket Lab enters credit agreement with banks", "RKLB"))
    assert not any(c[0] == "PARTNERSHIP" for c in _categories("Managing partner at fund discusses $ASTS", "ASTS"))

    assert ("PARTNERSHIP", "BULLISH") in _categories("AST SpaceMobile signs commercial agreement with Verizon", "ASTS")
    assert ("PARTNERSHIP", "BULLISH") in _categories("Satellogic announces strategic partnership", "SATL")


def test_catalyst_contract_loss_and_stock_crash_wording():
    """'NASA contract loss' is a bearish contract event; 'stock could crash' is not a launch failure."""
    cats = _categories("Rocket Lab stock may be undervalued despite NASA contract loss", "RKLB")
    assert ("GOVERNMENT_CONTRACT", "BEARISH") in cats
    assert ("GOVERNMENT_CONTRACT", "BULLISH") not in cats

    assert not any(c[0] == "LAUNCH_FAILURE" for c in _categories("3 reasons SpaceX stock could crash in Q4", "SPCX"))
    assert ("LAUNCH_FAILURE", "BEARISH") in _categories("Firefly rocket crashed into the ocean after launch", "SPCX")


def test_catalyst_cash_burn_is_not_capital_raise():
    """Ongoing cash burn is a fundamental risk, not a CAPITAL_RAISE event."""
    assert not any(c[0] == "CAPITAL_RAISE" for c in _categories("$RKLB cash burn continues", "RKLB"))
    assert ("CAPITAL_RAISE", "BEARISH") in _categories("AST SpaceMobile prices $500M convertible notes offering", "ASTS")


def test_reconcile_sentiment_with_catalyst():
    """
    - Neutral classifier + CRITICAL/HIGH catalyst -> catalyst prior (+/-0.60 / +/-0.40).
    - Opposite classifier -> average of classifier and prior.
    - Agreeing classifier, MEDIUM catalysts, generic LAUNCH and missing catalysts -> unchanged.
    """
    failure = {"category": "LAUNCH_FAILURE", "direction": "BEARISH", "importance": "CRITICAL"}
    raise_cat = {"category": "CAPITAL_RAISE", "direction": "BEARISH", "importance": "HIGH"}

    assert reconcile_sentiment_with_catalyst(0.0, "NEUTRAL", 0.95, failure) == (-0.6, "BEARISH", 0.8)
    assert reconcile_sentiment_with_catalyst(0.05, "NEUTRAL", 0.90, raise_cat) == (-0.4, "BEARISH", 0.7)

    score, label, conf = reconcile_sentiment_with_catalyst(0.5, "BULLISH", 0.9, failure)
    assert score == -0.05 and label == "NEUTRAL" and conf == 0.8

    assert reconcile_sentiment_with_catalyst(-0.7, "BEARISH", 0.9, failure) == (-0.7, "BEARISH", 0.9)

    medium = {"category": "TECHNICAL_MILESTONE", "direction": "BULLISH", "importance": "MEDIUM"}
    assert reconcile_sentiment_with_catalyst(0.0, "NEUTRAL", 0.7, medium) == (0.0, "NEUTRAL", 0.7)

    launch = {"category": "LAUNCH", "direction": "BULLISH", "importance": "HIGH"}
    assert reconcile_sentiment_with_catalyst(0.0, "NEUTRAL", 0.7, launch) == (0.0, "NEUTRAL", 0.7)

    assert reconcile_sentiment_with_catalyst(0.0, "NEUTRAL", 0.7, None) == (0.0, "NEUTRAL", 0.7)


def test_signal_catalyst_risk_gate():
    """A bearish CRITICAL event or confirmed capital raise caps BUY/STRONG BUY at WATCH (CATALYST RISK)."""
    indicators = {"price": 10.0, "status": "AVAILABLE", "rsi14": 55.0}

    res_clean = generate_signal_and_explanation(ticker="RKLB", smi=80.0, indicators=indicators)
    assert res_clean["base_signal"] == "BUY"

    res_failure = generate_signal_and_explanation(
        ticker="RKLB", smi=80.0, indicators=indicators,
        catalysts_found=[{"category": "LAUNCH_FAILURE", "direction": "BEARISH", "importance": "CRITICAL"}]
    )
    assert res_failure["base_signal"] == "WATCH"
    assert "CATALYST RISK" in res_failure["signal_modifier"]

    res_raise = generate_signal_and_explanation(
        ticker="ASTS", smi=90.0, indicators=indicators,
        catalysts_found=[{"category": "CAPITAL_RAISE", "direction": "BEARISH", "importance": "HIGH"}]
    )
    assert res_raise["base_signal"] == "WATCH"

    # Bullish CRITICAL catalysts and MEDIUM bearish ones do not trigger the gate
    res_bullish = generate_signal_and_explanation(
        ticker="RKLB", smi=80.0, indicators=indicators,
        catalysts_found=[
            {"category": "GOVERNMENT_CONTRACT", "direction": "BULLISH", "importance": "CRITICAL"},
            {"category": "ANALYST_DOWNGRADE", "direction": "BEARISH", "importance": "MEDIUM"},
        ]
    )
    assert res_bullish["base_signal"] == "BUY"
    assert res_bullish["signal_modifier"] is None


def test_signal_momentum_does_not_mix_ssi_into_smi():
    """When SMI is available, a zero SMI momentum must not be replaced by SSI momentum in alerts."""
    res = generate_signal_and_explanation(ticker="ASTS", smi=65.0, smi_mom_1d=0.0, ssi_mom_1d=9.0)
    alert_ids = [a["id"] for a in res["alerts"]]
    assert "ASTS:MOMENTUM:ACCELERATION" not in alert_ids

    # Without SMI, the SSI is the primary index, so its momentum applies
    res_ssi = generate_signal_and_explanation(ticker="ASTS", ssi=65.0, ssi_mom_1d=9.0)
    assert "ASTS:MOMENTUM:ACCELERATION" in [a["id"] for a in res_ssi["alerts"]]


def test_signal_bands_are_mirrored_around_50():
    """
    Bearish bands mirror bullish ones around 50 (bullish use >=, bearish use <=):
    STRONG BUY >= 85 | BUY >= 70 | WATCH >= 55 | HOLD (45, 55) | CAUTION <= 45 | AVOID <= 30 | STRONG AVOID <= 15
    """
    indicators = {"price": 10.0, "status": "AVAILABLE", "rsi14": 55.0}
    expected = [
        (85.0, "STRONG BUY"), (84.9, "BUY"), (70.0, "BUY"), (69.9, "WATCH"), (55.0, "WATCH"),
        (54.9, "HOLD"), (50.0, "HOLD"), (45.1, "HOLD"),
        (45.0, "CAUTION"), (30.1, "CAUTION"), (30.0, "AVOID"), (15.1, "AVOID"), (15.0, "STRONG AVOID"), (0.0, "STRONG AVOID"),
    ]
    for smi, band in expected:
        res = generate_signal_and_explanation(ticker="RKLB", smi=smi, indicators=indicators)
        assert res["base_signal"] == band, f"SMI {smi}: expected {band}, got {res['base_signal']}"

    # Mirror check: the distance from 50 that triggers each bullish band triggers its bearish twin
    for dist, bull, bear in [(5.0, "WATCH", "CAUTION"), (20.0, "BUY", "AVOID"), (35.0, "STRONG BUY", "STRONG AVOID")]:
        assert generate_signal_and_explanation(ticker="RKLB", smi=50.0 + dist, indicators=indicators)["base_signal"] == bull
        assert generate_signal_and_explanation(ticker="RKLB", smi=50.0 - dist, indicators=indicators)["base_signal"] == bear


def test_caution_bearish_alert_mirrors_watch_bullish():
    """CAUTION at SMI <= 40 emits an INFO alert, mirroring WATCH_BULLISH at SMI >= 60; AVOID alerts start at 30."""
    res_caution = generate_signal_and_explanation(ticker="SPCE", smi=40.0)
    ids = [a["id"] for a in res_caution["alerts"]]
    assert "SPCE:SIGNAL:CAUTION_BEARISH" in ids
    assert "SPCE:SIGNAL:AVOID" not in ids

    res_mild = generate_signal_and_explanation(ticker="SPCE", smi=43.0)
    assert not any(a["category"] == "SIGNAL" for a in res_mild["alerts"])

    res_avoid = generate_signal_and_explanation(ticker="SPCE", smi=28.0)
    assert "SPCE:SIGNAL:AVOID" in [a["id"] for a in res_avoid["alerts"]]
