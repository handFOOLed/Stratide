# Architecture — draft for interrogation

**Status: DRAFT except accepted [ADR-001](adr/0001-hybrid-strategy-execution.md), [ADR-002](adr/0002-in-process-risk-gateway.md), [ADR-003](adr/0003-account-wide-order-uncertainty.md), [ADR-004](adr/0004-configurable-conditional-recovery.md), [ADR-005](adr/0005-tiered-data-evidence.md), [ADR-006](adr/0006-independent-validation-isolation.md), [ADR-007](adr/0007-conservative-frequency-matched-simulation.md), [ADR-008](adr/0008-dynamic-portfolio-capital-cap.md), [ADR-009](adr/0009-auto-promotion-owner-veto.md), [ADR-011](adr/0011-immediate-promotion-nonblocking-notifications.md), [ADR-012](adr/0012-adaptive-research-daily-hard-budget.md), [ADR-013](adr/0013-one-time-cloud-data-consent.md), [ADR-014](adr/0014-isolated-strategy-workers.md), [ADR-015](adr/0015-automatic-data-manager-network-isolation.md), [ADR-016](adr/0016-verified-data-source-failover.md), [ADR-017](adr/0017-single-writer-durable-recovery.md), [ADR-018](adr/0018-equity-based-loss-drawdown-breakers.md), [ADR-019](adr/0019-account-and-strategy-risk-layers.md), [ADR-020](adr/0020-versioned-requalification-auto-promotion.md), [ADR-021](adr/0021-group-isolation-shared-instrument-attribution.md), [ADR-022](adr/0022-trusted-cross-group-intent-netting.md), [ADR-023](adr/0023-single-market-reference-internal-transfer.md), [ADR-024](adr/0024-prorata-partial-fill-attribution.md), [ADR-025](adr/0025-adaptive-risk-budget-decay-quality-gates.md), [ADR-026](adr/0026-budgeted-shadow-observation-and-local-strategy-registry.md), [ADR-027](adr/0027-historical-failure-as-evidence-not-permanent-ban.md), [ADR-028](adr/0028-dedicated-broker-account-initial-live.md), [ADR-029](adr/0029-owner-manual-takeover-explicit-return.md), [ADR-030](adr/0030-owner-takeover-pending-order-choice.md), [ADR-031](adr/0031-inline-confirmation-for-protective-order-cancellation.md), [ADR-032](adr/0032-manual-trades-suspense-ledger-unassigned-attribution.md), [ADR-033](adr/0033-owner-explicit-manual-fill-group-attribution.md), [ADR-035](adr/0035-record-date-corporate-action-group-attribution.md), and [ADR-036](adr/0036-owner-approval-for-voluntary-corporate-actions.md) (which supersedes [ADR-010](adr/0010-configurable-deployment-grace-period.md)).** Do not treat other design options as settled.

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
- **Independent local/remote strategy Workers are accepted (ADR-014).** Flexible Python/NumPy/PyTorch workloads run outside the Rust core; WASM is optional, not a required artifact/runtime format. Exact OS isolation and protocol fields remain implementation details.
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
- **No-edge and no-promotion are valid outcomes.** Passing the Evaluator is only one prerequisite: a separate trusted Promotion Gate checks the independently verified evidence and Owner veto/previously authorized live scope (ADR-009). Exact thresholds remain open.

## Accepted decision: conservative, frequency-matched execution simulation (ADR-007)

- **Default first-stage simulation is daily-bar and conservative** about fills. An OHLC price touch is not proof of execution; never assume favorable intrabar ordering without adequate data.
- Enforce **instrument-specific** trading rules where applicable: lot sizes, trading/settlement availability (including T+1 only where it applies), suspensions, price limits, tick sizes, fees/taxes, and plausible execution costs/liquidity.
- Separate decision data availability from execution time: a close-derived signal must not be backfilled at the same known closing price without a supported execution mechanism.
- Models needing minute/tick/order-book information may be explored freely, but are not promotion-eligible on an unsupported daily-bar simulation. Add higher-fidelity simulators only when credible candidate strategies justify them.
- M0 validates a minimal paper-only, reproducible order/risk/ledger slice rather than an extensive microstructure exchange simulator.

## Accepted decision: dynamic portfolio allocation and account-principal cap (ADR-008)

- Portfolio-level funds are a **single shared cash/positions ledger**. Qualified strategies may receive dynamic weights within the owner's authorized capital and independent risk constraints; a unit of cash cannot be simultaneously allocated twice.
- **Hard research scale limit:** backtest and forward-paper initial capital must not exceed the Owner-authorized account principal. The Agent cannot increase it, invent external deposits, use default leverage, or turn a not-yet-funded illustrative account size into verified capital.
- Standalone candidate backtests may each use the same capped initial capital for comparison; a concurrent multi-strategy portfolio must share one actual simulated cash balance and cannot add those standalone capitals together.
- Owner research-capital authorization is **not** the same as the maximum market exposure allowed by the Risk Kernel. Profit/loss and cash flows are reported honestly; test profit cannot silently raise the principal authorization for a new trial.
- Allocation authority does not itself confer strategy promotion permission. A separate trusted Promotion Gate may autonomously promote eligible, non-vetoed strategies **only inside Owner-preauthorized live capital/risk limits** (ADR-009).
- M0 only needs a constrained shared paper ledger and one rejection demonstrating the capital/risk limits, not an optimizer.

## Accepted decision: autonomous strategy promotion with Owner veto (ADR-009)

- **B is the target for eventual live capability:** the trusted Promotion Gate can automatically promote independently validated, versioned strategies when live mode has separately been enabled and all preauthorized account/capital/risk limits are satisfied. A mandatory per-strategy Owner approval step is **not** the default.
- **Owner can reject any strategy for any reason.** Persist strategy bans/vetoes in trusted state, prevent Agent overrides and notification-based approval loopholes; rejection blocks new risk immediately. Existing orders/positions are managed conservatively, not blindly liquidated.
- **No promotion power for the Agent itself.** The Evaluator and Promotion Gate hold distinct decision authority, and neither can change Risk Kernel rules or raise authorized account principal.
- No broker or live-promotion implementation belongs in M0; exact qualification standards, veto scope and safe unwind policy remain to be designed.

## Accepted decision: immediate autonomous activation; optional grace period (ADR-011)

- ADR-011 **supersedes ADR-010's default wait**. The trusted Promotion Gate may automatically activate independently validated, non-vetoed strategies within previously Owner-enabled live, capital, and risk scope. Default `promotion.grace_period = 0m`.
- The Owner may explicitly choose a 10-minute (or other permissible nonzero) delay; Agent cannot modify this setting or Owner vetoes. Waiting is optional, never mandatory per-strategy human review.
- User sleep, unavailable phones, or failed routine delivery must not block otherwise authorized promotion. Record actions and provide a low-noise daily strategy summary; issue high-priority risk alerts separately.
- Always recheck qualification, available budget, account and risk freezes, current exposure and veto at activation. **Risk limits cannot guarantee realized loss ceilings** during gaps, limit-down, halts, T+1, or broker failures; independent evaluation remains mandatory.
- Many simultaneous strategies use one shared allocation and exposure budget (ADR-008), not separate copies of principal. Exact selection/retirement policy is open.
- M0 remains paper-only; no real orders or promotion machinery.

## Accepted decision: adaptive research with a daily Owner hard cap (ADR-012)

- **Research Agent plans its work autonomously** within the Owner-set `research.daily_spend_limit`; no valid cap means no paid research starts. Agent cannot raise the cap, auto-top-up or borrow trade principal for experiments.
- **Trusted, shared Budget Gate** accounts for daily consumed fees and conservative reservations for concurrent / cross-day LLM, remote compute or metered research calls before launch. Exhausted budget pauses new paid research, **not** live risk/ledger/order controls.
- Provider billing lag and unbounded metering mean an app-only budget gate is **not a perfect guarantee** of final provider charges; reconcile actual invoices and use provider-side caps where available.
- Define Owner-configured daily reset timezone and billable cost categories when provider interfaces are chosen. Operational critical API costs need a **separate** budget and safe service-failure behavior.
- Keep M0 paper-only; no paid-research orchestration platform or artificial daily monetary figure.

## Accepted decision: persistent cloud research-data authorization (ADR-013)

- **One explicit consent for a defined receiver, research purpose and data scope**, then reuse it for subsequent requests and account updates; do not pester the Owner with per-call or per-field approvals.
- Owner may allow **rich account context** (holdings, cash history, trades, portfolio metrics and research logs) for cloud analysis. It is not inherently limited to anonymized percentages when explicitly authorized.
- Scope expands or receiver/purpose changes only with a new Owner authorization. The Owner can inspect or revoke future sharing at any time. Do not claim a revocation erases third-party records already transmitted.
- No cloud research-side access to broker credentials, execution tokens, account identity secrets, Owner settings or risk-configuration write interfaces. Market-data provider redistribution licenses and specific provider retention/training policies must be checked.
- Keep the control lightweight, trusted and auditable; **permission to read/share data is not permission to trade**. M0 does not implement cloud account synchronization.

## Accepted decision: independent isolated strategy workers (ADR-014)

- Run untrusted generated strategies in **separate local restricted processes or remote isolated Workers**, not as dynamically loaded code inside `stratided`. Local CPU/resource-light strategies and remotely computed intensive strategies share one authenticated, versioned, time-limited proposal boundary (ADR-001).
- Python and practical scientific/ML ecosystems are permitted in Workers; **WASM is not mandatory**. Existing production strategy artifacts must be frozen and independently validated before eligibility (ADR-006/009).
- Process separation alone **does not prove containment**. Limit access to filesystem, host environment/secrets, child processes, network, CPU/memory and wall-clock time using platform-verifiable restrictions. If a particular Windows/macOS/Linux host cannot enforce its required sandbox policy, place the workload in trusted isolated remote compute or reject it, not in the credential-bearing core.
- Worker crash, misbehavior or disconnection must not bypass Portfolio/Risk/Execution or authorize stale proposals. Worker never owns broker keys, a brokerage API, production ledger writes or Owner risk-setting writes.
- **ADR-015 settles production Worker network posture:** deny arbitrary internet egress and obtain market/feature data through a trusted Data Manager; research Workers retain appropriately controlled external discovery. OS sandbox implementation and proposal serialization remain open. Avoid large plugin systems and speculative cross-OS sandbox matrices in M0.

## Accepted decision: automated data discovery with a trusted Data Manager (ADR-015)

- **Agent research can discover and test external sources** in isolated research environments, while production Strategy Workers have **no arbitrary internet access**. A trusted Data Manager feeds them normalized, permission-checked market and research inputs.
- Automatically use legally accessible, trusted built-in public sources. Automatically discovering a new source does **not** permit Agent-written adapters to execute inside the trusted core: promote sources into production only after lightweight source, security, quality and licensing checks.
- Trusted adapters own API keys, request limits, cache, provenance, source versions, `event_time` and `available_at` semantics. Never expose an arbitrary-URL proxy, broker interface or owner-risk writes to Workers.
- First-time Owner authorization is needed for new billable services, API keys and previously unapproved sensitive account-data transfers; existing authorized use follows ADR-013 without repetitive prompts. Research spend remains bounded by ADR-012.
- Production data uncertainty/staleness must not be treated as fresh execution evidence. ADR-016 permits automatic failover to trusted fresh backup sources; unresolved material conflicts or missing data halt new exposure for affected dependent strategies.
- Data Manager is a **logical trust boundary**, not a requirement for a new microservice. M0 remains paper-only and does not require real data subscriptions.

## Accepted decision: verified automatic source failover (ADR-016)

- Data Manager can autonomously replace a failing primary with an **already-approved, legally usable, compatible and fresh** backup, after normalizing instrument identities, sessions, units, price adjustments and availability timestamps.
- **Unexplained material conflicts or no valid feed** freeze new risk for instruments/strategies dependent on the compromised data; a compromised shared portfolio input affects all its consumers. No favorable source-picking, fake quotes, stale signal replay or blind liquidations.
- Data-feed uncertainty is distinct from **ADR-003 account-wide order uncertainty**: ambiguous broker submissions continue to freeze the entire relevant account; new market data cannot resolve them.
- Audit provider IDs, switch dates and data versions; require consistent/healthy source before switching back to prevent flapping. Emergency failover cannot trust unapproved adapters, new paid sources or missing privacy consent.
- Provider thresholds and real adapters are future phases, not M0.

## Accepted decision: single execution writer with durable recovery (ADR-017)

- **One trusted trading writer per actual broker account.** Do not build dual-active or automatically promoted backup trading instances. A same-host exclusive lock prevents duplicate local core processes but **does not protect across hosts**; transferring live authority to Windows/macOS/Linux requires ensuring the old machine can no longer submit orders before enabling the new machine.
- Persist order intent and uncertain statuses, broker correlation IDs, fills, cash/positions, risk breakers, Owner authority/veto and strategy version references in reliable local state. Backup with consistent snapshots and restore validation, not naive copies of a live database.
- **On restart, no immediate new risk.** Reload and validate critical state, recover technical halt/unknown-order flags, then use authoritative broker order/fill/cash/position reconciliation before resuming live entries. ADR-003 freezes account-wide new risk for uncertainty; ADR-004 governs conditional-auto/manual *technical* recovery, and loss breakers remain unaffected.
- Never blindly replay pending signals or re-submit ambiguous broker orders, and do not auto-liquidate unknown holdings. Old strategy proposals expire rather than turning into fresh decisions on restart.
- Accept downtime when the only host is offline in exchange for simplicity and avoiding duplicate financial actions. M0 needs a paper-only restart/ledger consistency check, not real broker recovery or failover infrastructure.

## Accepted decision: account-equity loss and drawdown breakers (ADR-018)

- **Use trusted whole-account equity/NAV, not only realized P&L**, for daily-loss and peak-to-trough drawdown circuit breakers. Unrealized mark-to-market losses count alongside realized P&L, net fees, cash, positions and relevant payables.
- **Owner deposits/withdrawals are not trading gains/losses.** Compare a cash-flow-adjusted start-of-day baseline and cash-flow-adjusted high-water-mark equity history; avoid false triggers from external transfers or dividends/corporate actions misclassified as external capital.
- The independent Risk Kernel evaluates and persists the baseline, high-water mark, valuation provenance, threshold breaches and resulting financial-risk halt. Financial breakers block account-wide **new risk**, not necessarily trusted risk reductions; no automatic liquidation or guaranteed loss bound.
- **Material uncertainty in account-wide NAV must not be treated as “safe.”** If stale/missing/conflicting marks or mismatched holdings make the full-account breaker unreliable, stop new account risk; data-fault scopes under ADR-016 cannot bypass account risk checks.
- Technical recovery via ADR-004, changing day, quote refresh or process restart may **never automatically clear a financial-loss/drawdown lock**; Owner-controlled release is a separate later design. Numeric limits in `docs/RISK_POLICY.md` remain illustrative rather than settled values.
- M0 only needs a focused paper ledger NAV/update, adjusted deposit/withdrawal case, breaker rejection and persisted restart check, not full multi-asset live valuation.

## Accepted decision: account-plus-strategy risk boundaries (ADR-019)

- **Risk Kernel enforces both layers:** a valid proposal must fit its strategy-level budget/financial lock and the shared account-wide capital, exposure, daily-loss and drawdown rules. Strategy-level pass never overrides an account-level halt; account-level health never excuses a halted strategy.
- **Portfolio Allocator may set dynamic qualified-strategy budgets** only inside existing Owner account authorization (ADR-008). Include in-flight orders and actual shared cash/exposure, avoid double allocation; risk budgets do not create extra principal.
- **Strategy performance is attributable**: link strategy identity/lineage to trades, holdings, marked-to-market realized/unrealized P&L, allocated fees and transfers; internal reallocation must not look like gains. Cross-strategy shared positions require reliable attribution before relying on strategy risk numbers.
- **Strategy losses freeze that strategy's new risk only**, leaving healthy unrelated strategies eligible after *all* other risk checks. Account NAV loss/drawdown (ADR-018) or unknown broker orders (ADR-003) still stops **all new account risk**. Existing orders/positions are managed by trustworthy state, not indiscriminate liquidation.
- **Persist locks and prevent relabeling resets:** Agent cannot rename/split/redeploy the same frozen strategy to reset its risk counters or alter its caps; retain trusted lineage/eligibility and audit. Strategy financial-halt release authority remains an explicit **open** decision (not ADR-004's technical auto recovery).
- Do not build multi-strategy allocation/attribution complexity in M0. One paper strategy ID, credible account/strategy risk-reject contract and persisted state suffice for the lean initial slice.

## Accepted decisions: revised version qualification and group-level data isolation (ADR-020/021)

- ADR-020: A changed parameter or model creates a new immutable strategy version, not an automatic trading permission. After independent validation and forward observation, a newly qualified version can be autonomously deployed within Owner approval and risk scope. Previous versions retain losses and locks.
- ADR-021: Multiple groups may trade the same security, with distinct group ID, private research, signals, state, virtual holdings and P&L attribution. One group cannot implicitly read or overwrite another's internal data.
- A trusted account ledger still holds all real cash, orders, fills and positions. Group virtual allocations reconcile to it. Account-wide exposure/risk reflects all groups; default isolation cannot conceal total risk. Common market data is shareable.
- ADR-022 accepts trusted pre-execution aggregation/netting of opposite group intents, conditional on eligible owned inventory and account/strategy risk checks. Internal virtual attribution transfers are not broker fills; precise reference-price, matching window and partial-fill attribution remain open. M0 remains one paper strategy/group.

## Accepted decision: trusted cross-group order-intent netting (ADR-022)

- Each group independently emits authenticated, timestamped, versioned buy/sell/target intents. The trusted Portfolio Allocator aggregates compatible same-instrument intents **before** mandatory portfolio and Risk Kernel approval, yielding the actual net external order, if any.
- A buy-100 / B sell-100 pair may lead to **zero broker order** if group B owns verifiable, eligible shares and the trusted book can make a fair, auditable **virtual allocation transfer**. Such transfers are not actual exchange trades and cannot create physical shares, real brokerage P&L or cash.
- Before allocation and netting enforce account-wide/strategy limits, shared order commitments, genuine sellable inventory, settlement restrictions (including relevant A-share T+1), session rules and current Owner permissions. Unknown/invalid group positions cannot be self-matched into fake fills or hidden losses.
- Non-offset net orders only affect real positions/cash after actual verified broker fills. Track origin intents → internal reallocation events → submitted order → broker fills → group virtual attribution; partial fills require deterministic accounting. Do not feed one group's private signals into other groups.
- **ADR-023 fixes internal transfer valuation:** both groups use the **same trusted market-reference-price snapshot** for each auditable virtual allocation transfer; the transfer is not a broker fill, creates no real trading fees/spread or extra account P&L. Exact quote-field selection, execution-window alignment and partial-fill attribution remain open. M0 must not build multi-group netting machinery.

## Accepted decision: one trusted internal allocation reference price (ADR-023)

- For a permitted virtual transfer between groups, Portfolio Allocator supplies **one trusted market reference price** with an instrument identity, timestamp, `available_at`, source/version and unique event ID. Both transfer sides use the identical quantity and price; neither group or Agent chooses its favorable bid/ask side.
- Treat the entry as **internal virtual share/cost-basis attribution only**. It may reclassify group-level virtual unrealized/realized performance but **must not create a broker fill, actual cash or tax/fee expense, market spread revenue or incremental total account equity**. Group virtual slices always reconcile to physical account positions.
- An invalid/stale/conflicted quote or missing eligible transfer inventory blocks that internal allocation; ADR-016 trusted source checks and trading/settlement rules apply. Preserve idempotent records and unmodified group research/signal isolation.
- Precise internal-transfer reference quote and execution windows remain implementation choices. **ADR-024 settles external partial-fill attribution: equal-priority groups split confirmed fills pro rata; preauthorized risk-reduction priorities may supersede.** M0 remains single group and has no internal transfer engine.

## Accepted decision: proportional attribution of external partial fills (ADR-024)

- If the trusted Portfolio Allocator combines compatible same-side intents into one brokerage order, divide **actual broker-confirmed fills** among eligible groups within the same pre-established execution priority by their valid remaining quantity proportions. Example: demand 200 + 100, confirmed fill 90 → group attribution 60 + 30, not 300 filled.
- The independent Risk Kernel may authorize an objectively verified **risk-reducing** intent priority before routing. Strategies cannot self-label urgent requests or change priority after seeing a favorable fill; groups at the same priority share proportionally, not by signal arrival timestamp.
- Use discrete share quantities, deterministic and auditable rounding/remainder allocation with precommitted tie-breaking. Group attributed quantities must sum exactly to attributable confirmed broker fills, never exceed permitted group demand, and reconcile with the physical account. Unknown broker executions remain unresolved per ADR-003, never treated as fills.
- Attribute confirmed prices and actual aggregated fees/costs according to a precommitted consistent method, with exact account totals and no hindsight favoritism. Cumulative partial fills, cancel/restart/replayed callbacks must be idempotent and must not duplicate allocations.
- ADR-023's **virtual internal transfers** are not external broker fills and carry no real trading fees. Concrete partial-fill price-lot/cost remainder conventions remain later implementation details. Do not implement cross-group fill accounting in M0.

## Accepted decision: bi-directional adaptive strategy risk budgets with safety-quality gates (ADR-025)

- **Strategy acceptance is distinct from budget sizing.** An independent Evaluator and trusted Promotion Gate decide eligibility; Portfolio Allocator recommends budgets; only Risk Kernel enforces the actual account/strategy/group limits and can reject or cap any increase. The research Agent cannot write financial controls.
- After qualification, **start small, increase only gradually on sustained evidence**, and permit faster reductions/entry halts under verified volatility, liquidity, concentration, cost, and strategy deterioration signals. Market stress is not automatically proof of permanent alpha decay; treat insufficient evidence as uncertainty, not a green light to increase exposure.
- Keep the adaptive decision mechanism **deterministic, explainable, bounded and reproducible**: versioned inputs/parameters, an explicit recommendation record and independent hard risk gates, plus anti-churn hysteresis/cooldown. Do not silently enlarge authorized principal or borrow against paper gains; share account cash and cumulative exposure across all strategies.
- Stale/contradictory data or broker uncertainty never supports a budget increase; do not confuse lowering a risk budget with an executed liquidation. Existing holdings must be handled under genuine tradability/T+1 and broker reconciliation.
- **Quality is a mandatory pre-live condition, not a general promise:** pure-function/invariant and fault-injection tests, deterministic replay, stress/cost/market-regime paper and shadow comparison, accounting consistency, restart persistence, Owner-controlled feature activation/disable for *automatic scaling up*. Financial circuit breakers remain independent and cannot be disabled by the allocator.
- M0 is paper-only and has **no adaptive allocator or strategy decay engine**; preserve the simple future budget proposal interface. Actual metrics, sample requirements, scaling rates and approval limits are future Owner/implementation decisions.

## ADR-026: bounded shadow pool and local strategy registry

- Dormant strategies are not continuously observed. Keep limited active shadow slots under CPU, disk and research budgets; mark observation gaps on resumption.
- Share versioned public market datasets while isolating group-private results. Preserve essential ledger, veto and independent evaluation evidence, and archive less useful experimental detail under retention controls.
- Use local SQLite metadata/search to select a small number of allowed strategy summaries before consuming cloud model tokens; bound result count, repeated expansion and query cost under ADR-012.
- Storage pressure pauses optional research before it can affect critical account state. M0 excludes the pool and registry implementation.

## Accepted decision: historical strategy failures are research evidence, not perpetual bans (ADR-027)

- A failure record in the authorized local Strategy Registry **does not automatically prohibit future exploratory research** into a similar economic idea. Search local immutable hashes, research lineage, feature fingerprints and failed evaluation summaries before paid experiments. A changed hash alone is not proof of unrelated risk.
- Re-exploration should record what has materially changed (data, hypothesis, execution cost, market regime or method), what previous evidence contradicts the idea, and what outcome would falsify the new hypothesis. Cheap exact repeat detection may reuse trustworthy cached evidence, not silently redo identical paid research.
- Rechecking old holdouts does not generate new independent out-of-sample evidence. Freeze new artifacts, retain failures and attempts, and require the independent Evaluator/forward observation and separate trusted Promotion Gate for any fresh live eligibility (ADR-006/020). A past financial halt or an active Owner veto **never** disappears merely because Agent restarts research.
- Keep group-private failure details behind ADR-021/026 authorized search scopes; return only bounded authorized summaries to the LLM. No new Agent authority over research budgets, account Risk Kernel, execution or real broker state.
- M0 has no automated strategy research registry or permanent-failure blacklist. Similarity algorithm and re-research frequency remain open.

## Accepted decision: dedicated brokerage account for initial live operation (ADR-028)

- The first real-money deployment uses a **dedicated broker account** for Stratide, separate from everyday manual trading. Multiple internal strategy groups still use **one shared physical account ledger**; this does not mandate one real brokerage account per strategy group.
- No routine Owner/manual-app or third-party concurrent trading inside this account during automatic operation. This is an operational boundary, **not** a claim that the broker can technically prevent external orders; brokerage permissions and availability of a separate legal account must be verified before live deployment.
- Authoritative broker order/fill/cash/positions/sellable quantities must still be reconciled at start, restart and material discrepancy/uncertainty. Unknown external trades or unexplained balances freeze **all new account risk** until verified; corporate actions, authorized deposits/withdrawals and fees require correct treatment and cannot be misreported as alpha.
- Emergency Owner intervention requires a persisted manual-takeover lock, complete automatic order submission suspension and **explicit Owner return** after authoritative reconciliation per ADR-029. ADR-030/031 govern Owner-selected keep/cancel and protective-order acknowledgement. Do not quietly turn the initial dedicated-account decision into ordinary mixed manual/automated trading.
- Existing ADR-003/004/017 broker uncertainty, single writer and financial lock rules remain binding. M0 has no actual broker account access or manual trade attribution.

## Accepted decision: Owner manual takeover requires explicit return (ADR-029)

- Owner emergency manual takeover of the dedicated broker account is **not** a technical broker disconnection. Persist an independent `OWNER_MANUAL_TAKEOVER` execution-authority lock **before** reporting safe handoff; while active, submit no new Stratide broker orders (including automatic risk-reducing orders), but continue permitted read-only reconciliation, monitoring and notifications.
- Owner-initiated, authenticated return is required; reconciliation success, signal timers, midnight, restart, cloud Agent, or ADR-004 technical `conditional_auto` cannot restore automatic execution authority.
- Returning is **conditional**, not an unconditional order: verify actual broker open orders, fills, settled/sellable positions and funds, account/strategy financial locks, Owner authorizations and a single valid execution writer. Do not replay queued pre-takeover orders; use fresh proposals via independent Risk Kernel.
- Open broker orders may continue or fill after system suspension. **ADR-030 decides the Owner chooses whether to keep existing broker orders or explicitly request cancellation using a red warning action during manual takeover.** Neither choice guarantees a particular fill/cancel outcome. A local stop cannot guarantee an in-flight request was not accepted by the broker; surface uncertainty and fail closed until checked.
- Keep durable handoff/return audit and race-safe order-submission fencing. M0 does not implement live manual takeover UI or broker cancellation.

## Accepted decision: selectable keep-or-attempt-cancel pending broker orders at takeover (ADR-030)

- Present a clear emergency takeover confirmation with **two adjacent actions**: normal `Keep open orders and take control`, red/destructive `Attempt cancellation of open orders and take control`. An independent `Cancel` dialog button is placed on the opposite side and **does not take control or cancel any broker orders**. Do not auto-select a mode.
- Both takeover actions first persist/fence the manual-control state required by ADR-029, stopping new automatic buy/sell submissions. The keep option leaves previously submitted broker orders active and reports that they can fill. The red option invokes a trusted Owner-authorized **broker cancel-request** path only after the handoff lock is durable; that exception is not new strategy order authority.
- Do not equate a cancel request/acceptance with completed cancellation. Continue to reconcile pending-cancel, partial-fill, filled, rejected-cancel and unknown broker results. Under ADR-031, if verified protective orders are included, the red option requires a default-unchecked **inline risk acknowledgement in the same takeover dialog**, not a second modal. Bind acknowledgement to the reviewed order snapshot; refresh/reconfirm when material order/protection status changes. Unknown safety classification must not be silently treated as non-protective; fail conservatively.
- With either takeover mode, Owner must still explicitly return control after complete reconciliation; closing the UI, network recovery or technical autorecovery never does so. No live UI or broker adapter in M0.

## Accepted decision: protective order cancellation requires inline Owner acknowledgement (ADR-031)

- In the ADR-030 takeover dialog, list any recognized protective/risk-reducing pending orders and their instrument, remaining size and risk role. Before selecting red `Attempt cancellation and take control` when such orders are present, Owner must explicitly check a **default-unchecked** acknowledgement that cancelling these orders may remove risk protection. No second dialog; neutral Keep and opposite-side Cancel remain unchanged.
- The confirmation covers one trusted order-list/risk-classification snapshot, **not newly arrived or materially changed protective orders**. A changed snapshot resets acknowledgement and demands refreshed review. If protection classification or order identities cannot be trusted, do not claim cancellation is risk-free or blindly mass-cancel.
- The trusted core must persist/fence ADR-029 manual takeover before any Owner-authorized cancel requests and reconcile actual broker cancel/fill states. No auto-resumption and no such live UI/API in M0.

## Accepted decision: manual account trades enter a suspense ledger until attributed (ADR-032)

- During ADR-029 Owner takeover, broker-confirmed **Owner-manual** fills update the one real account's shares, cash, fees and portfolio risk immediately, with an attributable source record and idempotent broker identifiers. Do not infer strategy ownership of a manual fill by portfolio-share ratio or favor a winning group.
- Maintain a **separate manual-adjustment/suspense attribution view** for unresolved group ownership and P&L/cost basis. Historical strategy slices that now exceed the actual account's shares are **stale claims**, not usable holdings; stop affected strategy execution rather than allowing double-selling.
- Reconcile the real account total against confirmed strategy slices and a clearly identified unresolved difference. Account NAV includes actual broker activity, but group P&L is provisional until a justified, auditable allocation is made. Preserve raw fills, failure/lock history and audit decisions instead of rewriting them.
- Identify fills from already-working Stratide orders by authoritative broker order ID even if they arrive during manual control: existing verified strategy fills keep their original attribution, whereas proven Owner-manual fills or genuinely unknown-source fills enter the appropriate suspense/investigation path.
- Explicit Owner handback does **not** bypass unresolved group allocation, order state or shared account financial locks. If the uncertainty affects account-wide exposure/funds, all new account risk stays frozen; if isolated to known instruments/groups, keep them disabled pending reliable allocation.
- **ADR-033 determines the assignment authority:** only authenticated Owner may explicitly select the eligible group(s) and split quantities for each confirmed manual-trade suspense item. Trusted accounting validates remaining quantities, historic group lots, actual cost/fees and account conservation; never auto-allocate pro rata or let an LLM optimize group P&L. M0 has no live adjustment ledger.

## Accepted decision: Owner explicitly assigns suspense manual trades to groups (ADR-033)

- Display authoritative manual-trade fill references and remaining unallocated amounts from ADR-032; Owner chooses eligible `group_id` values and their quantities, optionally splitting one actual fill among multiple groups. No auto-default share ratios or Agent-generated guess.
- Allocation only creates audited group attribution events; real broker fills/cash/fees and account NAV remain immutable. Require enough verifiable original group inventory for assigned sells and enough actual confirmed purchased shares for buy allocation; reconcile quantities, money, cost basis and fees, keeping manual intervention distinguishable from original automated strategy performance.
- Use versioned snapshots and idempotent immutable events, rejecting stale or exceeding allocations. Do not reset historical loss locks or retroactively rewrite the strategy's trading decisions.
- Unresolved or invalid group attribution blocks relevant group/instrument automation, while shared account uncertainty blocks all new account risk. **Owner handback under ADR-029 is a separate necessary condition.** M0 has no UI or manual broker trade attribution feature.

## ADR-035: record-date corporate action entitlement

Passive dividends and bonus shares are allocated using verified group holdings at the record date. Broker cash and shares remain authoritative, with no double-counting of dividend receivables or split-created paper wealth. Active rights subscriptions are not authorized. This is future work, not M0.

## ADR-036: Owner approval for voluntary corporate actions

Passive dividends and bonus shares stay automatic (ADR-035). Funded rights subscriptions, tender/election choices and other discretionary corporate actions are **Owner-approved per event**, never an automatic Agent action. The trusted system can identify and explain the event and verified deadlines, but no silence or available cash implies permission. Any approved action still requires independent broker, available cash and Risk Kernel checks; broker acceptance and completion must be reconciled. Do not block unrelated strategies for an ordinary declined or ignored optional event. M0 has no such broker action or UI.

## Likely implementation boundaries

- **Production core:** lightweight Rust daemon, no GPU; data, risk, ledger, order state, broker abstraction.
- **Research:** external model providers and isolated compute workers; no account credentials.
- **Persistence:** SQLite for authoritative trading/operational state; Parquet possibly for research datasets. Need transaction/backup design.
- **Strategy runtime:** isolated local Worker process or remote Worker, supporting Python/ML as needed, producing proposals through the same trust boundary (ADR-001/014). WASM is optional; exact packaging and OS sandbox details remain open.
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

- What is the minimal verifiable local OS sandbox and Data Manager interface for Worker read-only access under ADR-014/015 on Windows/macOS ARM64/Linux?
- What is the minimum broker interface needed for authentic paper fills and later live A-share compliance?
- What specific Owner-authorized daily-loss and drawdown threshold levels and reliable NAV mark-price conventions should be configured when real supported assets are known (ADR-018)?
- What is the minimal risk-gate API, and how should loss-breaker release differ from ADR-004's technical-only recovery?
- How to choose practical evaluator holdout reuse limits, diagnostics and promotion criteria for actual candidate strategies without unnecessary statistical infrastructure?
- Which parts of research can run with bounded CPU locally vs remote-only workers?
- What minimal Promotion Gate/veto and portfolio strategy selection policy should enforce ADR-009/011 while retaining genuinely unattended operation?
- For actual chosen AI/data vendors, what license, retention/training, deletion and transfer constraints apply within ADR-013's one-time authorized research scope?
- What is the minimal platform-specific account authority transfer and verified state/backup restore procedure for ADR-017, given actual broker adapter compatibility?

See `docs/GRILL_BRIEF.md` for a discussion-ready agenda.
