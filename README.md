**简体中文** | [English](README.en.md)

# Stratide

本地优先、**仅模拟交易（Paper-only）** 的个人量化研究系统：Rust 风控/账本与历史回放、真实盘后数据观察、本地只读 Paper Dashboard 与受控研究 Agent。**不能用于真实资金交易，也不代表已验证盈利能力。**

## 当前状态

- **已实现：** Paper Risk Kernel、持久账本、六报告、真实历史 EOD 探索性回测、只观察的前向 EOD journal、[Web Dashboard V1](apps/dashboard/README.md)。
- **本分支 Draft：** [Agent V1](docs/M2_PR02.md) 完成持久任务、日/月预算、受控 HTTPS Provider、本地 fake、EOD 去重和 Web 基础交互；[API](docs/AGENT_API.md) 与 [自测证据](docs/evidence/m2-pr02/README.md) 已保存。真实 Provider **REAL_PROVIDER_NOT_VERIFIED**，未配置 Owner 预算/授权不付费；独立风险核查和同 HEAD 审查待完成。
- **仍受阻：** 仅 68 个历史交易日、3 笔模拟成交，长窗口公司行为/费用证据 `DATA_BLOCKED`；前向观察仅 1 个有效日、**尚无真正前向模拟成交或 NAV**。
- **下一步：** [#22 Agent 功能与 API（Sol）](https://github.com/handFOOLed/Stratide/issues/22) → [#23 整站 UI/UX（DeepSeek）](https://github.com/handFOOLed/Stratide/issues/23)。细节与证据见 [当前状态](docs/STATUS.md)。

## Windows 本地体验

在仓库根目录运行（以下为**合成测试数据**，不是实际市场收益）：

```powershell
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report'

# 验证 Agent 闭环：仅本地 fake / TST 合成费用。
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report' -AgentDir state/agent-fake -FakeAgent
```

浏览器打开 `http://127.0.0.1:8710`；Ctrl+C 停止。使用自己的已发布 Paper 六报告请参阅 [Dashboard 启动与数据说明](apps/dashboard/README.md)。Rust/CLI/观察工具见 [工程说明](docs/PAPER_TRADING_ROADMAP.md) 与 `scripts/README.md`。

## 团队与文档

- **Owner：** 范围与合并决定；**Sol：** 后端、Agent、接口和关键测试；**DeepSeek：** 信息架构、字体/组件、布局与平滑动效；**ChatGPT：** 固定 HEAD 审查、获授权后合并。
- [DeepSeek UI 交接规范](docs/UI_HANDOFF_DEEPSEEK.md) · [编码规则](AGENTS.md) · [产品原则](docs/PRODUCT.md) · [风险规范](docs/RISK_POLICY.md) · [历史 ADR](docs/adr/)。

**所有历史回放均不等于实时前向验证；不接入实盘券商。**
