import { agentFetch } from './api';

export interface ConsentState {
  version: string;
  required: boolean;
  accepted_at: string | null;
}

export function readConsent(): Promise<ConsentState> {
  return agentFetch<ConsentState>('', 'consent');
}

export function acceptConsent(): Promise<ConsentState> {
  return agentFetch<ConsentState>('', 'consent', { method: 'POST', body: {} });
}
