[简体中文](README.md) | **English**

# Stratide

A local-first, **paper-only** personal quantitative research system: Rust risk/ledger and replay, genuine EOD observation, a local read-only Paper Dashboard and controlled research Agent. **Not authorized for real-money trading; no proven trading edge.**

## Status

- **Implemented:** paper Risk Kernel, durable ledger and reports, exploratory historical EOD replay, observe-only forward EOD journal, and [Web Dashboard V1](apps/dashboard/README.md).
- **Draft on this branch:** [Agent V1](docs/M2_PR02.md) adds persistent tasks, daily/monthly spending gates, controlled HTTPS generation, a local fake Provider, EOD deduplication and basic Web controls. [API](docs/AGENT_API.md) and [self-test evidence](docs/evidence/m2-pr02/README.md) are available. **REAL_PROVIDER_NOT_VERIFIED**; no paid requests without Owner budgets/consent. Targeted independent risk checks and fixed-HEAD review remain pending.
- **Limits:** 68 historical sessions / 3 simulated fills; longer history `DATA_BLOCKED` by corporate-action and fee evidence. Only one valid forward observation day; **no continuous forward-paper fills or account NAV**.
- **Next:** [#22 Agent implementation and APIs (Sol)](https://github.com/handFOOLed/Stratide/issues/22) → [#23 complete UI/UX redesign (DeepSeek)](https://github.com/handFOOLed/Stratide/issues/23). See [current status and evidence](docs/STATUS.md).

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
