**简体中文** | [English](README.en.md)

# Stratide

> **项目现行状态｜2026-11-05**：V2/M3 **模块 A/B/C 软件工程已合并至 `main`**：[#82 / PR #86](https://github.com/handFOOLed/Stratide/pull/86) 全市场 EOD 数据层、[#83 / PR #87](https://github.com/handFOOLed/Stratide/pull/87) 受控 TimesFM + DeepSeek 自动研究、[#84 / PR #88](https://github.com/handFOOLed/Stratide/pull/88) 多证券共享 Paper 账户与 T+1 事后模拟。**#85 / M3-PR04 已提交 Draft 开发交付（未合并）：** 可构建的 Windows 11 安装包、用户登录后台自启、单实例 Supervisor/Launcher、双击打开 Dashboard、运行诊断页、升级/卸载数据保全。安装与首启步骤见 [WINDOWS_INSTALL](docs/WINDOWS_INSTALL.md)，设计与已知限制见 [M3_PR04](docs/M3_PR04.md)、[证据](docs/evidence/m3-pr04/README.md)。**未 Ready/未合并；研究/WSL 自动链路仍未接入。** [现行状态](docs/STATUS.md) · [V2 总路线图 #81](https://github.com/handFOOLed/Stratide/issues/81)。

> **不能误解的能力边界**：目前是 Paper-only，不接券商/真钱；自动模拟采用冻结 T 日意图、T+1 盘后实收日线的 `EX_POST_OPEN_ASSUMPTION`。未核验公司行为假设必须 Owner 单独批准且受原 Risk 与保守额度约束，不能当作真实成交或策略有效性。真实全市场在线采集/自动模型/Windows 安装产品尚未完成全部实机 E2E（本机沙箱无法执行快捷方式/自启/卸载注册表，见证据），84 个 READY 会话为研究暖机条件；真实数据云外发默认 DENIED，DeepSeek 内部硬预算仍是 CNY ¥5/日、¥100/月。N100 部署延期。



本地优先、**仅模拟交易（Paper-only）** 的个人量化研究系统：Rust 风控/账本与历史回放、真实盘后数据观察、本地只读 Paper Dashboard 与受控研究 Agent。**不能用于真实资金交易，也不代表已验证盈利能力。**

## 历史模块记录（以下“Draft/当前”均为原提交时状态）

- **M2-PR20 真实历史本地风险（#74 / 本分支 Draft）：** 已有真实 V1/V2 数据与质量标签 → 前缀冻结 → TimesFM CPU → 原任务/Registry/report/verify 已实际通过三证券。真实因子变化/缺口拒绝，新行情请求、云调用及计费均为 0；真实风险结果禁止外发。PIT、样本外优势、Paper/Live 与 N100 资格仍未验证。见[操作](docs/M2_PR20.md)和[证据](docs/evidence/m2-pr20/README.md)。

- **M2-PR19 真实 Fusion（#71 / PR #72 已合并）：** 原本地 TimesFM → 真实 `deepseek-flash` → 严格组合 → 原 Registry/Inbox/report/verify 已通过。Owner 追加授权的一次调用收到 1065/722 token，返回合法 100% 现金研究组合；两次授权合计估算 ¥0.015420，首次失败及预留保留。同一真实 Agent 共享 CNY ¥5/日、¥100/月（Asia/Shanghai），Fusion 已 OFF，Paper/Live 不开放。见[运行与状态](docs/M2_PR19.md)和[真实证据](docs/evidence/m2-pr19/README.md)。

- **M2-PR18 本地 TimesFM CPU（#69 / PR #70 已合并 / 默认 OFF）：** 固定官方 TimesFM 2.5 200M 权重与 CPU 依赖，按需 Python Worker 接原风险结果/Naive/EWMA；WSL2 Linux 隔离 4/4、真实 CPU 生产闭环及 16 点压力矩阵已实测；生产目标 N100 Linux，N100 验收仍 `NOT_VERIFIED`。不改变旧云路径或 Paper/Live 权限。见[运行与隔离边界](docs/M2_PR18.md)、[Linux 证据与回归限制](docs/evidence/m2-pr18/linux-r1/README.md)。

- **M2-PR17 DeepSeek HTTPS（#67 / 默认 OFF）：** 真实 API model 固定为 `deepseek-flash`，本模块内部默认 ID 为 `ds4.1flash`。复用原 Agent/CNY Budget 与 PR15 AST/PR62 离线评价；开发验证使用 recorded/loopback，真实请求为 `REAL_PROVIDER_NOT_RUN_OWNER_AUTHORIZATION_MISSING`，Paper/Live 仍 BLOCKED。见[操作与边界](docs/M2_PR17.md)和[测试证据](docs/evidence/m2-pr17/README.md)。

Owner 首次使用：在既有真实 CNY Agent 的 `settings.json` 手动填日/月 hard cap，复制[空配置](research/agent/deepseek-owner-config.example.json)到本机 ignored 目录，明确单次上限、DeepSeek 接收方、纯合成字段许可、密钥来源与已复核的价格期限；不要把 TST 账本换币种。依次运行 `scripts/autonomous-research.py configure`、`init --source authorized_cloud`、只读 `preflight`，核对字段说明/请求 SHA/最大预留；然后 `enable --opt-in APPROVE_ONE_SYNTHETIC_DEEPSEEK_REQUEST` 和 `once` 最多发一个真实请求。`disable` 停止后续外发，`status/history/report/verify` 只读审计；未知费用必须沿用原 Owner 发票核销，不能自动释放。[完整可复制命令](docs/M2_PR17.md#owner-操作)。以上为 PR17 原始交付状态；PR19 的新授权和唯一真实 Fusion 首验见上方最新记录。

- **历史 sidecar V2（本分支 Draft / #59）：** [M2-PR13](docs/M2_PR13.md) 使用现有 2000 积分 Tushare 账号执行四 API 五年历史回填；每 API 1212 日期已落地、共 6068 次请求，支持持久有界续传、版本查询与冻结锚点复权。[真实证据](docs/evidence/m2-pr13/README.md)；数据仅在本机、ex-post / coverage PARTIAL，不增加 PIT 或交易资格。
- **历史仓库 V1（PR #58 已合并）：** [M2-PR12](docs/M2_PR12.md) 提供独立 SQLite 证券目录、交易日历、未复权日线的预检/试采/有界回填、断点续传与只读查询。真实取得范围与缺口见[证据](docs/evidence/m2-pr12/README.md)；`historical_backfill_ex_post / PIT NOT_VERIFIED`，不增加前向或交易资格。
- **已实现：** Paper Risk Kernel、持久账本、六报告、真实历史 EOD 探索性回测、只观察的前向 EOD journal、[Web Dashboard V1](apps/dashboard/README.md)。
- **Agent V1 已在 main：** 持久任务、日/月预算、受控 Provider、本地 fake、EOD 去重及 [API](docs/AGENT_API.md)；真实 Provider **REAL_PROVIDER_NOT_VERIFIED**，未配置 Owner 预算/授权不付费。
- **候选链路已合并：** [M2-PR04 / PR #30](docs/M2_PR04.md) 提供登记 → 冻结 → 独立评价 → 隔离历史回放 CLI；#31 双线独立 PASS，研究证据不足、资格默认拒绝继续有效。
- **EOD 快照已合并：** [M2-PR05 / PR #33](docs/M2_PR05.md) 提供离线只读同步、持久研究快照、状态和消费 CLI。
- **Fake Agent 闭环已合并：** [M2-PR06 / PR #35](docs/M2_PR06.md) 接通显式快照 → 本地 Fake Agent 持久任务 → 候选研究来源；原快照手动路径不自动调度，scope 禁止云外发，资格默认拒绝。
- **EOD Auto / 审阅 / Shadow 已合并：** [PR #44](docs/M2_PR07.md)、[PR #46](docs/M2_PR08.md)、[PR #48](docs/M1_PR10.md) 提供本地 Fake 自动研究、人工模板审阅、固定 SMA5/20 只观察日志。
- **自动 EOD Operator 已合并（PR #50）：** [自动 EOD Operator V1](docs/M2_PR09.md) 一次配置/启用后，前台 watch 自动串起原采集器 → Snapshot → Shadow/可选 Fake。15:15 起检查，保留原 16:00 正式采集门槛；Windows 原生安全凭据、持久停用、原证据恢复和只读报告，默认 OFF。
- **公司行为证据已合并（PR #38）：** [证据包 V1](docs/M1_PR07B.md) 保留真实公告的 `FACTS_PARTIAL / historical_pit=NOT_VERIFIED`，没有真实历史准入。
- **现金分红模型已合并（PR #40）：** [CASH_DIVIDEND_V1](docs/M1_PR08.md) 完成隔离现金分红的登记→应收/税负→到账、统一 NAV/Risk、七报告和独立算法复算；旧 synthetic CLI、v3/68 日保持兼容。
- **历史分红桥接已合并（PR #42）：** [历史分红桥接 V1](docs/M1_PR09.md) 将原冻结行情、PR38 证据和显式模型假设接入 v4、原 SMA5/20、七报告及独立算法/双基准；实际运行 77 会话 **EXPLORATORY_EX_POST**，真实 PIT 新增 **0 天**，真实准入继续拒绝。
- **仍受阻：** 仅 68 个历史交易日、3 笔模拟成交，长窗口公司行为/费用证据 `DATA_BLOCKED`；真实 EOD 两日 `EOD_CONTINUITY_VERIFIED`，开盘源仍 BLOCKED，**尚无真正前向模拟成交或 NAV**。
- **当前顺序：** #74 交付真实历史 → 本地 TimesFM 核心闭环，单个 Draft 等待固定 HEAD 审查。后续预冻结样本外协议、积累前向 EOD；UI 在核心之后。见[当前状态](docs/STATUS.md)。
- **PR #56 审查修复：** 新链路须显式绑定已有 Owner AgentDir/配置，与旧 Agent 共用同一费用库，不再初始化第二个预算。预算修复已获源码复审确认；原 PR52/54 三套盘后完整回归 **10+4+13 项均 exit 0**，PR #56 后续已合并，原开发证据保留；见 [R1 证据](docs/evidence/m2-pr11/r1/README.md)。

## Windows 安装包（#85 Draft）

运行 `dist\installer\Stratide-Setup-0.3.0-x64.exe`（按用户安装，无需管理员）；详细步骤、升级/卸载和构建方式见 [WINDOWS_INSTALL](docs/WINDOWS_INSTALL.md)。安装包与 SHA256 的生成：

```powershell
pwsh -NoProfile -File scripts/build-windows-installer.ps1 -Version 0.3.0
```

以下为**旧版开发态启动示例**，需要源码、PowerShell 7、Node 与 Rust，不是安装产品。

在仓库根目录运行（以下为**合成测试数据**，不是实际市场收益）：

```powershell
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report'

# 验证 Agent 闭环：仅本地 fake / TST 合成费用。
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report' -AgentDir state/agent-fake -FakeAgent
```

浏览器打开 `http://127.0.0.1:8710`；Ctrl+C 停止。使用自己的已发布 Paper 六报告请参阅 [Dashboard 启动与数据说明](apps/dashboard/README.md)。Rust/CLI/观察工具见 [工程说明](docs/PAPER_TRADING_ROADMAP.md) 与 `scripts/README.md`。

## 团队与文档

- **Owner：** 范围、外发/费用许可和最终合并；**DeepSeek：** 当前 #85 的 Windows 安装、后台启动器、必要后端/脚本/首启配置/UI 全模块实施；**ChatGPT：** 固定 HEAD 审查和 Owner 授权后合并。此前 Sol/DeepSeek 的分工属于历史记录，见 [AGENTS.md](AGENTS.md)。
- [DeepSeek UI 交接规范](docs/UI_HANDOFF_DEEPSEEK.md) · [编码规则](AGENTS.md) · [产品原则](docs/PRODUCT.md) · [风险规范](docs/RISK_POLICY.md) · [历史 ADR](docs/adr/)。

**所有历史回放均不等于实时前向验证；不接入实盘券商。**
