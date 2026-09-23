import math
import re
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict, Any
from app.config import settings

CATALYST_CONFIG = {
    "SATELLITE_DEPLOYMENT": {
        "keywords": [
            "satellite deployment", "satellites deployed", "satellite deployed",
            "deployed satellites", "reaches orbit", "reached orbit", "placed in orbit",
            "inserted into orbit", "constellation deployment", "fcc license",
            "direct to cell", "direct-to-cell", "into orbit", "launches satellites",
            "launched satellites", "deploys satellites"
        ],
        "direction": "BULLISH",
        "importance": "HIGH"
    },
    "LAUNCH": {
        "keywords": [
            "launch", "launches", "launching", "test launch", "orbital launch",
            "rocket launch", "satellite launch", "space launch", "boca chica",
            "electron rocket", "neutron rocket", "starship", "lift off", "liftoff"
        ],
        "direction": "BULLISH",
        "importance": "HIGH"
    },
    "FAA_APPROVAL": {
        "keywords": ["faa license", "faa approval", "environmental review", "launch license", "cleared for launch"],
        "direction": "BULLISH",
        "importance": "HIGH"
    },
    "GOVERNMENT_CONTRACT": {
        "keywords": ["government contract", "defense contract", "sda contract", "military contract", "federal contract"],
        "direction": "BULLISH",
        "importance": "CRITICAL"
    },
    "PARTNERSHIP": {
        "keywords": ["partnership", "mno", "partner", "agreement", "collaboration", "verizon", "at&t"],
        "direction": "BULLISH",
        "importance": "HIGH"
    },
    "REVENUE": {
        "keywords": [
            "revenue beat", "revenue beats", "earnings beat", "earnings beats",
            "guidance beat", "record revenue", "record sales", "revenue surge",
            "revenue surges", "profitable quarter", "profit beats", "revenue growth",
            "revenue grows", "arr growth"
        ],
        "direction": "BULLISH",
        "importance": "MEDIUM"
    },
    "TECHNICAL_MILESTONE": {
        "keywords": ["hot fire", "engine test", "fairing", "stage 1", "milestone", "payload", "qualification"],
        "direction": "BULLISH",
        "importance": "MEDIUM"
    },
    "CAPITAL_RAISE": {
        "keywords": [
            "dilution", "share offering", "shares offering", "public offering",
            "common stock offering", "direct offering", "secondary offering",
            "registered direct", "registered direct offering", "equity offering",
            "convertible notes", "convertible senior notes", "convertible debt",
            "convertible debentures", "notes offering", "prices convertible notes",
            "prices offering", "prices public offering", "at-the-market",
            "at the market", "atm offering", "atm facility", "atm program",
            "atm sales", "atm agreement", "capital raise", "cash burn",
            "debt offering", "private placement", "pipe financing", "pipe offering"
        ],
        "direction": "BEARISH",
        "importance": "HIGH"
    },
    "LAUNCH_FAILURE": {
        "keywords": [
            "launch failure", "failed launch", "explosion", "exploded", "exploding",
            "rud", "rapid unscheduled disassembly", "lost vehicle", "mission failure",
            "payload lost", "booster lost", "crash", "crashed", "engine failure"
        ],
        "direction": "BEARISH",
        "importance": "CRITICAL"
    },
    "LAUNCH_DELAY": {
        "keywords": [
            "launch delay", "launch delays", "delay", "delayed", "delays",
            "rescheduled", "postponed", "launch abort", "anomaly", "scrubbed",
            "scrub", "grounded", "launch hold", "countdown hold",
            "countdown on hold", "pad hold"
        ],
        "direction": "BEARISH",
        "importance": "HIGH"
    },
    "ANALYST_DOWNGRADE": {
        "keywords": ["downgrade", "underweight", "sell rating", "price target cut"],
        "direction": "BEARISH",
        "importance": "MEDIUM"
    }
}


def calculate_engagement_score(likes: int, reposts: int, replies: int, views: int) -> float:
    """
    Calculate log-scaled engagement score:
    engagement = log1p(likes + 2*reposts + 1.5*replies + views/1000)
    """
    normalized_views = float(views) / 1000.0 if views else 0.0
    weighted_sum = float(likes) + 2.0 * float(reposts) + 1.5 * float(replies) + normalized_views
    return math.log1p(weighted_sum)


def calculate_recency_weight(created_at: datetime, reference_now: Optional[datetime] = None, half_life_hours: float = 12.0) -> float:
    """
    Exponential decay weight based on age in hours.
    weight = exp(-lambda * age_hours)
    """
    created_at_utc = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at.astimezone(timezone.utc)
    
    if reference_now is not None:
        now_utc = reference_now.replace(tzinfo=timezone.utc) if reference_now.tzinfo is None else reference_now.astimezone(timezone.utc)
    else:
        now_utc = datetime.now(timezone.utc)

    age_seconds = max(0.0, (now_utc - created_at_utc).total_seconds())
    age_hours = age_seconds / 3600.0
    
    decay_lambda = math.log(2.0) / half_life_hours
    weight = math.exp(-decay_lambda * age_hours)
    return round(weight, 4)


def calculate_relevance_score(text: str, symbol: str, aliases: List[str]) -> float:
    """
    Calculates relevance score from 0.0 to 1.0 based on keyword match.
    """
    clean_text = text.lower()
    
    # Exact ticker match with $ prefix
    if f"${symbol.lower()}" in clean_text:
        return 1.0
        
    # Check aliases
    for alias in aliases:
        if alias.lower() in clean_text:
            return 0.85
            
    # Standalone symbol match
    if re.search(r'\b' + re.escape(symbol.lower()) + r'\b', clean_text):
        return 0.75

    # Secondary space terms alone without ticker/alias do not meet min relevance threshold (P1.4 audit fix)
    space_generic = ["satellite", "orbit", "space", "launch", "rocket"]
    if any(g in clean_text for g in space_generic):
        return 0.25

    return 0.10


IMPORTANCE_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# Semantic entity and action lexicons for contextual catalyst resolution
# Semantic entity and action lexicons for contextual catalyst resolution
GOV_AGENCIES = [
    "nasa", "space force", "dod", "pentagon", "sda", "usaf", "darpa", "nro",
    "department of defense", "defense department", "space development agency"
]
CONTRACT_TERMS = ["contract", "contracts", "agreement", "agreements", "task order", "award", "awards", "awarded", "procurement", "grant", "deal"]

CONTRACT_CANCELLATION_PATTERNS = [
    # cancel/cancelled/cancelling contract/award/deal
    r"\b(?:cancels?|cancelled|canceled|canceling|cancelling|cancellation)\b(?:\s+\w+){0,4}\s+\b(?:contract|award|task\s+order|agreement|deal|grant)\b",
    r"\b(?:contract|award|task\s+order|agreement|deal|grant)\b(?:\s+\w+){0,4}\s+\b(?:cancelled|canceled|canceling|cancelling|cancellation)\b",
    # terminate/terminated contract/award/deal
    r"\b(?:terminates?|terminated|terminating|termination)\b(?:\s+\w+){0,4}\s+\b(?:contract|award|task\s+order|agreement|deal)\b",
    r"\b(?:contract|award|task\s+order|agreement|deal)\b(?:\s+\w+){0,4}\s+\b(?:terminated|termination)\b",
    # revoke/rescind/scrap contract
    r"\b(?:revokes?|revoked|revoking|rescinds?|rescinded|rescinding|scraps?|scrapped|scrapping)\b(?:\s+\w+){0,4}\s+\b(?:contract|award|task\s+order|deal)\b",
    r"\b(?:contract|award|task\s+order|deal)\b(?:\s+\w+){0,4}\s+\b(?:revoked|rescinded|scrapped)\b",
    # loses/lost contract/award/deal
    r"\b(?:lost|loses|losing)\b(?:\s+\w+){0,3}\s+\b(?:contract|award|deal)\b",
    # loss of contract/award
    r"\b(?:loss\s+of)\s+(?:the\s+|a\s+|its\s+)?(?:contract|award|deal)\b",
    # dropped/cut from contract/program
    r"\b(?:dropped\s+from|cut\s+from)\s+(?:the\s+|a\s+)?(?:contract|program|award)\b"
]

PARTNERSHIP_CANCELLATION_PATTERNS = [
    r"\b(?:cancels?|cancelled|canceled|canceling|cancelling|cancellation)\b(?:\s+\w+){0,4}\s+\b(?:partnership|collaboration|agreement|mou|mno\s+deal)\b",
    r"\b(?:partnership|collaboration|agreement|mou|mno\s+deal)\b(?:\s+\w+){0,4}\s+\b(?:cancelled|canceled|canceling|cancelling|cancellation)\b",
    r"\b(?:terminates?|terminated|terminating|termination)\b(?:\s+\w+){0,4}\s+\b(?:partnership|collaboration|agreement|mou)\b",
    r"\b(?:partnership|collaboration|agreement|mou)\b(?:\s+\w+){0,4}\s+\b(?:terminated|termination)\b",
    r"\b(?:dissolves?|dissolved|dissolving|ends?|ended|ending)\b(?:\s+\w+){0,3}\s+\b(?:partnership|collaboration|agreement)\b",
    r"\b(?:drops?|dropped|dropping)\b(?:\s+\w+){0,3}\s+\b(?:partner|partnership)\b"
]

FAA_DENIAL_PATTERNS = [
    r"\bdeni(es|ed)\b",
    r"\breject(s|ed|ing)?\b",
    r"\bgrounds?\b",
    r"\brevok(es|ed|ing)\b",
    r"\bsuspend(s|ed|ing)?\b"
]

FIGURATIVE_EXPLOSION_PATTERNS = [
    r"\bexplosions?\s+(?:of|in)\s+(?:demand|growth|interest|sales|activity|volume|revenue|users|orders|popularity|traffic|capacity)\b",
    r"\b(?:demand|growth|interest|sales|popularity|revenue|activity)\s+exploded\b",
    r"\bexploded\s+(?:in\s+popularity|higher|onto\s+the\s+scene)\b"
]

FINANCIAL_CRASH_PATTERNS = [
    r"\b(?:stock|shares?|market|price|valuation|equity)\s+crash(?:es|ed)?\b",
    r"\bcrash(?:es|ed)?\s+(?:after\s+earnings|post-earnings|following\s+earnings|in\s+trading|on\s+results|on\s+guidance)\b",
    r"\b(?:crashed|crashing)\s+(?:\d+%\s+|over\s+\d+%\s+|more\s+than\s+\d+%\s+)?(?:after|following|on|today|yesterday|this\s+week)\b",
    r"\bcrash(?:es|ed)?\s+\d+%\b"
]

ANALYST_HOLD_PATTERNS = [
    r"\b(?:analysts?|firm|wall\s+street|brokerage)\s+(?:keeps?|maintains?|reiterates?|initiates?|has)\s+(?:a\s+)?hold\b",
    r"\bhold\s+rating\b",
    r"\brated\s+hold\b",
    r"\bhold\s+recommendation\b",
    r"\bkeep\s+hold\b"
]

EARNINGS_NEGATIVE_PATTERNS = [
    r"\b(?:net\s+loss|loss\s+widens?|miss(?:es|ed)?\s+(?:earnings|revenue|estimates|expectations)|quarterly\s+loss)\b"
]

HYPOTHETICAL_PATTERNS = [
    r"^\s*(?:what\s+if|could|would|might|hypothetically)\b",
    r"\b(?:what\s+if|speculation:|rumor:|unconfirmed:|hypothetical)\b"
]

HISTORICAL_PATTERNS = [
    r"\b(?:in\s+(?:19\d\d|20[01]\d|202[0-3])|years\s+ago|historically|in\s+the\s+past|back\s+in\s+(?:19\d\d|20\d\d)|anniversary\s+of)\b"
]

NON_AEROSPACE_LAUNCH_PATTERNS = [
    # Offerings & Capital raises: "launches $500M share offering", "launches notes offering"
    r"\blaunch(?:es|ed|ing)?\s+(?:(?:\$\d+[bmk]?|\d+\s*(?:million|billion))\s+)?(?:share|shares|public|equity|debt|notes?|atm|direct|stock|token|coin)\s+offering\b",
    r"\blaunch(?:es|ed|ing)?\s+(?:a\s+|an\s+|the\s+)?(?:tender\s+offer|share\s+buyback|stock\s+offering|notes?\s+offering|debt\s+offering|equity\s+offering|capital\s+raise)\b",
    # Commercial products, consumer apps, services, stores, brands, platforms
    r"\blaunch(?:es|ed|ing)?\s+(?:a\s+|an\s+|the\s+|new\s+|its\s+|their\s+)?(?:product|products|product\s+line|service|services|platform|platforms|app|apps|application|applications|feature|features|initiative|initiatives|store|stores|brand|brands|program|programs|fund|etf|website|tool|tools|subscription|subscriptions|campaign|campaigns|tier|tiers)\b",
    # Legal / regulatory investigations
    r"\blaunch(?:es|ed|ing)?\s+(?:a\s+|an\s+|the\s+|new\s+|its\s+|their\s+)?(?:investigation|investigations|inquiry|inquiries|probe|probes|lawsuit|lawsuits|audit|audits|review|proxy\s+fight|takeover\s+bid)\b",
]

AEROSPACE_CONTEXT_TERMS = {
    "rocket", "rockets", "spacecraft", "booster", "boosters", "capsule",
    "orbit", "orbital", "suborbital", "pad", "launchpad", "spaceport",
    "payload", "payloads", "satellite", "satellites", "constellation", "mission",
    "missions", "lift off", "liftoff", "blast off", "countdown", "stage 1", "stage 2",
    "fairing", "electron", "neutron", "falcon", "starship", "vulcan", "new glenn",
    "terran", "h3", "ariane", "antares", "boca chica", "cape canaveral", "vandenberg",
    "wallops", "kennedy space center", "ksc", "space force", "iss", "moon", "lunar",
    "mars", "astronaut", "astronauts", "space flight", "spaceflight"
}

CATALYST_NEGATION_WORDS = [
    "not", "no", "never", "without", "hardly", "barely", "scarcely",
    "don't", "dont", "doesn't", "doesnt", "didn't", "didnt",
    "won't", "wont", "can't", "cant", "cannot", "couldn't", "couldnt",
    "wouldn't", "wouldnt", "shouldn't", "shouldnt", "isn't", "isnt",
    "aren't", "arent", "wasn't", "wasnt", "weren't", "werent",
    "neither", "nor", "rules out", "ruled out", "denies", "denied", "zero"
]

CATALYST_AFFIRMATIVE_IDIOMS = [
    "no doubt", "without doubt", "without a doubt",
    "no question", "without question", "no wonder", "no surprise"
]


def is_catalyst_negated(kw: str, clean_text: str) -> bool:
    """
    Returns True if all occurrences of keyword kw in clean_text are preceded by
    a genuine negation within 0-2 intervening words without breaking punctuation.
    """
    temp_text = clean_text
    for idiom in CATALYST_AFFIRMATIVE_IDIOMS:
        temp_text = re.sub(r'\b' + re.escape(idiom) + r'\b', '__AFFIRMED__', temp_text)

    kw_re = re.compile(r'\b' + re.escape(kw) + r'\b')
    kw_matches = list(kw_re.finditer(temp_text))
    if not kw_matches:
        return False

    neg_words_pattern = r'\b(?:' + '|'.join(re.escape(nw) for nw in CATALYST_NEGATION_WORDS) + r')\b'

    for m in kw_matches:
        start_pos = m.start()
        prefix = temp_text[max(0, start_pos - 50):start_pos]
        neg_search = re.search(neg_words_pattern + r'(?:\s+[a-z0-9\'-]+){0,2}\s*$', prefix)
        if neg_search:
            segment = prefix[neg_search.start():]
            if any(punct in segment for punct in ['.', ';', '!', '?', ',', ':', '-', '—', '(', ')']):
                return False
            continue
        else:
            return False

    return True


def detect_catalysts(
    text: str,
    ticker: Optional[str] = None,
    include_hypothetical: bool = True,
    include_historical: bool = True
) -> List[Dict[str, Any]]:
    """
    Detects all matching market catalysts, decoupling entity mentions from event predicates,
    resolving negation, cancellation, competitor rivalry, and filtering out hypothetical/historical noise.
    Returns a list of dicts sorted by importance hierarchy:
    [{"category": cat, "direction": dir, "importance": imp, "keyword": kw, ...}, ...]
    """
    clean_text = text.lower()
    matches: List[Dict[str, Any]] = []
    seen_categories = set()

    # 1. Detect if the text represents a purely speculative/hypothetical question
    is_hypo = any(re.search(p, clean_text) for p in HYPOTHETICAL_PATTERNS) or (
        clean_text.endswith("?") and any(re.search(rf"\b{w}\b", clean_text) for w in ["what if", "could", "might", "would", "is it possible"])
    )

    # 2. Detect if the text is historical retrospect (e.g. event from years ago)
    is_hist = any(re.search(p, clean_text) for p in HISTORICAL_PATTERNS)

    # 3. Detect inter-company competitor rivalry (e.g. "NASA selects SpaceX over Rocket Lab", "Rocket Lab beats SpaceX")
    winner = None
    defeated = None

    # Pattern A: "selects/wins/awarded [winner] over [defeated]"
    m_selects = re.search(r'\b(?:wins?|awarded|selects?|selected|picks?|picked|choos(?:es|ing)|chosen)\s+([a-z0-9\s]+?)\s+(?:over|instead of|against|beating)\s+([a-z0-9\s]+?)(?:\s+(?:for|on|in|to|with)\b|[.,;]|$)', clean_text)
    if m_selects:
        winner = m_selects.group(1).strip()
        defeated = m_selects.group(2).strip()
    else:
        # Pattern B: "[winner] beats/defeats/outcompetes [defeated]"
        m_beats = re.search(r'\b([a-z0-9\s]+?)\s+(?:beats?|defeats?|outcompetes?)\s+([a-z0-9\s]+?)(?:\s+(?:for|on|in|to|with)\b|[.,;]|$)', clean_text)
        if m_beats:
            cand_defeated = m_beats.group(2).strip().lower()
            financial_beat_terms = (
                "earnings", "estimates", "expectations", "guidance", "consensus",
                "forecasts", "wall street", "analysts", "projections", "targets",
                "revenue", "loss", "profit", "views", "q1", "q2", "q3", "q4"
            )
            if not any(cand_defeated == term or cand_defeated.startswith(term + " ") for term in financial_beat_terms):
                winner = m_beats.group(1).strip()
                defeated = m_beats.group(2).strip()

    if winner and defeated:
        def _match_phrase(phrase: str, target: Optional[str]) -> bool:
            if not target or not phrase:
                return False
            t = target.lower().strip()
            p = phrase.lower()
            if re.search(r'\b' + re.escape(t) + r'\b', p):
                return True
            alias_map = {
                "rklb": ["rocket lab", "rklb", "electron", "neutron"],
                "asts": ["ast spacemobile", "ast spacemobile inc", "spacemobile", "asts", "bluebird", "ast"],
                "lunr": ["intuitive machines", "lunr", "nova-c"],
                "spcx": ["spacex", "spcx", "starship", "falcon"],
                "bksy": ["blacksky", "bksy"],
                "pl": ["planet labs", "planet labs pbc", "planet labs inc", "planet", "pl"],
                "rdw": ["redwire", "redwire space", "rdw"],
                "mnts": ["momentus", "mnts"],
                "llap": ["terran orbital", "llap"]
            }
            for alias in alias_map.get(t, []):
                if re.search(r'\b' + re.escape(alias) + r'\b', p):
                    return True
            return False

        is_target_winner = _match_phrase(winner, ticker)
        is_target_defeated = _match_phrase(defeated, ticker)

        if is_target_winner:
            matches.append({
                "category": "GOVERNMENT_CONTRACT",
                "direction": "BULLISH",
                "importance": "CRITICAL",
                "keyword": f"beat competitor {defeated}"
            })
            seen_categories.add("GOVERNMENT_CONTRACT")
        elif is_target_defeated or not ticker:
            matches.append({
                "category": "GOVERNMENT_CONTRACT",
                "direction": "BEARISH",
                "importance": "CRITICAL",
                "keyword": f"competitor {winner} selected over {defeated}"
            })
            seen_categories.add("GOVERNMENT_CONTRACT")

    # 4. Government contract detection with contextual entity & cancellation decoupling
    has_contract_cancellation = any(re.search(p, clean_text) for p in CONTRACT_CANCELLATION_PATTERNS)
    has_gov_entity = any(re.search(rf"\b{re.escape(g)}\b", clean_text) for g in GOV_AGENCIES)
    has_contract_noun = any(re.search(rf"\b{re.escape(c)}\b", clean_text) for c in CONTRACT_TERMS)
    has_direct_gov_phrase = any(re.search(rf"\b{re.escape(p)}\b", clean_text) for p in [
        "government contract", "defense contract", "sda contract", "military contract", "federal contract"
    ])

    has_partner_cancel = any(re.search(p, clean_text) for p in PARTNERSHIP_CANCELLATION_PATTERNS)
    has_partner_kw = any(re.search(rf"\b{re.escape(kw)}\b", clean_text) for kw in CATALYST_CONFIG["PARTNERSHIP"]["keywords"])

    if "GOVERNMENT_CONTRACT" not in seen_categories:
        is_gov = (
            has_direct_gov_phrase
            or (has_gov_entity and (has_contract_noun or has_contract_cancellation))
            or (has_contract_noun and has_contract_cancellation and not has_partner_cancel and not (has_partner_kw and not has_gov_entity))
        )
        if is_gov:
            if has_contract_cancellation:
                matches.append({
                    "category": "GOVERNMENT_CONTRACT",
                    "direction": "BEARISH",
                    "importance": "CRITICAL",
                    "keyword": "cancels contract"
                })
                seen_categories.add("GOVERNMENT_CONTRACT")
            else:
                matches.append({
                    "category": "GOVERNMENT_CONTRACT",
                    "direction": "BULLISH",
                    "importance": "CRITICAL",
                    "keyword": "government contract"
                })
                seen_categories.add("GOVERNMENT_CONTRACT")

    # 5. Partnership detection with cancellation handling
    if "PARTNERSHIP" not in seen_categories:
        has_partnership_kw = any(re.search(rf"\b{re.escape(kw)}\b", clean_text) for kw in CATALYST_CONFIG["PARTNERSHIP"]["keywords"])
        if has_partnership_kw:
            has_partner_cancel = any(re.search(p, clean_text) for p in PARTNERSHIP_CANCELLATION_PATTERNS)
            if has_partner_cancel:
                matches.append({
                    "category": "PARTNERSHIP",
                    "direction": "BEARISH",
                    "importance": "HIGH",
                    "keyword": "partnership cancelled/terminated"
                })
                seen_categories.add("PARTNERSHIP")
            else:
                matches.append({
                    "category": "PARTNERSHIP",
                    "direction": "BULLISH",
                    "importance": "HIGH",
                    "keyword": "partnership"
                })
                seen_categories.add("PARTNERSHIP")

    # 6. FAA Approval detection with denial/grounding handling
    if "FAA_APPROVAL" not in seen_categories:
        has_faa_kw = any(re.search(rf"\b{re.escape(kw)}\b", clean_text) for kw in CATALYST_CONFIG["FAA_APPROVAL"]["keywords"])
        if has_faa_kw:
            if any(re.search(p, clean_text) for p in FAA_DENIAL_PATTERNS):
                matches.append({
                    "category": "FAA_APPROVAL",
                    "direction": "BEARISH",
                    "importance": "HIGH",
                    "keyword": "faa denial/grounding"
                })
                seen_categories.add("FAA_APPROVAL")
            else:
                matches.append({
                    "category": "FAA_APPROVAL",
                    "direction": "BULLISH",
                    "importance": "HIGH",
                    "keyword": "faa approval"
                })
                seen_categories.add("FAA_APPROVAL")

    # 7. Technical Milestone detection with test failure handling
    if "TECHNICAL_MILESTONE" not in seen_categories:
        has_milestone_kw = any(re.search(rf"\b{re.escape(kw)}\b", clean_text) for kw in CATALYST_CONFIG["TECHNICAL_MILESTONE"]["keywords"])
        if has_milestone_kw:
            is_fig_exp = any(re.search(p, clean_text) for p in FIGURATIVE_EXPLOSION_PATTERNS)
            exp_failure = any(re.search(p, clean_text) for p in [r"\bexplosion\b", r"\bexplod(ed|ing)\b"]) and not is_fig_exp
            if any(re.search(p, clean_text) for p in [r"\bfail(ed|ure|s)?\b", r"\banomaly\b"]) or exp_failure:
                matches.append({
                    "category": "TECHNICAL_MILESTONE",
                    "direction": "BEARISH",
                    "importance": "HIGH",
                    "keyword": "milestone test failure"
                })
                seen_categories.add("TECHNICAL_MILESTONE")
            else:
                matches.append({
                    "category": "TECHNICAL_MILESTONE",
                    "direction": "BULLISH",
                    "importance": "MEDIUM",
                    "keyword": "technical milestone"
                })
                seen_categories.add("TECHNICAL_MILESTONE")

    # 8. Match remaining categories from CATALYST_CONFIG
    # Prioritize risk-critical categories (LAUNCH_FAILURE, LAUNCH_DELAY) ahead of generic categories (LAUNCH)
    remaining_categories = [
        cat for cat in ["LAUNCH_FAILURE", "LAUNCH_DELAY", "CAPITAL_RAISE", "ANALYST_DOWNGRADE", "SATELLITE_DEPLOYMENT", "REVENUE", "LAUNCH"]
        if cat in CATALYST_CONFIG and cat not in seen_categories
    ]
    for cat in CATALYST_CONFIG:
        if cat not in seen_categories and cat not in remaining_categories and cat not in ["GOVERNMENT_CONTRACT", "PARTNERSHIP", "FAA_APPROVAL", "TECHNICAL_MILESTONE"]:
            remaining_categories.append(cat)

    for category in remaining_categories:
        if category in seen_categories:
            continue
        # If launch failure, delay, or capital raise was detected, suppress generic bullish LAUNCH
        if category == "LAUNCH" and ("LAUNCH_FAILURE" in seen_categories or "LAUNCH_DELAY" in seen_categories or "CAPITAL_RAISE" in seen_categories):
            continue

        # Suppress bullish REVENUE if earnings report indicates net loss or earnings miss
        if category == "REVENUE" and any(re.search(p, clean_text) for p in EARNINGS_NEGATIVE_PATTERNS):
            continue

        config = CATALYST_CONFIG[category]
        for kw in config["keywords"]:
            # Guard against negated catalyst keywords across all categories
            if is_catalyst_negated(kw, clean_text):
                continue

            # Guard against figurative explosion idioms (e.g. "explosion of demand")
            if category == "LAUNCH_FAILURE" and kw in ("explosion", "exploded", "exploding"):
                if any(re.search(p, clean_text) for p in FIGURATIVE_EXPLOSION_PATTERNS):
                    continue

            # Guard against financial stock crashes (e.g. "stock crash after earnings")
            if category == "LAUNCH_FAILURE" and kw in ("crash", "crashed"):
                if any(re.search(p, clean_text) for p in FINANCIAL_CRASH_PATTERNS):
                    continue

            # Guard against analyst equity hold ratings (e.g. "analysts keep hold rating")
            if category == "LAUNCH_DELAY" and kw in ("hold", "launch hold", "countdown hold", "pad hold"):
                if any(re.search(p, clean_text) for p in ANALYST_HOLD_PATTERNS):
                    continue

            # Guard against non-aerospace launches and require space context for bare launch verbs
            if category == "LAUNCH":
                if kw in ("launch", "launches", "launching", "launched"):
                    if any(re.search(p, clean_text) for p in NON_AEROSPACE_LAUNCH_PATTERNS):
                        continue
                    if not any(re.search(rf"\b{re.escape(term)}\b", clean_text) for term in AEROSPACE_CONTEXT_TERMS):
                        continue

            kw_pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(kw_pattern, clean_text):
                matches.append({
                    "category": category,
                    "direction": config["direction"],
                    "importance": config["importance"],
                    "keyword": kw
                })
                seen_categories.add(category)
                break

    # Ensure mutually exclusive launch events: LAUNCH_FAILURE, LAUNCH_DELAY, and CAPITAL_RAISE supersede generic LAUNCH
    if any(m["category"] in ("LAUNCH_FAILURE", "LAUNCH_DELAY", "CAPITAL_RAISE") for m in matches):
        matches = [m for m in matches if m["category"] != "LAUNCH"]

    # 10. Apply hypothetical and historical qualifiers
    final_matches = []
    for m in matches:
        m_copy = dict(m)
        if is_hypo:
            m_copy["is_hypothetical"] = True
            m_copy["importance"] = "LOW"
        if is_hist:
            m_copy["is_historical"] = True
            m_copy["importance"] = "LOW"

        if is_hypo and not include_hypothetical:
            continue
        if is_hist and not include_historical:
            continue
        final_matches.append(m_copy)

    # 11. Sort by:
    # 1) Importance hierarchy (CRITICAL first, then HIGH, etc.)
    # 2) Polar risk on tie (BEARISH before BULLISH)
    # 3) Specificity on tie (longer keyword first)
    final_matches.sort(
        key=lambda c: (
            IMPORTANCE_RANK.get(c["importance"], 99),
            0 if c["direction"] == "BEARISH" else 1,
            -len(c.get("keyword", ""))
        )
    )
    return final_matches


def detect_catalyst(text: str, ticker: Optional[str] = None) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Detect highest-priority market catalyst in the text based on importance hierarchy.
    Excludes hypothetical or historical retrospective statements from actionable alerts.
    Returns (catalyst_category, direction, importance)
    """
    all_cats = detect_catalysts(text, ticker=ticker, include_hypothetical=False, include_historical=False)
    if not all_cats:
        return None, None, None
    top = all_cats[0]
    return top["category"], top["direction"], top["importance"]


def calculate_news_score(
    news_items: List[Any],
    analysis_timestamp: Optional[datetime] = None,
    half_life_hours: float = 24.0
) -> Dict[str, Any]:
    """
    Computes aggregated News Score (0 to 100) from recent news articles.
    Filters articles by settings.NEWS_MIN_RELEVANCE (default 0.40).
    Dynamically recalculates recency weight relative to analysis_timestamp.
    Returns news_score = None when no relevant news items exist (Adaptive weight normalization).
    """
    if not news_items:
        return {
            "news_score": None,
            "total_news": 0,
            "bullish_news_pct": 0.0,
            "bearish_news_pct": 0.0
        }

    if analysis_timestamp is None:
        analysis_timestamp = datetime.now(timezone.utc)

    min_rel = getattr(settings, "NEWS_MIN_RELEVANCE", 0.40)
    relevant_items = [
        item for item in news_items
        if getattr(item, "relevance_score", 1.0) is None or getattr(item, "relevance_score", 1.0) >= min_rel
    ]

    if not relevant_items:
        return {
            "news_score": None,
            "total_news": 0,
            "bullish_news_pct": 0.0,
            "bearish_news_pct": 0.0
        }

    total_weight = 0.0
    weighted_sentiment_sum = 0.0
    bull_cnt = 0
    bear_cnt = 0

    for item in relevant_items:
        # Importance weighting multiplier
        imp_mult = 1.0
        if getattr(item, 'catalyst_importance', None) == "CRITICAL":
            imp_mult = 2.0
        elif getattr(item, 'catalyst_importance', None) == "HIGH":
            imp_mult = 1.5

        # Recency decay for news (half-life 24 hours, dynamic from analysis_timestamp)
        pub_at = getattr(item, "published_at", None)
        if pub_at is not None:
            rec_w = calculate_recency_weight(pub_at, reference_now=analysis_timestamp, half_life_hours=half_life_hours)
        else:
            rec_w = getattr(item, "recency_weight", 1.0) or 1.0

        rel_score = getattr(item, 'relevance_score', 1.0) if getattr(item, 'relevance_score', 1.0) is not None else 1.0
        conf_score = getattr(item, 'sentiment_confidence', 1.0) if getattr(item, 'sentiment_confidence', 1.0) is not None else 1.0
        w = rel_score * rec_w * conf_score * imp_mult
        
        total_weight += w
        weighted_sentiment_sum += getattr(item, 'sentiment_score', 0.0) * w

        if getattr(item, 'sentiment_label', None) == "BULLISH":
            bull_cnt += 1
        elif getattr(item, 'sentiment_label', None) == "BEARISH":
            bear_cnt += 1

    if total_weight <= 0:
        return {
            "news_score": None,
            "total_news": len(relevant_items),
            "bullish_news_pct": 0.0,
            "bearish_news_pct": 0.0
        }

    norm_sent = weighted_sentiment_sum / total_weight
    raw_news_score = 50.0 + (50.0 * norm_sent)
    news_score = max(0.0, min(100.0, round(raw_news_score, 1)))

    n_total = len(relevant_items)
    return {
        "news_score": news_score,
        "total_news": n_total,
        "bullish_news_pct": round(100.0 * bull_cnt / n_total, 1),
        "bearish_news_pct": round(100.0 * bear_cnt / n_total, 1)
    }
