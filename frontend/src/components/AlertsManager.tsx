import React, { useState, useEffect, useRef } from 'react';
import { Bell, AlertTriangle, Zap, TrendingUp, Check } from 'lucide-react';
import { AlertItem } from '../types';

interface AlertsManagerProps {
  alerts: AlertItem[];
}

export const AlertsManager: React.FC<AlertsManagerProps> = ({ alerts }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission>('default');
  const notifiedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    if ('Notification' in window) {
      setPermission(Notification.permission);
    }
  }, []);

  const requestNotificationPermission = async () => {
    if ('Notification' in window) {
      const res = await Notification.requestPermission();
      setPermission(res);
      if (res === 'granted' && alerts.length > 0) {
        new Notification('🚀 Space Sentiment Index Alerts Enabled', {
          body: `Monitoring active signals. ${alerts.length} active alerts detected.`,
          icon: '🚀'
        });
      }
    }
  };

  // Trigger desktop notification ONLY when brand new alerts arrive
  useEffect(() => {
    if (permission !== 'granted' || !alerts || alerts.length === 0) return;

    alerts.forEach((alert) => {
      const key = `${alert.ticker}:${alert.type}`;
      if (!notifiedRef.current.has(key)) {
        notifiedRef.current.add(key);
        try {
          new Notification(`SSI Alert: ${alert.ticker}`, {
            body: alert.message,
            icon: '🚀'
          });
        } catch (e) {
          console.warn('Could not fire desktop notification', e);
        }
      }
    });
  }, [alerts, permission]);

  return (
    <div style={{ position: 'relative' }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          background: alerts.length > 0 ? 'rgba(239, 68, 68, 0.15)' : 'rgba(255, 255, 255, 0.05)',
          border: `1px solid ${alerts.length > 0 ? 'rgba(239, 68, 68, 0.4)' : 'var(--border-color)'}`,
          color: alerts.length > 0 ? '#ef4444' : 'var(--text-muted)',
          padding: '8px 12px',
          borderRadius: '10px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          fontSize: '0.85rem',
          fontWeight: 600,
          transition: 'all 0.2s ease'
        }}
      >
        <Bell size={16} />
        {alerts.length > 0 && (
          <span
            style={{
              background: '#ef4444',
              color: '#fff',
              borderRadius: '10px',
              padding: '1px 6px',
              fontSize: '0.72rem',
              fontWeight: 800
            }}
          >
            {alerts.length}
          </span>
        )}
      </button>

      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: '44px',
            right: '0',
            width: '340px',
            background: '#0f172a',
            border: '1px solid var(--border-color)',
            boxShadow: '0 12px 35px rgba(0, 0, 0, 0.7)',
            borderRadius: '14px',
            padding: '16px',
            zIndex: 1000,
            animation: 'fadeIn 0.2s ease'
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
            <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 700, fontSize: '0.95rem' }}>
              System Alerts & Signals
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {alerts.length} active
            </span>
          </div>

          {permission !== 'granted' && (
            <button
              onClick={requestNotificationPermission}
              style={{
                width: '100%',
                background: 'rgba(0, 242, 254, 0.1)',
                border: '1px solid rgba(0, 242, 254, 0.3)',
                color: 'var(--accent-cyan)',
                borderRadius: '8px',
                padding: '8px',
                fontSize: '0.78rem',
                cursor: 'pointer',
                marginBottom: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px'
              }}
            >
              <Zap size={14} /> Enable Desktop Notifications
            </button>
          )}

          {alerts.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '20px 0', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No critical divergence or high-volatility alerts active.
            </div>
          ) : (
            <div style={{ maxHeight: '280px', overflowY: 'auto' }}>
              {alerts.map((al, idx) => (
                <div
                  key={idx}
                  style={{
                    background: 'rgba(255, 255, 255, 0.03)',
                    borderLeft: `3px solid ${al.level === 'CRITICAL' ? '#ef4444' : '#f59e0b'}`,
                    borderRadius: '6px',
                    padding: '8px 10px',
                    marginBottom: '8px',
                    fontSize: '0.8rem',
                    lineHeight: '1.4'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '3px' }}>
                    <strong style={{ color: '#fff' }}>{al.ticker}</strong>
                    <span style={{ fontSize: '0.7rem', color: al.level === 'CRITICAL' ? '#ef4444' : '#f59e0b' }}>
                      {al.type}
                    </span>
                  </div>
                  <div style={{ color: 'var(--text-main)' }}>{al.message}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
