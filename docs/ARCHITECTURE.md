# Architecture — draft for interrogation

**Status: DRAFT except accepted [ADR-001](adr/0001-hybrid-strategy-execution.md), [ADR-002](adr/0002-in-process-risk-gateway.md), [ADR-003](adr/0003-account-wide-order-uncertainty.md), [ADR-004](adr/0004-configurable-conditional-recovery.md), [ADR-005](adr/0005-tiered-data-evidence.md), and [ADR-006](adr/0006-independent-validation-isolation.md).** Do not treat other design options as settled.

## Domains and trust boundaries

```text
Cloud LLM API ---> Research Orchestrator ---> Isolated Research Worker
                         |                         |
                         v                         v
                   Research Memory       Candidate Artifacts + Results
                                                  |
                                         Independent Evaluator
                                                  |
                                        Strategy Registry / Gate
                                                  |
                  Market Data ---> Strategy Runtime (no broker access)
                                        |  trade proposal
                                        v
                                   Portfolio Intent
                                        |
                                   Independent Risk
                                        |
                          Durable Order State Machine
                                        |
                                  Broker Adapter
                                        |
                                 Account Reconciliation

CLI now / private web dashboard later ---> Authenticated Control API
                                         (never direct broker access)
```

The diagrams describe logical roles, not necessarily separate processes or servers. Cloud LLM inference is mandatory **only for AI tasks**; trading and risk enforcement must not depend on its availability.

## Accepted decision: hybrid strategy execution (ADR-001)

- **Local and remote strategy decisions are both allowed.** Each produces a versioned, authenticated, time-bounded proposal via one contract and a locally enforced Portfolio → Risk → Execution path. Remote compute has no brokerage or risk-config privileges.
- **Cloud loss does not authorize stale trades.** Missing or expired proposals cannot add risk; local risk, ledger and reconciliation remain operational.
- **No runtime format chosen yet.** WASM versus a restricted native worker versus declarative/remote computation is still open.
- **Cross-platform direction:** Windows x64 for development; macOS ARM64 (Mac mini) or Linux x64/ARM64 as *possible future* low-power deployment hosts. Broker-specific compatibility remains unproven and may require a separate gateway.

## Accepted decision: in-process risk module and one order gateway (ADR-002)

- **One trusted Rust core process:** Risk Kernel and Execution Engine are separate internal modules in the same `stratided` process. No independent risk daemon initially.
- **Mandatory local gate:** strategies, research Agent and Web UI submit proposals only. Broker order emission is reachable only through a constrained Execution Engine path consuming valid, approved intents.
- **Untrusted code is outside the trusted process.** Rust module separation is not OS process isolation, and cannot prevent all bugs inside the core itself; critical order/risk paths need focused financial-risk tests.
- **Persistent halt state:** breaker and ambiguous-order state survive restarts; do not add risk while state is unknown. Technical recovery is controlled by ADR-004; loss-breaker release remains independent.

## Accepted decision: account-wide halt on broker uncertainty (ADR-003)

- If a broker order submission has an uncertain outcome (e.g. timed out after possible acceptance), persist an unknown-order state and **halt new risk across the entire account**, including unrelated strategies and instruments.
- Never infer rejection from a timeout or blindly re-submit. Query broker orders, executions, cash and positions and reconcile before restoring new-entry eligibility.
- Existing holdings and risk-reducing operations require actual state knowledge; do not automatically liquidate or issue duplicate protective orders.
- This halt survives restart. Restoration after verified reconciliation follows the **configurable conditional-auto/manual policy** in ADR-004; loss breakers do not auto-clear.
- Assume subsequent order submissions may fail as well; avoid repeated probes that create more uncertainty. Use bounded, backoff-aware read queries when available.

## Accepted decision: configurable technical recovery policy (ADR-004)

- **Default `conditional_auto`:** auto-release technical/account-connectivity entry halt only after authoritative order/fill/cash/position reconciliation, stable broker connectivity, and no active risk breaker; re-evaluate signal age and trading eligibility rather than replaying stale orders.
- **Configurable `manual`:** even after reconciliation, require authenticated Owner approval. Neither mode can bypass reconciliation or release financial-loss/drawdown circuit breakers.
- **Repeated or conflicting failures:** remain halted and require Owner intervention; store reason/evidence/state across restart. Precise stability/repetition thresholds are broker-specific and remain open until adapter design.
- **Trusted configuration only:** Owner settings are audited; Agent and strategies cannot modify recovery authority. Favor a small enumerated choice over UI slider proliferation.

## Accepted decision: tiered market-data evidence (ADR-005)

- **Exploration can use incomplete historical data** provided results are honestly labeled exploratory; doing so does not grant strategy promotion permission.
- **Formal historical promotion evidence** must independently establish point-in-time availability for all features used at each decision (including announcement/revision timing where relevant). Avoid look-ahead, revision and survivorship bias.
- **Forward-observed evidence** is permitted when point-in-time history is unavailable: collect strategy signals, actual input snapshots and simulated execution outcomes prospectively, without retroactive rewriting or confusing exploratory results with verified backtests.
- Research Agent cannot certify its own data or backtest as promotion-grade evidence. The independent Evaluator enforces evidence boundaries; shadow trading is not live trading.
- No mandate to acquire expensive data or exhaustively verify all exploration inputs at M0; spend verification effort only when financial decisions depend on it.

## Accepted decision: independent validation isolation (ADR-006)

- **Open-ended research remains unrestricted in strategy families**, but the independent Evaluator controls formal holdouts, evaluation rules and promotion-grade metrics. Research Agent cannot certify its own results.
- Freeze the candidate's code/model hash, parameters, dataset version and research lineage **before** protected evaluation. Subsequent modifications form a new candidate.
- Record evaluation attempts and held-out windows; limit repeated peek/optimization against the same holdout. High backtest scores across thousands of trials are not necessarily evidence of tradeable alpha.
- Forward-observed paper/shadow testing of a frozen candidate on genuinely new data supplements independently validated point-in-time backtests. Account for costs and execution realism.
- **No-edge and no-promotion are valid outcomes.** Evaluation success is not itself live-trading authorization. Exact statistics, budgets and gate criteria are separate future choices.

## Likely implementation boundaries

- **Production core:** lightweight Rust daemon, no GPU; data, risk, ledger, order state, broker abstraction.
- **Research:** external model providers and isolated compute workers; no account credentials.
- **Persistence:** SQLite for authoritative trading/operational state; Parquet possibly for research datasets. Need transaction/backup design.
- **Strategy runtime:** local lightweight workers or remote compute behind a unified proposal boundary (ADR-001). Artifact format (WASM/native/other) is not selected.
- **User interface:** CLI initially; authenticated Control API loopback-only; future standalone Web Dashboard for a private site.
- **Deployment:** Windows now; macOS ARM64 Mac mini or Linux mini PC later if justified. No required Docker, Redis, Kafka, or Kubernetes in the core.

## Invariants worth protecting

1. Research code never directly places orders or changes live risk limits.
2. Unknown broker state cannot trigger a blind duplicate order.
3. Risk circuit breaker state persists across restart and cannot be overridden by research agent.
4. Real order and ledger events are durable, attributed and reconcilable.
5. Strategies can see only data available at the decision timestamp; use event-time + available-at semantics.
6. Unavailable cloud AI may pause research, but does not remove account safety controls.
7. Failed/unsupported strategy promotion results in no production change.
8. There is a legitimate no-trade/no-edge outcome.

## Open design questions (not decisions)

- Which **local strategy runtime/artifact format** best enforces the hybrid proposal boundary while supporting unusual ML/AI strategies?
- What is the minimum broker interface needed for authentic paper fills and later live A-share compliance?
- How do we define and verify account-equity daily-loss and high-water-mark drawdown thresholds?
- What is the minimal risk-gate API, and how should loss-breaker release differ from ADR-004's technical-only recovery?
- How to choose practical evaluator holdout reuse limits, diagnostics and promotion criteria for actual candidate strategies without unnecessary statistical infrastructure?
- Which parts of research can run with bounded CPU locally vs remote-only workers?
- What constitutes strategy promotion and when is human authorization mandatory?
- Which data can be stored/shipped to external providers under licenses and privacy expectations?
- What is the resource budget and minimum uptime/recovery test for macOS/Linux mini PC deployment, considering broker compatibility?

See `docs/GRILL_BRIEF.md` for a discussion-ready agenda.
