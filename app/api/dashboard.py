from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.database.repository import (
    get_latest_ssi_snapshots_batch,
    get_latest_market_snapshots_batch,
    get_active_divergences_batch,
    utc_now
)
from app.config import INITIAL_TICKERS

router = APIRouter(tags=["Dashboard"])


@router.get("/api/dashboard")
def get_dashboard(db: Session = Depends(get_db)) -> Dict[str, Any]:
    rankings = []
    alerts = []
    
    ticker_symbols = [t.symbol for t in INITIAL_TICKERS]
    
    # 3 Consolidated Batch Queries (eliminates N+1 DB queries)
    ssi_snaps = get_latest_ssi_snapshots_batch(db, tickers=ticker_symbols)
    mkt_snaps = get_latest_market_snapshots_batch(db, tickers=ticker_symbols)
    divs_by_ticker = get_active_divergences_batch(db, hours=24, tickers=ticker_symbols)
    
    for ticker_config in INITIAL_TICKERS:
        symbol = ticker_config.symbol
        ssi_snap = ssi_snaps.get(symbol)
        mkt_snap = mkt_snaps.get(symbol)
        divs = divs_by_ticker.get(symbol, [])

        if ssi_snap:
            # Stale Data Calculation
            now_dt = utc_now()
            age_hours = None
            is_stale = False
            if ssi_snap.timestamp:
                snap_dt = ssi_snap.timestamp
                if snap_dt.tzinfo is not None:
                    snap_dt = snap_dt.replace(tzinfo=None)
                age_hours = round(max(0.0, (now_dt - snap_dt).total_seconds() / 3600.0), 1)
                is_stale = age_hours >= 6.0

            # Check active divergences for this ticker
            primary_div = divs[0].type if divs else "NONE"

            smi_val = ssi_snap.smi if ssi_snap.smi is not None else ssi_snap.ssi
            ssi_val = ssi_snap.social_score
            sig_str = ssi_snap.signal or "N/A"
            base_sig = ssi_snap.base_signal or sig_str
            mod_sig = ssi_snap.signal_modifier

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
                "signal": sig_str,
                "base_signal": base_sig,
                "signal_modifier": mod_sig,
                "divergence": primary_div,
                "confidence": round(ssi_snap.confidence, 1),
                "data_quality": round(ssi_snap.data_quality if ssi_snap.data_quality is not None else ssi_snap.data_completeness, 1),
                "data_completeness": round(ssi_snap.data_completeness, 1),
                "price": ssi_snap.price,
                "market_status": mkt_snap.market_status if mkt_snap else "AVAILABLE",
                "timestamp": ssi_snap.timestamp.isoformat() + "Z" if ssi_snap.timestamp else None,
                "data_age_hours": age_hours,
                "is_stale": is_stale
            })

            # Check if active alert applies
            if "STRONG BUY" in ssi_snap.signal:
                alerts.append({
                    "ticker": symbol,
                    "type": "STRONG_BUY",
                    "level": "CRITICAL",
                    "message": f"🚀 {symbol} issued a STRONG BUY signal (SMI: {smi_val:.0f}/100)"
                })
            elif "STRONG AVOID" in ssi_snap.signal:
                alerts.append({
                    "ticker": symbol,
                    "type": "STRONG_AVOID",
                    "level": "CRITICAL",
                    "message": f"🛑 {symbol} issued a STRONG AVOID signal (SMI: {smi_val:.0f}/100) — high capital risk"
                })
            
            for d in divs:
                d_level = (
                    "CRITICAL" if "BEARISH_CONFIRMATION" in d.type
                    else "HIGH" if ("CONFIRMATION" in d.type or "DIVERGENCE" in d.type)
                    else "MEDIUM"
                )
                alerts.append({
                    "ticker": symbol,
                    "type": d.type,
                    "level": d_level,
                    "message": f"⚠️ {symbol}: {d.description}"
                })

            if is_stale and age_hours is not None:
                alerts.append({
                    "ticker": symbol,
                    "type": "STALE_DATA",
                    "level": "WARNING",
                    "message": f"⏳ {symbol} data is {age_hours:.1f}h old (Pipeline awaiting scheduled execution)"
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
                "base_signal": "N/A",
                "signal_modifier": None,
                "divergence": "NONE",
                "confidence": 0.0,
                "data_quality": 0.0,
                "data_completeness": 0.0,
                "price": None,
                "market_status": "DATA_UNAVAILABLE",
                "timestamp": None,
                "data_age_hours": None,
                "is_stale": False
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
