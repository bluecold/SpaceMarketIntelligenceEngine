"""
SEC EDGAR dilution monitor (phases 1 and 2): form classification, submissions parsing, the SEC OFFERING
modifier and gate (an OFFERING caps BUY at WATCH since 2.2.5), FILING alerts that only resolve after a successful fetch, and freshness.
No network: the EDGAR client runs on httpx.MockTransport.
"""
import asyncio
from datetime import datetime, timedelta

import httpx
import pytest

from app.collectors import sec_edgar_provider as sec_mod
from app.collectors.base import SecFilingData
from app.collectors.sec_edgar_provider import EdgarSecProvider, parse_submissions
from app.collectors.sec_forms import (
    DEBT_FINANCING, OFFERING, RESALE, SHELF, UNREGISTERED_SALE, classify_filing
)
from app.config import settings
from app.database.connection import SessionLocal
from app.database.models import AlertModel, SecFilingModel, SourceCheckModel
from app.database.repository import (
    get_recent_sec_filings, record_source_check, save_alerts, save_sec_filings, utc_now
)
from app.monitoring.freshness import check_sec
from app.scoring.signal import generate_signal_and_explanation

NOW = datetime(2026, 11, 25, 15, 0, 0)


# --- Classification -----------------------------------------------------------------------------------

@pytest.mark.parametrize("form,items,expected", [
    ("424B5", None, OFFERING),
    ("424B4", None, OFFERING),
    ("424B3", None, RESALE),
    ("424B7", None, RESALE),
    ("S-3", None, SHELF),
    ("S-3ASR", None, SHELF),
    ("S-1/A", None, SHELF),
    # Convertible notes: 1.01 + 2.03 + 3.02 -> the equity side is what dilutes
    ("8-K", "1.01,2.03,3.02,9.01", UNREGISTERED_SALE),
    ("8-K", "1.01,2.03,9.01", DEBT_FINANCING),
    ("8-K/A", "3.02", UNREGISTERED_SALE),
    # A customer contract (1.01 alone) or results (2.02) are not financing
    ("8-K", "1.01,9.01", None),
    ("8-K", "2.02,9.01", None),
    ("10-Q", None, None),
    ("4", None, None),
    ("", None, None),
])
def test_classify_filing(form, items, expected):
    assert classify_filing(form, items) == expected


# --- Submissions parsing ------------------------------------------------------------------------------

def _payload():
    recent = {
        "accessionNumber": ["0001-26-000005", "0001-26-000004", "0001-26-000003", "0001-26-000002", "0001-25-000001"],
        "filingDate": ["2026-11-20", "2026-11-18", "2026-11-10", "2026-11-01", "2025-06-01"],
        "acceptanceDateTime": ["2026-11-20T21:05:12.000Z", "2026-11-18T12:00:00.000Z", "", "2026-11-01T10:00:00.000Z", "2025-06-01T10:00:00.000Z"],
        "form": ["424B5", "8-K", "10-Q", "S-3", "424B5"],
        "items": ["", "1.01,2.03,3.02", "", "", ""],
        "primaryDocument": ["d424b5.htm", "d8k.htm", "d10q.htm", "ds3.htm", "old.htm"],
        "primaryDocDescription": ["424B5", "8-K", "10-Q", "S-3", "424B5"],
    }
    return {"cik": "1780312", "filings": {"recent": recent}}


def test_parse_submissions_keeps_tracked_forms_inside_history():
    out = parse_submissions(_payload(), "ASTS", "0001780312", history_days=400, today=NOW)
    # 10-Q dropped (untracked), the 2025 offering dropped (older than 400 days)
    assert [(f.form, f.category) for f in out] == [("424B5", OFFERING), ("8-K", UNREGISTERED_SALE), ("S-3", SHELF)]
    first = out[0]
    assert first.accepted_at == datetime(2026, 11, 20, 21, 5, 12)
    assert first.url == "https://www.sec.gov/Archives/edgar/data/1780312/000126000005/d424b5.htm"
    assert first.source == "LIVE"


# --- EDGAR client (no network) ------------------------------------------------------------------------

def _install_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(sec_mod.httpx, "AsyncClient",
                        lambda *a, **kw: real_client(*a, transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(EdgarSecProvider, "_cik_map", {})
    monkeypatch.setattr(EdgarSecProvider, "_cik_map_loaded_at", 0.0)


def test_provider_is_disabled_without_user_agent(monkeypatch):
    def handler(request):  # pragma: no cover - must not be called
        raise AssertionError("no request may be sent without a declared User-Agent")
    _install_transport(monkeypatch, handler)
    res = asyncio.run(EdgarSecProvider(user_agent="").fetch_filings("ASTS"))
    assert res.status == "DISABLED"


def test_provider_resolves_cik_and_declares_user_agent(monkeypatch):
    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers.get("User-Agent")))
        if request.url.path.endswith("company_tickers.json"):
            return httpx.Response(200, json={"0": {"cik_str": 1780312, "ticker": "ASTS", "title": "AST SpaceMobile"}})
        if request.url.path.endswith("CIK0001780312.json"):
            return httpx.Response(200, json=_payload())
        return httpx.Response(404)

    _install_transport(monkeypatch, handler)
    prov = EdgarSecProvider(user_agent="SMIE test contact@example.com")
    res = asyncio.run(prov.fetch_filings("ASTS"))
    assert res.status == "OK" and res.cik == "0001780312"
    assert all(ua == "SMIE test contact@example.com" for _, ua in seen)
    # Unknown symbol: not an error, just no SEC registrant
    assert asyncio.run(prov.fetch_filings("NOPE")).status == "NOT_APPLICABLE"


def test_provider_raises_on_http_error(monkeypatch):
    _install_transport(monkeypatch, lambda request: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(EdgarSecProvider(user_agent="SMIE test contact@example.com").fetch_filings("ASTS", cik="1780312"))


# --- Signal: informational modifier and alerts --------------------------------------------------------

def _signal(filings, smi=60.0):
    return generate_signal_and_explanation(
        ticker="ASTS", smi=smi, indicators={"price": 10.0, "status": "AVAILABLE"}, recent_filings=filings
    )


def _filing(category, form, items=None, days_ago=1.0):
    return {"category": category, "form": form, "items": items, "accepted_at": NOW - timedelta(days=days_ago)}


def test_offering_adds_modifier_and_alert_without_changing_the_band():
    base = _signal([])
    res = _signal([_filing(OFFERING, "424B5")])
    assert res["base_signal"] == base["base_signal"] == "WATCH"
    assert "SEC OFFERING" in res["signal_modifier"]
    alert = next(a for a in res["alerts"] if a["id"] == "ASTS:FILING:SEC_OFFERING")
    assert alert["category"] == "FILING" and alert["level"] == "HIGH" and "424B5" in alert["message"]
    assert any("SEC offering prospectus" in r for r in res["reasons"])


def test_unregistered_sale_stays_informational():
    """8-K 3.02 showed no measurable effect in the event study: modifier and alert only, the BUY stays."""
    res = _signal([_filing(UNREGISTERED_SALE, "8-K", "1.01,2.03,3.02")], smi=75.0)
    assert res["base_signal"] == "BUY"
    assert "SEC OFFERING" in res["signal_modifier"]
    assert "unchanged" in next(a for a in res["alerts"] if a["id"] == "ASTS:FILING:SEC_OFFERING")["message"]


def test_offering_caps_buy_and_strong_buy_at_watch():
    """Phase 2 (2.2.5): an offering prospectus inside the alert window gates bullish bands."""
    for smi in (75.0, 90.0):
        res = _signal([_filing(OFFERING, "424B5")], smi=smi)
        assert res["base_signal"] == "WATCH", smi
        assert res["signal_modifier"].count("SEC OFFERING") == 1
    res = _signal([_filing(OFFERING, "424B5")], smi=75.0)
    assert "capped at WATCH" in next(a for a in res["alerts"] if a["id"] == "ASTS:FILING:SEC_OFFERING")["message"]
    assert any("BUY capped at WATCH" in r for r in res["reasons"])
    assert _signal([_filing(OFFERING, "424B5")], smi=40.0)["base_signal"] == "CAUTION"  # never raises a band


def test_offering_gate_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "SEC_OFFERING_GATE_ENABLED", False)
    res = _signal([_filing(OFFERING, "424B5")], smi=75.0)
    assert res["base_signal"] == "BUY" and "SEC OFFERING" in res["signal_modifier"]


def test_shelf_and_debt_alert_without_modifier():
    res = _signal([_filing(SHELF, "S-3"), _filing(DEBT_FINANCING, "8-K", "1.01,2.03")])
    assert "SEC OFFERING" not in (res["signal_modifier"] or "")
    ids = {a["id"]: a["level"] for a in res["alerts"]}
    assert ids["ASTS:FILING:SEC_SHELF"] == "INFO"
    assert ids["ASTS:FILING:SEC_DEBT"] == "WARNING"


def test_no_filings_leaves_signal_untouched():
    res = _signal([])
    assert not any(a["category"] == "FILING" for a in res["alerts"])
    assert "SEC" not in (res["signal_modifier"] or "")


# --- Persistence --------------------------------------------------------------------------------------

def _data(accession, category, form, accepted, source="LIVE", ticker="TSEC"):
    return SecFilingData(ticker=ticker, cik="0000000001", accession_number=accession, form=form, category=category,
                         filed_date=accepted.date().isoformat(), accepted_at=accepted, source=source)


def test_save_is_idempotent_and_window_excludes_old_and_mock():
    db = SessionLocal()
    try:
        now = utc_now()
        rows = [
            _data("t-1", OFFERING, "424B5", now - timedelta(days=1)),
            _data("t-2", SHELF, "S-3", now - timedelta(days=30)),
            _data("t-3", OFFERING, "424B5", now - timedelta(hours=5), source="MOCK"),
        ]
        assert save_sec_filings(db, rows) == 3
        assert save_sec_filings(db, rows) == 0
        recent = get_recent_sec_filings(db, "TSEC", days=5)
        assert [r.accession_number for r in recent] == ["t-1"]
        assert {r.accession_number for r in get_recent_sec_filings(db, "TSEC", days=5, include_mock=True)} == {"t-1", "t-3"}
    finally:
        db.query(SecFilingModel).filter(SecFilingModel.ticker == "TSEC").delete()
        db.commit()
        db.close()


def test_filing_alert_stays_open_while_edgar_is_failing():
    db = SessionLocal()
    try:
        alert = {"id": "SATL:FILING:SEC_OFFERING", "type": "SEC_OFFERING", "category": "FILING", "level": "HIGH",
                 "message": "test"}
        save_alerts(db, "SATL", [alert], resolve_categories={"FILING"})
        # EDGAR down: FILING not in the resolvable set -> the open alert survives a run that did not see it
        save_alerts(db, "SATL", [], resolve_categories={"SIGNAL"})
        row = db.query(AlertModel).filter(AlertModel.alert_id == "SATL:FILING:SEC_OFFERING").first()
        assert row.resolved_at is None
        # EDGAR back and the filing out of its window -> resolved
        save_alerts(db, "SATL", [], resolve_categories={"FILING"})
        db.refresh(row)
        assert row.resolved_at is not None
    finally:
        db.query(AlertModel).filter(AlertModel.alert_id == "SATL:FILING:SEC_OFFERING").delete()
        db.commit()
        db.close()


# --- Freshness ----------------------------------------------------------------------------------------

def test_freshness_tracks_the_last_successful_fetch(monkeypatch):
    monkeypatch.setattr(settings, "SEC_PROVIDER", "edgar")
    monkeypatch.setattr(settings, "SEC_EDGAR_ENABLED", True)
    db = SessionLocal()
    try:
        monkeypatch.setattr(settings, "SEC_USER_AGENT", "")
        assert check_sec(db, "TSEC", utc_now())["status"] == "disabled"

        monkeypatch.setattr(settings, "SEC_USER_AGENT", "SMIE test contact@example.com")
        assert check_sec(db, "TSEC", utc_now())["status"] == "no_data"

        record_source_check(db, "sec_edgar", "TSEC", "OK")
        assert check_sec(db, "TSEC", utc_now())["status"] == "ok"

        record_source_check(db, "sec_edgar", "TSEC", "ERROR", detail="HTTP 503")
        later = utc_now() + timedelta(hours=settings.SEC_STALE_HOURS + 1)
        stale = check_sec(db, "TSEC", later)
        assert stale["status"] == "stale" and "HTTP 503" in stale["detail"]

        record_source_check(db, "sec_edgar", "TSEC", "NOT_APPLICABLE", detail="no SEC registrant for TSEC")
        assert check_sec(db, "TSEC", later)["status"] == "not_applicable"
    finally:
        db.query(SourceCheckModel).filter(SourceCheckModel.ticker == "TSEC").delete()
        db.commit()
        db.close()
