import React, { useState, useMemo } from 'react';
import { HistoryPoint } from '../types';

interface HistoryChartProps {
  data: HistoryPoint[];
}

export const HistoryChart: React.FC<HistoryChartProps> = ({ data }) => {
  const [hoveredPoint, setHoveredPoint] = useState<HistoryPoint | null>(null);
  const [hoverPos, setHoverPos] = useState<{ x: number; y: number } | null>(null);

  // Series visibility toggles
  const [showPrice, setShowPrice] = useState(true);
  const [showSMI, setShowSMI] = useState(true);
  const [showSSI, setShowSSI] = useState(true);
  const [showPMS, setShowPMS] = useState(true);

  const safeData = data || [];

  const width = 800;
  const height = 240;
  const padding = { top: 20, right: 55, bottom: 38, left: 45 };

  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;
  const bottomY = padding.top + chartH;

  // Real continuous timeline mapping
  const { minTime, maxTime, timeSpan } = useMemo(() => {
    if (!safeData || safeData.length === 0) {
      return { minTime: 0, maxTime: 1, timeSpan: 1 };
    }
    const times = safeData.map((d) => new Date(d.timestamp).getTime()).filter((t) => !isNaN(t));
    const minT = times.length > 0 ? Math.min(...times) : 0;
    const maxT = times.length > 0 ? Math.max(...times) : 1;
    return { minTime: minT, maxTime: maxT, timeSpan: maxT - minT || 1 };
  }, [safeData]);

  // X scale: Continuous time projection with index fallback
  const getX = (item: HistoryPoint, index: number): number => {
    if (safeData.length <= 1 || timeSpan === 0) return padding.left + chartW / 2;
    const t = new Date(item.timestamp).getTime();
    if (isNaN(t)) {
      return padding.left + (index / (Math.max(1, safeData.length - 1))) * chartW;
    }
    return padding.left + ((t - minTime) / timeSpan) * chartW;
  };

  // Y scale for 0-100 Scores (SMI, SSI, PMS)
  const getY_Score = (score: number | null | undefined): number | null => {
    if (score === null || score === undefined || isNaN(score)) return null;
    const clamped = Math.max(0, Math.min(100, score));
    return padding.top + chartH - (clamped / 100) * chartH;
  };

  // Y scale for Price (minPrice to maxPrice)
  const validPrices = useMemo(
    () => safeData.map((d) => d.price).filter((p): p is number => p !== null && p !== undefined && p > 0),
    [safeData]
  );
  const minPrice = validPrices.length > 0 ? Math.min(...validPrices) * 0.95 : 0;
  const maxPrice = validPrices.length > 0 ? Math.max(...validPrices) * 1.05 : 100;
  const priceRange = maxPrice - minPrice || 1;

  const getY_Price = (price: number | null | undefined): number | null => {
    if (price === null || price === undefined || price <= 0 || isNaN(price)) return null;
    return padding.top + chartH - ((price - minPrice) / priceRange) * chartH;
  };

  // Helper: Generates discontinuous SVG polyline path, splitting on null values or gaps > 48h
  const buildSegmentedPath = (
    getYCoord: (p: HistoryPoint) => number | null,
    maxGapHours: number = 48
  ): string => {
    if (safeData.length === 0) return '';
    const maxGapMs = maxGapHours * 3600 * 1000;
    let path = '';
    let inSegment = false;
    let prevTime: number | null = null;

    safeData.forEach((pt, i) => {
      const y = getYCoord(pt);
      const t = new Date(pt.timestamp).getTime();

      if (y === null) {
        inSegment = false;
        prevTime = null;
        return;
      }

      const isGap = prevTime !== null && !isNaN(t) && t - prevTime > maxGapMs;
      const x = getX(pt, i);

      if (!inSegment || isGap) {
        path += `${path ? ' ' : ''}M ${x.toFixed(1)},${y.toFixed(1)}`;
        inSegment = true;
      } else {
        path += ` L ${x.toFixed(1)},${y.toFixed(1)}`;
      }

      prevTime = !isNaN(t) ? t : null;
    });

    return path;
  };

  // Helper: Generates discontinuous SVG area path
  const buildSegmentedArea = (
    getYCoord: (p: HistoryPoint) => number | null,
    maxGapHours: number = 48
  ): string => {
    if (safeData.length === 0) return '';
    const maxGapMs = maxGapHours * 3600 * 1000;
    let fullArea = '';
    let currentSeg: { x: number; y: number }[] = [];
    let prevTime: number | null = null;

    const flushSegment = () => {
      if (currentSeg.length > 1) {
        const first = currentSeg[0];
        const last = currentSeg[currentSeg.length - 1];
        const segPath = `M ${first.x.toFixed(1)},${bottomY} L ${currentSeg
          .map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`)
          .join(' L ')} L ${last.x.toFixed(1)},${bottomY} Z`;
        fullArea += `${fullArea ? ' ' : ''}${segPath}`;
      }
      currentSeg = [];
    };

    safeData.forEach((pt, i) => {
      const y = getYCoord(pt);
      const t = new Date(pt.timestamp).getTime();

      if (y === null) {
        flushSegment();
        prevTime = null;
        return;
      }

      const isGap = prevTime !== null && !isNaN(t) && t - prevTime > maxGapMs;
      if (isGap) {
        flushSegment();
      }

      const x = getX(pt, i);
      currentSeg.push({ x, y });
      prevTime = !isNaN(t) ? t : null;
    });

    flushSegment();
    return fullArea;
  };

  // Segmented Paths
  const smiPath = useMemo(() => buildSegmentedPath((d) => getY_Score(d.smi ?? d.ssi)), [safeData, minTime, maxTime]);
  const smiAreaPath = useMemo(() => buildSegmentedArea((d) => getY_Score(d.smi ?? d.ssi)), [safeData, minTime, maxTime]);
  const ssiPath = useMemo(() => buildSegmentedPath((d) => getY_Score(d.ssi ?? d.social_score)), [safeData, minTime, maxTime]);
  const pmsPath = useMemo(() => buildSegmentedPath((d) => getY_Score(d.pms)), [safeData, minTime, maxTime]);
  const pricePath = useMemo(() => buildSegmentedPath((d) => getY_Price(d.price)), [safeData, minTime, maxTime, validPrices]);

  // Date formatters for continuous timeline axis
  const formatTimeLabel = (timestampMs: number): string => {
    if (!timestampMs || isNaN(timestampMs)) return '';
    const d = new Date(timestampMs);
    return d.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
  };

  if (!data || data.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)', background: 'rgba(0,0,0,0.2)', borderRadius: '12px' }}>
        No historical snapshot data available yet. Run analysis to start accumulating history points.
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', width: '100%', background: 'rgba(11, 15, 25, 0.6)', borderRadius: '14px', border: '1px solid var(--border-color)', padding: '14px' }}>
      {/* Top Header & Series Toggles */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', padding: '0 4px', flexWrap: 'wrap', gap: '8px' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>
          Interactive Multi-Series Timeline ({data.length} snapshots)
        </span>

        {/* Toggle Pills */}
        <div style={{ display: 'flex', gap: '8px', fontSize: '0.75rem', flexWrap: 'wrap' }}>
          {/* Price Toggle */}
          <button
            onClick={() => setShowPrice(!showPrice)}
            style={{
              background: showPrice ? 'rgba(245, 158, 11, 0.15)' : 'transparent',
              border: `1px solid ${showPrice ? '#f59e0b' : 'var(--border-color)'}`,
              color: showPrice ? '#f59e0b' : 'var(--text-muted)',
              padding: '3px 8px', borderRadius: '6px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '5px'
            }}
          >
            <span style={{ width: '8px', height: '3px', background: '#f59e0b', display: 'inline-block', borderRadius: '2px' }} />
            Price ($)
          </button>

          {/* SMI Toggle */}
          <button
            onClick={() => setShowSMI(!showSMI)}
            style={{
              background: showSMI ? 'rgba(168, 85, 247, 0.15)' : 'transparent',
              border: `1px solid ${showSMI ? '#a855f7' : 'var(--border-color)'}`,
              color: showSMI ? '#a855f7' : 'var(--text-muted)',
              padding: '3px 8px', borderRadius: '6px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '5px'
            }}
          >
            <span style={{ width: '8px', height: '3px', background: '#a855f7', display: 'inline-block', borderRadius: '2px' }} />
            SMI Integral
          </button>

          {/* SSI Toggle */}
          <button
            onClick={() => setShowSSI(!showSSI)}
            style={{
              background: showSSI ? 'rgba(16, 185, 129, 0.15)' : 'transparent',
              border: `1px solid ${showSSI ? 'var(--bullish-green)' : 'var(--border-color)'}`,
              color: showSSI ? 'var(--bullish-green)' : 'var(--text-muted)',
              padding: '3px 8px', borderRadius: '6px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '5px'
            }}
          >
            <span style={{ width: '8px', height: '3px', background: 'var(--bullish-green)', display: 'inline-block', borderRadius: '2px' }} />
            SSI Social
          </button>

          {/* PMS Toggle */}
          <button
            onClick={() => setShowPMS(!showPMS)}
            style={{
              background: showPMS ? 'rgba(0, 229, 255, 0.15)' : 'transparent',
              border: `1px solid ${showPMS ? 'var(--accent-cyan)' : 'var(--border-color)'}`,
              color: showPMS ? 'var(--accent-cyan)' : 'var(--text-muted)',
              padding: '3px 8px', borderRadius: '6px', cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: '5px'
            }}
          >
            <span style={{ width: '8px', height: '3px', background: 'var(--accent-cyan)', display: 'inline-block', borderRadius: '2px' }} />
            PMS Prediction
          </button>
        </div>
      </div>

      {/* Main SVG Container */}
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: '100%', height: 'auto', overflow: 'visible' }}
        onMouseLeave={() => { setHoveredPoint(null); setHoverPos(null); }}
      >
        <defs>
          <linearGradient id="smiGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#a855f7" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#a855f7" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Horizontal Grid lines (0, 25, 50, 75, 100) */}
        {[0, 25, 50, 75, 100].map((val) => {
          const y = padding.top + chartH - (val / 100) * chartH;
          return (
            <g key={val}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
              <text x={padding.left - 8} y={y + 3} fill="var(--text-dim)" fontSize="10" textAnchor="end">{val}</text>
            </g>
          );
        })}

        {/* Bottom Time Axis Ticks */}
        {timeSpan > 0 && (
          <g>
            <text x={padding.left} y={bottomY + 18} fill="var(--text-dim)" fontSize="9.5" textAnchor="start">
              {formatTimeLabel(minTime)}
            </text>
            {data.length > 2 && (
              <text x={padding.left + chartW / 2} y={bottomY + 18} fill="var(--text-dim)" fontSize="9.5" textAnchor="middle">
                {formatTimeLabel(minTime + timeSpan / 2)}
              </text>
            )}
            <text x={width - padding.right} y={bottomY + 18} fill="var(--text-dim)" fontSize="9.5" textAnchor="end">
              {formatTimeLabel(maxTime)}
            </text>
          </g>
        )}

        {/* Right Y-Axis for Price ($) */}
        {validPrices.length > 0 && showPrice && (
          <g>
            <text x={width - padding.right + 8} y={padding.top + 3} fill="#f59e0b" fontSize="10" textAnchor="start">
              ${maxPrice.toFixed(1)}
            </text>
            <text x={width - padding.right + 8} y={padding.top + chartH + 3} fill="#f59e0b" fontSize="10" textAnchor="start">
              ${minPrice.toFixed(1)}
            </text>
          </g>
        )}

        {/* SMI Shaded Area & Line */}
        {showSMI && smiAreaPath && (
          <path d={smiAreaPath} fill="url(#smiGradient)" />
        )}
        {showSMI && smiPath && (
          <path d={smiPath} fill="none" stroke="#a855f7" strokeWidth="2.5" strokeLinecap="round" />
        )}

        {/* SSI Line (Green) */}
        {showSSI && ssiPath && (
          <path d={ssiPath} fill="none" stroke="var(--bullish-green)" strokeWidth="1.8" strokeDasharray="4 2" strokeLinecap="round" />
        )}

        {/* PMS Line (Cyan) */}
        {showPMS && pmsPath && (
          <path d={pmsPath} fill="none" stroke="var(--accent-cyan)" strokeWidth="1.8" strokeLinecap="round" />
        )}

        {/* Price Line (Amber) */}
        {showPrice && pricePath && (
          <path d={pricePath} fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" />
        )}

        {/* Data Point Hover Hotspots */}
        {data.map((pt, i) => {
          const x = getX(pt, i);
          const ySmi = getY_Score(pt.smi ?? pt.ssi);
          return (
            <g key={i}>
              {ySmi !== null && (
                <circle
                  cx={x}
                  cy={ySmi}
                  r={hoveredPoint === pt ? 6 : 3}
                  fill="#a855f7"
                  stroke="#fff"
                  strokeWidth="1.5"
                  style={{ cursor: 'pointer', transition: 'r 0.2s' }}
                />
              )}
              <rect
                x={x - 12}
                y={padding.top}
                width={24}
                height={chartH}
                fill="transparent"
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => {
                  setHoveredPoint(pt);
                  setHoverPos({ x, y: ySmi ?? (padding.top + chartH / 2) });
                }}
              />
            </g>
          );
        })}

        {/* Vertical Crosshair Line */}
        {hoverPos && (
          <line
            x1={hoverPos.x}
            y1={padding.top}
            x2={hoverPos.x}
            y2={bottomY}
            stroke="rgba(255,255,255,0.4)"
            strokeWidth="1"
            strokeDasharray="2 2"
          />
        )}
      </svg>

      {/* Interactive Tooltip Card */}
      {hoveredPoint && hoverPos && (
        <div
          style={{
            position: 'absolute',
            left: `${Math.min(hoverPos.x, width - 210)}px`,
            top: `${Math.max(10, hoverPos.y - 120)}px`,
            background: 'rgba(15, 23, 42, 0.95)',
            border: '1px solid var(--accent-cyan)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            borderRadius: '8px',
            padding: '10px 14px',
            pointerEvents: 'none',
            zIndex: 100,
            fontSize: '0.78rem',
            minWidth: '190px'
          }}
        >
          <div style={{ color: 'var(--text-muted)', marginBottom: '4px', fontSize: '0.7rem' }}>
            {new Date(hoveredPoint.timestamp).toLocaleString([], { hour12: false })}
          </div>
          <div style={{ color: '#a855f7', fontWeight: 700 }}>
            SMI (Integral): {hoveredPoint.smi !== null && hoveredPoint.smi !== undefined ? `${hoveredPoint.smi.toFixed(1)}/100` : (hoveredPoint.ssi !== null && hoveredPoint.ssi !== undefined ? `${hoveredPoint.ssi.toFixed(1)}/100 (SSI Fallback)` : 'N/A')}
          </div>
          <div style={{ color: 'var(--bullish-green)', fontWeight: 600 }}>
            SSI (Social): {hoveredPoint.ssi !== null && hoveredPoint.ssi !== undefined ? `${hoveredPoint.ssi.toFixed(1)}/100` : (hoveredPoint.social_score !== null && hoveredPoint.social_score !== undefined ? `${hoveredPoint.social_score.toFixed(1)}/100` : 'N/A (Sin cobertura)')}
          </div>
          <div style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>
            PMS (Polymarket): {hoveredPoint.pms !== null && hoveredPoint.pms !== undefined ? `${hoveredPoint.pms.toFixed(1)}/100` : 'N/A (Sin predicciones)'}
          </div>
          <div style={{ color: '#f59e0b', fontWeight: 600 }}>
            Price: {hoveredPoint.price !== null && hoveredPoint.price !== undefined && hoveredPoint.price > 0 ? `$${hoveredPoint.price.toFixed(2)}` : 'N/A (Sin cotización)'}
          </div>
          <div style={{ color: '#fff', fontSize: '0.7rem', marginTop: '3px' }}>
            Signal: <b>{hoveredPoint.signal || 'N/A'}</b>
          </div>
        </div>
      )}
    </div>
  );
};
