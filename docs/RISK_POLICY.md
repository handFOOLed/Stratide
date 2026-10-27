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

An ambiguous broker submission halts **all new risk for the affected account** until trustworthy full-account reconciliation; no blind duplicate sends and no inference that timeout means rejection. Persist the freeze through restart. Confirmed orders, executions, cash and positions are prerequisites to any recovery; whether owner approval is additionally required is still open.

## P0 scenario acceptance examples for later phases

1. Timeout after possible broker acceptance: persist unknown outcome and block **all new account openings**, not only the affected symbol; no blind duplicate retry.
2. Restart while circuit breaker active: breaker remains active.
3. Agent submits trade bypassing risk: rejected at independent gateway.
4. Market event arrives after decision-time: never enters historical strategy inputs.
5. Broker holdings and internal ledger disagree: no new orders until reconciled.
6. Insufficient funds / lot constraints: rejected before order transmission.

In M0 these are **specification-level expectations**, not a claim they already work.
