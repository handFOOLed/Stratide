**简体中文** | [English](README.en.md)

# Stratide

**PR #8 补测后进展（仍为 Draft）：** Owner 对本账户自动采集和本地原始响应保存作出明确声明后，新建 journal 已完成实际 HTTPS 入库、恢复及重复/晚到核对，当前为 1 个有效前向日、0 提案/成交。许可依据仍仅为 Owner 声明，非供应商书面或独立认证；待独立复验及许可门槛判定。见 [R1 证据](docs/evidence/m1-pr04a-r1/README.md)。以下首次提交的 blocked 记录保留。

**M1-PR04A 开发分支：Draft / BLOCKED。** 已增加只观察的独立 journal、单次盘后采集适配器及 CSV/JSON CLI；本机 Tushare HTTPS `daily`/`trade_cal` 实测可读，但自动采集/原始响应持久保存许可仍未确认，样例默认阻断。有效前向日数、策略提案、模拟成交均为 0；没有修改 v3 财务账本。见 [命令、实际输出和未验证范围](docs/M1_PR04A.md)及[来源核验](docs/M1_PR04A_SOURCE_FEASIBILITY.md)。此分支尚待 Terra 独立验收、小猫审查和 Owner 授权合并，不能视为整个 M1 已完成。

[ADR-026](docs/adr/0026-budgeted-shadow-observation-and-local-strategy-registry.md)：限额研究与策略索引。[ADR-027](docs/adr/0027-historical-failure-as-evidence-not-permanent-ban.md)：历史失败作为研究证据，而不是永久研究禁令；重新研究也不会解除真实资金风控。

**自主量化交易与开放式策略发现平台**  
*Autonomous Quantitative Trading & Open-Ended Strategy Discovery*

> **当前状态：M0-PR01、PR-02、PR-03 已合并，Windows 上完成 Terra 独立验收与 ChatGPT 源码审查。** 现有 **paper-only** 能力包括独立风控、单写入者 SQLite 持久账本、原子预留、保守日线模拟成交、冻结输入的确定性回放，以及六份可审计 CSV/JSON 报表；PR-03 见 [PR #6](https://github.com/handFOOLed/Stratide/pull/6)，合并提交 `13de8d43f663caa16c983609d2d5161ca497d123`。随仓样例仅为 `synthetic_test` **合成人工数据/费率**，没有经过核验的真实历史行情或长期前向模拟，也没有真实券商接口。Linux/macOS、物理断电及实际行情许可/可得性未验证。**不得使用当前代码管理真实资金或以示例数据声称盈利能力。**

人工成交先记入独立待归属账簿，不推断策略组归属，见 [ADR-032](docs/adr/0032-manual-trades-suspense-ledger-unassigned-attribution.md)；最终由 Owner 显式选择归属组别和数量，不允许自动按比例猜测或修改真实成交，见 [ADR-033](docs/adr/0033-owner-explicit-manual-fill-group-attribution.md)。

PR-02 已合并；其 R2 修复要求订单有效期严格覆盖完整交易时段，开盘资格不代表确定成交时刻；缺行情仍可补数重试。v1／v2 账本保留且拒绝自动迁移，现有模型为 v3。详见 [R2 修复说明](docs/M0_PR02_R2.md)；该文保留合并前的历史状态与证据。

## 当前优先任务：可观察的模拟交易

根据 [ADR-037](docs/adr/0037-observable-paper-trading-first-and-independent-review-gates.md)，先实现可复现的单策略模拟交易内核（M0），再接入真实来源行情进行前向 Paper Trading 观察（M1），输出净值、持仓、成交、费用、回撤及风险拒单等可核实报告。**GPT-6.1 Sol 编码、GPT-6.1 Terra 独立测试/出具同 SHA 验收报告、ChatGPT（小猫）审查并在明确通过后用 HEAD SHA 锁定安全合并、Owner 观察结果及决定范围**。详细 PR 交付与验收标准见 [模拟交易路线图](docs/PAPER_TRADING_ROADMAP.md)。所有结果须区分合成、历史回放和前向模拟；当前只交付 M0 的窄范围模拟内核，仍不能用于真实资金。

## 项目愿景

已合并的回放命令、实际导出文件和验证边界见 [M0-PR03 实现说明](docs/M0_PR03.md)及 [R1 中断恢复修复](docs/M0_PR03_R1.md)；基础账本见 [M0-PR02 实现说明](docs/M0_PR02.md)。PR #6 的 [Terra 独立 PASS 验收](https://github.com/handFOOLed/Stratide/pull/6#issuecomment-6465953588) 与 [ChatGPT 同 SHA 代码审查](https://github.com/handFOOLed/Stratide/pull/6#pullrequestreview-5680851123) 已完成。**下一里程碑为 M1 的真实来源前向 Paper 观察，尚未实现或验收。**

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
- **分红送股自动归属：** 按可信股权登记日权益份额，将现金分红和送股自动记到对应策略组，并对账券商实际金额、税费、份额与成本；不重复计算收益。配股缴款等需新资金的事项按 ADR-036 由 Owner 明确批准（[ADR-035](docs/adr/0035-record-date-corporate-action-group-attribution.md)）。
- **主动公司行为需批准：** 配股缴款、认购和要约选择由可信系统识别、核对和提醒，但只有 Owner 对具体事件明确批准后才可能参与；现金、风控和券商条件仍必须核验，不回应不代表同意（[ADR-036](docs/adr/0036-owner-approval-for-voluntary-corporate-actions.md)）。
- **跨组交易意图净额执行：** 可信组合分配器在执行前合并同股相反买卖意图，尽量减少券商委托；内部虚拟份额变更不是交易所成交，不得虚构现金、收益或绕过实际交易限制（[ADR-022](docs/adr/0022-trusted-cross-group-intent-netting.md)）。
- **内部转移统一定价：** 跨组虚拟份额调整由可信组合管理器使用同一市场参考价进行双方记账，不生成虚假的买卖价差、真实手续费、券商成交或额外账户净值（[ADR-023](docs/adr/0023-single-market-reference-internal-transfer.md)）。
- **外部部分成交按比例归属：** 同优先级内各组按有效需求占比分配券商真实确认成交的份额；风险减仓可有可信优先级，取整和实际费用分摊必须可复现，绝不把未成交数量算入持仓（[ADR-024](docs/adr/0024-prorata-partial-fill-attribution.md)）。
- **单实例安全恢复：** 每个真实账户同一时刻只允许一个有执行权的核心，重启后先恢复持久状态并核对券商订单/资金/持仓，不盲目重发订单；迁移主机需先停用旧执行端（[ADR-017](docs/adr/0017-single-writer-durable-recovery.md)）。
- **初始实盘专用账户：** 真实资金运行时优先使用不与日常人工交易混用的 Stratide 专用证券账户；仍需向券商对账，发现未知订单、成交或持仓差异时停止该账户新增风险。具体券商与开户条件须先验证（[ADR-028](docs/adr/0028-dedicated-broker-account-initial-live.md)）。
- **紧急人工接管：** Owner 接管后立即持久禁止所有新的自动券商委托；网络恢复、重启或对账成功也不能自行恢复。必须由 Owner 明确交还，且券商订单、持仓、资金及所有风控检查通过（[ADR-029](docs/adr/0029-owner-manual-takeover-explicit-return.md)）。
- **接管时挂单处理选择：** 相邻普通「保留挂单并接管」与红色警示「尝试撤单并接管」，另一侧独立「取消」仅关闭界面。撤单不保证成功，保护性卖单可能受影响；不将撤单请求当作券商确认（[ADR-030](docs/adr/0030-owner-takeover-pending-order-choice.md)）。
- **保护性挂单撤销确认：** 当撤单涉及保护性委托，必须在原接管界面额外勾选风险确认，不弹第二层窗口；订单情况变化后旧确认失效（[ADR-031](docs/adr/0031-inline-confirmation-for-protective-order-cancellation.md)）。
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
  stratide-cli/        风险示例、持久 Paper CLI、确定性回放与 CSV/JSON 报表
  dashboard/           未来的私有 Web 控制台（未实现）
crates/
  contracts/           Paper 账户、提案与可信快照契约
  risk/                独立 Paper 风险审查（无下单/成交）
  ledger/              Paper 撮合、原子预留与 SQLite 事件账本
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

真实数据接入、策略运行时、真实券商执行与控制 API **尚未实现**；后续只在真实开发任务需要时增加，不提前堆空目录和无意义的抽象。

## 本地运行

安装稳定版 Rust 工具链，然后在仓库根目录执行：

```powershell
cargo check --workspace
cargo test --workspace
cargo run -p stratide-cli -- status
cargo run -p stratide-cli -- risk-demo --initial-cash-fen 1000000 --max-order-fen 500000 --account-cap-fen 800000 --strategy-cap-fen 500000 --daily-loss-fen 100000 --drawdown-fen 200000
cargo run -p stratided

# state/ 是运行数据目录；仅创建父目录，不覆盖任何已有账户。
New-Item -ItemType Directory -Force state | Out-Null
cargo run -p stratide-cli -- paper-create state/paper-demo-r2 --initial-cash-fen 1000000 --max-order-fen 500000 --account-cap-fen 800000 --strategy-cap-fen 500000 --daily-loss-fen 100000 --drawdown-fen 200000
cargo run -p stratide-cli -- paper-submit-synthetic state/paper-demo-r2
cargo run -p stratide-cli -- paper-match-synthetic state/paper-demo-r2
cargo run -p stratide-cli -- paper-status state/paper-demo-r2
```

### 已合并 PR-03：运行合成回放与生成六份报告

下面的路径是**新建**示例路径，勿覆盖已有账户/报表；参数是人民币整数分，均需用户显式设置。

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

六份报告为 `report.json`、`events.json`、`daily.csv`、`orders.csv`、`fills.csv`、`positions.csv`。同一冻结输入重跑会检查账本事件和报表内容；意外中断的可识别残缺旧报表先归档，再以同路径恢复。**这些仅是合成数据的模拟账簿与计算演示，不是已验证的真实历史收益。**

`risk-demo` 的价格、规则、费用与时间均为固定 `synthetic_test` 输入，金额参数以整数分显式传入，无默认本金；接受提案不代表成交，也不改变现金或持仓。`stratided` 仍是占位程序。**编译成功不代表能够安全交易**；Windows 若未加载 MSVC 开发环境，可用 `./scripts/with-msvc.ps1` 代替 `cargo`。回放的实际 Windows 独立验收、报表及未验证项见 [M0-PR03](docs/M0_PR03.md) 和 [PR #6](https://github.com/handFOOLed/Stratide/pull/6)。

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
