import React, { useEffect, useState } from 'react';
import { TickerDetailResponse, HistoryPoint } from '../types';
import { HistoryChart } from './HistoryChart';
import {
  X, CheckCircle, AlertTriangle, MessageSquare, Newspaper,
  Zap, Layers, TrendingUp, DollarSign, Activity, Compass, ExternalLink, ShieldCheck
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

  const smiVal = detail.header.smi ?? detail.header.ssi ?? 50.0;
  const ssiVal = detail.header.ssi ?? 50.0;
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
              <div style={{ fontSize: '2rem', fontFamily: 'var(--font-heading)', fontWeight: 800, color: 'var(--accent-cyan)' }}>
                {smiVal.toFixed(1)} <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>/100</span>
              </div>
            </div>

            <div style={{ borderLeft: '1px solid var(--border-color)', paddingLeft: '16px' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase' }}>SSI (SOCIAL)</div>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--bullish-green)' }}>
                {ssiVal.toFixed(1)}
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
        <div className="tech-grid" style={{ marginBottom: '20px' }}>
          <div className="tech-item">
            <div className="tech-key">SOCIAL SSI (30%)</div>
            <div className="tech-val" style={{ color: 'var(--bullish-green)' }}>
              {detail.score_breakdown.social_score?.toFixed(1) ?? '--'}
            </div>
          </div>
          <div className="tech-item">
            <div className="tech-key">POLYMARKET PMS (15%)</div>
            <div className="tech-val" style={{ color: 'var(--accent-cyan)' }}>
              {detail.score_breakdown.prediction_score ? `${detail.score_breakdown.prediction_score.toFixed(1)}` : 'N/A'}
            </div>
          </div>
          <div className="tech-item">
            <div className="tech-key">NEWS / CATALYSTS (20%)</div>
            <div className="tech-val" style={{ color: '#f59e0b' }}>
              {detail.score_breakdown.news_score ? `${detail.score_breakdown.news_score.toFixed(1)}` : 'N/A'}
            </div>
          </div>
          <div className="tech-item">
            <div className="tech-key">MARKET MOMENTUM (20%)</div>
            <div className="tech-val" style={{ color: '#38bdf8' }}>
              {detail.score_breakdown.momentum_score ? `${detail.score_breakdown.momentum_score.toFixed(1)}` : 'N/A'}
            </div>
          </div>
          <div className="tech-item">
            <div className="tech-key">CONFIDENCE</div>
            <div className="tech-val" style={{ color: '#fff' }}>
              {detail.header.confidence ? `${detail.header.confidence.toFixed(0)}%` : '0%'}
            </div>
          </div>
          <div className="tech-item">
            <div className="tech-key">DATA QUALITY</div>
            <div className="tech-val" style={{ color: 'var(--accent-cyan)' }}>
              {detail.header.data_quality ? `${detail.header.data_quality.toFixed(0)}%` : '0%'}
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
        {activeTab === 'prediction' && (
          <div>
            {detail.prediction_markets && detail.prediction_markets.length > 0 ? (
              <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '12px' }}>
                {detail.prediction_markets.map((m) => (
                  <div
                    key={m.id}
                    style={{
                      background: 'rgba(255, 255, 255, 0.03)',
                      border: '1px solid var(--border-color)',
                      borderRadius: '10px',
                      padding: '16px'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
                      <div>
                        <span style={{ fontSize: '0.7rem', textTransform: 'uppercase', color: 'var(--accent-cyan)', fontWeight: 700 }}>
                          {m.category}
                        </span>
                        <h4 style={{ margin: '4px 0 8px 0', fontSize: '1rem', color: '#fff' }}>{m.title}</h4>
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
                          Quality: {m.quality_score}/100
                        </span>
                      </div>
                    </div>

                    {/* Probability Bar */}
                    <div style={{ margin: '12px 0 8px 0' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', fontWeight: 700, marginBottom: '4px' }}>
                        <span style={{ color: 'var(--bullish-green)' }}>YES: {m.yes_probability}%</span>
                        <span style={{ color: 'var(--bearish-red)' }}>NO: {m.no_probability}%</span>
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
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.76rem', color: 'var(--text-muted)', marginTop: '10px' }}>
                      <span>Vol: <b style={{ color: '#fff' }}>${(m.volume / 1000).toFixed(1)}k</b></span>
                      <span>Liquidity: <b style={{ color: '#fff' }}>${(m.liquidity / 1000).toFixed(1)}k</b></span>
                      <span>Spread: <b style={{ color: '#fff' }}>{(m.spread * 100).toFixed(1)}¢</b></span>
                      {m.url && (
                        <a href={m.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-cyan)', display: 'flex', alignItems: 'center', gap: '3px', textDecoration: 'none' }}>
                          View on Polymarket <ExternalLink size={12} />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)', background: 'rgba(0,0,0,0.2)', borderRadius: '8px' }}>
                No active Polymarket contracts mapped directly to this ticker yet.
              </div>
            )}
          </div>
        )}

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
          <div className="tech-grid">
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
              <div className="tech-key">VOL RATIO</div>
              <div className="tech-val">{detail.technical_data.volume_ratio ? `${detail.technical_data.volume_ratio.toFixed(2)}x` : 'N/A'}</div>
            </div>
            <div className="tech-item">
              <div className="tech-key">TECH SCORE</div>
              <div className="tech-val">{detail.technical_data.technical_score !== null ? `${detail.technical_data.technical_score}/40` : 'N/A'}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
