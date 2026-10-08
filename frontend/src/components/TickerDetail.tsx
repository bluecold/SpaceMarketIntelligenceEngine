import React, { useEffect, useState } from 'react';
import { TickerDetailResponse, HistoryPoint, PredictionMarketItem, formatWeight } from '../types';
import { HistoryChart } from './HistoryChart';
import { MessageSquare, Newspaper, Zap, Activity, Compass, ExternalLink, Target, Globe } from 'lucide-react';
import { fmt, fmtPrice, isNum, riskTone, Tone, useThresholds } from '../lib/scale';
import { Badge, DataFlags, EmptyState, Modal, Notice, ScoreValue, SignalPill } from './ui';

const FEED_PREVIEW_SIZE = 8;
const DESCRIPTION_CLAMP_CHARS = 220;

// Why a post does not feed the SSI (mirrors the exclusion reasons of calculate_social_score)
const EXCLUDED_REASON_LABELS: Record<string, string> = {
  language: 'language',
  spam: 'promo/spam',
  low_relevance: 'low relevance',
  duplicate: 'duplicate'
};

type TabId = 'prediction' | 'social' | 'news' | 'divergences' | 'technical';
type MarketFilter = 'ALL' | 'DIRECT' | 'SECTOR';
type FeedView = 'influential' | 'latest' | 'excluded';

const sentimentTone = (label: string): Tone =>
  label === 'BULLISH' ? 'strong-bull' : label === 'BEARISH' ? 'strong-bear' : 'neutral';

interface TickerDetailProps {
  ticker: string;
  onClose: () => void;
  lastUpdate?: string | null;
}

export const TickerDetail: React.FC<TickerDetailProps> = ({ ticker, onClose, lastUpdate }) => {
  const [detail, setDetail] = useState<TickerDetailResponse | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const [activeTab, setActiveTab] = useState<TabId>('social');
  const [feedView, setFeedView] = useState<FeedView>('influential');
  const [showAllPosts, setShowAllPosts] = useState(false);
  const thresholds = useThresholds();

  useEffect(() => {
    let isCancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const getJson = (url: string) =>
      fetch(url, { signal: controller.signal }).then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      });

    Promise.all([getJson(`/api/tickers/${ticker}`), getJson(`/api/tickers/${ticker}/history`)])
      .then(([detailData, historyData]) => {
        if (isCancelled) return;
        setDetail(detailData);
        setHistory(historyData.history || []);
      })
      .catch((err: Error) => {
        if (isCancelled || err.name === 'AbortError') return;
        console.error('Failed to load ticker details', err);
        setError(err.message || 'Network error');
      })
      .finally(() => {
        if (!isCancelled) setLoading(false);
      });

    return () => {
      isCancelled = true;
      controller.abort();
    };
  }, [ticker, lastUpdate, reloadKey]);

  if (!detail) {
    return (
      <Modal onClose={onClose} labelledBy="ticker-detail-title" className="modal-sm">
        <h2 id="ticker-detail-title" className="dialog-title">${ticker}</h2>
        {loading ? (
          <p className="page-status" role="status">Loading SMIE multi-source intelligence for ${ticker}...</p>
        ) : (
          <Notice kind="error" action={{ label: 'Retry', onClick: () => setReloadKey((k) => k + 1) }}>
            Could not load the details for ${ticker}{error ? ` (${error})` : ''}.
          </Notice>
        )}
      </Modal>
    );
  }

  const { header, score_breakdown: breakdown } = detail;
  const tickerUpper = detail.ticker.toUpperCase();
  const isDirectMarket = (m: PredictionMarketItem) => !!(m.is_direct || (m.ticker && m.ticker.toUpperCase() === tickerUpper));
  const directMarkets = (detail.prediction_markets || []).filter(isDirectMarket);
  const countedPosts = (detail.recent_posts || []).filter((p) => p.status !== 'excluded');

  const tabs: { id: TabId; icon: React.ReactNode; label: string }[] = [
    { id: 'social', icon: <MessageSquare size={16} />, label: `X Social Feed (${countedPosts.length})` },
    { id: 'news', icon: <Newspaper size={16} />, label: `News & Catalysts (${detail.recent_news?.length || 0})` },
    { id: 'prediction', icon: <Compass size={16} />, label: `Prediction Markets (${directMarkets.length})` },
    { id: 'divergences', icon: <Zap size={16} />, label: `Divergences & WHY (${detail.divergences?.length || 0})` },
    { id: 'technical', icon: <Activity size={16} />, label: 'Technicals' }
  ];

  const pillars: { key: string; label: string; value: number | null | undefined; tone?: Tone; empty?: string; title?: string }[] = [
    { key: 'social', label: 'Social SSI', value: breakdown.social_score },
    { key: 'prediction', label: 'Polymarket PMS', value: breakdown.prediction_score },
    { key: 'news', label: 'News / Catalysts', value: breakdown.news_score },
    { key: 'momentum', label: 'Market Momentum', value: breakdown.momentum_score },
    {
      key: 'fundamental',
      label: 'Fundamentals',
      value: breakdown.fundamental_score,
      empty: '— (no data)',
      title: 'Without fundamental data this pillar is excluded and its weight is redistributed across the SMI'
    },
    { key: 'risk', label: 'Risk / Safety', value: breakdown.risk_score, tone: riskTone(breakdown.risk_score, thresholds) }
  ];

  return (
    <Modal onClose={onClose} labelledBy="ticker-detail-title" className="modal-lg">
      {/* Header */}
      <div className="detail-header">
        <div>
          <div className="detail-title-row">
            <h2 id="ticker-detail-title" className="detail-ticker">${detail.ticker}</h2>
            <SignalPill signal={header.signal} baseSignal={header.base_signal} className="pill-lg" />
            <DataFlags isStale={header.is_stale} ageHours={header.data_age_hours} ageDigits={1} />
          </div>
          <p className="text-muted">{detail.name}</p>
        </div>

        <div className="detail-scores">
          <div>
            <div className="micro-label">SMI</div>
            <div className="detail-score-main">
              <ScoreValue value={header.smi} />
              {isNum(header.smi) && <span className="detail-score-unit">/100</span>}
            </div>
          </div>
          <div className="detail-score-divider">
            <div className="micro-label">SSI (Social)</div>
            <ScoreValue value={header.ssi} className="detail-score-sub" />
          </div>
          <div className="detail-score-divider">
            <div className="micro-label">PMS (Polymarket)</div>
            <ScoreValue value={header.pms} className="detail-score-sub" />
          </div>
        </div>
      </div>

      <div className="detail-section">
        <HistoryChart data={history} />
      </div>

      {/* Pillars */}
      <div className="detail-section">
        <div className="pillars-header">
          <span className="eyebrow">SMIE Multi-Factor Pillars</span>
          <div className="pillars-meta">
            <span>Confidence: <strong className="text-strong">{fmt(header.confidence, 0, '0')}%</strong></span>
            <span>Data Quality: <strong className="tone-accent">{fmt(header.data_quality, 0, '0')}%</strong></span>
            {detail.sample_counts && (
              <span title="Posts / News / Markets used">
                Data Depth: <strong className="text-strong">{detail.sample_counts.post_count}P / {detail.sample_counts.news_count}N / {detail.sample_counts.prediction_count}M</strong>
              </span>
            )}
          </div>
        </div>
        <div className="tech-grid">
          {pillars.map((p) => (
            <div key={p.key} className="tech-item" title={p.title}>
              <div className="tech-key">{p.label} ({formatWeight(detail.engine, p.key)})</div>
              <div className="tech-val">
                {isNum(p.value) || !p.empty ? <ScoreValue value={p.value} tone={p.tone} /> : <span className="tone-none text-sm">{p.empty}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="tabs" role="tablist" aria-label={`${detail.ticker} detail sections`}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      <div role="tabpanel" id={`panel-${activeTab}`} aria-labelledby={`tab-${activeTab}`}>
        {activeTab === 'prediction' && (
          <PredictionTab
            detail={detail}
            isDirectMarket={isDirectMarket}
          />
        )}

        {activeTab === 'social' && (
          <SocialTab
            detail={detail}
            feedView={feedView}
            onFeedViewChange={(view) => { setFeedView(view); setShowAllPosts(false); }}
            showAll={showAllPosts}
            onToggleShowAll={() => setShowAllPosts(!showAllPosts)}
          />
        )}

        {activeTab === 'news' && (
          <div className="tweets-feed">
            {detail.recent_news && detail.recent_news.length > 0 ? (
              detail.recent_news.map((item) => (
                <div key={item.id} className="tweet-card">
                  <div className="tweet-header">
                    <span className="strong tone-accent">{item.source || 'News Source'}</span>
                    <span className={`tone-${sentimentTone(item.sentiment_label)}`}>{item.sentiment_label}</span>
                  </div>
                  <a href={item.url} target="_blank" rel="noopener noreferrer" className="news-link">
                    {item.title}
                  </a>
                  <span className="text-muted text-xs">Published: {new Date(item.published_at).toLocaleDateString()}</span>
                </div>
              ))
            ) : (
              <EmptyState>No recent news recorded for this ticker.</EmptyState>
            )}
          </div>
        )}

        {activeTab === 'divergences' && (
          <div>
            {detail.divergences && detail.divergences.length > 0 ? (
              <div className="detail-section">
                <h4 className="subsection-title">Active Market Divergences</h4>
                {detail.divergences.map((d) => (
                  <div key={d.id} className={`divergence-card ${d.direction === 'BULLISH' ? 'is-bull' : 'is-bear'}`}>
                    <div className="divergence-title">[{d.type}] {d.direction}</div>
                    <div className="divergence-desc">{d.description}</div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState className="detail-section">
                No conflicting divergences detected. Social, Prediction, and Price indicators are currently in structural alignment.
              </EmptyState>
            )}

            <div className="reasons-box">
              <h3 className="reasons-title">
                <Zap size={18} color="var(--accent-cyan)" /> WHY THIS SIGNAL?
              </h3>
              {detail.reasons?.map((r, i) => (
                <div key={i} className={`reason-item ${r.startsWith('+') ? 'pos' : r.startsWith('-') ? 'neg' : 'info'}`}>
                  {r}
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'technical' && (
          <div className="tech-grid">
            <TechItem label="Price" value={fmtPrice(detail.technical_data.price, 'N/A')} />
            <TechItem label="EMA 200" value={fmtPrice(detail.technical_data.ema200, 'N/A')} />
            <TechItem label="RSI (14)" value={fmt(detail.technical_data.rsi14, 1, 'N/A')} />
            <TechItem label="MACD Hist" value={fmt(detail.technical_data.macd_histogram, 2, 'N/A')} />
            <TechItem label="ATR (14)" value={isNum(detail.technical_data.atr) ? `$${detail.technical_data.atr.toFixed(2)}` : 'N/A'} />
            <TechItem label="Vol Ratio" value={isNum(detail.technical_data.volume_ratio) ? `${detail.technical_data.volume_ratio.toFixed(2)}x` : 'N/A'} />
            <TechItem label="Tech Score" value={isNum(detail.technical_data.technical_score) ? `${detail.technical_data.technical_score}/40` : 'N/A'} />
            <div className="tech-item">
              <div className="tech-key">Risk / Safety</div>
              <div className="tech-val">
                <ScoreValue value={breakdown.risk_score} suffix="/100" tone={riskTone(breakdown.risk_score, thresholds)} />
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};

const TechItem: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="tech-item">
    <div className="tech-key">{label}</div>
    <div className="tech-val">{value}</div>
  </div>
);

// --- Prediction markets tab -------------------------------------------------

interface PredictionTabProps {
  detail: TickerDetailResponse;
  isDirectMarket: (m: PredictionMarketItem) => boolean;
}

const PredictionTab: React.FC<PredictionTabProps> = ({ detail, isDirectMarket }) => {
  const directMarkets = (detail.prediction_markets || []).filter(isDirectMarket);

  return (
    <div>
      <div className="toolbar">
        <div className="chip-group" role="group" aria-label="Market filter">
          <button
            type="button"
            className="chip chip-bull active"
          >
            <Target size={12} />
            <span>Direct Contracts ${detail.ticker} ({directMarkets.length})</span>
          </button>
        </div>
        <div className="text-muted text-xs">
          Weighted PMS: <ScoreValue value={detail.header.pms} suffix="/100" className="strong" />
        </div>
      </div>

      {directMarkets.length > 0 ? (
        <div className="market-list">
          {directMarkets.map((m) => (
            <MarketCard key={m.id} market={m} ticker={detail.ticker} isDirect={true} />
          ))}
        </div>
      ) : (
        <EmptyState className="empty-dashed">
          <p>
            There are currently no Polymarket contracts specific to ${detail.ticker}.
          </p>
          <p className="text-muted text-xs" style={{ marginTop: '0.5rem' }}>
            Polymarket prediction score (PMS) is excluded from the SMI calculation and its weight is redistributed across other active pillars.
          </p>
        </EmptyState>
      )}
    </div>
  );
};

const MarketCard: React.FC<{ market: PredictionMarketItem; ticker: string; isDirect: boolean }> = ({ market: m, ticker, isDirect }) => {
  const [expanded, setExpanded] = useState(false);
  const impactBeta = isNum(m.impact_weight) ? m.impact_weight : null;
  const isLong = (m.description?.length ?? 0) > DESCRIPTION_CLAMP_CHARS;

  return (
    <div className={`market-card ${isDirect ? 'is-direct' : 'is-sector'}`}>
      <div className="market-card-top">
        <div className="badge-row">
          {isDirect ? (
            <Badge variant="bull" className="strong"><Target size={11} /> DIRECT CONTRACT ${ticker}</Badge>
          ) : (
            <Badge variant="purple" className="strong"><Globe size={11} /> SECTOR CATALYST ({m.ticker || 'SPCX / Macro'})</Badge>
          )}
          {!isDirect && impactBeta !== null && (
            <Badge variant={impactBeta >= 0 ? 'info' : 'bear'} title="Estimated impact of this event on the ticker">
              Beta on ${ticker}: {impactBeta >= 0 ? '+' : ''}{(impactBeta * 100).toFixed(0)}%
            </Badge>
          )}
          <span className="micro-label">{m.category}</span>
        </div>
        <Badge variant={m.quality_score >= 50 ? 'muted' : 'degraded'} title="Market quality: liquidity, volume and spread">
          Quality: {m.quality_score.toFixed(0)}/100
        </Badge>
      </div>

      <h4 className="market-title">{m.title}</h4>
      {m.description && (
        <>
          <p className={`market-desc ${isLong && !expanded ? 'clamped' : ''}`}>{m.description}</p>
          {isLong && (
            <button type="button" className="link-btn" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </>
      )}

      <div className="prob">
        <div className="prob-labels">
          <span className="tone-strong-bull">YES: {m.yes_probability.toFixed(1)}%</span>
          <span className="tone-strong-bear">NO: {m.no_probability.toFixed(1)}%</span>
        </div>
        <div
          className="prob-track"
          role="meter"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={m.yes_probability}
          aria-label="YES probability"
        >
          <div className="prob-fill" style={{ width: `${m.yes_probability}%` }} />
        </div>
      </div>

      <div className="market-metrics">
        <span>Vol: <b className="text-strong">${(m.volume / 1000).toFixed(1)}k</b></span>
        <span>Liquidity: <b className="text-strong">${(m.liquidity / 1000).toFixed(1)}k</b></span>
        <span>Spread: <b className="text-strong">{(m.spread * 100).toFixed(1)}¢</b></span>
        {m.url && (
          <a href={m.url} target="_blank" rel="noopener noreferrer" className="ext-link">
            View on Polymarket <ExternalLink size={12} />
          </a>
        )}
      </div>
    </div>
  );
};

// --- Social feed tab --------------------------------------------------------

interface SocialTabProps {
  detail: TickerDetailResponse;
  feedView: FeedView;
  onFeedViewChange: (view: FeedView) => void;
  showAll: boolean;
  onToggleShowAll: () => void;
}

const SocialTab: React.FC<SocialTabProps> = ({ detail, feedView, onFeedViewChange, showAll, onToggleShowAll }) => {
  const stats = detail.social_stats;
  const allPosts = detail.recent_posts || [];
  // Posts without a status come from an older API: treat them as counted
  const counted = allPosts.filter((p) => p.status !== 'excluded');
  const excluded = allPosts.filter((p) => p.status === 'excluded');
  const latest = [...counted].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  const list = { influential: counted, latest, excluded }[feedView];
  const visible = showAll ? list : list.slice(0, FEED_PREVIEW_SIZE);
  const maxShare = Math.max(1, ...counted.map((p) => p.vote_share || 0));
  const excludedSummary = Object.entries(stats?.excluded_post_counts || {})
    .map(([reason, n]) => `${n} ${EXCLUDED_REASON_LABELS[reason] || reason}`)
    .join(', ');

  const views: { id: FeedView; label: string }[] = [
    { id: 'influential', label: 'Most influential' },
    { id: 'latest', label: 'Latest' },
    { id: 'excluded', label: `Excluded (${excluded.length})` }
  ];

  return (
    <div>
      {stats && stats.total_posts > 0 ? (
        <div className="sentiment-summary">
          <div><div className="micro-label">Bullish</div><div className="sentiment-pct tone-strong-bull">{stats.bullish_pct}%</div></div>
          <div><div className="micro-label">Neutral</div><div className="sentiment-pct tone-neutral">{stats.neutral_pct}%</div></div>
          <div><div className="micro-label">Bearish</div><div className="sentiment-pct tone-strong-bear">{stats.bearish_pct}%</div></div>
        </div>
      ) : (
        <EmptyState className="detail-section">
          No recent social posts collected in the analysis window (SSI anchors to its 14-day baseline, 50 = normal).
        </EmptyState>
      )}

      <div className="toolbar">
        <div className="chip-group" role="group" aria-label="Feed view">
          {views.map((v) => (
            <button
              key={v.id}
              type="button"
              aria-pressed={feedView === v.id}
              className={`chip chip-accent ${feedView === v.id ? 'active' : ''}`}
              onClick={() => onFeedViewChange(v.id)}
            >
              {v.label}
            </button>
          ))}
        </div>
        <span className="text-muted text-xs">
          {counted.length} count toward the SSI
          {excluded.length > 0 ? ` · ${excluded.length} excluded${excludedSummary ? ` (${excludedSummary})` : ''}` : ''}
        </span>
      </div>

      <div className={`tweets-feed ${showAll ? 'scrollable' : ''}`}>
        {visible.length > 0 ? (
          visible.map((post) => {
            const isExcluded = post.status === 'excluded';
            const isOpinion = post.sentiment_label === 'BULLISH' || post.sentiment_label === 'BEARISH';
            const tone = sentimentTone(post.sentiment_label);
            return (
              <div key={`${post.id}-${post.created_at}`} className={`tweet-card ${isExcluded ? 'is-excluded' : ''}`}>
                <div className="tweet-header">
                  <span>@{post.username}</span>
                  {isExcluded ? (
                    <span className="strong">Excluded: {EXCLUDED_REASON_LABELS[post.excluded_reason || ''] || post.excluded_reason}</span>
                  ) : (
                    <span className={`tone-${tone}`}>{post.sentiment_label} ({post.sentiment_score.toFixed(2)})</span>
                  )}
                </div>
                <div className="tweet-text">{post.text}</div>
                {!isExcluded && (isOpinion ? (
                  <div className="vote-share" title="Share of the opinion weight behind the SSI">
                    <div className="vote-share-track">
                      <div
                        className={`vote-share-fill bg-${tone}`}
                        style={{ width: `${Math.min(100, ((post.vote_share || 0) / maxShare) * 100)}%` }}
                      />
                    </div>
                    <span className="text-muted text-2xs nowrap">{(post.vote_share || 0).toFixed(1)}% of SSI vote</span>
                  </div>
                ) : (
                  <div className="text-muted text-2xs tweet-note">Neutral · counts as a mention, does not vote</div>
                ))}
                {post.catalyst && !isExcluded && (
                  <div className="tone-accent text-xs tweet-note">⚡ Catalyst: {post.catalyst}</div>
                )}
              </div>
            );
          })
        ) : (
          <EmptyState>
            {feedView === 'excluded' ? 'No posts were excluded in the analysis window.' : 'No recent social posts collected.'}
          </EmptyState>
        )}
      </div>

      {list.length > FEED_PREVIEW_SIZE && (
        <button type="button" className="btn-outline-full" onClick={onToggleShowAll}>
          {showAll ? 'Show less' : `Show all (${list.length})`}
        </button>
      )}
    </div>
  );
};
