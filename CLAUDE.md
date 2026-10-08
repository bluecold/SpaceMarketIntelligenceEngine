# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Space Market Intelligence Engine (SMIE v2.2): a quantitative engine that scores space and aerospace stocks (ASTS, RKLB, SATL, SPCE, SPCX). It blends five separate sources into a 0–100 SMI index, an explainable signal, divergence detection and alerts. The sources are X/Twitter sentiment, Polymarket probabilities, Google News catalysts, yfinance fundamentals and yfinance price/technicals. The backend is a Python 3.11+ modular monolith (FastAPI, SQLAlchemy, SQLite). The frontend is React 18, TypeScript and Vite. Project docs (`README.md`, `PROJECT_CONTEXT.md`, `audit/*.md`) are in Spanish; code and comments are in English.

`PROJECT_CONTEXT.md` is the master design document. It holds the formulas, thresholds and the reasoning behind them. `SPACE_MARKET_INTELLIGENCE_ENGINE_SPEC.md` is the original spec. When you change scoring behavior, update `PROJECT_CONTEXT.md` and the README feature list too; release commits keep them in sync.

## Commands

```bash
pip install -r requirements.txt
cd frontend && npm install && npm run build      # build output goes to frontend/dist, which FastAPI serves

python -m app.main                               # API + built SPA at http://localhost:8000
cd frontend && npm run dev                       # Vite dev server on :3000, proxies /api to :8000

python -m pytest tests/ -v                       # full suite
python -m pytest tests/test_smi.py -v            # single file
python -m pytest tests/test_smi.py::test_name -v # single test

python -m app.cli run-all                        # full pipeline once (same as `python -m app.cli.commands run-all`)
python -m app.cli analyze ASTS                   # per-ticker breakdown with "WHY?" explanations
# other CLI subcommands: collect-social, collect-polymarket, collect-news, collect-market,
# calculate-smi, calculate-divergences, daily-report, backtest
python -m app.cli reclassify-social --days 14  # relabel stored X posts after changing SOCIAL_SENTIMENT_MODEL
```

The frontend has ESLint (`cd frontend && npm run lint`, flat config in `frontend/eslint.config.js`); there is no Python linter or formatter config. Frontend type checking runs as part of `npm run build` (`tsc && vite build`). Frontend score colors come from `engine.thresholds` (served by `describe_engine()` from the `THRESHOLD_*` and `RISK_GATE_THRESHOLD` settings) through `frontend/src/lib/scale.ts`; don't hardcode score cutoffs in components.

## Architecture

**Pipeline (`app/jobs/runner.py`)** is the center of the system. `run_full_pipeline` takes a DB-level lock, starts a 30s heartbeat worker, then for each ticker: ingests social, news, market and Polymarket data through the collectors, classifies sentiment, computes each pillar score, combines them in `calculate_smi`, builds the signal and explanation, detects divergences, and saves snapshots and alerts. The same entry point runs from the CLI, from `POST /api/jobs/run` (`app/api/jobs.py`, run as a background task), and from APScheduler when `ENABLE_SCHEDULER=True` (started in `app/main.py` lifespan).

**Layers:**
- `app/collectors/`: provider interfaces in `base.py` (`XProvider`, `MarketProviderInterface`, `PredictionMarketProvider` and Pydantic data models), with live and mock implementations. Factory functions in `runner.py` pick a provider from the `X_PROVIDER`, `NEWS_PROVIDER` and `POLYMARKET_PROVIDER` settings. Mock fallback only happens when `ALLOW_MOCK_FALLBACK=True`.
- `app/sentiment/`: `classifier.py` (lexical classifier, or local FinBERT `ProsusAI/finbert` when `USE_FINBERT=True`) and `weighting.py` (engagement/recency/relevance weights, catalyst detection with negation handling and launch-vs-product disambiguation, news score).
- `app/technical/`: `indicators.py` (EMA200, RSI with Wilder smoothing, Bollinger, MACD, ATR, intraday reversal metrics) and `scorer.py` (0–40 technical score).
- `app/scoring/`: one module per pillar (`social`, `prediction`, `momentum`, `risk`, `fundamentals`). `smi.py` combines them with the `WEIGHT_*` settings (v2.2: social 35 / news 30 / PMS 15 / momentum 10 / fundamentals 10 / risk 0, so sentiment drives 80%) and re-normalizes over the pillars that have data. Risk is left out of the average and only used as a gate in `signal.py`. Momentum is deliberately low-variance technical context (EMA200 trend filter, signed volume, RSI penalty): no momentum variant predicted forward returns on 2 years of prices. The social pillar (`app/scoring/social.py`) is opinion-only polarity (neutral, non-English and promo-spam posts excluded), re-centered on each ticker's 14-day baseline by `apply_social_baseline` in the runner, so SSI 50 means "normal for this ticker". A missing pillar is `None` and gets excluded. It is never filled in with a neutral 50. `signal.py` maps SMI to the symmetric `base_signal` bands from `settings.THRESHOLD_*`, adds cumulative `signal_modifier`s (DILUTION RISK, NO MKT DATA, etc.), and applies capital-preservation gates.
- `app/divergence/detector.py`: compares X, Polymarket and price against each other.
- `app/backtesting/engine.py`: Model A vs Model B backtests with paired block bootstrap. It imports the **same** `calculate_smi` and `generate_signal_and_explanation` that the live pipeline uses.
- `app/database/`: `models.py` (SQLAlchemy), `repository.py` (all reads and writes, alert lifecycle, job lock), `connection.py` (engine, `rebind_engine`, `init_db`).
- `app/api/`: FastAPI routers mounted under `/api/*`. `app/main.py` also serves `frontend/dist` as an SPA with a catch-all route.
- `api/index.py`: thin wrapper that exposes `app.main:app` to serverless hosts.

**Rules to keep when editing:**
- **Live/backtest parity:** `calculate_technical_indicators`, `calculate_momentum_score` and `calculate_risk_score` take an `at_index` argument. Calling one with `at_index=i` must give the same result as calling it on `df.iloc[:i+1]`, so there is no lookahead. Risk and fundamental gates must match between the live engine and both backtest models. `tests/test_strategy_parity.py` checks this.
- **Schema changes:** there is no Alembic. `init_db()` runs `create_all` and then a hand-maintained list of `(table, column, DDL)` entries that get `ALTER TABLE ADD COLUMN` on existing SQLite DBs. When you add a column to a model, also add it to that list in `connection.py`.
- **Data provenance:** rows in `social_posts` and `prediction_markets` carry a `source` value (`LIVE`/`MOCK`/`DEGRADED`). The provenance of a snapshot or alert is derived from those rows. When `ALLOW_MOCK_FALLBACK=False`, startup purges mock rows.
- **Alert lifecycle (`save_alerts`):** alerts auto-resolve only when the matching fetch succeeded (`fund_success`, `mkt_success`, Polymarket ingest success), so a network outage doesn't close and reopen them. `CATALYST` alerts have a 5-day grace period. Alert IDs look like `{ticker}:{CATEGORY}:{subtype}`. The frontend keys desktop notifications per episode as `{alert_id}@{opened_at}`.
- **Job concurrency:** a partial unique index `uq_job_runs_single_running` on `job_runs(status='RUNNING')` makes sure only one pipeline runs at a time. A second run attempt gets HTTP 409. Jobs whose heartbeat is older than 120s count as zombies.
- **API auth (`verify_api_key`):** uses `secrets.compare_digest` with the `X-API-KEY` or `Authorization: Bearer` header. With no `API_SECRET_KEY` set, development allows unauthenticated access but production returns 503.

## Configuration

`app/config.py` holds the `Settings` class (pydantic-settings, reads `.env`), the `INITIAL_TICKERS` universe (`TickerConfig` with aliases used for relevance matching), `DEFAULT_EVENT_COMPANY_MAPPINGS`, and every tunable threshold (signal bands, PMS weights, volume ratios). Put new thresholds there instead of hardcoding them. `USE_FINBERT` enables local transformer models; it defaults to `False` in code but is `True` in `.env.example`. News use `SENTIMENT_MODEL` (FinBERT); X posts use `SOCIAL_SENTIMENT_MODEL` (FinTwitBERT) with `SOCIAL_SENTIMENT_THRESHOLD` 0.90 via `get_social_sentiment_classifier()`. Models download to `~/.cache/huggingface/` on first use. Each stored post records `sentiment_model`. The default DB is `data/space_sentiment.db`. `data/` and `scratch/` are gitignored.

## Tests

`tests/conftest.py` sets `ENVIRONMENT=testing` before importing the app, switches all providers to mock, turns off the scheduler, and calls `rebind_engine` to point at `data/test_space_sentiment.db`. It refuses to run against the production DB. Tests need no network access. New tests that touch the DB or providers must import through this setup and must not build their own engine on `space_sentiment.db`.

`audit/` holds the signal-quality audit reports and their repro scripts (`python -m audit.review_round2`, `python -m audit.verify_signal_audit_fixed`). `reproduce_signal_audit.py` asserts old defects and is kept only as history. Don't use it as an acceptance test.

`audit/sentiment_2026_10/` holds the read-only studies behind the v2.2 scoring changes (model comparison, blind review labels keyed by tweet ID, momentum IC, SMI composition/pillar IC, spam check); see its README. Run them from the repo root with `python -m audit.sentiment_2026_10.<script>`. Measure before changing weights or thresholds, and filter by `rules_version` (stored per snapshot) so pre-2.2 snapshots are not mixed in. Pending work is tracked in section 5 of `PROJECT_CONTEXT.md`. The repo is public: never commit tweet texts or usernames (outputs go to the gitignored `audit/output/`).
