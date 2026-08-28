from typing import List, Dict, Any
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database.connection import get_db
from app.database.repository import (
    get_latest_ssi_snapshots_batch,
    get_latest_market_snapshots_batch,
    get_active_divergences_batch,
    get_active_alerts_batch,
    utc_now
)
from app.config import INITIAL_TICKERS

router = APIRouter(tags=["Dashboard"])


@router.get("/api/dashboard")
def get_dashboard(db: Session = Depends(get_db)) -> Dict[str, Any]:
    rankings = []
    alerts = []
    
    ticker_symbols = [t.symbol for t in INITIAL_TICKERS]
    now_dt = utc_now()
    
    # 4 Consolidated Batch Queries (eliminates N+1 DB queries)
    ssi_snaps = get_latest_ssi_snapshots_batch(db, tickers=ticker_symbols)
    mkt_snaps = get_latest_market_snapshots_batch(db, tickers=ticker_symbols)
    divs_by_ticker = get_active_divergences_batch(db, hours=24, tickers=ticker_symbols)
    db_alerts = get_active_alerts_batch(db, tickers=ticker_symbols)
    
    for ticker_config in INITIAL_TICKERS:
        symbol = ticker_config.symbol
        ssi_snap = ssi_snaps.get(symbol)
        mkt_snap = mkt_snaps.get(symbol)
        divs = divs_by_ticker.get(symbol, [])

        if ssi_snap:
            # Stale Data Calculation
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
                "post_count": ssi_snap.post_count,
                "news_count": ssi_snap.news_count,
                "prediction_count": ssi_snap.prediction_count,
                "data_source": getattr(ssi_snap, "data_source", "LIVE") or "LIVE",
                "social_source": getattr(ssi_snap, "social_source", "LIVE") or "LIVE",
                "prediction_source": getattr(ssi_snap, "prediction_source", "LIVE") or "LIVE",
                "news_source": getattr(ssi_snap, "news_source", "LIVE") or "LIVE",
                "market_source": getattr(ssi_snap, "market_source", "LIVE") or "LIVE",
                "price": ssi_snap.price,
                "market_status": mkt_snap.market_status if mkt_snap else "AVAILABLE",
                "timestamp": ssi_snap.timestamp.isoformat() + "Z" if ssi_snap.timestamp else None,
                "data_age_hours": age_hours,
                "is_stale": is_stale
            })

            # If no database alerts exist yet, provide fallback alerts from snapshot
            if not db_alerts:
                snap_iso = ssi_snap.timestamp.isoformat() + "Z" if ssi_snap.timestamp else None

                if ssi_snap.signal and "STRONG BUY" in ssi_snap.signal:
                    alerts.append({
                        "id": f"{symbol}:SIGNAL:STRONG_BUY",
                        "ticker": symbol,
                        "type": "STRONG_BUY",
                        "category": "SIGNAL",
                        "level": "CRITICAL",
                        "message": f"🚀 {symbol} issued a STRONG BUY signal (SMI: {smi_val:.0f}/100)",
                        "timestamp": snap_iso,
                        "age_hours": age_hours,
                        "is_active": not is_stale
                    })
                elif ssi_snap.signal and "STRONG AVOID" in ssi_snap.signal:
                    alerts.append({
                        "id": f"{symbol}:SIGNAL:STRONG_AVOID",
                        "ticker": symbol,
                        "type": "STRONG_AVOID",
                        "category": "SIGNAL",
                        "level": "CRITICAL",
                        "message": f"🛑 {symbol} issued a STRONG AVOID signal (SMI: {smi_val:.0f}/100) — high capital risk",
                        "timestamp": snap_iso,
                        "age_hours": age_hours,
                        "is_active": not is_stale
                    })
                
                for d in divs:
                    d_level = (
                        "CRITICAL" if "BEARISH_CONFIRMATION" in d.type
                        else "HIGH" if ("CONFIRMATION" in d.type or "DIVERGENCE" in d.type)
                        else "MEDIUM"
                    )
                    div_dt = d.timestamp
                    if div_dt and div_dt.tzinfo is not None:
                        div_dt = div_dt.replace(tzinfo=None)
                    div_age = round(max(0.0, (now_dt - div_dt).total_seconds() / 3600.0), 1) if div_dt else age_hours
                    div_iso = d.timestamp.isoformat() + "Z" if (hasattr(d, "timestamp") and d.timestamp) else snap_iso

                    alerts.append({
                        "id": f"{symbol}:DIVERGENCE:{d.type}:{d.id if hasattr(d, 'id') else '0'}",
                        "ticker": symbol,
                        "type": d.type,
                        "category": "DIVERGENCE",
                        "level": d_level,
                        "message": f"⚠️ {symbol}: {d.description}",
                        "timestamp": div_iso,
                        "age_hours": div_age,
                        "is_active": not is_stale
                    })

            # Add stale data warning if applicable
            if is_stale and age_hours is not None:
                alerts.append({
                    "id": f"{symbol}:SYSTEM:STALE_DATA",
                    "ticker": symbol,
                    "type": "STALE_DATA",
                    "category": "SYSTEM",
                    "level": "WARNING",
                    "message": f"⏳ {symbol} data is {age_hours:.1f}h old (Pipeline awaiting scheduled execution)",
                    "timestamp": ssi_snap.timestamp.isoformat() + "Z" if ssi_snap.timestamp else None,
                    "age_hours": age_hours,
                    "is_active": False
                })
        else:
            rankings.append({
                "ticker": symbol,
                "name": ticker_config.name,
                "smi": None,
                "ssi": None,
                "pms": None,
                "delta_1d": None,
                "social_score": None,
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
                "post_count": 0,
                "news_count": 0,
                "prediction_count": 0,
                "price": None,
                "market_status": "DATA_UNAVAILABLE",
                "timestamp": None,
                "data_age_hours": None,
                "is_stale": False
            })

    # If database alerts exist, format them directly as the authoritative source
    if db_alerts:
        for al in db_alerts:
            al_ts = al.timestamp
            if al_ts and al_ts.tzinfo is not None:
                al_ts = al_ts.replace(tzinfo=None)
            al_age = round(max(0.0, (now_dt - al_ts).total_seconds() / 3600.0), 1) if al_ts else None
            
            snap = ssi_snaps.get(al.ticker)
            is_snap_stale = False
            if snap and snap.timestamp:
                st = snap.timestamp.replace(tzinfo=None) if snap.timestamp.tzinfo else snap.timestamp
                is_snap_stale = (now_dt - st).total_seconds() / 3600.0 >= 6.0

            alerts.append({
                "id": al.alert_id,
                "ticker": al.ticker,
                "type": al.type,
                "category": al.category,
                "level": al.level,
                "message": al.message,
                "timestamp": al.timestamp.isoformat() + "Z" if al.timestamp else None,
                "age_hours": al_age,
                "is_active": not is_snap_stale
            })

    # Sort rankings by SMI descending, safely placing None values at the bottom
    rankings.sort(
        key=lambda x: (x["smi"] is not None, x["smi"] if x["smi"] is not None else -1.0),
        reverse=True
    )

    return {
        "title": "SPACE MARKET INTELLIGENCE ENGINE",
        "last_update": rankings[0]["timestamp"] if rankings and rankings[0]["timestamp"] else None,
        "count": len(rankings),
        "rankings": rankings,
        "alerts": alerts
    }
