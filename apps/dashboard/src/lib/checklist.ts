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
  const tushareView =
    tushare === null
      ? null
      : dependencyStatusView('tushare_credential', tushare.state, tushare.reason ?? null, tushare.note ?? null);
  const marketEodView =
    marketEod === null
      ? null
      : dependencyStatusView('market_eod', marketEod.state, marketEod.reason ?? null, marketEod.note ?? null);
  const tushareDone = tushareView !== null && tushareView.kind === 'ok';
  const marketEodDone = marketEodView !== null && marketEodView.kind === 'ok';
  const market = runtime.market;
  const backfillDone = market !== null && market.backfillComplete;
  const backfillKnown =
    market !== null &&
    (market.backfillComplete || market.backfillRunning || market.statusKnown || market.statusError !== null);
  const researchConfigured =
    agent.status !== null && agent.status.default_model !== null && agent.status.budget.state === 'configured';
  const knownIncomplete =
    (setupKnown && !setupDone) ||
    (tushareView !== null && !tushareDone) ||
    (marketEodView !== null && !marketEodDone) ||
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

export function checklistVisible(progress: ChecklistProgress, dismissed: boolean): boolean {
  if (progress.knownComplete) return false;
  if (progress.knownIncomplete) return true;
  return !dismissed;
}
