from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.database.repository import (
    get_latest_ssi_snapshot, get_latest_market_snapshot, get_active_divergences
)
from app.config import INITIAL_TICKERS

router = APIRouter(tags=["Dashboard"])


@router.get("/api/dashboard")
def get_dashboard(db: Session = Depends(get_db)) -> Dict[str, Any]:
    rankings = []
    alerts = []
    
    for ticker_config in INITIAL_TICKERS:
        symbol = ticker_config.symbol
        ssi_snap = get_latest_ssi_snapshot(db, symbol)
        mkt_snap = get_latest_market_snapshot(db, symbol)

        if ssi_snap:
            # Check active divergences for this ticker
            divs = get_active_divergences(db, ticker=symbol, hours=24)
            primary_div = divs[0].type if divs else "NONE"

            smi_val = ssi_snap.smi if ssi_snap.smi is not None else ssi_snap.ssi
            ssi_val = ssi_snap.social_score  # Pure Social

            rankings.append({
                "ticker": symbol,
                "name": ticker_config.name,
                "smi": round(smi_val, 1),
                "ssi": round(ssi_val, 1),
                "pms": round(ssi_snap.prediction_score, 1) if ssi_snap.prediction_score is not None else None,
                "delta_1d": ssi_snap.ssi_momentum_1d,
                "social_score": round(ssi_snap.social_score, 1),
                "prediction_score": round(ssi_snap.prediction_score, 1) if ssi_snap.prediction_score is not None else None,
                "news_score": round(ssi_snap.news_score, 1) if ssi_snap.news_score is not None else None,
                "momentum_score": round(ssi_snap.momentum_score, 1) if ssi_snap.momentum_score is not None else None,
                "risk_score": round(ssi_snap.risk_score, 1) if ssi_snap.risk_score is not None else None,
                "technical_score": ssi_snap.technical_score,
                "market_score": round((ssi_snap.technical_score / 40.0) * 100.0, 1) if ssi_snap.technical_score is not None else None,
                "signal": ssi_snap.signal,
                "divergence": primary_div,
                "confidence": round(ssi_snap.confidence, 1),
                "data_quality": round(ssi_snap.data_quality if ssi_snap.data_quality is not None else ssi_snap.data_completeness, 1),
                "data_completeness": round(ssi_snap.data_completeness, 1),
                "price": ssi_snap.price,
                "market_status": mkt_snap.market_status if mkt_snap else "AVAILABLE",
                "timestamp": ssi_snap.timestamp.isoformat() + "Z" if ssi_snap.timestamp else None
            })

            # Check if active alert applies
            if "STRONG BUY" in ssi_snap.signal:
                alerts.append({
                    "ticker": symbol,
                    "type": "STRONG_BUY",
                    "level": "CRITICAL",
                    "message": f"🚀 {symbol} issued a STRONG BUY signal (SMI: {smi_val:.0f}/100)"
                })
            
            for d in divs:
                alerts.append({
                    "ticker": symbol,
                    "type": d.type,
                    "level": "HIGH",
                    "message": f"⚠️ {symbol}: {d.description}"
                })
        else:
            rankings.append({
                "ticker": symbol,
                "name": ticker_config.name,
                "smi": 50.0,
                "ssi": 50.0,
                "pms": None,
                "delta_1d": 0.0,
                "social_score": 50.0,
                "prediction_score": None,
                "news_score": None,
                "momentum_score": None,
                "risk_score": None,
                "technical_score": None,
                "market_score": None,
                "signal": "N/A",
                "divergence": "NONE",
                "confidence": 0.0,
                "data_quality": 0.0,
                "data_completeness": 0.0,
                "price": None,
                "market_status": "DATA_UNAVAILABLE",
                "timestamp": None
            })

    # Sort rankings by SMI descending
    rankings.sort(key=lambda x: x["smi"], reverse=True)

    return {
        "title": "SPACE MARKET INTELLIGENCE ENGINE",
        "last_update": rankings[0]["timestamp"] if rankings and rankings[0]["timestamp"] else None,
        "count": len(rankings),
        "rankings": rankings,
        "alerts": alerts
    }
