import logging
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf
from app.collectors.base import MarketProviderInterface, MarketData

logger = logging.getLogger(__name__)


class YFinanceMarketProvider(MarketProviderInterface):
    async def get_market_data(self, ticker: str) -> MarketData:
        try:
            # Download 1 year of daily history to ensure EMA200 can be calculated
            ticker_obj = yf.Ticker(ticker)
            df = ticker_obj.history(period="1y", interval="1d")
            
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if df.empty or len(df) < 5 or 'Close' not in df.columns:
                logger.warning(f"Market data for {ticker} unavailable or insufficient history.")
                return MarketData(
                    ticker=ticker,
                    timestamp=now,
                    price=None,
                    volume=None,
                    status="DATA_UNAVAILABLE",
                    raw_df=None
                )
            
            # Extract latest price and volume
            latest_row = df.iloc[-1]
            latest_price = float(latest_row['Close'])
            latest_volume = float(latest_row['Volume'])

            if pd.isna(latest_price) or latest_price <= 0:
                return MarketData(
                    ticker=ticker,
                    timestamp=now,
                    price=None,
                    volume=None,
                    status="DATA_UNAVAILABLE",
                    raw_df=None
                )

            return MarketData(
                ticker=ticker,
                timestamp=now,
                price=latest_price,
                volume=latest_volume,
                status="AVAILABLE",
                raw_df=df
            )
        except Exception as e:
            logger.error(f"Error fetching market data for {ticker}: {e}")
            return MarketData(
                ticker=ticker,
                timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
                price=None,
                volume=None,
                status="DATA_UNAVAILABLE",
                raw_df=None
            )
