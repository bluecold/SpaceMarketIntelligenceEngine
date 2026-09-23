import React, { useEffect, useState, useRef } from 'react';
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
  const jobPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastFetchedRef = useRef<number>(Date.now());

  const fetchDashboard = () => {
    fetch('/api/dashboard')
      .then((res) => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }
        return res.json();
      })
      .then((data) => {
        setDashboard(data);
        setLoading(false);
        lastFetchedRef.current = Date.now();
      })
      .catch((err) => {
        console.error('Failed to fetch dashboard', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchDashboard();

    // 1. Periodic background refresh (2 minutes) to ensure near-realtime alert dispatch
    const pollInterval = setInterval(() => {
      fetchDashboard();
    }, 120000);

    // 2. Focus refresh: update if user returns to tab after >= 1 min idle
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        const elapsed = Date.now() - lastFetchedRef.current;
        if (elapsed >= 60000) { // 1 minute
          fetchDashboard();
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      clearInterval(pollInterval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (jobPollRef.current) {
        clearInterval(jobPollRef.current);
        jobPollRef.current = null;
      }
    };
  }, []);

  const handleTriggerAnalysis = async () => {
    setIsAnalyzing(true);
    if (jobPollRef.current) {
      clearInterval(jobPollRef.current);
      jobPollRef.current = null;
    }

    try {
      const storedApiKey = localStorage.getItem('smie_api_key');
      const headers: Record<string, string> = {};
      if (storedApiKey) {
        headers['X-API-KEY'] = storedApiKey;
      }

      let resp = await fetch('/api/jobs/run', { method: 'POST', headers });

      // If unauthorized, prompt user to enter API key and store in localStorage
      if (resp.status === 401) {
        const inputKey = window.prompt(
          'API_SECRET_KEY is required to trigger pipeline analysis on this server. Please enter your API Key:'
        );
        if (inputKey && inputKey.trim()) {
          localStorage.setItem('smie_api_key', inputKey.trim());
          headers['X-API-KEY'] = inputKey.trim();
          resp = await fetch('/api/jobs/run', { method: 'POST', headers });
        } else {
          setIsAnalyzing(false);
          return;
        }
      }

      if (resp.status === 409) {
        const conflictData = await resp.json().catch(() => ({}));
        alert(conflictData.detail || 'A pipeline execution is already in progress. Please wait.');
        setIsAnalyzing(false);
        return;
      }

      if (resp.status === 202) {
        const data = await resp.json();
        const jobId = data.job_id;
        if (jobId) {
          jobPollRef.current = setInterval(async () => {
            try {
              const statusRes = await fetch(`/api/jobs/${jobId}`);
              if (statusRes.ok) {
                const job = await statusRes.json();
                if (job.status === 'SUCCESS' || job.status === 'ERROR') {
                  if (jobPollRef.current) {
                    clearInterval(jobPollRef.current);
                    jobPollRef.current = null;
                  }
                  setIsAnalyzing(false);
                  fetchDashboard();
                }
              }
            } catch (pollErr) {
              console.error('Error polling job status:', pollErr);
              if (jobPollRef.current) {
                clearInterval(jobPollRef.current);
                jobPollRef.current = null;
              }
              setIsAnalyzing(false);
              fetchDashboard();
            }
          }, 1500);
          return;
        }
      }
      fetchDashboard();
      setIsAnalyzing(false);
    } catch (err) {
      console.error('Error triggering analysis:', err);
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
        onSelectTicker={(ticker) => setSelectedTicker(ticker)}
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
          lastUpdate={dashboard?.last_update || null}
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
