from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime, timezone


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
    timestamp: datetime = datetime.now(timezone.utc)


def detect_divergences(
    ticker: str,
    social_score: float,
    prediction_score: Optional[float] = None,
    news_score: Optional[float] = None,
    momentum_score: Optional[float] = None,
    technical_score: Optional[float] = None,
    price_return_1d: Optional[float] = None,
    volume_ratio: Optional[float] = None,
    rsi: Optional[float] = None
) -> List[DivergenceResult]:
    """
    Divergence Engine for SMIE v2.0 (Tripartite Analysis: X ↔ Polymarket ↔ Price).
    
    Identifies non-trivial market regimes:
    1. BULLISH_DIVERGENCE: Narrative / Prediction expectations are positive while price lags or drops.
    2. BEARISH_DIVERGENCE: Narrative / Prediction expectations are collapsing while price is temporarily elevated.
    3. BULLISH_CONFIRMATION: Multi-source alignment (Social + Prediction + Price + High Volume).
    4. BEARISH_CONFIRMATION: Multi-source collapse (Social + Prediction + Price falling + High Volume).
    5. EARLY_REVERSAL: Sharp disagreement between Social narrative and Polymarket capital expectations.
    """
    results: List[DivergenceResult] = []
    now = datetime.now(timezone.utc)

    # Directional normalizations (-1.0 to +1.0)
    # 50 is neutral
    dir_social = (social_score - 50.0) / 50.0
    dir_pred = (prediction_score - 50.0) / 50.0 if prediction_score is not None else None
    dir_price = 0.0
    if price_return_1d is not None:
        dir_price = max(-1.0, min(1.0, price_return_1d / 5.0))
    elif momentum_score is not None:
        dir_price = (momentum_score - 50.0) / 50.0
    elif technical_score is not None:
        dir_price = ((technical_score / 40.0) * 100.0 - 50.0) / 50.0

    vol_ratio = volume_ratio if volume_ratio is not None else 1.0

    # -------------------------------------------------------------
    # 1. STRONG CONFIRMATION SCENARIOS
    # -------------------------------------------------------------
    # Bullish Confirmation: Social >= +0.30, Price >= +0.20, Volume >= 1.2x (and PMS >= +0.20 if available)
    if dir_social >= 0.30 and dir_price >= 0.20 and vol_ratio >= 1.2:
        if dir_pred is None or dir_pred >= 0.20:
            pred_text = f" and Polymarket probability (+{int(prediction_score)}%)" if prediction_score else ""
            results.append(DivergenceResult(
                ticker=ticker,
                type="BULLISH_CONFIRMATION",
                source_a="X_SOCIAL",
                source_b="PRICE_ACTION",
                source_c="POLYMARKET" if prediction_score else None,
                direction="BULLISH",
                strength=0.90 if dir_pred is not None and dir_pred >= 0.30 else 0.75,
                confidence=0.88,
                description=f"Strong multi-source confirmation: Social sentiment ({social_score:.0f}){pred_text} aligned with upward price momentum on heavy volume ({vol_ratio:.1f}x).",
                timestamp=now
            ))

    # Bearish Confirmation: Social <= -0.30, Price <= -0.20, Volume >= 1.2x
    elif dir_social <= -0.30 and dir_price <= -0.20 and vol_ratio >= 1.2:
        if dir_pred is None or dir_pred <= -0.20:
            pred_text = f" and Polymarket expectations ({int(prediction_score)}%)" if prediction_score else ""
            results.append(DivergenceResult(
                ticker=ticker,
                type="BEARISH_CONFIRMATION",
                source_a="X_SOCIAL",
                source_b="PRICE_ACTION",
                source_c="POLYMARKET" if prediction_score else None,
                direction="BEARISH",
                strength=0.90 if dir_pred is not None and dir_pred <= -0.30 else 0.75,
                confidence=0.88,
                description=f"Strong bearish confirmation: Social sentiment ({social_score:.0f}){pred_text} confirmed by falling price action on above-average volume ({vol_ratio:.1f}x).",
                timestamp=now
            ))

    # -------------------------------------------------------------
    # 2. DIVERGENCE SCENARIOS (Narrative / Prediction vs Price)
    # -------------------------------------------------------------
    # Bullish Divergence: Narrative/Expectations are Bullish, but Price is falling
    bullish_sources = []
    if dir_social >= 0.25:
        bullish_sources.append(f"X Social ({social_score:.0f})")
    if dir_pred is not None and dir_pred >= 0.25:
        bullish_sources.append(f"Polymarket PMS ({prediction_score:.0f})")
        
    if bullish_sources and dir_price <= -0.15:
        strength = min(1.0, (max(dir_social, dir_pred or 0.0) - dir_price) / 1.5)
        src_desc = " and ".join(bullish_sources)
        results.append(DivergenceResult(
            ticker=ticker,
            type="BULLISH_DIVERGENCE",
            source_a="SOCIAL_PREDICTION",
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
    if dir_social <= -0.25:
        bearish_sources.append(f"X Social ({social_score:.0f})")
    if dir_pred is not None and dir_pred <= -0.25:
        bearish_sources.append(f"Polymarket PMS ({prediction_score:.0f})")

    if bearish_sources and (dir_price >= 0.15 or (rsi and rsi >= 72)):
        strength = min(1.0, (dir_price - min(dir_social, dir_pred or 0.0)) / 1.5)
        src_desc = " and ".join(bearish_sources)
        results.append(DivergenceResult(
            ticker=ticker,
            type="BEARISH_DIVERGENCE",
            source_a="SOCIAL_PREDICTION",
            source_b="PRICE_ACTION",
            source_c="RSI_OVEREXTENSION" if rsi and rsi >= 72 else None,
            direction="BEARISH",
            strength=round(strength, 2),
            confidence=round(0.70 + (0.15 if len(bearish_sources) > 1 else 0.0), 2),
            description=f"Bearish Divergence: Price is extended ({dir_price:+.2f}) while {src_desc} is deteriorating. High risk of mean reversion.",
            timestamp=now
        ))

    # -------------------------------------------------------------
    # 3. EARLY REVERSAL SCENARIOS (X vs Polymarket Disconnect)
    # -------------------------------------------------------------
    # E.g. Social is very bearish (panic), but Polymarket "smart capital" is highly bullish
    if dir_pred is not None:
        # Case A: Social Bearish vs Polymarket Bullish
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
                description=f"Early Reversal Watch: Retail social narrative is fearful ({social_score:.0f}) while Prediction Markets price high success probability ({prediction_score:.0f}). Potential bottom formation.",
                timestamp=now
            ))
        # Case B: Social Hype / Euphoria vs Polymarket Bearish
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
                description=f"Early Reversal Watch: High retail euphoria on X ({social_score:.0f}) contradicts low prediction market probability ({prediction_score:.0f}). Possible bull trap.",
                timestamp=now
            ))

    return results
