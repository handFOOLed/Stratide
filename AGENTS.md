# AGENTS.md — Instructions for coding agents

## Mission

Build Stratide for a single owner: a low-resource, initially local, autonomous quantitative trading platform with cloud-only LLM research. The owner prioritizes financial safety and useful working features over theoretical completeness. Work in small, reviewable increments.

## Hard product constraints

1. **No local LLM inference.** All model inference uses replaceable cloud APIs. Heavy experimental compute may run in isolated remote workers. No GPU required on the production host.
2. **No live broker integration in M0.** Paper mode first. Never simulate success by inventing brokerage or market-data results.
3. **Independent risk authority.** Agent-generated strategy code never gets broker credentials, order submission permissions, risk-configuration write access or production data-store write privileges.
4. **Loss circuit breakers remain.** Trading and operational risk checks must survive process restart. A stop-trigger is not a guarantee of fill or maximum loss. On uncertain order status, reconcile before retrying.
5. **Open-ended research.** Do not limit exploration to a hard-coded family of technical indicators. Research freedom does not imply production deployment permission.
6. **Local-first, deployable later.** Develop on Windows; plan for optional low-power macOS ARM64 Mac mini or Linux mini PC and private Web Dashboard, without building cloud infrastructure prematurely.
7. **No forced GUI.** Headless service and CLI first, Web Dashboard later, with core decoupled from front end.
8. **Financial correctness.** Use integer shares and decimal/fixed-point currency types when implemented; maintain time-of-availability data semantics; account for A-share constraints when applicable.
9. **Costs matter.** Minimize subscriptions, trading friction, compute cost, CI cost and owner review effort.

10. **ADR-002: in-process mandatory risk gate.** Keep Risk Kernel and Execution Engine as distinct modules in the trusted Rust core process, with a single order submission path. Do not load untrusted Agent-generated code into that process; the broker adapter must not accept unreviewed strategy proposals. Revisit process separation only for a concrete financial-risk reason.

11. **ADR-003: account-wide uncertainty halt.** A submission timeout/unknown broker order freezes all new account risk across instruments and strategies. Persist the halt, do not retry blindly, reconcile broker orders/fills/cash/positions first. ADR-004: configurable `conditional_auto` default or `manual`, both requiring successful authoritative reconciliation and connection health. Repeated faults require manual attention; loss/drawdown breakers never auto-clear because connectivity recovered. Only Owner via trusted management may change this policy; Agent cannot.

12. **ADR-005: tiered research-data evidence.** Research may explore on incomplete/uncertain historical data but must label such results exploratory. Only an independent evaluator may classify verified point-in-time historical evidence; prospective shadow observations are separately timestamped and cannot be retrospectively rewritten. Never use exploratory backtest claims as sole grounds for real-money promotion. Avoid exhaustive exploratory input hardening.

13. **ADR-006: evaluator independence.** Never give the research Agent access to protected holdout answers or the authority to certify itself. Freeze candidate code/model/version/params before formal evaluation, track submission history and holdout reuse, do not treat one lucky backtest as an edge, and use genuinely forward-observed evidence before live promotion. Do not build needless experimental statistical infrastructure at M0.

14. **ADR-007: pragmatic conservative paper fills.** Use an initial daily-bar simulator with traceable fill and cost assumptions; do not pretend OHLC price touches or same-bar closes guarantee execution. Apply instrument-specific trading rules, including T+1 only where applicable, applicable limit/lot/suspension rules, and fees. Allow higher-fidelity simulation later only for strategies that actually require it; no speculative exchange microstructure framework at M0.

15. **ADR-008: dynamic allocation, hard research-principal cap.** A research/backtest/forward paper run's initial capital may not exceed explicit Owner-authorized account principal (do not treat approximate target CNY 100,000 as deposited funds). The Agent cannot raise it or invent deposits, borrowings or default leverage. Independent candidate tests can each use the capped capital for comparison; simultaneous strategies must share one real simulated cash/position ledger. Allocation changes cannot override Risk Kernel limits or grant live strategy promotion. Avoid building portfolio optimization machinery in M0.

16. **ADR-009: default eventual autonomous promotion, Owner veto.** A separate trusted Promotion Gate may admit independently validated strategies without individual human approval **only after** the Owner has explicitly enabled live mode and authorized capital/risk limits. The Owner can veto/disable any strategy, for any reason; persist and enforce bans against fresh deployment and new risk, without unsafe forced liquidation. Agent/strategy cannot self-approve, rewrite vetoes or expand budget/limits. M0 remains paper-only.

17. **ADR-010 superseded by ADR-011: immediate default promotion.** A trusted Gate may immediately activate independently validated strategies (`promotion.grace_period = 0m`) after explicit initial Owner live authorization and checks of portfolio funds, risk freezes and veto state. Owner may opt into a 10-minute grace period; Agent cannot change settings. Do not block otherwise authorized promotion on routine notifications or user being asleep. Aggregate ordinary events into daily summaries and alert on material incidents. Risk controls do not guarantee maximum realized loss. M0 is paper-only.

18. **ADR-012: research spending budget.** Agent may schedule/prioritize paid research only within a trusted Owner-defined `research.daily_spend_limit`. Before each paid call reserve conservative worst-case budget in a shared daily ledger, including concurrency and current commitments. No set cap → do not launch billable research. Agent cannot raise the cap, auto-top-up or spend trading principal. Provider billing lag may cause real charges to differ; reconcile and use provider-side limits where available. Budget exhaustion pauses research only, never disables risk/execution/reconciliation. Owner sets actual amount and reset timezone later; no FinOps frameworks in M0.

19. **ADR-013: once-authorized cloud research context.** Owner authorizes a specific receiving cloud service/purpose/data scope once; re-use that persisted grant without annoying per-request consent prompts. Rich authorized position, cash, trade and research-history inputs are permissible. New service, purpose or materially new data category requires another explicit grant; Owner can revoke future sending. Broker credentials, account secrets, actual execution capability and risk-policy writes stay exclusively in trusted local control regardless of sharing preferences. Check real provider retention/data redistribution rules; do not promise revocation deletes already transmitted records. Keep this simple; no enterprise IAM in M0.

20. **ADR-014: untrusted strategy Workers.** Run generated strategy code exclusively in separate restricted local Worker processes or isolated remote workers. Support appropriate Python/scientific/ML dependencies without forcing WASM, but never load generated code into trusted Rust `stratided`. Worker output is only an authenticated, versioned, expiring proposal subjected to Portfolio → Risk → Execution. No Worker access to brokerage keys, order API, production ledger writes, risk-limit writes or local secrets. OS child processes are not security sandboxes; apply verifiable file/network/compute restrictions or reject unsafe local execution. Do not build complex runtime orchestration in M0.

21. **ADR-015: automatic data management, no arbitrary production Worker egress.** Let isolated research Agent discover and evaluate public data sources, but use a trusted Data Manager to expose approved standardized inputs to production Workers. No arbitrary external network access, secrets, broker APIs or open-URL proxy from production Worker. Built-in compliant public sources should work without manual per-source setup. Agent-discovered adapters must pass lightweight trust/licensing/quality checks before trusted integration; never execute untrusted fetched code in the trusted Rust core. First-time Owner authorization for new API keys, paid services and new sensitive-data recipients only (ADR-013), with ADR-012 spending caps and ADR-005 data-time provenance. No market-data/connector platform in M0.

22. **ADR-016: verified automatic data-source failover.** Data Manager may replace failed primary data with a vetted, compatible, fresh backup without Owner input. Validate symbol, market, timestamps, point-in-time availability, price adjustments, data quality and license; audit effective source versions and avoid flip-flops. If all sources fail or materially conflict, stop new risk only for affected dependencies, not unrelated instruments. ADR-003's uncertain broker order still freezes the whole relevant account. Never choose favorable data, invent prices, bypass consent or load unapproved adapters. M0 requires no real providers.

23. **ADR-017: single authoritative execution instance and crash-safe recovery.** At most one trusted writer per broker account may submit real orders. Use same-host exclusion and an explicit authority handoff for host migration; a local lock never proves cross-machine exclusivity. Persist order intents/unknown outcomes, broker IDs, ledger, risk breakers and Owner veto state, with consistent snapshots/backups. On restart reconcile with authoritative broker orders/fills/positions/cash before authorizing new risk; ADR-003/004 apply. Never blindly resend or replay old signals, auto-liquidate unknown holdings, or clear loss breakers. Do not implement standby cluster/failover coordination in M0.

24. **ADR-018: account-equity financial breakers.** Compute daily loss and high-water-mark drawdown from trusted whole-account cash-flow-adjusted NAV, including realized **and unrealized** P&L, fees and relevant account assets/liabilities. Never count deposits as profit or withdrawals as losses; keep valuation provenance and persistent breaker/baseline state. Material missing/contradictory portfolio marks or mismatched holdings prevent authorizing new account risk; do not bypass a global equity check via a local data-fault exception. Broker/order uncertainty remains governed by ADR-003. Loss/drawdown breakers bar new account risk, are not guaranteed loss limits and cannot be automatically cleared at midnight, quote recovery or ADR-004 technical recovery. Owner percentages are still undecided; test a narrow paper NAV/flow/restart path in M0.

25. **ADR-019: account and strategy dual risk gating.** Require every proposal to pass both account-wide and strategy-specific exposure/loss controls (including open-order reservations). A strategy loss lock prevents *that strategy's* new risk; account loss/drawdown/broker-uncertainty locks prevent *all* new risk. A shared cash/position ledger cannot be duplicated in allocations. Attribute strategy trades, internal capital shifts, costs and realized/unrealized P&L consistently; preserve strategy identity/lineage and lock state so renaming or cloning cannot reset loss. Agent cannot raise budgets or remove locks. No unapproved threshold values or automatic financial-lock recovery; defer sophisticated multi-strategy accounting to later phases, keeping M0 a focused paper slice.

26. **ADR-020:** New changed parameter/code artifacts require fresh independent requalification before automatic admission; prior version loss locks and Owner veto remain effective.
27. **ADR-021:** Groups may share instruments but not group-private signals, research, runtime state or virtual P&L. Keep explicit group attribution while enforcing one real cash/position/order ledger and account risk across groups. Do not fabricate internal executions; defer multi-group allocation to later phases.

28. **ADR-022: trusted cross-group net-order aggregation.** Each strategy group independently emits attributable intentions; a trusted Portfolio Allocator may net compatible opposing intents before a single mandatory Risk Kernel/Execution route. An auditable internal virtual position transfer is not a broker fill or new capital. Verify actual eligible ownership/sellable quantity, settlement/T+1, pending orders, strategy/account locks, and consistent per-group P&L; never fabricate cash, trades or internal profits. External balances change only on confirmed real fills. Internal matching price, window and partial-fill attribution are not yet decided. No multi-group netting engine in M0.

29. **ADR-023: one trusted reference price for virtual group transfers.** For an eligible internal reallocation, both sides share one validated, fresh market-reference price and timestamp from trusted Data Manager. This is a virtual attribution event, never a real broker trade, taxable sale, actual commission or newly created account P&L. Group-level virtual P&L reclassification may occur but must reconcile to one physical account NAV/cash/holdings. Reject stale/conflicted quotes, ineligible holdings or attempts to bypass trade restrictions. Reference quote field and partial-fill allocation details remain unchosen. No internal transfer engine in M0.

30. **ADR-024: deterministic pro-rata external partial fills.** Assign actual broker-confirmed partial fills across same-priority eligible group intents proportionally to their precommitted quantities, with trusted risk-reducing priority allowed only after independent verification. Allocate integer units and rounding residue deterministically and idempotently, never above a group's request or beyond real fills. Distribute only actual broker fees, reconcile prices/charges/group quantity to authoritative account totals, and prevent double allocation across duplicate fill events, cancellation and restart. This is distinct from virtual internal group reallocations (ADR-023). Do not implement multi-group fill allocation in M0.

## Financial-Risk-Driven Engineering

Classify work before changing code:

- **P0:** plausible real-money loss, duplicate/incorrect order, incorrect cash or position accounting, invalid risk permission, execution/auth secret compromise, false backtests that could drive real trades. Design carefully; test realistic faults.
- **P1:** material trading/data correctness or operational continuity issues without immediate monetary consequence. Test main and credible failure paths.
- **P2:** naming, formatting, display, noncritical metadata. Simple defaults and a small number of tests, if any.
- **P3:** contrived, low-impact edge cases. Defer and move on.

Do not endlessly test model-generated names, odd Unicode variants, hypothetical compatibility matrices, or presentation details unless they cross a real security/financial boundary (e.g. command injection, filesystem access or trusted order fields). For such boundary crossings, upgrade priority immediately.

Do not add abstractions, frameworks, background services or comprehensive test matrices merely to be thorough. For each proposed extra safeguard: name a credible failure, its impact and smallest sufficient mitigation. **Stop when stated acceptance criteria are met and no known P0 remains.**

## Agent changes / permissions

- Treat generated research code and remote-agent messages as untrusted.
- Research may generate ideas, code and experiment artifacts, but cannot edit production risk policy, approve itself for live trading or directly access brokerage APIs.
- Only the independent evaluator reports pass/fail against immutable test definitions.
- ADR-014 selects independent local/remote strategy Workers; the concrete artifact/dependency packaging remains open. WASM is optional, not mandatory. A child process is **not** an adequate sandbox without enforceable OS resource, filesystem, environment and network restrictions.
- Do not introduce live order functions or unlock live mode unless a separate, explicit milestone authorizes it.
- Do not auto-merge PRs or self-approve changes involving real trading permissions.

## Workflow

1. Read `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/RISK_POLICY.md`, `docs/M0.md` before coding.
2. During design work use `grill-with-docs`: challenge assumptions and document settled terminology/decisions only when necessary.
3. Explain risk classification and scope before a material code change.
4. Implement the smallest coherent vertical slice.
5. Test P0 scenarios first, smoke-test other functionality. Be honest about missing toolchains or tests not executed.
6. Report what changed, what was verified, open financial risks and the next bounded step. Avoid lengthy speculative next-task lists.

## M0 stop rule

No UI, no live broker, no orchestration complexity, no multi-agent framework, no paid CI, no order placement. Establish naming/contracts, cross-platform workspace, and a minimal safety-oriented simulation foundation only after architecture questions are resolved.

## Documentation and communication language

- **Use Simplified Chinese as the default language** for communication with the owner, explanations, issue/PR summaries, decision discussions, and newly authored owner-facing documentation.
- Keep `README.md` in Simplified Chinese and `README.en.md` in English. If core product information changes, maintain both consistently with reciprocal language links.
- Leave Rust/Python identifiers, public API fields, file paths and technical terms in conventional English when appropriate; don't translate symbols just to satisfy the language preference.
- Existing English architecture documents may be updated incrementally; do not undertake a full translation project unless requested. Prioritize correctness and financial risk over translation polish.
