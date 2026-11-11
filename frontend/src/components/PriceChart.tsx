import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
} from 'lightweight-charts';
import type { IChartApi, ISeriesApi, ISeriesMarkersPluginApi, SeriesMarker, Time } from 'lightweight-charts';
import { CandlesResponse, ChartMarker, PriceCandle } from '../types';

interface PriceChartProps {
  ticker: string;
  // Changes after each pipeline run, so the chart reloads with the new bar
  refreshKey?: string | null;
}

type RangeId = '3M' | '6M' | '1Y' | 'ALL';
const RANGE_SESSIONS: Record<RangeId, number | null> = { '3M': 63, '6M': 126, '1Y': 252, ALL: null };

// Chart palette (mirrors the CSS variables in App.css; the canvas cannot read them)
const COLORS = {
  up: '#10b981',
  down: '#ef4444',
  text: '#94a3b8',
  grid: 'rgba(255, 255, 255, 0.05)',
  border: '#1e2d4a',
  ema: '#f59e0b',
  bollinger: 'rgba(59, 130, 246, 0.75)',
  level: 'rgba(203, 213, 225, 0.55)',
  earnings: '#a855f7',
  neutral: '#cbd5e1',
};

const fmtNum = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(digits);

const fmtVolume = (v: number | null | undefined) => {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(Math.round(v));
};

const timeToKey = (t: Time | undefined): string | null => {
  if (t === undefined) return null;
  if (typeof t === 'string') return t;
  if (typeof t === 'number') return new Date(t * 1000).toISOString().slice(0, 10);
  return `${t.year}-${String(t.month).padStart(2, '0')}-${String(t.day).padStart(2, '0')}`;
};

const markerColor = (m: ChartMarker) => {
  if (m.kind === 'EARNINGS') return COLORS.earnings;
  if (m.direction === 'BEARISH') return COLORS.down;
  if (m.direction === 'BULLISH') return COLORS.up;
  return COLORS.neutral;
};

const toSeriesMarker = (m: ChartMarker): SeriesMarker<Time> => {
  if (m.kind === 'SIGNAL') {
    const bearish = m.direction === 'BEARISH';
    return {
      time: m.time,
      position: bearish ? 'aboveBar' : 'belowBar',
      shape: bearish ? 'arrowDown' : m.direction === 'BULLISH' ? 'arrowUp' : 'circle',
      color: markerColor(m),
    };
  }
  if (m.kind === 'CATALYST') {
    return { time: m.time, position: 'aboveBar', shape: 'circle', color: markerColor(m), text: '!' };
  }
  return { time: m.time, position: 'belowBar', shape: 'square', color: markerColor(m), text: 'E' };
};

const Toggle: React.FC<{ active: boolean; color: string; onClick: () => void; children: React.ReactNode }> = ({
  active, color, onClick, children,
}) => (
  <button
    type="button"
    onClick={onClick}
    aria-pressed={active}
    className="price-chart-pill"
    style={active ? { borderColor: color, color } : undefined}
  >
    <span className="price-chart-swatch" style={{ background: color }} />
    {children}
  </button>
);

export const PriceChart: React.FC<PriceChartProps> = ({ ticker, refreshKey }) => {
  const [data, setData] = useState<CandlesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<RangeId>('6M');
  const [showEma, setShowEma] = useState(true);
  const [showBollinger, setShowBollinger] = useState(false);
  const [showMarkers, setShowMarkers] = useState(true);
  const [hoverKey, setHoverKey] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const emaRef = useRef<ISeriesApi<'Line'> | null>(null);
  const bollingerRefs = useRef<ISeriesApi<'Line'>[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetch(`/api/tickers/${ticker}/candles?days=520`, { signal: controller.signal })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((body: CandlesResponse) => setData(body))
      .catch((err: Error) => {
        if (err.name === 'AbortError') return;
        setError(err.message || 'Network error');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [ticker, refreshKey]);

  const candles = useMemo<PriceCandle[]>(() => data?.candles ?? [], [data]);
  const markers = useMemo<ChartMarker[]>(() => data?.markers ?? [], [data]);
  const candleByTime = useMemo(() => new Map(candles.map((c) => [c.time, c])), [candles]);
  const markersByTime = useMemo(() => {
    const map = new Map<string, ChartMarker[]>();
    markers.forEach((m) => map.set(m.time, [...(map.get(m.time) ?? []), m]));
    return map;
  }, [markers]);

  // Build the chart once per dataset
  useEffect(() => {
    const el = containerRef.current;
    if (!el || candles.length === 0) return;

    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: COLORS.text,
        fontFamily: "'Inter', sans-serif",
        fontSize: 11,
      },
      grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      rightPriceScale: { borderColor: COLORS.border },
      timeScale: { borderColor: COLORS.border, rightOffset: 4 },
      crosshair: { mode: CrosshairMode.Normal },
    });
    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.up,
      downColor: COLORS.down,
      wickUpColor: COLORS.up,
      wickDownColor: COLORS.down,
      borderVisible: false,
      priceLineVisible: false,
    });
    candleSeries.setData(candles.map((c) => ({ time: c.time, open: c.open, high: c.high, low: c.low, close: c.close })));
    candleSeries.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.06 } });

    // Volume in its own pane, so the price axis never has to stretch below the lows
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceLineVisible: false,
      lastValueVisible: false,
    }, 1);
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
    volumeSeries.setData(
      candles
        .filter((c) => c.volume !== null)
        .map((c) => ({
          time: c.time,
          value: c.volume as number,
          color: c.close >= c.open ? 'rgba(16, 185, 129, 0.35)' : 'rgba(239, 68, 68, 0.35)',
        }))
    );

    const lineData = (pick: (c: PriceCandle) => number | null) =>
      candles.filter((c) => pick(c) !== null).map((c) => ({ time: c.time, value: pick(c) as number }));
    const overlay = (color: string, width: 1 | 2, style: LineStyle = LineStyle.Solid) =>
      chart.addSeries(LineSeries, {
        color,
        lineWidth: width,
        lineStyle: style,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });

    const ema = overlay(COLORS.ema, 2);
    ema.setData(lineData((c) => c.ema200));
    emaRef.current = ema;

    const upper = overlay(COLORS.bollinger, 1);
    upper.setData(lineData((c) => c.bb_upper));
    const middle = overlay(COLORS.bollinger, 1, LineStyle.Dashed);
    middle.setData(lineData((c) => c.bb_middle));
    const lower = overlay(COLORS.bollinger, 1);
    lower.setData(lineData((c) => c.bb_lower));
    bollingerRefs.current = [upper, middle, lower];

    const levels = data?.levels;
    if (levels?.high_52w) {
      candleSeries.createPriceLine({
        price: levels.high_52w, color: COLORS.level, lineWidth: 1, lineStyle: LineStyle.Dotted,
        axisLabelVisible: true, title: '52w high',
      });
    }
    if (levels?.low_52w) {
      candleSeries.createPriceLine({
        price: levels.low_52w, color: COLORS.level, lineWidth: 1, lineStyle: LineStyle.Dotted,
        axisLabelVisible: true, title: '52w low',
      });
    }

    markersRef.current = createSeriesMarkers(candleSeries, []);

    const panes = chart.panes();
    if (panes.length > 1) {
      panes[0].setStretchFactor(5);
      panes[1].setStretchFactor(1);
    }

    chart.subscribeCrosshairMove((param) => setHoverKey(timeToKey(param.time)));

    return () => {
      chartRef.current = null;
      emaRef.current = null;
      bollingerRefs.current = [];
      markersRef.current = null;
      chart.remove();
    };
  }, [candles, data]);

  // Overlay visibility
  useEffect(() => {
    emaRef.current?.applyOptions({ visible: showEma });
    bollingerRefs.current.forEach((s) => s.applyOptions({ visible: showBollinger }));
    markersRef.current?.setMarkers(showMarkers ? markers.map(toSeriesMarker) : []);
  }, [showEma, showBollinger, showMarkers, markers, candles]);

  // Visible window
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || candles.length === 0) return;
    const sessions = RANGE_SESSIONS[range];
    if (sessions === null || sessions >= candles.length) {
      chart.timeScale().fitContent();
      return;
    }
    chart.timeScale().setVisibleRange({
      from: candles[candles.length - sessions].time,
      to: candles[candles.length - 1].time,
    });
  }, [range, candles]);

  const hasEma = candles.some((c) => c.ema200 !== null);
  const last = candles.length > 0 ? candles[candles.length - 1] : null;
  const shown = (hoverKey && candleByTime.get(hoverKey)) || last;
  const shownIndex = shown ? candles.indexOf(shown) : -1;
  const prevClose = shownIndex > 0 ? candles[shownIndex - 1].close : null;
  const changePct = shown && prevClose ? ((shown.close - prevClose) / prevClose) * 100 : null;
  const shownMarkers = shown ? markersByTime.get(shown.time) ?? [] : [];

  return (
    <div className="price-chart">
      <div className="price-chart-header">
        <span className="price-chart-title">
          Daily Price Chart
          <span className="price-chart-subtitle"> · visual context, not an input of the SMI</span>
        </span>
        <div className="price-chart-controls">
          {(Object.keys(RANGE_SESSIONS) as RangeId[]).map((id) => (
            <button
              key={id}
              type="button"
              className={`price-chart-pill${range === id ? ' is-active' : ''}`}
              aria-pressed={range === id}
              onClick={() => setRange(id)}
            >
              {id}
            </button>
          ))}
          <span className="price-chart-separator" />
          {hasEma && (
            <Toggle active={showEma} color={COLORS.ema} onClick={() => setShowEma(!showEma)}>EMA200</Toggle>
          )}
          <Toggle active={showBollinger} color="#3b82f6" onClick={() => setShowBollinger(!showBollinger)}>Bollinger</Toggle>
          <Toggle active={showMarkers} color={COLORS.neutral} onClick={() => setShowMarkers(!showMarkers)}>Events</Toggle>
        </div>
      </div>

      {loading && candles.length === 0 && <div className="price-chart-empty">Loading price history…</div>}
      {error && candles.length === 0 && <div className="price-chart-empty">Price chart unavailable ({error}).</div>}
      {!loading && !error && candles.length === 0 && (
        <div className="price-chart-empty">
          No daily bars stored yet. They are saved on every pipeline run: run the analysis once to fill the chart.
        </div>
      )}

      {candles.length > 0 && shown && (
        <>
          <div className="price-chart-legend">
            <span className="price-chart-date">{shown.time}</span>
            <span>O <b>{fmtNum(shown.open)}</b></span>
            <span>H <b>{fmtNum(shown.high)}</b></span>
            <span>L <b>{fmtNum(shown.low)}</b></span>
            <span>C <b>{fmtNum(shown.close)}</b></span>
            {changePct !== null && (
              <span style={{ color: changePct >= 0 ? COLORS.up : COLORS.down }}>
                {changePct >= 0 ? '+' : ''}{changePct.toFixed(2)}%
              </span>
            )}
            <span>Vol <b>{fmtVolume(shown.volume)}</b></span>
            {showEma && shown.ema200 !== null && <span style={{ color: COLORS.ema }}>EMA200 {fmtNum(shown.ema200)}</span>}
            {data?.last_bar_partial && shown === last && <span className="price-chart-partial">session open: partial bar</span>}
          </div>

          <div ref={containerRef} className="price-chart-canvas" />

          <div className="price-chart-events">
            {showMarkers && shownMarkers.length > 0 ? (
              shownMarkers.map((m, i) => (
                <span key={`${m.kind}-${m.label}-${i}`} className="price-chart-event">
                  <span className="price-chart-dot" style={{ background: markerColor(m) }} />
                  <b>{m.kind === 'CATALYST' ? m.label.replace(/_/g, ' ') : m.kind}</b> {m.text}
                </span>
              ))
            ) : (
              <span className="price-chart-hint">
                Arrows: signal band changes (up bullish, down bearish, dot back to HOLD) · <span style={{ color: COLORS.down }}>!</span> bearish catalyst headline ·{' '}
                <span style={{ color: COLORS.earnings }}>E</span> earnings. Hover a bar for details.
              </span>
            )}
          </div>

          <div className="price-chart-footer">
            <span>52w range {fmtNum(data?.levels.low_52w)} – {fmtNum(data?.levels.high_52w)}</span>
            {data && data.levels.range_sessions < 252 && <span>({data.levels.range_sessions} sessions stored)</span>}
            {data?.next_earnings_date && <span>Next earnings {data.next_earnings_date}</span>}
            <span>Daily bars, regular session only (no pre/after-hours)</span>
          </div>
        </>
      )}
    </div>
  );
};
