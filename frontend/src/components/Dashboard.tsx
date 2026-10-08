import React, { useState } from 'react';
import { Zap } from 'lucide-react';
import { RankingItem, EngineInfo, formatWeight } from '../types';
import { fmtPrice, isNum, riskTone, scoreTone, signalTone, useThresholds } from '../lib/scale';
import { Badge, DataFlags, EmptyState, ScoreValue, SignalPill } from './ui';

interface DashboardProps {
  rankings: RankingItem[];
  onSelectTicker: (ticker: string) => void;
  engine?: EngineInfo;
}

type ViewMode = 'table' | 'cards';

// Enter/Space activation for rows and cards that act as buttons
const activateOnKey = (action: () => void) => (e: React.KeyboardEvent) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    action();
  }
};

const DivergenceTag: React.FC<{ divergence?: string; withIcon?: boolean }> = ({ divergence, withIcon }) => {
  if (!divergence || divergence === 'NONE') return <span className="text-muted text-xs">Aligned</span>;
  return (
    <Badge variant={divergence.includes('BULLISH') ? 'bull' : 'bear'}>
      {withIcon && <Zap size={12} />}
      {divergence.split(':')[0]}
    </Badge>
  );
};

export const Dashboard: React.FC<DashboardProps> = ({ rankings, onSelectTicker, engine }) => {
  const [viewMode, setViewMode] = useState<ViewMode>('table');
  const thresholds = useThresholds();

  const topAsset = rankings.find((r) => r.signal?.includes('BUY')) || rankings.find((r) => isNum(r.smi)) || rankings[0];
  const validSmis = rankings.map((r) => r.smi).filter(isNum);
  const avgSmi = validSmis.length > 0 ? validSmis.reduce((acc, v) => acc + v, 0) / validSmis.length : null;

  return (
    <main>
      {/* Sector overview */}
      <div className="summary-grid">
        <section className="summary-card">
          <div className="summary-label">Top Space Intelligence Asset</div>
          <div className={`summary-value tone-${topAsset ? signalTone(topAsset.signal, topAsset.base_signal) : 'none'}`}>
            {topAsset?.ticker || '—'}
          </div>
          <div className="summary-meta">
            SMI: <ScoreValue value={topAsset?.smi} /> · Signal: {topAsset?.signal || '—'}
          </div>
        </section>

        <section className="summary-card">
          <div className="summary-label">Tracked Universe & Providers</div>
          <div className="summary-value tone-accent">{rankings.length} Assets</div>
          <div className="summary-meta">X (Social) + Polymarket + yfinance + News</div>
        </section>

        <section className="summary-card">
          <div className="summary-label">Average Sector SMI</div>
          <div className={`summary-value tone-${scoreTone(avgSmi, thresholds)}`}>
            {isNum(avgSmi) ? `${avgSmi.toFixed(1)} / 100` : '—'}
          </div>
          <div className="summary-meta">
            {engine
              ? `Social ${formatWeight(engine, 'social')} · News ${formatWeight(engine, 'news')} · Prediction ${formatWeight(engine, 'prediction')} · Market ${formatWeight(engine, 'momentum')} · Fundamentals ${formatWeight(engine, 'fundamental')}`
              : 'Multi-Source SMI'}
          </div>
        </section>
      </div>

      {/* Title and view selector */}
      <div className="section-header">
        <div>
          <h2 className="section-title">Active Rankings</h2>
          <p className="section-subtitle">
            Synthesis of Social Narrative (X), Prediction Markets (Polymarket), News, Technical Price Action and Fundamentals.
          </p>
        </div>

        <div className="segmented" role="group" aria-label="View mode">
          {(['table', 'cards'] as const).map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setViewMode(mode)}
              aria-pressed={viewMode === mode}
              className={`btn btn-sm ${viewMode === mode ? 'btn-primary' : 'btn-secondary'}`}
            >
              {mode === 'table' ? 'Table' : 'Cards'}
            </button>
          ))}
        </div>
      </div>

      <ScaleLegend />

      {rankings.length === 0 ? (
        <EmptyState>No snapshots yet. Run the SMIE pipeline to score the tracked tickers.</EmptyState>
      ) : viewMode === 'table' ? (
        <div className="table-wrap">
          <table className="terminal-table">
            <thead>
              <tr>
                <th scope="col">Ticker / Asset</th>
                <th scope="col" className="num">SMI</th>
                <th scope="col" className="num">SSI (Social)</th>
                <th scope="col" className="num col-md">PMS (Polymarket)</th>
                <th scope="col" className="num col-md">Market</th>
                <th scope="col" className="num col-md">Risk / Safety</th>
                <th scope="col" className="center">Signal</th>
                <th scope="col" className="num col-lg">Confidence</th>
                <th scope="col" className="center col-lg">Divergence</th>
                <th scope="col" className="right">Price</th>
              </tr>
            </thead>
            <tbody>
              {rankings.map((stock) => (
                <tr
                  key={stock.ticker}
                  className="table-row-interactive"
                  tabIndex={0}
                  aria-label={`Open details for ${stock.ticker}`}
                  onClick={() => onSelectTicker(stock.ticker)}
                  onKeyDown={activateOnKey(() => onSelectTicker(stock.ticker))}
                >
                  <td>
                    <div className="ticker-cell">
                      <span className="ticker-cell-symbol">${stock.ticker}</span>
                      <DataFlags source={stock.data_source} isStale={stock.is_stale} ageHours={stock.data_age_hours} />
                    </div>
                    <div className="text-muted text-xs">{stock.name}</div>
                  </td>
                  <td className="num"><ScoreValue value={stock.smi} className="score-lg" /></td>
                  <td className="num"><ScoreValue value={stock.ssi} className="score-md" /></td>
                  <td className="num col-md"><ScoreValue value={stock.pms} className="score-md" /></td>
                  <td className="num col-md"><ScoreValue value={stock.market_score} digits={0} suffix="/100" /></td>
                  <td className="num col-md">
                    <ScoreValue value={stock.risk_score} digits={0} suffix="/100" tone={riskTone(stock.risk_score, thresholds)} />
                  </td>
                  <td className="center"><SignalPill signal={stock.signal} baseSignal={stock.base_signal} /></td>
                  <td className="num col-lg">
                    <div className={`text-xs strong ${stock.confidence >= 70 ? 'text-ok' : 'text-warn'}`}>{(stock.confidence ?? 0).toFixed(0)}%</div>
                    <div className="text-muted text-2xs">Quality: {(stock.data_quality ?? 0).toFixed(0)}%</div>
                  </td>
                  <td className="center col-lg"><DivergenceTag divergence={stock.divergence} /></td>
                  <td className="right strong text-strong">
                    {fmtPrice(stock.price, stock.market_status === 'DATA_UNAVAILABLE' ? 'N/A' : '—')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="stock-grid">
          {rankings.map((stock) => (
            <div
              key={stock.ticker}
              className="stock-card"
              role="button"
              tabIndex={0}
              aria-label={`Open details for ${stock.ticker}`}
              onClick={() => onSelectTicker(stock.ticker)}
              onKeyDown={activateOnKey(() => onSelectTicker(stock.ticker))}
            >
              <div className="card-top">
                <div>
                  <div className="ticker-cell">
                    <span className="ticker-symbol">${stock.ticker}</span>
                    <DataFlags source={stock.data_source} isStale={stock.is_stale} ageHours={stock.data_age_hours} />
                  </div>
                  <div className="company-name">{stock.name}</div>
                </div>
                <div className="right">
                  <div className="micro-label">SMI</div>
                  <ScoreValue value={stock.smi} className="ssi-score-badge" />
                </div>
              </div>

              <div className="card-signal-row">
                <SignalPill signal={stock.signal} baseSignal={stock.base_signal} />
                <span className="text-muted text-sm">
                  Confidence: <b className="text-strong">{(stock.confidence ?? 0).toFixed(0)}%</b>
                </span>
              </div>

              <div className="card-subscores">
                <div><span className="text-muted">SSI </span><ScoreValue value={stock.ssi} digits={0} className="strong" /></div>
                <div><span className="text-muted">PMS </span><ScoreValue value={stock.pms} digits={0} className="strong" /></div>
                <div>
                  <span className="text-muted">Risk </span>
                  <ScoreValue value={stock.risk_score} digits={0} tone={riskTone(stock.risk_score, thresholds)} className="strong" />
                </div>
                <div><span className="text-muted">Price </span><b>{fmtPrice(stock.price, 'N/A')}</b></div>
              </div>

              {stock.divergence && stock.divergence !== 'NONE' && (
                <div className="card-divergence"><DivergenceTag divergence={stock.divergence} withIcon /></div>
              )}
            </div>
          ))}
        </div>
      )}
    </main>
  );
};

// Explains the color scale, which follows the engine's signal bands (mirrored around 50)
const ScaleLegend: React.FC = () => {
  const t = useThresholds();
  const items: { tone: string; label: string }[] = [
    { tone: 'strong-bull', label: `≥ ${t.buy} Buy` },
    { tone: 'bull', label: `≥ ${t.watch} Watch` },
    { tone: 'neutral', label: `${t.hold}–${t.watch} Hold` },
    { tone: 'bear', label: `≤ ${t.hold} Caution` },
    { tone: 'strong-bear', label: `≤ ${t.avoid} Avoid` }
  ];
  return (
    <div className="scale-legend" aria-label="Score color scale">
      <span className="text-muted">Score scale (50 = neutral):</span>
      {items.map((it) => (
        <span key={it.tone} className={`scale-legend-item tone-${it.tone}`}>
          <span className="scale-dot" aria-hidden="true" />
          {it.label}
        </span>
      ))}
      <span className="text-muted">· Risk is red below the {t.risk_gate} gate</span>
    </div>
  );
};
