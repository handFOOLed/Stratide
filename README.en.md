[简体中文](README.md) | **English**

# Stratide

**Autonomous Quantitative Trading & Open-Ended Strategy Discovery**

Status: **M0 scaffold — NOT a trading system**. No market-data provider, broker connection, order routing, research agent, or real-money execution is implemented. Do not use this repository to manage real funds.

## Product intent

Stratide is a resource-light, local-first automated trading system with open-ended autonomous research, cloud LLMs only, independent financial risk controls, and a future optional private Web Dashboard. Target design is a personal account around CNY 100,000; this is a sizing assumption, not funds committed or a return promise.

- **Now:** develop and run on Windows PC; backtesting and paper trading first.
- **Later, conditional:** deploy the same portable core on a low-power 24/7 **Apple Silicon Mac mini (macOS ARM64) or Linux mini PC**, with private authenticated web access. Broker adapters may require separate platform-specific integration.
- **Research:** free to explore models, asset types and hypotheses; generated code runs in isolated research workers.
- **Hybrid strategy execution:** light strategies may compute locally and demanding ones remotely. Both submit standardized proposals through the local risk gateway ([ADR-001](docs/adr/0001-hybrid-strategy-execution.md)).
- **One-time cloud research consent:** Owner may authorize rich portfolio and transaction context for a specific cloud service and purpose once, then allow repeated access without per-request prompts. Grants are revocable for future sharing; broker credentials, execution access and risk policy authority never leave the trusted local core ([ADR-013](docs/adr/0013-one-time-cloud-data-consent.md)).
- **Production:** accepts only promoted, versioned strategy artifacts under a separately enforced risk authority.
- **Capital discipline:** eligible strategies may share a dynamically allocated portfolio, but the research/backtest/paper starting principal cannot exceed the Owner-authorized account principal. The Agent cannot invent deposits, duplicate cash across simultaneous strategies or enable default leverage ([ADR-008](docs/adr/0008-dynamic-portfolio-capital-cap.md)).
- **Daily research spending cap:** the Agent may dynamically plan paid research within an Owner-defined daily limit, enforced by a trusted budget gate. Exhaustion pauses new paid research, not ongoing trading-risk/reconciliation operations ([ADR-012](docs/adr/0012-adaptive-research-daily-hard-budget.md)).
- **Priority:** test failure modes that can lose money; avoid speculative hardening of inconsequential UI/metadata cases.

## Repository map

```text
apps/
  stratided/           tiny placeholder for future background service
  stratide-cli/        tiny placeholder for future local CLI
  dashboard/           future private Web UI (not implemented)
crates/
  contracts/           shared protocol placeholder
  data/                future data acquisition module
  strategy-runtime/    future isolated strategy runtime
  portfolio/           future portfolio accounting/allocation
  risk/                future independent risk decision module
  execution/           future order state machine
  ledger/              future append-only transaction/audit ledger
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

Install a current stable Rust toolchain. This repo is a minimal Cargo workspace with no external dependencies at initialization.

```powershell
cargo check --workspace
cargo test --workspace
cargo run -p stratide-cli -- status
cargo run -p stratided
```

Both executables only identify themselves as M0 placeholders. A successful build **does not** mean it is safe to trade.

## GitHub repository

Repository: https://github.com/handFOOLed/Stratide (private). The M0 scaffold is checked in. Clone with your normal GitHub authentication; never commit credentials.

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
