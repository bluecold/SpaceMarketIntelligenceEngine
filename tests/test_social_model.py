import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.config import INITIAL_TICKERS, settings
from app.database.connection import SessionLocal
from app.database.models import SocialPostModel
from app.database.repository import save_social_posts
from app.sentiment import classifier as classifier_module
from app.sentiment.classifier import FinBERTSentimentClassifier, HeuristicSentimentClassifier


def _fake_pipeline(prob_by_text):
    """Mimics a HuggingFace text-classification pipeline with top_k=None."""
    def run(texts, truncation=True, max_length=128, **kwargs):
        return [[{"label": k, "score": v} for k, v in prob_by_text[t].items()] for t in texts]
    return run


def test_fintwit_labels_with_high_threshold():
    """
    FinTwitBERT emits BULLISH/BEARISH/NEUTRAL labels; only |P(bull) - P(bear)| >= 0.90 counts as an opinion.
    A 0.78 bullish margin (opinion for FinBERT's 0.20 rule) stays NEUTRAL.
    """
    clf = FinBERTSentimentClassifier("StephanAkkerman/FinTwitBERT-sentiment", label_threshold=0.90)
    clf.pipeline = _fake_pipeline({
        "strong bull": {"BULLISH": 0.95, "BEARISH": 0.02, "NEUTRAL": 0.03},
        "weak bull": {"BULLISH": 0.85, "BEARISH": 0.07, "NEUTRAL": 0.08},
        "strong bear": {"BULLISH": 0.01, "BEARISH": 0.97, "NEUTRAL": 0.02},
    })
    res = clf.analyze_batch(["strong bull", "weak bull", "strong bear"])
    assert [r.label for r in res] == ["BULLISH", "NEUTRAL", "BEARISH"]
    assert res[1].score == pytest.approx(0.78)
    assert clf.model_id == "StephanAkkerman/FinTwitBERT-sentiment"


def test_finbert_vocabulary_unchanged():
    """FinBERT's positive/negative/neutral labels keep the 0.20 rule."""
    clf = FinBERTSentimentClassifier("ProsusAI/finbert")
    clf.pipeline = _fake_pipeline({"x": {"positive": 0.55, "negative": 0.10, "neutral": 0.35}})
    res = clf.analyze("x")
    assert res.label == "BULLISH" and res.score == pytest.approx(0.45)


def test_inference_failure_falls_back_and_reports_heuristic_model():
    """If inference fails, labels come from the lexicon and model_id says so (so they are never stored as FinTwit)."""
    clf = FinBERTSentimentClassifier("StephanAkkerman/FinTwitBERT-sentiment", label_threshold=0.90)

    def broken(texts, truncation=True, max_length=128, **kwargs):
        raise RuntimeError("boom")
    clf.pipeline = broken
    res = clf.analyze_batch(["$ASTS short squeeze incoming"])
    assert res[0].label == "BULLISH"
    assert clf.model_id == "heuristic-lexicon"


def test_social_and_news_classifiers_are_separate(monkeypatch):
    """Tweets use SOCIAL_SENTIMENT_MODEL/THRESHOLD; news keep SENTIMENT_MODEL; lexicon when transformers are off."""
    monkeypatch.setattr(classifier_module, "_classifier_instance", None)
    monkeypatch.setattr(classifier_module, "_social_classifier_instance", None)
    monkeypatch.setattr(settings, "USE_FINBERT", True)
    monkeypatch.setattr(settings, "SENTIMENT_MODEL", "ProsusAI/finbert")
    monkeypatch.setattr(settings, "SOCIAL_SENTIMENT_MODEL", "StephanAkkerman/FinTwitBERT-sentiment")
    monkeypatch.setattr(settings, "SOCIAL_SENTIMENT_THRESHOLD", 0.90)

    social = classifier_module.get_social_sentiment_classifier()
    news = classifier_module.get_sentiment_classifier()
    assert social.model_name == "StephanAkkerman/FinTwitBERT-sentiment" and social.label_threshold == 0.90
    assert news.model_name == "ProsusAI/finbert" and news.label_threshold == 0.20

    monkeypatch.setattr(classifier_module, "_social_classifier_instance", None)
    monkeypatch.setattr(settings, "USE_FINBERT", False)
    assert isinstance(classifier_module.get_social_sentiment_classifier(), HeuristicSentimentClassifier)


class _FakeSocialClassifier(HeuristicSentimentClassifier):
    """Labels every post BULLISH +0.95 and reports itself as FinTwitBERT."""
    def __init__(self, model_id="StephanAkkerman/FinTwitBERT-sentiment", fail=False):
        self._model_id = model_id
        self.fail = fail

    @property
    def model_id(self):
        return "heuristic-lexicon" if self.fail else self._model_id

    def analyze_batch(self, texts):
        from app.sentiment.classifier import SentimentResult
        return [SentimentResult(score=0.95, label="BULLISH", confidence=0.96) for _ in texts]


def _seed_posts(db, prefix, n=3, created=None):
    created = created or datetime.now(timezone.utc) - timedelta(hours=2)
    save_social_posts(db, [{
        "tweet_id": f"{prefix}_{i}", "ticker": "ASTS", "username": f"u{i}", "text": f"$ASTS long thesis post {i}",
        "created_at": created, "sentiment_score": 0.0, "sentiment_label": "NEUTRAL", "sentiment_confidence": 0.9,
        "relevance_score": 1.0, "source": "LIVE"
    } for i in range(n)])


def _cleanup(db, prefix):
    db.query(SocialPostModel).filter(SocialPostModel.tweet_id.like(f"{prefix}_%")).delete(synchronize_session=False)
    db.commit()


def test_reclassify_updates_history_once_and_records_model():
    """Posts in the window are relabelled and tagged with the model; a second run skips them; old posts are untouched."""
    from app.jobs.reclassify import reclassify_social_posts

    db = SessionLocal()
    try:
        _cleanup(db, "rc")
        _seed_posts(db, "rc", n=3)
        _seed_posts(db, "rc_old", n=2, created=datetime.now(timezone.utc) - timedelta(days=30))

        res = reclassify_social_posts(db, days=14, classifier=_FakeSocialClassifier())
        mine = db.query(SocialPostModel).filter(SocialPostModel.tweet_id.like("rc_%")).all()
        recent = [p for p in mine if not p.tweet_id.startswith("rc_old")]
        old = [p for p in mine if p.tweet_id.startswith("rc_old")]
        assert res["processed"] >= 3
        assert all(p.sentiment_label == "BULLISH" and p.sentiment_model == "StephanAkkerman/FinTwitBERT-sentiment" for p in recent)
        assert all(p.sentiment_label == "NEUTRAL" and p.sentiment_model is None for p in old)

        # Second run with the same model id: already-labelled posts are skipped (a BEARISH relabel would show it)
        class _Bearish(_FakeSocialClassifier):
            def analyze_batch(self, texts):
                from app.sentiment.classifier import SentimentResult
                return [SentimentResult(score=-0.95, label="BEARISH", confidence=0.96) for _ in texts]

        reclassify_social_posts(db, days=14, classifier=_Bearish())
        db.expire_all()
        recent = db.query(SocialPostModel).filter(SocialPostModel.tweet_id.in_([f"rc_{i}" for i in range(3)])).all()
        assert all(p.sentiment_label == "BULLISH" for p in recent)
    finally:
        _cleanup(db, "rc")
        _cleanup(db, "rc_old")
        db.close()


def test_reclassify_aborts_when_model_falls_back():
    """A model that silently falls back to the lexicon must not overwrite stored labels."""
    from app.jobs.reclassify import reclassify_social_posts

    db = SessionLocal()
    try:
        _cleanup(db, "rcf")
        _seed_posts(db, "rcf", n=2)

        class _FallsBack(_FakeSocialClassifier):
            def analyze_batch(self, texts):
                self.fail = True
                return super().analyze_batch(texts)

        with pytest.raises(RuntimeError, match="reclassification aborted"):
            reclassify_social_posts(db, days=14, classifier=_FallsBack())
        db.expire_all()
        stored = db.query(SocialPostModel).filter(SocialPostModel.tweet_id.like("rcf_%")).all()
        assert all(p.sentiment_label == "NEUTRAL" and p.sentiment_model is None for p in stored)
    finally:
        _cleanup(db, "rcf")
        db.close()


def test_ingestion_stores_sentiment_model_and_lang():
    """Live ingestion records which model labelled each post and X's language code."""
    from app.collectors.base import SocialPostData
    from app.jobs.runner import ingest_social_posts_for_ticker

    class _Provider:
        async def search(self, query, ticker, max_results=100):
            return [SocialPostData(tweet_id="ing_1", ticker=ticker, username="a", text="$ASTS loading more shares",
                                   created_at=datetime.now(timezone.utc), lang="en")]

    db = SessionLocal()
    try:
        _cleanup(db, "ing")
        cfg = next(t for t in INITIAL_TICKERS if t.symbol == "ASTS")
        asyncio.run(ingest_social_posts_for_ticker(db, cfg, x_provider=_Provider(), sentiment_classifier=_FakeSocialClassifier()))
        post = db.query(SocialPostModel).filter(SocialPostModel.tweet_id == "ing_1").one()
        assert post.sentiment_model == "StephanAkkerman/FinTwitBERT-sentiment"
        assert post.lang == "en"
    finally:
        _cleanup(db, "ing")
        db.close()
