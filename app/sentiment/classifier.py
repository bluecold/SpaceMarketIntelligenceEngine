import re
import math
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
    """Fast, deterministic finance lexicon & keyword sentiment analyzer with negation detection and tanh saturation."""
    
    BULLISH_KEYWORDS = [
        "bull", "bullish", "moon", "buy", "buying", "long", "call", "calls",
        "surge", "surges", "surging", "surged", "beat", "beats", "beating",
        "outperform", "outperforms", "outperforming", "outperformed",
        "growth", "breakout", "success", "successful", "upgrade", "upgrades", "upgraded", "upgrading",
        "win", "wins", "winning", "won", "milestone", "record high", "all-time high", "all time high",
        "ath", "52-week high", "gamechanger", "expansion", "profit", "profitable",
        "profitability", "rally", "rallies", "rallying", "rallied", "soar", "soars", "soaring", "soared"
    ]
    
    BEARISH_KEYWORDS = [
        "bear", "bearish", "short", "shorts", "short interest", "sell", "selling",
        "put", "puts", "dilution", "capital raise", "offering", "downgrade", "downgrades", "downgraded", "downgrading",
        "delay", "delayed", "delays", "delaying", "failure", "fail", "failed", "failing", "fails",
        "miss", "missed", "misses", "missing", "underperform", "underperforms", "underperforming", "underperformed",
        "burn", "cash burn", "drop", "dropped", "dropping", "drops", "loss", "losses",
        "plunge", "plunges", "plunging", "plunged", "crash", "crashes", "crashing", "crashed",
        "tumble", "tumbles", "tumbling", "tumbled",
        "halt", "halted", "halting", "risk", "bankruptcy", "lawsuit", "investigation", "stretched", "overvalued"
    ]

    HIGH_PRICE_EXPRESSIONS = [
        "all-time high", "all time high", "ath", "record high", "52-week high"
    ]

    NEGATIVE_METRIC_TARGETS = [
        "short", "shorts", "short interest", "loss", "losses", "debt", "risk", "burn", "cash burn", "dilution"
    ]

    NEGATION_WORDS = [
        "not", "no", "never", "without", "hardly", "barely", "scarcely",
        "failed", "fail", "fails", "failing", "lack", "lacks", "lacking",
        "don't", "dont", "doesn't", "doesnt", "didn't", "didnt",
        "won't", "wont", "can't", "cant", "cannot", "couldn't", "couldnt",
        "wouldn't", "wouldnt", "shouldn't", "shouldnt", "isn't", "isnt",
        "aren't", "arent", "wasn't", "wasnt", "weren't", "werent",
        "neither", "nor"
    ]

    AFFIRMATIVE_IDIOMS = [
        "no doubt", "without doubt", "without a doubt",
        "no question", "without question", "no wonder", "no surprise"
    ]

    def _is_negated(self, kw: str, clean_text: str) -> bool:
        """
        Check if keyword is preceded by a genuine negation within 0-2 intervening words,
        resisting affirmative idioms (e.g. 'no doubt') and punctuation boundaries.
        """
        # 1. Mask affirmative idioms so phrases like 'no doubt' are not treated as negations
        temp_text = clean_text
        for idiom in self.AFFIRMATIVE_IDIOMS:
            temp_text = re.sub(r'\b' + re.escape(idiom) + r'\b', '__AFFIRMED__', temp_text)

        # 2. Strict syntax window: Negation word + 0 to 2 words + target keyword
        neg_re = (
            r'\b(?:' + '|'.join(re.escape(nw) for nw in self.NEGATION_WORDS) + r')\b'
            r'(?:\s+[a-z0-9\'-]+){0,2}\s+'
            r'\b' + re.escape(kw) + r'\b'
        )
        match = re.search(neg_re, temp_text)
        if match:
            matched_segment = match.group(0)
            if not any(punct in matched_segment for punct in ['.', ';', '!', '?', ',', ':', '-', '—', '(', ')']):
                return True
        return False

    def analyze(self, text: str) -> SentimentResult:
        clean_text = text.lower()
        
        bull_hits = 0
        bear_hits = 0

        # Evaluate Bullish keywords with negation inversion and context disambiguation
        for kw in self.BULLISH_KEYWORDS:
            if re.search(r'\b' + re.escape(kw) + r'\b', clean_text):
                # Disambiguation: if 'all-time high' is modifying a negative metric (e.g. 'short interest reaches all-time high')
                if kw in self.HIGH_PRICE_EXPRESSIONS:
                    neg_pattern = (
                        r'\b(?:' + '|'.join(re.escape(t) for t in self.NEGATIVE_METRIC_TARGETS) + r')\b'
                        r'(?:\s+[a-z0-9\'-]+){0,3}\s+'
                        r'\b' + re.escape(kw) + r'\b'
                    )
                    neg_pattern_rev = (
                        r'\b' + re.escape(kw) + r'\b'
                        r'(?:\s+(?:in|of))?\s+'
                        r'\b(?:' + '|'.join(re.escape(t) for t in self.NEGATIVE_METRIC_TARGETS) + r')\b'
                    )
                    if re.search(neg_pattern, clean_text) or re.search(neg_pattern_rev, clean_text):
                        bear_hits += 1
                        continue

                if self._is_negated(kw, clean_text):
                    bear_hits += 1  # Negated bullish = Bearish
                else:
                    bull_hits += 1

        # Evaluate Bearish keywords with negation inversion
        for kw in self.BEARISH_KEYWORDS:
            if re.search(r'\b' + re.escape(kw) + r'\b', clean_text):
                if self._is_negated(kw, clean_text):
                    bull_hits += 1  # Negated bearish = Bullish
                else:
                    bear_hits += 1
        
        total_hits = bull_hits + bear_hits
        if total_hits == 0:
            return SentimentResult(score=0.0, label="NEUTRAL", confidence=0.7)

        # Smooth saturation using hyperbolic tangent: tanh((bull_hits - bear_hits) / 2.0)
        # Prevents a single isolated hit from triggering maximum conviction (+1.0)
        delta_hits = bull_hits - bear_hits
        score = math.tanh(delta_hits / 2.0)
        score = max(-1.0, min(1.0, score))

        if score >= 0.20:
            label = "BULLISH"
        elif score <= -0.20:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

        confidence = min(0.95, round(0.40 + 0.15 * min(4, total_hits), 2))
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
