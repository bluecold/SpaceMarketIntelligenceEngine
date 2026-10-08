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
    fundamental_score: Optional[float] = None,
    risk_score: Optional[float] = None,
    momentum_score: Optional[float] = None,
    is_mom_comparable_1d: bool = True
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
        post_count = (
            social_stats.get("effective_sample_size")
            or social_stats.get("total_posts")
            or social_stats.get("relevant_posts")
        )
        
    raw_social = social_score
    effective_social = apply_bayesian_shrinkage(raw_social, post_count) if (raw_social is not None and post_count is not None) else raw_social
    # Momentum must come from the same index as primary_index: SSI momentum is only used when SMI is unavailable
    mom_source = smi_mom_1d if smi is not None else ssi_mom_1d
    effective_mom = mom_source if (mom_source is not None and mom_source != 0.0) else None
    
    rsi = indicators.get("rsi14")
    price = indicators.get("price")
    ema200 = indicators.get("ema200")
    vol_ratio = indicators.get("volume_ratio")
    market_status = indicators.get("status")
    if market_status is None:
        market_status = "AVAILABLE" if (price is not None and price > 0) else "DATA_UNAVAILABLE"

    # Fundamental Runway & Burn analysis
    runway_info = get_fundamental_runway_info(fundamentals)
    runway_months = runway_info.get("runway_months")
    risk_tier = runway_info.get("risk_tier")
    cash_val = runway_info.get("cash")
    burn_val = runway_info.get("burn")

    has_any_data = any(x is not None for x in [smi, ssi, social_score, prediction_score, news_score, technical_score_raw, fundamental_score, indicators.get("price")])
    modifiers: List[str] = []
    is_overbought = False

    # 1. Base Signal Thresholds (Using SMI as the comprehensive index)
    if not has_any_data or (data_quality is not None and data_quality == 0.0):
        base_signal = "HOLD"
        modifiers.append("NO DATA")
    else:
        if primary_index >= settings.THRESHOLD_STRONG_BUY:
            base_signal = "STRONG BUY"
        elif primary_index >= settings.THRESHOLD_BUY:
            base_signal = "BUY"
        elif primary_index >= settings.THRESHOLD_WATCH:
            base_signal = "WATCH"
        elif primary_index > settings.THRESHOLD_HOLD:
            base_signal = "HOLD"
        elif primary_index > settings.THRESHOLD_AVOID:
            base_signal = "CAUTION"
        elif primary_index > settings.THRESHOLD_STRONG_AVOID:
            base_signal = "AVOID"
        else:
            base_signal = "STRONG AVOID"

        # Capital Preservation Gate 1: Acute Source Contradiction (source_agreement <= -0.60)
        if source_agreement is not None and source_agreement <= -0.60:
            if base_signal in ["STRONG BUY", "BUY"]:
                base_signal = "WATCH"
            if "CONFLICTING SOURCES" not in modifiers:
                modifiers.append("CONFLICTING SOURCES")

        # Capital Preservation Gate 2: Low Data Quality (< 30.0%)
        if data_quality is not None and data_quality < 30.0:
            if base_signal in ["STRONG BUY", "BUY"]:
                base_signal = "WATCH"
            if "LOW DATA QUALITY" not in modifiers:
                modifiers.append("LOW DATA QUALITY")

        # Capital Preservation Gate 3: Critical Cash Runway (< 6 months)
        if runway_months is not None and runway_months < 6.0:
            if base_signal in ["STRONG BUY", "BUY"]:
                base_signal = "BUY" if base_signal == "STRONG BUY" else "WATCH"
            if "DILUTION RISK" not in modifiers:
                modifiers.append("DILUTION RISK")

        # Capital Preservation Gate 3b: Active bearish event catalyst (launch failure, contract cancellation,
        # competitor selected, confirmed capital raise). Slow pillars cannot keep a BUY alive through such an event.
        has_bearish_event = any(
            cat.get("direction") == "BEARISH"
            and (cat.get("importance") == "CRITICAL" or cat.get("category") == "CAPITAL_RAISE")
            for cat in catalysts_found
        )
        if has_bearish_event:
            if base_signal in ["STRONG BUY", "BUY"]:
                base_signal = "WATCH"
            if "CATALYST RISK" not in modifiers:
                modifiers.append("CATALYST RISK")

        # Special Rule: Overbought restriction (RSI > 75 restricts both STRONG BUY and BUY to WATCH)
        is_overbought = False
        if rsi is not None and rsi > 75.0:
            is_overbought = True
            if base_signal in ["STRONG BUY", "BUY"]:
                base_signal = "WATCH"
            if "OVEREXTENDED" not in modifiers:
                modifiers.append("OVEREXTENDED")

        # Capital Preservation Gate 4: Elevated Volatility / Risk Governance (risk_score < RISK_GATE_THRESHOLD)
        # Size Down, Don't Veto: Cap STRONG BUY to BUY and flag for reduced position sizing (50%)
        if risk_score is not None and risk_score < settings.RISK_GATE_THRESHOLD:
            if base_signal == "STRONG BUY":
                base_signal = "BUY"
            if "HIGH RISK" not in modifiers:
                modifiers.append("HIGH RISK")

        # Market Confirmation Gate: Non-operable without active market price (restricts BUY/STRONG BUY to WATCH)
        if market_status != "AVAILABLE" or price is None or price <= 0:
            if base_signal in ["STRONG BUY", "BUY"]:
                base_signal = "WATCH"
            if "NO MKT DATA" not in modifiers:
                modifiers.append("NO MKT DATA")

    signal_modifier = " | ".join(modifiers) if modifiers else None
    full_signal = f"{base_signal} ({signal_modifier})" if signal_modifier else base_signal

    eff_momentum = momentum_score
    if eff_momentum is None and indicators:
        eff_momentum = indicators.get("momentum_score")

    # 2. Tripartite Divergence Engine (X ↔ Polymarket ↔ Price)
    active_divergences = detect_divergences(
        ticker=ticker,
        social_score=raw_social,
        prediction_score=prediction_score,
        prediction_delta_24h=eff_pred_delta,
        news_score=news_score,
        momentum_score=eff_momentum,
        technical_score=technical_score_raw,
        price_return_1d=price_change_1d,
        volume_ratio=vol_ratio,
        rsi=rsi,
        post_count=post_count,
        intraday_reversal_pct=indicators.get("intraday_reversal_pct"),
        range_location=indicators.get("range_location")
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
    elif base_signal == "BUY":
        if effective_mom is not None and effective_mom >= 3.0 and is_mom_comparable_1d:
            alerts.append({
                "id": f"{ticker}:SIGNAL:MOMENTUM_BUY",
                "ticker": ticker,
                "type": "MOMENTUM_BUY",
                "category": "SIGNAL",
                "level": "HIGH",
                "message": f"📈 {ticker} BUY signal confirmed with accelerating SMI (+{effective_mom} 1D)"
            })
        else:
            alerts.append({
                "id": f"{ticker}:SIGNAL:BUY",
                "ticker": ticker,
                "type": "BUY",
                "category": "SIGNAL",
                "level": "HIGH",
                "message": f"📈 {ticker} issued BUY signal (SMI: {primary_index:.1f}/100)"
            })
    elif base_signal == "AVOID":
        alerts.append({
            "id": f"{ticker}:SIGNAL:AVOID",
            "ticker": ticker,
            "type": "AVOID",
            "category": "SIGNAL",
            "level": "WARNING",
            "message": f"⚠️ {ticker} entered bearish AVOID regime (SMI: {primary_index:.1f}/100)"
        })
    elif base_signal == "WATCH" and primary_index >= 60.0:
        alerts.append({
            "id": f"{ticker}:SIGNAL:WATCH_BULLISH",
            "ticker": ticker,
            "type": "WATCH_BULLISH",
            "category": "SIGNAL",
            "level": "INFO",
            "message": f"👀 {ticker} emerging into bullish WATCH territory (SMI: {primary_index:.1f}/100)"
        })
    elif base_signal == "CAUTION" and primary_index <= 40.0:
        alerts.append({
            "id": f"{ticker}:SIGNAL:CAUTION_BEARISH",
            "ticker": ticker,
            "type": "CAUTION_BEARISH",
            "category": "SIGNAL",
            "level": "INFO",
            "message": f"👀 {ticker} slipping into bearish CAUTION territory (SMI: {primary_index:.1f}/100)"
        })

    # SMI 24h Momentum shift alerts
    if effective_mom is not None and is_mom_comparable_1d:
        if effective_mom >= 5.0:
            alerts.append({
                "id": f"{ticker}:MOMENTUM:ACCELERATION",
                "ticker": ticker,
                "type": "MOMENTUM_ACCELERATION",
                "category": "SIGNAL",
                "level": "INFO",
                "message": f"⚡ {ticker}: SMI momentum accelerated +{effective_mom:.1f} pts in 24h"
            })
        elif effective_mom <= -5.0:
            alerts.append({
                "id": f"{ticker}:MOMENTUM:BREAKDOWN",
                "ticker": ticker,
                "type": "MOMENTUM_BREAKDOWN",
                "category": "SIGNAL",
                "level": "WARNING",
                "message": f"📉 {ticker}: SMI momentum dropped {effective_mom:.1f} pts in 24h"
            })

    # X attention spike: abnormal mention volume, labelled with the direction the conversation is leaning
    attention_ratio = social_stats.get("mention_volume_ratio") if social_stats else None
    spike_ratio = getattr(settings, "SOCIAL_ATTENTION_SPIKE_RATIO", 2.0)
    if attention_ratio is not None and attention_ratio >= spike_ratio:
        if effective_social is not None and effective_social >= 55.0:
            lean = "bullish"
        elif effective_social is not None and effective_social <= 45.0:
            lean = "bearish"
        else:
            lean = "mixed"
        alerts.append({
            "id": f"{ticker}:SIGNAL:ATTENTION_SPIKE",
            "ticker": ticker,
            "type": "ATTENTION_SPIKE",
            "category": "SIGNAL",
            "level": "WARNING" if lean == "mixed" else "HIGH",
            "message": f"📣 {ticker}: X mention volume {attention_ratio:.1f}x normal with {lean} sentiment"
                       + (f" (SSI {effective_social:.0f})" if effective_social is not None else "")
        })

    for div in active_divergences:
        div_level = (
            "CRITICAL" if "BEARISH_CONFIRMATION" in div.type
            else "HIGH" if ("CONFIRMATION" in div.type or "DIVERGENCE" in div.type)
            else "MEDIUM"
        )
        alerts.append({
            "id": f"{ticker}:DIVERGENCE:{div.type}:{div.direction}",
            "ticker": ticker,
            "type": div.type,
            "category": "DIVERGENCE",
            "level": div_level,
            "message": f"⚠️ {ticker}: {div.description}"
        })

    seen_cat_alerts: Set[str] = set()
    for cat in catalysts_found:
        imp = cat.get("importance")
        if imp in ("CRITICAL", "HIGH"):
            cat_key = str(cat.get("category", "")).upper()
            if cat_key and cat_key not in seen_cat_alerts:
                seen_cat_alerts.add(cat_key)
                cat_name = cat_key.replace("_", " ").title()
                cat_type = "CRITICAL_CATALYST" if imp == "CRITICAL" else "HIGH_CATALYST"
                cat_level = "CRITICAL" if imp == "CRITICAL" else "HIGH"
                alerts.append({
                    "id": f"{ticker}:CATALYST:{cat_key}",
                    "ticker": ticker,
                    "type": cat_type,
                    "category": "CATALYST",
                    "level": cat_level,
                    "message": f"⚡ {cat_name} detected on {ticker} ({imp.title()} Catalyst)"
                })


    # Fundamental Balance Sheet & Runway Alerts
    cash_m = (cash_val / 1e6) if cash_val is not None else 0.0
    burn_m = (burn_val / 1e6) if burn_val is not None else 0.0
    as_of_str = f" as of {runway_info.get('as_of_date')}" if runway_info.get('as_of_date') else ""
    if runway_months is not None and runway_months < 6.0:
        if runway_months == 0.0:
            msg = f"🚨 {ticker} Critical Runway Alert: Cash exhausted (0.0 months remaining, ${cash_m:.0f}M cash / ${burn_m:.0f}M annual burn{as_of_str}) — acute survival/insolvency risk"
        else:
            msg = f"🚨 {ticker} Critical Runway Alert: {runway_months:.1f} months of cash remaining (${cash_m:.0f}M cash / ${burn_m:.0f}M annual burn{as_of_str}) — acute dilution/capital raise risk"
        alerts.append({
            "id": f"{ticker}:FUNDAMENTAL:CAPITAL_RAISE_RISK",
            "ticker": ticker,
            "type": "CAPITAL_RAISE_RISK",
            "category": "FUNDAMENTAL",
            "level": "CRITICAL",
            "message": msg
        })
    elif runway_months is not None and runway_months < 12.0 and risk_tier == "HIGH":
        alerts.append({
            "id": f"{ticker}:FUNDAMENTAL:DILUTION_WATCH",
            "ticker": ticker,
            "type": "DILUTION_WATCH",
            "category": "FUNDAMENTAL",
            "level": "HIGH",
            "message": f"⚠️ {ticker} Low Runway Alert: {runway_months:.1f} months of cash remaining (${cash_m:.0f}M cash{as_of_str}) — watch for financing announcements"
        })

    # Technical Structural & Price Action Alerts
    intraday_rev = indicators.get("intraday_reversal_pct")
    range_loc = indicators.get("range_location")
    d_high = indicators.get("day_high")
    b_lower = indicators.get("bollinger_lower")

    # A. Bearish Intraday Reversal / Exhaustion
    if intraday_rev is not None and intraday_rev <= -4.5:
        if (range_loc is None or range_loc <= 0.38) and (vol_ratio is not None and vol_ratio >= 1.15):
            high_str = f" (${d_high:.2f})" if d_high else ""
            rev_level = "HIGH" if intraday_rev <= -7.0 else "WARNING"
            alerts.append({
                "id": f"{ticker}:TECHNICAL:INTRADAY_REVERSAL",
                "ticker": ticker,
                "type": "INTRADAY_REVERSAL_EXHAUSTION",
                "category": "TECHNICAL",
                "level": rev_level,
                "message": f"📉 {ticker}: Bearish intraday reversal ({intraday_rev:.1f}% from session high{high_str}) on {vol_ratio:.1f}x volume"
            })

    # B. RSI Extremes
    if rsi is not None:
        if rsi >= 75.0:
            alerts.append({
                "id": f"{ticker}:TECHNICAL:RSI_OVERBOUGHT",
                "ticker": ticker,
                "type": "RSI_OVERBOUGHT",
                "category": "TECHNICAL",
                "level": "WARNING",
                "message": f"⚠️ {ticker}: RSI severely overbought ({rsi:.1f}) — elevated mean-reversion risk"
            })
        elif rsi <= 30.0:
            alerts.append({
                "id": f"{ticker}:TECHNICAL:RSI_OVERSOLD",
                "ticker": ticker,
                "type": "RSI_OVERSOLD",
                "category": "TECHNICAL",
                "level": "WARNING",
                "message": f"⚠️ {ticker}: RSI deeply oversold ({rsi:.1f}) — potential technical exhaustion"
            })

    # C. 200 EMA Support Breakdown on Volume
    if price is not None and ema200 is not None and price < ema200:
        if indicators.get("ema200_reliable", True):
            if price_change_1d is not None and price_change_1d <= -2.0 and vol_ratio is not None and vol_ratio >= 1.2:
                alerts.append({
                    "id": f"{ticker}:TECHNICAL:EMA200_BREAKDOWN",
                    "ticker": ticker,
                    "type": "EMA200_BREAKDOWN",
                    "category": "TECHNICAL",
                    "level": "HIGH",
                    "message": f"📉 {ticker}: Lost institutional 200 EMA support (${ema200:.2f}) on heavy volume"
                })

    # D. Bollinger Bands Lower Piercing
    if price is not None and b_lower is not None and price < b_lower:
        alerts.append({
            "id": f"{ticker}:TECHNICAL:BOLLINGER_LOWER_BREACH",
            "ticker": ticker,
            "type": "BOLLINGER_LOWER_BREACH",
            "category": "TECHNICAL",
            "level": "WARNING",
            "message": f"⚡ {ticker}: Pierced 2σ Lower Bollinger Band (${b_lower:.2f}) — extreme stretch"
        })

    # 4. Build Detailed Multi-Source "WHY?" Reasons (Explanations)
    reasons = []

    # Fundamental Balance Sheet reasons
    if runway_months is not None:
        if runway_months == 0.0:
            reasons.append(f"- 🚨 Critical Capital Exhaustion: 0.0 months of cash runway remaining (${cash_m:.0f}M cash / ${burn_m:.0f}M burn{as_of_str}) — severe dilution/insolvency risk")
        elif runway_months < 6.0:
            reasons.append(f"- 🚨 Critical Capital Raise Risk: only {runway_months:.1f} months of cash runway remaining before dilution")
        elif runway_months < 12.0:
            reasons.append(f"- Low cash runway: {runway_months:.1f} months of liquidity available (${cash_m:.0f}M cash)")
        elif runway_months >= 24.0 or runway_months == 999.0:
            reasons.append(f"+ Strong balance sheet runway: >24 months of cash reserves (low dilution risk)")

    # Social Narrative reasons: SSI is centered on the ticker's own norm, so distance from 50 is the signal
    social_baseline = social_stats.get("social_baseline") if social_stats else None
    baseline_txt = f" (raw {social_stats.get('social_polarity_raw'):.0f} vs norm {social_baseline:.0f})" if (
        social_baseline is not None and social_stats.get("social_polarity_raw") is not None
    ) else ""
    if effective_social is not None and (post_count is None or post_count > 0):
        if effective_social >= 58.0:
            reasons.append(f"+ X sentiment more bullish than this ticker's norm: SSI {effective_social:.0f}{baseline_txt}")
        elif effective_social <= 42.0:
            reasons.append(f"- X sentiment more bearish than this ticker's norm: SSI {effective_social:.0f}{baseline_txt}")

    if attention_ratio is not None and attention_ratio >= spike_ratio:
        reasons.append(f"! X mention volume {attention_ratio:.1f}x this ticker's normal daily rate")

    # No Data State reason
    if not has_any_data or (data_quality is not None and data_quality == 0.0):
        reasons.append("- No data sources available for evaluation (NO DATA)")

    if effective_mom is not None and effective_mom != 0.0:
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
                existing_rank = IMPORTANCE_RANK.get(existing_imp, 99)
                if current_rank < existing_rank:
                    unique_catalysts[cat_type] = cat
                elif current_rank == existing_rank:
                    # Risk-first tie breaker (BEARISH priority for capital preservation)
                    if cat.get("direction") == "BEARISH" and unique_catalysts[cat_type].get("direction") != "BEARISH":
                        unique_catalysts[cat_type] = cat

        # Resolve inter-category conflicts: LAUNCH_FAILURE / LAUNCH_DELAY supersede generic LAUNCH
        if "LAUNCH_FAILURE" in unique_catalysts or "LAUNCH_DELAY" in unique_catalysts:
            unique_catalysts.pop("LAUNCH", None)
        if "LAUNCH_FAILURE" in unique_catalysts and "LAUNCH_DELAY" in unique_catalysts:
            unique_catalysts.pop("LAUNCH_DELAY", None)

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
        "alerts": alerts,
        "social_score_raw": raw_social,
        "social_score_effective": effective_social
    }
