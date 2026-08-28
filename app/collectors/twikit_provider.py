import os
import logging
from datetime import datetime, timezone
from typing import List
from app.collectors.base import XProvider, SocialPostData
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

            # 1. Check if saved cookies exist
            if os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0:
                try:
                    self.client.load_cookies(cookies_file)
                    logger.info(f"Loaded existing X cookies from {cookies_file}")
                    self._authenticated = True
                    return True
                except Exception as e:
                    logger.warning(f"Failed to load cookies from {cookies_file}: {e}. Retrying login...")

            # 2. If no valid cookies, perform login with credentials
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

    async def search(self, query: str, ticker: str, max_results: int = 100) -> List[SocialPostData]:
        is_auth = await self._ensure_authenticated()
        if not is_auth or not self.client:
            if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                return await self._fallback_provider.search(query, ticker, max_results)
            logger.warning(f"Twikit unauthenticated and ALLOW_MOCK_FALLBACK=False. Returning empty dataset for {ticker}.")
            return []

        posts = []
        try:
            tweets = await self.client.search_tweet(query, 'Latest', count=max_results)
            if tweets:
                for tweet in tweets:
                    if hasattr(tweet, 'created_at') and tweet.created_at:
                        try:
                            parsed_dt = datetime.strptime(tweet.created_at, '%a %b %d %H:%M:%S %z %Y')
                            created_dt = parsed_dt.astimezone(timezone.utc)
                        except Exception:
                            created_dt = datetime.now(timezone.utc)
                    else:
                        created_dt = datetime.now(timezone.utc)
                    posts.append(SocialPostData(
                        tweet_id=str(tweet.id),
                        ticker=ticker,
                        username=getattr(tweet.user, 'name', 'x_user') if hasattr(tweet, 'user') else 'x_user',
                        text=getattr(tweet, 'text', ''),
                        created_at=created_dt,
                        url=f"https://x.com/x/status/{tweet.id}",
                        likes=getattr(tweet, 'favorite_count', 0),
                        reposts=getattr(tweet, 'retweet_count', 0),
                        replies=getattr(tweet, 'reply_count', 0),
                        views=getattr(tweet, 'view_count', 0)
                    ))
            logger.info(f"Twikit collected {len(posts)} posts for {ticker} query '{query}'.")
            if not posts and getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                return await self._fallback_provider.search(query, ticker, max_results)
        except Exception as e:
            if getattr(settings, "ALLOW_MOCK_FALLBACK", False):
                logger.warning(f"Twikit search error for ticker {ticker} ({e}). Using mock fallback.")
                return await self._fallback_provider.search(query, ticker, max_results)
            logger.error(f"Twikit search error for ticker {ticker} ({e}). ALLOW_MOCK_FALLBACK=False, returning empty dataset.")
            return []
            
        return posts
