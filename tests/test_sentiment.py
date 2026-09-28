from app.sentiment.classifier import HeuristicSentimentClassifier
from app.sentiment.weighting import calculate_engagement_score, calculate_recency_weight, calculate_relevance_score


def test_heuristic_classifier_bullish():
    classifier = HeuristicSentimentClassifier()
    res = classifier.analyze("ASTSpaceMobile $ASTS satellite milestone launch contract win!")
    assert res.label == "BULLISH"
    assert res.score > 0.20


def test_heuristic_classifier_bearish():
    classifier = HeuristicSentimentClassifier()
    res = classifier.analyze("$SPCE stock price dropping after cash burn dilution risk warning")
    assert res.label == "BEARISH"
    assert res.score < -0.20


def test_engagement_log_scaling():
    # Test log scaling prevents viral post dominance
    eng1 = calculate_engagement_score(likes=10, reposts=2, replies=1, views=500)
    eng2 = calculate_engagement_score(likes=1000, reposts=500, replies=200, views=50000)
    
    assert eng1 > 0
    assert eng2 > eng1
    assert eng2 < 10.0  # Log scale dampens gigantic viral numbers


def test_relevance_score():
    rel_exact = calculate_relevance_score("$ASTS BlueBird satellite launch", "ASTS", ["$ASTS", "AST SpaceMobile"])
    assert rel_exact == 1.0

    rel_standalone = calculate_relevance_score("ASTS satellite launch", "ASTS", ["$ASTS", "AST SpaceMobile"])
    assert rel_standalone == 0.75

    rel_unrelated = calculate_relevance_score("Random tweet about coffee and weather", "ASTS", ["$ASTS"])
    assert rel_unrelated <= 0.10


def test_calculate_news_score_empty_returns_none():
    """Validates that empty news items returns None for news_score (no fake 50s)."""
    from app.sentiment.weighting import calculate_news_score
    res = calculate_news_score([])
    assert res["news_score"] is None
    assert res["total_news"] == 0
    assert res["bullish_news_pct"] == 0.0
    assert res["bearish_news_pct"] == 0.0


def test_calculate_news_score_with_bullish_items():
    from datetime import datetime, timezone
    from app.sentiment.weighting import calculate_news_score
    from app.database.models import NewsItemModel

    news = [
        NewsItemModel(
            ticker="ASTS",
            title="AST SpaceMobile Receives Landmark FCC License",
            url="https://example.com/news1",
            source="SpaceNews",
            published_at=datetime.now(timezone.utc),
            sentiment_score=0.8,
            sentiment_label="BULLISH",
            relevance_score=1.0,
            catalyst_importance="CRITICAL"
        )
    ]
    res = calculate_news_score(news)
    assert res["news_score"] is not None
    assert res["news_score"] > 70.0
    assert res["total_news"] == 1
    assert res["bullish_news_pct"] == 100.0


def test_detect_multiple_catalysts_concurrent():
    from app.sentiment.weighting import detect_catalysts
    text = "ASTS announces capital raise dilution after payload launch delay"
    cats = detect_catalysts(text)
    
    cat_names = [c["category"] for c in cats]
    assert "CAPITAL_RAISE" in cat_names
    assert "LAUNCH_DELAY" in cat_names
    assert len(cats) >= 2


def test_detect_catalyst_importance_priority():
    from app.sentiment.weighting import detect_catalyst
    # Text contains both a MEDIUM milestone and a CRITICAL government contract
    text = "Rocket Lab completes hot fire engine test and wins landmark NASA government contract"
    cat_type, cat_dir, cat_imp = detect_catalyst(text)
    
    assert cat_type == "GOVERNMENT_CONTRACT"
    assert cat_imp == "CRITICAL"
    assert cat_dir == "BULLISH"


def test_heuristic_classifier_negation_inversion():
    classifier = HeuristicSentimentClassifier()

    # 1. Negated Bullish phrases should invert to BEARISH
    res1 = classifier.analyze("I am not bullish on this stock, no launch confirmation yet.")
    assert res1.label == "BEARISH"
    assert res1.score < 0.0

    res2 = classifier.analyze("Failed deployment and lack of revenue growth")
    assert res2.label == "BEARISH"
    assert res2.score < 0.0

    # 2. Negated Bearish phrases should invert to BULLISH
    res3 = classifier.analyze("Management confirms no dilution and not selling any shares.")
    assert res3.label == "BULLISH"
    assert res3.score > 0.0

    # 3. Affirmative idioms (e.g. 'no doubt') should NOT invert following bullish words
    res4 = classifier.analyze("No doubt about it, this is a great rocket launch and milestone contract!")
    assert res4.label == "BULLISH"
    assert res4.score > 0.0

    # 4. Punctuation boundary prevents distant negation crossing clauses
    res5 = classifier.analyze("This is no joke, massive launch success today.")
    assert res5.label == "BULLISH"
    assert res5.score > 0.0


def test_news_score_respects_relevance_weighting():
    from app.sentiment.weighting import calculate_news_score
    from datetime import datetime, timezone
    from collections import namedtuple

    MockNews = namedtuple("MockNews", ["sentiment_score", "sentiment_label", "published_at", "relevance_score", "catalyst_importance"])

    now = datetime.now(timezone.utc)
    # High relevance (+0.8 bullish with relevance 1.0) vs Low relevance (-0.8 bearish with relevance 0.2)
    news = [
        MockNews(sentiment_score=0.8, sentiment_label="BULLISH", published_at=now, relevance_score=1.0, catalyst_importance="MEDIUM"),
        MockNews(sentiment_score=-0.8, sentiment_label="BEARISH", published_at=now, relevance_score=0.2, catalyst_importance="MEDIUM"),
    ]

    res = calculate_news_score(news)
    assert res["news_score"] is not None
    # Score should be significantly bullish (> 70) because the bullish news had 5x higher relevance
    assert res["news_score"] > 70.0


def test_high_keyword_disambiguation_false_positives():
    """
    Verify that phrases like 'high risk', 'high cash burn', or 'all-time high short interest'
    are properly classified as BEARISH without false positive bullish hits from 'high'.
    """
    classifier = HeuristicSentimentClassifier()

    # 1. High risk & high cash burn (must be BEARISH)
    res_risk = classifier.analyze("ASTS faces high risk and high cash burn ahead of commercial service.")
    assert res_risk.label == "BEARISH"
    assert res_risk.score < 0.0

    # 2. Short interest at all-time high (must be BEARISH)
    res_short = classifier.analyze("RKLB short interest hits an all-time high amid market selloff.")
    assert res_short.label == "BEARISH"
    assert res_short.score < 0.0

    # 3. All-time high in price / stock context (must be BULLISH)
    res_ath = classifier.analyze("ASTS reaches an all-time high after successful commercial satellite launch milestone.")
    assert res_ath.label == "BULLISH"
    assert res_ath.score > 0.0


def test_neutral_domain_nouns_not_bullish():
    """
    Verify that domain nouns (rocket, satellite, launch, nasa, fcc) are NOT treated as bullish keywords,
    and factual descriptive sentences score NEUTRAL rather than degenerate +1.0.
    """
    classifier = HeuristicSentimentClassifier()

    # 1. Factual space activity post (must be NEUTRAL, score = 0.0)
    res_factual = classifier.analyze("SpaceX launches another Falcon 9 rocket with 20 Starlink satellites for NASA.")
    assert res_factual.label == "NEUTRAL"
    assert res_factual.score == 0.0

    # 2. Polar bullish post with tanh saturation (score ~ 0.46 for 1 hit, not 1.0)
    res_surge = classifier.analyze("Rocket Lab stock surges following earnings release.")
    assert res_surge.label == "BULLISH"
    assert 0.40 <= res_surge.score <= 0.60, f"Expected smooth tanh score ~0.46, got {res_surge.score}"

    # 3. Multi-hit bullish conviction
    res_multi = classifier.analyze("ASTS wins landmark contract, surges to all-time high with massive revenue growth.")
    assert res_multi.label == "BULLISH"
    assert res_multi.score >= 0.80


def test_detect_catalysts_word_boundaries_and_bearish_priority():
    """
    Verify that:
    1. Substrings like 'Seattle', 'battery', 'dodge' do NOT match 'att' or 'dod'.
    2. Exact word 'att' or 'dod' DOES match.
    3. 'launch abort' prioritizes BEARISH LAUNCH_DELAY over BULLISH LAUNCH.
    """
    from app.sentiment.weighting import detect_catalysts, detect_catalyst

    # 1. False substring matches must NOT trigger catalysts
    text_substrings = "The engineer from Seattle replaced the battery and attempted to dodge the obstacle in the carrier narrative."
    cats_false = detect_catalysts(text_substrings)
    assert len(cats_false) == 0, f"Expected 0 catalysts from false substrings, got {cats_false}"

    # 2. Legitimate acronyms with word boundaries DO trigger
    text_legit = "ASTS signs definitive partnership with AT&T and receives major DoD contract."
    cats_legit = detect_catalysts(text_legit)
    cat_names = [c["category"] for c in cats_legit]
    assert "GOVERNMENT_CONTRACT" in cat_names

    # 3. Anomaly / Launch Abort must prioritize BEARISH LAUNCH_DELAY over BULLISH LAUNCH
    text_abort = "Rocket Lab suffers launch abort after detecting engine anomaly during countdown."
    top_cat, top_dir, top_imp = detect_catalyst(text_abort)
    assert top_cat == "LAUNCH_DELAY"
    assert top_dir == "BEARISH"
    cats_abort = detect_catalysts(text_abort)
    cat_names_abort = [c["category"] for c in cats_abort]
    assert "LAUNCH_DELAY" in cat_names_abort
    assert "LAUNCH" not in cat_names_abort, "LAUNCH_DELAY must suppress generic BULLISH LAUNCH"

    # 4. Catastrophic Launch Failure / Explosion must prioritize CRITICAL BEARISH LAUNCH_FAILURE over BULLISH LAUNCH
    text_fail = "Terrible news: launch failure destroyed the payload after booster explosion during stage 1 ascent."
    top_fail_cat, top_fail_dir, top_fail_imp = detect_catalyst(text_fail)
    assert top_fail_cat == "LAUNCH_FAILURE"
    assert top_fail_dir == "BEARISH"
    assert top_fail_imp == "CRITICAL"
    cats_fail = detect_catalysts(text_fail)
    cat_names_fail = [c["category"] for c in cats_fail]
    assert "LAUNCH_FAILURE" in cat_names_fail
    assert "LAUNCH" not in cat_names_fail, "LAUNCH_FAILURE must suppress generic BULLISH LAUNCH"


def test_signal_reasons_deduplicates_and_ranks_catalysts():
    """
    Verify that generate_signal_and_explanation:
    1. Deduplicates multiple instances of the same catalyst category.
    2. Ranks CRITICAL catalysts from later items ahead of repetitive HIGH/MEDIUM items.
    3. Never prints duplicate lines for the same category.
    4. Prunes contradictory generic LAUNCH when LAUNCH_FAILURE or LAUNCH_DELAY is present.
    """
    from app.scoring.signal import generate_signal_and_explanation

    # Simulate 10 duplicate SATELLITE_DEPLOYMENT items from social posts followed by 1 CRITICAL GOVERNMENT_CONTRACT from news
    raw_catalysts = [{"category": "SATELLITE_DEPLOYMENT", "direction": "BULLISH", "importance": "HIGH"}] * 10
    raw_catalysts.append({"category": "GOVERNMENT_CONTRACT", "direction": "BULLISH", "importance": "CRITICAL"})
    raw_catalysts.append({"category": "CAPITAL_RAISE", "direction": "BEARISH", "importance": "HIGH"})

    res = generate_signal_and_explanation(
        ticker="ASTS",
        smi=75.0,
        social_score=75.0,
        catalysts_found=raw_catalysts
    )

    reasons = res["reasons"]
    catalyst_reasons = [r for r in reasons if "catalyst" in r.lower()]

    # 1. Must contain CRITICAL Government Contract at the top
    assert len(catalyst_reasons) == 3
    assert "[CRITICAL] Government Contract" in catalyst_reasons[0]

    # 2. Must not repeat Satellite Deployment multiple times
    sat_reasons = [r for r in catalyst_reasons if "Satellite Deployment" in r]
    assert len(sat_reasons) == 1

    # 3. Must contain Capital Raise
    cap_reasons = [r for r in catalyst_reasons if "Capital Raise" in r]
    assert len(cap_reasons) == 1

    # 4. Conflicting launch failure and launch catalyst must prune positive launch
    conflicting_catalysts = [
        {"category": "LAUNCH_FAILURE", "direction": "BEARISH", "importance": "CRITICAL"},
        {"category": "LAUNCH", "direction": "BULLISH", "importance": "HIGH"},
        {"category": "LAUNCH_DELAY", "direction": "BEARISH", "importance": "HIGH"}
    ]
    res_conflict = generate_signal_and_explanation(
        ticker="RKLB",
        smi=30.0,
        catalysts_found=conflicting_catalysts
    )
    conflict_reasons = res_conflict["reasons"]
    assert any("[CRITICAL] Launch Failure" in r for r in conflict_reasons)
    assert not any("+ Positive catalyst" in r and "Launch" in r for r in conflict_reasons)
    assert not any("Launch Delay" in r for r in conflict_reasons)


def test_news_score_below_relevance_threshold_returns_none():
    """Verify that calculate_news_score returns None when all news items are below NEWS_MIN_RELEVANCE."""
    from datetime import datetime, timezone
    from collections import namedtuple
    from app.sentiment.weighting import calculate_news_score

    MockNews = namedtuple("MockNews", ["sentiment_score", "sentiment_label", "published_at", "relevance_score", "catalyst_importance"])
    now = datetime.now(timezone.utc)

    # 3 news items with low relevance (relevance = 0.10, threshold is 0.40)
    low_rel_news = [
        MockNews(sentiment_score=0.9, sentiment_label="BULLISH", published_at=now, relevance_score=0.10, catalyst_importance="LOW"),
        MockNews(sentiment_score=-0.8, sentiment_label="BEARISH", published_at=now, relevance_score=0.15, catalyst_importance="LOW"),
    ]

    res = calculate_news_score(low_rel_news)
    assert res["news_score"] is None
    assert res["total_news"] == 0


def test_rss_news_pubdate_timezone_conversion():
    """Verify that RSS pubDate strings with timezones are converted to naive UTC correctly."""
    from email.utils import parsedate_to_datetime
    from datetime import timezone

    # 1. PubDate with Eastern Daylight Time (-0400)
    pub_str_edt = "Fri, 28 Aug 2026 10:00:00 -0400"
    dt_edt = parsedate_to_datetime(pub_str_edt)
    utc_dt = dt_edt.astimezone(timezone.utc).replace(tzinfo=None)
    # 10:00:00 -0400 is 14:00:00 UTC
    assert utc_dt.hour == 14
    assert utc_dt.day == 28

    # 2. PubDate with Tokyo Time (+0900)
    pub_str_jst = "Fri, 28 Aug 2026 05:00:00 +0900"
    dt_jst = parsedate_to_datetime(pub_str_jst)
    utc_jst = dt_jst.astimezone(timezone.utc).replace(tzinfo=None)
    # 05:00:00 +0900 on Aug 28 is 20:00:00 UTC on Aug 27
    assert utc_jst.hour == 20
    assert utc_jst.day == 27


def test_catalyst_cancellation_and_entity_decoupling():
    """
    Validates the fix for audit issue 9:
    'NASA cancels Rocket Lab contract' must return GOVERNMENT_CONTRACT with direction BEARISH and CRITICAL importance.
    Entities (NASA, DoD) are decoupled from static bullish directions and respect cancellation/termination actions.
    """
    from app.sentiment.weighting import detect_catalysts, detect_catalyst

    # 1. Contract cancellation must be BEARISH and CRITICAL
    text_cancel = "Breaking: NASA cancels Rocket Lab contract following program review."
    cat_type, cat_dir, cat_imp = detect_catalyst(text_cancel)
    assert cat_type == "GOVERNMENT_CONTRACT"
    assert cat_dir == "BEARISH", f"Expected BEARISH for cancellation, got {cat_dir}"
    assert cat_imp == "CRITICAL"

    # 2. DoD contract termination
    text_dod_term = "DoD terminates contract with AST SpaceMobile due to schedule adjustments."
    dod_cats = detect_catalysts(text_dod_term)
    assert len(dod_cats) >= 1
    assert dod_cats[0]["category"] == "GOVERNMENT_CONTRACT"
    assert dod_cats[0]["direction"] == "BEARISH"

    # 3. Contract award must be BULLISH and CRITICAL
    text_award = "Rocket Lab wins and NASA awards landmark defense government contract."
    cat_type_a, cat_dir_a, cat_imp_a = detect_catalyst(text_award)
    assert cat_type_a == "GOVERNMENT_CONTRACT"
    assert cat_dir_a == "BULLISH"
    assert cat_imp_a == "CRITICAL"

    # 4. Standalone agency mention without contract or award/cancellation must NOT trigger contract catalyst
    text_neutral_agency = "NASA astronaut gives presentation on space biology experiments aboard ISS."
    agency_cats = detect_catalysts(text_neutral_agency)
    assert len(agency_cats) == 0, f"Expected 0 catalysts for non-contract agency mention, got {agency_cats}"

    # 5. Partnership termination must be BEARISH
    text_partner_term = "Verizon terminates partnership agreement with AST SpaceMobile."
    p_type, p_dir, p_imp = detect_catalyst(text_partner_term)
    assert p_type == "PARTNERSHIP"
    assert p_dir == "BEARISH"

    # 6. FAA license denial/grounding must be BEARISH
    text_faa_deny = "FAA denies launch license and grounds rocket pending investigation."
    faa_type, fae_dir, faa_imp = detect_catalyst(text_faa_deny)
    assert faa_type == "FAA_APPROVAL"
    assert fae_dir == "BEARISH"


def test_catalyst_hypothetical_and_historical_filtering():
    """
    Validates that:
    1. Pure hypothetical questions (e.g. 'What if NASA cancels Rocket Lab contract?')
       are flagged as hypothetical and do NOT trigger actionable critical trading alerts.
    2. Historical retrospectives from years ago (e.g. events in 2021)
       are flagged as historical and excluded from breaking news alerts.
    """
    from app.sentiment.weighting import detect_catalysts, detect_catalyst

    # 1. Hypothetical question
    text_hypo = "What if NASA cancels Rocket Lab contract if the next milestone slips?"
    hypo_cats = detect_catalysts(text_hypo, include_hypothetical=True)
    assert len(hypo_cats) >= 1
    assert hypo_cats[0].get("is_hypothetical") is True
    assert hypo_cats[0]["importance"] == "LOW"

    # Top actionable catalyst must be None for hypothetical speculation
    act_type, act_dir, act_imp = detect_catalyst(text_hypo)
    assert act_type is None, f"Hypothetical speculation must not trigger actionable catalyst alert, got {act_type}"

    # 2. Historical past event
    text_hist = "Rocket Lab previously lost a contract in 2021 before restructuring operations."
    hist_cats = detect_catalysts(text_hist, include_historical=True)
    assert len(hist_cats) >= 1
    assert hist_cats[0].get("is_historical") is True
    assert hist_cats[0]["importance"] == "LOW"

    # Top actionable catalyst must be None for historical retrospect
    h_type, h_dir, h_imp = detect_catalyst(text_hist)
    assert h_type is None, f"Historical retrospective must not trigger actionable catalyst alert, got {h_type}"


def test_catalyst_competitor_rivalry():
    """
    Validates that competitor selection over a company (e.g. 'NASA selects SpaceX over Rocket Lab')
    is identified as a BEARISH catalyst for the passed-over entity.
    """
    from app.sentiment.weighting import detect_catalysts, detect_catalyst

    text_rival = "NASA selects SpaceX over Rocket Lab for the Artemis lunar transport contract."
    cats = detect_catalysts(text_rival, ticker="RKLB")
    assert len(cats) >= 1
    assert cats[0]["category"] == "GOVERNMENT_CONTRACT"
    assert cats[0]["direction"] == "BEARISH"
    assert cats[0]["importance"] == "CRITICAL"

    c_type, c_dir, c_imp = detect_catalyst(text_rival, ticker="RKLB")
    assert c_type == "GOVERNMENT_CONTRACT"
    assert c_dir == "BEARISH"
    assert c_imp == "CRITICAL"


def test_catalyst_common_phrases_false_positive_elimination():
    """
    Validates the elimination of critical false positives triggered by common financial and idiomatic phrases:
    1. 'Redwire reports Q2 net loss as defense revenue grows' -> NO false GOVERNMENT_CONTRACT or false REVENUE beat.
    2. 'Rocket Lab shares drop despite NASA award' -> BULLISH CRITICAL GOVERNMENT_CONTRACT award, NOT false cancellation.
    3. 'Analysts keep hold rating on ASTS' -> NO false LAUNCH_DELAY.
    4. 'Planet Labs stock crash after earnings' -> NO false LAUNCH_FAILURE.
    5. 'explosion of demand' -> NO false LAUNCH_FAILURE.
    """
    from app.sentiment.weighting import detect_catalysts, detect_catalyst

    # 1. Net loss with defense revenue growth
    t1 = "Redwire reports Q2 net loss as defense revenue grows"
    cats1 = detect_catalysts(t1)
    gov_cats1 = [c for c in cats1 if c["category"] == "GOVERNMENT_CONTRACT"]
    assert len(gov_cats1) == 0, f"Expected 0 GOVERNMENT_CONTRACT catalysts for '{t1}', got {gov_cats1}"
    rev_cats1 = [c for c in cats1 if c["category"] == "REVENUE" and c["direction"] == "BULLISH"]
    assert len(rev_cats1) == 0, f"Expected no BULLISH REVENUE when net loss is reported, got {rev_cats1}"

    # 2. Shares drop despite NASA award
    t2 = "Rocket Lab shares drop despite NASA award"
    top_cat2, top_dir2, top_imp2 = detect_catalyst(t2)
    assert top_cat2 == "GOVERNMENT_CONTRACT", f"Expected GOVERNMENT_CONTRACT for '{t2}', got {top_cat2}"
    assert top_dir2 == "BULLISH", f"Expected BULLISH award, got {top_dir2}"
    assert top_imp2 == "CRITICAL"

    # 3. Analyst hold rating
    t3 = "Analysts keep hold rating on ASTS"
    cats3 = detect_catalysts(t3)
    delay_cats3 = [c for c in cats3 if c["category"] == "LAUNCH_DELAY"]
    assert len(delay_cats3) == 0, f"Expected 0 LAUNCH_DELAY for '{t3}', got {delay_cats3}"

    # 4. Stock market crash
    t4 = "Planet Labs stock crash after earnings"
    cats4 = detect_catalysts(t4)
    fail_cats4 = [c for c in cats4 if c["category"] == "LAUNCH_FAILURE"]
    assert len(fail_cats4) == 0, f"Expected 0 LAUNCH_FAILURE for '{t4}', got {fail_cats4}"

    # 5. Idiomatic explosion of demand
    t5 = "AST SpaceMobile sees explosion of demand for direct to cell connectivity"
    cats5 = detect_catalysts(t5)
    fail_cats5 = [c for c in cats5 if c["category"] == "LAUNCH_FAILURE"]
    assert len(fail_cats5) == 0, f"Expected 0 LAUNCH_FAILURE for '{t5}', got {fail_cats5}"


def test_catalyst_competitor_rivalry_word_boundaries():
    """
    Validates that competitor rivalry matching enforces regex word boundaries so that:
    - 'ast' does NOT match 'at last' or 'fast'
    - 'pl' does NOT match 'complex' or 'application'
    - Financial performance 'beats' (e.g. 'beats earnings guidance') are not treated as rival defeats
    - Legitimate entities DO match correctly with word boundaries
    """
    from app.sentiment.weighting import detect_catalysts

    # 'at last' and 'fast' should not trigger ASTS in competitor rivalry
    text_last = "NASA selects SpaceX over Blue Origin at last for lunar mission"
    cats_last = detect_catalysts(text_last, ticker="ASTS")
    assert len(cats_last) == 0, f"Expected 0 catalysts for ASTS from 'at last', got {cats_last}"

    text_fast = "SpaceX beats fast rivals for next launch milestone"
    cats_fast = detect_catalysts(text_fast, ticker="ASTS")
    ast_rival = [c for c in cats_fast if "selected over" in c.get("keyword", "") or "beat competitor" in c.get("keyword", "")]
    assert len(ast_rival) == 0, f"ASTS should not match 'fast' in competitor rivalry, got {ast_rival}"

    # 'complex' should not trigger PL in competitor rivalry
    text_complex = "SpaceX beats complex rivals for next launch milestone"
    cats_complex = detect_catalysts(text_complex, ticker="PL")
    pl_rival = [c for c in cats_complex if "selected over" in c.get("keyword", "") or "beat competitor" in c.get("keyword", "")]
    assert len(pl_rival) == 0, f"PL should not match 'complex' in competitor rivalry, got {pl_rival}"

    # Legitimate mentions DO match
    text_pl_real = "NASA selects SpaceX over Planet Labs for Earth observation contract"
    cats_pl_real = detect_catalysts(text_pl_real, ticker="PL")
    assert any(c["category"] == "GOVERNMENT_CONTRACT" and c["direction"] == "BEARISH" for c in cats_pl_real)

    text_asts_real = "NASA selects SpaceX over AST SpaceMobile for communications contract"
    cats_asts_real = detect_catalysts(text_asts_real, ticker="ASTS")
    assert any(c["category"] == "GOVERNMENT_CONTRACT" and c["direction"] == "BEARISH" for c in cats_asts_real)

    # Financial 'beats' should not count as competitor rivalry
    text_fin_beat = "Rocket Lab reports record revenue surge and beats earnings guidance"
    cats_fin = detect_catalysts(text_fin_beat, ticker="RKLB")
    rival_cats = [c for c in cats_fin if c["category"] == "GOVERNMENT_CONTRACT" and "beat competitor" in c.get("keyword", "")]
    assert len(rival_cats) == 0, f"Expected no competitor defeat for earnings guidance beat, got {rival_cats}"


def test_heuristic_classifier_ambiguous_words():
    """
    Validates that ambiguous words in HeuristicSentimentClassifier do not cause false polarities:
    1. 'call' in earnings/conference call is NEUTRAL, not BULLISH.
    2. 'long' in long-term/long time is NEUTRAL, not BULLISH.
    3. 'short' in short-term is NEUTRAL, not BEARISH.
    4. 'put' in 'put into orbit' is NEUTRAL/BULLISH, not BEARISH.
    5. 'sell-side' in 'sell-side analysts upgrade' does not trigger BEARISH 'sell'.
    6. 'profit-taking' in 'drops due to profit-taking' does not trigger BULLISH 'profit'.
    7. 'derisk' / 'risk management' does not trigger BEARISH 'risk'.
    """
    from app.sentiment.classifier import HeuristicSentimentClassifier
    classifier = HeuristicSentimentClassifier()

    # 1. Earnings and conference calls
    res_call = classifier.analyze("Company will host an earnings call with analysts tomorrow.")
    assert res_call.label == "NEUTRAL", f"Expected NEUTRAL for earnings call, got {res_call.label}"
    assert res_call.score == 0.0

    res_conf_call = classifier.analyze("Management discussed satellite constellation during quarterly conference call.")
    assert res_conf_call.label == "NEUTRAL"
    assert res_conf_call.score == 0.0

    # Explicit call options DO trigger bullish
    res_call_opt = classifier.analyze("Traders aggressively buying call options ahead of flight.")
    assert res_call_opt.label == "BULLISH"
    assert res_call_opt.score > 0.20

    # 2. Long-term / long time vs Long position
    res_long_term = classifier.analyze("Long term outlook for commercial space payload delivery.")
    assert res_long_term.label == "NEUTRAL"
    assert res_long_term.score == 0.0

    res_go_long = classifier.analyze("Prominent institutional fund decides to go long on ASTS shares.")
    assert res_go_long.label == "BULLISH"
    assert res_go_long.score > 0.20

    # 3. Short-term vs Short selling / short interest
    res_short_term = classifier.analyze("Short-term volatility expected ahead of regulatory announcement.")
    assert res_short_term.label == "NEUTRAL"
    assert res_short_term.score == 0.0

    res_short_int = classifier.analyze("Hedge fund initiates aggressive short position as short interest climbs.")
    assert res_short_int.label == "BEARISH"
    assert res_short_int.score < -0.20

    # 4. Put into orbit vs Put options
    res_put_orbit = classifier.analyze("Second batch of commercial satellites was put into orbit successfully.")
    assert res_put_orbit.label == "BULLISH", f"Expected BULLISH for successful orbit, got {res_put_orbit.label}"
    assert res_put_orbit.score > 0.20

    res_put_opt = classifier.analyze("Bearish traders loaded on put options targeting sharp price drop.")
    assert res_put_opt.label == "BEARISH"
    assert res_put_opt.score < -0.20

    # 5. Sell-side analysts upgrade
    res_sell_side = classifier.analyze("Sell-side analysts upgrade Rocket Lab to outperform.")
    assert res_sell_side.label == "BULLISH", f"Expected BULLISH for upgrade, got {res_sell_side.label}"
    assert res_sell_side.score > 0.20

    # 6. Profit-taking
    res_profit_take = classifier.analyze("Stock drops 5% due to profit-taking.")
    assert res_profit_take.label == "BEARISH", f"Expected BEARISH for drop due to profit-taking, got {res_profit_take.label}"
    assert res_profit_take.score < 0.0

    res_profit_alone = classifier.analyze("Traders engaging in profit-taking ahead of weekend.")
    assert res_profit_alone.label == "NEUTRAL", f"Profit-taking alone must not be BULLISH, got {res_profit_alone.label}"
    assert res_profit_alone.score == 0.0

    # 7. Derisk / Risk management vs Downside / Dilution Risk
    res_derisk = classifier.analyze("Hot fire engine test completed to derisk the launch vehicle architecture.")
    assert res_derisk.score >= 0.0

    res_dilution_risk = classifier.analyze("ASTS faces high dilution risk and cash burn in upcoming quarter.")
    assert res_dilution_risk.label == "BEARISH"
    assert res_dilution_risk.score < -0.20


def test_heuristic_classifier_conflicted_signals_confidence():
    """
    Validates that signal confidence reflects net agreement / polarization:
    - 2 bullish + 2 bearish signals (e.g. 'Bullish growth but heavy loss and drop'):
      Yields score = 0.0, label = NEUTRAL, with confidence heavily penalized (<= 0.40, NOT 0.95!).
    - Unanimous signals (e.g. 4 bullish hits):
      Yields high confidence (0.95).
    """
    from app.sentiment.classifier import HeuristicSentimentClassifier
    classifier = HeuristicSentimentClassifier()

    # 1. Severely conflicted text (2 bullish: bullish, growth; 2 bearish: loss, drop)
    res_conflicted = classifier.analyze("Bullish growth but heavy loss and drop")
    assert res_conflicted.score == 0.0
    assert res_conflicted.label == "NEUTRAL"
    assert res_conflicted.confidence <= 0.40, (
        f"Conflicted signals (2 bull, 2 bear) must have low confidence (<= 0.40), got {res_conflicted.confidence}"
    )

    # 2. Unanimous high-conviction bullish (4 bullish hits)
    res_unanimous = classifier.analyze("ASTS wins landmark contract, surges to all-time high with massive revenue growth.")
    assert res_unanimous.label == "BULLISH"
    assert res_unanimous.score >= 0.80
    assert res_unanimous.confidence >= 0.90, f"Unanimous signals should have high confidence, got {res_unanimous.confidence}"


def test_finbert_classifier_inference():
    """Validates local FinBERT batch inference and label classification."""
    from app.sentiment.classifier import FinBERTSentimentClassifier
    classifier = FinBERTSentimentClassifier()
    texts = [
        "Company announces major record profits and breakthrough commercial contract win.",
        "Severe launch anomaly and catastrophic rocket explosion causes massive loss.",
        "The board meeting is scheduled for tomorrow at 2 PM."
    ]
    results = classifier.analyze_batch(texts)
    assert len(results) == 3
    assert results[0].label == "BULLISH"
    assert results[0].score > 0.20
    assert results[1].label == "BEARISH"
    assert results[1].score < -0.20
    assert results[2].label == "NEUTRAL"

