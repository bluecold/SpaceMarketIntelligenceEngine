import React, { useEffect, useState } from 'react';
import { TickerDetailResponse, HistoryPoint } from '../types';
import { HistoryChart } from './HistoryChart';
import {
  X, CheckCircle, AlertTriangle, MessageSquare, Newspaper,
  Zap, Layers, TrendingUp, DollarSign, Activity, Compass, ExternalLink, ShieldCheck,
  Target, Globe
} from 'lucide-react';

interface TickerDetailProps {
  ticker: string;
  onClose: () => void;
}

export const TickerDetail: React.FC<TickerDetailProps> = ({ ticker, onClose }) => {
  const [detail, setDetail] = useState<TickerDetailResponse | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'prediction' | 'social' | 'news' | 'divergences' | 'technical'>('prediction');
  const [marketFilter, setMarketFilter] = useState<'ALL' | 'DIRECT' | 'SECTOR'>('ALL');

  useEffect(() => {
    Promise.all([
      fetch(`/api/tickers/${ticker}`).then((res) => res.json()),
      fetch(`/api/tickers/${ticker}/history`).then((res) => res.json())
    ])
      .then(([detailData, historyData]) => {
        setDetail(detailData);
        setHistory(historyData.history || []);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load ticker details', err);
        setLoading(false);
      });
  }, [ticker]);

  if (loading) {
    return (
      <div className="modal-overlay">
        <div className="modal-content" style={{ textAlign: 'center', padding: '60px' }}>
          <p>Loading SMIE multi-source intelligence for ${ticker}...</p>
        </div>
      </div>
    );
  }

  if (!detail) return null;

  const smiVal = detail.header.smi ?? detail.header.ssi;
  const ssiVal = detail.header.ssi;
  const pmsVal = detail.header.pms;

  const getSignalClass = (signal: string) => {
    const s = signal.toUpperCase();
    if (s.includes('STRONG BUY') || s.includes('BUY')) return 'signal-buy';
    if (s.includes('WATCH') || s.includes('HOLD')) return 'signal-watch';
    if (s.includes('AVOID')) return 'signal-avoid';
    return 'signal-na';
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '960px', width: '95%' }}>
        <button className="btn-close" onClick={onClose}><X size={20} /></button>

        {/* Modal Header */}
        <div className="detail-header" style={{ borderBottom: '1px solid var(--border-color)', paddingBottom: '16px', marginBottom: '20px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
              <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '2.2rem', margin: 0 }}>${detail.ticker}</h2>
              <span className={`signal-pill ${getSignalClass(detail.header.signal)}`} style={{ fontSize: '0.85rem' }}>
                {detail.header.signal}
              </span>
              {detail.header.is_stale && (
                <span
                  style={{
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    color: 'var(--neutral-yellow)',
                    background: 'rgba(255, 179, 0, 0.12)',
                    border: '1px solid rgba(255, 179, 0, 0.3)',
                    padding: '3px 8px',
                    borderRadius: '6px'
                  }}
                >
                  ⏳ Data Age: {detail.header.data_age_hours ? `${detail.header.data_age_hours.toFixed(1)}h` : 'Stale'}
                </span>
              )}
            </div>
            <p style={{ color: 'var(--text-muted)', margin: '4px 0 0 0' }}>{detail.name}</p>
          </div>

          <div style={{ display: 'flex', gap: '20px', alignItems: 'center', textAlign: 'right' }}>
            <div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>SMI (INTEGRAL)</div>
              <div style={{ fontSize: '2rem', fontFamily: 'var(--font-heading)', fontWeight: 800, color: smiVal !== null && smiVal !== undefined ? 'var(--accent-cyan)' : 'var(--text-muted)' }}>
                {smiVal !== null && smiVal !== undefined ? (
                  <>{smiVal.toFixed(1)} <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>/100</span></>
                ) : (
                  '—'
                )}
              </div>
            </div>

            <div style={{ borderLeft: '1px solid var(--border-color)', paddingLeft: '16px' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>SSI (SOCIAL)</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: ssiVal !== null && ssiVal !== undefined ? 'var(--bullish-green)' : 'var(--text-muted)' }}>
                {ssiVal !== null && ssiVal !== undefined ? ssiVal.toFixed(1) : '—'}
              </div>
            </div>

            <div style={{ borderLeft: '1px solid var(--border-color)', paddingLeft: '16px' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>PMS (POLYMARKET)</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: pmsVal !== null ? 'var(--accent-cyan)' : 'var(--text-muted)' }}>
                {pmsVal !== null ? `${pmsVal.toFixed(1)}` : '--'}
              </div>
            </div>
          </div>
        </div>

        {/* Historical Interactive Multi-Series Chart */}
        <div style={{ marginBottom: '24px' }}>
          <HistoryChart data={history} />
        </div>

        {/* Multivariable 6 Pillars Grid */}
        <div style={{ marginBottom: '20px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              SMIE Multi-Factor 6 Pillars Architecture
            </span>
            <div style={{ display: 'flex', gap: '14px', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              <span>Confidence: <strong style={{ color: '#fff' }}>{detail.header.confidence ? `${detail.header.confidence.toFixed(0)}%` : '0%'}</strong></span>
              <span>Data Quality: <strong style={{ color: 'var(--accent-cyan)' }}>{detail.header.data_quality ? `${detail.header.data_quality.toFixed(0)}%` : '0%'}</strong></span>
              {detail.sample_counts && (
                <span>Data Depth: <strong style={{ color: '#e2e8f0' }}>{detail.sample_counts.post_count}P / {detail.sample_counts.news_count}N / {detail.sample_counts.prediction_count}M</strong></span>
              )}
            </div>
          </div>
          <div className="tech-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
            <div className="tech-item">
              <div className="tech-key">SOCIAL SSI (30%)</div>
              <div className="tech-val" style={{ color: 'var(--bullish-green)' }}>
                {detail.score_breakdown.social_score !== null && detail.score_breakdown.social_score !== undefined ? detail.score_breakdown.social_score.toFixed(1) : '—'}
              </div>
            </div>
            <div className="tech-item">
              <div className="tech-key">POLYMARKET PMS (15%)</div>
              <div className="tech-val" style={{ color: 'var(--accent-cyan)' }}>
                {detail.score_breakdown.prediction_score !== null && detail.score_breakdown.prediction_score !== undefined ? detail.score_breakdown.prediction_score.toFixed(1) : '—'}
              </div>
            </div>
            <div className="tech-item">
              <div className="tech-key">NEWS / CATALYSTS (20%)</div>
              <div className="tech-val" style={{ color: '#f59e0b' }}>
                {detail.score_breakdown.news_score !== null && detail.score_breakdown.news_score !== undefined ? detail.score_breakdown.news_score.toFixed(1) : '—'}
              </div>
            </div>
            <div className="tech-item">
              <div className="tech-key">MARKET MOMENTUM (20%)</div>
              <div className="tech-val" style={{ color: '#38bdf8' }}>
                {detail.score_breakdown.momentum_score !== null && detail.score_breakdown.momentum_score !== undefined ? detail.score_breakdown.momentum_score.toFixed(1) : '—'}
              </div>
            </div>
            <div className="tech-item" title="Pilar modular: al no haber feed fundamental conectado, su 10% se redistribuye proporcionalmente en el SMI">
              <div className="tech-key">FUNDAMENTALS (10%)</div>
              <div className="tech-val" style={{ color: '#a78bfa', fontSize: detail.score_breakdown.fundamental_score ? undefined : '0.9rem' }}>
                {detail.score_breakdown.fundamental_score !== null && detail.score_breakdown.fundamental_score !== undefined ? detail.score_breakdown.fundamental_score.toFixed(1) : '— (Modular)'}
              </div>
            </div>
            <div className="tech-item">
              <div className="tech-key">RISK / SAFETY (5%)</div>
              <div className="tech-val" style={{ color: detail.score_breakdown.risk_score !== null && detail.score_breakdown.risk_score !== undefined ? (detail.score_breakdown.risk_score >= 60 ? 'var(--bullish-green)' : detail.score_breakdown.risk_score <= 35 ? 'var(--bearish-red)' : 'var(--neutral-yellow)') : 'var(--text-muted)' }}>
                {detail.score_breakdown.risk_score !== null && detail.score_breakdown.risk_score !== undefined ? detail.score_breakdown.risk_score.toFixed(1) : '—'}
              </div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div style={{ display: 'flex', gap: '8px', borderBottom: '1px solid var(--border-color)', marginBottom: '16px', overflowX: 'auto' }}>
          <button
            onClick={() => setActiveTab('prediction')}
            className={`tab-btn ${activeTab === 'prediction' ? 'active' : ''}`}
            style={{
              background: 'none', border: 'none',
              borderBottom: activeTab === 'prediction' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeTab === 'prediction' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '8px 14px', fontSize: '0.88rem', fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <Compass size={16} /> Prediction Markets ({detail.prediction_markets?.length || 0})
          </button>

          <button
            onClick={() => setActiveTab('social')}
            className={`tab-btn ${activeTab === 'social' ? 'active' : ''}`}
            style={{
              background: 'none', border: 'none',
              borderBottom: activeTab === 'social' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeTab === 'social' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '8px 14px', fontSize: '0.88rem', fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <MessageSquare size={16} /> X Social Feed ({detail.recent_posts?.length || 0})
          </button>

          <button
            onClick={() => setActiveTab('news')}
            className={`tab-btn ${activeTab === 'news' ? 'active' : ''}`}
            style={{
              background: 'none', border: 'none',
              borderBottom: activeTab === 'news' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeTab === 'news' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '8px 14px', fontSize: '0.88rem', fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <Newspaper size={16} /> News & Catalysts ({detail.recent_news?.length || 0})
          </button>

          <button
            onClick={() => setActiveTab('divergences')}
            className={`tab-btn ${activeTab === 'divergences' ? 'active' : ''}`}
            style={{
              background: 'none', border: 'none',
              borderBottom: activeTab === 'divergences' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeTab === 'divergences' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '8px 14px', fontSize: '0.88rem', fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <Zap size={16} /> Divergences & WHY ({detail.divergences?.length || 0})
          </button>

          <button
            onClick={() => setActiveTab('technical')}
            className={`tab-btn ${activeTab === 'technical' ? 'active' : ''}`}
            style={{
              background: 'none', border: 'none',
              borderBottom: activeTab === 'technical' ? '2px solid var(--accent-cyan)' : '2px solid transparent',
              color: activeTab === 'technical' ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '8px 14px', fontSize: '0.88rem', fontWeight: 600, cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '6px'
            }}
          >
            <Activity size={16} /> Technicals
          </button>
        </div>

        {/* TAB 1: Prediction Markets (Polymarket) */}
        {activeTab === 'prediction' && (() => {
          const allMarkets = detail.prediction_markets || [];
          const directMarkets = allMarkets.filter((m) => m.is_direct || (m.ticker && m.ticker.toUpperCase() === detail.ticker.toUpperCase()));
          const sectorMarkets = allMarkets.filter((m) => !m.is_direct && (!m.ticker || m.ticker.toUpperCase() !== detail.ticker.toUpperCase()));

          const displayedMarkets = marketFilter === 'DIRECT'
            ? directMarkets
            : marketFilter === 'SECTOR'
            ? sectorMarkets
            : allMarkets;

          return (
            <div>
              {/* Prediction Sub-Filter Pills & PMS Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button
                    onClick={() => setMarketFilter('ALL')}
                    style={{
                      background: marketFilter === 'ALL' ? 'rgba(0, 242, 254, 0.15)' : 'rgba(255, 255, 255, 0.04)',
                      border: marketFilter === 'ALL' ? '1px solid var(--accent-cyan)' : '1px solid rgba(255, 255, 255, 0.08)',
                      color: marketFilter === 'ALL' ? 'var(--accent-cyan)' : 'var(--text-muted)',
                      borderRadius: '20px',
                      padding: '4px 12px',
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    Todos ({allMarkets.length})
                  </button>

                  <button
                    onClick={() => setMarketFilter('DIRECT')}
                    style={{
                      background: marketFilter === 'DIRECT' ? 'rgba(16, 185, 129, 0.18)' : 'rgba(255, 255, 255, 0.04)',
                      border: marketFilter === 'DIRECT' ? '1px solid var(--bullish-green)' : '1px solid rgba(255, 255, 255, 0.08)',
                      color: marketFilter === 'DIRECT' ? 'var(--bullish-green)' : 'var(--text-muted)',
                      borderRadius: '20px',
                      padding: '4px 12px',
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    <Target size={12} />
                    <span>Directos ${detail.ticker} ({directMarkets.length})</span>
                  </button>

                  <button
                    onClick={() => setMarketFilter('SECTOR')}
                    style={{
                      background: marketFilter === 'SECTOR' ? 'rgba(168, 85, 247, 0.18)' : 'rgba(255, 255, 255, 0.04)',
                      border: marketFilter === 'SECTOR' ? '1px solid #c084fc' : '1px solid rgba(255, 255, 255, 0.08)',
                      color: marketFilter === 'SECTOR' ? '#c084fc' : 'var(--text-muted)',
                      borderRadius: '20px',
                      padding: '4px 12px',
                      fontSize: '0.72rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      transition: 'all 0.15s ease'
                    }}
                  >
                    <Globe size={12} />
                    <span>Sectoriales / SpaceX ({sectorMarkets.length})</span>
                  </button>
                </div>

                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  PMS Ponderado: <strong style={{ color: 'var(--accent-cyan)' }}>{detail.header.pms ? `${detail.header.pms.toFixed(1)}/100` : '—'}</strong>
                </div>
              </div>

              {/* Markets List */}
              {displayedMarkets.length > 0 ? (
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '12px' }}>
                  {displayedMarkets.map((m) => {
                    const isDirect = m.is_direct || (m.ticker && m.ticker.toUpperCase() === detail.ticker.toUpperCase());
                    const impactBeta = m.impact_weight !== undefined && m.impact_weight !== null ? m.impact_weight : null;

                    return (
                      <div
                        key={m.id}
                        style={{
                          background: isDirect ? 'rgba(16, 185, 129, 0.04)' : 'rgba(255, 255, 255, 0.03)',
                          border: isDirect ? '1px solid rgba(16, 185, 129, 0.3)' : '1px solid var(--border-color)',
                          borderLeft: isDirect ? '4px solid var(--bullish-green)' : '4px solid #a855f7',
                          borderRadius: '10px',
                          padding: '16px',
                          transition: 'all 0.15s ease'
                        }}
                      >
                        {/* Top Tagging & Quality Bar */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px', marginBottom: '6px' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                            {/* Role Badge */}
                            {isDirect ? (
                              <span
                                style={{
                                  fontSize: '0.68rem',
                                  fontWeight: 800,
                                  background: 'rgba(16, 185, 129, 0.15)',
                                  color: 'var(--bullish-green)',
                                  border: '1px solid rgba(16, 185, 129, 0.4)',
                                  padding: '2px 7px',
                                  borderRadius: '4px',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '4px'
                                }}
                              >
                                <Target size={11} /> CONTRATO DIRECTO ${detail.ticker}
                              </span>
                            ) : (
                              <span
                                style={{
                                  fontSize: '0.68rem',
                                  fontWeight: 800,
                                  background: 'rgba(168, 85, 247, 0.15)',
                                  color: '#c084fc',
                                  border: '1px solid rgba(168, 85, 247, 0.4)',
                                  padding: '2px 7px',
                                  borderRadius: '4px',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '4px'
                                }}
                              >
                                <Globe size={11} /> CATALIZADOR SECTORIAL ({m.ticker || 'SPCX / Macro'})
                              </span>
                            )}

                            {/* Impact Beta pill if sector catalyst */}
                            {!isDirect && impactBeta !== null && (
                              <span
                                style={{
                                  fontSize: '0.68rem',
                                  fontWeight: 600,
                                  background: impactBeta >= 0 ? 'rgba(0, 242, 254, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                  color: impactBeta >= 0 ? 'var(--accent-cyan)' : 'var(--bearish-red)',
                                  border: `1px solid ${impactBeta >= 0 ? 'rgba(0, 242, 254, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
                                  padding: '2px 6px',
                                  borderRadius: '4px'
                                }}
                              >
                                Beta en ${detail.ticker}: {impactBeta >= 0 ? `+${(impactBeta * 100).toFixed(0)}%` : `${(impactBeta * 100).toFixed(0)}%`}
                              </span>
                            )}

                            <span style={{ fontSize: '0.68rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
                              {m.category}
                            </span>
                          </div>

                          <div style={{ textAlign: 'right' }}>
                            <span
                              style={{
                                fontSize: '0.72rem',
                                fontWeight: 700,
                                padding: '3px 8px',
                                borderRadius: '6px',
                                background: m.quality_score >= 50 ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                                color: m.quality_score >= 50 ? 'var(--bullish-green)' : 'var(--bearish-red)',
                                border: `1px solid ${m.quality_score >= 50 ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`
                              }}
                            >
                              Calidad: {m.quality_score.toFixed(0)}/100
                            </span>
                          </div>
                        </div>

                        {/* Title & Description */}
                        <h4 style={{ margin: '6px 0 6px 0', fontSize: '0.96rem', color: '#fff', lineHeight: '1.4' }}>
                          {m.title}
                        </h4>
                        {m.description && (
                          <p style={{ margin: '0 0 10px 0', fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: '1.35' }}>
                            {m.description}
                          </p>
                        )}

                        {/* Probability Bar */}
                        <div style={{ margin: '10px 0 8px 0' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px' }}>
                            <span style={{ color: 'var(--bullish-green)' }}>YES: {m.yes_probability.toFixed(1)}%</span>
                            <span style={{ color: 'var(--bearish-red)' }}>NO: {m.no_probability.toFixed(1)}%</span>
                          </div>
                          <div style={{ height: '8px', width: '100%', background: 'rgba(239,68,68,0.4)', borderRadius: '4px', overflow: 'hidden' }}>
                            <div
                              style={{
                                height: '100%',
                                width: `${m.yes_probability}%`,
                                background: 'var(--bullish-green)',
                                borderRadius: '4px 0 0 4px',
                                transition: 'width 0.5s ease'
                              }}
                            />
                          </div>
                        </div>

                        {/* Market Depth Metrics */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.76rem', color: 'var(--text-muted)', marginTop: '10px', flexWrap: 'wrap', gap: '8px' }}>
                          <span>Vol: <b style={{ color: '#fff' }}>${(m.volume / 1000).toFixed(1)}k</b></span>
                          <span>Liquidity: <b style={{ color: '#fff' }}>${(m.liquidity / 1000).toFixed(1)}k</b></span>
                          <span>Spread: <b style={{ color: '#fff' }}>{(m.spread * 100).toFixed(1)}¢</b></span>
                          {m.url && (
                            <a href={m.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-cyan)', display: 'flex', alignItems: 'center', gap: '3px', textDecoration: 'none', fontWeight: 600 }}>
                              Ver en Polymarket <ExternalLink size={12} />
                            </a>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: '36px 16px', color: 'var(--text-muted)', background: 'rgba(0,0,0,0.2)', borderRadius: '10px', border: '1px dashed rgba(255,255,255,0.08)' }}>
                  <p style={{ margin: '0 0 8px 0', fontSize: '0.88rem', color: 'var(--text-dim)' }}>
                    {marketFilter === 'DIRECT'
                      ? `Actualmente no hay apuestas directas en Polymarket con ticker específico $${detail.ticker}.`
                      : 'No hay contratos de predicción para el filtro seleccionado.'}
                  </p>
                  {marketFilter === 'DIRECT' && sectorMarkets.length > 0 && (
                    <button
                      onClick={() => setMarketFilter('SECTOR')}
                      style={{
                        background: 'rgba(168, 85, 247, 0.15)',
                        border: '1px solid #c084fc',
                        color: '#c084fc',
                        borderRadius: '6px',
                        padding: '6px 14px',
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        marginTop: '6px'
                      }}
                    >
                      Ver {sectorMarkets.length} Catalizadores Sectoriales (SpaceX / NASA / Space Force)
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })()}

        {/* TAB 2: Social Feed */}
        {activeTab === 'social' && (
          <div>
            {/* Sentiment Summary Bar */}
            {detail.social_stats && detail.social_stats.total_posts > 0 ? (
              <div style={{ display: 'flex', justifyContent: 'space-around', background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '8px', marginBottom: '16px' }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>BULLISH</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--bullish-green)' }}>
                    {detail.social_stats.bullish_pct}%
                  </div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>NEUTRAL</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--neutral-yellow)' }}>
                    {detail.social_stats.neutral_pct}%
                  </div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>BEARISH</div>
                  <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--bearish-red)' }}>
                    {detail.social_stats.bearish_pct}%
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ textAlign: 'center', background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '8px', marginBottom: '16px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                No recent social posts collected in the analysis window (Anchor Baseline: 50.0)
              </div>
            )}

            <div className="tweets-feed">
              {detail.recent_posts && detail.recent_posts.length > 0 ? (
                detail.recent_posts.slice(0, 8).map((post) => (
                  <div key={post.id} className="tweet-card">
                    <div className="tweet-header">
                      <span>@{post.username}</span>
                      <span style={{ color: post.sentiment_label === 'BULLISH' ? 'var(--bullish-green)' : post.sentiment_label === 'BEARISH' ? 'var(--bearish-red)' : 'var(--neutral-yellow)' }}>
                        {post.sentiment_label} ({post.sentiment_score.toFixed(2)})
                      </span>
                    </div>
                    <div className="tweet-text">{post.text}</div>
                    {post.catalyst && (
                      <div style={{ marginTop: '6px', fontSize: '0.72rem', color: 'var(--accent-cyan)' }}>
                        ⚡ Catalyst: {post.catalyst}
                      </div>
                    )}
                  </div>
                ))
              ) : (
                <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)' }}>
                  No recent social posts collected.
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: News Feed */}
        {activeTab === 'news' && (
          <div className="tweets-feed">
            {detail.recent_news && detail.recent_news.length > 0 ? (
              detail.recent_news.map((item) => (
                <div key={item.id} className="tweet-card">
                  <div className="tweet-header">
                    <span style={{ fontWeight: 600, color: 'var(--accent-cyan)' }}>{item.source || 'News Source'}</span>
                    <span style={{ color: item.sentiment_label === 'BULLISH' ? 'var(--bullish-green)' : item.sentiment_label === 'BEARISH' ? 'var(--bearish-red)' : 'var(--neutral-yellow)' }}>
                      {item.sentiment_label}
                    </span>
                  </div>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: '#fff', textDecoration: 'none', fontWeight: 500, fontSize: '0.9rem', display: 'block', margin: '4px 0' }}
                  >
                    {item.title}
                  </a>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    Published: {new Date(item.published_at).toLocaleDateString()}
                  </span>
                </div>
              ))
            ) : (
              <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-muted)' }}>
                No recent news recorded for this ticker.
              </div>
            )}
          </div>
        )}

        {/* TAB 4: Active Divergences & WHY Explanations */}
        {activeTab === 'divergences' && (
          <div>
            {/* Active Divergences List */}
            {detail.divergences && detail.divergences.length > 0 ? (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ fontSize: '0.9rem', color: 'var(--accent-cyan)', marginBottom: '8px' }}>Active Market Divergences</h4>
                {detail.divergences.map((d) => (
                  <div
                    key={d.id}
                    style={{
                      background: d.direction === 'BULLISH' ? 'var(--bullish-bg)' : 'var(--bearish-bg)',
                      border: `1px solid ${d.direction === 'BULLISH' ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
                      padding: '12px',
                      borderRadius: '8px',
                      marginBottom: '8px'
                    }}
                  >
                    <div style={{ fontWeight: 700, fontSize: '0.85rem', color: d.direction === 'BULLISH' ? 'var(--bullish-green)' : 'var(--bearish-red)' }}>
                      [{d.type}] {d.direction}
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#fff', marginTop: '4px' }}>
                      {d.description}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ padding: '12px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', marginBottom: '16px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                No conflicting divergences detected. Social, Prediction, and Price indicators are currently in structural alignment.
              </div>
            )}

            {/* WHY? Reasons Box */}
            <div className="reasons-box">
              <h3 style={{ fontSize: '1rem', marginBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Zap size={18} color="var(--accent-cyan)" /> WHY THIS SIGNAL?
              </h3>
              {detail.reasons && detail.reasons.map((r, i) => {
                const isPos = r.startsWith('+');
                const isNeg = r.startsWith('-');
                return (
                  <div key={i} className={`reason-item ${isPos ? 'pos' : isNeg ? 'neg' : 'info'}`}>
                    {r}
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* TAB 5: Technical Data */}
        {activeTab === 'technical' && (
          <div className="tech-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))' }}>
            <div className="tech-item">
              <div className="tech-key">PRICE</div>
              <div className="tech-val">{detail.technical_data.price ? `$${detail.technical_data.price.toFixed(2)}` : 'N/A'}</div>
            </div>
            <div className="tech-item">
              <div className="tech-key">EMA 200</div>
              <div className="tech-val">{detail.technical_data.ema200 ? `$${detail.technical_data.ema200.toFixed(2)}` : 'N/A'}</div>
            </div>
            <div className="tech-item">
              <div className="tech-key">RSI (14)</div>
              <div className="tech-val">{detail.technical_data.rsi14 ? detail.technical_data.rsi14.toFixed(1) : 'N/A'}</div>
            </div>
            <div className="tech-item">
              <div className="tech-key">MACD HIST</div>
              <div className="tech-val">{detail.technical_data.macd_histogram ? detail.technical_data.macd_histogram.toFixed(2) : 'N/A'}</div>
            </div>
            <div className="tech-item">
              <div className="tech-key">ATR (14)</div>
              <div className="tech-val">{detail.technical_data.atr !== null && detail.technical_data.atr !== undefined ? `$${detail.technical_data.atr.toFixed(2)}` : 'N/A'}</div>
            </div>
            <div className="tech-item">
              <div className="tech-key">VOL RATIO</div>
              <div className="tech-val">{detail.technical_data.volume_ratio ? `${detail.technical_data.volume_ratio.toFixed(2)}x` : 'N/A'}</div>
            </div>
            <div className="tech-item">
              <div className="tech-key">TECH SCORE</div>
              <div className="tech-val">{detail.technical_data.technical_score !== null ? `${detail.technical_data.technical_score}/40` : 'N/A'}</div>
            </div>
            <div className="tech-item">
              <div className="tech-key">RISK / SAFETY</div>
              <div className="tech-val" style={{ color: detail.score_breakdown.risk_score !== null && detail.score_breakdown.risk_score !== undefined ? (detail.score_breakdown.risk_score >= 60 ? 'var(--bullish-green)' : detail.score_breakdown.risk_score <= 35 ? 'var(--bearish-red)' : 'var(--neutral-yellow)') : 'var(--text-muted)' }}>
                {detail.score_breakdown.risk_score !== null && detail.score_breakdown.risk_score !== undefined ? `${detail.score_breakdown.risk_score.toFixed(1)}/100` : 'N/A'}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
