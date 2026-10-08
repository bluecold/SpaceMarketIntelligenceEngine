import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { Tone, fmt, scoreTone, signalTone, useThresholds } from '../lib/scale';

// --- Scores & signals -------------------------------------------------------

interface ScoreValueProps {
  value: number | null | undefined;
  digits?: number;
  suffix?: string;
  tone?: Tone;               // Overrides the default score scale (e.g. riskTone)
  className?: string;
}

export const ScoreValue: React.FC<ScoreValueProps> = ({ value, digits = 1, suffix = '', tone, className = '' }) => {
  const thresholds = useThresholds();
  const resolved = tone ?? scoreTone(value, thresholds);
  return (
    <span className={`tone-${resolved} ${className}`.trim()}>
      {resolved === 'none' ? '—' : `${fmt(value, digits)}${suffix}`}
    </span>
  );
};

interface SignalPillProps {
  signal: string;
  baseSignal?: string | null;
  className?: string;
}

export const SignalPill: React.FC<SignalPillProps> = ({ signal, baseSignal, className = '' }) => (
  <span className={`signal-pill pill-${signalTone(signal, baseSignal)} ${className}`.trim()}>{signal}</span>
);

// --- Badges -----------------------------------------------------------------

export type BadgeVariant = 'mock' | 'degraded' | 'stale' | 'info' | 'bull' | 'bear' | 'purple' | 'muted';

interface BadgeProps {
  variant: BadgeVariant;
  title?: string;
  className?: string;
  children: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({ variant, title, className = '', children }) => (
  <span className={`badge badge-${variant} ${className}`.trim()} title={title}>{children}</span>
);

interface DataFlagsProps {
  source?: string | null;
  isStale?: boolean;
  ageHours?: number | null;
  ageDigits?: number;
}

// Provenance and freshness flags shown next to a ticker
export const DataFlags: React.FC<DataFlagsProps> = ({ source, isStale, ageHours, ageDigits = 0 }) => (
  <>
    {source === 'MOCK' && (
      <Badge variant="mock" title="Synthetic / mock simulation data active">MOCK</Badge>
    )}
    {source === 'DEGRADED' && (
      <Badge variant="degraded" title="Degraded feed: some pillars excluded or unavailable">DEGRADED</Badge>
    )}
    {isStale && (
      <Badge variant="stale" title={ageHours ? `Data is ${ageHours.toFixed(ageDigits)}h old` : 'Data is stale'}>
        ⏳ {ageHours ? `${ageHours.toFixed(ageDigits)}h old` : 'Stale'}
      </Badge>
    )}
  </>
);

// --- Modal ------------------------------------------------------------------

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

// Open modals, innermost last: Escape and the focus trap only act on the top one
const modalStack: symbol[] = [];

interface ModalProps {
  onClose: () => void;
  labelledBy: string;
  className?: string;
  closeButton?: boolean;
  children: React.ReactNode;
}

export const Modal: React.FC<ModalProps> = ({ onClose, labelledBy, className = '', closeButton = true, children }) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    const id = Symbol('modal');
    modalStack.push(id);
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    dialogRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (modalStack[modalStack.length - 1] !== id) return;
      if (e.key === 'Escape') {
        e.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (e.key === 'Tab' && dialogRef.current) {
        const nodes = Array.from(dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
        if (nodes.length === 0) return;
        const first = nodes[0];
        const last = nodes[nodes.length - 1];
        if (e.shiftKey && (document.activeElement === first || document.activeElement === dialogRef.current)) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      modalStack.splice(modalStack.indexOf(id), 1);
      if (modalStack.length === 0) document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, []);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        ref={dialogRef}
        className={`modal-content ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
      >
        {closeButton && (
          <button type="button" className="btn-close" onClick={onClose} aria-label="Close">
            <X size={20} />
          </button>
        )}
        {children}
      </div>
    </div>
  );
};

// --- Notices ----------------------------------------------------------------

export type NoticeKind = 'error' | 'warning' | 'success' | 'info';

interface NoticeProps {
  kind: NoticeKind;
  children: React.ReactNode;
  onDismiss?: () => void;
  action?: { label: string; onClick: () => void };
}

export const Notice: React.FC<NoticeProps> = ({ kind, children, onDismiss, action }) => (
  <div className={`notice notice-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
    <div className="notice-body">{children}</div>
    {action && (
      <button type="button" className="notice-action" onClick={action.onClick}>{action.label}</button>
    )}
    {onDismiss && (
      <button type="button" className="notice-dismiss" onClick={onDismiss} aria-label="Dismiss">
        <X size={14} />
      </button>
    )}
  </div>
);

// Shared empty / placeholder block
export const EmptyState: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <div className={`empty-state ${className}`.trim()}>{children}</div>
);
