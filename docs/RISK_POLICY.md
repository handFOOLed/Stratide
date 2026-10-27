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
- Daily cash-flow-adjusted account-equity loss alert/entry pause: 1% **(illustrative only; ADR-018 calculation basis accepted, percentage not decided).**
- Peak-to-trough **cash-flow-adjusted** account-equity drawdown entry lock: 8% **(illustrative only; ADR-018 calculation basis accepted, percentage not decided).**
- No leverage by default.
- Data stale / portfolio mismatch / unknown broker order: fail closed for **new** risk.

Circuit breakers are **operational triggers**, not guaranteed realized loss limits. A-share T+1, stops, limit-down, gaps, halts, and network failure can prevent execution. Forced liquidation is not an automatic response to unknown account/order state.

## Accepted account-level uncertainty protection (ADR-003)

An ambiguous broker submission halts **all new risk for the affected account** until trustworthy full-account reconciliation; no blind duplicate sends and no inference that timeout means rejection. Persist the freeze through restart. Confirmed orders, executions, cash and positions are prerequisites to any recovery. Per [ADR-004](adr/0004-configurable-conditional-recovery.md), the owner chooses `conditional_auto` (default) or `manual`; repeated technical failures require manual intervention. Network recovery must not release loss/drawdown circuit breakers.

## Strategy evidence integrity (ADR-005)

Data with unverified historical availability may support exploration, **not** live-capital promotion. Formal historical evaluation uses independent point-in-time availability verification; historical publication/revision information must not leak backwards in decision time. Prospective shadow/paper observation can accumulate fresh evidence when trustworthy historical snapshots do not exist; independent review is still required before live promotion.

## Independent evaluator and overfitting controls (ADR-006)

The Agent must not control protected holdout evaluation, fabricate its own qualification, or selectively conceal trial history. Freeze and version submitted candidates; keep evaluation attempts, costs and holdout usage auditable. Repeated testing against the same history reduces its value as independent evidence. Use prospective forward observation on genuinely unseen data before any possible live-money promotion. The separate promotion policy is established by [ADR-009](adr/0009-auto-promotion-owner-veto.md): a trusted gate may auto-promote eligible candidates inside Owner-preauthorized live limits, subject to an effective, persisted Owner veto. Neither the Agent nor Evaluator may self-grant trading access.

## Conservative execution simulation (ADR-007)

First-stage historical and paper execution uses **frequency-matched conservative assumptions**: treat day-bar data as insufficient to prove all limit fills or intrabar ordering, and never retroactively execute at the close used to generate the signal. Include realistic eligible-instrument trading constraints (T+1 where applicable, lots, halts, price limits), fees/taxes/slippage and execution uncertainty when measuring net performance. Strategies dependent on finer execution data cannot be promoted based on day-bar fills alone. Do not build a tick exchange simulator for M0.

## Account-principal ceiling for research and portfolio allocation (ADR-008)

The Owner sets the maximum authorized account principal used as starting capital for a research, backtest or paper account; it must not exceed a verifiable real-account capital basis when connected. The research Agent cannot raise that limit or invent deposits. Independent candidate comparisons may each run at the same capped capital; concurrent strategies must share one ledger and cannot double-spend cash. No default leverage or borrowed cash. Distinguish this **starting principal ceiling** from the independent Risk Kernel's potentially lower exposure/position limits; example percentages above remain drafts, not configured permissions. The dynamic allocator may rebalance qualified strategies but cannot approve novel ones for live deployment; only a separate trusted Promotion Gate may do so within Owner-preauthorized limits under ADR-009.

## Autonomous promotion and Owner veto (ADR-009)

When live trading has been **separately authorized** by the Owner and financial/risk limits are already enforced, the trusted Promotion Gate (not the Agent) may admit independently qualified strategies without requiring approval for each strategy. The Owner can reject/disable a strategy for any reason; veto state persists and cannot be modified by Agent code. Veto immediately stops new risk from that strategy; existing broker orders and positions need safe reconciliation/exit handling instead of blind forced liquidation. Per [ADR-011](adr/0011-immediate-promotion-nonblocking-notifications.md), the trusted Gate immediately activates independently qualified candidates by default (`0m`) within explicit Owner live authorizations, while the Owner may opt into a 10-minute delay. Routine notification failure does not block promotion, but missing qualification, vetoed strategy, financial freeze, budget or account uncertainty must block it. Risk limits cannot guarantee fills or an absolute realized-loss ceiling. No automatic risk-limit increase, reopening of loss breakers, or unapproved live-mode enablement.

## Independent daily research spending authority (ADR-012)

A trusted budget gate, not the research Agent itself, enforces the Owner-configured daily research spending cap before launching paid model/remote-compute experiments. Include already consumed fees plus conservative per-job reservations across concurrent tasks. The Agent may optimize priorities but cannot top up, change the cap, duplicate allocations or use trading principal. Third-party billing delays mean spend-estimate checks cannot guarantee exact final charges; reconcile bills and use provider-side spending controls where supported. Paid research stops at the cap; existing account/risk/ledger duties continue, and production-critical metered API budgets must be separately handled.

## Cloud research authorization and strict execution boundary (ADR-013)

The Owner may grant a persistent one-time authorization for a specific cloud research receiver, data categories and purpose, including detailed portfolio/transaction history. The trusted control plane reuses it for normal subsequent research queries without re-prompting; scope expansion, a new receiving service or new purpose requires fresh permission. Revocation stops future sending but cannot by itself erase data already transmitted to a vendor. Brokerage secrets, identity credentials, order submission and Risk Kernel writes are never included, no matter what analytical context is authorized. Check the actual API provider's retention/training contract and market-data redistribution licenses. Record authorization changes without scattering raw sensitive data in logs.

## Isolated generated-strategy execution (ADR-014)

AI-generated and other untrusted strategy code must execute in restricted local-process or isolated remote Workers, never as plugins in the trusted Rust risk/execution core. Worker access to broker credentials, direct order routing, risk-policy mutation and production ledger writes is denied; proposals are authenticated, time-bounded and independently risk checked. **Process separation alone is insufficient**: confirm sandboxing constraints on filesystem/environment secrets, network and resource limits before enabling untrusted code on a production machine. Where enforcement is unsupported, deny local execution or relocate to a genuinely isolated environment. WASM is optional, not required.

## Trusted data ingestion boundary and production Worker network rules (ADR-015)

Production strategy Workers must not browse arbitrary websites, directly call uncontrolled third-party APIs, or use a Data Manager as an open URL proxy. Only the trusted Data Manager accesses approved, license-compatible adapters and protects provider secrets; generated Worker code receives governed read-only input with source, availability-time, freshness and quality metadata. Research Agents may discover new sources in isolated research environments, but discoveries alone do not approve new trusted executable adapters. Owner approval is required for new paid services, sensitive-data sharing or API credentials; approved routine fetching needs no repeated prompts. Missing or stale data must not be silently fabricated or treated as a valid basis for opening new risk. Actual vendor selection and conflict thresholds remain open; ADR-016 governs verified automatic failover.

## Automatic verified data source failover (ADR-016)

On primary feed failure, the trusted Data Manager may automatically switch to an approved, fresh and compatible backup. Compare normalized time and `available_at`, symbol/market identity, unit and adjustment semantics before trusting a substitution. With no fresh valid feed or unexplained material cross-source conflict, halt **affected strategies/instruments' new exposure** rather than automatically freezing unrelated trading; expand scope if shared input is affected. Preserve current holdings/ledger and risk duties. Do not choose the favorable provider or rewrite forward records. Switching feeds cannot clear ADR-003's account-wide broker order uncertainty halt. Unapproved/paid/new-consent sources do not gain permissions via emergency failover.

## Single trading writer and crash-safe recovery (ADR-017)

Only one trusted execution instance may have real order authority for a given broker account. Local process locks do not provide cross-host exclusivity; during host migration, old execution authority must be demonstrably disabled before a replacement is enabled. Persist order intents/correlation IDs, submission uncertainty, broker fills, cash/positions, circuit breakers and Owner bans with crash-safe transaction discipline. On startup load and verify state and broker orders/fills/cash/positions before new risk; unknown/ambiguous states trigger ADR-003's account-wide freeze, with any later technical recovery controlled by ADR-004. Never blindly replay prior orders, treat a timeout as a rejection, clear loss breakers, or force-liquidate unknown positions. Backup/restore uses coherent validated snapshots rather than casual copies of a live SQLite database. M0 only requires paper-mode focused recovery testing.

## Account-equity-based financial loss and drawdown breakers (ADR-018)

Compute daily loss and drawdown from trustworthy **whole-account NAV/equity**, including unrealized market moves as well as realized gains/losses, fees and costs. External deposits and withdrawals must be normalized rather than misreported as investment returns; the peak/high-water-mark and daily reference equity must be measured on a consistent cash-flow-adjusted basis. Risk Kernel, not Agent or strategy Worker, owns valuation checks, threshold checks and persistent breaker state. If valuation or holdings are materially unknown, do not assume zero loss: prevent new account risk until equity can be evaluated reliably. Activation stops **new risky exposure** at the account level; risk-reducing management may proceed only when orders/positions are trustworthy and trading rules permit. No automatic liquidation or guarantee of a realized loss ceiling. Restoring quotations, changing the date or performing ADR-004 technical recovery must **not** clear financial breakers. The example 1% and 8% limits above are not Owner-approved production settings.

## P0 scenario acceptance examples for later phases

1. Timeout after possible broker acceptance: persist unknown outcome and block **all new account openings**, not only the affected symbol; no blind duplicate retry.
2. Restart while circuit breaker active: breaker remains active.
3. Agent submits trade bypassing risk: rejected at independent gateway.
4. Market event arrives after decision-time: never enters historical strategy inputs.
5. Broker holdings and internal ledger disagree: no new orders until reconciled.
6. Insufficient funds / lot constraints: rejected before order transmission.

In M0 these are **specification-level expectations**, not a claim they already work.
