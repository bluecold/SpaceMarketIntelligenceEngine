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

    active_components = {}

    # 1. Cash Runway & Burn Rate (Base Weight: 40%)
    if total_cash is not None or free_cashflow is not None:
        runway_score = 50.0
        if total_cash is not None and total_cash <= 0:
            # Zero or negative cash buffer is an acute existential survival crisis
            runway_score = 0.0
        elif free_cashflow is not None:
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
                # Negative FCF but total_cash is unknown (None)
                runway_score = 25.0
        elif total_cash is not None and total_cash > 100_000_000:
            runway_score = 70.0
        active_components["runway"] = (runway_score, 0.40)

    # 2. Debt Burden & Solvency (Base Weight: 25%)
    if total_cash is not None or total_debt is not None:
        solvency_score = 50.0
        if total_cash is not None:
            if total_cash <= 0:
                if total_debt is not None and total_debt > 0:
                    solvency_score = 10.0  # Zero cash with debt = severe insolvency risk
                elif total_debt is not None and total_debt == 0:
                    solvency_score = 40.0  # Zero cash and zero debt = fragile
                else:
                    solvency_score = 25.0  # Zero cash with unknown debt
            elif total_debt is not None:
                if total_debt == 0 or total_cash >= total_debt:
                    # Verified net cash positive
                    solvency_score = 80.0
                else:
                    debt_to_cash = total_debt / total_cash
                    if debt_to_cash <= 1.5:
                        solvency_score = 60.0
                    elif debt_to_cash <= 3.0:
                        solvency_score = 40.0
                    else:
                        solvency_score = 20.0
            else:
                # total_cash > 0, but total_debt is None (unknown debt).
                # Do NOT assume debt is 0. Neutral score without false net-cash-positive bonus.
                solvency_score = 50.0
        elif total_debt is not None:
            if total_debt > 0:
                solvency_score = 30.0  # Debt exists, cash buffer unknown
            else:
                solvency_score = 50.0  # Zero debt reported, cash unknown
        active_components["solvency"] = (solvency_score, 0.25)

    # 3. Revenue Growth YoY (Base Weight: 20%)
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
        active_components["growth"] = (growth_score, 0.20)

    # 4. Gross Margins / Unit Economics (Base Weight: 15%)
    if gross_margins is not None:
        if gross_margins >= 0.40:        # High software/data payload margin (>40%)
            margin_score = 80.0
        elif gross_margins >= 0.20:      # Healthy aerospace manufacturing margin (20-40%)
            margin_score = 65.0
        elif gross_margins >= 0.0:       # Positive gross margin
            margin_score = 45.0
        else:                            # Negative gross margins
            margin_score = 25.0
        active_components["margin"] = (margin_score, 0.15)

    if not active_components:
        return None

    total_weight = sum(w for _, w in active_components.values())
    weighted_score = sum(score * (w / total_weight) for score, w in active_components.values())

    return max(0.0, min(100.0, round(weighted_score, 1)))


def get_fundamental_runway_info(fund_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculates runway months, annual burn rate, and capital raise / dilution risk tier.
    Preserves None for unknown values, explicitly treats 0.0 as known zero,
    and returns balance sheet accounting dates and period types.
    """
    if not fund_data or not isinstance(fund_data, dict):
        return {
            "runway_months": None,
            "risk_tier": "UNKNOWN",
            "cash": None,
            "burn": None,
            "debt": None,
            "as_of_date": None,
            "period_type": None
        }

    total_cash = fund_data.get("total_cash")
    free_cashflow = fund_data.get("free_cashflow")
    total_debt = fund_data.get("total_debt")  # Preserve None; do not coalesce to 0.0
    as_of_date = fund_data.get("balance_sheet_date") or fund_data.get("as_of_date")
    period_type = fund_data.get("period_type")

    # Case 1: Total cash is known and exhausted (0 or negative)
    if total_cash is not None and total_cash <= 0:
        annual_burn = abs(free_cashflow) if (free_cashflow is not None and free_cashflow < 0) else (0.0 if free_cashflow is not None else None)
        return {
            "runway_months": 0.0,
            "risk_tier": "CRITICAL",
            "cash": total_cash,
            "burn": annual_burn,
            "debt": total_debt,
            "as_of_date": as_of_date,
            "period_type": period_type
        }

    # Case 2: Burning cash with positive cash reserves
    if free_cashflow is not None and free_cashflow < 0 and total_cash is not None and total_cash > 0:
        annual_burn = abs(free_cashflow)
        runway_months = (total_cash / annual_burn) * 12.0
        if runway_months < 6.0:
            risk_tier = "CRITICAL"
        elif runway_months < 12.0:
            risk_tier = "HIGH"
        else:
            risk_tier = "LOW"
        return {
            "runway_months": round(runway_months, 1),
            "risk_tier": risk_tier,
            "cash": total_cash,
            "burn": annual_burn,
            "debt": total_debt,
            "as_of_date": as_of_date,
            "period_type": period_type
        }

    # Case 3: Cash flow positive / break-even
    if free_cashflow is not None and free_cashflow >= 0:
        return {
            "runway_months": 999.0,  # Cash flow positive
            "risk_tier": "SAFE",
            "cash": total_cash,
            "burn": 0.0,
            "debt": total_debt,
            "as_of_date": as_of_date,
            "period_type": period_type
        }

    # Case 4: Explicit runway_months provided directly in payload
    explicit_runway = fund_data.get("runway_months")
    if explicit_runway is not None:
        if explicit_runway < 6.0:
            risk_tier = "CRITICAL"
        elif explicit_runway < 12.0:
            risk_tier = "HIGH"
        elif explicit_runway >= 999.0:
            risk_tier = "SAFE"
        else:
            risk_tier = "LOW"
        annual_burn = abs(free_cashflow) if (free_cashflow is not None and free_cashflow < 0) else None
        return {
            "runway_months": round(float(explicit_runway), 1),
            "risk_tier": risk_tier,
            "cash": total_cash,
            "burn": annual_burn,
            "debt": total_debt,
            "as_of_date": as_of_date,
            "period_type": period_type
        }

    # Case 5: Cash or FCF unknown
    annual_burn = abs(free_cashflow) if (free_cashflow is not None and free_cashflow < 0) else None
    return {
        "runway_months": None,
        "risk_tier": "UNKNOWN",
        "cash": total_cash,
        "burn": annual_burn,
        "debt": total_debt,
        "as_of_date": as_of_date,
        "period_type": period_type
    }

