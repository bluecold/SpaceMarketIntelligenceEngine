from typing import Dict, Any, Optional, List, Set
from app.config import settings
from app.divergence.detector import detect_divergences, DivergenceResult
from app.scoring.social import apply_bayesian_shrinkage
from app.scoring.fundamentals import get_fundamental_runway_info
from app.sentiment.weighting import IMPORTANCE_RANK


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
    news_score: Optional[float] = None,
    source_agreement: Optional[float] = None,
    data_quality: Optional[float] = None,
    fundamentals: Optional[Dict[str, Any]] = None,
    fundamental_score: Optional[float] = None
) -> Dict[str, Any]:
    """
    Generates quantitative trading signal, multi-source divergence detection,
    structured alerts, and natural language "WHY?" explanations according to SMIE v2.0.
    Enforces Capital Preservation / Flat gates when edge is unproven or data is in acute conflict.
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
    
    # Extract post count to apply Bayesian shrinkage on small social sample sizes
    post_count = None
    if social_stats:
        post_count = social_stats.get("total_posts") or social_stats.get("relevant_posts")
        
    raw_social = social_score if social_score is not None else primary_index
    effective_social = apply_bayesian_shrinkage(raw_social, post_count)
    effective_mom = smi_mom_1d if smi_mom_1d != 0.0 else ssi_mom_1d
    
    rsi = indicators.get("rsi14")
    price = indicators.get("price")
    ema200 = indicators.get("ema200")
    vol_ratio = indicators.get("volume_ratio")
    market_status = indicators.get("status", "AVAILABLE")

    # Fundamental Runway & Burn analysis
    runway_info = get_fundamental_runway_info(fundamentals)
    runway_months = runway_info.get("runway_months")
    risk_tier = runway_info.get("risk_tier")
    cash_val = runway_info.get("cash")
    burn_val = runway_info.get("burn")

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

    # Capital Preservation Gate 1: Acute Source Contradiction (source_agreement <= -0.60)
    if source_agreement is not None and source_agreement <= -0.60:
        if base_signal in ["STRONG BUY", "BUY"]:
            base_signal = "WATCH"
            signal_modifier = "CONFLICTING SOURCES"

    # Capital Preservation Gate 2: Low Data Quality (< 30.0%)
    if data_quality is not None and data_quality < 30.0:
        if base_signal in ["STRONG BUY", "BUY"]:
            base_signal = "WATCH"
            signal_modifier = "LOW DATA QUALITY"

    # Capital Preservation Gate 3: Critical Cash Runway (< 6 months)
    if runway_months is not None and runway_months < 6.0:
        if base_signal in ["STRONG BUY", "BUY"]:
            base_signal = "BUY" if base_signal == "STRONG BUY" else "WATCH"
            signal_modifier = "DILUTION RISK" if not signal_modifier else f"{signal_modifier} | DILUTION RISK"

    # Special Rule: Overbought restriction (RSI > 75 restricts STRONG BUY to WATCH, warns on BUY)
    is_overbought = False
    if rsi is not None and rsi > 75.0:
        is_overbought = True
        if base_signal == "STRONG BUY":
            base_signal = "WATCH"
            signal_modifier = "OVEREXTENDED"
        elif base_signal == "BUY":
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
        rsi=rsi,
        post_count=post_count
    )

    primary_divergence_text = "NONE"
    if active_divergences:
        primary_divergence_text = f"{active_divergences[0].type}: {active_divergences[0].description}"

    # 3. Browser Alerts Generation
    alerts = []
    if base_signal == "STRONG BUY" or "STRONG BUY" in full_signal:
        alerts.append({
            "id": f"{ticker}:SIGNAL:STRONG_BUY",
            "ticker": ticker,
            "type": "STRONG_BUY",
            "category": "SIGNAL",
            "level": "CRITICAL",
            "message": f"🚀 {ticker} reached STRONG BUY signal (SMI: {primary_index}/100)"
        })
    elif base_signal == "STRONG AVOID":
        alerts.append({
            "id": f"{ticker}:SIGNAL:STRONG_AVOID",
            "ticker": ticker,
            "type": "STRONG_AVOID",
            "category": "SIGNAL",
            "level": "CRITICAL",
            "message": f"🛑 {ticker} issued STRONG AVOID signal (SMI: {primary_index}/100) — high capital risk"
        })
    elif base_signal == "BUY" and effective_mom >= 3.0:
        alerts.append({
            "id": f"{ticker}:SIGNAL:MOMENTUM_BUY",
            "ticker": ticker,
            "type": "MOMENTUM_BUY",
            "category": "SIGNAL",
            "level": "HIGH",
            "message": f"📈 {ticker} BUY signal confirmed with accelerating SMI (+{effective_mom} 1D)"
        })

    for div in active_divergences:
        div_level = (
            "CRITICAL" if "BEARISH_CONFIRMATION" in div.type
            else "HIGH" if ("CONFIRMATION" in div.type or "DIVERGENCE" in div.type)
            else "MEDIUM"
        )
        alerts.append({
            "id": f"{ticker}:DIVERGENCE:{div.type}",
            "ticker": ticker,
            "type": div.type,
            "category": "DIVERGENCE",
            "level": div_level,
            "message": f"⚠️ {ticker}: {div.description}"
        })

    seen_cat_alerts: Set[str] = set()
    for cat in catalysts_found:
        if cat.get("importance") == "CRITICAL":
            cat_key = str(cat.get("category", "")).upper()
            if cat_key and cat_key not in seen_cat_alerts:
                seen_cat_alerts.add(cat_key)
                cat_name = cat_key.replace("_", " ").title()
                alerts.append({
                    "id": f"{ticker}:CATALYST:{cat_key}",
                    "ticker": ticker,
                    "type": "CRITICAL_CATALYST",
                    "category": "CATALYST",
                    "level": "CRITICAL",
                    "message": f"⚡ Critical Catalyst detected on {ticker}: {cat_name}"
                })

    # Fundamental Balance Sheet & Runway Alerts
    cash_m = (cash_val / 1e6) if cash_val else 0.0
    burn_m = (burn_val / 1e6) if burn_val else 0.0
    if runway_months is not None and runway_months < 6.0:
        alerts.append({
            "id": f"{ticker}:FUNDAMENTAL:CAPITAL_RAISE_RISK",
            "ticker": ticker,
            "type": "CAPITAL_RAISE_RISK",
            "category": "FUNDAMENTAL",
            "level": "CRITICAL",
            "message": f"🚨 {ticker} Critical Runway Alert: {runway_months:.1f} months of cash remaining (${cash_m:.0f}M cash / ${burn_m:.0f}M annual burn) — acute dilution/capital raise risk"
        })
    elif runway_months is not None and runway_months < 12.0 and risk_tier == "HIGH":
        alerts.append({
            "id": f"{ticker}:FUNDAMENTAL:DILUTION_WATCH",
            "ticker": ticker,
            "type": "DILUTION_WATCH",
            "category": "FUNDAMENTAL",
            "level": "HIGH",
            "message": f"⚠️ {ticker} Low Runway Alert: {runway_months:.1f} months of cash remaining (${cash_m:.0f}M cash) — watch for financing announcements"
        })

    # 4. Build Detailed Multi-Source "WHY?" Reasons (Explanations)
    reasons = []

    # Fundamental Balance Sheet reasons
    if runway_months is not None:
        if runway_months < 6.0:
            reasons.append(f"- 🚨 Critical Capital Raise Risk: only {runway_months:.1f} months of cash runway remaining before dilution")
        elif runway_months < 12.0:
            reasons.append(f"- Low cash runway: {runway_months:.1f} months of liquidity available (${cash_m:.0f}M cash)")
        elif runway_months >= 24.0 or runway_months == 999.0:
            reasons.append(f"+ Strong balance sheet runway: >24 months of cash reserves (low dilution risk)")

    # Social Narrative reasons
    bull_pct = social_stats.get("weighted_bullish_pct", 0)
    bear_pct = social_stats.get("weighted_bearish_pct", 0)
    if bull_pct >= 60.0:
        reasons.append(f"+ High social bullish sentiment: {bull_pct}% of relevant posts are bullish")
    elif bear_pct >= 40.0:
        reasons.append(f"- Elevated social bearish sentiment: {bear_pct}% of relevant posts are bearish")

    if effective_mom >= 8.0:
        reasons.append(f"+ Rapid SMI acceleration (+{effective_mom:.1f} pts in 24h): strong momentum expansion")
    elif effective_mom >= 4.0:
        reasons.append(f"+ SMI momentum rising (+{effective_mom:.1f} pts in 24h)")
    elif effective_mom <= -8.0:
        reasons.append(f"- Severe SMI breakdown ({effective_mom:.1f} pts in 24h): rapid sentiment drop")
    elif effective_mom <= -4.0:
        reasons.append(f"- SMI momentum deteriorating ({effective_mom:.1f} pts in 24h)")

    # Prediction Market reasons
    if prediction_score is not None:
        if prediction_score >= 65.0:
            reasons.append(f"+ Prediction Markets (Polymarket) imply bullish event expectations (PMS: {prediction_score:.0f}/100)")
        elif prediction_score <= 40.0:
            reasons.append(f"- Prediction Markets (Polymarket) imply low event probabilities (PMS: {prediction_score:.0f}/100)")

    # Catalysts (Deduplicate by category keeping max importance, rank by hierarchy, and take top 3)
    if catalysts_found:
        unique_catalysts = {}
        for cat in catalysts_found:
            cat_type = cat.get("category")
            if not cat_type:
                continue
            imp = cat.get("importance", "MEDIUM")
            current_rank = IMPORTANCE_RANK.get(imp, 99)
            if cat_type not in unique_catalysts:
                unique_catalysts[cat_type] = cat
            else:
                existing_imp = unique_catalysts[cat_type].get("importance", "MEDIUM")
                if current_rank < IMPORTANCE_RANK.get(existing_imp, 99):
                    unique_catalysts[cat_type] = cat

        sorted_catalysts = sorted(
            unique_catalysts.values(),
            key=lambda c: (
                IMPORTANCE_RANK.get(c.get("importance", "MEDIUM"), 99),
                0 if c.get("direction") == "BEARISH" else 1
            )
        )

        for cat in sorted_catalysts[:3]:
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
