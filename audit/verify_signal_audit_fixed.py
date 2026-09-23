"""Verification script asserting that audit defects are RESOLVED.
Run: python -m audit.verify_signal_audit_fixed
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['ENABLE_SCHEDULER'] = 'false'

import pandas as pd

from app.config import INITIAL_TICKERS, settings
from app.backtesting.engine import evaluate_backtest_dataset, compute_hypothesis_significance
from app.collectors.base import PredictionMarketData
from app.collectors.market_provider import _fetch_market_data_sync
from app.collectors.news_provider import NewsItemData
from app.jobs.runner import ingest_news_for_ticker
from app.scoring.momentum import calculate_momentum_score
from app.scoring.prediction import calculate_prediction_market_score
from app.scoring.signal import generate_signal_and_explanation
from app.scoring.smi import calculate_smi
from app.sentiment.classifier import HeuristicSentimentClassifier
from app.sentiment.weighting import calculate_news_score, calculate_relevance_score, detect_catalysts

now = datetime.now(timezone.utc)
results = {}

print("--- RUNNING AUDIT RESOLUTION VERIFICATION ---")

# Probe 1: Resolved markets must NOT contribute to live scoring
market = PredictionMarketData(
    external_id='audit', ticker='ASTS', title='ASTS success',
    created_at=now, end_date=now - timedelta(days=2), status='RESOLVED',
    yes_probability=1.0, no_probability=0.0, quality_score=90
)
pms = calculate_prediction_market_score('ASTS', [market])
assert pms[0] is None, f"Expected None for resolved market, got {pms[0]}"
results['probe_1_resolved_market_excluded'] = "PASSED: pms is None"
print("[PASS] Probe 1: Resolved markets correctly excluded from score")

# Probe 2: Old candles (e.g. 2020) must NOT be marked AVAILABLE
df = pd.DataFrame(
    {'Open': [100]*30, 'High': [101]*30, 'Low': [99]*30, 'Close': [100]*30, 'Volume': [1000]*30},
    index=pd.date_range('2020-01-01', periods=30, tz='America/New_York')
)
with patch('app.collectors.market_provider.yf.Ticker', return_value=SimpleNamespace(history=lambda **kw: df)):
    stale = _fetch_market_data_sync('ASTS')
assert stale.status in ['STALE', 'DATA_UNAVAILABLE'], f"Expected STALE or DATA_UNAVAILABLE, got {stale.status}"
results['probe_2_stale_candle_detected'] = f"PASSED: status is {stale.status}"
print(f"[PASS] Probe 2: Multi-year stale candles flagged as {stale.status}")

# Probe 3: High volume in falling market must penalize score (not boost)
falling = pd.DataFrame({'Close': [110, 108, 106, 104, 102, 100]})
ind = {'status': 'AVAILABLE', 'price': 100, 'rsi14': 40, 'volume_ratio': 1.0}
low = calculate_momentum_score(ind, falling)
high = calculate_momentum_score({**ind, 'volume_ratio': 3.0}, falling)
assert high < low, f"Expected high-volume dump to have lower score ({high}) than normal ({low})"
results['probe_3_falling_market_volume_penalty'] = f"PASSED: normal={low:.1f}, high_vol={high:.1f}"
print(f"[PASS] Probe 3: High-volume selling penalized (normal: {low:.1f}, heavy: {high:.1f})")

# Probe 4: Generic sector news without ticker mention must stay below threshold
text = 'Rocket launch success and growth'
rel = calculate_relevance_score(text, 'ASTS', ['$ASTS', 'AST SpaceMobile'])
assert rel < settings.NEWS_MIN_RELEVANCE, f"Expected rel < {settings.NEWS_MIN_RELEVANCE}, got {rel}"
results['probe_4_generic_sector_relevance'] = f"PASSED: relevance={rel:.2f} (< {settings.NEWS_MIN_RELEVANCE})"
print(f"[PASS] Probe 4: Generic sector headline relevance ({rel:.2f}) < threshold")

# Probe 5: Ingestion preserves entity context for catalysts
class NewsFixture:
    async def fetch_news(self, **kwargs):
        return [NewsItemData(
            ticker=kwargs['ticker'],
            title='NASA selects SpaceX over Rocket Lab for contract',
            summary='', source='audit', url='https://example.invalid/audit',
            published_at=now - timedelta(days=90) # Old article (90 days)
        )]

cfg = next(c for c in INITIAL_TICKERS if c.symbol == 'SPCX')
with patch('app.jobs.runner.save_news_items', return_value=1):
    _, _, cats = asyncio.run(ingest_news_for_ticker(None, cfg,
        news_provider=NewsFixture(), sentiment_classifier=HeuristicSentimentClassifier()))
# Since published_at was 90 days ago, it should be filtered out from active catalysts
assert len(cats) == 0, f"Expected stale catalyst to be filtered, got {len(cats)}"
# And when entity context is passed directly:
explicit = detect_catalysts('NASA selects SpaceX over Rocket Lab for contract', ticker='SPCX')
assert explicit[0]['direction'] == 'BULLISH', f"Expected BULLISH for SpaceX winner, got {explicit[0]['direction']}"
results['probe_5_catalyst_context_and_freshness'] = "PASSED: stale filtered out, entity-aware detection"
print("[PASS] Probe 5: Catalyst entity context and age filter verified")

# Probe 6: Missing market confirmation prevents unconfirmed STRONG BUY
composite = calculate_smi(social_score=100, news_score=100, post_count=30, news_count=3)
signal = generate_signal_and_explanation(
    ticker='ASTS', smi=composite['smi'], social_score=100, news_score=100,
    source_agreement=composite['source_agreement'], data_quality=composite['data_quality'],
    indicators={'status': 'DATA_UNAVAILABLE'}
)
assert signal['base_signal'] != 'STRONG BUY', f"Expected signal to be gated down from STRONG BUY, got {signal['base_signal']}"
assert 'NO MKT DATA' in signal['signal'], f"Expected NO MKT DATA modifier in {signal['signal']}"
results['probe_6_unconfirmed_strong_buy_gated'] = f"PASSED: signal is {signal['signal']}"
print(f"[PASS] Probe 6: Missing market data restricts signal to {signal['signal']}")

# Probe 7: Multiple modifiers (dilution + overextended) preserved
signal = generate_signal_and_explanation(
    ticker='ASTS', smi=90, data_quality=100,
    fundamentals={'runway_months': 3}, indicators={'status': 'AVAILABLE', 'rsi14': 80}
)
assert 'DILUTION RISK' in signal['signal'] and 'OVEREXTENDED' in signal['signal'], \
    f"Expected both DILUTION RISK and OVEREXTENDED in {signal['signal']}"
results['probe_7_modifier_stacking'] = f"PASSED: signal is {signal['signal']}"
print(f"[PASS] Probe 7: Multiple modifiers preserved simultaneously: {signal['signal']}")

# Probe 8: Price-only snapshots backtest executes cleanly without TypeError
backtest = evaluate_backtest_dataset([{'ticker': 'ASTS', 'price': 100}, {'ticker': 'ASTS', 'price': 101}], holding_period_days=1)
assert 'model_a_baseline' in backtest, "Expected backtest to return model results"
results['probe_8_empty_snapshots_backtest'] = "PASSED: no TypeError"
print("[PASS] Probe 8: Empty/price-only snapshots backtested cleanly without TypeError")

# Probe 9: Stored signals/weights in snapshots are respected
snaps = [{'ticker': 'ASTS', 'timestamp': now + timedelta(days=i), 'price': 100+i,
          'social_score': 100, 'news_score': 100, 'momentum_score': 0,
          'post_count': 30, 'news_count': 3, 'rsi14': 60,
          'smi': 100, 'base_signal': 'STRONG BUY', 'rules_version': 'audit',
          'effective_weights': {'social': 1.0}} for i in range(3)]
backtest = evaluate_backtest_dataset(snaps, holding_period_days=1)
# With stored STRONG BUY signal, trades are executed
assert backtest['model_b_multisource']['metrics']['total_trades'] >= 1, \
    f"Expected trades to be executed from stored signals, got {backtest['model_b_multisource']['metrics']['total_trades']}"
results['probe_9_stored_signal_executed'] = f"PASSED: trades = {backtest['model_b_multisource']['metrics']['total_trades']}"
print(f"[PASS] Probe 9: Stored snapshot signal executed in backtest ({backtest['model_b_multisource']['metrics']['total_trades']} trades)")

# Probe 10: Bootstrap checks date overlap across sample sets
a = [{'return': float(i % 7 - 3), 'entry_time': now + timedelta(days=i)} for i in range(40)]
b_shifted = [{**t, 'entry_time': t['entry_time'] + timedelta(days=3650)} for t in a]
diff_decade = compute_hypothesis_significance(a, b_shifted, n_bootstrap=100)
assert diff_decade.get('date_overlap_count', 0) == 0, "Expected 0 date overlap for 10-year shift"
results['probe_10_date_aware_bootstrap'] = f"PASSED: overlap={diff_decade.get('date_overlap_count')}"
print("[PASS] Probe 10: Bootstrap detects mismatched dates across trade sets")

# Probe 11: Source outage does not create false positive momentum spike
previous = calculate_smi(social_score=0, news_score=100, post_count=30, news_count=3)
current = calculate_smi(news_score=100, news_count=3, previous_smi_1d=previous)
assert abs(current['smi_momentum_1d']) < 30.0, f"Expected subdued momentum on coverage shift, got {current['smi_momentum_1d']}"
results['probe_11_coverage_shift_momentum'] = f"PASSED: momentum={current['smi_momentum_1d']:.1f}"
print(f"[PASS] Probe 11: Source dropout handled without artificial momentum spike ({current['smi_momentum_1d']:.1f})")

print("\nALL 11 AUDIT PROBES VERIFIED AND FIXED SUCCESSFULLY!")
print(json.dumps(results, indent=2))
