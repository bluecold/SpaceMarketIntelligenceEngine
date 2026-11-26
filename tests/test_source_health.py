"""Source health (app/monitoring/source_health.py): classified fetch errors, alerts and the twikit diagnosis."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.collectors.base import SourceAuthError, SourceIncompatibleError
from app.config import settings
from app.database.models import AlertModel, Base, SourceCheckModel, TickerModel
from app.database import repository
from app.monitoring import source_health as sh

T0 = datetime(2026, 11, 25, 15, 0)


@pytest.fixture
def db():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    session = sessionmaker(bind=eng)()
    yield session
    session.close()
    eng.dispose()


@pytest.fixture
def live_providers(monkeypatch):
    monkeypatch.setattr(settings, "X_PROVIDER", "twikit")
    monkeypatch.setattr(settings, "NEWS_PROVIDER", "rss")
    monkeypatch.setattr(settings, "POLYMARKET_PROVIDER", "polymarket")
    monkeypatch.setattr(settings, "POLYMARKET_ENABLED", True)


@pytest.fixture
def clock(monkeypatch):
    """record_source_check stamps utc_now(); drive it explicitly."""
    state = {"now": T0}
    monkeypatch.setattr(repository, "utc_now", lambda: state["now"])
    return state


def _named_exc(name, msg=""):
    return type(name, (Exception,), {})(msg)


# --- Classification ---------------------------------------------------------------------------------

@pytest.mark.parametrize("exc, kind", [
    (SourceAuthError("x"), sh.AUTH),
    (SourceIncompatibleError("x"), sh.INCOMPATIBLE),
    (_named_exc("TooManyRequests", "status: 429"), sh.RATE_LIMITED),
    (_named_exc("Unauthorized", "status: 401"), sh.AUTH),
    (_named_exc("HTTPError", "403 Forbidden for url"), sh.AUTH),
    (_named_exc("ConnectError", "[Errno 11001] getaddrinfo failed"), sh.NETWORK),
    (TimeoutError("read timed out"), sh.NETWORK),
    (ValueError("unexpected payload"), sh.ERROR),
])
def test_classify_source_error(exc, kind):
    assert sh.classify_source_error(exc) == kind


def test_twikit_invalid_session_tells_cookies_from_broken_client(monkeypatch):
    """X answers both cases with the same InvalidSession; only the handshake shows whether the login was accepted."""
    from app.collectors import twikit_provider as tp
    err = _named_exc("InvalidSession", "x.com returned the logged-out page shell")
    monkeypatch.setitem(tp._handshake_state, "logged_in", True)
    assert isinstance(tp.classify_twikit_error(err), SourceIncompatibleError)
    monkeypatch.setitem(tp._handshake_state, "logged_in", False)
    assert isinstance(tp.classify_twikit_error(err), SourceAuthError)
    assert isinstance(tp.classify_twikit_error(_named_exc("AccountLocked")), SourceAuthError)
    assert tp.classify_twikit_error(_named_exc("NotFound")) is None


def test_handshake_follows_same_site_redirect_only():
    import asyncio
    asyncio.run(_handshake_redirect_case())


async def _handshake_redirect_case():
    """x.com answers a logged-in GET / with 307 -> /home and an empty body; twikit 2.3.3 did not follow it."""
    from app.collectors import twikit_provider as tp
    calls = []

    class FakeCookies(dict):
        pass

    def resp(status, location=None, cookies=()):
        return SimpleNamespace(status_code=status, headers={"location": location} if location else {},
                               cookies=FakeCookies({c: "1" for c in cookies}))

    responses = {"https://x.com": resp(307, "/home", cookies=("twid",)), "https://x.com/home": resp(200),
                 "https://evil.example": resp(302, "https://elsewhere.example/")}

    class Inner:
        async def request(self, method="GET", url="", **kw):
            calls.append(url)
            return responses[url]

    tp._handshake_state["logged_in"] = False
    out = await tp._RedirectFollowingSession(Inner()).request(method="GET", url="https://x.com")
    assert out.status_code == 200 and calls == ["https://x.com", "https://x.com/home"]
    assert tp._handshake_state["logged_in"] is True

    calls.clear()
    out = await tp._RedirectFollowingSession(Inner()).request(method="GET", url="https://evil.example")
    assert out.status_code == 302 and calls == ["https://evil.example"]


# --- Recording and evaluation -----------------------------------------------------------------------

def test_record_source_check_tracks_failure_streak(db, clock):
    repository.record_source_check(db, "x", "ASTS", "ERROR", detail="boom", error_kind="AUTH")
    clock["now"] = T0 + timedelta(hours=2)
    repository.record_source_check(db, "x", "ASTS", "ERROR", detail="boom again", error_kind="AUTH")
    row = db.query(SourceCheckModel).one()
    assert row.error_since == T0 and row.error_kind == "AUTH" and row.last_success_at is None

    clock["now"] = T0 + timedelta(hours=3)
    repository.record_source_check(db, "x", "ASTS", "OK")
    db.refresh(row)
    assert row.error_kind is None and row.error_since is None and row.last_success_at == T0 + timedelta(hours=3)


def test_auth_failure_is_critical_on_first_attempt_and_grouped(db, clock, live_providers):
    for tk in ("ASTS", "RKLB"):
        repository.record_source_check(db, "x", tk, "ERROR", detail="cookies", error_kind="AUTH")
    health = sh.evaluate_source_health(db, now=T0)
    assert health["status"] == "critical"
    [p] = health["problems"]
    assert p["source"] == "x" and p["kind"] == "AUTH" and p["severity"] == "CRITICAL"
    assert p["tickers"] == ["ASTS", "RKLB"]
    assert "X_AUTH_TOKEN" in p["action"]


def test_incompatible_client_says_cookies_are_fine(db, clock, live_providers):
    repository.record_source_check(db, "x", "SPCX", "ERROR", error_kind="INCOMPATIBLE")
    [p] = sh.evaluate_source_health(db, now=T0)["problems"]
    assert p["severity"] == "CRITICAL" and "cookies are fine" in p["action"].lower()


def test_transient_errors_escalate_with_streak_length(db, clock, live_providers):
    repository.record_source_check(db, "news", "ASTS", "ERROR", error_kind="NETWORK")
    assert sh.evaluate_source_health(db)["problems"] == []          # a single blip is not an alert
    clock["now"] = T0 + timedelta(hours=settings.SOURCE_ERROR_WARNING_HOURS)
    repository.record_source_check(db, "news", "ASTS", "ERROR", error_kind="NETWORK")
    assert sh.evaluate_source_health(db)["problems"][0]["severity"] == "WARNING"
    clock["now"] = T0 + timedelta(hours=settings.SOURCE_ERROR_CRITICAL_HOURS)
    repository.record_source_check(db, "news", "ASTS", "ERROR", error_kind="NETWORK")
    assert sh.evaluate_source_health(db)["problems"][0]["severity"] == "CRITICAL"


def test_mock_sources_and_successes_are_ignored(db, clock, monkeypatch):
    monkeypatch.setattr(settings, "X_PROVIDER", "mock")
    repository.record_source_check(db, "x", "ASTS", "ERROR", error_kind="AUTH")
    repository.record_source_check(db, "market", "ASTS", "OK")
    assert sh.evaluate_source_health(db) == {"status": "ok", "problems": []}


def test_global_source_applies_to_every_ticker(db, clock, live_providers):
    repository.record_source_check(db, "polymarket", sh.GLOBAL_TICKER, "ERROR", error_kind="AUTH")
    health = sh.evaluate_source_health(db)
    assert health["problems"][0]["tickers"] == []
    assert sh.build_source_error_alert("SATL", health) is not None


def test_alert_opens_and_resolves_through_save_alerts(db, clock, live_providers):
    db.add(TickerModel(symbol="ASTS", name="AST SpaceMobile"))
    db.commit()
    repository.record_source_check(db, "x", "ASTS", "ERROR", error_kind="INCOMPATIBLE")
    alert = sh.build_source_error_alert("ASTS", sh.evaluate_source_health(db))
    assert alert["id"] == "ASTS:SYSTEM:SOURCE_ERROR" and alert["level"] == "CRITICAL"
    assert sh.build_source_error_alert("RKLB", sh.evaluate_source_health(db)) is None
    repository.save_alerts(db, "ASTS", [alert], resolve_categories={"SYSTEM"})
    row = db.query(AlertModel).filter(AlertModel.alert_id == "ASTS:SYSTEM:SOURCE_ERROR").one()
    assert row.resolved_at is None

    repository.record_source_check(db, "x", "ASTS", "OK")
    assert sh.build_source_error_alert("ASTS", sh.evaluate_source_health(db)) is None
    repository.save_alerts(db, "ASTS", [], resolve_categories={"SYSTEM"})
    db.refresh(row)
    assert row.resolved_at is not None


def test_health_endpoint_exposes_source_errors():
    from fastapi.testclient import TestClient
    from app.main import app

    body = TestClient(app).get("/api/health").json()
    assert body["source_errors"]["status"] in ("ok", "warning", "critical", "error")
    if body["source_errors"]["status"] in ("warning", "critical"):
        assert body["status"] == "degraded"
