import React from 'react';
import { RefreshCw, HelpCircle } from 'lucide-react';
import { AlertsManager } from './AlertsManager';
import { AlertItem } from '../types';

interface HeaderProps {
  lastUpdate: string | null;
  isAnalyzing: boolean;
  alerts: AlertItem[];
  onTriggerAnalysis: () => void;
  onOpenAbout: () => void;
  onSelectTicker?: (ticker: string) => void;
  version?: string;
}

export const Header: React.FC<HeaderProps> = ({
  lastUpdate,
  isAnalyzing,
  alerts,
  onTriggerAnalysis,
  onOpenAbout,
  onSelectTicker,
  version
}) => {
  return (
    <header className="app-header">
      <button type="button" className="brand-section" onClick={onOpenAbout} title="Open the SMIE user guide">
        <span className="brand-icon" aria-hidden="true">🚀</span>
        <span className="brand-text">
          <h1 className="brand-title">SPACE MARKET INTELLIGENCE ENGINE</h1>
          <span className="brand-subtitle">
            Social (X) • Prediction Markets (Polymarket) • News • Technical context{version ? ` · SMIE v${version}` : ''}
          </span>
        </span>
      </button>

      <div className="header-actions">
        <button type="button" onClick={onOpenAbout} className="btn btn-ghost btn-md">
          <HelpCircle size={14} color="var(--accent-cyan)" />
          <span>User Guide</span>
        </button>

        <span className="sources-tag" title="Data sources blended into the SMI">
          X · Polymarket · News · yfinance
        </span>

        {lastUpdate && (
          <span className="last-update-tag" title={new Date(lastUpdate).toLocaleString()}>
            Updated: {new Date(lastUpdate).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })}
          </span>
        )}

        <AlertsManager alerts={alerts} onSelectTicker={onSelectTicker} />

        <button type="button" className="btn-trigger" onClick={onTriggerAnalysis} disabled={isAnalyzing} aria-busy={isAnalyzing}>
          <RefreshCw className={isAnalyzing ? 'spin' : ''} size={16} aria-hidden="true" />
          {isAnalyzing ? 'Analyzing...' : 'Run SMIE Pipeline'}
        </button>
      </div>
    </header>
  );
};
