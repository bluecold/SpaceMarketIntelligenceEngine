import asyncio
import logging
from datetime import datetime, date, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List, Set
import pandas as pd
import yfinance as yf
from app.config import INITIAL_TICKERS
from app.collectors.base import MarketProviderInterface, MarketData

logger = logging.getLogger(__name__)

_EASTERN_TZ = ZoneInfo("America/New_York")

# In-memory fundamentals cache: ticker -> (timestamp, data_dict) with 24h TTL
_FUNDAMENTALS_CACHE: dict = {}
_CACHE_TTL_SECONDS = 86400  # 24 hours


def _calculate_easter(year: int) -> date:
    """Computes Easter Sunday using the Meeus/Jones/Butcher Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """Finds the nth occurrence of a weekday in a month (1-indexed). 0=Mon, 6=Sun."""
    first_day = date(year, month, 1)
    day_offset = (weekday - first_day.weekday()) % 7
    return first_day + timedelta(days=day_offset + (n - 1) * 7)


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """Finds the last occurrence of a weekday in a month. 0=Mon, 6=Sun."""
    if month == 12:
        last_day = date(year, 12, 31)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    day_offset = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=day_offset)


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    """Observes fixed holiday on Friday if Saturday, Monday if Sunday."""
    d = date(year, month, day)
    if d.weekday() == 5:  # Saturday -> Friday
        return d - timedelta(days=1)
    elif d.weekday() == 6:  # Sunday -> Monday
        return d + timedelta(days=1)
    return d


def get_us_market_holidays(year: int) -> Set[date]:
    """Returns set of date objects for all official NYSE/NASDAQ full-day holidays in a year."""
    holidays: Set[date] = set()
    
    # New Year's Day (observed)
    nyd = _observed_fixed_holiday(year, 1, 1)
    holidays.add(nyd)
    
    # Check if Dec 31 of year is observed New Year's for year + 1
    if date(year, 12, 31).weekday() == 4:
        holidays.add(date(year, 12, 31))
        
    # Martin Luther King Jr. Day: 3rd Monday in January
    holidays.add(_nth_weekday_of_month(year, 1, 0, 3))
    
    # Washington's Birthday (Presidents' Day): 3rd Monday in February
    holidays.add(_nth_weekday_of_month(year, 2, 0, 3))
    
    # Good Friday: Friday before Easter Sunday
    easter = _calculate_easter(year)
    good_friday = easter - timedelta(days=2)
    holidays.add(good_friday)
    
    # Memorial Day: Last Monday in May
    holidays.add(_last_weekday_of_month(year, 5, 0))
    
    # Juneteenth National Independence Day (June 19, observed)
    holidays.add(_observed_fixed_holiday(year, 6, 19))
    
    # Independence Day (July 4, observed)
    holidays.add(_observed_fixed_holiday(year, 7, 4))
    
    # Labor Day: 1st Monday in September
    holidays.add(_nth_weekday_of_month(year, 9, 0, 1))
    
    # Thanksgiving Day: 4th Thursday in November
    holidays.add(_nth_weekday_of_month(year, 11, 3, 4))
    
    # Christmas Day (Dec 25, observed)
    holidays.add(_observed_fixed_holiday(year, 12, 25))
    
    return holidays


def get_us_market_early_closes(year: int) -> Set[date]:
    """Returns set of date objects for official NYSE/NASDAQ early close (1:00 PM Eastern) days."""
    early_closes: Set[date] = set()
    
    # Day before Independence Day (July 3 if weekday and July 4 is not Saturday)
    july3 = date(year, 7, 3)
    if july3.weekday() < 5 and date(year, 7, 4).weekday() != 5:
        early_closes.add(july3)
        
    # Black Friday (Day after Thanksgiving): 4th Friday in November
    thanksgiving = _nth_weekday_of_month(year, 11, 3, 4)
    black_friday = thanksgiving + timedelta(days=1)
    early_closes.add(black_friday)
    
    # Christmas Eve (Dec 24 if weekday and not observed Christmas)
    dec24 = date(year, 12, 24)
    if dec24.weekday() < 5 and date(year, 12, 25).weekday() != 5:
        early_closes.add(dec24)
        
    return early_closes


def determine_market_session(dt: Optional[datetime] = None) -> str:
    """
    Determines US Equity market session status (NYSE/NASDAQ):
    - Converts input datetime to America/New_York timezone (supporting both EDT and EST).
    - Returns 'WEEKEND' if Saturday or Sunday.
    - Returns 'CLOSED' if official US market holiday.
    - Returns 'REGULAR' if Mon-Fri between 09:30 and 16:00 Eastern (or 09:30 to 13:00 on early close days).
    - Returns 'CLOSED' otherwise.
    """
    ref_dt = dt or datetime.now(timezone.utc)
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)
    
    eastern_dt = ref_dt.astimezone(_EASTERN_TZ)
    
    # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
    if eastern_dt.weekday() >= 5:
        return "WEEKEND"
    
    curr_date = eastern_dt.date()
    holidays = get_us_market_holidays(curr_date.year)
    if curr_date in holidays:
        return "CLOSED"
    
    eastern_minutes = eastern_dt.hour * 60 + eastern_dt.minute
    open_minutes = 9 * 60 + 30  # 09:30 AM Eastern
    
    early_closes = get_us_market_early_closes(curr_date.year)
    close_minutes = (13 * 60) if curr_date in early_closes else (16 * 60)  # 1:00 PM or 4:00 PM Eastern
    
    if open_minutes <= eastern_minutes < close_minutes:
        return "REGULAR"
    return "CLOSED"


def _fetch_market_data_sync(ticker: str) -> MarketData:
    """Synchronous worker function executed in a separate thread."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    session = determine_market_session(now)
    try:
        cfg = next((t for t in INITIAL_TICKERS if t.symbol == ticker), None)
        provider_symbol = (cfg.market_symbol or ticker) if cfg else ticker
        ticker_obj = yf.Ticker(provider_symbol)
        df = ticker_obj.history(period="1y", interval="1d")
        
        if df.empty or len(df) < 5 or 'Close' not in df.columns:
            logger.warning(f"Market data for {ticker} unavailable or insufficient history.")
            return MarketData(
                ticker=ticker,
                timestamp=now,
                observed_at=None,
                candle_date=None,
                market_session=session,
                price=None,
                volume=None,
                status="DATA_UNAVAILABLE",
                raw_df=None
            )
        
        latest_row = df.iloc[-1]
        latest_price = float(latest_row['Close'])
        latest_volume = float(latest_row['Volume'])

        # Extract underlying candle observed timestamp and date
        last_idx = df.index[-1]
        obs_dt = None
        if hasattr(last_idx, "tz_convert"):
            try:
                if last_idx.tzinfo is not None:
                    obs_dt = last_idx.tz_convert('UTC').to_pydatetime().replace(tzinfo=None)
                else:
                    obs_dt = last_idx.to_pydatetime()
            except Exception:
                obs_dt = now
        elif isinstance(last_idx, datetime):
            obs_dt = last_idx.replace(tzinfo=None) if last_idx.tzinfo is not None else last_idx
        else:
            obs_dt = now

        c_date = str(getattr(last_idx, "date", lambda: obs_dt.date())())

        if pd.isna(latest_price) or latest_price <= 0:
            return MarketData(
                ticker=ticker,
                timestamp=now,
                observed_at=obs_dt,
                candle_date=c_date,
                market_session=session,
                price=None,
                volume=None,
                status="DATA_UNAVAILABLE",
                raw_df=None
            )

        return MarketData(
            ticker=ticker,
            timestamp=now,
            observed_at=obs_dt,
            candle_date=c_date,
            market_session=session,
            price=round(latest_price, 2),
            volume=int(latest_volume) if not pd.isna(latest_volume) else 0,
            status="AVAILABLE",
            raw_df=df
        )
    except Exception as e:
        logger.error(f"Error fetching market data for {ticker}: {e}")
        return MarketData(
            ticker=ticker,
            timestamp=now,
            observed_at=None,
            candle_date=None,
            market_session=session,
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
        "net_debt": None,
        "free_cashflow": None,
        "revenue_growth": None,
        "gross_margins": None,
        "operating_margins": None,
        "market_cap": None,
        "balance_sheet_date": None,
        "cashflow_date": None,
        "period_type": None
    }

    try:
        cfg = next((t for t in INITIAL_TICKERS if t.symbol == ticker_up), None)
        provider_symbol = (cfg.market_symbol or ticker_up) if cfg else ticker_up
        ticker_obj = yf.Ticker(provider_symbol)

        # Fast Info for Market Cap
        try:
            fast_info = getattr(ticker_obj, "fast_info", None)
            if fast_info and hasattr(fast_info, "market_cap"):
                result["market_cap"] = fast_info.market_cap
        except Exception:
            pass

        # Balance Sheet Data (Prioritize Quarterly over Annual for current cash/debt state)
        try:
            bs = None
            period_type = None

            # Check quarterly balance sheet first
            q_bs = getattr(ticker_obj, "quarterly_balance_sheet", None)
            if q_bs is not None and not q_bs.empty:
                bs = q_bs
                period_type = "quarterly"
            else:
                ann_bs = getattr(ticker_obj, "balance_sheet", None)
                if ann_bs is not None and not ann_bs.empty:
                    bs = ann_bs
                    period_type = "annual"

            if bs is not None and not bs.empty:
                result["period_type"] = period_type
                # Extract accounting balance sheet date
                if len(bs.columns) > 0:
                    col_date = bs.columns[0]
                    result["balance_sheet_date"] = str(col_date)[:10] if col_date is not None else None

                for cash_key in ['End Cash Position', 'Cash Cash Equivalents And Short Term Investments', 'Cash And Cash Equivalents']:
                    if cash_key in bs.index:
                        val = bs.loc[cash_key].iloc[0]
                        if not pd.isna(val):
                            result["total_cash"] = float(val)
                            break

                # Extract Total Debt strictly without substituting Net Debt
                for debt_key in ['Total Debt', 'Total Debt And Capital Lease Obligation']:
                    if debt_key in bs.index:
                        val = bs.loc[debt_key].iloc[0]
                        if not pd.isna(val):
                            result["total_debt"] = float(val)
                            break

                # If Total Debt not directly reported, check component sum: Long Term Debt + Current Debt
                if result["total_debt"] is None:
                    lt_debt = bs.loc['Long Term Debt'].iloc[0] if 'Long Term Debt' in bs.index else None
                    curr_debt = bs.loc['Current Debt'].iloc[0] if 'Current Debt' in bs.index else None
                    if lt_debt is not None or curr_debt is not None:
                        val_lt = float(lt_debt) if (lt_debt is not None and not pd.isna(lt_debt)) else 0.0
                        val_curr = float(curr_debt) if (curr_debt is not None and not pd.isna(curr_debt)) else 0.0
                        if val_lt > 0 or val_curr > 0:
                            result["total_debt"] = val_lt + val_curr

                # Capture Net Debt separately in its own dedicated field
                if 'Net Debt' in bs.index:
                    val_net = bs.loc['Net Debt'].iloc[0]
                    if not pd.isna(val_net):
                        result["net_debt"] = float(val_net)
        except Exception as bs_err:
            logger.debug(f"Balance sheet extraction failed for {ticker_up}: {bs_err}")

        # Cashflow Data (Prioritize Quarterly TTM FCF over Annual)
        try:
            cf = None
            q_cf = getattr(ticker_obj, "quarterly_cashflow", None)
            if q_cf is not None and not q_cf.empty:
                cf = q_cf
                if len(cf.columns) > 0:
                    result["cashflow_date"] = str(cf.columns[0])[:10]

                # Check for Cash balance fallback if not found in Balance Sheet
                if 'End Cash Position' in cf.index and result["total_cash"] is None:
                    val = cf.loc['End Cash Position'].iloc[0]
                    if not pd.isna(val):
                        result["total_cash"] = float(val)

                # Compute TTM Free Cash Flow if quarterly data available
                # 1. First priority: directly reported 'Free Cash Flow'
                if 'Free Cash Flow' in cf.index:
                    fcf_row = cf.loc['Free Cash Flow'].dropna()
                    if len(fcf_row) > 0:
                        if len(fcf_row) >= 4:
                            result["free_cashflow"] = float(fcf_row.iloc[:4].sum())
                        else:
                            result["free_cashflow"] = float((fcf_row.sum() / len(fcf_row)) * 4.0)
                # 2. Second priority: calculate FCF = Operating Cash Flow - abs(CAPEX)
                else:
                    ocf_key = next((k for k in ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities', 'Operating Cashflow'] if k in cf.index), None)
                    capex_key = next((k for k in ['Capital Expenditure', 'Capital Expenditures', 'Capital Expenditure Reported', 'Net PPE Purchase And Sale'] if k in cf.index), None)
                    if ocf_key is not None and capex_key is not None:
                        ocf_row = cf.loc[ocf_key].dropna()
                        capex_row = cf.loc[capex_key].dropna()
                        common_cols = [c for c in cf.columns if c in ocf_row.index and c in capex_row.index]
                        if common_cols:
                            fcf_series = []
                            for c in common_cols[:4]:
                                o_val = float(ocf_row[c])
                                cap_val = float(capex_row[c])
                                # CAPEX in cashflow statement is cash outflow; FCF = CFO - abs(CAPEX)
                                fcf_series.append(o_val - abs(cap_val))
                            if len(fcf_series) >= 4:
                                result["free_cashflow"] = float(sum(fcf_series))
                            elif len(fcf_series) > 0:
                                result["free_cashflow"] = float((sum(fcf_series) / len(fcf_series)) * 4.0)

            # Fallback to annual cashflow if quarterly FCF wasn't found
            if result["free_cashflow"] is None:
                ann_cf = getattr(ticker_obj, "cashflow", None)
                if ann_cf is not None and not ann_cf.empty:
                    if len(ann_cf.columns) > 0 and result["cashflow_date"] is None:
                        result["cashflow_date"] = str(ann_cf.columns[0])[:10]
                    if 'End Cash Position' in ann_cf.index and result["total_cash"] is None:
                        val = ann_cf.loc['End Cash Position'].iloc[0]
                        if not pd.isna(val):
                            result["total_cash"] = float(val)

                    if 'Free Cash Flow' in ann_cf.index:
                        val = ann_cf.loc['Free Cash Flow'].iloc[0]
                        if not pd.isna(val):
                            result["free_cashflow"] = float(val)
                    else:
                        ocf_key = next((k for k in ['Operating Cash Flow', 'Cash Flow From Continuing Operating Activities', 'Operating Cashflow'] if k in ann_cf.index), None)
                        capex_key = next((k for k in ['Capital Expenditure', 'Capital Expenditures', 'Capital Expenditure Reported', 'Net PPE Purchase And Sale'] if k in ann_cf.index), None)
                        if ocf_key is not None and capex_key is not None:
                            val_ocf = ann_cf.loc[ocf_key].iloc[0]
                            val_capex = ann_cf.loc[capex_key].iloc[0]
                            if not pd.isna(val_ocf) and not pd.isna(val_capex):
                                result["free_cashflow"] = float(val_ocf) - abs(float(val_capex))
        except Exception as cf_err:
            logger.debug(f"Cashflow extraction failed for {ticker_up}: {cf_err}")

        # Financials Data (Revenue, Gross Margin, Revenue Growth)
        try:
            fin = None
            is_quarterly_fin = False
            q_fin = getattr(ticker_obj, "quarterly_financials", None)
            if q_fin is not None and not q_fin.empty:
                fin = q_fin
                is_quarterly_fin = True
            else:
                ann_fin = getattr(ticker_obj, "financials", None)
                if ann_fin is not None and not ann_fin.empty:
                    fin = ann_fin
                    is_quarterly_fin = False

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

                        if is_quarterly_fin:
                            # For quarterly statements, calculate true Year-over-Year (YoY) growth by comparing
                            # current quarter against the same quarter 1 year ago (4 quarters prior / index 4)
                            if len(rev_series) >= 5:
                                prev_yoy_rev = rev_series.iloc[4]
                                if not pd.isna(prev_yoy_rev) and prev_yoy_rev > 0:
                                    result["revenue_growth"] = float((latest_rev - prev_yoy_rev) / prev_yoy_rev)
                            else:
                                # If quarterly financials have < 5 quarters, fallback to annual financials for YoY
                                ann_fin = getattr(ticker_obj, "financials", None)
                                if ann_fin is not None and not ann_fin.empty and 'Total Revenue' in ann_fin.index:
                                    ann_rev_series = ann_fin.loc['Total Revenue'].dropna()
                                    if len(ann_rev_series) >= 2 and ann_rev_series.iloc[1] > 0:
                                        result["revenue_growth"] = float((ann_rev_series.iloc[0] - ann_rev_series.iloc[1]) / ann_rev_series.iloc[1])
                        else:
                            # For annual statements, iloc[0] vs iloc[1] is FY_t vs FY_{t-1}, which is 1 year YoY
                            if len(rev_series) >= 2:
                                prev_rev = rev_series.iloc[1]
                                if not pd.isna(prev_rev) and prev_rev > 0:
                                    result["revenue_growth"] = float((latest_rev - prev_rev) / prev_rev)
        except Exception as fin_err:
            logger.debug(f"Financials extraction failed for {ticker_up}: {fin_err}")

        if all(v is None for v in result.values()):
            logger.warning(f"No fundamental financial statements available for {ticker_up} (e.g. ETF/proxy or missing SEC filings).")
        else:
            logger.info(f"Retrieved fundamentals for {ticker_up}: Cash=${result['total_cash']}, Debt=${result['total_debt']}, NetDebt=${result['net_debt']}, FCF=${result['free_cashflow']}, AsOf={result['balance_sheet_date']} ({result['period_type']})")

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
