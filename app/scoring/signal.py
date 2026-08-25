from typing import Dict, Any, Optional, List
from app.config import settings
from app.divergence.detector import detect_divergences, DivergenceResult


def generate_signal_and_explanation(
    ticker: str,
    smi: Optional[float] = None,
    ssi: Optional[float] = None,
    social_score: Optional[float] = None,
    technical_score_raw: Optional[float] = None,
    indicators: Optional[Dict[str, Any]] = None,
    social_stats: Optional[Dict[str, Any]] = None,
    catalysts_found: Optional[List[Dict[str, Any]]] = None,
    smi_mom_1d: float = 0.0,
    ssi_mom_1d: float = 0.0,
    price_change_1d: Optional[float] = None,
    prediction_score: Optional[float] = None,
    prediction_delta_24h: Optional[float] = None,
    prediction_data: Optional[Dict[str, Any]] = None,
    news_score: Optional[float] = None
) -> Dict[str, Any]:
    """
    Generates quantitative trading signal, multi-source divergence detection,
    structured alerts, and natural language "WHY?" explanations according to SMIE v2.0.
    """
    indicators = indicators or {}
    social_stats = social_stats or {}
    catalysts_found = catalysts_found or []
    
    # Extract prediction delta if not directly provided
    eff_pred_delta = prediction_delta_24h
    if eff_pred_delta is None and prediction_data:
        eff_pred_delta = prediction_data.get("pms_delta_24h") if prediction_data.get("pms_delta_24h") is not None else prediction_data.get("delta_24h")

    # Primary composite index (SMI with fallback to SSI)
    primary_index = smi if smi is not None else (ssi if ssi is not None else 50.0)
    effective_social = social_score if social_score is not None else primary_index
    effective_mom = smi_mom_1d if smi_mom_1d != 0.0 else ssi_mom_1d
    
    rsi = indicators.get("rsi14")
    price = indicators.get("price")
    ema200 = indicators.get("ema200")
    vol_ratio = indicators.get("volume_ratio")
    market_status = indicators.get("status", "AVAILABLE")

    # 1. Base Signal Thresholds (Using SMI as the comprehensive index)
    if primary_index >= settings.THRESHOLD_STRONG_BUY:
        base_signal = "STRONG BUY"
    elif primary_index >= settings.THRESHOLD_BUY:
        base_signal = "BUY"
    elif primary_index >= settings.THRESHOLD_WATCH:
        base_signal = "WATCH"
    elif primary_index >= settings.THRESHOLD_HOLD:
        base_signal = "HOLD"
    elif primary_index >= settings.THRESHOLD_AVOID:
        base_signal = "AVOID"
    else:
        base_signal = "STRONG AVOID"

    signal_modifier = None

    # Special Rule: Overbought restriction (RSI > 75 restricts STRONG BUY to WATCH with modifier)
    is_overbought = False
    if rsi is not None and rsi > 75.0:
        is_overbought = True
        if base_signal == "STRONG BUY":
            base_signal = "WATCH"
            signal_modifier = "OVEREXTENDED"

    if market_status != "AVAILABLE":
        if base_signal in ["STRONG BUY", "BUY"]:
            signal_modifier = "NO MKT DATA"

    full_signal = f"{base_signal} ({signal_modifier})" if signal_modifier else base_signal

    # 2. Tripartite Divergence Engine (X ↔ Polymarket ↔ Price)
    active_divergences = detect_divergences(
        ticker=ticker,
        social_score=effective_social,
        prediction_score=prediction_score,
        prediction_delta_24h=eff_pred_delta,
        news_score=news_score,
        technical_score=technical_score_raw,
        price_return_1d=price_change_1d,
        volume_ratio=vol_ratio,
        rsi=rsi
    )

    primary_divergence_text = "NONE"
    if active_divergences:
        primary_divergence_text = f"{active_divergences[0].type}: {active_divergences[0].description}"

    # 3. Browser Alerts Generation
    alerts = []
    if base_signal == "STRONG BUY" or "STRONG BUY" in full_signal:
        alerts.append({
            "ticker": ticker,
            "type": "STRONG_BUY",
            "level": "CRITICAL",
            "message": f"🚀 {ticker} reached STRONG BUY signal (SMI: {primary_index}/100)"
        })
    elif base_signal == "BUY" and effective_mom >= 3.0:
        alerts.append({
            "ticker": ticker,
            "type": "MOMENTUM_BUY",
            "level": "HIGH",
            "message": f"📈 {ticker} BUY signal confirmed with accelerating SMI (+{effective_mom} 1D)"
        })

    for div in active_divergences:
        alerts.append({
            "ticker": ticker,
            "type": div.type,
            "level": "HIGH" if "CONFIRMATION" in div.type or "DIVERGENCE" in div.type else "MEDIUM",
            "message": f"⚠️ {ticker}: {div.description}"
        })

    for cat in catalysts_found:
        if cat.get("importance") == "CRITICAL":
            alerts.append({
                "ticker": ticker,
                "type": "CRITICAL_CATALYST",
                "level": "CRITICAL",
                "message": f"⚡ Critical Catalyst detected on {ticker}: {cat.get('category')}"
            })

    # 4. Build Detailed Multi-Source "WHY?" Reasons (Explanations)
    reasons = []

    # Social Narrative reasons
    bull_pct = social_stats.get("weighted_bullish_pct", 0)
    bear_pct = social_stats.get("weighted_bearish_pct", 0)
    if bull_pct >= 60.0:
        reasons.append(f"+ High social bullish sentiment: {bull_pct}% of relevant posts are bullish")
    elif bear_pct >= 40.0:
        reasons.append(f"- Elevated social bearish sentiment: {bear_pct}% of relevant posts are bearish")

    if effective_mom > 2.0:
        reasons.append(f"+ Momentum rising strongly (+{effective_mom} in 24h)")
    elif effective_mom < -2.0:
        reasons.append(f"- Momentum deteriorating ({effective_mom} in 24h)")

    # Prediction Market reasons
    if prediction_score is not None:
        if prediction_score >= 65.0:
            reasons.append(f"+ Prediction Markets (Polymarket) imply bullish event expectations (PMS: {prediction_score:.0f}/100)")
        elif prediction_score <= 40.0:
            reasons.append(f"- Prediction Markets (Polymarket) imply low event probabilities (PMS: {prediction_score:.0f}/100)")

    # Catalysts
    for cat in catalysts_found[:3]:
        cat_name = str(cat.get("category", "")).replace("_", " ").title()
        direction = cat.get("direction")
        imp = cat.get("importance", "MEDIUM")
        prefix = f"[{imp}] " if imp in ["HIGH", "CRITICAL"] else ""
        if direction == "BULLISH":
            reasons.append(f"+ Positive catalyst: {prefix}{cat_name}")
        else:
            reasons.append(f"- Risk catalyst: {prefix}{cat_name}")

    # Technical Market reasons
    if market_status == "AVAILABLE":
        if price is not None and ema200 is not None:
            if price > ema200:
                reasons.append(f"+ Price (${price:.2f}) is trading above 200 EMA (${ema200:.2f})")
            else:
                reasons.append(f"- Price (${price:.2f}) is trading below 200 EMA (${ema200:.2f})")

        if rsi is not None:
            if 50.0 <= rsi <= 70.0:
                reasons.append(f"+ RSI ({rsi:.1f}) is in bullish neutral territory")
            elif rsi > 75.0:
                reasons.append(f"- RSI ({rsi:.1f}) is overbought (>75)")
            elif rsi < 35.0:
                reasons.append(f"- RSI ({rsi:.1f}) is severely depressed (<35)")

        if vol_ratio is not None and vol_ratio >= 1.3:
            reasons.append(f"+ Volume ratio is elevated ({vol_ratio:.2f}x 20 MA)")
    else:
        reasons.append("! Market price data is currently unavailable for technical indicator validation")

    explanation_text = "\n".join(reasons) if reasons else "Neutral baseline signal based on current inputs."

    return {
        "signal": full_signal,
        "base_signal": base_signal,
        "signal_modifier": signal_modifier,
        "is_overbought": is_overbought,
        "divergence": primary_divergence_text,
        "active_divergences": [d.model_dump() for d in active_divergences],
        "explanation": explanation_text,
        "reasons": reasons,
        "alerts": alerts
    }
