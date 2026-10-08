import { createContext, useContext } from 'react';
import { SignalThresholds } from '../types';

// Mirrors the defaults in app/config.py. The API serves the live values in `engine.thresholds`;
// these only apply until the first response arrives (or against an older backend).
export const DEFAULT_THRESHOLDS: SignalThresholds = {
  strong_buy: 85,
  buy: 70,
  watch: 55,
  hold: 45,
  avoid: 30,
  strong_avoid: 15,
  risk_gate: 35
};

export const ThresholdsContext = createContext<SignalThresholds>(DEFAULT_THRESHOLDS);

export const useThresholds = (): SignalThresholds => useContext(ThresholdsContext);

// Diverging scale around 50: the same reading the engine uses for its signal bands
export type Tone = 'strong-bull' | 'bull' | 'neutral' | 'bear' | 'strong-bear' | 'none';

export const isNum = (v: number | null | undefined): v is number =>
  v !== null && v !== undefined && !Number.isNaN(v);

export const scoreTone = (score: number | null | undefined, t: SignalThresholds): Tone => {
  if (!isNum(score)) return 'none';
  if (score >= t.buy) return 'strong-bull';
  if (score >= t.watch) return 'bull';
  if (score <= t.avoid) return 'strong-bear';
  if (score <= t.hold) return 'bear';
  return 'neutral';
};

// Risk is a safety score (higher = safer). Red when the capital-preservation gate fires,
// green only on the mirror side of the gate, neutral in between.
export const riskTone = (risk: number | null | undefined, t: SignalThresholds): Tone => {
  if (!isNum(risk)) return 'none';
  if (risk < t.risk_gate) return 'strong-bear';
  if (risk > 100 - t.risk_gate) return 'bull';
  return 'neutral';
};

const SIGNAL_TONES: Record<string, Tone> = {
  'STRONG BUY': 'strong-bull',
  BUY: 'strong-bull',
  WATCH: 'bull',
  HOLD: 'neutral',
  CAUTION: 'bear',
  AVOID: 'strong-bear',
  'STRONG AVOID': 'strong-bear'
};

// `signal` may carry modifiers ("WATCH (HIGH RISK)"); the band is the part before them
export const signalTone = (signal: string | null | undefined, baseSignal?: string | null): Tone => {
  const band = (baseSignal || signal || '').toUpperCase().split('(')[0].trim();
  return SIGNAL_TONES[band] ?? 'none';
};

export const fmt = (v: number | null | undefined, digits = 1, fallback = '—'): string =>
  isNum(v) ? v.toFixed(digits) : fallback;

export const fmtPrice = (v: number | null | undefined, fallback = '—'): string =>
  isNum(v) && v > 0 ? `$${v.toFixed(2)}` : fallback;
