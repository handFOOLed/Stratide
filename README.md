**简体中文** | [English](README.en.md)

# Stratide

[ADR-026](docs/adr/0026-budgeted-shadow-observation-and-local-strategy-registry.md)：限额研究与策略索引。[ADR-027](docs/adr/0027-historical-failure-as-evidence-not-permanent-ban.md)：历史失败作为研究证据，而不是永久研究禁令；重新研究也不会解除真实资金风控。

**自主量化交易与开放式策略发现平台**  
*Autonomous Quantitative Trading & Open-Ended Strategy Discovery*

> **当前状态：M0 工程骨架，尚不是可用的交易系统。** 目前尚未实现行情接入、券商接口、下单执行、研究 Agent 或真实资金交易。**请勿使用当前代码管理真实资金。**

## 项目愿景

Stratide 是面向个人用户的**低资源占用、本地优先**的自动化交易平台。它允许云端 AI Agent 自主探索新的交易策略，但所有实际交易必须受到**独立、不可绕过的风控系统**约束。

设计参考规模约为 **人民币 10 万元的潜在交易账户**。这只是工程容量假设，既不代表已投入资金，也不代表收益承诺。

核心原则：

- **先验证，后实盘：** 目前在 Windows 电脑上开发、回测和模拟交易。
- **有效才部署：** 仅在稳定性和扣除成本后的表现得到充分验证后，才考虑迁移至低功耗、24 小时运行的 **Mac mini（macOS ARM64）或 Linux 迷你主机**；券商接口跨平台兼容性需另行验证。
- **未来可远程管理：** 预留独立 Web Dashboard，与个人网站连接时需采用严格的访问认证，且不直接暴露交易内核。
- **研究自由：** Agent 可探索各种模型、资产和假设；生成代码只在隔离环境运行。
- **混合策略执行：** 简单策略本地计算、复杂策略允许远程计算，但一律向本地独立风控提交标准化提案（[ADR-001](docs/adr/0001-hybrid-strategy-execution.md)）。
- **独立策略 Worker：** Agent 生成的 Python/ML 策略运行在本地受限进程或远程隔离环境，不在持有资金权限的 Rust 核心执行；不强制 WASM，运行环境必须有实际可验证的隔离边界（[ADR-014](docs/adr/0014-isolated-strategy-workers.md)）。
- **自动数据源管理：** 研究 Agent 可自主发现、评估公开数据源；生产策略 Worker 默认不随意访问互联网，而是通过可信 Data Manager 获取数据。内置合规免费来源不要求逐个手工配置，涉及付费、凭据或新的敏感数据共享时才首次授权（[ADR-015](docs/adr/0015-automatic-data-manager-network-isolation.md)）。
- **可信备用数据源自动切换：** 主源失败后自动接入已验证的新鲜备源；数据重大冲突或都不可用时暂停受影响策略的新增交易，不改变券商订单未知时全账户冻结的要求（[ADR-016](docs/adr/0016-verified-data-source-failover.md)）。
- **实盘受控：** 只有完成独立验证并获得授权的版本化策略才可能进入生产环境。
- **风控独立：** 必须具备基础亏损熔断、仓位与订单约束、状态持久化和异常对账；熔断不能保证成交或锁定最大亏损。
- **净值亏损熔断：** 每日亏损和回撤以可信账户净值计算，包含已实现与浮动盈亏；出入金不算作策略盈亏，重大估值不确定时不允许新增风险，触发后不能因跨日或重启自动解除（[ADR-018](docs/adr/0018-equity-based-loss-drawdown-breakers.md)）。
- **账户与策略双层风控：** 单策略亏损/超额仅限制该策略新增风险；账户级亏损熔断或订单状态不明则禁止所有策略新增风险。策略预算共用账户资金且不得靠改名重置熔断（[ADR-019](docs/adr/0019-account-and-strategy-risk-layers.md)）。
- **新版本自主准入：** 策略改参生成新的冻结版本，重新独立验证通过后可自动晋升，不清除历史亏损和禁令（[ADR-020](docs/adr/0020-versioned-requalification-auto-promotion.md)）。
- **策略组数据隔离：** 不同组可以持有同一股票，但组内生成的数据、信号、虚拟份额和盈亏独立归属；真实资金、仓位和账户风险共用一份账本（[ADR-021](docs/adr/0021-group-isolation-shared-instrument-attribution.md)）。
- **跨组交易意图净额执行：** 可信组合分配器在执行前合并同股相反买卖意图，尽量减少券商委托；内部虚拟份额变更不是交易所成交，不得虚构现金、收益或绕过实际交易限制（[ADR-022](docs/adr/0022-trusted-cross-group-intent-netting.md)）。
- **内部转移统一定价：** 跨组虚拟份额调整由可信组合管理器使用同一市场参考价进行双方记账，不生成虚假的买卖价差、真实手续费、券商成交或额外账户净值（[ADR-023](docs/adr/0023-single-market-reference-internal-transfer.md)）。
- **外部部分成交按比例归属：** 同优先级内各组按有效需求占比分配券商真实确认成交的份额；风险减仓可有可信优先级，取整和实际费用分摊必须可复现，绝不把未成交数量算入持仓（[ADR-024](docs/adr/0024-prorata-partial-fill-attribution.md)）。
- **单实例安全恢复：** 每个真实账户同一时刻只允许一个有执行权的核心，重启后先恢复持久状态并核对券商订单/资金/持仓，不盲目重发订单；迁移主机需先停用旧执行端（[ADR-017](docs/adr/0017-single-writer-durable-recovery.md)）。
- **不在本地跑大模型：** LLM 推理经可替换的云端 API；重型研究计算可使用远程 Worker。交易核心不需要 GPU。
- **云端账户研究数据授权：** 用户首次确认云端接收服务与数据范围后，Agent 可持续读取已授权的持仓、资金及交易研究上下文，不反复弹窗；可随时撤销后续共享，但券商密钥和交易权限绝不外传（[ADR-013](docs/adr/0013-one-time-cloud-data-consent.md)）。
- **动态组合资金池：** 已通过资格验证的策略可在授权范围内动态共享资金。研究、回测和模拟账户的起始本金不得超过你明确授权的账户本金，Agent 不得虚构资金、重复分配现金或默认使用杠杆（[ADR-008](docs/adr/0008-dynamic-portfolio-capital-cap.md)）。
- **双向动态预算与严格质量门槛：** 新策略小额起步，在持续证据支持下谨慎扩容；可信市场风险/策略衰退信号可更快限制新增风险。独立风控始终拥有最终权限，实盘启用前须完成可复现测试、异常注入和长期模拟/影子观察；M0 不实现该功能（[ADR-025](docs/adr/0025-adaptive-risk-budget-decay-quality-gates.md)）。
- **风险驱动工程：** 深入测试可能带来财产损失的问题；不为无关紧要的名称、格式或极端展示异常投入过度开发时间。
- **控制总成本：** 综合考虑交易摩擦、数据订阅、模型 API、计算和维护费用；允许系统在缺乏可信交易优势时保持不交易。
- **每日研究预算硬上限：** Agent 可在你设置的每日上限内自主规划模型调用和计算实验；不能自行提额。研究费用用尽仅暂停新的付费研究，不影响已有交易的风控与对账（[ADR-012](docs/adr/0012-adaptive-research-daily-hard-budget.md)）。

## 仓库结构

```text
apps/
  stratided/           Rust 后台服务占位程序
  stratide-cli/        本地 CLI 占位程序
  dashboard/           未来的私有 Web 控制台（未实现）
crates/
  contracts/           共享契约占位库
research/              云端 Agent / 远程计算的设计说明
config/                配置与部署说明
scripts/               本地辅助工具说明

docs/
  PRODUCT.md           已确认的产品原则
  ARCHITECTURE.md      待讨论的架构草案
  GRILL_BRIEF.md       grill-with-docs 质询议程
  M0.md                第一阶段范围与验收标准
  RISK_POLICY.md       财务风险优先的开发规范

AGENTS.md              Codex 等编程 Agent 的工作规则
Cargo.toml             Rust Workspace
README.en.md           English README
```

数据、策略运行时、风控、执行、账本、控制 API 等模块**尚未实现**；后续只在真实开发任务需要时增加，不提前堆空目录和无意义的抽象。

## 本地运行

安装稳定版 Rust 工具链，然后在仓库根目录执行：

```powershell
cargo check --workspace
cargo test --workspace
cargo run -p stratide-cli -- status
cargo run -p stratided
```

目前两个可执行程序仅用于验证 M0 工程结构，**编译成功不代表能够安全交易**。当前版本尚未经过完整本地编译与测试验证。

仓库：[handFOOLed/Stratide](https://github.com/handFOOLed/Stratide)（Private）。请使用正常的 GitHub 身份认证拉取，不要将 API Key、券商凭据或个人账户数据提交到仓库。

## 开发前：grill-with-docs

在进入实质性编码前，先用 [grill-with-docs](https://github.com/mattpocock/skills/tree/main/skills/engineering/grill-with-docs) 对产品设计和技术架构进行针对性质询。原版工作流依赖 `grilling` 与 `domain-modeling`。可按需在 Codex 环境安装：

```powershell
npx skills add mattpocock/skills --skill grilling
npx skills add mattpocock/skills --skill domain-modeling
npx skills add mattpocock/skills --skill grill-with-docs
```

安装外部 skill 前应先检查其说明。重点阅读：

- [架构草案](docs/ARCHITECTURE.md)
- [架构质询议程](docs/GRILL_BRIEF.md)
- [Agent 开发规则](AGENTS.md)
- [风险策略](docs/RISK_POLICY.md)

不要为了形式提前生成一堆 ADR 或术语文档。只有确实形成重要技术决策后才记录。具体 skill 命令取决于 Codex 环境。

## 开发纪律

**研究可以大胆探索，生产部署必须谨慎，风控权限不可妥协。**

开发任务优先用中文沟通。对真实资金有影响的风险必须认真验证；普通 UI、展示文本和无财务后果的边缘问题应以简单实现为主，避免过度工程化。
