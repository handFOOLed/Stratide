# Financial-Risk-Driven Engineering and Preliminary Risk Requirements

## Priority rules

- **P0:** accidental real order, duplicate submission, lost/incorrect money or positions, bypassed circuit breaker, credential exposure, false backtest evidence promoting unsafe strategies. Realistic tests and fault injection are justified.
- **P1:** market-data quality, crash/restart/reconciliation, reproducible research claims, user-visible incorrect critical state. Focused tests.
- **P2:** metadata, labels, formatting, ordinary UI defects. Simple fallback or one representative test.
- **P3:** non-material speculative edge cases. Do not proactively build defenses.

A minor-looking input becomes P0 **only when** it can cross an execution/security/financial boundary. E.g. a malformed strategy title displayed as text is P2; an untrusted string used in a shell command without isolation is P0.

## Draft guardrails — *not configured or implemented*

These **illustrative** initial numbers must be reviewed against trading strategy, fees and liquidity before live operation:

- Position weight cap per instrument: 10% of equity.
- Total risky exposure cap: 50% of equity.
- Daily net equity loss alert/entry pause: 1%.
- Peak-to-trough account drawdown entry lock: 8%.
- No leverage by default.
- Data stale / portfolio mismatch / unknown broker order: fail closed for **new** risk.

Circuit breakers are **operational triggers**, not guaranteed realized loss limits. A-share T+1, stops, limit-down, gaps, halts, and network failure can prevent execution. Forced liquidation is not an automatic response to unknown account/order state.

## Accepted account-level uncertainty protection (ADR-003)

An ambiguous broker submission halts **all new risk for the affected account** until trustworthy full-account reconciliation; no blind duplicate sends and no inference that timeout means rejection. Persist the freeze through restart. Confirmed orders, executions, cash and positions are prerequisites to any recovery. Per [ADR-004](adr/0004-configurable-conditional-recovery.md), the owner chooses `conditional_auto` (default) or `manual`; repeated technical failures require manual intervention. Network recovery must not release loss/drawdown circuit breakers.

## Strategy evidence integrity (ADR-005)

Data with unverified historical availability may support exploration, **not** live-capital promotion. Formal historical evaluation uses independent point-in-time availability verification; historical publication/revision information must not leak backwards in decision time. Prospective shadow/paper observation can accumulate fresh evidence when trustworthy historical snapshots do not exist; independent review is still required before live promotion.

## Independent evaluator and overfitting controls (ADR-006)

The Agent must not control protected holdout evaluation, fabricate its own qualification, or selectively conceal trial history. Freeze and version submitted candidates; keep evaluation attempts, costs and holdout usage auditable. Repeated testing against the same history reduces its value as independent evidence. Use prospective forward observation on genuinely unseen data before any possible live-money promotion. The final promotion policy is separate and not yet determined.

## Conservative execution simulation (ADR-007)

First-stage historical and paper execution uses **frequency-matched conservative assumptions**: treat day-bar data as insufficient to prove all limit fills or intrabar ordering, and never retroactively execute at the close used to generate the signal. Include realistic eligible-instrument trading constraints (T+1 where applicable, lots, halts, price limits), fees/taxes/slippage and execution uncertainty when measuring net performance. Strategies dependent on finer execution data cannot be promoted based on day-bar fills alone. Do not build a tick exchange simulator for M0.

## Account-principal ceiling for research and portfolio allocation (ADR-008)

The Owner sets the maximum authorized account principal used as starting capital for a research, backtest or paper account; it must not exceed a verifiable real-account capital basis when connected. The research Agent cannot raise that limit or invent deposits. Independent candidate comparisons may each run at the same capped capital; concurrent strategies must share one ledger and cannot double-spend cash. No default leverage or borrowed cash. Distinguish this **starting principal ceiling** from the independent Risk Kernel's potentially lower exposure/position limits; example percentages above remain drafts, not configured permissions. The dynamic allocator may rebalance qualified strategies but cannot approve novel ones for live deployment.

## P0 scenario acceptance examples for later phases

1. Timeout after possible broker acceptance: persist unknown outcome and block **all new account openings**, not only the affected symbol; no blind duplicate retry.
2. Restart while circuit breaker active: breaker remains active.
3. Agent submits trade bypassing risk: rejected at independent gateway.
4. Market event arrives after decision-time: never enters historical strategy inputs.
5. Broker holdings and internal ledger disagree: no new orders until reconciled.
6. Insufficient funds / lot constraints: rejected before order transmission.

In M0 these are **specification-level expectations**, not a claim they already work.
