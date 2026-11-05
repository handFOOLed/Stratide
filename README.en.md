[简体中文](README.md) | **English**

# Stratide

**A Windows 11, local-first A-share end-of-day research and automated paper-trading desktop application.**

Stratide brings market-data ingestion, local TimesFM forecasting, permission-controlled DeepSeek strategy research, risk controls, a shared paper-trading ledger, and a local Dashboard together. It supports optional background start at Windows sign-in and double-click desktop launching.

## Features

- **EOD market data:** Tushare A-share universe, incremental collection, data-coverage gates, and source provenance.
- **Automated research:** Lightweight universe screening → local TimesFM CPU via WSL2 → separately authorized DeepSeek Fusion research and frozen candidates.
- **Multi-security paper trading:** Shared cash, positions, fees, and risk/ledger; T+1 ex-post opening-price simulation from previously frozen decisions.
- **Local Dashboard:** Market health, research, simulated portfolio and fills, cost controls, approvals, notifications, and runtime diagnostics.
- **Windows experience:** Installer, desktop shortcut, single-instance supervisor, optional sign-in startup, data-preserving upgrades and uninstall.

## Quick start

1. Visit [GitHub Releases](https://github.com/handFOOLed/Stratide/releases) and install `Stratide-Setup-0.3.0-x64.exe`.
2. **Double-click Stratide** on the desktop. The launcher starts or reuses the local service and opens the Dashboard in your default browser.
3. Open **Settings → Runtime & Installation** (`运行与安装`), save your Tushare token, initialize and enable EOD collection.
4. For automated research, connect your existing WSL2 TimesFM environment and run the Worker probe. Enable research and any real-data sharing only through the separate Owner authorization workflow.
5. To simulate trades, explicitly create/bind a paper account and configure the Owner-approved risk and strategy policy. Enable optional sign-in startup when ready.

For step-by-step setup, see the [user guide (Chinese)](docs/USER_GUIDE.md). The installer does not silently authorize paid cloud calls or trading policies.

## Documentation

| Topic | Link |
| --- | --- |
| First-time setup and daily use | [User guide](docs/USER_GUIDE.md) |
| Installation and upgrades | [Windows installation](docs/WINDOWS_INSTALL.md) |
| Troubleshooting and operating constraints | [Known limitations](docs/KNOWN_LIMITATIONS.md) |
| Implementation status and provenance | [Project status](docs/STATUS.md) |
| Engineering and historical records | [Documentation index](docs/README.md) |

## Project

**Stratide V2 / Windows 0.3.0** is available as a local paper-trading application. All four engineering milestones are merged to `main`: [PR #86](https://github.com/handFOOLed/Stratide/pull/86), [#87](https://github.com/handFOOLed/Stratide/pull/87), [#88](https://github.com/handFOOLed/Stratide/pull/88), and [#89](https://github.com/handFOOLed/Stratide/pull/89).

**Paper-only:** No brokerage connection or real-money execution. Real market-data egress requires explicit, separately scoped authorization, and research never bypasses local risk controls.

Developers: [AGENTS.md](AGENTS.md) · [docs/README.md](docs/README.md).
