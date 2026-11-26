import React, { useEffect } from 'react';
import { Notice } from './ui';
import { SourceProblem } from '../types';

// One desktop notification per failure episode (source + kind + start), shared by every ticker it affects.
// The per-ticker SOURCE_ERROR alerts are skipped by AlertsManager so the same outage does not notify 5 times.
const NOTIFIED_KEY = 'smie_source_problem_notified';

const readNotified = (): Set<string> => {
  try {
    return new Set(JSON.parse(localStorage.getItem(NOTIFIED_KEY) || '[]'));
  } catch {
    return new Set();
  }
};

const writeNotified = (keys: Set<string>) => {
  try {
    localStorage.setItem(NOTIFIED_KEY, JSON.stringify(Array.from(keys).slice(-50)));
  } catch {
    // Storage unavailable: the notification may repeat on reload, the banner is unaffected
  }
};

const KIND_LABEL: Record<string, string> = {
  AUTH: 'credentials rejected',
  INCOMPATIBLE: 'client no longer compatible',
  RATE_LIMITED: 'rate-limited',
  NETWORK: 'unreachable',
  ERROR: 'fetch failing',
};

const formatSince = (iso: string | null): string => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
};

export const SourceHealthBanner: React.FC<{ problems: SourceProblem[] }> = ({ problems }) => {
  useEffect(() => {
    if (!problems.length || !('Notification' in window) || Notification.permission !== 'granted') return;
    const notified = readNotified();
    let changed = false;
    problems.forEach((p) => {
      const key = `${p.source}:${p.kind}@${p.since ?? ''}`;
      if (notified.has(key)) return;
      notified.add(key);
      changed = true;
      try {
        new Notification(`SMIE [${p.severity}] ${p.label}: ${KIND_LABEL[p.kind] ?? p.kind}`, { body: p.action });
      } catch (e) {
        console.warn('Could not fire desktop notification', e);
      }
    });
    if (changed) writeNotified(notified);
  }, [problems]);

  if (!problems.length) return null;

  return (
    <>
      {problems.map((p) => {
        const since = formatSince(p.since);
        const scope = p.tickers.length ? p.tickers.join(', ') : 'all tickers';
        return (
          <Notice key={`${p.source}:${p.kind}`} kind={p.severity === 'CRITICAL' ? 'error' : 'warning'}>
            <strong>{p.label}: {KIND_LABEL[p.kind] ?? p.kind}</strong>
            {since && <> since {since}</>} ({scope}). Its pillar is left out of the SMI until it recovers.
            <br />
            <span>{p.action}</span>
          </Notice>
        );
      })}
    </>
  );
};
