from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.database.repository import (
    get_latest_ssi_snapshot, get_recent_social_posts,
    get_recent_news_items, get_recent_prediction_markets,
    get_active_divergences
)
from app.config import INITIAL_TICKERS


def generate_daily_report(db: Session) -> Dict[str, Any]:
    """
    Generates the formal Space Market Daily Report according to Spec Sections 110 & 111:
    - Sector Sentiment / Regime
    - Top Bullish & Top Bearish assets
    - Largest Sentiment change (Delta SSI)
    - Largest Prediction Market move (Delta PMS / prob pp)
    - Active Divergences across the sector
    - Price movers and volume anomalies
    - Signals & Risks
    """
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%d %b %Y").upper()

    ticker_summaries = []
    all_divergences = []
    all_catalysts = []

    for cfg in INITIAL_TICKERS:
        symbol = cfg.symbol
        snap = get_latest_ssi_snapshot(db, symbol)
        divs = get_active_divergences(db, ticker=symbol, hours=24)
        posts = get_recent_social_posts(db, ticker=symbol, hours=24)
        news = get_recent_news_items(db, ticker=symbol, days=2)
        markets = get_recent_prediction_markets(db, ticker=symbol)

        for d in divs:
            all_divergences.append({"ticker": symbol, "type": d.type, "direction": d.direction, "desc": d.description})

        for p in posts:
            if p.catalyst and p.catalyst not in [c["name"] for c in all_catalysts]:
                all_catalysts.append({"ticker": symbol, "name": p.catalyst, "importance": p.catalyst_importance, "direction": p.catalyst_direction})

        for n in news:
            if n.catalyst and n.catalyst not in [c["name"] for c in all_catalysts]:
                all_catalysts.append({"ticker": symbol, "name": n.catalyst, "importance": n.catalyst_importance, "direction": n.catalyst_direction})

        if snap:
            smi = snap.smi if snap.smi is not None else snap.ssi
            ticker_summaries.append({
                "ticker": symbol,
                "name": cfg.name,
                "smi": smi,
                "ssi": snap.social_score,
                "pms": snap.prediction_score,
                "delta_1d": snap.ssi_momentum_1d,
                "signal": snap.signal,
                "confidence": snap.confidence,
                "price": snap.price,
                "markets_count": len(markets)
            })
        else:
            ticker_summaries.append({
                "ticker": symbol,
                "name": cfg.name,
                "smi": None,
                "ssi": None,
                "pms": None,
                "delta_1d": None,
                "signal": "N/A",
                "confidence": 0.0,
                "price": None,
                "markets_count": len(markets)
            })

    # Sort by SMI descending, putting None values at the bottom
    ticker_summaries.sort(
        key=lambda x: (x["smi"] is not None, x["smi"] if x["smi"] is not None else -1.0),
        reverse=True
    )

    valid_smis = [t["smi"] for t in ticker_summaries if t["smi"] is not None]
    if valid_smis:
        avg_smi = sum(valid_smis) / len(valid_smis)
        if avg_smi >= 70.0:
            sector_sentiment = "BULLISH"
        elif avg_smi >= 55.0:
            sector_sentiment = "MODERATELY BULLISH"
        elif avg_smi >= 45.0:
            sector_sentiment = "NEUTRAL"
        elif avg_smi >= 35.0:
            sector_sentiment = "MODERATELY BEARISH"
        else:
            sector_sentiment = "BEARISH"
        avg_smi_rounded = round(avg_smi, 1)
        avg_smi_str = f"{avg_smi:.1f}/100"
    else:
        avg_smi = None
        avg_smi_rounded = None
        avg_smi_str = "AWAITING_DATA"
        sector_sentiment = "AWAITING_DATA"

    evaluated_tickers = [t for t in ticker_summaries if t["smi"] is not None]
    top_bullish = evaluated_tickers[0]["ticker"] if evaluated_tickers else "NONE"
    top_bearish = evaluated_tickers[-1]["ticker"] if evaluated_tickers else "NONE"
    top_bullish_smi = f"{evaluated_tickers[0]['smi']:.1f}" if evaluated_tickers else "N/A"
    top_bearish_smi = f"{evaluated_tickers[-1]['smi']:.1f}" if evaluated_tickers else "N/A"

    # Largest SSI increase
    evaluated_with_delta = [t for t in ticker_summaries if t["delta_1d"] is not None]
    largest_ssi_move = max(evaluated_with_delta, key=lambda x: x["delta_1d"]) if evaluated_with_delta else None
    
    # Strongest Divergences
    bull_divs = [d for d in all_divergences if d["direction"] == "BULLISH"]
    bear_divs = [d for d in all_divergences if d["direction"] == "BEARISH"]

    strongest_bull_div = bull_divs[0]["ticker"] if bull_divs else "None"
    strongest_bear_div = bear_divs[0]["ticker"] if bear_divs else "None"

    # Build Markdown Text representation matching Spec Section 111
    lines = [
        "==================================================",
        f"SPACE MARKET INTELLIGENCE DAILY REPORT",
        f"DATE: {date_str}",
        "==================================================",
        f"\n[1] SECTOR REGIME: {sector_sentiment} (Avg SMI: {avg_smi_str})",
        f"- Top Bullish:               {top_bullish} (SMI: {top_bullish_smi})",
        f"- Top Bearish:               {top_bearish} (SMI: {top_bearish_smi})",
    ]

    if largest_ssi_move:
        lines.append(f"- Largest Sentiment Move:    {largest_ssi_move['ticker']} ({largest_ssi_move['delta_1d']:+.1f} 1D)")

    lines.extend([
        f"- Strongest Bullish Div:     {strongest_bull_div}",
        f"- Strongest Bearish Div:     {strongest_bear_div}",
        "\n[2] ASSET SIGNALS & MULTIVARIATE BREAKDOWN:"
    ])

    for t in ticker_summaries:
        smi_str = f"{t['smi']:>4.1f}" if t['smi'] is not None else "  --"
        ssi_str = f"{t['ssi']:>4.1f}" if t['ssi'] is not None else "  --"
        pms_str = f"{t['pms']:.0f}" if t['pms'] is not None else "--"
        price_str = f"${t['price']:.2f}" if t['price'] is not None else "N/A"
        lines.append(f"  {t['ticker']:<5} | SMI: {smi_str} | SSI: {ssi_str} | PMS: {pms_str:>3} | Signal: {t['signal']:<12} | Conf: {t['confidence']:>3.0f}% | Price: {price_str}")

    if all_catalysts:
        lines.append("\n[3] KEY CATALYSTS DETECTED:")
        for cat in all_catalysts[:4]:
            lines.append(f"  - [{cat['ticker']}] {cat['name']} ({cat['direction']}, {cat['importance']})")

    if all_divergences:
        lines.append("\n[4] ACTIVE DIVERGENCES & REGIME ALERTS:")
        for d in all_divergences[:4]:
            lines.append(f"  - [{d['ticker']}] {d['type']}: {d['desc']}")

    lines.append("==================================================")
    markdown_text = "\n".join(lines)

    return {
        "date": date_str,
        "timestamp": now.isoformat(),
        "sector_sentiment": sector_sentiment,
        "average_smi": avg_smi_rounded,
        "top_bullish": top_bullish,
        "top_bearish": top_bearish,
        "largest_sentiment_change": {
            "ticker": largest_ssi_move["ticker"] if largest_ssi_move else None,
            "delta_1d": largest_ssi_move["delta_1d"] if largest_ssi_move else 0.0
        },
        "strongest_bullish_divergence": strongest_bull_div,
        "strongest_bearish_divergence": strongest_bear_div,
        "ticker_summaries": ticker_summaries,
        "catalysts": all_catalysts[:6],
        "active_divergences": all_divergences[:6],
        "markdown_report": markdown_text
    }
