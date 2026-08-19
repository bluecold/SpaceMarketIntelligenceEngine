import random
from datetime import datetime, timedelta
from typing import List
from app.collectors.base import XProvider, SocialPostData

MOCK_TEMPLATES = {
    "ASTS": [
        ("SpaceMobile_Fan", "ASTS BlueBird satellite deployment milestone confirmed by FCC! Massive coverage expansion. $ASTS 🚀", "BULLISH", "SATELLITE_DEPLOYMENT"),
        ("TechTrader_99", "AST SpaceMobile signing new MNO partner agreement soon. Huge recurring revenue potential.", "BULLISH", "PARTNERSHIP"),
        ("SatCom_Analyst", "ASTS price action looking strong after breaking resistance. High volume accumulation.", "BULLISH", "TECHNICAL_MILESTONE"),
        ("BearishShorts", "AST SpaceMobile valuation looks stretched here. Potential dilution risk ahead? $ASTS", "BEARISH", "DILUTION"),
        ("SpaceInvestor", "Holding ASTS long term, cellular broadband directly to unmodified smartphones is a gamechanger.", "BULLISH", "PRODUCT")
    ],
    "RKLB": [
        ("RocketFanatic", "Rocket Lab Electron launch #50 success! Archimedes engine hot fire tests progressing smoothly. $RKLB", "BULLISH", "LAUNCH"),
        ("AeroQuant", "RKLB government contract win for satellite constellation payload defense. $45M value.", "BULLISH", "GOVERNMENT_CONTRACT"),
        ("MarketTrader", "Rocket Lab quarterly revenue growth +35% YoY. Neutron development on track for 2026.", "BULLISH", "REVENUE"),
        ("SpaceBear", "RKLB launch delay reported due to weather and range availability.", "BEARISH", "LAUNCH_DELAY"),
        ("GalacticInvestor", "Neutron rocket stage 1 fairing test completed. Rocket Lab building serious medium-lift competitor.", "BULLISH", "TECHNICAL_MILESTONE")
    ],
    "SATL": [
        ("GeoSpatial_Pro", "Satellogic launching 4 new high-res Earth observation satellites with SpaceX. $SATL", "BULLISH", "LAUNCH"),
        ("SatlTrader", "SATL new enterprise partnership for agriculture mapping data.", "BULLISH", "PARTNERSHIP"),
        ("SmallCapPicks", "Satellogic volume spiking on government remote sensing agreement announcement.", "BULLISH", "GOVERNMENT_CONTRACT")
    ],
    "SPCE": [
        ("GalacticFlyer", "Virgin Galactic flight schedule updated. Commercial flights continuing space tourism ops. $SPCE", "BULLISH", "PRODUCT"),
        ("ShortSeller_X", "Virgin Galactic cash burn rate remains high. Dilution risk is real for SPCE.", "BEARISH", "CAPITAL_RAISE"),
        ("AeroNews", "SPCE analyst downgrade to underweight following quarterly guidance revision.", "BEARISH", "ANALYST_DOWNGRADE")
    ],
    "SPCX": [
        ("StarshipTracker", "SpaceX Starship orbital test launch prep underway in Boca Chica! $SPCX", "BULLISH", "LAUNCH"),
        ("StarlinkUser", "Starlink subscriber count passes 4 Million worldwide. Massive revenue milestone.", "BULLISH", "REVENUE"),
        ("SpaceXWatch", "SpaceX contract win with NASA for Artemis moon lander payload module.", "BULLISH", "GOVERNMENT_CONTRACT")
    ]
}


class MockXProvider(XProvider):
    async def search(self, query: str, ticker: str, max_results: int = 100) -> List[SocialPostData]:
        posts = []
        templates = MOCK_TEMPLATES.get(ticker, MOCK_TEMPLATES["ASTS"])
        
        count = min(max_results, random.randint(15, 30))
        now = datetime.utcnow()

        for i in range(count):
            user, text, label, catalyst = random.choice(templates)
            age_minutes = random.randint(5, 1400) # within last 24h
            created_at = now - timedelta(minutes=age_minutes)
            tweet_id = f"mock_{ticker.lower()}_{int(created_at.timestamp())}_{i}"
            
            posts.append(SocialPostData(
                tweet_id=tweet_id,
                ticker=ticker,
                username=user,
                text=f"{text} (Ref: {i+100})",
                created_at=created_at,
                url=f"https://x.com/{user}/status/{tweet_id}",
                likes=random.randint(2, 450),
                reposts=random.randint(0, 120),
                replies=random.randint(0, 45),
                views=random.randint(150, 12000)
            ))
            
        return posts
