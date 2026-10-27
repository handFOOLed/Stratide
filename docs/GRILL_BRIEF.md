# Grill-with-docs — Stratide architecture interrogation

## Brief for Codex

Use the `grill-with-docs` skill against this repository. Read `README.md`, `AGENTS.md`, `docs/PRODUCT.md`, `docs/ARCHITECTURE.md`, `docs/RISK_POLICY.md`, and `docs/M0.md` first. Challenge meaningful ambiguities with **one tightly scoped question at a time**, concrete scenarios, recommended answer with rationale, and alternatives. Do not ask the owner to re-answer settled product preferences. Record decisions as a concise glossary entry or ADR only when they actually crystallize; avoid boilerplate documentation.

Use this opening frame:

> We are designing a low-resource local-first trading engine paired with cloud-only autonomous research. Explore trading strategies without preset strategy-family restrictions; never allow research/AI to bypass financial risk controls. The owner wants practical, risk-proportional engineering, not exhaustive hypothetical edge-case testing. Challenge the riskiest assumptions before writing implementation code.

## Already decided (do not re-litigate)

- Open-ended autonomous strategy research (including generated strategy code).
- Cloud-only LLM inference, no production GPU requirement.
- Paper testing and local Windows before any live money.
- Independent risk authority and loss circuit breakers.
- Low operating cost, low local resource requirements.
- Future macOS ARM64 Mac mini or Linux mini PC and private Web Dashboard only after evidence of value.
- **ADR-001 accepted:** hybrid local/remote strategy computation with unified proposals, always locally risk-gated. Do not re-litigate hybrid vs all-local vs all-cloud.
- **ADR-002 accepted:** Risk Kernel and Execution Engine are separate modules inside one trusted Rust core process; one mandatory order gateway; untrusted strategy code stays outside it. Do not re-litigate the basic in-process vs separate-daemon choice without concrete financial risk evidence.
- **ADR-003 accepted:** uncertain broker submission freezes all new risk for the account, not only the affected ticker; preserve state, reconcile orders/fills/cash/positions and never blindly retry.
- **ADR-004 accepted:** recovery of technical-only broker halts is configurable (`conditional_auto` default / `manual`), but always needs full reconciliation and stable connection; repeated faults require Owner intervention. Loss/drawdown breakers never auto-clear as a side effect.
- **ADR-005 accepted:** incomplete/low-cost historical data may be used for exploratory research, but promotion-grade historical backtests need independently verified point-in-time inputs; forward-observed shadow trading can build new evidence when historical availability is unprovable. Do not equate shadow testing with live deployment.
- **ADR-006 accepted:** Agent freely explores, but cannot inspect/alter protected evaluation rules or repeatedly use the same holdout as an unlimited tuning oracle. Freeze and hash candidates, track attempts and research lineage, use genuine forward observation before live eligibility. Do not mandate complex statistics or arbitrary test-count limits at M0.
- **ADR-007 accepted:** initial paper/backtesting fills use conservative daily-bar assumptions, with instrument-specific tradability, fees and timing; no assumed favorable fills from OHLC alone. Higher-fidelity market simulation only when the strategy/data actually requires it.
- **ADR-008 accepted:** portfolio allocation may change weights among eligible strategies, but every formal backtest/forward-paper run must start with at most the Owner-authorized account principal. Combined multi-strategy paper execution must share one cash ledger and cannot double-count capital; default no borrowing or leverage. Allocation does not authorize live promotion.
- Financial-risk-driven testing; do not spend days on harmless malformed names.

## Decision tree — highest-value unresolved choices

1. **Implementation of ADR-001 (still open)**: local strategy artifact/runtime choices (WASM, declarative, restricted child process) and minimal unified proposal contract; remote compute is allowed but must not bypass local risk.
2. **Risk gateway implementation (ADR-002)**: how do private APIs and persisted breaker state prevent unchecked order emission; what minimal operator-unlock rule is needed?
3. **ADR-003/004 implementation (open):** minimal order identifiers, broker reconciliation and bounded query behavior; exact stability/repeated-fault policy should be tuned for the actual adapter, not speculated about now.
4. **ADR-005 implementation (open):** minimal point-in-time evidence metadata, forward-observation journaling and corporate-action handling; no exhaustive data-quality engineering at M0.
5. **ADR-006 implementation (open):** choose minimal candidate freeze, evaluator feedback, held-out data isolation and eventually appropriate thresholds; core principle is settled.
6. **ADR-007 implementation (open):** when instruments/data are chosen, define a minimal conservative daily-bar fill model, fee schedule and supported tradability rules; avoid inventing a tick-level simulator.
7. **Live automation authority (open; next):** may a newly validated frozen strategy automatically become eligible to trade real funds within preauthorized capital/risk limits, or must the Owner explicitly approve each new strategy? Regulatory reporting must be checked when real brokerage is chosen.
8. **Local-to-miniPC migration**: what state must be backed up, recovered, and reconciled so identical logic can resume safely on macOS ARM64 or Linux (given broker OS constraints)?
9. **External data and cloud privacy**: who may receive raw datasets, account/portfolio metadata and research logs? What licensing or confidentiality applies?
10. **Cost control**: what daily/monthly budgets and stop conditions keep remote research cheaper than plausible incremental edge?

## Output expectations

- Decisions vs assumptions vs unresolved questions kept separate.
- A short glossary of terms only after settling definitions.
- ADRs only for costly-to-reverse real tradeoffs.
- Update `docs/ARCHITECTURE.md` as choices are made; avoid inventing full implementation.
- First implementation recommendation must be a narrow, testable M0 slice with explicit non-goals.
