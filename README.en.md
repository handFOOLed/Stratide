[简体中文](README.md) | **English**

# Stratide

**PR04B engineering increment (Draft, unmerged):** adds daily `forward-eod-step`, optional foreground `observe-eod.ps1 -Watch`, calendar-day completeness summaries and read-only `forward-eod-at` views. It reuses the actual PR04A journal without changing the financial ledger. Evidence still covers **one valid observation day, zero proposals/fills**; consecutive real trading days and independent opening receipts remain unverified. See [PR04B operations and evidence](docs/M1_PR04B.md) and [opening-evidence research](docs/M1_PR04B_OPENING_EVIDENCE.md) (Chinese).

**PR #8 / M1-PR04A merged** ([PR](https://github.com/handFOOLed/Stratide/pull/8); merge `1ef06eb1d17f8796e3b43d2ad0a903382fa0fd23`; reviewed HEAD `295751cf15bfaa68407dd243f45394b5147e1227`). A limited Windows **observe-only** Tushare EOD workflow now writes actually received market data, raw hashes, timestamps, duplicate/backfill/gap diagnostics and CSV/JSON reports to a separate forward journal. [Terra independent acceptance](https://github.com/handFOOLed/Stratide/pull/8#issuecomment-6471878822) included **89 Windows tests** and offline checks of Sol-collected raw bytes; the reviewer did **not** independently make HTTPS calls. [ChatGPT source review](https://github.com/handFOOLed/Stratide/pull/8#pullrequestreview-5684495112) passed. There is **one valid observed forward trading day, zero proposals and zero simulated fills**; NAV/drawdown are unavailable. Provider authorization is not independently certified; the Owner accepts personal noncommercial local use. A past development tool transcript exposed a plaintext Token; this remains disclosed, and the value must not be committed or logged by the application. Multi-day forward observations and actual paper trading are **not** completed.

**Historical initial M1-PR04A submission: Draft / BLOCKED.** Initial provider permission and live-journal evidence were unavailable; the original blocked record is preserved in [M1-PR04A](docs/M1_PR04A.md) and [source feasibility notes](docs/M1_PR04A_SOURCE_FEASIBILITY.md). Subsequent Owner scope confirmation, real local collection, R2 fix, independent narrow acceptance and merge are documented above. **The complete M1 milestone is not finished.**

[ADR-035](docs/adr/0035-record-date-corporate-action-group-attribution.md): record-date dividends and bonus shares are attributed automatically to eligible groups.
[ADR-036](docs/adr/0036-owner-approval-for-voluntary-corporate-actions.md): funded rights subscriptions and voluntary issuer elections require event-specific Owner approval, never silent automatic execution.

[ADR-032](docs/adr/0032-manual-trades-suspense-ledger-unassigned-attribution.md): confirmed Owner-manual fills enter a separate suspense ledger; real broker balances update immediately. [ADR-033](docs/adr/0033-owner-explicit-manual-fill-group-attribution.md): only explicit Owner-directed group quantities can resolve suspense, subject to verified inventories, fee/cost reconciliation and unchanged broker facts.

[ADR-026](docs/adr/0026-budgeted-shadow-observation-and-local-strategy-registry.md): bounded shadow observation, locally indexed strategy lookup and limited cloud-LLM context. [ADR-027](docs/adr/0027-historical-failure-as-evidence-not-permanent-ban.md): past failures are research evidence, not permanent research bans or permission to bypass live financial locks.

**Current development priority:** deliver verifiable M0 paper trading core first, then M1 genuine forward paper observation on provenance-tagged market data with NAV/trade/fee/drawdown reports. GPT-6.1 Sol implements; GPT-6.1 Terra independently tests and publishes SHA-specific acceptance evidence; ChatGPT reviews source and evidence, then performs the SHA-guarded merge after clearance; the Owner sets scope and evaluates results. See [ADR-037](docs/adr/0037-observable-paper-trading-first-and-independent-review-gates.md) and [the paper roadmap](docs/PAPER_TRADING_ROADMAP.md). Historical replays are not live observations.

**Autonomous Quantitative Trading & Open-Ended Strategy Discovery**

Status: **M0-PR01/02/03 and M1-PR04A merged**. The paper-only engine provides a Risk Kernel, durable SQLite financial ledger, conservative synthetic fills and deterministic replay; PR04A adds a **separate observe-only real EOD market-data journal** without placing simulated orders or producing account NAV. [PR #6](https://github.com/handFOOLed/Stratide/pull/6) delivered synthetic replay; [PR #8](https://github.com/handFOOLed/Stratide/pull/8) delivered the first limited real EOD observation on Windows. This is not multi-day forward-paper trading or proof of strategy returns. Linux/macOS, power loss, provider permission scope, fillability and brokerage remain unverified or unimplemented. **Do not use this code to manage real money.** See [M0-PR03](docs/M0_PR03.md) and [M1-PR04A](docs/M1_PR04A.md).

- **ADR-020/021/022:** New versions require independent requalification. Strategy groups can hold the same instrument with separate internal data/P&L but one real account ledger. Trusted portfolio allocation nets compatible opposing group intents before actual broker orders; internal virtual transfers are not exchange fills. See [ADR-020](docs/adr/0020-versioned-requalification-auto-promotion.md), [ADR-021](docs/adr/0021-group-isolation-shared-instrument-attribution.md), and [ADR-022](docs/adr/0022-trusted-cross-group-intent-netting.md).
- **ADR-023:** Both sides of an internal group-to-group virtual allocation use the same trusted market-reference price. Internal reallocation is not a broker fill and adds no actual spread, fees, account equity or real trading P&L ([ADR-023](docs/adr/0023-single-market-reference-internal-transfer.md)).
- **ADR-024:** Actual confirmed partial broker fills are allocated pro rata within the same precommitted priority among eligible groups, with deterministic share rounding, verified risk-reduction priority and reconciled real fees. Unfilled shares are not booked as positions ([ADR-024](docs/adr/0024-prorata-partial-fill-attribution.md)).

PR-02 is merged. Its R2 fix requires exclusive expiry strictly after session close; opening risk qualification is not a proven fill time. Missing-data retries remain supported. Matching model v3 preserves and rejects v1/v2 ledgers without automatic migration. See the historical [R2 evidence and limits](docs/M0_PR02_R2.md) (Chinese).

## Product intent

Stratide is a resource-light, local-first automated trading system with open-ended autonomous research, cloud LLMs only, independent financial risk controls, and a future optional private Web Dashboard. Target design is a personal account around CNY 100,000; this is a sizing assumption, not funds committed or a return promise.

- **Now:** develop and run on Windows PC; backtesting and paper trading first.
- **Later, conditional:** deploy the same portable core on a low-power 24/7 **Apple Silicon Mac mini (macOS ARM64) or Linux mini PC**, with private authenticated web access. Broker adapters may require separate platform-specific integration.
- **Research:** free to explore models, asset types and hypotheses; generated code runs in isolated research workers.
- **Hybrid strategy execution:** light strategies may compute locally and demanding ones remotely. Both submit standardized proposals through the local risk gateway ([ADR-001](docs/adr/0001-hybrid-strategy-execution.md)).
- **Isolated strategy Workers:** generated Python/ML code runs in a restricted local process or isolated remote Worker, never in the credential-bearing Rust core. WASM is optional; actual OS sandbox/resource/access controls must be verified ([ADR-014](docs/adr/0014-isolated-strategy-workers.md)).
- **Automatic data source management:** isolated research Agents may discover and vet public sources, while production Workers have no arbitrary internet access and receive governed inputs from a trusted Data Manager. Built-in compliant public sources need no repetitive manual setup; new credentials, payment and sensitive-data-sharing recipients require initial Owner approval ([ADR-015](docs/adr/0015-automatic-data-manager-network-isolation.md)).
- **Automatic verified failover:** a suitable fresh approved backup takes over after provider failure. Missing or materially conflicting feeds block new exposure for affected strategies; uncertain broker order states still halt account-wide new risk ([ADR-016](docs/adr/0016-verified-data-source-failover.md)).
- **One-time cloud research consent:** Owner may authorize rich portfolio and transaction context for a specific cloud service and purpose once, then allow repeated access without per-request prompts. Grants are revocable for future sharing; broker credentials, execution access and risk policy authority never leave the trusted local core ([ADR-013](docs/adr/0013-one-time-cloud-data-consent.md)).
- **Production:** accepts only promoted, versioned strategy artifacts under a separately enforced risk authority.
- **Single-writer safe recovery:** only one live order-capable core per broker account; restore persistent state and reconcile with the broker before new risk after restart, with explicit authority handoff when moving hosts ([ADR-017](docs/adr/0017-single-writer-durable-recovery.md)).
- **Dedicated initial live account:** the first real-money release uses a brokerage account exclusively allocated to Stratide, not routine manual trades. Broker reconciliation is still mandatory; unknown external orders or mismatches stop new exposure. Verify separate-account availability and API suitability before any live release ([ADR-028](docs/adr/0028-dedicated-broker-account-initial-live.md)).
- **Explicit return after Owner manual takeover:** disable new automated brokerage submissions when the Owner takes control, including automated risk-reducing orders. Restarts or technical recovery cannot auto-resume. Only authenticated Owner handback following authoritative broker reconciliation and all risk checks can restore submission authority ([ADR-029](docs/adr/0029-owner-manual-takeover-explicit-return.md)).
- **Open-order choice at takeover:** neutral Keep orders and adjacent red warning Attempt cancel orders actions; an opposite-side Cancel merely dismisses the takeover dialog. A broker cancellation request is not proof of cancellation, and protective orders may be affected ([ADR-030](docs/adr/0030-owner-takeover-pending-order-choice.md)).
- **Equity-based financial circuit breakers:** trusted cash-flow-adjusted account NAV includes unrealized and realized P&L. External deposits/withdrawals are not trading P&L; uncertain valuation prevents new risk. Financial locks persist across midnight/restart and cannot be released by technical recovery ([ADR-018](docs/adr/0018-equity-based-loss-drawdown-breakers.md)).
- **Dual-layer financial risk:** strategy loss/budget locks bar that strategy from adding risk, while account-wide loss/drawdown/broker-uncertainty halts all strategies. Funds and order commitments are shared, and identity changes cannot reset financial locks ([ADR-019](docs/adr/0019-account-and-strategy-risk-layers.md)).
- **Capital discipline:** eligible strategies may share a dynamically allocated portfolio, but the research/backtest/paper starting principal cannot exceed the Owner-authorized account principal. The Agent cannot invent deposits, duplicate cash across simultaneous strategies or enable default leverage ([ADR-008](docs/adr/0008-dynamic-portfolio-capital-cap.md)).
- **Bidirectional adaptive risk budgets with hard quality gates:** start newly promoted strategies small, scale up cautiously only on robust evidence, and restrict new exposure faster under credible stress or degradation. Independent Risk Kernel overrides the allocator; deterministic replay, fault/stress tests and paper/shadow observation precede separately Owner-enabled live sizing. This is not part of M0 ([ADR-025](docs/adr/0025-adaptive-risk-budget-decay-quality-gates.md)).
- **Daily research spending cap:** the Agent may dynamically plan paid research within an Owner-defined daily limit, enforced by a trusted budget gate. Exhaustion pauses new paid research, not ongoing trading-risk/reconciliation operations ([ADR-012](docs/adr/0012-adaptive-research-daily-hard-budget.md)).
- **Priority:** test failure modes that can lose money; avoid speculative hardening of inconsequential UI/metadata cases.

## Repository map

```text
apps/
  stratided/           tiny placeholder for future background service
  stratide-cli/        local risk demo, durable paper CLI, deterministic replay and reports
  dashboard/           future private Web UI (not implemented)
crates/
  contracts/           paper account, proposal and trusted snapshot contracts
  data/                future data acquisition module
  strategy-runtime/    future isolated strategy runtime
  portfolio/           future portfolio accounting/allocation
  risk/                independent paper risk review, no execution/fills
  ledger/              paper execution, reservations and SQLite event ledger
  forward/             real EOD observe-only adapter and separate SQLite journal
  control-api/         future local-only control interface
research/              cloud LLM and remote worker design notes
config/                environment and deployment notes
scripts/               local workflow helpers

docs/PRODUCT.md        fixed product goals
docs/ARCHITECTURE.md   draft, not frozen
docs/GRILL_BRIEF.md    decisions for grill-with-docs
docs/M0.md             first milestone and stopping rule
docs/RISK_POLICY.md    risk-driven engineering policy
AGENTS.md              instructions for coding agents
```

Empty feature modules are **not** pre-created as fake crates. Add them only when M0 requirements justify it.

## Quick start

Install a current stable Rust toolchain. SQLite is bundled; a C/C++ compiler is required. Windows can use the installed MSVC toolchain through `./scripts/with-msvc.ps1` instead of `cargo`.

```powershell
cargo check --workspace
cargo test --workspace
cargo run -p stratide-cli -- status
cargo run -p stratide-cli -- risk-demo --initial-cash-fen 1000000 --max-order-fen 500000 --account-cap-fen 800000 --strategy-cap-fen 500000 --daily-loss-fen 100000 --drawdown-fen 200000
cargo run -p stratided

New-Item -ItemType Directory -Force state | Out-Null
cargo run -p stratide-cli -- paper-create state/paper-demo-r2 --initial-cash-fen 1000000 --max-order-fen 500000 --account-cap-fen 800000 --strategy-cap-fen 500000 --daily-loss-fen 100000 --drawdown-fen 200000
cargo run -p stratide-cli -- paper-submit-synthetic state/paper-demo-r2
cargo run -p stratide-cli -- paper-match-synthetic state/paper-demo-r2
cargo run -p stratide-cli -- paper-status state/paper-demo-r2
```

### Synthetic replay and reports (merged PR-03)

Use **new, unused** ledger and report directories. All account limits and principal are explicit integer CNY fen. The committed input is fully artificial; this is not a claim of real-world strategy performance.

```powershell
$input = 'samples/m0-pr03-synthetic.json'
$sha = (Get-FileHash $input -Algorithm SHA256).Hash.ToLowerInvariant()
cargo run --locked -p stratide-cli -- paper-replay $input state/pr03-ledger state/pr03-report --sha256 $sha --initial-cash-fen 1000000 --max-order-fen 500000 --account-cap-fen 800000 --strategy-cap-fen 500000 --daily-loss-fen 100000 --drawdown-fen 200000
cargo run --locked -p stratide-cli -- paper-status state/pr03-ledger
cargo run --locked -p stratide-cli -- paper-report $input state/pr03-ledger state/pr03-report --sha256 $sha
Import-Csv state/pr03-report/daily.csv | Format-Table
Import-Csv state/pr03-report/orders.csv | Format-Table
Import-Csv state/pr03-report/fills.csv | Format-Table
```

The six exports are `report.json`, `events.json`, `daily.csv`, `orders.csv`, `fills.csv` and `positions.csv`. Re-running verifies the frozen input, ledger events and derived output. Recognized incomplete exports are preserved as archives before recovery to the original path. See [M0-PR03](docs/M0_PR03.md) and [R1 recovery notes](docs/M0_PR03_R1.md).

### Real-source EOD observation only (merged PR-04A)

Use fresh observer/report paths so existing evidence is not overwritten. The checked-in `samples/m1-pr04a-observer.json` has `local_automation_and_raw_storage_authorized=false` and blocks live collection by default. To run within your own accepted usage scope, copy and review it locally, then explicitly set the flag to `true`. The collector requires `STRATIDE_TUSHARE_TOKEN` in the local process environment; do not commit the value to Git or print it in application logs.

```powershell
Copy-Item samples/m1-pr04a-observer.json state/my-forward-config.json
# Review the local config copy and explicitly set its authorization flag when appropriate.
cargo run --locked -p stratide-cli -- forward-init state/my-forward-journal state/my-forward-config.json
cargo run --locked -p stratide-cli -- forward-collect-once state/my-forward-journal
cargo run --locked -p stratide-cli -- forward-status state/my-forward-journal
cargo run --locked -p stratide-cli -- forward-report state/my-forward-journal state/my-forward-report
Import-Csv state/my-forward-report/daily.csv | Format-Table
```

The exports are `report.json`, `daily.csv` and `events.json`. This remains **observe-only**, with no paper trades, funded NAV or fake fill evidence. Existing reports with different contents are preserved; choose a new report directory. See [PR04A implementation](docs/M1_PR04A.md) and [R2 test evidence](docs/evidence/m1-pr04a-r2/README.md).

`risk-demo` uses fixed `synthetic_test` prices, rules, costs and timestamps. Pass all principal/risk settings explicitly in integer CNY fen; there is no default capital. Acceptance never means a fill or changes cash/positions. `stratided` remains a placeholder. A successful build **does not** mean it is safe to trade. The paper ledger's Windows acceptance and replay reporting limits are recorded in [M0-PR02](docs/M0_PR02.md), [M0-PR03](docs/M0_PR03.md) and [PR #6](https://github.com/handFOOLed/Stratide/pull/6).

## GitHub repository

Repository: https://github.com/handFOOLed/Stratide (private). The M0 scaffold is checked in. Clone with your normal GitHub authentication; never commit credentials.

Protective-order cancellation confirmation follows [ADR-031](docs/adr/0031-inline-confirmation-for-protective-order-cancellation.md).

## Before implementation: grill-with-docs

The original [grill-with-docs skill](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs) delegates to **grilling** and **domain-modeling**. Install all three into your Codex workspace, then run `grill-with-docs` explicitly against [`docs/GRILL_BRIEF.md`](docs/GRILL_BRIEF.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`AGENTS.md`](AGENTS.md).

```powershell
npx skills add mattpocock/skills --skill grilling
npx skills add mattpocock/skills --skill domain-modeling
npx skills add mattpocock/skills --skill grill-with-docs
```

Review external skill instructions before installing them. Keep terminology in `GLOSSARY.md` and irreversible trade-offs in `docs/adr/` **only when decided**; do not create boilerplate ADRs. Exact CLI invocation may depend on your Codex version.

## Development rule

**Research freely. Deploy carefully. Risk authority is not negotiable.**

---
Documentation language policy: Chinese is the primary language for owner-facing project communication; English is maintained here for external readers. Code symbols and public technical contracts may remain in English.
