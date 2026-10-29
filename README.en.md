[简体中文](README.md) | **English**

# Stratide

A local-first, **paper-only** personal quantitative research system: Rust risk/ledger and replay, genuine EOD observation, a local read-only Paper Dashboard and controlled research Agent. **Not authorized for real-money trading; no proven trading edge.**

## Status

- **Implemented:** paper Risk Kernel, durable ledger and reports, exploratory historical EOD replay, observe-only forward EOD journal, and [Web Dashboard V1](apps/dashboard/README.md).
- **Agent V1 is in main:** persistent tasks, daily/monthly spending gates, controlled Providers, a local fake, EOD deduplication and [APIs](docs/AGENT_API.md). **REAL_PROVIDER_NOT_VERIFIED**; no paid requests without Owner budgets/consent.
- **Draft on this branch:** [M2-PR04](docs/M2_PR04.md) adds candidate registration → freeze → independent evaluation → isolated historical replay through a CLI. Engineering self-tests pass; research evidence remains insufficient and eligibility is denied. Fixed-HEAD review and targeted independent challenges remain pending.
- **Limits:** 68 historical sessions / 3 simulated fills; longer history `DATA_BLOCKED` by corporate-action and fee evidence. Only one valid forward observation day; **no continuous forward-paper fills or account NAV**.
- **Current order:** [#29 core implementation](https://github.com/handFOOLed/Stratide/issues/29) follows **Core-first, UI-later**. Sol will integrate all UI using the merged PR #28 visual baseline after the core features are complete. See [current status and evidence](docs/STATUS.md).

## Try the dashboard on Windows

From the repository root, using a **synthetic test report**:

```powershell
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report'

# Local fake Agent only; synthetic TST fees.
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report' -AgentDir state/agent-fake -FakeAgent
```

Open `http://127.0.0.1:8710`; stop with Ctrl+C. For your own published report and other commands, see [Dashboard instructions](apps/dashboard/README.md) and [engineering roadmap](docs/PAPER_TRADING_ROADMAP.md).

## Roles and documentation

**Owner:** scope/merge authority · **Sol:** backend, Agent, API and critical tests · **DeepSeek:** information architecture, typography, shared UI components, responsive layout and motion · **ChatGPT:** same-HEAD review and Owner-authorized merge.

[DeepSeek UI handoff](docs/UI_HANDOFF_DEEPSEEK.md) · [Coding guidance](AGENTS.md) · [Product principles](docs/PRODUCT.md) · [Financial risk policy](docs/RISK_POLICY.md) · [Accepted ADRs](docs/adr/).

**Historical replay is not genuine forward validation. No live brokerage integration.**
