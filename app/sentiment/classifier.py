import re
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger(__name__)


class SentimentResult(BaseModel):
    score: float  # -1.0 to +1.0
    label: str  # BULLISH, BEARISH, NEUTRAL
    confidence: float  # 0.0 to 1.0


class BaseSentimentClassifier(ABC):
    @abstractmethod
    def analyze(self, text: str) -> SentimentResult:
        pass

    def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        return [self.analyze(t) for t in texts]


class HeuristicSentimentClassifier(BaseSentimentClassifier):
    """Fast, deterministic finance lexicon & keyword sentiment analyzer for rapid dev & testing."""
    
    BULLISH_KEYWORDS = [
        "bull", "bullish", "moon", "rocket", "buy", "buying", "long", "call", "calls",
        "milestone", "launch", "contract", "revenue", "growth", "breakout", "deployment",
        "fcc", "nasa", "partner", "partnership", "success", "upgrade", "record", "high",
        "gamechanger", "expansion", "profit", "profitable", "satellite"
    ]
    
    BEARISH_KEYWORDS = [
        "bear", "bearish", "short", "shorts", "sell", "selling", "put", "puts", "dilution",
        "capital raise", "offering", "downgrade", "delay", "delayed", "failure", "fail",
        "burn", "cash burn", "drop", "dropped", "loss", "losses", "risk", "bankruptcy",
        "lawsuit", "investigation", "stretched", "overvalued"
    ]

    def analyze(self, text: str) -> SentimentResult:
        clean_text = text.lower()
        
        bull_hits = sum(1 for kw in self.BULLISH_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', clean_text))
        bear_hits = sum(1 for kw in self.BEARISH_KEYWORDS if re.search(r'\b' + re.escape(kw) + r'\b', clean_text))
        
        total_hits = bull_hits + bear_hits
        if total_hits == 0:
            return SentimentResult(score=0.0, label="NEUTRAL", confidence=0.7)

        score = (bull_hits - bear_hits) / float(total_hits)
        score = max(-1.0, min(1.0, score))

        if score >= 0.20:
            label = "BULLISH"
        elif score <= -0.20:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        confidence = min(0.95, 0.5 + 0.15 * total_hits)
        return SentimentResult(score=round(score, 3), label=label, confidence=round(confidence, 2))


class FinBERTSentimentClassifier(BaseSentimentClassifier):
    """HuggingFace ProsusAI/finbert model with lazy loading and batch processing."""
    
    def __init__(self, model_name: str = "ProsusAI/finbert"):
        self.model_name = model_name
        self.pipeline = None

    def _load_model(self):
        if self.pipeline is not None:
            return
        try:
            from transformers import pipeline
            logger.info(f"Loading FinBERT model '{self.model_name}'...")
            self.pipeline = pipeline("text-classification", model=self.model_name, return_all_scores=True)
            logger.info("FinBERT model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load FinBERT model ({e}). Falling back to Heuristic classifier.")
            self.pipeline = None

    def analyze(self, text: str) -> SentimentResult:
        results = self.analyze_batch([text])
        return results[0]

    def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        self._load_model()
        if self.pipeline is None:
            fallback = HeuristicSentimentClassifier()
            return fallback.analyze_batch(texts)

        output_results = []
        try:
            # Batch inference with HuggingFace pipeline
            predictions = self.pipeline(texts, truncation=True, max_length=128)
            for preds in predictions:
                scores = {item['label'].lower(): item['score'] for item in preds}
                # ProsusAI/finbert labels: positive, negative, neutral
                pos = scores.get('positive', 0.0)
                neg = scores.get('negative', 0.0)
                neu = scores.get('neutral', 0.0)

                score = pos - neg  # Range -1.0 to +1.0
                if score >= 0.20:
                    label = "BULLISH"
                elif score <= -0.20:
                    label = "BEARISH"
                else:
                    label = "NEUTRAL"
                
                confidence = max(pos, neg, neu)
                output_results.append(SentimentResult(score=round(score, 3), label=label, confidence=round(confidence, 2)))
        except Exception as e:
            logger.error(f"Error during FinBERT batch inference: {e}")
            fallback = HeuristicSentimentClassifier()
            return fallback.analyze_batch(texts)

        return output_results


# Global Singleton for Classifier
_classifier_instance = None


def get_sentiment_classifier() -> BaseSentimentClassifier:
    global _classifier_instance
    if _classifier_instance is None:
        if settings.USE_FINBERT and settings.SENTIMENT_MODEL.startswith("ProsusAI"):
            _classifier_instance = FinBERTSentimentClassifier(settings.SENTIMENT_MODEL)
        else:
            _classifier_instance = HeuristicSentimentClassifier()
    return _classifier_instance
