import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("SMIE.Fundamentals")


def calculate_fundamental_score(fund_data: Optional[Dict[str, Any]]) -> Optional[float]:
    """
    Computes a normalized Fundamental Health Score (0 - 100) specifically tailored for
    commercial space technology and aerospace growth companies.
    
    Sub-Components:
    1. Cash Runway & Burn Rate (40%): Evaluates months of operational survival without dilution.
    2. Debt Burden & Solvency (25%): Measures cash buffer relative to debt obligations.
    3. Revenue Growth YoY (20%): Evaluates commercialization and contract execution traction.
    4. Gross & Operating Margins (15%): Evaluates unit economics and path to profitability.
    
    Returns None if no fundamental data is available (clean adaptive exclusion).
    """
    if not fund_data or not isinstance(fund_data, dict):
        return None

    total_cash = fund_data.get("total_cash")
    total_debt = fund_data.get("total_debt")
    free_cashflow = fund_data.get("free_cashflow")
    revenue_growth = fund_data.get("revenue_growth")
    gross_margins = fund_data.get("gross_margins")

    # If all primary metrics are None, return None
    if all(v is None for v in [total_cash, total_debt, free_cashflow, revenue_growth, gross_margins]):
        return None

    # 1. Cash Runway & Burn Rate (Weight: 40%)
    runway_score = 50.0
    if free_cashflow is not None:
        if free_cashflow >= 0:
            # Cash flow positive: highest health tier
            runway_score = 90.0
        elif total_cash is not None and total_cash > 0:
            annual_burn = abs(free_cashflow)
            runway_years = total_cash / annual_burn if annual_burn > 0 else 5.0
            if runway_years >= 2.5:      # 30+ months runway
                runway_score = 85.0
            elif runway_years >= 1.5:    # 18 - 30 months runway
                runway_score = 70.0
            elif runway_years >= 1.0:    # 12 - 18 months runway
                runway_score = 55.0
            elif runway_years >= 0.5:    # 6 - 12 months runway (capital raise risk)
                runway_score = 35.0
            else:                        # < 6 months runway (severe dilution/insolvency risk)
                runway_score = 15.0
        else:
            runway_score = 25.0
    elif total_cash is not None and total_cash > 100_000_000:
        runway_score = 70.0

    # 2. Debt Burden & Solvency (Weight: 25%)
    solvency_score = 50.0
    if total_cash is not None and total_cash > 0:
        debt = total_debt if total_debt is not None else 0.0
        if debt == 0 or total_cash >= debt:
            # Net cash positive
            solvency_score = 80.0
        else:
            debt_to_cash = debt / total_cash
            if debt_to_cash <= 1.5:
                solvency_score = 60.0
            elif debt_to_cash <= 3.0:
                solvency_score = 40.0
            else:
                solvency_score = 20.0
    elif total_debt is not None and total_debt > 0:
        solvency_score = 30.0

    # 3. Revenue Growth YoY (Weight: 20%)
    growth_score = 50.0
    if revenue_growth is not None:
        if revenue_growth >= 0.50:       # > +50% YoY
            growth_score = 90.0
        elif revenue_growth >= 0.20:     # +20% to +50% YoY
            growth_score = 75.0
        elif revenue_growth >= 0.0:      # 0% to +20% YoY
            growth_score = 55.0
        elif revenue_growth >= -0.20:    # -20% to 0% YoY
            growth_score = 35.0
        else:                            # < -20% YoY contraction
            growth_score = 20.0

    # 4. Gross Margins / Unit Economics (Weight: 15%)
    margin_score = 50.0
    if gross_margins is not None:
        if gross_margins >= 0.40:        # High software/data payload margin (>40%)
            margin_score = 80.0
        elif gross_margins >= 0.20:      # Healthy aerospace manufacturing margin (20-40%)
            margin_score = 65.0
        elif gross_margins >= 0.0:       # Positive gross margin
            margin_score = 45.0
        else:                            # Negative gross margins
            margin_score = 25.0

    weighted_score = (
        0.40 * runway_score +
        0.25 * solvency_score +
        0.20 * growth_score +
        0.15 * margin_score
    )

    return max(0.0, min(100.0, round(weighted_score, 1)))
