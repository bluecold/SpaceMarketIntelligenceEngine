import logging
from collections import Counter
from datetime import timedelta
from typing import Any, Callable, Dict, Optional

from sqlalchemy.orm import Session

from app.database.models import SocialPostModel
from app.database.repository import utc_now
from app.sentiment.classifier import BaseSentimentClassifier, get_social_sentiment_classifier
from app.sentiment.weighting import detect_catalysts, reconcile_sentiment_with_catalyst

logger = logging.getLogger("SMIE.Reclassify")


def reclassify_social_posts(
    db: Session,
    days: int = 14,
    classifier: Optional[BaseSentimentClassifier] = None,
    batch_size: int = 256,
    only_other_models: bool = True,
    on_batch: Optional[Callable[[int, int], None]] = None
) -> Dict[str, Any]:
    """
    Re-runs the X/Twitter classifier on stored posts created in the last `days`, applying the same
    catalyst detection and catalyst/sentiment reconciliation as live ingestion.

    Used when the social model changes, so the 14-day SSI baseline is not built from a mix of models.
    Posts already labelled by the current model are skipped unless only_other_models=False.
    Aborts without writing a batch if the transformer falls back to the heuristic lexicon, so a model
    loading failure never silently overwrites history with lower-quality labels.
    """
    classifier = classifier or get_social_sentiment_classifier()
    target_model = classifier.model_id
    since = utc_now() - timedelta(days=days)

    posts = db.query(SocialPostModel).filter(SocialPostModel.created_at >= since).order_by(SocialPostModel.id).all()
    if only_other_models:
        posts = [p for p in posts if p.sentiment_model != target_model]

    before = Counter(p.sentiment_label for p in posts)
    after: Counter = Counter()
    changed = 0

    for start in range(0, len(posts), batch_size):
        batch = posts[start:start + batch_size]
        results = classifier.analyze_batch([p.text or "" for p in batch])
        if classifier.model_id != target_model:
            db.rollback()
            raise RuntimeError(
                f"Social model '{target_model}' was unavailable (fell back to '{classifier.model_id}'); "
                f"reclassification aborted after {start} posts."
            )

        for post, res in zip(batch, results):
            cats = detect_catalysts(post.text or "", ticker=post.ticker)
            top = cats[0] if cats else None
            score, label, conf = reconcile_sentiment_with_catalyst(res.score, res.label, res.confidence, top)
            if label != post.sentiment_label:
                changed += 1
            post.sentiment_score = score
            post.sentiment_label = label
            post.sentiment_confidence = conf
            post.catalyst = top["category"] if top else None
            post.catalyst_direction = top["direction"] if top else None
            post.catalyst_importance = top["importance"] if top else "MEDIUM"
            post.sentiment_model = target_model
            after[label] += 1

        db.commit()
        if on_batch:
            on_batch(start + len(batch), len(posts))

    logger.info(f"Reclassified {len(posts)} posts with {target_model} ({changed} label changes).")
    return {
        "model": target_model,
        "days": days,
        "processed": len(posts),
        "label_changes": changed,
        "labels_before": dict(before),
        "labels_after": dict(after)
    }
