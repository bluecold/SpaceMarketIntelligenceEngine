"""Second audit: offline counterexamples, not desired-behavior regression tests.

Run: python -m audit.review_round2
Uses only an in-memory database and mocked HTTP/market providers.
"""
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['ENABLE_SCHEDULER'] = 'false'

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings, INITIAL_TICKERS
from app.database.connection import Base
from app.database.models import AlertModel, PredictionMarketSnapshotModel
from app.database.repository import save_alerts, save_prediction_markets
from app.collectors.base import PredictionMarketData
from app.collectors.market_provider import _fetch_market_data_sync
from app.collectors.news_provider import GoogleRSSNewsProvider
from app.jobs.runner import ingest_news_for_ticker
from app.backtesting.engine import compute_hypothesis_significance, evaluate_backtest_dataset
from app.scoring.smi import calculate_smi
from app.scoring.signal import generate_signal_and_explanation
from app.technical.scorer import calculate_technical_score
from app.sentiment.weighting import detect_catalysts
from app.sentiment.classifier import HeuristicSentimentClassifier

for key, value in dict(WEIGHT_SOCIAL=.30, WEIGHT_PREDICTION=.15, WEIGHT_NEWS=.20,
        WEIGHT_MOMENTUM=.20, WEIGHT_FUNDAMENTALS=.10, WEIGHT_RISK=.05,
        ENABLE_DYNAMIC_WEIGHT_FEEDBACK=False, POLYMARKET_MIN_QUALITY=30,
        THRESHOLD_STRONG_BUY=85, THRESHOLD_BUY=75, THRESHOLD_WATCH=65,
        THRESHOLD_HOLD=50, THRESHOLD_AVOID=35).items():
    setattr(settings, key, value)

results = {}
now = datetime(2026, 9, 24, 16, tzinfo=timezone.utc)

# R2-01: one overlapping date does not establish paired samples.
a = [{'return': float(i % 7 - 3), 'entry_time': now + timedelta(days=i)} for i in range(40)]
b = [{'return': t['return'] + .5, 'entry_time': t['entry_time']} for t in a]
misaligned = [{**t, 'entry_time': t['entry_time'] + (timedelta(0) if i == 0 else timedelta(days=3650))}
              for i, t in enumerate(b)]
aligned_stats = compute_hypothesis_significance(a, b, n_bootstrap=100)
bad_stats = compute_hypothesis_significance(a, misaligned, n_bootstrap=100)
assert aligned_stats == bad_stats and bad_stats['positive_edge_significant']
results['one_shared_date_bootstrap'] = bad_stats
iso_b = [{**t, 'entry_time': t['entry_time'].isoformat()} for t in b]
iso_stats = compute_hypothesis_significance(a, iso_b, n_bootstrap=100)
assert 'No calendar date overlap' in iso_stats['test_method']
results['equivalent_iso_dates_rejected'] = iso_stats['test_method']

# R2-02: pipeline supplies RAW historical social scores to an effective-score comparison.
prior = calculate_smi(social_score=0, news_score=50, fundamental_score=50, post_count=1, news_count=3)
curr = calculate_smi(social_score=0, news_score=50, post_count=1, news_count=3,
    previous_smi_1d=prior['smi'], previous_active_pillars=['social', 'news', 'fundamental'],
    previous_scores={'social': 0, 'news': 50, 'fundamental': 50})
assert curr['smi_momentum_1d'] == 27
results['unchanged_evidence_false_momentum'] = curr['smi_momentum_1d']
prior2 = calculate_smi(social_score=0, news_score=100, post_count=30, news_count=3)
curr2 = calculate_smi(news_score=100, news_count=3, previous_smi_1d=prior2,
                      previous_smi_3d=prior2, previous_smi_5d=prior2)
assert curr2['smi_momentum_1d'] == 0 and curr2['smi_momentum_3d'] == 60
results['coverage_delta_horizons'] = {k: curr2[k] for k in ['smi_momentum_1d', 'smi_momentum_3d', 'smi_momentum_5d']}

# R2-03: final weights undergo quality modulation for a second time.
inputs = dict(social_score=100, prediction_score=0, prediction_quality=50,
    news_score=100, momentum_score=100, fundamental_score=100, risk_score=100,
    post_count=30, news_count=3, prediction_count=1)
original = calculate_smi(**inputs)
replayed = calculate_smi(**inputs, custom_weights=original['effective_weights'])
assert original['smi'] != replayed['smi']
results['double_quality_weight'] = {'original': original['smi'], 'replayed': replayed['smi']}

# Stored production arm vs current-rules control differs even WITHOUT Polymarket.
snaps = [{'ticker': 'ASTS', 'timestamp': now + timedelta(days=i), 'price': 100+i,
    'social_score': 100, 'news_score': 100, 'momentum_score': 100,
    'post_count': 30, 'news_count': 3, 'prediction_score': None,
    'rsi14': 80, 'market_status': 'AVAILABLE', 'smi': 90,
    'base_signal': 'BUY', 'rules_version': 'historical-fixture'} for i in range(3)]
comparison = evaluate_backtest_dataset(snaps, holding_period_days=1)
na = comparison['model_a_baseline']['metrics']['total_trades']
nb = comparison['model_b_multisource']['metrics']['total_trades']
assert na == 0 and nb == 2
results['different_rules_without_polymarket'] = {'model_a': na, 'model_b': nb}

# R2-04: stale quote spanning several open sessions still AVAILABLE.
class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return now.astimezone(tz) if tz else now.replace(tzinfo=None)

df = pd.DataFrame({'Open': [100]*30, 'High': [101]*30, 'Low': [99]*30,
    'Close': [100]*30, 'Volume': [1000]*30},
    index=pd.bdate_range(end='2026-09-21', periods=30, tz='America/New_York'))
with patch('app.collectors.market_provider.datetime', FixedDatetime), patch(
    'app.collectors.market_provider.yf.Ticker', return_value=SimpleNamespace(history=lambda **kw: df)):
    quote = _fetch_market_data_sync('ASTS')
assert quote.status == 'AVAILABLE'
results['monday_price_on_thursday'] = {'candle_date': quote.candle_date, 'status': quote.status}

# R2-05: actual repository behavior, isolated SQLite DB.
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
with Session(engine) as db:
    m = PredictionMarketData(external_id='audit-r2', ticker='ASTS', title='ASTS launch',
        created_at=now, yes_probability=.5, no_probability=.5, probability_change_24h=0)
    save_prediction_markets(db, [m])
    old = db.query(PredictionMarketSnapshotModel).one()
    old.timestamp = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24)
    db.commit()
    current = m.model_copy(update={'yes_probability': .7, 'no_probability': .3, 'probability_change_24h': 0})
    save_prediction_markets(db, [current])
    assert current.probability_change_24h == 20
    results['explicit_zero_overwritten'] = current.probability_change_24h

    alert = {'id': 'ASTS:CATALYST:AUDIT', 'type': 'CRITICAL_CATALYST', 'category': 'CATALYST',
             'level': 'CRITICAL', 'message': 'audit fixture'}
    try:
        save_alerts(db, 'ASTS', [alert])
        raise RuntimeError('simulated snapshot persistence failure')
    except RuntimeError:
        db.rollback()
    assert db.query(AlertModel).count() == 1
    results['alert_survives_outer_rollback'] = True

    # HTTP 503 is swallowed by collector; ingestion appears successful to runner.
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = SimpleNamespace(status_code=503)
    cfg = next(c for c in INITIAL_TICKERS if c.symbol == 'ASTS')
    with patch('app.collectors.news_provider.httpx.AsyncClient', return_value=client):
        saved, news, catalysts = asyncio.run(ingest_news_for_ticker(db, cfg,
            news_provider=GoogleRSSNewsProvider(), sentiment_classifier=HeuristicSentimentClassifier()))
    assert (saved, news, catalysts) == (0, [], [])
    save_alerts(db, 'ASTS', catalysts, resolve_missing=True)
    assert db.query(AlertModel).one().resolved_at is not None
    results['http_503_looks_successful_and_resolves_alert'] = True

# R2-06: two remaining semantic/directional counterexamples.
headline = 'Rocket Lab beats SpaceX for NASA contract'
winner = detect_catalysts(headline, ticker='RKLB')[0]
loser = detect_catalysts(headline, ticker='SPCX')[0]
assert winner['direction'] == 'BEARISH' and loser['direction'] == 'BULLISH'
results['beats_pattern_reverses_winner'] = {'RKLB': winner['direction'], 'SPCX': loser['direction']}
sentiment = HeuristicSentimentClassifier().analyze('NASA cancels Rocket Lab contract')
assert sentiment.label == 'NEUTRAL'
results['contract_cancellation_sentiment'] = sentiment.model_dump()

technical = dict(status='AVAILABLE', price=100, ema200=110, rsi14=40,
    bollinger_upper=110, bollinger_middle=105, bollinger_lower=95,
    macd_histogram=-1, atr=2, price_change_1d=-5, candle_score=-1)
t1 = calculate_technical_score({**technical, 'volume_ratio': 1})
t3 = calculate_technical_score({**technical, 'volume_ratio': 3})
assert t3 > t1
results['technical_bearish_volume_bonus'] = {'normal': t1, 'high_volume': t3}

# Missing price bypasses gate when status is omitted; explicit unavailability still permits BUY.
no_status = generate_signal_and_explanation(ticker='ASTS', smi=95, data_quality=100, indicators={})
unavailable = generate_signal_and_explanation(ticker='ASTS', smi=95, data_quality=100,
    indicators={'status': 'DATA_UNAVAILABLE'})
assert no_status['base_signal'] == 'STRONG BUY' and unavailable['base_signal'] == 'BUY'
results['market_gate'] = {'without_status': no_status['signal'], 'unavailable': unavailable['signal']}

engine.dispose()
print(json.dumps(results, indent=2, ensure_ascii=True))
