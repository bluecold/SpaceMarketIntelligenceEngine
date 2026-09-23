"""Offline audit probes. Run: python -m audit.reproduce_signal_audit

These assert observed defects, not desired behavior. No production DB access,
network calls, or strategy changes. Settings are overridden only in this process.
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

settings.WEIGHT_SOCIAL = 0.30
settings.WEIGHT_PREDICTION = 0.15
settings.WEIGHT_NEWS = 0.20
settings.WEIGHT_MOMENTUM = 0.20
settings.WEIGHT_FUNDAMENTALS = 0.10
settings.WEIGHT_RISK = 0.05
settings.ENABLE_DYNAMIC_WEIGHT_FEEDBACK = False
settings.POLYMARKET_MIN_QUALITY = 30
settings.THRESHOLD_STRONG_BUY = 85
settings.THRESHOLD_BUY = 75
settings.THRESHOLD_WATCH = 65
settings.THRESHOLD_HOLD = 50
settings.THRESHOLD_AVOID = 35
settings.NEWS_MIN_RELEVANCE = 0.40
settings.VOLUME_RATIO_INSTITUTIONAL_BUY = 1.2
settings.VOLUME_RATIO_WEAKNESS = 0.8

now = datetime.now(timezone.utc)
results = {}

# 1. Resolved markets continue contributing to the live scorer.
market = PredictionMarketData(external_id='audit', ticker='ASTS', title='ASTS success',
    created_at=now, end_date=now - timedelta(days=2), status='RESOLVED',
    yes_probability=1, no_probability=0, quality_score=90)
pms = calculate_prediction_market_score('ASTS', [market])
assert pms[0] == 80
results['closed_market_pms'] = pms[0]

# 2. Old candles returned by the provider are marked AVAILABLE.
df = pd.DataFrame({'Open': [100]*30, 'High': [101]*30, 'Low': [99]*30,
                   'Close': [100]*30, 'Volume': [1000]*30},
                  index=pd.date_range('2020-01-01', periods=30, tz='America/New_York'))
with patch('app.collectors.market_provider.yf.Ticker', return_value=SimpleNamespace(history=lambda **kw: df)):
    stale = _fetch_market_data_sync('ASTS')
assert stale.status == 'AVAILABLE'
results['stale_candle'] = {'date': stale.candle_date, 'status': stale.status}

# 3. A high-volume falling market receives a bullish boost.
falling = pd.DataFrame({'Close': [110, 108, 106, 104, 102, 100]})
ind = {'status': 'AVAILABLE', 'price': 100, 'rsi14': 40, 'volume_ratio': 1}
low = calculate_momentum_score(ind, falling)
high = calculate_momentum_score({**ind, 'volume_ratio': 3}, falling)
assert high > low
results['falling_market_volume_bonus'] = {'normal': low, 'high_volume': high}

# 4. A generic sector headline qualifies for ASTS without mentioning it.
text = 'Rocket launch success and growth'
rel = calculate_relevance_score(text, 'ASTS', ['$ASTS', 'AST SpaceMobile'])
sent = HeuristicSentimentClassifier().analyze(text)
news = calculate_news_score([SimpleNamespace(relevance_score=rel,
    sentiment_score=sent.score, sentiment_label=sent.label,
    sentiment_confidence=sent.confidence, published_at=now)])
assert rel == 0.4 and news['news_score'] > 75
results['unrelated_sector_news'] = {'relevance': rel, 'news_score': news['news_score']}

# 5. Ingestion loses the ticker context and admits old critical catalysts.
class NewsFixture:
    async def fetch_news(self, **kwargs):
        return [NewsItemData(ticker=kwargs['ticker'],
            title='NASA selects SpaceX over Rocket Lab for contract',
            summary='', source='audit', url='https://example.invalid/audit',
            published_at=now - timedelta(days=90))]

cfg = next(c for c in INITIAL_TICKERS if c.symbol == 'SPCX')
with patch('app.jobs.runner.save_news_items', return_value=1):
    _, _, cats = asyncio.run(ingest_news_for_ticker(None, cfg,
        news_provider=NewsFixture(), sentiment_classifier=HeuristicSentimentClassifier()))
explicit = detect_catalysts('NASA selects SpaceX over Rocket Lab for contract', ticker='SPCX')
assert cats[0]['direction'] == 'BEARISH' and explicit[0]['direction'] == 'BULLISH'
results['old_winner_headline_catalyst'] = {'ingestion': cats[0], 'with_entity_context': explicit[0]}

# 6. Missing market confirmation does not prevent a strong buy.
composite = calculate_smi(social_score=100, news_score=100, post_count=30, news_count=3)
signal = generate_signal_and_explanation(ticker='ASTS', smi=composite['smi'],
    social_score=100, news_score=100, source_agreement=composite['source_agreement'],
    data_quality=composite['data_quality'], indicators={'status': 'DATA_UNAVAILABLE'})
assert signal['base_signal'] == 'STRONG BUY'
results['no_market_signal'] = {'signal': signal['signal'], 'quality': composite['data_quality']}

# 7. Modifiers overwrite material warnings.
signal = generate_signal_and_explanation(ticker='ASTS', smi=90, data_quality=100,
    fundamentals={'runway_months': 3}, indicators={'status': 'AVAILABLE', 'rsi14': 80})
assert signal['signal_modifier'] == 'OVEREXTENDED'
results['lost_dilution_modifier'] = signal['signal']

# 8. Price-only snapshots cause a TypeError in the backtest.
try:
    evaluate_backtest_dataset([{'ticker': 'ASTS', 'price': 100},
                               {'ticker': 'ASTS', 'price': 101}], holding_period_days=1)
except TypeError as exc:
    results['empty_score_backtest_exception'] = str(exc)
else:
    raise AssertionError('Expected None-vs-float TypeError')

# 9. Stored weights/signal/strategy version have no effect on the evaluation.
snaps = [{'ticker': 'ASTS', 'timestamp': now + timedelta(days=i), 'price': 100+i,
          'social_score': 100, 'news_score': 100, 'momentum_score': 0,
          'post_count': 30, 'news_count': 3, 'rsi14': 60,
          'smi': 100, 'base_signal': 'STRONG BUY', 'rules_version': 'audit',
          'effective_weights': {'social': 1.0}} for i in range(3)]
backtest = evaluate_backtest_dataset(snaps, holding_period_days=1)
assert backtest['model_b_multisource']['metrics']['total_trades'] == 0
results['stored_strong_buy_ignored'] = backtest['model_b_multisource']['metrics']['total_trades']

# 10. Bootstrap results ignore all dates, even non-overlapping years.
a = [{'return': float(i % 7 - 3), 'entry_time': now + timedelta(days=i)} for i in range(40)]
b = [{'return': t['return'] + 0.5, 'entry_time': t['entry_time']} for t in a]
b_shifted = [{**t, 'entry_time': t['entry_time'] + timedelta(days=3650)} for t in b]
same_dates = compute_hypothesis_significance(a, b, n_bootstrap=100)
other_decade = compute_hypothesis_significance(a, b_shifted, n_bootstrap=100)
assert same_dates == other_decade
results['bootstrap_ignores_dates'] = {'same_result': True, 'ci': same_dates['confidence_interval_95']}

# 11. A source outage alone creates a large positive SMI momentum.
previous = calculate_smi(social_score=0, news_score=100, post_count=30, news_count=3)
current = calculate_smi(news_score=100, news_count=3, previous_smi_1d=previous['smi'])
assert current['smi_momentum_1d'] == 60
results['source_dropout_momentum'] = {'before': previous['smi'], 'after': current['smi'],
                                      'delta': current['smi_momentum_1d']}

print(json.dumps(results, indent=2, ensure_ascii=True))
