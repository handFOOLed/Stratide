import { dependencyStatusView } from './status.ts';
import type { AgentState } from '../state/useAgent';
import type { RuntimeState } from '../state/useRuntime';

export interface ChecklistProgress {
  knownComplete: boolean;
  knownIncomplete: boolean;
}

/**
 * Hide the checklist only when every item is known and done.
 * A still-loading item is neither: a previously dismissed list stays hidden,
 * and a known gap brings it back.
 */
export function checklistProgress(runtime: RuntimeState, agent: AgentState): ChecklistProgress {
  const setupKnown = runtime.status !== null;
  const setupDone = runtime.status !== null && runtime.status.setup_complete;
  const dependencies = runtime.status === null ? null : runtime.status.dependencies;
  const tushare = dependencies === null ? null : dependencies.tushare_credential;
  const marketEod = dependencies === null ? null : dependencies.market_eod;
  const tushareProgress = dependencyProgress('tushare_credential', tushare);
  const marketEodProgress = dependencyProgress('market_eod', marketEod);
  const tushareDone = tushareProgress === 'done';
  const marketEodDone = marketEodProgress === 'done';
  const market = runtime.market;
  // backfillComplete is the only completion bit. A rejected report is a known gap
  // even if a progress file previously caused the list to be dismissed.
  const backfillDone = market !== null && market.backfillComplete === true;
  const backfillKnown =
    market !== null &&
    (backfillDone ||
      market.backfillRunning === true ||
      market.statusKnown === true ||
      market.statusError !== null ||
      market.verification === 'rejected');
  const researchConfigured =
    agent.status !== null && agent.status.default_model !== null && agent.status.budget.state === 'configured';
  const knownIncomplete =
    (setupKnown && !setupDone) ||
    tushareProgress === 'gap' ||
    marketEodProgress === 'gap' ||
    (backfillKnown && !backfillDone) ||
    (agent.status !== null && !researchConfigured);
  const knownComplete =
    setupDone &&
    tushareDone &&
    marketEodDone &&
    backfillKnown &&
    backfillDone &&
    agent.status !== null &&
    researchConfigured;
  return { knownComplete, knownIncomplete };
}

type DependencyRecord = { state: string; reason?: string | null; note?: string | null } | null;

/** A deferred light-status check is unknown, not a gap. A missing credential is a gap. */
function dependencyProgress(
  key: 'tushare_credential' | 'market_eod',
  dependency: DependencyRecord,
): 'done' | 'gap' | 'unknown' {
  if (dependency === null || dependency.reason === 'CREDENTIAL_CHECK_DEFERRED') return 'unknown';
  const view = dependencyStatusView(key, dependency.state, dependency.reason ?? null, dependency.note ?? null);
  return view.kind === 'ok' ? 'done' : 'gap';
}

export function checklistVisible(progress: ChecklistProgress, dismissed: boolean): boolean {
  if (progress.knownComplete) return false;
  if (progress.knownIncomplete) return true;
  return !dismissed;
}

/** Null leaves the stored flag alone. A known gap clears it; a known complete sets it. */
export function nextChecklistDismissed(progress: ChecklistProgress): boolean | null {
  if (progress.knownComplete) return true;
  if (progress.knownIncomplete) return false;
  return null;
}
