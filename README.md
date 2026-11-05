**简体中文** | [English](README.en.md)

# Stratide

**面向 Windows 11 的本地 A 股盘后研究与自动 Paper 模拟交易系统。**

Stratide 将市场行情采集、TimesFM 本地时序预测、受控 DeepSeek 策略研究、风险管理与 Paper 交易整合到一个 Dashboard。它可以在 Windows 用户登录后自动运行，也可以通过桌面快捷方式双击启动。

## 核心功能

- **盘后市场数据**：Tushare A 股市场证券池、增量 EOD 采集、数据完整性与来源追踪。
- **自动研究**：全市场轻量筛选 → 本地 WSL2/CPU TimesFM → 按授权使用 DeepSeek 生成并冻结策略候选。
- **多证券 Paper 模拟**：共享现金、持仓、手续费与风控账本；T+1 盘后基于冻结意图进行事后假设成交。
- **一体化 Dashboard**：查看行情、研究任务、组合、交易、预算、审批通知与后台状态。
- **Windows 桌面体验**：安装包、桌面快捷方式、单实例后台服务、可选登录自启、数据保留式升级/卸载。

## 快速开始

1. 在 [GitHub Releases](https://github.com/handFOOLed/Stratide/releases) 下载 `Stratide-Setup-0.3.0-x64.exe`，按向导安装。
2. **双击桌面 Stratide 图标**；软件会启动或复用本地服务，并在默认浏览器打开 Dashboard。
3. 进入 **设置 → 运行与安装**，保存 Tushare Token、初始化并启用 EOD 数据采集。
4. 如需自动研究，在同一页面配置已有 WSL2 TimesFM 并点击「检测 WSL Worker」；随后按 **设置 → 权限与安全** 中的 Owner 流程启用研究、独立数据外发授权与预算。
5. 如需自动 Paper 模拟，在既有 Owner 流程中配置或绑定 Paper 账户、风险与策略，再按需启用 Windows 登录自启。

详细步骤与高级配置入口见 **[完整使用教程](docs/USER_GUIDE.md)**。第一次使用只想查看界面和状态时，可以先不启用付费研究或模拟交易。

## 文档

| 你想了解的内容 | 入口 |
| --- | --- |
| 从安装到日常使用 | [使用教程](docs/USER_GUIDE.md) |
| 安装、升级、卸载 | [Windows 安装手册](docs/WINDOWS_INSTALL.md) |
| 错误提示、系统要求与运行边界 | [故障排查与已知限制](docs/KNOWN_LIMITATIONS.md) |
| 项目进度与工程证据 | [当前状态](docs/STATUS.md) |
| 代码、架构、历史文档 | [文档中心](docs/README.md) |

## 项目说明

- 当前版本：**Stratide V2 / Windows 0.3.0**，四个工程模块均已合入 `main`（[PR #86](https://github.com/handFOOLed/Stratide/pull/86) · [#87](https://github.com/handFOOLed/Stratide/pull/87) · [#88](https://github.com/handFOOLed/Stratide/pull/88) · [#89](https://github.com/handFOOLed/Stratide/pull/89)）。
- **Paper-only**：不连接真实券商、不以真实资金下单。真实市场数据云端外发需要单独授权，模型研究不能绕过本地风险控制。
- 本项目为个人使用场景构建；涉及交易与投资的决定由使用者自行承担。

开发者可从 [AGENTS.md](AGENTS.md) 和 [docs/README.md](docs/README.md) 开始了解系统内部结构。
