"""Source health: fetch errors, classified so the operator knows what to do.

freshness.py catches a source that answers but brings nothing new, and only after hours (X: 12h). A source that
fails outright is a different problem and often a permanent one: rejected cookies or a site change that broke the
client library do not heal by themselves, and while they last the pillar silently drops out of the SMI (X carries
35% of it). Between 10/11 and 26/11/2026 the X collector failed on every run and the only signal was a WARNING
freshness alert that blamed expired cookies, while the real cause was a twikit/X incompatibility.

The pipeline records every fetch in `source_checks` (record_source_check with an error kind). This module reads
those rows (DB only, no network) and returns one problem per (source, kind) with the affected tickers, how long it
has been failing, and the action that fixes it. The runner turns it into a per-ticker SYSTEM:SOURCE_ERROR alert,
/api/health serves it under `source_errors`, the dashboard shows it as a banner, and `run-all` prints it.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings, x_collection_off
from app.database.models import SourceCheckModel

AUTH, INCOMPATIBLE, RATE_LIMITED, NETWORK, ERROR = "AUTH", "INCOMPATIBLE", "RATE_LIMITED", "NETWORK", "ERROR"
PERMANENT_KINDS = {AUTH, INCOMPATIBLE}
KIND_RANK = {AUTH: 0, INCOMPATIBLE: 1, RATE_LIMITED: 2, NETWORK: 3, ERROR: 4}

# Sources the pipeline records (source_checks.source) and their display names
SOURCE_LABELS = {"x": "X / Twitter", "news": "Google News RSS", "market": "yfinance (price)",
                 "polymarket": "Polymarket", "sec_edgar": "SEC EDGAR"}
GLOBAL_TICKER = "ALL"  # source_checks.ticker for sector-wide fetches (Polymarket)

ACTIONS = {
    ("x", AUTH): "Log in to x.com in a browser, copy the auth_token and ct0 cookies into X_AUTH_TOKEN and X_CT0 "
                 "in .env, delete data/x_cookies.json if it exists, and run the pipeline again.",
    ("x", INCOMPATIBLE): "The X session works, but the search request fails. Either X changed its web client "
                         "(update twikit with pip install -U twikit when a fix is released) or the account has "
                         "search restricted, which a library update will not fix. Until then the social pillar is "
                         "left out of the SMI; set X_PROVIDER=off to switch X off on purpose.",
    ("x", RATE_LIMITED): "X is rate-limiting the account: run the pipeline less often or lower X_SEARCH_MAX_PAGES.",
    ("sec_edgar", AUTH): "EDGAR rejected the request: set SEC_USER_AGENT to 'Name email@domain' in .env.",
    ("sec_edgar", RATE_LIMITED): "EDGAR is throttling requests (10/s limit): wait and run again.",
}
DEFAULT_ACTIONS = {
    AUTH: "The source rejected the credentials: renew them in .env and run again.",
    INCOMPATIBLE: "The source changed its format or protocol: the collector or its library needs an update.",
    RATE_LIMITED: "The source is rate-limiting requests: run less often and try again later.",
    NETWORK: "The source could not be reached: check the internet connection, VPN or firewall.",
    ERROR: "The fetch failed: see the server log for the full error.",
}

_AUTH_MARKERS = ("401", "403", "unauthor", "forbidden", "invalid session", "invalidsession", "cookie",
                 "login", "logged-out", "credential", "api key", "token expired", "accountlocked",
                 "accountsuspended", "user-agent", "user agent")
_RATE_MARKERS = ("429", "too many requests", "rate limit", "ratelimit", "toomanyrequests", "throttl")
_NETWORK_MARKERS = ("timed out", "timeout", "connecterror", "connection", "name resolution", "getaddrinfo",
                    "temporary failure", "network is unreachable", "ssl", "remote end closed", "readerror",
                    "max retries", "proxy")


def classify_source_error(exc: BaseException) -> str:
    """Error kind of a collector exception. Typed SourceError subclasses win; otherwise the class name and the
    message decide, so library errors (twikit, httpx, requests, yfinance) map without importing them."""
    kind = getattr(exc, "kind", None)
    if kind in KIND_RANK:
        return kind
    text = f"{type(exc).__name__} {exc}".lower()
    if any(m in text for m in _RATE_MARKERS):
        return RATE_LIMITED
    if any(m in text for m in _AUTH_MARKERS):
        return AUTH
    if isinstance(exc, (TimeoutError, ConnectionError)) or any(m in text for m in _NETWORK_MARKERS):
        return NETWORK
    return ERROR


def _naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


def _active_sources() -> set:
    """Sources whose current configuration makes a live fetch (a row left from a mock or disabled period is ignored)."""
    active = {"market"}
    if settings.X_PROVIDER.lower() != "mock" and not x_collection_off():
        active.add("x")
    if getattr(settings, "NEWS_PROVIDER", "rss").lower() != "mock":
        active.add("news")
    if getattr(settings, "POLYMARKET_ENABLED", True) and settings.POLYMARKET_PROVIDER.lower() != "mock":
        active.add("polymarket")
    if getattr(settings, "SEC_EDGAR_ENABLED", True) and getattr(settings, "SEC_PROVIDER", "edgar").lower() != "mock":
        active.add("sec_edgar")
    return active


def severity_for(kind: str, failing_hours: float) -> Optional[str]:
    """CRITICAL / WARNING, or None while a transient failure is still too short to be worth an alert."""
    if kind in PERMANENT_KINDS:
        return "CRITICAL"
    if failing_hours >= settings.SOURCE_ERROR_CRITICAL_HOURS:
        return "CRITICAL"
    if failing_hours >= settings.SOURCE_ERROR_WARNING_HOURS:
        return "WARNING"
    return None


def evaluate_source_health(db: Session, now: Optional[datetime] = None) -> Dict[str, Any]:
    """{"status": "ok"|"warning"|"critical", "problems": [...]} with one problem per (source, kind), most severe first.

    A failure streak is measured from its first failed attempt to the latest one, so a manual run once a day
    does not make a one-off network error look like hours of outage."""
    now = _naive_utc(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    active = _active_sources()
    rows = db.query(SourceCheckModel).filter(SourceCheckModel.status == "ERROR").all()

    groups: Dict[tuple, Dict[str, Any]] = {}
    for r in rows:
        if r.source not in active:
            continue
        kind = r.error_kind or ERROR
        since = _naive_utc(r.error_since) or _naive_utc(r.last_attempt_at)
        last = _naive_utc(r.last_attempt_at) or since
        g = groups.setdefault((r.source, kind), {"tickers": [], "since": since, "last_attempt": last,
                                                 "last_success": _naive_utc(r.last_success_at), "detail": r.detail})
        if r.ticker != GLOBAL_TICKER:
            g["tickers"].append(r.ticker)
        if since and (g["since"] is None or since < g["since"]):
            g["since"] = since
        if last and (g["last_attempt"] is None or last > g["last_attempt"]):
            g["last_attempt"], g["detail"] = last, r.detail or g["detail"]
        ls = _naive_utc(r.last_success_at)
        if ls and (g["last_success"] is None or ls > g["last_success"]):
            g["last_success"] = ls

    problems: List[Dict[str, Any]] = []
    for (source, kind), g in groups.items():
        failing_hours = ((g["last_attempt"] - g["since"]).total_seconds() / 3600.0
                         if g["since"] and g["last_attempt"] else 0.0)
        severity = severity_for(kind, failing_hours)
        if severity is None:
            continue
        label = SOURCE_LABELS.get(source, source)
        problems.append({
            "source": source,
            "label": label,
            "kind": kind,
            "severity": severity,
            "tickers": sorted(g["tickers"]),
            "since": _iso(g["since"]),
            "last_attempt": _iso(g["last_attempt"]),
            "last_success": _iso(g["last_success"]),
            "failing_hours": round(failing_hours, 1),
            "detail": (g["detail"] or "")[:300],
            "action": ACTIONS.get((source, kind), DEFAULT_ACTIONS.get(kind, DEFAULT_ACTIONS[ERROR])),
        })
    problems.sort(key=lambda p: (0 if p["severity"] == "CRITICAL" else 1, KIND_RANK.get(p["kind"], 9), p["source"]))
    status = "critical" if any(p["severity"] == "CRITICAL" for p in problems) else ("warning" if problems else "ok")
    return {"status": status, "problems": problems}


KIND_TEXT = {AUTH: "credentials rejected", INCOMPATIBLE: "client no longer compatible", RATE_LIMITED: "rate-limited",
             NETWORK: "unreachable", ERROR: "fetch failing"}


def build_source_error_alert(ticker: str, health: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Per-ticker SYSTEM alert for the sources failing for this ticker (or sector-wide), None when all fetch fine.

    The ID is stable per ticker, so the episode stays open while the problem lasts and resolves on the first run
    where every fetch succeeds; the dashboard banner (fed by /api/health) shows the problem once for all tickers."""
    tk = ticker.upper()
    mine = [p for p in health.get("problems", []) if not p["tickers"] or tk in p["tickers"]]
    if not mine:
        return None
    level = "CRITICAL" if any(p["severity"] == "CRITICAL" for p in mine) else "WARNING"
    since_txt = lambda p: f" since {p['since'][:16].replace('T', ' ')} UTC" if p.get("since") else ""
    parts = [f"{p['label']}: {KIND_TEXT.get(p['kind'], p['kind'])}{since_txt(p)}. {p['action']}" for p in mine]
    return {
        "id": f"{tk}:SYSTEM:SOURCE_ERROR",
        "type": "SOURCE_ERROR",
        "category": "SYSTEM",
        "level": level,
        "message": f"⛔ {tk}: data source failing. " + " | ".join(parts),
    }
