import React, { useEffect, useState } from 'react';
import { Header } from './components/Header';
import { Dashboard } from './components/Dashboard';
import { TickerDetail } from './components/TickerDetail';
import { AboutModal } from './components/AboutModal';
import { DashboardResponse, RankingItem } from './types';
import './App.css';

export const App: React.FC = () => {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [showAboutModal, setShowAboutModal] = useState<boolean>(false);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchDashboard = () => {
    fetch('/api/dashboard')
      .then((res) => res.json())
      .then((data) => {
        setDashboard(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch dashboard', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchDashboard();
  }, []);

  const handleTriggerAnalysis = async () => {
    setIsAnalyzing(true);
    try {
      await fetch('/api/jobs/run', { method: 'POST' });
      fetchDashboard();
    } catch (err) {
      console.error('Error triggering analysis:', err);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="app-container">
      <Header
        lastUpdate={dashboard?.last_update || null}
        isAnalyzing={isAnalyzing}
        alerts={dashboard?.alerts || []}
        onTriggerAnalysis={handleTriggerAnalysis}
        onOpenAbout={() => setShowAboutModal(true)}
      />

      {loading ? (
        <div style={{ textAlign: 'center', padding: '100px 0', color: 'var(--text-muted)' }}>
          Loading Space Market Intelligence Engine...
        </div>
      ) : (
        <Dashboard
          rankings={dashboard?.rankings || []}
          onSelectTicker={(ticker) => setSelectedTicker(ticker)}
        />
      )}

      {/* Detail Modal for Selected Asset */}
      {selectedTicker && (
        <TickerDetail
          ticker={selectedTicker}
          onClose={() => setSelectedTicker(null)}
        />
      )}

      {/* System Guide & About Modal triggered by App Logo or Manual button */}
      {showAboutModal && (
        <AboutModal
          onClose={() => setShowAboutModal(false)}
        />
      )}
    </div>
  );
};

export default App;
