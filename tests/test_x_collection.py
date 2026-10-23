"""
v2.2.2 collection fixes: X search paging (one twikit request returns at most 20 tweets, which covered only
1-20 minutes of traffic for ASTS/RKLB/SPCX), coverage-aware mention volume, price-recap headlines and the
not-applicable Polymarket pillar.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.config import INITIAL_TICKERS, settings
from app.collectors.twikit_provider import TwikitProvider
from app.database.models import SocialPostModel
from app.jobs.runner import build_x_query
from app.scoring.smi import calculate_smi
from app.scoring.social import apply_social_baseline, calculate_social_baseline, calculate_social_score
from app.sentiment.weighting import calculate_news_score, is_price_recap_headline

NOW_UTC = datetime(2026, 10, 30, 12, 0, 0, tzinfo=timezone.utc)


def _tweet(i, minutes_ago):
    created = (NOW_UTC - timedelta(minutes=minutes_ago)).strftime('%a %b %d %H:%M:%S %z %Y')
    return SimpleNamespace(id=i, created_at=created, text=f"tweet {i} $ASTS", user=SimpleNamespace(name=f"u{i}"),
                           lang="en", favorite_count=0, retweet_count=0, reply_count=0, view_count=0)


class _Page(list):
    """Mimics twikit's Result: iterable page with an async next()."""
    def __init__(self, pages, idx, client):
        super().__init__(pages[idx] if idx < len(pages) else [])
        self._pages, self._idx, self._client = pages, idx, client

    async def next(self):
        self._client.calls += 1
        if self._client.fail_on_call == self._client.calls:
            raise RuntimeError("Rate limit exceeded")
        return _Page(self._pages, self._idx + 1, self._client)


class _FakeClient:
    def __init__(self, pages, fail_on_call=None):
        self.pages, self.calls, self.fail_on_call, self.queries = pages, 0, fail_on_call, []

    async def search_tweet(self, query, product, count=20, cursor=None):
        self.calls += 1
        self.queries.append(query)
        return _Page(self.pages, 0, self)


def _provider(client, monkeypatch, max_pages=10):
    monkeypatch.setattr(settings, "X_SEARCH_MAX_PAGES", max_pages)
    monkeypatch.setattr(settings, "X_SEARCH_PAGE_DELAY_SECONDS", 0.0)
    prov = TwikitProvider()
    prov.client, prov._authenticated = client, True
    return prov


def _pages(n_pages, per_page=20, minutes_step=1):
    """Newest first, as X 'Latest' returns them: tweet ids descend with age."""
    pages, k = [], 0
    for _ in range(n_pages):
        page = []
        for _ in range(per_page):
            page.append(_tweet(100000 - k, minutes_ago=k * minutes_step))
            k += 1
        pages.append(page)
    return pages


def test_search_pages_until_known_tweet_and_returns_only_new_ones(monkeypatch):
    pages = _pages(5)
    known = {str(100000 - 45)}  # 46th newest tweet was stored by the previous run
    client = _FakeClient(pages)
    posts = asyncio.run(_provider(client, monkeypatch).search("q", "ASTS", known_ids=known))
    assert len(posts) == 59      # every tweet of the 3 pages read except the known one
    assert client.calls == 3     # stops paging after the page holding the known tweet


def test_search_meta_reports_complete_and_cap(monkeypatch):
    prov = _provider(_FakeClient(_pages(5)), monkeypatch)
    asyncio.run(prov.search("q", "ASTS", known_ids={str(100000 - 45)}))
    assert prov.last_search_meta.complete and prov.last_search_meta.stop_reason == "reached_known"

    capped = _provider(_FakeClient(_pages(5)), monkeypatch, max_pages=2)
    posts = asyncio.run(capped.search("q", "ASTS"))
    assert len(posts) == 40
    assert not capped.last_search_meta.complete and capped.last_search_meta.stop_reason == "page_cap"

    exhausted = _provider(_FakeClient(_pages(2)), monkeypatch)
    asyncio.run(exhausted.search("q", "ASTS"))
    assert exhausted.last_search_meta.complete and exhausted.last_search_meta.stop_reason == "exhausted"


def test_search_stops_at_since_and_adds_time_operator(monkeypatch):
    client = _FakeClient(_pages(5, minutes_step=30))  # 20 tweets cover 10h per page
    prov = _provider(client, monkeypatch)
    since = NOW_UTC - timedelta(hours=24)
    posts = asyncio.run(prov.search("q", "ASTS", since=since))
    assert all(p.created_at >= since for p in posts)
    assert len(posts) == 49  # minutes_ago 0..1440 step 30
    assert prov.last_search_meta.stop_reason == "reached_since"
    assert client.queries[0] == f"q since_time:{int(since.timestamp())}"


def test_rate_limit_mid_paging_keeps_partial_posts(monkeypatch):
    prov = _provider(_FakeClient(_pages(5), fail_on_call=3), monkeypatch)
    posts = asyncio.run(prov.search("q", "ASTS"))
    assert len(posts) == 40
    assert not prov.last_search_meta.complete


def test_x_query_uses_language_operator_and_spcx_override(monkeypatch):
    monkeypatch.setattr(settings, "SOCIAL_ALLOWED_LANGUAGES", ["en"])
    by_symbol = {t.symbol: t for t in INITIAL_TICKERS}
    assert build_x_query(by_symbol["ASTS"]) == '($ASTS OR "AST SpaceMobile") lang:en'
    # A bare "SpaceX" filled a 20-tweet page in about a minute
    assert build_x_query(by_symbol["SPCX"]) == '($SPCX OR ("SpaceX" (stock OR shares OR IPO))) lang:en'


NOW = datetime(2026, 11, 1, 12, 0, 0)


def _post(i, created, collected=None):
    return SocialPostModel(tweet_id=f"v{i}", ticker="ASTS", username=f"user_{i}", text=f"volume post {i} $ASTS",
                           created_at=created, collected_at=collected, sentiment_score=0.5, sentiment_label="BULLISH",
                           sentiment_confidence=1.0, relevance_score=1.0, engagement_score=0.0)


def test_mention_rate_ignores_single_page_era_but_keeps_its_polarity(monkeypatch):
    monkeypatch.setattr(settings, "SOCIAL_VOLUME_SINCE", "2026-10-28T00:00:00")
    history = []
    for d in range(2, 9):
        created = NOW - timedelta(days=d)
        for k in range(10):
            history.append(_post(d * 100 + k, created, collected=created))  # collected Oct 24-30
    base = calculate_social_baseline(history, NOW - timedelta(days=14), NOW - timedelta(hours=24))
    assert base["opinion_post_count"] == 70            # polarity still uses every post
    assert base["days_covered"] == 3                   # only Oct 28-30 (collected after the cutoff) feed the mention rate
    assert base["daily_post_rate"] == 10.0


def test_partial_window_has_no_mention_ratio():
    history = [_post(d * 100 + k, NOW - timedelta(hours=30 + 24 * d)) for d in range(5) for k in range(10)]
    base = calculate_social_baseline(history, NOW - timedelta(days=14), NOW - timedelta(hours=24))
    current = calculate_social_score([_post(9000 + i, NOW) for i in range(30)], analysis_timestamp=NOW)
    assert apply_social_baseline(current, base)["mention_volume_ratio"] == pytest.approx(3.0, abs=0.01)
    assert apply_social_baseline(current, base, coverage_complete=False)["mention_volume_ratio"] is None


@pytest.mark.parametrize("title", [
    "Rocket Lab (NASDAQ:RKLB) Stock Falls 4.9% - Here's What Happened - MarketBeat",
    "AST SpaceMobile Inc Stock (ASTS) Moved Down by 14.90% on Oct 9: What Investors Need To Know - TradingKey",
    "Ast Spacemobile stock hits 52-week low at 49.3 USD - Investing.com",
    "Why Is AST SpaceMobile Stock Falling Thursday? - Benzinga",
    "AST SpaceMobile stock Analysis closes at $56.93, down 6.13% - The Cryptonomist",
    "Redwire Falls 5% as Space Stocks Sell Off Together; Rocket Lab Drops 4% - 24/7 Wall St.",
])
def test_price_recap_headlines_detected(title):
    assert is_price_recap_headline(title)


@pytest.mark.parametrize("title", [
    "Rocket Lab Revenue Jumps 40% on Record Launch Cadence - Reuters",
    "SpaceX Stock Could Soar by 73%, According to a Wall Street Analyst - The Motley Fool",
    "TD Cowen Cut Its Rocket Lab Target. It Still Sees 32% Upside - TIKR.com",
    "Rocket Lab Delays Neutron Again - Yahoo Finance",
])
def test_news_with_content_is_not_a_price_recap(title):
    assert not is_price_recap_headline(title)


def test_price_recaps_carry_no_direction_unless_they_name_a_catalyst():
    now = datetime.now(timezone.utc)

    def item(title, score, label, catalyst=None):
        return SimpleNamespace(title=title, sentiment_score=score, sentiment_label=label, sentiment_confidence=0.9,
                               published_at=now, relevance_score=0.85, catalyst=catalyst, catalyst_importance=None)

    recaps = [item(f"Rocket Lab Stock Falls {p}% - Time to Sell? - MarketBeat", -0.9, "BEARISH") for p in (3, 4, 5)]
    res = calculate_news_score(recaps + [item("Rocket Lab wins new launch contract - Reuters", 0.8, "BULLISH")], analysis_timestamp=now)
    assert res["price_recap_news_count"] == 3
    assert res["opinion_news_count"] == 1
    assert res["news_score"] > 50.0

    with_catalyst = item("Rocket Lab Stock Falls 10% After Delaying Neutron to 2027 - Yahoo", -0.9, "BEARISH", catalyst="LAUNCH_DELAY")
    res = calculate_news_score([with_catalyst], analysis_timestamp=now)
    assert res["price_recap_news_count"] == 0
    assert res["news_score"] < 50.0


def test_company_without_polymarket_contracts_is_not_missing_data():
    kw = dict(social_score=60.0, news_score=55.0, momentum_score=50.0, fundamental_score=70.0, post_count=20, news_count=5)
    missing = calculate_smi(**kw)
    not_applicable = calculate_smi(**kw, prediction_applicable=False)
    assert missing["data_quality"] == 80.0
    assert not_applicable["data_quality"] == 100.0
    assert not_applicable["smi"] == missing["smi"]
