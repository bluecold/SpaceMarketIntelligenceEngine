import React from 'react';
import { Rocket, RefreshCw, Activity, Radio, Compass, Newspaper, HelpCircle, Info } from 'lucide-react';
import { AlertsManager } from './AlertsManager';
import { AlertItem } from '../types';

interface HeaderProps {
  lastUpdate: string | null;
  isAnalyzing: boolean;
  alerts: AlertItem[];
  onTriggerAnalysis: () => void;
  onOpenAbout: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  lastUpdate,
  isAnalyzing,
  alerts,
  onTriggerAnalysis,
  onOpenAbout
}) => {
  return (
    <header className="app-header">
      {/* Clickable Brand Section / Logo to open Guide Modal */}
      <div
        className="brand-section"
        onClick={onOpenAbout}
        style={{
          cursor: 'pointer',
          transition: 'transform 0.2s, opacity 0.2s',
          userSelect: 'none'
        }}
        title="Haz clic para ver el Manual, Objetivos y Guía de Uso de SMIE"
      >
        <div className="brand-icon" style={{ position: 'relative' }}>
          🚀
          <span
            style={{
              position: 'absolute',
              bottom: '-4px',
              right: '-4px',
              background: 'var(--accent-cyan)',
              color: '#000',
              borderRadius: '50%',
              width: '14px',
              height: '14px',
              fontSize: '10px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 800
            }}
          >
            ?
          </span>
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h1 className="brand-title" style={{ margin: 0 }}>SPACE MARKET INTELLIGENCE ENGINE</h1>
            <span
              style={{
                fontSize: '0.68rem',
                color: 'var(--accent-cyan)',
                border: '1px solid rgba(0, 242, 254, 0.4)',
                background: 'rgba(0, 242, 254, 0.08)',
                padding: '2px 6px',
                borderRadius: '4px',
                fontWeight: 600
              }}
            >
              Info / Guía ℹ️
            </span>
          </div>
          <p className="brand-subtitle">
            Multivariate Space Market Intelligence: Social (X) • Prediction Markets (Polymarket) • Technical • News (SMIE v2.0)
          </p>
        </div>
      </div>

      <div className="header-actions">
        {/* Help / Guide Quick Button */}
        <button
          onClick={onOpenAbout}
          className="btn btn-secondary"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            fontSize: '0.78rem',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            background: 'rgba(255, 255, 255, 0.04)'
          }}
          title="Abrir Guía y Manual de la Aplicación"
        >
          <HelpCircle size={14} color="var(--accent-cyan)" />
          <span>Manual de Uso</span>
        </button>

        {/* Provider Freshness Indicators */}
        <div
          style={{
            display: 'flex',
            gap: '6px',
            alignItems: 'center',
            background: 'rgba(0,0,0,0.3)',
            padding: '4px 8px',
            borderRadius: '6px',
            fontSize: '0.72rem',
            border: '1px solid var(--border-color)'
          }}
        >
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px', color: 'var(--bullish-green)' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--bullish-green)', display: 'inline-block' }} />
            X / Social
          </span>
          <span style={{ color: 'var(--border-color)' }}>|</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px', color: 'var(--accent-cyan)' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-cyan)', display: 'inline-block' }} />
            Polymarket
          </span>
          <span style={{ color: 'var(--border-color)' }}>|</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px', color: '#f59e0b' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#f59e0b', display: 'inline-block' }} />
            yfinance
          </span>
        </div>

        {lastUpdate && (
          <span className="last-update-tag">
            Updated: {new Date(lastUpdate).toLocaleTimeString()}
          </span>
        )}

        <AlertsManager alerts={alerts} />

        <button
          className="btn-trigger"
          onClick={onTriggerAnalysis}
          disabled={isAnalyzing}
        >
          <RefreshCw className={isAnalyzing ? "spin" : ""} size={16} />
          {isAnalyzing ? "Analyzing..." : "Run SMIE Pipeline"}
        </button>
      </div>
    </header>
  );
};
