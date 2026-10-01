from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from app.config import settings
from app.scoring.social import apply_bayesian_shrinkage


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DivergenceResult(BaseModel):
    ticker: str
    type: str  # BULLISH_DIVERGENCE, BEARISH_DIVERGENCE, BULLISH_CONFIRMATION, BEARISH_CONFIRMATION, EARLY_REVERSAL
    source_a: str
    source_b: str
    source_c: Optional[str] = None
    direction: str  # "BULLISH", "BEARISH", "NEUTRAL"
    strength: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    description: str
    timestamp: datetime = Field(default_factory=utc_now)


def detect_divergences(
    ticker: str,
    social_score: Optional[float] = None,
    prediction_score: Optional[float] = None,
    prediction_delta_24h: Optional[float] = None,
    news_score: Optional[float] = None,
    momentum_score: Optional[float] = None,
    technical_score: Optional[float] = None,
    price_return_1d: Optional[float] = None,
    volume_ratio: Optional[float] = None,
    rsi: Optional[float] = None,
    post_count: Optional[int] = None,
    intraday_reversal_pct: Optional[float] = None,
    range_location: Optional[float] = None
) -> List[DivergenceResult]:
    """
    Divergence Engine for SMIE v2.0 (Tripartite Analysis: X ↔ Polymarket ↔ Price).
    
    Identifies non-trivial market regimes:
    1. BULLISH_DIVERGENCE: Narrative / Prediction expectations are positive while price lags or drops.
    2. BEARISH_DIVERGENCE: Narrative / Prediction expectations are collapsing while price is temporarily elevated.
    3. BULLISH_CONFIRMATION: Multi-source alignment (Social + Prediction + Price + High Volume).
    4. BEARISH_CONFIRMATION: Multi-source collapse (Social + Prediction + Price falling + High Volume).
    5. EARLY_REVERSAL: Sharp 24h shift in Polymarket probabilities (ΔPMS_24h >= +15%) or structural disconnect.
    """
    results: List[DivergenceResult] = []
    now = datetime.now(timezone.utc)

    # Directional normalizations (-1.0 to +1.0)
    # Apply Bayesian shrinkage to social score if post_count is provided and sample size is small (< 10)
    effective_social = None
    dir_social = None
    if social_score is not None:
        effective_social = apply_bayesian_shrinkage(social_score, post_count) if post_count is not None else social_score
        dir_social = (effective_social - 50.0) / 50.0

    dir_pred = (prediction_score - 50.0) / 50.0 if prediction_score is not None else None
    dir_price = 0.0
    if price_return_1d is not None:
        # Micro-noise dampening: if |price_return_1d| < 1.0%, smoothly shrink towards 0 to eliminate whipsawing false divergences
        abs_ret = abs(price_return_1d)
        if abs_ret < 1.0:
            dampened_ret = price_return_1d * abs_ret  # Quadratic dampening on sub-1% daily noise
        else:
            dampened_ret = price_return_1d

        scaled_return = max(-1.0, min(1.0, dampened_ret / 5.0))

        # If momentum_score is available, blend 50% short-term daily return with 50% structural trend momentum
        if momentum_score is not None:
            dir_mom = (momentum_score - 50.0) / 50.0
            dir_price = 0.50 * scaled_return + 0.50 * dir_mom
        else:
            dir_price = scaled_return
    elif momentum_score is not None:
        dir_price = (momentum_score - 50.0) / 50.0
    elif technical_score is not None:
        dir_price = ((technical_score / 40.0) * 100.0 - 50.0) / 50.0

    # Intraday rejection adjustment: if price collapsed from session high, drag dir_price downward
    if intraday_reversal_pct is not None and intraday_reversal_pct <= -3.0:
        rev_drag = max(-1.0, intraday_reversal_pct / 8.0)
        dir_price = min(dir_price, 0.60 * dir_price + 0.40 * rev_drag)

    vol_ratio = volume_ratio if volume_ratio is not None else 1.0

    # -------------------------------------------------------------
    # 1. STRONG CONFIRMATION SCENARIOS
    # -------------------------------------------------------------
    # Bullish Confirmation: Social >= +0.30, Price >= +0.20, Volume >= 1.2x (and PMS >= +0.20 if available)
    if dir_social is not None and dir_social >= 0.30 and dir_price >= 0.20 and vol_ratio >= 1.2:
        if dir_pred is None or dir_pred >= 0.20:
            pred_text = f" and Polymarket expectations ({prediction_score:.0f}%)" if prediction_score is not None else ""
            results.append(DivergenceResult(
                ticker=ticker,
                type="BULLISH_CONFIRMATION",
                source_a="X_SOCIAL",
                source_b="PRICE_ACTION",
                source_c="POLYMARKET" if prediction_score is not None else None,
                direction="BULLISH",
                strength=0.90 if dir_pred is not None and dir_pred >= 0.30 else 0.75,
                confidence=0.88,
                description=f"Strong multi-source confirmation: Social sentiment ({effective_social:.0f}){pred_text} aligned with upward price momentum on heavy volume ({vol_ratio:.1f}x).",
                timestamp=now
            ))

    # Bearish Confirmation: Social <= -0.30, Price <= -0.20, Volume >= 1.2x
    elif dir_social is not None and dir_social <= -0.30 and dir_price <= -0.20 and vol_ratio >= 1.2:
        if dir_pred is None or dir_pred <= -0.20:
            pred_text = f" and Polymarket expectations ({prediction_score:.0f}%)" if prediction_score is not None else ""
            results.append(DivergenceResult(
                ticker=ticker,
                type="BEARISH_CONFIRMATION",
                source_a="X_SOCIAL",
                source_b="PRICE_ACTION",
                source_c="POLYMARKET" if prediction_score is not None else None,
                direction="BEARISH",
                strength=0.90 if dir_pred is not None and dir_pred <= -0.30 else 0.75,
                confidence=0.88,
                description=f"Strong bearish confirmation: Social sentiment ({effective_social:.0f}){pred_text} confirmed by falling price action on above-average volume ({vol_ratio:.1f}x).",
                timestamp=now
            ))

    # -------------------------------------------------------------
    # 2. DIVERGENCE SCENARIOS (Narrative / Prediction vs Price)
    # -------------------------------------------------------------
    # Bullish Divergence: Narrative/Expectations are Bullish, but Price is falling
    bullish_sources = []
    if dir_social is not None and dir_social >= 0.18:
        bullish_sources.append(f"X Social ({effective_social:.0f})")
    if dir_pred is not None and dir_pred >= 0.18:
        bullish_sources.append(f"Polymarket PMS ({prediction_score:.0f})")
        
    if bullish_sources and dir_price <= -0.10:
        valid_dirs = [d for d in [dir_social, dir_pred] if d is not None]
        max_dir = max(valid_dirs) if valid_dirs else 0.0
        strength = min(1.0, (max_dir - dir_price) / 1.5)
        src_desc = " and ".join(bullish_sources)
        results.append(DivergenceResult(
            ticker=ticker,
            type="BULLISH_DIVERGENCE",
            source_a="PREDICTION_MARKET" if dir_social is None else ("SOCIAL_PREDICTION" if dir_pred is not None else "X_SOCIAL"),
            source_b="PRICE_ACTION",
            source_c="MOMENTUM",
            direction="BULLISH",
            strength=round(strength, 2),
            confidence=round(0.70 + (0.15 if len(bullish_sources) > 1 else 0.0), 2),
            description=f"Bullish Divergence: {src_desc} is accelerating upward while price action is lagging/falling ({dir_price:+.2f}). Potential accumulation setup.",
            timestamp=now
        ))

    # Bearish Divergence: Narrative/Expectations are Bearish, but Price is rising/overextended
    bearish_sources = []
    if dir_social is not None and dir_social <= -0.18:
        bearish_sources.append(f"X Social ({effective_social:.0f})")
    if dir_pred is not None and dir_pred <= -0.18:
        bearish_sources.append(f"Polymarket PMS ({prediction_score:.0f})")

    if bearish_sources and (dir_price >= 0.10 or (rsi and rsi >= 70)):
        valid_dirs = [d for d in [dir_social, dir_pred] if d is not None]
        min_dir = min(valid_dirs) if valid_dirs else 0.0
        strength = min(1.0, (dir_price - min_dir) / 1.5)
        src_desc = " and ".join(bearish_sources)
        results.append(DivergenceResult(
            ticker=ticker,
            type="BEARISH_DIVERGENCE",
            source_a="PREDICTION_MARKET" if dir_social is None else ("SOCIAL_PREDICTION" if dir_pred is not None else "X_SOCIAL"),
            source_b="PRICE_ACTION",
            source_c="RSI_OVEREXTENSION" if rsi and rsi >= 70 else None,
            direction="BEARISH",
            strength=round(strength, 2),
            confidence=round(0.70 + (0.15 if len(bearish_sources) > 1 else 0.0), 2),
            description=f"Bearish Divergence: Price is extended ({dir_price:+.2f}) while {src_desc} is deteriorating. High risk of mean reversion.",
            timestamp=now
        ))

    # -------------------------------------------------------------
    # 2b. INTRADAY EXHAUSTION DIVERGENCE (Fade the Open / Sell the News)
    # -------------------------------------------------------------
    has_constructive_narrative = (
        (dir_social is not None and dir_social >= 0.08)
        or (news_score is not None and news_score >= 55.0)
        or (dir_pred is not None and dir_pred >= 0.08)
    )
    if has_constructive_narrative and intraday_reversal_pct is not None and intraday_reversal_pct <= -4.0 and vol_ratio >= 1.15:
        if range_location is None or range_location <= 0.40:
            narrative_desc = (
                f"Social Sentiment ({effective_social:.0f})" if (dir_social is not None and dir_social >= 0.08)
                else (f"News Catalysts ({news_score:.0f})" if news_score is not None else "Polymarket Expectations")
            )
            strength = min(1.0, abs(intraday_reversal_pct) / 8.0)
            results.append(DivergenceResult(
                ticker=ticker,
                type="INTRADAY_BEARISH_DIVERGENCE",
                source_a="NARRATIVE_SENTIMENT",
                source_b="INTRADAY_PRICE_ACTION",
                source_c="VOLUME_DISTRIBUTION" if vol_ratio >= 1.3 else None,
                direction="BEARISH",
                strength=round(strength, 2),
                confidence=0.82,
                description=f"Intraday Exhaustion Divergence: Constructive morning narrative from {narrative_desc} faded by aggressive intraday selling ({intraday_reversal_pct:.1f}% from session high on {vol_ratio:.1f}x volume).",
                timestamp=now
            ))


    # -------------------------------------------------------------
    # 3. EARLY REVERSAL SCENARIOS (X vs Polymarket Dynamic & Structural Disconnect)
    # -------------------------------------------------------------
    min_delta = settings.DIVERGENCE_EARLY_REVERSAL_DELTA

    # Dynamic Case A: Bullish Early Reversal via 24h Polymarket Probability Surge (ΔPMS_24h >= +15%)
    if prediction_delta_24h is not None and prediction_delta_24h >= min_delta:
        soc_subdued = (dir_social is None) or (effective_social is not None and effective_social <= 55.0) or (dir_social is not None and dir_social <= 0.10)
        if soc_subdued and (price_return_1d is None or price_return_1d <= 2.0):
            strength = min(1.0, 0.70 + (prediction_delta_24h / 100.0))
            soc_desc = f"retail social sentiment ({effective_social:.0f})" if effective_social is not None else "retail sentiment"
            results.append(DivergenceResult(
                ticker=ticker,
                type="EARLY_REVERSAL",
                source_a="POLYMARKET_MOMENTUM",
                source_b="X_SOCIAL" if effective_social is not None else "PRICE_ACTION",
                source_c="PRICE_ACTION" if effective_social is not None else None,
                direction="BULLISH",
                strength=round(strength, 2),
                confidence=0.85,
                description=f"Early Reversal Watch: Polymarket probability surged (+{prediction_delta_24h:+.1f}% in 24h) while {soc_desc} and price action remain subdued. Potential smart money frontrunning.",
                timestamp=now
            ))
    # Dynamic Case B: Bearish Early Reversal via 24h Polymarket Probability Collapse (ΔPMS_24h <= -15%)
    elif prediction_delta_24h is not None and prediction_delta_24h <= -min_delta:
        if dir_social is not None and effective_social is not None and (effective_social >= 60.0 or dir_social >= 0.20):
            strength = min(1.0, 0.70 + (abs(prediction_delta_24h) / 100.0))
            results.append(DivergenceResult(
                ticker=ticker,
                type="EARLY_REVERSAL",
                source_a="POLYMARKET_MOMENTUM",
                source_b="X_SOCIAL",
                source_c="PRICE_ACTION",
                direction="BEARISH",
                strength=round(strength, 2),
                confidence=0.85,
                description=f"Early Reversal Alert: Polymarket probability collapsed ({prediction_delta_24h:+.1f}% in 24h) contradicting elevated retail optimism on X ({effective_social:.0f}). High risk of institutional dump or failed catalyst.",
                timestamp=now
            ))
    # Structural Fallback: Level Disconnect (Panic in Social vs High Bullish PMS or vice versa)
    elif dir_pred is not None and dir_social is not None and effective_social is not None:
        if dir_social <= -0.30 and dir_pred >= 0.30:
            results.append(DivergenceResult(
                ticker=ticker,
                type="EARLY_REVERSAL",
                source_a="X_SOCIAL",
                source_b="POLYMARKET",
                source_c="PRICE_STABILIZING",
                direction="BULLISH",
                strength=0.80,
                confidence=0.72,
                description=f"Early Reversal Watch: Retail social narrative is fearful ({effective_social:.0f}) while Prediction Markets price high success probability ({prediction_score:.0f}). Potential bottom formation.",
                timestamp=now
            ))
        elif dir_social >= 0.35 and dir_pred <= -0.30:
            results.append(DivergenceResult(
                ticker=ticker,
                type="EARLY_REVERSAL",
                source_a="X_SOCIAL",
                source_b="POLYMARKET",
                source_c="PRICE_OVEREXTENDED",
                direction="BEARISH",
                strength=0.80,
                confidence=0.72,
                description=f"Early Reversal Watch: High retail euphoria on X ({effective_social:.0f}) contradicts low prediction market probability ({prediction_score:.0f}). Possible bull trap.",
                timestamp=now
            ))

    return results
