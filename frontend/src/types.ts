export interface AlertItem {
  id?: string;
  ticker: string;
  type: string;
  category?: 'SIGNAL' | 'DIVERGENCE' | 'CATALYST' | 'SYSTEM' | string;
  level: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'WARNING';
  message: string;
  timestamp?: string | null;
  age_hours?: number | null;
  is_active?: boolean;
}

export interface RankingItem {
  ticker: string;
  name: string;
  smi: number | null;                // Space Market Intelligence Index (0-100)
  ssi: number | null;                // Space Sentiment Index (Social 0-100)
  pms: number | null;         // Prediction Market Score (0-100)
  market_score: number | null;// Technical Market Score (0-100)
  delta_1d: number | null;
  social_score: number | null;
  prediction_score: number | null;
  news_score: number | null;
  momentum_score: number | null;
  risk_score: number | null;
  technical_score: number | null;
  signal: string;             // STRONG BUY, BUY, WATCH, HOLD, AVOID, STRONG AVOID (can include modifier)
  base_signal?: string;       // STRONG BUY, BUY, WATCH, HOLD, AVOID, STRONG AVOID
  signal_modifier?: string | null; // OVEREXTENDED, NO MKT DATA, etc.
  divergence?: string;
  confidence: number;         // 0-100%
  data_quality: number;       // 0-100%
  data_completeness: number;
  post_count?: number | null;
  news_count?: number | null;
  prediction_count?: number | null;
  price: number | null;
  market_status: string;
  timestamp: string | null;
  data_age_hours?: number | null;
  is_stale?: boolean;
}

export interface DashboardResponse {
  title: string;
  last_update: string | null;
  count: number;
  rankings: RankingItem[];
  alerts?: AlertItem[];
}

export interface SocialPost {
  id: string;
  username: string;
  text: string;
  url: string | null;
  created_at: string;
  sentiment_score: number;
  sentiment_label: string;
  confidence: number;
  likes: number;
  reposts: number;
  replies: number;
  views: number;
  relevance: number;
  catalyst: string | null;
  catalyst_importance?: string;
}

export interface NewsItem {
  id: number;
  title: string;
  source: string | null;
  url: string;
  published_at: string;
  sentiment_score: number;
  sentiment_label: string;
  relevance: number;
  catalyst: string | null;
  catalyst_importance?: string;
}

export interface PredictionMarketItem {
  id: string;
  title: string;
  description: string | null;
  category: string;
  yes_probability: number;   // 0 - 100%
  no_probability: number;    // 0 - 100%
  volume: number;            // USD
  liquidity: number;         // USD
  spread: number;
  quality_score: number;     // 0 - 100
  url: string | null;
  ticker?: string | null;
  is_direct?: boolean;
  event_role?: 'DIRECT' | 'SECTOR_CATALYST';
  impact_weight?: number | null;
  event_key?: string | null;
}

export interface DivergenceItem {
  id: number;
  type: string;
  direction: string;
  strength: number;
  confidence: number;
  description: string;
  timestamp: string;
}

export interface CatalystItem {
  category: string;
  direction: string;
  importance: string;
}

export interface TechnicalData {
  price: number | null;
  market_status: string;
  ema200: number | null;
  rsi14: number | null;
  bollinger_upper: number | null;
  bollinger_middle: number | null;
  bollinger_lower: number | null;
  macd_line: number | null;
  macd_signal: number | null;
  macd_histogram: number | null;
  volume_ma20: number | null;
  volume_ratio: number | null;
  atr: number | null;
  technical_score: number | null;
}

export interface TickerDetailResponse {
  ticker: string;
  name: string;
  header: {
    smi: number;
    ssi: number;
    pms: number | null;
    signal: string;
    base_signal?: string;
    signal_modifier?: string | null;
    confidence: number;
    data_quality: number;
    data_completeness: number;
    smi_momentum_1d: number;
    price: number | null;
    timestamp?: string | null;
    data_age_hours?: number | null;
    is_stale?: boolean;
  };
  score_breakdown: {
    social_score: number;
    prediction_score: number | null;
    news_score: number | null;
    momentum_score: number | null;
    technical_score: number | null;
    scaled_technical: number | null;
    risk_score: number | null;
    fundamental_score: number | null;
  };
  sample_counts?: {
    post_count: number;
    news_count: number;
    prediction_count: number;
  };
  social_stats: {
    total_posts: number;
    relevant_posts: number;
    bullish_pct: number;
    neutral_pct: number;
    bearish_pct: number;
    weighted_bullish_pct?: number;
    weighted_neutral_pct?: number;
    weighted_bearish_pct?: number;
  };
  technical_data: TechnicalData;
  catalysts: CatalystItem[];
  prediction_markets: PredictionMarketItem[];
  divergences: DivergenceItem[];
  reasons: string[];
  explanation: string;
  recent_posts: SocialPost[];
  recent_news: NewsItem[];
}

export interface HistoryPoint {
  timestamp: string;
  price: number | null;
  smi: number;
  ssi: number;
  pms: number | null;
  social_score: number;
  news_score?: number | null;
  momentum_score?: number | null;
  risk_score?: number | null;
  volume: number | null;
  signal: string;
}

export interface HistoryResponse {
  ticker: string;
  name: string;
  count: number;
  history: HistoryPoint[];
}
