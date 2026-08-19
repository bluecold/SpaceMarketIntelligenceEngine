import React, { useState } from 'react';
import { RankingItem } from '../types';
import { TrendingUp, TrendingDown, Eye, AlertCircle, Zap, Shield, HelpCircle, Activity, Globe } from 'lucide-react';

interface DashboardProps {
  rankings: RankingItem[];
  onSelectTicker: (ticker: string) => void;
}

export const Dashboard: React.FC<DashboardProps> = ({ rankings, onSelectTicker }) => {
  const [viewMode, setViewMode] = useState<'cards' | 'table'>('table');

  const getSignalClass = (signal: string) => {
    const s = signal.toUpperCase();
    if (s.includes('STRONG BUY') || s.includes('BUY')) return 'signal-buy';
    if (s.includes('WATCH') || s.includes('HOLD')) return 'signal-watch';
    if (s.includes('AVOID')) return 'signal-avoid';
    return 'signal-na';
  };

  const getScoreColor = (score: number | null | undefined) => {
    if (score === null || score === undefined) return 'var(--text-muted)';
    if (score >= 75) return 'var(--bullish-green)';
    if (score >= 50) return 'var(--neutral-yellow)';
    return 'var(--bearish-red)';
  };

  const topBullish = rankings.find(r => r.signal.includes('BUY')) || rankings[0];
  const avgSmi = rankings.length > 0
    ? (rankings.reduce((acc, r) => acc + (r.smi || r.ssi || 50), 0) / rankings.length).toFixed(1)
    : '--';

  return (
    <div>
      {/* Top Sector Overview Summary Bar */}
      <div className="summary-grid">
        <div className="summary-card">
          <div className="summary-label">Top Space Intelligence Asset</div>
          <div className="summary-value" style={{ color: 'var(--bullish-green)' }}>
            {topBullish?.ticker || '--'}
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            SMI: {topBullish?.smi || '--'} | Signal: {topBullish?.signal || '--'}
          </div>
        </div>

        <div className="summary-card">
          <div className="summary-label">Tracked Universe & Providers</div>
          <div className="summary-value" style={{ color: 'var(--accent-cyan)' }}>
            {rankings.length} Assets
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            X (Social) + Polymarket + yfinance + News
          </div>
        </div>

        <div className="summary-card">
          <div className="summary-label">Average Sector SMI</div>
          <div className="summary-value" style={{ color: '#fff' }}>
            {avgSmi} / 100
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Multi-Source: Social 30% | Prediction 15% | News 20% | Market 20%
          </div>
        </div>
      </div>

      {/* Header and View Selector */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.3rem', margin: 0 }}>
            Space Market Intelligence Engine — Active Rankings
          </h2>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', margin: '4px 0 0 0' }}>
            Real-time synthesis of Social Narrative (X), Prediction Markets (Polymarket), Technical Price Action and News.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '6px', background: 'var(--card-bg)', padding: '4px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
          <button
            onClick={() => setViewMode('table')}
            className={`btn ${viewMode === 'table' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '6px 12px', fontSize: '0.78rem' }}
          >
            Terminal Table
          </button>
          <button
            onClick={() => setViewMode('cards')}
            className={`btn ${viewMode === 'cards' ? 'btn-primary' : 'btn-secondary'}`}
            style={{ padding: '6px 12px', fontSize: '0.78rem' }}
          >
            Cards View
          </button>
        </div>
      </div>

      {/* 1. Terminal Table View */}
      {viewMode === 'table' ? (
        <div style={{ background: 'var(--card-bg)', borderRadius: '12px', border: '1px solid var(--border-color)', overflowX: 'auto' }}>
          <table className="terminal-table" style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)', fontFamily: 'var(--font-heading)' }}>
                <th style={{ padding: '12px 16px' }}>TICKER / ASSET</th>
                <th style={{ padding: '12px 12px', textAlign: 'center' }}>SMI (INTEGRAL)</th>
                <th style={{ padding: '12px 12px', textAlign: 'center' }}>SSI (SOCIAL)</th>
                <th style={{ padding: '12px 12px', textAlign: 'center' }}>PMS (POLYMARKET)</th>
                <th style={{ padding: '12px 12px', textAlign: 'center' }}>MARKET SCORE</th>
                <th style={{ padding: '12px 12px', textAlign: 'center' }}>SIGNAL</th>
                <th style={{ padding: '12px 12px', textAlign: 'center' }}>CONFIDENCE</th>
                <th style={{ padding: '12px 12px', textAlign: 'center' }}>REGIME / DIVERGENCE</th>
                <th style={{ padding: '12px 16px', textAlign: 'right' }}>PRICE</th>
              </tr>
            </thead>
            <tbody>
              {rankings.map((stock) => {
                const smi = stock.smi !== undefined ? stock.smi : stock.ssi;
                return (
                  <tr
                    key={stock.ticker}
                    className="table-row-interactive"
                    onClick={() => onSelectTicker(stock.ticker)}
                    style={{ borderBottom: '1px solid rgba(255,255,255,0.05)', cursor: 'pointer' }}
                  >
                    {/* Ticker & Name */}
                    <td style={{ padding: '12px 16px' }}>
                      <div style={{ fontWeight: 700, color: '#fff', fontSize: '0.95rem' }}>${stock.ticker}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{stock.name}</div>
                    </td>

                    {/* SMI Score */}
                    <td style={{ padding: '12px 12px', textAlign: 'center' }}>
                      <span className="smi-badge" style={{ color: getScoreColor(smi), fontWeight: 800, fontSize: '1.05rem' }}>
                        {smi.toFixed(1)}
                      </span>
                    </td>

                    {/* SSI (Social Score) */}
                    <td style={{ padding: '12px 12px', textAlign: 'center' }}>
                      <span style={{ color: getScoreColor(stock.ssi), fontWeight: 700 }}>
                        {stock.ssi ? stock.ssi.toFixed(1) : '--'}
                      </span>
                    </td>

                    {/* PMS (Prediction Market Score) */}
                    <td style={{ padding: '12px 12px', textAlign: 'center' }}>
                      {stock.pms !== null && stock.pms !== undefined ? (
                        <span style={{ color: getScoreColor(stock.pms), fontWeight: 700 }}>
                          {stock.pms.toFixed(1)}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>--</span>
                      )}
                    </td>

                    {/* Market Score */}
                    <td style={{ padding: '12px 12px', textAlign: 'center' }}>
                      {stock.market_score !== null && stock.market_score !== undefined ? (
                        <span style={{ color: getScoreColor(stock.market_score), fontWeight: 600 }}>
                          {stock.market_score.toFixed(0)}/100
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>--</span>
                      )}
                    </td>

                    {/* Signal */}
                    <td style={{ padding: '12px 12px', textAlign: 'center' }}>
                      <span className={`signal-pill ${getSignalClass(stock.signal)}`}>
                        {stock.signal}
                      </span>
                    </td>

                    {/* Confidence & Data Quality */}
                    <td style={{ padding: '12px 12px', textAlign: 'center' }}>
                      <div style={{ fontSize: '0.78rem', fontWeight: 600, color: stock.confidence >= 70 ? 'var(--bullish-green)' : 'var(--neutral-yellow)' }}>
                        {stock.confidence ? stock.confidence.toFixed(0) : '0'}%
                      </div>
                      <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                        Qual: {stock.data_quality ? stock.data_quality.toFixed(0) : '0'}%
                      </div>
                    </td>

                    {/* Divergence */}
                    <td style={{ padding: '12px 12px', textAlign: 'center' }}>
                      {stock.divergence && stock.divergence !== 'NONE' ? (
                        <span
                          style={{
                            fontSize: '0.72rem',
                            fontWeight: 700,
                            color: stock.divergence.includes('BULLISH') ? 'var(--bullish-green)' : (stock.divergence.includes('BEARISH') ? 'var(--bearish-red)' : 'var(--accent-cyan)'),
                            background: stock.divergence.includes('BULLISH') ? 'var(--bullish-bg)' : (stock.divergence.includes('BEARISH') ? 'var(--bearish-bg)' : 'rgba(0, 229, 255, 0.1)'),
                            padding: '3px 8px',
                            borderRadius: '4px',
                            display: 'inline-block'
                          }}
                        >
                          {stock.divergence.split(':')[0]}
                        </span>
                      ) : (
                        <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Aligned</span>
                      )}
                    </td>

                    {/* Price */}
                    <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                      <div style={{ fontWeight: 600, color: '#fff' }}>
                        {stock.price ? `$${stock.price.toFixed(2)}` : (stock.market_status === 'DATA_UNAVAILABLE' ? 'N/A' : '--')}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        /* 2. Cards Grid View */
        <div className="stock-grid">
          {rankings.map((stock) => {
            const smi = stock.smi !== undefined ? stock.smi : stock.ssi;
            return (
              <div
                key={stock.ticker}
                className="stock-card"
                onClick={() => onSelectTicker(stock.ticker)}
              >
                <div className="card-top">
                  <div>
                    <div className="ticker-symbol">${stock.ticker}</div>
                    <div className="company-name">{stock.name}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>SMI INDEX</div>
                    <div className="ssi-score-badge" style={{ color: getScoreColor(smi) }}>
                      {smi.toFixed(1)}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '6px', margin: '8px 0' }}>
                  <span className={`signal-pill ${getSignalClass(stock.signal)}`}>
                    {stock.signal}
                  </span>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Confidence: <b style={{ color: '#fff' }}>{stock.confidence}%</b>
                  </span>
                </div>

                {/* Sub-scores preview */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '4px', marginTop: '10px', padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px', fontSize: '0.75rem' }}>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Social: </span>
                    <b style={{ color: getScoreColor(stock.ssi) }}>{stock.ssi?.toFixed(0)}</b>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Poly: </span>
                    <b style={{ color: getScoreColor(stock.pms) }}>{stock.pms !== null && stock.pms !== undefined ? stock.pms.toFixed(0) : '--'}</b>
                  </div>
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>Price: </span>
                    <b>{stock.price ? `$${stock.price.toFixed(2)}` : 'N/A'}</b>
                  </div>
                </div>

                {/* Divergence Tag if present */}
                {stock.divergence && stock.divergence !== 'NONE' && (
                  <div
                    style={{
                      marginTop: '8px',
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: stock.divergence.includes('BULLISH') ? 'var(--bullish-green)' : 'var(--bearish-red)',
                      background: stock.divergence.includes('BULLISH') ? 'var(--bullish-bg)' : 'var(--bearish-bg)',
                      padding: '3px 8px',
                      borderRadius: '6px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '4px'
                    }}
                  >
                    <Zap size={12} />
                    {stock.divergence.split(':')[0]}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
