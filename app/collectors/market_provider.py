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

    async def fetch_market_data(self, ticker: str) -> MarketData:
        """Alias for get_market_data to maintain backwards compatibility."""
        return await self.get_market_data(ticker)

    async def get_fundamentals(self, ticker: str) -> dict:
        """
        Retrieves key balance sheet, cash runway, and growth metrics from yfinance.
        """
        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info or {}
            return {
                "total_cash": info.get("totalCash"),
                "total_debt": info.get("totalDebt"),
                "free_cashflow": info.get("freeCashflow") or info.get("operatingCashflow"),
                "revenue_growth": info.get("revenueGrowth"),
                "gross_margins": info.get("grossMargins"),
                "operating_margins": info.get("operatingMargins"),
                "market_cap": info.get("marketCap")
            }
        except Exception as e:
            logger.warning(f"Error fetching fundamentals for {ticker}: {e}")
            return {}

