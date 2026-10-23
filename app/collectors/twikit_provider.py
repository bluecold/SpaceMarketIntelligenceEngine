import asyncio
import os
import logging
from datetime import datetime, timezone
from typing import List
from app.collectors.base import XProvider, SocialPostData, SocialSearchMeta
from app.collectors.mock_x_provider import MockXProvider
from app.config import settings

logger = logging.getLogger(__name__)


class TwikitProvider(XProvider):
    def __init__(self):
        self.client = None
        self._authenticated = False
        self._fallback_provider = MockXProvider()

    async def _ensure_authenticated(self):
        if self._authenticated and self.client:
            return True

        try:
            from twikit import Client
            self.client = Client('en-US')
            cookies_file = settings.X_COOKIES_FILE

            # 1. Check if direct auth_token is configured in settings
            if getattr(settings, "X_AUTH_TOKEN", ""):
                auth_tok = settings.X_AUTH_TOKEN
                ct0_tok = getattr(settings, "X_CT0", "") or "0"
                self.client.set_cookies({"auth_token": auth_tok, "ct0": ct0_tok})
                logger.info("Configured X session via X_AUTH_TOKEN cookie")
                self._authenticated = True
                return True

            # 2. Check if saved cookies file exists
            if os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0:
                try:
                    self.client.load_cookies(cookies_file)
                    logger.info(f"Loaded existing X cookies from {cookies_file}")
                    self._authenticated = True
                    return True
                except Exception as e:
                    logger.warning(f"Failed to load cookies from {cookies_file}: {e}. Retrying login...")

            # 3. If no valid cookies, perform login with credentials
            if settings.X_AUTH_INFO_1 and settings.X_PASSWORD:
                logger.info(f"Logging in to X via Twikit with user: {settings.X_AUTH_INFO_1}...")
                await self.client.login(
                    auth_info_1=settings.X_AUTH_INFO_1,
                    auth_info_2=settings.X_AUTH_INFO_2,
                    password=settings.X_PASSWORD
                )
                # Ensure directory exists and save cookies
                os.makedirs(os.path.dirname(cookies_file) or ".", exist_ok=True)
                self.client.save_cookies(cookies_file)
                logger.info(f"Login successful. Saved new session cookies to {cookies_file}")
                self._authenticated = True
                return True
            else:
                logger.info("No active X credentials. Using realistic Mock X Provider fallback.")
                return False

        except Exception as e:
            logger.warning(f"Twikit authentication unavailable ({e}). Using mock provider fallback.")
            self._authenticated = False
            return False

    async def search(self, query: str, ticker: str, max_results: int = 100, since=None, known_ids=None) -> List[SocialPostData]:
        """
        Pages through X 'Latest' results (twikit returns at most 20 tweets per request) until it reaches a tweet
        already stored (known_ids), a tweet older than `since`, the end of the results, or X_SEARCH_MAX_PAGES.
        Returns only tweets not in known_ids. self.last_search_meta records whether the window was fully covered.
        """
        is_auth = await self._ensure_authenticated()
        if not is_auth or not self.client:
            if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                return await self._fallback_provider.search(query, ticker, max_results)
            err_msg = f"Twikit unauthenticated for ticker {ticker} (ALLOW_MOCK_FALLBACK=False)."
            logger.warning(err_msg)
            raise RuntimeError(err_msg)

        known_ids = known_ids or set()
        since_utc = None
        if since is not None:
            since_utc = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
            query = f"{query} since_time:{int(since_utc.timestamp())}"
        max_pages = max(1, int(getattr(settings, "X_SEARCH_MAX_PAGES", 10)))
        page_delay = float(getattr(settings, "X_SEARCH_PAGE_DELAY_SECONDS", 1.0))

        posts: List[SocialPostData] = []
        meta = SocialSearchMeta(complete=False, stop_reason="page_cap")
        try:
            from twikit.errors import TooManyRequests
        except ImportError:  # pragma: no cover - older twikit
            TooManyRequests = None

        page = None
        try:
            while meta.pages < max_pages:
                if page is None:
                    page = await self.client.search_tweet(query, 'Latest', count=20)
                else:
                    if page_delay > 0:
                        await asyncio.sleep(page_delay)
                    page = await page.next()
                meta.pages += 1
                batch = list(page or [])
                if not batch:
                    meta.stop_reason = "exhausted"
                    break
                for tweet in batch:
                    post = self._to_post(tweet, ticker)
                    if post.tweet_id in known_ids:
                        meta.stop_reason = "reached_known"
                    elif since_utc is not None and post.created_at < since_utc:
                        meta.stop_reason = "reached_since"
                    else:
                        posts.append(post)
                if meta.stop_reason in ("reached_known", "reached_since"):
                    break
            meta.complete = meta.stop_reason in ("exhausted", "reached_known", "reached_since")
        except Exception as e:
            rate_limited = TooManyRequests is not None and isinstance(e, TooManyRequests)
            if meta.pages > 0:
                # Keep the pages already read; the window is just not fully covered
                meta.stop_reason = "rate_limited" if rate_limited else "error"
                meta.complete = False
                logger.warning(f"Twikit stopped paging for {ticker} after {meta.pages} page(s) ({e}).")
            elif getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                logger.warning(f"Twikit search error for ticker {ticker} ({e}). Using mock fallback.")
                return await self._fallback_provider.search(query, ticker, max_results)
            else:
                logger.error(f"Twikit search error for ticker {ticker} ({e}). ALLOW_MOCK_FALLBACK=False, propagating exception.")
                raise

        self.last_search_meta = meta
        logger.info(f"Twikit collected {len(posts)} new posts for {ticker} in {meta.pages} page(s) "
                    f"(stop: {meta.stop_reason}, complete: {meta.complete}).")
        if not posts and not known_ids and getattr(settings, "ALLOW_MOCK_FALLBACK", False):
            return await self._fallback_provider.search(query, ticker, max_results)
        return posts

    @staticmethod
    def _to_post(tweet, ticker: str) -> SocialPostData:
        if hasattr(tweet, 'created_at') and tweet.created_at:
            try:
                parsed_dt = datetime.strptime(tweet.created_at, '%a %b %d %H:%M:%S %z %Y')
                created_dt = parsed_dt.astimezone(timezone.utc)
            except Exception:
                created_dt = datetime.now(timezone.utc)
        else:
            created_dt = datetime.now(timezone.utc)
        user_name = getattr(tweet.user, 'name', 'x_user') if getattr(tweet, 'user', None) else 'x_user'
        return SocialPostData(
            tweet_id=str(tweet.id),
            ticker=ticker,
            username=user_name,
            text=getattr(tweet, 'text', '') or '',
            created_at=created_dt,
            url=f"https://x.com/x/status/{tweet.id}",
            likes=int(getattr(tweet, 'favorite_count', 0) or 0),
            reposts=int(getattr(tweet, 'retweet_count', 0) or 0),
            replies=int(getattr(tweet, 'reply_count', 0) or 0),
            views=int(getattr(tweet, 'view_count', 0) or 0),
            source="LIVE",
            lang=getattr(tweet, 'lang', None)
        )
