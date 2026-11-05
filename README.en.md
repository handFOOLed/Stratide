[简体中文](README.md) | **English**

# Stratide

> **Current status (2026-11-05):** V2/M3 engineering modules **A/B/C are merged to `main`**: [#82 / PR #86](https://github.com/handFOOLed/Stratide/pull/86) market-wide EOD ingestion, [#83 / PR #87](https://github.com/handFOOLed/Stratide/pull/87) controlled TimesFM and DeepSeek automated research, and [#84 / PR #88](https://github.com/handFOOLed/Stratide/pull/88) one shared multi-security Paper ledger with ex-post T+1 assumptions. **The sole current task is [#85](https://github.com/handFOOLed/Stratide/issues/85): a real Windows 11 installer, optional user-logon background startup, a single-instance desktop launcher and automatic Dashboard opening. The Owner assigned the complete #85 delivery to DeepSeek; it is not yet built or merged.** See [current status](docs/STATUS.md) and [V2 roadmap #81](https://github.com/handFOOLed/Stratide/issues/81).

> **Critical limits:** Paper-only, no broker or real-money orders. Ex-post opening assumptions are not observed opening fills, PIT verification or evidence of an edge. Unverified corporate-action simulation requires separate Owner authorization and independent conservative caps. Real full-market production E2E and Windows distribution are not verified; research requires 84 READY sessions. Real-market egress to DeepSeek is DENIED by default, with one Agent budget of CNY ¥5/day and ¥100/month. N100 deployment is deferred.



A local-first, **paper-only** personal quantitative research system: Rust risk/ledger and replay, genuine EOD observation, a local read-only Paper Dashboard and controlled research Agent. **Not authorized for real-money trading; no proven trading edge.**

## Archived module-by-module status (Draft/current meant at that time)

- **M2-PR20 local risk from real history (#74 / this branch, Draft):** existing V1/V2 data and quality tags → prefix freeze → TimesFM CPU → original tasks/Registry/report/verify have passed a real three-security run. Factor changes and gaps reject; no new market requests, cloud calls or billing. Real risk results cannot leave the host. Historical PIT, out-of-sample advantage, Paper/Live eligibility and physical N100 acceptance remain unverified. See [operation](docs/M2_PR20.md) and [evidence](docs/evidence/m2-pr20/README.md).

- **M2-PR19 real Fusion (#71 / PR #72 merged):** real local TimesFM → real `deepseek-flash` → strict portfolio validation → original Registry/Inbox/report/verify passed. The Owner-authorized additional call returned 1065/722 tokens and a valid 100% cash research portfolio. Both authorized calls total a conservative ¥0.015420 estimate; the first failure and all reservations remain. One real Agent shares ¥5/day and ¥100/month (Asia/Shanghai). Fusion is OFF; Paper/Live remain blocked. See [operation/status](docs/M2_PR19.md) and [real evidence](docs/evidence/m2-pr19/README.md).

- **M2-PR18 local TimesFM CPU (#69 / PR #70 merged / OFF by default):** pinned official TimesFM 2.5 200M weights and CPU dependencies, with an on-demand Python Worker producing the original risk result and Naive/EWMA comparison. WSL2 Linux isolation passed 4/4, with a real CPU production cycle and 16 stress points completed. Production target: N100 Linux; N100 acceptance remains `NOT_VERIFIED`. Existing cloud paths and Paper/Live permissions are unchanged. See [operation and isolation](docs/M2_PR18.md) and [Linux evidence and regression limits](docs/evidence/m2-pr18/linux-r1/README.md).

- **M2-PR17 DeepSeek HTTPS (#67 / OFF by default):** the wire model is fixed to `deepseek-flash`; this module defaults to the internal ID `ds4.1flash`. It reuses the original Agent/CNY Budget and PR15 AST/PR62 offline evaluator. Developer validation uses recorded/loopback; the real result is `REAL_PROVIDER_NOT_RUN_OWNER_AUTHORIZATION_MISSING`. Paper/Live remain BLOCKED. See [operation and boundaries](docs/M2_PR17.md) and [test evidence](docs/evidence/m2-pr17/README.md).

First use by the Owner: manually set daily/monthly hard caps in the existing real CNY Agent settings. Copy the [empty configuration](research/agent/deepseek-owner-config.example.json) to an ignored local directory and explicitly fill the per-call cap, DeepSeek recipient, synthetic-only data approval, credential source and reviewed price expiry. Keep the existing currency identity. Run `scripts/autonomous-research.py configure`, `init --source authorized_cloud`, then read-only `preflight` and inspect the fields, request SHA and maximum reservation. Use `enable --opt-in APPROVE_ONE_SYNTHETIC_DEEPSEEK_REQUEST` followed by `once` for at most one real request. `disable` stops future dispatch; `status/history/report/verify` are read-only. Unknown charges retain the original reservation until Owner invoice reconciliation. [Copyable commands](docs/M2_PR17.md#owner-操作). This describes the original PR17 delivery; the new PR19 authorization and single real Fusion smoke are recorded above.

- **Historical Sidecar V2 (Draft / #59):** [M2-PR13](docs/M2_PR13.md) adds four-API, five-year collection using the existing 2000-point Tushare account: 1212 published dates per API and 6068 requests, with durable bounded resume, versioned queries and frozen-anchor adjustment. [Actual evidence](docs/evidence/m2-pr13/README.md); local-only data, ex-post / PARTIAL coverage, no PIT or trading qualification.
- **Historical Warehouse V1 (PR #58 merged):** [M2-PR12](docs/M2_PR12.md) adds an isolated SQLite catalog, calendar and unadjusted daily-bar warehouse with preflight, trial sampling, bounded backfill, resume and read-only queries. See [actual coverage evidence](docs/evidence/m2-pr12/README.md). `historical_backfill_ex_post / PIT NOT_VERIFIED`; no forward or trading qualification.
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
- **Current order:** #74 delivers the real-history → local TimesFM core loop in one Draft PR pending fixed-HEAD review. A separate frozen out-of-sample protocol and genuine forward EOD follow; UI integration follows the core. See [current status](docs/STATUS.md).
- **PR #56 review repair:** cloud research requires an explicit binding to the existing Owner AgentDir/configuration and shares its cost database. Source review confirmed the budget repair. All three original PR52/54 suites passed after close: **10+4+13 tests, each suite exit 0**. PR #56 is now merged; the original developer evidence is preserved. See [R1 evidence](docs/evidence/m2-pr11/r1/README.md).

## Legacy development-mode dashboard run (not the #85 installer)

From the repository root, using a **synthetic test report**:

```powershell
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report'

# Local fake Agent only; synthetic TST fees.
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report' -AgentDir state/agent-fake -FakeAgent
```

Open `http://127.0.0.1:8710`; stop with Ctrl+C. For your own published report and other commands, see [Dashboard instructions](apps/dashboard/README.md) and [engineering roadmap](docs/PAPER_TRADING_ROADMAP.md).

## Roles and documentation

**Owner:** scope, data egress/paid permission and final merge authority · **DeepSeek:** complete active #85 Windows installer, background service, launcher, first-run setup and necessary Rust/Python/PowerShell/UI integration · **ChatGPT:** fixed-HEAD review and Owner-authorized merge. Past Sol/DS UI-only assignments are archived; see [AGENTS.md](AGENTS.md).

[DeepSeek UI handoff](docs/UI_HANDOFF_DEEPSEEK.md) · [Coding guidance](AGENTS.md) · [Product principles](docs/PRODUCT.md) · [Financial risk policy](docs/RISK_POLICY.md) · [Accepted ADRs](docs/adr/).

**Historical replay is not genuine forward validation. No live brokerage integration.**
