[简体中文](README.md) | **English**

# Stratide

A local-first, **paper-only** personal quantitative research system: Rust risk/ledger and replay, genuine EOD observation, a local read-only Paper Dashboard and controlled research Agent. **Not authorized for real-money trading; no proven trading edge.**

## Status

- **Implemented:** paper Risk Kernel, durable ledger and reports, exploratory historical EOD replay, observe-only forward EOD journal, and [Web Dashboard V1](apps/dashboard/README.md).
- **Agent V1 is in main:** persistent tasks, daily/monthly spending gates, controlled Providers, a local fake, EOD deduplication and [APIs](docs/AGENT_API.md). **REAL_PROVIDER_NOT_VERIFIED**; no paid requests without Owner budgets/consent.
- **Candidate pipeline merged:** [M2-PR04 / PR #30](docs/M2_PR04.md) provides registration → freeze → independent evaluation → isolated historical replay. Both #31 independent tracks passed; research evidence remains insufficient and eligibility is denied.
- **EOD snapshots merged:** [M2-PR05 / PR #33](docs/M2_PR05.md) provides offline read-only verification, durable research snapshots, status and consumer CLI.
- **Fake Agent pipeline merged:** [M2-PR06 / PR #35](docs/M2_PR06.md) connects explicitly selected snapshots → persistent local Fake Agent tasks → candidate research provenance. The original manual snapshot path does not schedule automatically; cloud sending and trading eligibility remain denied.
- **EOD Auto / review / Shadow merged:** [PR #44](docs/M2_PR07.md), [PR #46](docs/M2_PR08.md) and [PR #48](docs/M1_PR10.md) provide local Fake research, manual template review and fixed SMA5/20 observe-only journals.
- **EOD Operator merged (PR #50):** [EOD Operator V1](docs/M2_PR09.md) connects the original collector → Snapshot → Shadow / optional Fake after one configuration and enable. Foreground watch checks from 15:15, retaining the original 16:00 collection gate. Native Windows credential storage, durable disable, authoritative recovery and read-only reports; OFF by default.
- **Corporate-action evidence merged (PR #38):** [Evidence Bundle V1](docs/M1_PR07B.md) preserves `FACTS_PARTIAL / historical_pit=NOT_VERIFIED`; no real historical admission.
- **Cash-dividend model merged (PR #40):** [CASH_DIVIDEND_V1](docs/M1_PR08.md) completes isolated entitlement → receivable/tax → settlement, shared NAV/Risk, seven reports and independent algorithmic accounting checks. The synthetic CLI, v3 and the original 68-session history remain compatible.
- **Historical dividend bridge merged (PR #42):** [Historical dividend bridge V1](docs/M1_PR09.md) connects frozen market inputs, PR38 evidence and explicit assumptions to v4, the original SMA5/20, seven reports, independent arithmetic and two ledger benchmarks. The actual 77-session run is **EXPLORATORY_EX_POST**; **0** new real PIT days, real admission remains denied.
- **Limits:** 68 historical sessions / 3 simulated fills; longer history `DATA_BLOCKED` by corporate-action and fee evidence. Two genuine EOD days are `EOD_CONTINUITY_VERIFIED`; opening-source evidence remains BLOCKED. **No continuous forward-paper fills or account NAV.**
- **Current order:** this branch implements [#51 Time-Series + Fusion V1](docs/M2_PR10.md): independent local numerical experts → the original Rust Agent/Budget Fusion fake → the original Candidate Inbox. OFF by default and research only; real models, data sharing and trading are not authorized. The full [#36 multi-modal research](https://github.com/handFOOLed/Stratide/issues/36) experiments await suitable data and model authorization. Sol will integrate all UI using the merged PR #28 visual baseline after the core features are complete. See [current status and evidence](docs/STATUS.md).

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
