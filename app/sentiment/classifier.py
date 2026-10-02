import re
import math
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
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

    @property
    def model_id(self) -> str:
        """Identifier of the model that actually produced the last results (stored per post)."""
        return "heuristic-lexicon"

    def analyze_batch(self, texts: List[str]) -> List[SentimentResult]:
        return [self.analyze(t) for t in texts]


class HeuristicSentimentClassifier(BaseSentimentClassifier):
    """Fast, deterministic finance lexicon & keyword sentiment analyzer with negation detection and tanh saturation."""
    
    BULLISH_KEYWORDS = [
        "bull", "bullish", "moon", "buy", "buying",
        "go long", "going long", "long position", "long positions", "long on", "heavily long", "long thesis",
        "call option", "call options", "call buying", "buying calls", "bullish calls",
        "__BUYING_CALLS__", "__SELLING_PUTS__", "__BULLISH_CALL_FLOW__", "__BULLISH_CALLS__",
        "surge", "surges", "surging", "surged", "beat", "beats", "beating",
        "outperform", "outperforms", "outperforming", "outperformed",
        "growth", "breakout", "success", "successful", "successfully", "upgrade", "upgrades", "upgraded", "upgrading",
        "win", "wins", "winning", "won", "milestone", "record high", "all-time high", "all time high",
        "ath", "52-week high", "gamechanger", "expansion", "profit", "profitable",
        "profitability", "rally", "rallies", "rallying", "rallied", "soar", "soars", "soaring", "soared",
        # A squeeze forces shorts to cover: bullish for the price
        "short squeeze", "undervalued",
        # FinTwit slang. Emojis are intentionally not scored: on real data rocket/chart emojis are mostly
        # decoration in watchlists, promos and literal launch posts, and flipped ~7% of posts to BULLISH.
        "lfg", "diamond hands"
    ]

    BEARISH_KEYWORDS = [
        "bear", "bearish", "short selling", "short seller", "short sellers", "short interest",
        "short position", "short positions", "shorting", "go short", "going short", "heavily short",
        "naked short", "fall short", "fell short", "falling short",
        "sell", "selling",
        "put option", "put options", "put buying", "buying puts", "bearish puts", "heavy puts",
        "__BUYING_PUTS__", "__SELLING_CALLS__", "__BEARISH_PUT_FLOW__", "__BEARISH_PUTS__",
        "dilution", "capital raise", "downgrade", "downgrades", "downgraded", "downgrading",
        # Only financing offerings; bare 'offering' also matches products and services
        "share offering", "shares offering", "stock offering", "public offering", "secondary offering",
        "equity offering", "direct offering", "notes offering", "atm offering", "convertible notes",
        "explosion", "explodes", "exploded", "exploding", "blew up", "blows up", "anomaly",
        "bagholder", "bagholders", "bag holder", "rug pull",
        "delay", "delayed", "delays", "delaying", "failure", "fail", "failed", "failing", "fails",
        "miss", "missed", "misses", "missing", "underperform", "underperforms", "underperforming", "underperformed",
        "burn", "cash burn", "drop", "dropped", "dropping", "drops", "loss", "losses",
        "plunge", "plunges", "plunging", "plunged", "crash", "crashes", "crashing", "crashed",
        "tumble", "tumbles", "tumbling", "tumbled",
        "halt", "halted", "halting",
        "high risk", "at risk", "downside risk", "dilution risk", "bankruptcy risk", "default risk",
        "execution risk", "risk warning", "risk of failure", "risk of delay", "risk of dilution", "risk-off",
        "bankruptcy", "lawsuit", "investigation", "stretched", "overvalued",
        "cancel", "cancels", "cancelled", "canceling", "cancellation",
        "terminate", "terminates", "terminated", "terminating", "termination",
        "revoke", "revokes", "revoked", "revoking", "rescind", "rescinds", "rescinded",
        "reject", "rejects", "rejected", "lost contract", "contract loss"
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

    def _preprocess(self, text: str) -> str:
        t = text.lower()
        # 0. Mask figurative explosions ('explosion of demand', 'shares exploded higher') so they are not read as failures
        t = re.sub(
            r'\bexplosions?\s+(?:of|in)\s+(?:demand|growth|interest|sales|activity|volume|revenue|users|orders|popularity|traffic|capacity)\b'
            r'|\b(?:demand|growth|interest|sales|popularity|revenue|activity|volume)\s+(?:explodes|exploded|exploding)\b'
            r'|\b(?:stock|stocks|shares?|price|calls?|options?)\s+(?:explodes|exploded|exploding|blew\s+up|blows\s+up)\b'
            r'|\b(?:explodes|exploded|exploding)\s+(?:higher|upward|up|in\s+popularity|onto\s+the\s+scene)\b',
            ' __FIGURATIVE_SURGE__ ', t
        )

        # 1. Options trading idioms resolution (prevents bare buy/sell from cancelling options direction)
        t = re.sub(r'\b(?:buy|buying|bought|load|loaded|loading|purchas(?:e|ing|ed))\s+(?:put\s+options?|puts)\b', ' __BUYING_PUTS__ ', t)
        t = re.sub(r'\b(?:sell|selling|sold)\s+(?:put\s+options?|puts)\b', ' __SELLING_PUTS__ ', t)
        t = re.sub(r'\b(?:buy|buying|bought|load|loaded|loading|purchas(?:e|ing|ed))\s+(?:call\s+options?|calls)\b', ' __BUYING_CALLS__ ', t)
        t = re.sub(r'\b(?:sell|selling|sold)\s+(?:call\s+options?|calls)\b', ' __SELLING_CALLS__ ', t)
        t = re.sub(r'\b(?:heavy\s+)?put\s+options?\s+(?:buying|volume|flow|sweeps?)\b', ' __BEARISH_PUT_FLOW__ ', t)
        t = re.sub(r'\b(?:heavy\s+)?call\s+options?\s+(?:buying|volume|flow|sweeps?)\b', ' __BULLISH_CALL_FLOW__ ', t)
        t = re.sub(r'\b(?:put\s+options?|bearish\s+puts?)\b', ' __BEARISH_PUTS__ ', t)
        t = re.sub(r'\b(?:call\s+options?|bullish\s+calls?)\b', ' __BULLISH_CALLS__ ', t)

        # 2. Mask sell-side / buy-side so 'sell'/'buy' don't trigger falsely
        t = re.sub(r'\bsell\s*-\s*side\b|\bsell\s+side\b', ' __SELL_SIDE__ ', t)
        t = re.sub(r'\bbuy\s*-\s*side\b|\bbuy\s+side\b', ' __BUY_SIDE__ ', t)

        # 3. Mask profit-taking so 'profit' doesn't trigger falsely
        t = re.sub(r'\bprofit\s*-\s*taking\b|\bprofit\s+taking\b|\btaking\s+profits?\b', ' __PROFIT_TAKING__ ', t)

        # 4. Mask short-term, short time, in short
        t = re.sub(r'\bshort\s*-\s*term\b|\bshort\s+term\b|\bin\s+short\b|\bshort\s+notice\b|\bshort\s+time\b', ' __SHORT_TERM__ ', t)

        # 5. Mask earnings / conference / investor calls
        t = re.sub(r'\b(?:earnings|conference|investor|quarterly|analyst|results|post-earnings)\s+calls?\b', ' __EARNINGS_CALL__ ', t)
        t = re.sub(r'\b(?:on|during)\s+(?:the\s+)?call\b', ' __ON_CALL__ ', t)

        # 6. Mask derisk / risk management / risk-on
        t = re.sub(r'\bde-?risking?\b|\bde-?risked\b', ' __DERISK__ ', t)
        t = re.sub(r'\brisk\s*-\s*on\b|\brisk\s+on\b', ' __RISK_ON__ ', t)
        t = re.sub(r'\b(?:manage|managing|mitigate|mitigating)\s+risk\b|\brisk\s+management\b|\brisk\s+mitigation\b', ' __RISK_MGMT__ ', t)

        # 7. Mask long-term, long time, long run, long way
        t = re.sub(r'\blong\s*-\s*term\b|\blong\s+term\b|\blong\s+time\b|\blong\s+run\b|\blong\s+road\b|\blong\s+way\b|\bhow\s+long\b', ' __LONG_TERM__ ', t)
        return t

    def _find_negation(self, kw: str, clean_text: str) -> Optional[Tuple[int, int]]:
        """
        Return the (start, end) span of the negation word governing keyword kw, or None.
        A negation counts when it precedes kw within 0-2 intervening words without punctuation,
        and is not part of an affirmative idiom (e.g. 'no doubt').
        """
        # 1. Mask affirmative idioms with same-length filler so match offsets stay aligned with clean_text
        temp_text = clean_text
        for idiom in self.AFFIRMATIVE_IDIOMS:
            temp_text = re.sub(r'\b' + re.escape(idiom) + r'\b', lambda m: '_' * len(m.group(0)), temp_text)

        # 2. Strict syntax window: Negation word + 0 to 2 words + target keyword
        neg_re = (
            r'\b(' + '|'.join(re.escape(nw) for nw in self.NEGATION_WORDS) + r')\b'
            r'(?:\s+[a-z0-9\'-]+){0,2}\s+'
            r'\b' + re.escape(kw) + r'\b'
        )
        match = re.search(neg_re, temp_text)
        if match:
            matched_segment = match.group(0)
            if not any(punct in matched_segment for punct in ['.', ';', '!', '?', ',', ':', '-', '—', '(', ')']):
                return match.span(1)
        return None

    def _is_negated(self, kw: str, clean_text: str) -> bool:
        return self._find_negation(kw, clean_text) is not None

    def _is_negative_metric_high(self, kw: str, clean_text: str) -> bool:
        """True when an 'all-time high' style expression modifies a negative metric (e.g. 'short interest hits all-time high')."""
        if kw not in self.HIGH_PRICE_EXPRESSIONS:
            return False
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
        return bool(re.search(neg_pattern, clean_text) or re.search(neg_pattern_rev, clean_text))

    def analyze(self, text: str) -> SentimentResult:
        clean_text = self._preprocess(text)

        # 1. Claim keyword spans longest-first so nested keywords ('cash burn' -> 'burn',
        #    'short selling' -> 'selling', 'risk of failure' -> 'failure') are counted once.
        #    Each keyword still counts at most once (presence semantics).
        candidates = [(kw, 1) for kw in self.BULLISH_KEYWORDS] + [(kw, -1) for kw in self.BEARISH_KEYWORDS]
        candidates.sort(key=lambda c: -len(c[0]))
        claimed: List[Tuple[int, int]] = []
        hits: List[Tuple[str, int, Tuple[int, int]]] = []
        for kw, polarity in candidates:
            for m in re.finditer(r'\b' + re.escape(kw) + r'\b', clean_text):
                span = m.span()
                if any(span[0] < c_end and c_start < span[1] for c_start, c_end in claimed):
                    continue
                claimed.append(span)
                hits.append((kw, polarity, span))
                break

        # 2. Resolve polarity with negation inversion and negative-metric disambiguation
        resolved: List[Tuple[str, int, Tuple[int, int]]] = []
        negator_spans: List[Tuple[int, int]] = []
        for kw, polarity, span in hits:
            if polarity > 0 and self._is_negative_metric_high(kw, clean_text):
                resolved.append((kw, -1, span))
                continue
            neg_span = self._find_negation(kw, clean_text)
            if neg_span is not None:
                negator_spans.append(neg_span)
                resolved.append((kw, -polarity, span))
            else:
                resolved.append((kw, polarity, span))

        # 3. A keyword that also served as the negator ('failed' in 'failed to beat') is not counted again
        bull_hits = 0
        bear_hits = 0
        for kw, polarity, span in resolved:
            if kw in self.NEGATION_WORDS and span in negator_spans:
                continue
            if polarity > 0:
                bull_hits += 1
            else:
                bear_hits += 1

        total_hits = bull_hits + bear_hits
        if total_hits == 0:
            return SentimentResult(score=0.0, label="NEUTRAL", confidence=0.70)

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

        # Signal agreement ratio: delta / total
        agreement = abs(delta_hits) / float(total_hits)

        if label in ("BULLISH", "BEARISH"):
            volume_factor = min(1.0, 0.40 + 0.15 * total_hits)
            conf = 0.35 + 0.60 * (agreement * volume_factor)
            confidence = min(0.95, max(0.35, conf))
        else:
            # Conflicted neutral: when opposing signals cancel out (e.g. 2 bull + 2 bear),
            # confidence is penalized down to reflect high uncertainty / contradiction
            conf = 0.35 + 0.35 * agreement
            confidence = min(0.70, max(0.30, conf))

        return SentimentResult(score=round(score, 3), label=label, confidence=round(confidence, 2))


class FinBERTSentimentClassifier(BaseSentimentClassifier):
    """
    Local HuggingFace sentiment model with lazy loading and batch processing.

    Supports both label vocabularies:
      - ProsusAI/finbert (news): positive / negative / neutral
      - StephanAkkerman/FinTwitBERT-sentiment (tweets): bullish / bearish / neutral
    score = P(positive|bullish) - P(negative|bearish); the label is BULLISH/BEARISH only when
    |score| >= label_threshold. FinTwitBERT needs a high threshold (0.90): its probabilities are
    overconfident and it reads ~68% of tweets as bullish at the FinBERT threshold of 0.20.
    Falls back to the heuristic lexicon if the model cannot be loaded or inference fails.
    """

    def __init__(self, model_name: str = "ProsusAI/finbert", label_threshold: float = 0.20):
        self.model_name = model_name
        self.label_threshold = label_threshold
        self.pipeline = None
        self._used_fallback = False

    @property
    def model_id(self) -> str:
        return "heuristic-lexicon" if self._used_fallback else self.model_name

    def _load_model(self):
        if self.pipeline is not None:
            return
        try:
            from transformers import pipeline
            logger.info(f"Loading FinBERT model '{self.model_name}'...")
            try:
                self.pipeline = pipeline("text-classification", model=self.model_name, top_k=None)
            except Exception:
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
        self._used_fallback = self.pipeline is None
        if self.pipeline is None:
            fallback = HeuristicSentimentClassifier()
            return fallback.analyze_batch(texts)

        if not texts:
            return []

        # Sanitize texts to prevent pipeline errors on empty or non-string inputs
        clean_texts = [str(t).strip() if (t and str(t).strip()) else "neutral" for t in texts]

        output_results = []
        try:
            # Batch inference with HuggingFace pipeline
            predictions = self.pipeline(clean_texts, truncation=True, max_length=128)
            for preds in predictions:
                if isinstance(preds, list):
                    scores = {item['label'].lower(): float(item['score']) for item in preds if isinstance(item, dict) and 'label' in item}
                elif isinstance(preds, dict):
                    scores = {preds.get('label', 'neutral').lower(): float(preds.get('score', 1.0))}
                else:
                    scores = {}

                # FinBERT: positive/negative/neutral; FinTwitBERT: bullish/bearish/neutral
                pos = scores.get('positive', scores.get('bullish', 0.0))
                neg = scores.get('negative', scores.get('bearish', 0.0))
                neu = scores.get('neutral', 0.0)

                score = pos - neg  # Range -1.0 to +1.0
                if score >= self.label_threshold:
                    label = "BULLISH"
                elif score <= -self.label_threshold:
                    label = "BEARISH"
                else:
                    label = "NEUTRAL"
                
                confidence = max(pos, neg, neu)
                output_results.append(SentimentResult(score=round(score, 3), label=label, confidence=round(confidence, 2)))
        except Exception as e:
            logger.error(f"Error during FinBERT batch inference: {e}")
            self._used_fallback = True
            fallback = HeuristicSentimentClassifier()
            return fallback.analyze_batch(texts)

        return output_results


# Global Singletons: one classifier for news (FinBERT), one for X posts (FinTwitBERT by default)
_classifier_instance = None
_social_classifier_instance = None


def get_sentiment_classifier() -> BaseSentimentClassifier:
    """News classifier: settings.SENTIMENT_MODEL (FinBERT, trained on formal financial text)."""
    global _classifier_instance
    if _classifier_instance is None:
        if getattr(settings, "USE_FINBERT", False):
            model_name = getattr(settings, "SENTIMENT_MODEL", "ProsusAI/finbert")
            _classifier_instance = FinBERTSentimentClassifier(model_name)
        else:
            _classifier_instance = HeuristicSentimentClassifier()
    return _classifier_instance


def get_social_sentiment_classifier() -> BaseSentimentClassifier:
    """
    X/Twitter classifier: settings.SOCIAL_SENTIMENT_MODEL with settings.SOCIAL_SENTIMENT_THRESHOLD.
    Uses the heuristic lexicon when transformer models are disabled (USE_FINBERT=False).
    To revert tweets to FinBERT, set SOCIAL_SENTIMENT_MODEL=ProsusAI/finbert and SOCIAL_SENTIMENT_THRESHOLD=0.20.
    """
    global _social_classifier_instance
    if _social_classifier_instance is None:
        if getattr(settings, "USE_FINBERT", False):
            _social_classifier_instance = FinBERTSentimentClassifier(
                getattr(settings, "SOCIAL_SENTIMENT_MODEL", "StephanAkkerman/FinTwitBERT-sentiment"),
                label_threshold=getattr(settings, "SOCIAL_SENTIMENT_THRESHOLD", 0.90)
            )
        else:
            _social_classifier_instance = HeuristicSentimentClassifier()
    return _social_classifier_instance

