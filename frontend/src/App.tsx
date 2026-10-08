import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Header } from './components/Header';
import { Dashboard } from './components/Dashboard';
import { TickerDetail } from './components/TickerDetail';
import { AboutModal } from './components/AboutModal';
import { ApiKeyDialog } from './components/ApiKeyDialog';
import { Notice, NoticeKind } from './components/ui';
import { DashboardResponse } from './types';
import { DEFAULT_THRESHOLDS, ThresholdsContext } from './lib/scale';
import './App.css';

const API_KEY_STORAGE_KEY = 'smie_api_key';
const DASHBOARD_POLL_MS = 120_000;
const JOB_POLL_MS = 1_500;
const JOB_POLL_TIMEOUT_MS = 20 * 60_000;   // Give up after 20 min (the backend flags zombie jobs after 120s without heartbeat)
const JOB_POLL_MAX_ERRORS = 5;
const TERMINAL_JOB_STATUSES = ['SUCCESS', 'PARTIAL', 'ERROR'];

const readStoredKey = (): string | null => {
  try {
    return localStorage.getItem(API_KEY_STORAGE_KEY);
  } catch {
    return null;
  }
};

const writeStoredKey = (key: string | null) => {
  try {
    if (key) localStorage.setItem(API_KEY_STORAGE_KEY, key);
    else localStorage.removeItem(API_KEY_STORAGE_KEY);
  } catch {
    // Storage unavailable (private mode): the key just won't be remembered
  }
};

const formatTime = (ms: number) =>
  new Date(ms).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit' });

interface NoticeState {
  kind: NoticeKind;
  text: string;
}

export const App: React.FC = () => {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [showAboutModal, setShowAboutModal] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<NoticeState | null>(null);
  const [apiKeyPrompt, setApiKeyPrompt] = useState<{ error: string | null } | null>(null);
  const jobPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastFetchedRef = useRef<number>(Date.now());

  const fetchDashboard = useCallback(() => {
    fetch('/api/dashboard')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status} ${res.statusText}`.trim());
        return res.json();
      })
      .then((data: DashboardResponse) => {
        setDashboard(data);
        setLoadError(null);
        lastFetchedRef.current = Date.now();
      })
      .catch((err: Error) => {
        console.error('Failed to fetch dashboard', err);
        setLoadError(err.message || 'Network error');
      })
      .finally(() => setLoading(false));
  }, []);

  const stopJobPolling = () => {
    if (jobPollRef.current) {
      clearInterval(jobPollRef.current);
      jobPollRef.current = null;
    }
  };

  useEffect(() => {
    fetchDashboard();

    // Periodic background refresh so alerts are dispatched near real time
    const pollInterval = setInterval(fetchDashboard, DASHBOARD_POLL_MS);

    // Refresh when the user returns to the tab after at least 1 minute away
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastFetchedRef.current >= 60_000) {
        fetchDashboard();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      clearInterval(pollInterval);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      stopJobPolling();
    };
  }, [fetchDashboard]);

  const finishAnalysis = (next: NoticeState | null) => {
    stopJobPolling();
    setIsAnalyzing(false);
    if (next) setNotice(next);
    fetchDashboard();
  };

  const pollJob = (jobId: number | string) => {
    const startedAt = Date.now();
    let consecutiveErrors = 0;

    jobPollRef.current = setInterval(async () => {
      if (Date.now() - startedAt > JOB_POLL_TIMEOUT_MS) {
        finishAnalysis({ kind: 'warning', text: 'The pipeline is taking longer than expected. Stopped waiting; the dashboard will refresh on its own.' });
        return;
      }
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        consecutiveErrors = 0;
        const job = await res.json();
        if (!TERMINAL_JOB_STATUSES.includes(job.status)) return;

        if (job.status === 'SUCCESS') {
          finishAnalysis({ kind: 'success', text: `Pipeline finished: ${job.records_processed ?? 0} records processed.` });
        } else if (job.status === 'PARTIAL') {
          finishAnalysis({ kind: 'warning', text: 'Pipeline finished with partial results: some data could not be saved. Check the server logs.' });
        } else {
          finishAnalysis({ kind: 'error', text: `Pipeline failed${job.error_message ? `: ${job.error_message}` : '.'}` });
        }
      } catch (err) {
        consecutiveErrors += 1;
        console.error('Error polling job status:', err);
        if (consecutiveErrors >= JOB_POLL_MAX_ERRORS) {
          finishAnalysis({ kind: 'error', text: 'Lost contact with the server while the pipeline was running.' });
        }
      }
    }, JOB_POLL_MS);
  };

  const handleTriggerAnalysis = async (keyOverride?: string) => {
    stopJobPolling();
    setNotice(null);
    setIsAnalyzing(true);

    const apiKey = keyOverride ?? readStoredKey();
    const headers: Record<string, string> = {};
    if (apiKey) headers['X-API-KEY'] = apiKey;

    try {
      const resp = await fetch('/api/jobs/run', { method: 'POST', headers });

      if (resp.status === 401) {
        // Missing or rejected key: forget the stored one and ask again
        writeStoredKey(null);
        setIsAnalyzing(false);
        setApiKeyPrompt({ error: apiKey ? 'The server rejected this API key.' : null });
        return;
      }
      if (apiKey) writeStoredKey(apiKey);

      if (resp.status === 409) {
        const body = await resp.json().catch(() => ({}));
        setNotice({ kind: 'warning', text: body.detail || 'A pipeline run is already in progress. Please wait for it to finish.' });
        setIsAnalyzing(false);
        return;
      }

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        setNotice({ kind: 'error', text: `Could not start the pipeline (HTTP ${resp.status})${body.detail ? `: ${body.detail}` : '.'}` });
        setIsAnalyzing(false);
        return;
      }

      const data = await resp.json().catch(() => ({}));
      if (data.job_id) {
        pollJob(data.job_id);
        return;
      }
      finishAnalysis(null);
    } catch (err) {
      console.error('Error triggering analysis:', err);
      setNotice({ kind: 'error', text: 'Could not reach the server to start the pipeline.' });
      setIsAnalyzing(false);
    }
  };

  const thresholds = dashboard?.engine?.thresholds ?? DEFAULT_THRESHOLDS;

  return (
    <ThresholdsContext.Provider value={thresholds}>
      <div className="app-container">
        <Header
          lastUpdate={dashboard?.last_update || null}
          isAnalyzing={isAnalyzing}
          alerts={dashboard?.alerts || []}
          onTriggerAnalysis={() => handleTriggerAnalysis()}
          onOpenAbout={() => setShowAboutModal(true)}
          onSelectTicker={setSelectedTicker}
          version={dashboard?.engine?.version}
        />

        <div className="notice-stack">
          {loadError && dashboard && (
            <Notice kind="warning" action={{ label: 'Retry', onClick: fetchDashboard }}>
              Could not refresh the dashboard ({loadError}). Showing data loaded at {formatTime(lastFetchedRef.current)}.
            </Notice>
          )}
          {notice && (
            <Notice kind={notice.kind} onDismiss={() => setNotice(null)}>{notice.text}</Notice>
          )}
        </div>

        {loading ? (
          <div className="page-status" role="status">Loading Space Market Intelligence Engine...</div>
        ) : !dashboard ? (
          <div className="page-status">
            <Notice kind="error" action={{ label: 'Retry', onClick: () => { setLoading(true); fetchDashboard(); } }}>
              Could not load the dashboard{loadError ? ` (${loadError})` : ''}. Is the API running on port 8000?
            </Notice>
          </div>
        ) : (
          <Dashboard
            rankings={dashboard.rankings || []}
            onSelectTicker={setSelectedTicker}
            engine={dashboard.engine}
          />
        )}

        {selectedTicker && (
          <TickerDetail
            ticker={selectedTicker}
            onClose={() => setSelectedTicker(null)}
            lastUpdate={dashboard?.last_update || null}
          />
        )}

        {showAboutModal && <AboutModal onClose={() => setShowAboutModal(false)} />}

        {apiKeyPrompt && (
          <ApiKeyDialog
            error={apiKeyPrompt.error}
            onCancel={() => setApiKeyPrompt(null)}
            onSubmit={(key) => {
              setApiKeyPrompt(null);
              handleTriggerAnalysis(key);
            }}
          />
        )}
      </div>
    </ThresholdsContext.Provider>
  );
};

export default App;
