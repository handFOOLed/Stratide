# Product Definition — current agreements

Status: **agreed product principles**, not a profitability claim.

## Mission

Stratide autonomously discovers, evaluates, manages and eventually executes trading strategies under independently enforced financial risk constraints. It must be able to conclude there is no credible edge and refrain from opening new risk.

## Owner priorities

- Target **around CNY 100,000** of possible future capital, not immediate commitment.
- Optimize for **net** results after market friction, data/AI/compute/subscription costs and risks.
- **ADR-012:** allow the Agent to choose and allocate research/experiment spending flexibly **within an Owner-defined daily hard cap** enforced outside the Agent. Exhaustion halts new paid research, not existing portfolio risk/order management. Research budget is distinct from account principal and operating-critical service costs.
- Prefer accessible and reliable low-cost data; asset universe should follow data economics and executable brokerage access, not an arbitrary product checklist.
- Stock prices are hard to predict; AI's job is hypothesis and research support, not unquestioned price prophecy.
- Agent may freely explore novel research directions and generated code; production strategy promotion is gated. **ADR-005:** incomplete historical datasets are acceptable for labeled exploratory research, but promotion evidence must be independently verified for point-in-time availability or accumulated in forward-observed paper/shadow evaluation.
- Keep independent risk kernel, loss-triggered entry shutdown, account/position reconciliation, bounded exposure, no uncontrolled leverage.
- **ADR-009/ADR-011:** future autonomous promotion is immediate by default inside Owner-enabled live capital and risk limits; optional configurable 10-minute grace period, not default. Sleeping or not receiving routine notifications does not block authorized promotion; daily summaries minimize review work. Owner veto remains effective. Risk controls mitigate exposure but cannot guarantee capped losses.
- **ADR-008:** dynamic portfolio allocation uses one shared account cash ledger. Agent research/backtest/forward-paper starting capital may never exceed the explicit Owner-authorized account principal; no fictitious deposits, duplicated funds across concurrent strategies or default leverage. The illustrative CNY 100,000 account is not an automatic authorization.
- **ADR-006:** autonomous research cannot turn repeated holdout peeking into false trading advantage; freeze candidate versions, keep independent evaluator authority, record all evaluations and require genuine forward evidence before live eligibility.
- Develop and paper trade on user's Windows PC first. A persistent **macOS ARM64 Mac mini or Linux mini PC** and private web dashboard are **conditional** on sustained evidence of value; broker integration may be OS-specific.
- Local footprint should be tiny: no GPU and no local model inference; LLM via cloud API, remote compute when justified. **Hybrid strategy decisions** are accepted: light strategies may run locally, complex ones remotely, but all proposals must pass local risk and order controls ([ADR-001](adr/0001-hybrid-strategy-execution.md)).
- No conventional stock-terminal GUI required. A CLI plus reports is sufficient for now.
- Prioritize credible financial failure over cosmetic edge cases and speculative enterprise hardening.

## Explicit non-goals now

- Guaranteed positive returns or fixed maximum loss.
- High-frequency trading / latency racing.
- Automated live account access at M0.
- Full multi-agent teams or heavy distributed infrastructure.
- Publicly accessible order-management endpoints.
- A polished frontend as the prerequisite for useful product behavior.
