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
- Financial-risk-driven testing; do not spend days on harmless malformed names.

## Decision tree — highest-value unresolved choices

1. **Implementation of ADR-001 (still open)**: local strategy artifact/runtime choices (WASM, declarative, restricted child process) and minimal unified proposal contract; remote compute is allowed but must not bypass local risk.
2. **Risk gateway implementation (ADR-002)**: how do private APIs and persisted breaker state prevent unchecked order emission; what minimal operator-unlock rule is needed?
3. **Executable order semantics**: if a broker times out after accepting an order, which identifiers and persisted states prevent duplicate execution?
4. **Market-data semantics**: can a daily strategy prove `available_at <= decision_time` for all inputs, and support price adjustments/corporate actions?
5. **Backtesting promotion**: how to avoid evaluating thousands of models on recycled held-out data and overfitting selection to chance?
6. **Paper fidelity**: how are A-share T+1, daily price limits, unavailable fills, lot size, fees, and liquidity handled? What cannot be simulated reliably?
7. **Live automation authority**: what is the smallest default manual-approval boundary before any novel promoted strategy can route a real order? Regulatory reporting must be checked.
8. **Local-to-miniPC migration**: what state must be backed up, recovered, and reconciled so identical logic can resume safely on macOS ARM64 or Linux (given broker OS constraints)?
9. **External data and cloud privacy**: who may receive raw datasets, account/portfolio metadata and research logs? What licensing or confidentiality applies?
10. **Cost control**: what daily/monthly budgets and stop conditions keep remote research cheaper than plausible incremental edge?

## Output expectations

- Decisions vs assumptions vs unresolved questions kept separate.
- A short glossary of terms only after settling definitions.
- ADRs only for costly-to-reverse real tradeoffs.
- Update `docs/ARCHITECTURE.md` as choices are made; avoid inventing full implementation.
- First implementation recommendation must be a narrow, testable M0 slice with explicit non-goals.
