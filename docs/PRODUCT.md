# Product Definition — current agreements

Status: **agreed product principles**, not a profitability claim.

## Mission

Stratide autonomously discovers, evaluates, manages and eventually executes trading strategies under independently enforced financial risk constraints. It must be able to conclude there is no credible edge and refrain from opening new risk.

## Owner priorities

- Target **around CNY 100,000** of possible future capital, not immediate commitment.
- Optimize for **net** results after market friction, data/AI/compute/subscription costs and risks.
- **ADR-012:** allow the Agent to choose and allocate research/experiment spending flexibly **within an Owner-defined daily hard cap** enforced outside the Agent. Exhaustion halts new paid research, not existing portfolio risk/order management. Research budget is distinct from account principal and operating-critical service costs.
- Prefer accessible and reliable low-cost data; asset universe should follow data economics and executable brokerage access, not an arbitrary product checklist.
- **ADR-015 and ADR-016:** research Agent auto-discovers potential sources; the trusted Data Manager supplies governed data to production Workers, and automatically fails over to an approved, compatible fresh backup. Material conflicts or all sources unavailable stop affected new-risk decisions. New paid services, credentials or sensitive data sharing still require initial Owner authorization; routine reads or switching between approved sources do not.
- Stock prices are hard to predict; AI's job is hypothesis and research support, not unquestioned price prophecy.
- **ADR-013:** the Owner can give a single revocable, persisted authorization for cloud analysis of rich portfolio/trade/account research context. Avoid repeat permission prompts inside an authorized scope; never transmit brokerage secrets or grant the research Agent order/risk authority.
- Agent may freely explore novel research directions and generated code; production strategy promotion is gated. **ADR-005:** incomplete historical datasets are acceptable for labeled exploratory research, but promotion evidence must be independently verified for point-in-time availability or accumulated in forward-observed paper/shadow evaluation.
- Keep independent risk kernel, loss-triggered entry shutdown, account/position reconciliation, bounded exposure, no uncontrolled leverage.
- **ADR-018:** daily-loss and drawdown locks rely on trustworthy whole-account cash-flow-adjusted equity including unrealized P&L, not just closed trades. Deposits and withdrawals are not strategy P&L; untrustworthy total NAV fails closed for new account risk. Financial-loss locks persist until separately authorized release; threshold amounts are still undecided.
- **ADR-019:** enforce account-level AND per-strategy risk budgets/halts; losses and group attribution persist without duplicate cash.
- **ADR-020:** new immutable parameter/code versions can auto-promote only after independent requalification, within Owner risk and veto scope.
- **ADR-021/ADR-022/ADR-023/ADR-024:** independent strategy groups may hold the same stock; Portfolio Allocator nets opposing intents and values permitted internal virtual transfers at one trusted reference price. Confirmed *external partial fills* are attributed proportionally among equal-priority eligible groups, with deterministic integer remainder and actual fee allocation. Private research/signals remain isolated; one physical account ledger, no fictitious fills, cash or NAV gains.
- **ADR-009/ADR-011:** future autonomous promotion is immediate by default inside Owner-enabled live capital and risk limits; optional configurable 10-minute grace period, not default. Sleeping or not receiving routine notifications does not block authorized promotion; daily summaries minimize review work. Owner veto remains effective. Risk controls mitigate exposure but cannot guarantee capped losses.
- **ADR-008:** dynamic portfolio allocation uses one shared account cash ledger. Agent research/backtest/forward-paper starting capital may never exceed the explicit Owner-authorized account principal; no fictitious deposits, duplicated funds across concurrent strategies or default leverage. The illustrative CNY 100,000 account is not an automatic authorization.
- **ADR-025:** allow trusted bidirectional adjustment of qualified strategies' allocated risk budgets. Gradual evidence-based increases and quicker risk-based restrictions; weak data or short losing streaks do not automatically imply alpha decay. Risk Kernel alone enforces Owner limits, break conditions and account-wide total exposure. Design deterministic audited calculations, replay/stress/fault tests and paper/shadow gating before separately authorized live dynamic sizing; M0 does not implement this.
- **ADR-026:** keep only a bounded number of paused strategies in shadow observation, archive others with explicit data gaps and preserve required evidence. Use local indexed strategy metadata and tightly bounded, authorized summaries to avoid sending every past strategy to cloud LLMs. Resource limits must not endanger actual account ledger and risk persistence.
- **ADR-027:** historical research failure is an input to future hypothesis formation and efficient duplicate checks, not an automatic permanent research ban. Similar candidates may be explored on materially new, testable evidence while all independent validation, Owner veto and financial lock rules continue to apply.
- **ADR-028:** first live brokerage account is dedicated to Stratide and not used for routine manual trades. The account remains subject to authoritative broker reconciliation; unexplained external orders, fills, cash or positions stop new account risk until reconciled. Availability of a suitable distinct account and adapter must be verified before real trading.
- **Dedicated-account scope clarification (Q34):** the Owner will not normally buy securities manually in the Stratide account. Do **not** build a standing Owner Manual investing sleeve or routine hybrid-manual portfolio. ADR-029/032/033 remain exceptional takeover and reconciliation safeguards, not an ongoing manual-position feature.
- **ADR-029:** Owner emergency manual takeover persists as an exclusive automation lock: no new robot broker submissions while active, including automated risk reduction. Returning execution authority requires an explicit authenticated Owner action, complete reconciliation, valid live authorization and no other risk locks; technical automatic recovery never overrides Owner control.
- **ADR-030/ADR-031:** the manual takeover dialog offers adjacent neutral Keep and red Attempt Cancel actions, with separate opposite-side Cancel. When trusted open orders include protective/risk-reducing orders, the red action requires an additional default-unchecked acknowledgement IN the same dialog, bound to the reviewed order snapshot. No second pop-up; uncertain order classification must never silently grant cancellation. Actual broker outcome still controls order state.
- **ADR-032:** confirmed Owner-manual broker trades go to an independent suspense ledger until group attribution is resolved, not automatic proportional splitting. Real account cash, positions and fees update immediately; affected strategies cannot trade using stale group holdings. Known old automated broker fills keep their original attribution.
- **ADR-033:** final allocation of manual trade suspense to strategy groups is made explicitly by the Owner, selecting eligible groups and quantities. Trusted accounting rejects allocations exceeding real fills/group inventory, reconciles costs/fees and preserves original broker facts; no automated guessing or financial-lock resets.
- **ADR-006:** autonomous research cannot turn repeated holdout peeking into false trading advantage; freeze candidate versions, keep independent evaluator authority, record all evaluations and require genuine forward evidence before live eligibility.
- Develop and paper trade on user's Windows PC first. A persistent **macOS ARM64 Mac mini or Linux mini PC** and private web dashboard are **conditional** on sustained evidence of value; broker integration may be OS-specific.
- **ADR-017:** use one authoritative trading instance, persist order/portfolio/risk state and reconcile before live restart; do not operate two active trading cores or automatic hardware failover. Hardware downtime is accepted rather than risking duplicate orders.
- Local footprint should be tiny: no GPU and no local model inference; LLM via cloud API, remote compute when justified. **Hybrid strategy decisions** are accepted: light strategies may run locally, complex ones remotely, but all proposals must pass local risk and order controls ([ADR-001](adr/0001-hybrid-strategy-execution.md)). **ADR-014:** generated Python/ML strategies execute in independent local/remote Workers, never inside the credential-bearing Rust core; WASM is not mandatory.
- No conventional stock-terminal GUI required. A CLI plus reports is sufficient for now.
- Prioritize credible financial failure over cosmetic edge cases and speculative enterprise hardening.

## Explicit non-goals now

- Guaranteed positive returns or fixed maximum loss.
- High-frequency trading / latency racing.
- Automated live account access at M0.
- Full multi-agent teams or heavy distributed infrastructure.
- Publicly accessible order-management endpoints.
- A polished frontend as the prerequisite for useful product behavior.
