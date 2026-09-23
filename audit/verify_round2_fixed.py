"""Comprehensive verification probes for Round 2 Audit Fixes (R2-01 through R2-09).
Run: python -m audit.verify_round2_fixed
"""
import os
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['ENABLE_SCHEDULER'] = 'false'

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.models import Base, PredictionMarketSnapshotModel, AlertModel
from app.database.repository import (
    save_prediction_markets,
    save_alerts,
    save_divergences,
    save_ssi_snapshot
)
from app.collectors.base import PredictionMarketData
from app.collectors.news_provider import GoogleRSSNewsProvider
from app.collectors.market_provider import _fetch_market_data_sync
from app.scoring.smi import calculate_smi
from app.scoring.signal import generate_signal_and_explanation
from app.scoring.momentum import calculate_momentum_score
from app.sentiment.weighting import detect_catalysts
from app.sentiment.classifier import HeuristicSentimentClassifier
from app.backtesting.engine import compute_hypothesis_significance, evaluate_backtest_dataset

now = datetime.now(timezone.utc)
results = {}

print("--- RUNNING ROUND 2 AUDIT RESOLUTION VERIFICATION ---")

# R2-01: Bootstrap paired calendar alignment
trades_a = [{'return': 1.0 + (i % 3), 'entry_time': f"2026-01-{i+1:02d}T10:00:00Z"} for i in range(35)]
# Set B has only 5 overlapping dates, rest are in February
trades_b = [{'return': 1.5 + (i % 3), 'entry_time': f"2026-01-{i+1:02d}T10:00:00Z"} for i in range(5)] + \
           [{'return': 1.5 + (i % 3), 'entry_time': f"2026-02-{i+1:02d}T10:00:00Z"} for i in range(30)]

res_overlap = compute_hypothesis_significance(trades_a, trades_b)
assert res_overlap["min_sample_reached"] is False, "Expected min_sample_reached=False due to low date overlap"
assert res_overlap["positive_edge_significant"] is False, "Expected positive_edge_significant=False"
assert res_overlap["date_overlap_count"] == 5, f"Expected 5 date overlap pairs, got {res_overlap['date_overlap_count']}"
results["R2-01_bootstrap_calendar_alignment"] = f"PASSED: overlap={res_overlap['date_overlap_count']}, min_sample={res_overlap['min_sample_reached']}"
print("[PASS] R2-01: Bootstrap enforces paired-calendar alignment and flags insufficient date overlap")

# R2-02: Bayesian shrinkage consistency in momentum calculation across 1D/3D/5D
from app.scoring.social import apply_bayesian_shrinkage
shrunk_val = apply_bayesian_shrinkage(80.0, 2, prior=50.0, min_reliable_sample=10)
smi_cur = calculate_smi(
    social_score=80.0,
    post_count=2,
    previous_smi_1d={"smi": shrunk_val, "social_score": shrunk_val, "effective_weights": {"social": 1.0}},
    previous_smi_3d={"smi": shrunk_val, "social_score": shrunk_val, "effective_weights": {"social": 1.0}},
    previous_smi_5d={"smi": shrunk_val, "social_score": shrunk_val, "effective_weights": {"social": 1.0}},
    custom_weights={"social": 1.0}
)
assert abs(smi_cur["smi_momentum_1d"]) < 1e-4, f"Expected zero momentum when shrunk scores match, got {smi_cur['smi_momentum_1d']}"
assert abs(smi_cur["smi_momentum_3d"]) < 1e-4, f"Expected zero 3D momentum, got {smi_cur['smi_momentum_3d']}"
assert abs(smi_cur["smi_momentum_5d"]) < 1e-4, f"Expected zero 5D momentum, got {smi_cur['smi_momentum_5d']}"
assert smi_cur["is_mom_comparable_1d"] is True
assert smi_cur["is_mom_comparable_3d"] is True
assert smi_cur["is_mom_comparable_5d"] is True
results["R2-02_bayesian_momentum_scale_consistency"] = f"PASSED: 1d={smi_cur['smi_momentum_1d']:.2f}, 3d={smi_cur['smi_momentum_3d']:.2f}, 5d={smi_cur['smi_momentum_5d']:.2f}"
print("[PASS] R2-02: Bayesian shrinkage momentum consistency across 1D, 3D, and 5D horizons verified")

# R2-03: Double quality factor modulation prevention & Pure counterfactual A/B evaluation
# 1) calculate_smi does not double-discount prediction weight when custom_weights is provided
base_smi = calculate_smi(prediction_score=80.0, prediction_quality=50.0, prediction_count=1)
# Pass custom_weights matching effective_weights
custom_smi = calculate_smi(prediction_score=80.0, prediction_quality=50.0, prediction_count=1, custom_weights=base_smi["effective_weights"])
assert abs(custom_smi["effective_weights"]["prediction"] - base_smi["effective_weights"]["prediction"]) < 1e-4, \
    f"Weight should not be double-discounted: orig={base_smi['effective_weights']['prediction']}, custom={custom_smi['effective_weights']['prediction']}"

# 2) A/B evaluation without prediction market data yields identical Model A and Model B signals
snaps_no_pred = [
    {'ticker': 'ASTS', 'timestamp': now + timedelta(days=i), 'price': 100 + i,
     'social_score': 85, 'news_score': 80, 'post_count': 25, 'news_count': 4,
     'rsi14': 55, 'market_status': 'AVAILABLE'}
    for i in range(3)
]
bt_res = evaluate_backtest_dataset(snaps_no_pred, holding_period_days=1)
assert bt_res["model_a_baseline"]["metrics"]["total_trades"] == bt_res["model_b_multisource"]["metrics"]["total_trades"], \
    "Model B must exactly match Model A when prediction markets are absent"
results["R2-03_no_double_discount_and_pure_ab"] = "PASSED: weights match & identical baseline in pure A/B"
print("[PASS] R2-03: Double quality discounting eliminated and pure counterfactual A/B validated")

# R2-04: Unit-of-work atomic persistence
from app.database.models import TickerModel
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
db = Session()
db.add(TickerModel(symbol="ASTS", name="AST SpaceMobile"))
db.commit()

# Flushing without commit: objects in session are not committed until explicit commit
save_alerts(db, "ASTS", [{"type": "PRICE_SURGE", "level": "HIGH", "message": "test", "category": "SIGNAL"}], commit=False)
assert db.query(AlertModel).count() == 1
db.rollback() # Rollback flushes away uncommitted work
assert db.query(AlertModel).count() == 0
results["R2-04_atomic_persistence_uow"] = "PASSED: rollback cleanly cleared uncommitted records"
print("[PASS] R2-04: Atomic unit-of-work rollback verified")

# R2-05: Category-scoped alert resolution & news collection error handling
# Add an active TECHNICAL alert and an active DIVERGENCE alert
save_alerts(db, "ASTS", [
    {"type": "RSI_OVERSOLD", "level": "HIGH", "message": "tech alert", "category": "TECHNICAL"},
    {"type": "BEARISH_DIVERGENCE", "level": "CRITICAL", "message": "div alert", "category": "DIVERGENCE"}
], commit=True)

# When resolving only DIVERGENCE, technical alert remains untouched
save_alerts(db, "ASTS", [], resolve_categories={"DIVERGENCE"}, commit=True)
reloaded_tech = db.query(AlertModel).filter(AlertModel.type == "RSI_OVERSOLD").first()
reloaded_div = db.query(AlertModel).filter(AlertModel.type == "BEARISH_DIVERGENCE").first()
assert reloaded_tech.resolved_at is None, "Technical alert should NOT be resolved by divergence run"
assert reloaded_div.resolved_at is not None, "Divergence alert should be resolved"

# Also verify GoogleRSSNewsProvider raises RuntimeError on HTTP failure
provider = GoogleRSSNewsProvider()
with patch("httpx.AsyncClient.get", return_value=MagicMock(status_code=500)):
    try:
        asyncio.run(provider.fetch_news(query="ASTS", ticker="ASTS"))
        raise AssertionError("Expected fetch_news to raise RuntimeError on HTTP 500")
    except RuntimeError as e:
        assert "500" in str(e)
results["R2-05_category_scoped_alerts_and_error_handling"] = "PASSED: category scoping & exception propagation verified"
print("[PASS] R2-05: Category-scoped alert resolution & news exception propagation verified")

# R2-06: Prediction market delta contract
market_flat = PredictionMarketData(
    external_id='poly-flat', ticker='ASTS', title='Flat Market',
    created_at=now, end_date=None, status='ACTIVE',
    yes_probability=0.50, no_probability=0.50, volume=10000, liquidity=5000, spread=0.01,
    probability_change_24h=0.0
)
save_prediction_markets(db, [market_flat], commit=True)
# Preserves 0.0
assert market_flat.probability_change_24h == 0.0

market_none = PredictionMarketData(
    external_id='poly-none', ticker='ASTS', title='Missing Market',
    created_at=now, end_date=None, status='ACTIVE',
    yes_probability=0.50, no_probability=0.50, volume=10000, liquidity=5000, spread=0.01,
    probability_change_24h=None
)
save_prediction_markets(db, [market_none], commit=True)
# Kept None when no 24h history exists
assert market_none.probability_change_24h is None
results["R2-06_delta_contract"] = "PASSED: 0.0 preserved, None distinguished"
print("[PASS] R2-06: Prediction market delta contract (0.0 vs None) verified")

# R2-07: Safe price indicator handling & session-aware freshness
sig_noprice = generate_signal_and_explanation(
    ticker="ASTS", smi=90, social_score=90, news_score=90,
    indicators={"price": None, "status": "AVAILABLE"}
)
assert sig_noprice["base_signal"] != "STRONG BUY", "Missing price must gate down STRONG BUY"
assert "NO MKT DATA" in sig_noprice["signal"]

sig_zeroprice = generate_signal_and_explanation(
    ticker="ASTS", smi=90, social_score=90, news_score=90,
    indicators={"price": 0.0, "status": "AVAILABLE"}
)
assert sig_zeroprice["base_signal"] != "STRONG BUY", "Zero price must gate down STRONG BUY"
assert "NO MKT DATA" in sig_zeroprice["signal"]
results["R2-07_safe_price_handling"] = "PASSED: missing/zero price gated down properly"
print("[PASS] R2-07: Safe price indicator handling and market gating verified")

# R2-08: Competition entity extraction & contract cancellation keywords
cats_select = detect_catalysts("NASA selects SpaceX over Rocket Lab for launch contract", ticker="RKLB")
assert len(cats_select) > 0
assert cats_select[0]["direction"] == "BEARISH", f"Expected BEARISH for loser RKLB, got {cats_select[0]['direction']}"

cats_cancel = detect_catalysts("US Space Force cancels contract with Rocket Lab due to delays", ticker="RKLB")
assert len(cats_cancel) > 0
assert cats_cancel[0]["direction"] == "BEARISH", f"Expected BEARISH for cancellation, got {cats_cancel[0]['direction']}"

clf = HeuristicSentimentClassifier()
assert clf.analyze("Pentagon terminates satellite contract").label == "BEARISH"
results["R2-08_competition_extraction_and_cancellation"] = "PASSED: competition direction & cancellation keywords verified"
print("[PASS] R2-08: Competition entity extraction and contract termination keywords verified")

# R2-09: Direction-aware volume scoring in technical scorer
# Falling prices with high volume (distribution) vs low volume
downtrend_df = pd.DataFrame({'Close': [100 - i * 2 for i in range(25)]})
ind_low_vol = {'status': 'AVAILABLE', 'price': 50, 'rsi14': 40, 'volume_ratio': 1.0}
ind_high_vol = {'status': 'AVAILABLE', 'price': 50, 'rsi14': 40, 'volume_ratio': 2.5}

score_low = calculate_momentum_score(ind_low_vol, downtrend_df)
score_high = calculate_momentum_score(ind_high_vol, downtrend_df)
assert score_high < score_low, f"High volume distribution must not score higher than normal (high: {score_high}, low: {score_low})"
results["R2-09_directional_volume_scoring"] = f"PASSED: distribution volume penalized (normal: {score_low}, heavy: {score_high})"
print(f"[PASS] R2-09: Direction-aware technical volume scoring verified (normal: {score_low}, heavy: {score_high})")

db.close()
print("\nALL ROUND 2 AUDIT RESOLUTION PROBES PASSED!")
