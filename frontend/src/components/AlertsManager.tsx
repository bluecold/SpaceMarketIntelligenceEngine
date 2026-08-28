import React, { useState, useEffect, useRef } from 'react';
import {
  Bell, Zap, Check,
  Clock, Radio, ExternalLink, CheckCheck, Settings,
  ShieldCheck, ShieldAlert
} from 'lucide-react';
import { AlertItem } from '../types';

interface AlertsManagerProps {
  alerts: AlertItem[];
  onSelectTicker?: (ticker: string) => void;
}

type FilterCategory = 'ALL' | 'CRITICAL' | 'DIVERGENCES' | 'SIGNALS' | 'SYSTEM';
type NotificationSeverity = 'CRITICAL' | 'HIGH' | 'ALL';

interface NotificationSettings {
  desktopEnabled: boolean;
  minSeverity: NotificationSeverity;
}

const READ_STORAGE_KEY = 'smie_read_alerts_v1';
const NOTIFIED_STORAGE_KEY = 'smie_desktop_notified_v1';
const SETTINGS_STORAGE_KEY = 'smie_alert_settings_v1';

const DEFAULT_SETTINGS: NotificationSettings = {
  desktopEnabled: true,
  minSeverity: 'CRITICAL'
};

export const AlertsManager: React.FC<AlertsManagerProps> = ({ alerts, onSelectTicker }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [permission, setPermission] = useState<NotificationPermission>('default');
  const [activeFilter, setActiveFilter] = useState<FilterCategory>('ALL');

  // Read alerts tracker
  const [readIds, setReadIds] = useState<Set<string>>(() => {
    try {
      const stored = localStorage.getItem(READ_STORAGE_KEY);
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  });

  // User notification preferences
  const [settings, setSettings] = useState<NotificationSettings>(() => {
    try {
      const stored = localStorage.getItem(SETTINGS_STORAGE_KEY);
      return stored ? { ...DEFAULT_SETTINGS, ...JSON.parse(stored) } : DEFAULT_SETTINGS;
    } catch {
      return DEFAULT_SETTINGS;
    }
  });

  const dropdownRef = useRef<HTMLDivElement>(null);
  const isInitialMountRef = useRef<boolean>(true);

  // Persistent notified registry (persisted in localStorage, loaded into ref)
  const notifiedIdsRef = useRef<Set<string>>((() => {
    try {
      const stored = localStorage.getItem(NOTIFIED_STORAGE_KEY);
      return stored ? new Set(JSON.parse(stored)) : new Set();
    } catch {
      return new Set();
    }
  })());

  const saveNotifiedIds = (set: Set<string>) => {
    try {
      // Auto-prune to keep most recent 100 entries to avoid localStorage bloat
      const arr = Array.from(set);
      const pruned = arr.length > 100 ? arr.slice(arr.length - 100) : arr;
      localStorage.setItem(NOTIFIED_STORAGE_KEY, JSON.stringify(pruned));
    } catch (e) {
      console.warn('Failed to save notified alerts', e);
    }
  };

  const saveReadIds = (set: Set<string>) => {
    try {
      // Auto-prune to keep most recent 100 entries to avoid localStorage bloat
      const arr = Array.from(set);
      const pruned = arr.length > 100 ? arr.slice(arr.length - 100) : arr;
      localStorage.setItem(READ_STORAGE_KEY, JSON.stringify(pruned));
    } catch (e) {
      console.warn('Failed to save read alerts', e);
    }
  };

  const updateSettings = (newSettings: Partial<NotificationSettings>) => {
    const updated = { ...settings, ...newSettings };
    setSettings(updated);
    try {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(updated));
    } catch (e) {
      console.warn('Failed to save alert settings', e);
    }
  };

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  useEffect(() => {
    if ('Notification' in window) {
      setPermission(Notification.permission);
    }
  }, []);

  const requestNotificationPermission = async () => {
    if ('Notification' in window) {
      const res = await Notification.requestPermission();
      setPermission(res);
      if (res === 'granted') {
        new Notification('🚀 SMIE Real-Time Alerts Enabled', {
          body: `Monitoreo de señales activado. Modo: ${settings.minSeverity === 'CRITICAL' ? 'Solo Críticas' : settings.minSeverity === 'HIGH' ? 'Críticas y Altas' : 'Todas'}.`,
          icon: '🚀'
        });
      }
    }
  };

  const triggerTestNotification = () => {
    if (permission !== 'granted') {
      requestNotificationPermission();
      return;
    }
    try {
      new Notification('🔔 SMIE Intelligence Alert Test', {
        body: 'Notificaciones de Windows funcionando correctamente en tiempo real.',
        icon: '🚀'
      });
    } catch (e) {
      console.warn('Error launching test notification', e);
    }
  };

  const getAlertKey = (al: AlertItem, index: number): string => {
    return al.id || `${al.ticker}:${al.type}:${al.timestamp || index}`;
  };

  const isAlertActive = (al: AlertItem): boolean => {
    if (al.is_active !== undefined) return al.is_active;
    if (al.age_hours !== undefined && al.age_hours !== null) return al.age_hours < 6.0;
    return true;
  };

  // --- COLD START PROTECTION & REAL-TIME DISPATCH ---
  useEffect(() => {
    if (!alerts || alerts.length === 0) return;

    // 1. SILENT COLD-START SEEDING:
    // On the initial page mount or reload (F5), seed all existing server alerts
    // into the notified set WITHOUT firing any Windows notification.
    if (isInitialMountRef.current) {
      isInitialMountRef.current = false;
      const updatedSet = new Set(notifiedIdsRef.current);
      alerts.forEach((al, idx) => {
        updatedSet.add(getAlertKey(al, idx));
      });
      notifiedIdsRef.current = updatedSet;
      saveNotifiedIds(updatedSet);
      return;
    }

    // 2. DISPATCH ONLY TRULY NEW ARRIVING ALERTS (subsequent polling / job triggers)
    if (permission !== 'granted' || !settings.desktopEnabled) return;

    const newToNotify: AlertItem[] = [];
    const updatedSet = new Set(notifiedIdsRef.current);

    alerts.forEach((alert, idx) => {
      const key = getAlertKey(alert, idx);
      if (updatedSet.has(key)) return;

      // Mark as processed in registry immediately to ensure idempotency
      updatedSet.add(key);

      // Freshness check: must be active and <= 30 minutes old
      const isActive = isAlertActive(alert);
      const isFresh = alert.age_hours === undefined || alert.age_hours === null || alert.age_hours <= 0.5;
      if (!isActive || !isFresh) return;

      // Severity check based on user preferences
      const isCritical = alert.level === 'CRITICAL';
      const isHigh = alert.level === 'HIGH';
      if (settings.minSeverity === 'CRITICAL' && !isCritical) return;
      if (settings.minSeverity === 'HIGH' && !isCritical && !isHigh) return;

      newToNotify.push(alert);
    });

    notifiedIdsRef.current = updatedSet;
    saveNotifiedIds(updatedSet);

    // Fire notifications for qualifying new alerts
    newToNotify.forEach((alert) => {
      try {
        const timeStr = alert.timestamp
          ? new Date(alert.timestamp).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
          : '';
        new Notification(`SMIE [${alert.level}] ${alert.ticker}`, {
          body: `${timeStr ? `[${timeStr}] ` : ''}${alert.message}`,
          icon: '🚀'
        });
      } catch (e) {
        console.warn('Could not fire desktop notification', e);
      }
    });
  }, [alerts, permission, settings]);

  const markAllAsRead = () => {
    const allKeys = new Set(readIds);
    alerts.forEach((al, idx) => allKeys.add(getAlertKey(al, idx)));
    setReadIds(allKeys);
    saveReadIds(allKeys);
  };

  const handleAlertClick = (al: AlertItem, idx: number) => {
    const key = getAlertKey(al, idx);
    if (!readIds.has(key)) {
      const updated = new Set(readIds);
      updated.add(key);
      setReadIds(updated);
      saveReadIds(updated);
    }

    setIsOpen(false);
    if (onSelectTicker) {
      onSelectTicker(al.ticker);
    }
  };

  const getCategory = (al: AlertItem): 'SIGNAL' | 'DIVERGENCES' | 'SYSTEM' => {
    if (al.category === 'SIGNAL' || al.type.includes('BUY') || al.type.includes('AVOID')) return 'SIGNAL';
    if (al.category === 'SYSTEM' || al.type.includes('STALE')) return 'SYSTEM';
    return 'DIVERGENCES';
  };

  // Time & Validity formatters
  const format24hTime = (ts?: string | null): string => {
    if (!ts) return '--:--:--';
    const d = new Date(ts);
    return isNaN(d.getTime())
      ? '--:--:--'
      : d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const formatRelativeTime = (ts?: string | null, ageHours?: number | null): string => {
    if (ageHours !== undefined && ageHours !== null) {
      if (ageHours < 0.05) return 'Recién emitido';
      if (ageHours < 1.0) return `hace ${Math.round(ageHours * 60)} min`;
      return `hace ${ageHours.toFixed(1)}h`;
    }
    if (!ts) return 'Reciente';
    const now = Date.now();
    const d = new Date(ts).getTime();
    if (isNaN(d)) return 'Reciente';
    const diffMin = Math.max(0, Math.floor((now - d) / 60000));
    if (diffMin < 2) return 'Justo ahora';
    if (diffMin < 60) return `hace ${diffMin} min`;
    const diffHours = (diffMin / 60).toFixed(1);
    return `hace ${diffHours}h`;
  };

  // Filter calculations
  const filteredAlerts = alerts.filter((al) => {
    if (activeFilter === 'CRITICAL') return al.level === 'CRITICAL';
    if (activeFilter === 'DIVERGENCES') return getCategory(al) === 'DIVERGENCES';
    if (activeFilter === 'SIGNALS') return getCategory(al) === 'SIGNAL';
    if (activeFilter === 'SYSTEM') return getCategory(al) === 'SYSTEM';
    return true;
  });

  const unreadCount = alerts.filter((al, idx) => !readIds.has(getAlertKey(al, idx))).length;
  const hasCriticalUnread = alerts.some((al, idx) => al.level === 'CRITICAL' && !readIds.has(getAlertKey(al, idx)));

  const countByFilter = {
    ALL: alerts.length,
    CRITICAL: alerts.filter(a => a.level === 'CRITICAL').length,
    DIVERGENCES: alerts.filter(a => getCategory(a) === 'DIVERGENCES').length,
    SIGNALS: alerts.filter(a => getCategory(a) === 'SIGNAL').length,
    SYSTEM: alerts.filter(a => getCategory(a) === 'SYSTEM').length,
  };

  return (
    <div style={{ position: 'relative' }} ref={dropdownRef}>
      {/* Bell Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        title="Centro de Alertas & Intelligence Radar"
        className={hasCriticalUnread ? "pulse-critical" : ""}
        style={{
          background: alerts.length > 0
            ? hasCriticalUnread ? 'rgba(239, 68, 68, 0.2)' : 'rgba(245, 158, 11, 0.15)'
            : 'rgba(255, 255, 255, 0.05)',
          border: `1px solid ${
            alerts.length > 0
              ? hasCriticalUnread ? 'rgba(239, 68, 68, 0.6)' : 'rgba(245, 158, 11, 0.4)'
              : 'var(--border-color)'
          }`,
          color: alerts.length > 0
            ? hasCriticalUnread ? '#ef4444' : '#f59e0b'
            : 'var(--text-muted)',
          padding: '8px 13px',
          borderRadius: '10px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '7px',
          fontSize: '0.85rem',
          fontWeight: 600,
          transition: 'all 0.2s ease',
          position: 'relative'
        }}
      >
        <Bell size={16} className={hasCriticalUnread ? "spin-gentle" : ""} />
        {alerts.length > 0 && (
          <span
            style={{
              background: unreadCount > 0 ? (hasCriticalUnread ? '#ef4444' : '#f59e0b') : 'var(--text-dim)',
              color: '#fff',
              borderRadius: '10px',
              padding: '1px 6px',
              fontSize: '0.72rem',
              fontWeight: 800
            }}
          >
            {unreadCount > 0 ? unreadCount : alerts.length}
          </span>
        )}
      </button>

      {/* Flyout Panel */}
      {isOpen && (
        <div
          style={{
            position: 'absolute',
            top: '46px',
            right: '0',
            width: '440px',
            maxWidth: '94vw',
            background: '#0c1322',
            border: '1px solid var(--border-color)',
            boxShadow: '0 16px 40px rgba(0, 0, 0, 0.85), 0 0 15px rgba(0, 242, 254, 0.1)',
            borderRadius: '14px',
            padding: '16px',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
            gap: '12px',
            animation: 'fadeIn 0.15s ease'
          }}
        >
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Radio size={16} color="var(--accent-cyan)" />
              <span style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, fontSize: '0.98rem', color: '#fff' }}>
                Intelligence Radar
              </span>
              <span style={{ fontSize: '0.72rem', background: 'rgba(0, 242, 254, 0.1)', color: 'var(--accent-cyan)', padding: '2px 6px', borderRadius: '4px', fontWeight: 700 }}>
                {alerts.length} en radar
              </span>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                onClick={() => setShowSettings(!showSettings)}
                style={{
                  background: showSettings ? 'rgba(0, 242, 254, 0.15)' : 'none',
                  border: showSettings ? '1px solid var(--accent-cyan)' : 'none',
                  color: showSettings ? 'var(--accent-cyan)' : 'var(--text-muted)',
                  cursor: 'pointer',
                  fontSize: '0.72rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '3px 7px',
                  borderRadius: '6px'
                }}
                title="Configuración de notificaciones de Windows"
              >
                <Settings size={13} />
                <span>Ajustes</span>
              </button>

              {unreadCount > 0 && (
                <button
                  onClick={markAllAsRead}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    fontSize: '0.72rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 6px',
                    borderRadius: '4px'
                  }}
                  title="Marcar todas las alertas como leídas"
                >
                  <CheckCheck size={13} /> Leídas
                </button>
              )}
            </div>
          </div>

          {/* Settings Panel (Toggleable) */}
          {showSettings && (
            <div
              style={{
                background: 'rgba(255, 255, 255, 0.03)',
                border: '1px solid rgba(0, 242, 254, 0.2)',
                borderRadius: '10px',
                padding: '12px',
                display: 'flex',
                flexDirection: 'column',
                gap: '10px'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.78rem', fontWeight: 700, color: '#fff', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <ShieldCheck size={14} color="var(--accent-cyan)" /> Notificaciones de Windows
                </span>
                <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer', gap: '6px', fontSize: '0.75rem' }}>
                  <input
                    type="checkbox"
                    checked={settings.desktopEnabled}
                    onChange={(e) => updateSettings({ desktopEnabled: e.target.checked })}
                    style={{ cursor: 'pointer' }}
                  />
                  <span style={{ color: settings.desktopEnabled ? 'var(--bullish-green)' : 'var(--text-muted)' }}>
                    {settings.desktopEnabled ? 'Activadas' : 'Silenciadas'}
                  </span>
                </label>
              </div>

              {settings.desktopEnabled && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    Umbral de severidad para popup en Windows:
                  </div>
                  <div style={{ display: 'flex', gap: '6px' }}>
                    {(
                      [
                        { id: 'CRITICAL', label: '🔴 Solo Críticas' },
                        { id: 'HIGH', label: '🟠 Críticas + Altas' },
                        { id: 'ALL', label: '⚪ Todas' }
                      ] as const
                    ).map((lvl) => (
                      <button
                        key={lvl.id}
                        onClick={() => updateSettings({ minSeverity: lvl.id })}
                        style={{
                          flex: 1,
                          padding: '4px 6px',
                          fontSize: '0.7rem',
                          fontWeight: settings.minSeverity === lvl.id ? 700 : 500,
                          borderRadius: '6px',
                          border: settings.minSeverity === lvl.id ? '1px solid var(--accent-cyan)' : '1px solid rgba(255,255,255,0.08)',
                          background: settings.minSeverity === lvl.id ? 'rgba(0, 242, 254, 0.15)' : 'rgba(255,255,255,0.02)',
                          color: settings.minSeverity === lvl.id ? '#fff' : 'var(--text-muted)',
                          cursor: 'pointer'
                        }}
                      >
                        {lvl.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '4px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                  🛡️ Carga inicial protegida (sin spam en F5)
                </span>
                <button
                  onClick={triggerTestNotification}
                  style={{
                    background: 'rgba(255, 255, 255, 0.05)',
                    border: '1px solid rgba(255, 255, 255, 0.1)',
                    color: 'var(--accent-cyan)',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    fontSize: '0.7rem',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '4px'
                  }}
                >
                  <Zap size={11} /> Probar aviso
                </button>
              </div>
            </div>
          )}

          {/* Filter Pills */}
          <div style={{ display: 'flex', gap: '6px', overflowX: 'auto', paddingBottom: '4px' }}>
            {(
              [
                { id: 'ALL', label: `Todas (${countByFilter.ALL})` },
                { id: 'CRITICAL', label: `🚨 Críticas (${countByFilter.CRITICAL})` },
                { id: 'DIVERGENCES', label: `⚡ Divergencias (${countByFilter.DIVERGENCES})` },
                { id: 'SIGNALS', label: `🚀 Señales (${countByFilter.SIGNALS})` },
                { id: 'SYSTEM', label: `⏳ Sistema (${countByFilter.SYSTEM})` }
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveFilter(tab.id)}
                style={{
                  background: activeFilter === tab.id ? 'rgba(0, 242, 254, 0.15)' : 'rgba(255, 255, 255, 0.04)',
                  border: activeFilter === tab.id ? '1px solid var(--accent-cyan)' : '1px solid rgba(255, 255, 255, 0.08)',
                  color: activeFilter === tab.id ? 'var(--accent-cyan)' : 'var(--text-muted)',
                  borderRadius: '20px',
                  padding: '4px 10px',
                  fontSize: '0.72rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  whiteSpace: 'nowrap',
                  transition: 'all 0.15s ease'
                }}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Desktop Permission Request Banner (if not yet granted) */}
          {permission !== 'granted' && (
            <div
              onClick={requestNotificationPermission}
              style={{
                background: 'rgba(0, 242, 254, 0.08)',
                border: '1px dashed rgba(0, 242, 254, 0.3)',
                color: 'var(--accent-cyan)',
                borderRadius: '8px',
                padding: '8px 12px',
                fontSize: '0.75rem',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '6px',
                transition: 'background 0.2s'
              }}
            >
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Zap size={14} /> Activar notificaciones en Windows (solo nuevas señales)
              </span>
              <span style={{ fontWeight: 700, fontSize: '0.72rem', textDecoration: 'underline' }}>
                Activar
              </span>
            </div>
          )}

          {/* Alerts List */}
          {filteredAlerts.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '30px 10px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No hay alertas activas en esta categoría.
            </div>
          ) : (
            <div style={{ maxHeight: '360px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '8px', paddingRight: '2px' }}>
              {filteredAlerts.map((al, idx) => {
                const key = getAlertKey(al, idx);
                const isRead = readIds.has(key);
                const isActive = isAlertActive(al);
                const isCritical = al.level === 'CRITICAL';
                const isHigh = al.level === 'HIGH';
                const isWarning = al.level === 'WARNING';

                const borderLeftColor = isCritical ? '#ef4444' : isHigh ? '#f59e0b' : isWarning ? '#eab308' : '#38bdf8';
                const cardBg = isCritical
                  ? 'rgba(239, 68, 68, 0.07)'
                  : isHigh
                  ? 'rgba(245, 158, 11, 0.05)'
                  : 'rgba(255, 255, 255, 0.03)';

                return (
                  <div
                    key={key}
                    onClick={() => handleAlertClick(al, idx)}
                    style={{
                      background: cardBg,
                      borderLeft: `4px solid ${borderLeftColor}`,
                      borderTop: '1px solid rgba(255, 255, 255, 0.05)',
                      borderRight: '1px solid rgba(255, 255, 255, 0.05)',
                      borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                      borderRadius: '8px',
                      padding: '10px 12px',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                      opacity: isRead ? 0.78 : 1,
                      position: 'relative'
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.transform = 'translateY(-1px)';
                      e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.5)';
                      e.currentTarget.style.borderColor = 'rgba(0, 242, 254, 0.4)';
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.transform = 'none';
                      e.currentTarget.style.boxShadow = 'none';
                      e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.05)';
                    }}
                  >
                    {/* Top Meta Line: Severity, Status & 24h Timestamp */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        {/* Severity Badge */}
                        <span
                          style={{
                            fontSize: '0.68rem',
                            fontWeight: 800,
                            padding: '1px 5px',
                            borderRadius: '3px',
                            background: isCritical ? '#ef4444' : isHigh ? '#f59e0b' : isWarning ? '#eab308' : '#38bdf8',
                            color: '#000'
                          }}
                        >
                          {al.level}
                        </span>

                        {/* Validity Badge */}
                        <span
                          style={{
                            fontSize: '0.68rem',
                            fontWeight: 600,
                            padding: '1px 5px',
                            borderRadius: '3px',
                            background: isActive ? 'rgba(16, 185, 129, 0.15)' : 'rgba(234, 179, 8, 0.15)',
                            color: isActive ? 'var(--bullish-green)' : '#eab308',
                            border: `1px solid ${isActive ? 'rgba(16, 185, 129, 0.3)' : 'rgba(234, 179, 8, 0.3)'}`
                          }}
                        >
                          {isActive ? '🟢 Vigente' : '⏳ Obsoleta'}
                        </span>

                        {!isRead && (
                          <span
                            style={{
                              width: '6px',
                              height: '6px',
                              borderRadius: '50%',
                              background: 'var(--accent-cyan)',
                              display: 'inline-block'
                            }}
                            title="No leída"
                          />
                        )}
                      </div>

                      {/* Exact 24h Time & Relative Age */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                        <Clock size={11} />
                        <span style={{ fontWeight: 600, color: '#cbd5e1' }}>
                          {format24hTime(al.timestamp)}
                        </span>
                        <span style={{ color: 'var(--text-dim)' }}>
                          ({formatRelativeTime(al.timestamp, al.age_hours)})
                        </span>
                      </div>
                    </div>

                    {/* Alert Message Body */}
                    <div style={{ fontSize: '0.82rem', color: 'var(--text-main)', lineHeight: '1.4', margin: '4px 0 6px 0' }}>
                      {al.message}
                    </div>

                    {/* Footer Action Link */}
                    <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', fontSize: '0.72rem', color: 'var(--accent-cyan)', gap: '3px', fontWeight: 600 }}>
                      <span>Inspeccionar ${al.ticker} en terminal</span>
                      <ExternalLink size={11} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
