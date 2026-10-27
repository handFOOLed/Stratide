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
- Production artifact format (WASM or another isolated runtime) is an **open design decision**, not a mandate.
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
