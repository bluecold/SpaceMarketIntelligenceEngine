import asyncio
import click
from app.config import settings, INITIAL_TICKERS
from app.jobs.runner import (
    run_full_pipeline, get_x_provider, get_polymarket_provider, get_news_provider,
    ingest_prediction_markets, ingest_social_posts_for_ticker, ingest_news_for_ticker,
    ingest_market_for_ticker
)
from app.collectors.market_provider import YFinanceMarketProvider
from app.database.connection import SessionLocal, init_db
from app.database.repository import (
    ensure_tickers_seeded, get_latest_ssi_snapshot, get_recent_social_posts,
    get_latest_market_snapshot, get_recent_prediction_markets,
    get_active_divergences
)
from app.sentiment.classifier import get_sentiment_classifier
from app.reports.daily_report import generate_daily_report
from app.backtesting.engine import run_historical_backtest


@click.group()
def cli():
    """Space Market Intelligence Engine (SMIE) CLI Tool"""
    pass


@cli.command()
def run_all():
    """Execute full pipeline for all space tickers."""
    click.echo(click.style("[SMIE] Starting full pipeline...", fg="cyan"))
    res = asyncio.run(run_full_pipeline(source="CLI"))
    if res.get("status") == "SUCCESS":
        click.echo(click.style("[SUCCESS] SMIE pipeline executed successfully!", fg="green"))
        for ticker, data in res.get("results", {}).items():
            click.echo(
                f"  [{ticker}] SMI: {data['smi']} | SSI: {data['ssi']} | "
                f"PMS: {data['pms'] or '--'} | Signal: {data['signal']} | "
                f"Confidence: {data['confidence']}%"
            )
    else:
        err_msg = res.get("error", "Pipeline execution failed")
        click.echo(click.style(f"[ERROR] {err_msg}", fg="red"))
        raise click.ClickException(str(err_msg))


@cli.command("collect-social")
def collect_social():
    """Collect social posts from X/Twitter."""
    click.echo("[SMIE] Collecting social posts from X...")
    async def _run():
        init_db()
        db = SessionLocal()
        try:
            ensure_tickers_seeded(db)
            x_provider = get_x_provider()
            sentiment_classifier = get_sentiment_classifier()
            total_added = 0
            for cfg in INITIAL_TICKERS:
                ticker = cfg.symbol
                added, clean_posts, _ = await ingest_social_posts_for_ticker(
                    db, cfg, x_provider=x_provider, sentiment_classifier=sentiment_classifier
                )
                total_added += added
                click.echo(f"  [{ticker}] Ingested {len(clean_posts)} posts ({added} new).")
            click.echo(click.style(f"[DONE] Social posts collected ({total_added} new saved).", fg="green"))
        finally:
            db.close()
    asyncio.run(_run())


@cli.command("collect-polymarket")
def collect_polymarket():
    """Collect prediction markets from Polymarket."""
    click.echo("[SMIE] Ingesting Polymarket prediction markets...")
    async def _run():
        init_db()
        db = SessionLocal()
        try:
            ensure_tickers_seeded(db)
            provider = get_polymarket_provider()
            markets = await ingest_prediction_markets(db, poly_provider=provider)
            click.echo(f"Retrieved and saved {len(markets)} space prediction markets.")
            for m in markets[:5]:
                click.echo(f"  - {m.title} (YES: {int(m.yes_probability*100)}%, Quality: {m.quality_score})")
        finally:
            db.close()
    asyncio.run(_run())


@cli.command("collect-news")
def collect_news():
    """Collect news articles from Google News RSS."""
    click.echo("[SMIE] Collecting space sector news...")
    async def _run():
        init_db()
        db = SessionLocal()
        try:
            ensure_tickers_seeded(db)
            news_provider = get_news_provider()
            sentiment_classifier = get_sentiment_classifier()
            total_added = 0
            for cfg in INITIAL_TICKERS:
                ticker = cfg.symbol
                added, clean_news, _ = await ingest_news_for_ticker(
                    db, cfg, news_provider=news_provider, sentiment_classifier=sentiment_classifier
                )
                total_added += added
                click.echo(f"  [{ticker}] Ingested {len(clean_news)} articles ({added} new).")
            click.echo(click.style(f"[DONE] News collection completed ({total_added} new saved).", fg="green"))
        finally:
            db.close()
    asyncio.run(_run())


@cli.command("collect-market")
def collect_market():
    """Collect market data & compute technical indicators."""
    click.echo("[SMIE] Collecting market data via yfinance...")
    async def _run():
        init_db()
        db = SessionLocal()
        try:
            ensure_tickers_seeded(db)
            market_provider = YFinanceMarketProvider()
            total_added = 0
            for cfg in INITIAL_TICKERS:
                ticker = cfg.symbol
                try:
                    indicators, _ = await ingest_market_for_ticker(db, cfg, market_provider=market_provider)
                    total_added += 1
                    price_val = indicators.get("price")
                    price_str = f"${price_val:.2f}" if price_val is not None else "N/A"
                    click.echo(f"  [{ticker}] Price: {price_str} | Status: {indicators.get('status')} | Tech Score: {indicators.get('technical_score') or '--'}")
                except Exception as e:
                    click.echo(click.style(f"  [{ticker}] Market collection error: {e}", fg="red"))
            click.echo(click.style(f"[DONE] Market indicators updated ({total_added} tickers).", fg="green"))
        finally:
            db.close()
    asyncio.run(_run())


@cli.command("calculate-smi")
def calculate_smi_cmd():
    """Calculate SMI, SSI, and PMS scores for all tickers."""
    click.echo("[SMIE] Calculating Space Market Intelligence scores...")
    init_db()
    res = asyncio.run(run_full_pipeline(source="CLI"))
    if res.get("status") == "SUCCESS":
        click.echo(click.style("[DONE] Scores & snapshots updated.", fg="green"))
    else:
        err_msg = res.get("error", "Pipeline calculation failed")
        click.echo(click.style(f"[ERROR] {err_msg}", fg="red"))
        raise click.ClickException(str(err_msg))


@cli.command("calculate-divergences")
def calculate_divergences_cmd():
    """Detect and evaluate tripartite divergences."""
    click.echo("[SMIE] Evaluating X ↔ Polymarket ↔ Price divergences...")
    init_db()
    db = SessionLocal()
    try:
        ensure_tickers_seeded(db)
        divs = get_active_divergences(db, hours=48)
        click.echo(f"Found {len(divs)} active divergences across sector:")
        for d in divs:
            click.echo(f"  [{d.ticker}] {d.type} ({d.direction}): {d.description}")
    finally:
        db.close()


@cli.command("daily-report")
def daily_report_cmd():
    """Generate and display the Space Market Intelligence Daily Report."""
    init_db()
    db = SessionLocal()
    try:
        ensure_tickers_seeded(db)
        rep = generate_daily_report(db)
        click.echo(rep["markdown_report"])
    finally:
        db.close()


@cli.command("backtest")
def backtest_cmd():
    """Run quantitative backtesting comparing Model A (X+Market) vs Model B (X+Market+Polymarket)."""
    click.echo(click.style("[SMIE] Running Quantitative Backtesting Engine...", fg="cyan"))
    init_db()
    db = SessionLocal()
    try:
        ensure_tickers_seeded(db)
        res = run_historical_backtest(db)
        click.echo(f"Total Snapshots Evaluated: {res['total_snapshots_analyzed']}")
        click.echo("==================================================")
        click.echo("MODEL COMPARISON (3-DAY HOLDING HORIZON):")
        click.echo("==================================================")
        
        h3 = res["evaluation_horizons"]["3D"]
        mA = h3["model_a_baseline"]["metrics"]
        mB = h3["model_b_multisource"]["metrics"]
        
        click.echo(f"Model A (X + Technical)           | Win Rate: {mA['win_rate']:>5.1f}% | Profit Factor: {mA['profit_factor']:>4.2f} | Sharpe: {mA['sharpe_ratio']:>4.2f}")
        click.echo(f"Model B (+ Polymarket PMS + News) | Win Rate: {mB['win_rate']:>5.1f}% | Profit Factor: {mB['profit_factor']:>4.2f} | Sharpe: {mB['sharpe_ratio']:>4.2f}")
        
        click.echo("--------------------------------------------------")
        hyp = h3["hypothesis_analysis"]
        click.echo(f"Polymarket Incremental Alpha: {click.style('CONFIRMED', fg='green') if hyp['polymarket_incremental_value'] else click.style('ACCUMULATING HISTORY', fg='yellow')}")
        click.echo(f"Win Rate Delta:               {hyp['win_rate_delta_pp']:+.1f} pp")
        click.echo(f"Profit Factor Delta:          {hyp['profit_factor_delta']:+.2f}")
        click.echo(f"Sharpe Ratio Delta:           {hyp['sharpe_delta']:+.2f}")
        click.echo("==================================================")
        click.echo(f"Summary: {res['summary_recommendation']}")
    finally:
        db.close()


@cli.command()
@click.argument('ticker')
def analyze(ticker):
    """Analyze single ticker and display complete intelligence summary."""
    ticker = ticker.upper()
    click.echo(f"[SMIE] Analyzing ticker {ticker}...")

    # Run pipeline to ensure fresh data
    init_db()
    res = asyncio.run(run_full_pipeline(source="CLI"))
    if res.get("status") != "SUCCESS":
        click.echo(click.style(f"[WARNING] Pipeline returned status {res.get('status')}: {res.get('error')}", fg="yellow"))

    db = SessionLocal()
    try:
        ensure_tickers_seeded(db)
        ssi_snap = get_latest_ssi_snapshot(db, ticker)
        mkt_snap = get_latest_market_snapshot(db, ticker)
        posts = get_recent_social_posts(db, ticker, hours=24)
        markets = get_recent_prediction_markets(db, ticker)
        divs = get_active_divergences(db, ticker, hours=48)

        if not ssi_snap:
            click.echo(click.style(f"No snapshot data found for {ticker}.", fg="yellow"))
            return

        click.echo("==================================================")
        click.echo(click.style(f"SPACE MARKET INTELLIGENCE ENGINE --- {ticker}", fg="cyan", bold=True))
        click.echo("==================================================")
        smi_val = ssi_snap.smi if ssi_snap.smi is not None else ssi_snap.ssi
        smi_str = f"{smi_val:.1f}" if smi_val is not None else "--"
        ssi_str = f"{ssi_snap.social_score:.1f}" if ssi_snap.social_score is not None else "--"
        pms_str = f"{ssi_snap.prediction_score:.1f}" if ssi_snap.prediction_score is not None else "--"
        conf_str = f"{ssi_snap.confidence:.1f}%" if ssi_snap.confidence is not None else "--"
        dq_val = ssi_snap.data_quality if ssi_snap.data_quality is not None else ssi_snap.data_completeness
        dq_str = f"{dq_val:.1f}%" if dq_val is not None else "--"
        mkt_str = f"{((ssi_snap.technical_score/40.0)*100.0):.1f}/100" if ssi_snap.technical_score is not None else "N/A"
        price_str = f"${ssi_snap.price:.2f}" if ssi_snap.price is not None else "N/A"

        click.echo(f"SMI (Market Intelligence Index): {smi_str} / 100")
        click.echo(f"SSI (Social Sentiment Index):    {ssi_str} / 100")
        click.echo(f"PMS (Prediction Market Score):   {pms_str} / 100")
        click.echo(f"Signal:                          {ssi_snap.signal}")
        click.echo(f"Confidence:                      {conf_str}")
        click.echo(f"Data Quality:                    {dq_str}")
        click.echo(f"Market Score:                    {mkt_str}")
        click.echo(f"Latest Price:                    {price_str}")
        click.echo(f"Social Posts (24h):              {len(posts)}")
        click.echo(f"Prediction Markets:              {len(markets)}")

        if divs:
            click.echo("\n--- ACTIVE DIVERGENCES ---")
            for d in divs:
                click.echo(f"• [{d.type}] {d.description}")

        click.echo("\n--- WHY? EXPLANATION ---")
        click.echo(ssi_snap.explanation or "No explanation generated.")
        click.echo("==================================================")

    finally:
        db.close()


if __name__ == "__main__":
    cli()
