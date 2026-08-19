import React, { useState } from 'react';
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

  if (!data || data.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '30px', color: 'var(--text-muted)', background: 'rgba(0,0,0,0.2)', borderRadius: '12px' }}>
        No historical snapshot data available yet. Run analysis to start accumulating history points.
      </div>
    );
  }

  const width = 800;
  const height = 230;
  const padding = { top: 20, right: 50, bottom: 30, left: 45 };

  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;

  // X scale: based on index or time
  const getX = (index: number) => {
    if (data.length === 1) return padding.left + chartW / 2;
    return padding.left + (index / (data.length - 1)) * chartW;
  };

  // Y scale for 0-100 Scores (SMI, SSI, PMS)
  const getY_Score = (score: number | null) => {
    if (score === null || score === undefined) return padding.top + chartH;
    const clamped = Math.max(0, Math.min(100, score));
    return padding.top + chartH - (clamped / 100) * chartH;
  };

  // Y scale for Price (minPrice to maxPrice)
  const validPrices = data.map((d) => d.price).filter((p): p is number => p !== null && p > 0);
  const minPrice = validPrices.length > 0 ? Math.min(...validPrices) * 0.95 : 0;
  const maxPrice = validPrices.length > 0 ? Math.max(...validPrices) * 1.05 : 100;
  const priceRange = maxPrice - minPrice || 1;

  const getY_Price = (price: number | null) => {
    if (price === null) return padding.top + chartH;
    return padding.top + chartH - ((price - minPrice) / priceRange) * chartH;
  };

  // 1. SMI Path (Purple)
  const smiPoints = data.map((d, i) => `${getX(i)},${getY_Score(d.smi ?? d.ssi)}`).join(' L ');
  const smiArea = data.length > 1
    ? `M ${getX(0)},${padding.top + chartH} L ${smiPoints} L ${getX(data.length - 1)},${padding.top + chartH} Z`
    : '';

  // 2. SSI Path (Blue)
  const ssiPoints = data.map((d, i) => `${getX(i)},${getY_Score(d.ssi ?? d.social_score)}`).join(' L ');

  // 3. PMS Path (Cyan / Emerald)
  const pmsPoints = data
    .filter((d) => d.pms !== null && d.pms !== undefined)
    .map((d) => {
      const idx = data.indexOf(d);
      return `${getX(idx)},${getY_Score(d.pms)}`;
    })
    .join(' L ');

  // 4. Price Path (Amber)
  const pricePoints = data
    .filter((d) => d.price !== null)
    .map((d) => {
      const idx = data.indexOf(d);
      return `${getX(idx)},${getY_Price(d.price)}`;
    })
    .join(' L ');

  return (
    <div style={{ position: 'relative', width: '100%', background: 'rgba(11, 15, 25, 0.6)', borderRadius: '14px', border: '1px solid var(--border-color)', padding: '14px' }}>
      {/* Top Header & Series Toggles */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', padding: '0 4px', flexWrap: 'wrap', gap: '8px' }}>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>
          Interactive Multi-Series History ({data.length} snapshots)
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
          const y = getY_Score(val);
          return (
            <g key={val}>
              <line x1={padding.left} y1={y} x2={width - padding.right} y2={y} stroke="rgba(255,255,255,0.06)" strokeDasharray="3 3" />
              <text x={padding.left - 8} y={y + 3} fill="var(--text-dim)" fontSize="10" textAnchor="end">{val}</text>
            </g>
          );
        })}

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
        {showSMI && smiArea && (
          <path d={smiArea} fill="url(#smiGradient)" />
        )}
        {showSMI && (
          <path d={`M ${smiPoints}`} fill="none" stroke="#a855f7" strokeWidth="2.5" strokeLinecap="round" />
        )}

        {/* SSI Line (Green) */}
        {showSSI && ssiPoints && (
          <path d={`M ${ssiPoints}`} fill="none" stroke="var(--bullish-green)" strokeWidth="1.8" strokeDasharray="4 2" strokeLinecap="round" />
        )}

        {/* PMS Line (Cyan) */}
        {showPMS && pmsPoints && (
          <path d={`M ${pmsPoints}`} fill="none" stroke="var(--accent-cyan)" strokeWidth="1.8" strokeLinecap="round" />
        )}

        {/* Price Line (Amber) */}
        {showPrice && pricePoints && (
          <path d={`M ${pricePoints}`} fill="none" stroke="#f59e0b" strokeWidth="2" strokeLinecap="round" />
        )}

        {/* Data Point Hover Hotspots */}
        {data.map((pt, i) => {
          const x = getX(i);
          const ySmi = getY_Score(pt.smi ?? pt.ssi);
          return (
            <g key={i}>
              <circle
                cx={x}
                cy={ySmi}
                r={hoveredPoint === pt ? 6 : 3}
                fill="#a855f7"
                stroke="#fff"
                strokeWidth="1.5"
                style={{ cursor: 'pointer', transition: 'r 0.2s' }}
              />
              <rect
                x={x - 15}
                y={padding.top}
                width={30}
                height={chartH}
                fill="transparent"
                style={{ cursor: 'pointer' }}
                onMouseEnter={() => {
                  setHoveredPoint(pt);
                  setHoverPos({ x, y: ySmi });
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
            y2={padding.top + chartH}
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
            left: `${Math.min(hoverPos.x, width - 200)}px`,
            top: `${Math.max(10, hoverPos.y - 120)}px`,
            background: 'rgba(15, 23, 42, 0.95)',
            border: '1px solid var(--accent-cyan)',
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            borderRadius: '8px',
            padding: '10px 14px',
            pointerEvents: 'none',
            zIndex: 100,
            fontSize: '0.78rem',
            minWidth: '180px'
          }}
        >
          <div style={{ color: 'var(--text-muted)', marginBottom: '4px', fontSize: '0.7rem' }}>
            {new Date(hoveredPoint.timestamp).toLocaleString()}
          </div>
          <div style={{ color: '#a855f7', fontWeight: 700 }}>
            SMI (Integral): {(hoveredPoint.smi ?? hoveredPoint.ssi).toFixed(1)}/100
          </div>
          <div style={{ color: 'var(--bullish-green)', fontWeight: 600 }}>
            SSI (Social): {hoveredPoint.ssi?.toFixed(1) ?? hoveredPoint.social_score?.toFixed(1)}/100
          </div>
          {hoveredPoint.pms !== null && hoveredPoint.pms !== undefined && (
            <div style={{ color: 'var(--accent-cyan)', fontWeight: 600 }}>
              PMS (Polymarket): {hoveredPoint.pms.toFixed(1)}/100
            </div>
          )}
          {hoveredPoint.price && (
            <div style={{ color: '#f59e0b', fontWeight: 600 }}>
              Price: ${hoveredPoint.price.toFixed(2)}
            </div>
          )}
          <div style={{ color: '#fff', fontSize: '0.7rem', marginTop: '3px' }}>
            Signal: <b>{hoveredPoint.signal}</b>
          </div>
        </div>
      )}
    </div>
  );
};
