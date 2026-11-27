"""
SEC filing classification for the dilution monitor (no network, no scoring).

Only the form type and the 8-K item codes are read, never the document text, so the classification is
deterministic and reproducible from the EDGAR submissions index alone.

Categories:
- OFFERING: a prospectus for a sale that is happening (424B1/B2/B4/B5). This is the dilution event; an
  at-the-market program shows up here once, when it is set up, and later sales only appear in the 10-Q.
- UNREGISTERED_SALE: 8-K item 3.02 (shares or convertibles sold outside a registration, e.g. a PIPE or the
  conversion shares behind 144A convertible notes, which never get a 424B).
- DEBT_FINANCING: 8-K item 2.03 (a new direct financial obligation: notes, loans, convertibles).
- SHELF: S-3/S-1/F-3/F-1 registrations. A shelf only allows the company to sell later and stays effective for
  three years, so cash-burning companies keep one almost permanently. Context, never a dilution event.
- RESALE: 424B3/424B7, shares sold by existing holders (resale registrations of SPAC-era companies are
  refreshed constantly). Stored for history, no alert.
"""
from typing import Optional

OFFERING = "OFFERING"
UNREGISTERED_SALE = "UNREGISTERED_SALE"
DEBT_FINANCING = "DEBT_FINANCING"
SHELF = "SHELF"
RESALE = "RESALE"

# Company sells new securities: the events behind the SEC OFFERING modifier
DILUTION_CATEGORIES = frozenset({OFFERING, UNREGISTERED_SALE})
# Categories that cap BUY / STRONG BUY at WATCH (phase 2, 27/11/2026). Only OFFERING: 33 episodes since 2022 gave a
# 3-session abnormal return of -7.3% (95% CI -13.0% to -1.4%); unregistered sales, shelves and resales showed no
# measurable effect (audit/sentiment_2026_10/event_study_sec.py, PROJECT_CONTEXT.md section 5).
GATE_CATEGORIES = frozenset({OFFERING})

OFFERING_FORMS = frozenset({"424B1", "424B2", "424B4", "424B5"})
RESALE_FORMS = frozenset({"424B3", "424B7"})
SHELF_FORMS = frozenset({"S-1", "S-1/A", "S-1MEF", "S-3", "S-3/A", "S-3ASR", "S-3MEF", "F-1", "F-1/A", "F-3", "F-3/A", "F-3ASR"})
CURRENT_REPORT_FORMS = frozenset({"8-K", "8-K/A"})

CATEGORY_LABELS = {
    OFFERING: "offering prospectus (new securities being sold)",
    UNREGISTERED_SALE: "unregistered sale of equity (8-K item 3.02)",
    DEBT_FINANCING: "new debt obligation (8-K item 2.03)",
    SHELF: "shelf registration (allows future offerings)",
    RESALE: "resale prospectus (existing holders selling)",
}


def parse_items(items: Optional[str]) -> set:
    """'1.01,2.03,9.01' -> {'1.01', '2.03', '9.01'}"""
    return {i.strip() for i in (items or "").split(",") if i.strip()}


def classify_filing(form: Optional[str], items: Optional[str] = None) -> Optional[str]:
    """Category of one EDGAR filing, or None when it is not tracked (10-Q, 4, SC 13G, plain 8-Ks...)."""
    f = (form or "").strip().upper()
    if f in OFFERING_FORMS:
        return OFFERING
    if f in RESALE_FORMS:
        return RESALE
    if f in SHELF_FORMS:
        return SHELF
    if f in CURRENT_REPORT_FORMS:
        codes = parse_items(items)
        # 3.02 first: a convertible note is usually filed as 1.01 + 2.03 + 3.02, and the equity side is the dilution
        if "3.02" in codes:
            return UNREGISTERED_SALE
        if "2.03" in codes:
            return DEBT_FINANCING
    return None
