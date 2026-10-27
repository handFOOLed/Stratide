# Architecture — draft for interrogation

**Status: DRAFT.** This is the opening hypothesis for `grill-with-docs`; do not treat design options as settled ADRs.

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

## Likely implementation boundaries

- **Production core:** lightweight Rust daemon, no GPU; data, risk, ledger, order state, broker abstraction.
- **Research:** external model providers and isolated compute workers; no account credentials.
- **Persistence:** SQLite for authoritative trading/operational state; Parquet possibly for research datasets. Need transaction/backup design.
- **Strategy runtime:** prefer a bounded portable artifact (e.g. WASM) *if practical*. Must test compilation, mathematical parity, resource limits and portability. Do not freeze until evaluated.
- **User interface:** CLI initially; authenticated Control API loopback-only; future standalone Web Dashboard for a private site.
- **Deployment:** first Windows; perhaps Linux mini PC later. No dependence on Docker, Redis, Kafka, or Kubernetes in core.

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

- What is the least-complex acceptable **strategy artifact/runtime**, especially for unusual ML/AI strategies?
- What is the minimum broker interface needed for authentic paper fills and later live A-share compliance?
- How do we define and verify account-equity daily-loss and high-water-mark drawdown thresholds?
- Is the independent risk authority a crate, a process, or an OS-isolated service, given low footprint?
- Which parts of research can run with bounded CPU locally vs remote-only workers?
- What constitutes strategy promotion and when is human authorization mandatory?
- Which data can be stored/shipped to external providers under licenses and privacy expectations?
- What is the resource budget and minimum uptime/recovery test for a mini PC deployment?

See `docs/GRILL_BRIEF.md` for a discussion-ready agenda.
