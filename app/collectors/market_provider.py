import asyncio
import logging
from datetime import datetime, timezone
import pandas as pd
import yfinance as yf
from app.collectors.base import MarketProviderInterface, MarketData

logger = logging.getLogger(__name__)


# In-memory fundamentals cache: ticker -> (timestamp, data_dict) with 24h TTL
_FUNDAMENTALS_CACHE: dict = {}
_CACHE_TTL_SECONDS = 86400  # 24 hours


def _fetch_market_data_sync(ticker: str) -> MarketData:
    """Synchronous worker function executed in a separate thread."""
    try:
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
            price=round(latest_price, 2),
            volume=int(latest_volume) if not pd.isna(latest_volume) else 0,
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


def _fetch_fundamentals_sync(ticker_up: str) -> dict:
    """Synchronous worker function executed in a separate thread."""
    result = {
        "total_cash": None,
        "total_debt": None,
        "free_cashflow": None,
        "revenue_growth": None,
        "gross_margins": None,
        "operating_margins": None,
        "market_cap": None
    }

    try:
        ticker_obj = yf.Ticker(ticker_up)

        # Fast Info for Market Cap
        try:
            fast_info = getattr(ticker_obj, "fast_info", None)
            if fast_info and hasattr(fast_info, "market_cap"):
                result["market_cap"] = fast_info.market_cap
        except Exception:
            pass

        # Balance Sheet Data (Cash & Debt)
        try:
            bs = ticker_obj.balance_sheet
            if bs is not None and not bs.empty:
                for cash_key in ['End Cash Position', 'Cash Cash Equivalents And Short Term Investments', 'Cash And Cash Equivalents']:
                    if cash_key in bs.index:
                        val = bs.loc[cash_key].iloc[0]
                        if not pd.isna(val):
                            result["total_cash"] = float(val)
                            break

                for debt_key in ['Total Debt', 'Net Debt']:
                    if debt_key in bs.index:
                        val = bs.loc[debt_key].iloc[0]
                        if not pd.isna(val):
                            result["total_debt"] = float(val)
                            break
        except Exception as bs_err:
            logger.debug(f"Balance sheet extraction failed for {ticker_up}: {bs_err}")

        # Cashflow Data (Free Cashflow)
        try:
            cf = ticker_obj.cashflow
            if cf is not None and not cf.empty:
                if 'End Cash Position' in cf.index and result["total_cash"] is None:
                    val = cf.loc['End Cash Position'].iloc[0]
                    if not pd.isna(val):
                        result["total_cash"] = float(val)

                for fcf_key in ['Free Cash Flow', 'Operating Cash Flow']:
                    if fcf_key in cf.index:
                        val = cf.loc[fcf_key].iloc[0]
                        if not pd.isna(val):
                            result["free_cashflow"] = float(val)
                            break
        except Exception as cf_err:
            logger.debug(f"Cashflow extraction failed for {ticker_up}: {cf_err}")

        # Financials Data (Revenue, Gross Margin, Revenue Growth)
        try:
            fin = ticker_obj.financials
            if fin is not None and not fin.empty:
                rev_series = fin.loc['Total Revenue'] if 'Total Revenue' in fin.index else None
                gp_series = fin.loc['Gross Profit'] if 'Gross Profit' in fin.index else None
                op_series = fin.loc['Operating Income'] if 'Operating Income' in fin.index else None

                if rev_series is not None and len(rev_series) > 0:
                    latest_rev = rev_series.iloc[0]
                    if not pd.isna(latest_rev) and latest_rev > 0:
                        if gp_series is not None and len(gp_series) > 0:
                            latest_gp = gp_series.iloc[0]
                            if not pd.isna(latest_gp):
                                result["gross_margins"] = float(latest_gp / latest_rev)

                        if op_series is not None and len(op_series) > 0:
                            latest_op = op_series.iloc[0]
                            if not pd.isna(latest_op):
                                result["operating_margins"] = float(latest_op / latest_rev)

                        if len(rev_series) >= 2:
                            prev_rev = rev_series.iloc[1]
                            if not pd.isna(prev_rev) and prev_rev > 0:
                                result["revenue_growth"] = float((latest_rev - prev_rev) / prev_rev)
        except Exception as fin_err:
            logger.debug(f"Financials extraction failed for {ticker_up}: {fin_err}")

        if all(v is None for v in result.values()):
            logger.warning(f"No fundamental financial statements available for {ticker_up} (e.g. ETF/proxy or missing SEC filings).")
        else:
            logger.info(f"Retrieved fundamentals for {ticker_up}: Cash=${result['total_cash']}, Debt=${result['total_debt']}, FCF=${result['free_cashflow']}")

        return result

    except Exception as e:
        logger.warning(f"Error fetching fundamentals for {ticker_up}: {e}")
        return result


class YFinanceMarketProvider(MarketProviderInterface):
    async def get_market_data(self, ticker: str) -> MarketData:
        """Fetch market data asynchronously in a worker thread to prevent event loop blocking."""
        return await asyncio.to_thread(_fetch_market_data_sync, ticker)

    async def fetch_market_data(self, ticker: str) -> MarketData:
        """Alias for get_market_data to maintain backwards compatibility."""
        return await self.get_market_data(ticker)

    async def get_fundamentals(self, ticker: str) -> dict:
        """
        Retrieves key balance sheet, cash runway, and growth metrics from yfinance
        using worker threads (asyncio.to_thread) and 24h caching.
        """
        ticker_up = ticker.upper()
        now_ts = datetime.now(timezone.utc).timestamp()

        # 1. Check in-memory cache
        if ticker_up in _FUNDAMENTALS_CACHE:
            cached_time, cached_data = _FUNDAMENTALS_CACHE[ticker_up]
            if (now_ts - cached_time) < _CACHE_TTL_SECONDS:
                return cached_data

        # 2. Fetch in background thread without blocking event loop
        result = await asyncio.to_thread(_fetch_fundamentals_sync, ticker_up)
        _FUNDAMENTALS_CACHE[ticker_up] = (now_ts, result)
        return result
