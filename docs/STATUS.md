# Stratide 当前状态

**2026-11-04 Owner 决策（个人自用门限放宽）：** 本仓库是单人、非商业、本地 Paper/EOD 研究。权威口径是 [Issue #19 评论](https://github.com/handFOOLed/Stratide/issues/19#issuecomment-6623136559)，并见于 [#10](https://github.com/handFOOLed/Stratide/issues/10#issuecomment-6623136884) 与 [#17](https://github.com/handFOOLed/Stratide/issues/17#issuecomment-6623137271)。

**放宽**

- **T 日盘后研究 / T+1 Paper：** T 日盘后取得并校验的 T 日 `daily.open` 可作为 T 日已知历史输入，供 T 日盘后研究并冻结 T+1 意图；T 日 open **不是** T+1 成交价。若采用 T+1 `daily.open` 作为 Paper 成交价假设，须 T+1 盘后取得该字段，按 T 日已冻结的意图、数量和撮合规则事后确认，标记 `EX_POST_OPEN_ASSUMPTION`，不得看过 T+1 数据后选择性下单、撤单或改价，也不能冒充开盘实收。现金、费用、停牌及唯一 Risk→Execution→Ledger 逐笔校验保持。 `stk_auction` 是可选增强，不挡工程实现。
- [#10](https://github.com/handFOOLed/Stratide/issues/10) 与 [#17](https://github.com/handFOOLed/Stratide/issues/17) 继续如实保留 `BLOCKED` / `NOT_VERIFIED` 和缺口，但**不再挡住工程合并、V1 收尾 PR 或 Dashboard 集成**。它们只挡住「宣称已验证可交易 / PIT 已过 / 开盘流已实收」。
- 个人模式下，大包脱敏证据、先红后绿全套、强制固定 HEAD 外部审查改为**可选**。日常合入以 Owner 本地相关绿测加简短说明为准。预算、外发、账本安全改动仍建议保留针对性反证。

**不放宽：** 真实行情或真实风险结果及派生摘要禁止外发 DeepSeek（`REAL_MARKET_DATA_EGRESS_DENIED`）。Agent 预算硬帽为 CNY ¥5/日、¥100/月（Asia/Shanghai）。无实盘券商、无真钱下单。Paper ≠ Live。

M2-PR20 / #74 已由 PR #75 并入 `main d557aa1`。下方 R1/R2 段落保留合并前记录；其中「待固定 HEAD 复审」不再是个人模式的日常合并硬门槛。

**2026-11-04 / PR #75 R2：** 修复 Rust historical 当日收盘的盘后时点门禁；上海 16:00 边界和日期/时区一致性反证通过。历史 13/13、research Rust 71/71、旧 CPU 11 pass + 1 skip；真实 task 9 / Registry / report/verify 通过，0 新云/行情调用。[R2 证据](evidence/m2-pr20/r2/README.md)。保持 Draft，待固定 HEAD 复审。

**2026-11-04 / PR #75 R1：** 历史模型 pin、完整纯 UNKNOWN opportunities、版本/未用字段已严格校验；来源索引改为证券+日期引用原 SHA，真实三证券 252 条来源绑定与 task 8 复核通过。57 个重算 SHA 反例先红后绿，历史套件 12/12、Rust 204/204，预算/授权/真实外发边界保持。[修复证据](evidence/m2-pr20/r1/README.md)。仍为 Draft，待新固定 HEAD 复审，未 Ready/merge。

**2026-11-03 / #74 / M2-PR20（本分支 Draft）：** 基于最新 main `971eb4ba90507142b1d32ca80af2d15859790933`（含已合并 PR #60/#70/#72），[真实历史 → 本地 TimesFM](M2_PR20.md) 已实际跑通三证券 84 会话 → CPU → 原 Agent task 6 / Registry / report/verify。真实因子变化与缺口样本 BLOCKED；原 calls/预算/授权未变，新市场请求/云调用/计费为 0，真实风险外发 `REAL_MARKET_DATA_EGRESS_DENIED`。数据仍 PARTIAL、PIT 未验证，Paper/Live 禁止，N100 未验收。[本期开发证据](evidence/m2-pr20/README.md)。以下旧条目保留其发生时的状态，本段是当前增量。

**2026-11-03 / #69 / PR #70 Linux R1：** 基于最新 main `b62c1171d8503e1f21e4b470847944c6fbe8dbf4`（PR #68 已合并），新增 [M2-PR18 本地 TimesFM 2.5 CPU](M2_PR18.md)，默认 OFF、独立 Worker、原任务/RiskExpertResult/Naive/EWMA，无新增计费或交易权限。开发/真实模型/Linux/N100 的实际验证状态分别记录于 [m2-pr18 evidence](evidence/m2-pr18/README.md)，N100 尚未验收；本分支保持 Draft。WSL2 Ubuntu ext4 已完成 Linux 隔离 4/4、0 skipped，真实 CPU 生产闭环、calls=0 与 Linux 16 点压力矩阵；[R1 命令/指标/回归限制](evidence/m2-pr18/linux-r1/README.md)。下方既有模块开发证据保留。

> 截至 2026-11-03，基于开始时最新 `main e24f30f69b12fa303221ccd4fc6b8ea9084dc989`，PR #66 已合并；附本分支 #67 DeepSeek HTTPS 开发状态。这是当时的实现快照，不是实盘承诺。当日的 **Core-first、UI-later** 指核心功能先用 CLI/持久报告验收，视觉基准为 PR #28。2026-11-04 起，#10/#17 不挡 Dashboard 集成，合入门槛以本页顶部为准。

## 已实现

| 领域 | 实际状态 | 证据 |
| --- | --- | --- |
| M2-PR20 真实历史本地风险（PR #75 已合并） | #74：显式 1–8 证券、前缀冻结/单位/版本/来源与质量，原 TimesFM CPU/任务/Registry；真实正常与拒绝样本及零云调用验证。ENGINEERING_PASS，PIT、样本外优势、开盘流实收与已验证可交易资格不升级 | [操作](M2_PR20.md) / [证据](evidence/m2-pr20/README.md) |
| M2-PR17 DeepSeek HTTPS（本分支 Draft） | #67：`ds4.1flash` → 官方 `deepseek-flash`；原 CNY Agent/Budget、受控密钥、纯合成输入、显式一次开关、PR15/PR62 研究闭环。默认 OFF；本次真实请求 `REAL_PROVIDER_NOT_RUN_OWNER_AUTHORIZATION_MISSING`，0 实际费用/真实密钥正文读取/新行情，不解锁 Paper/Live | [操作](M2_PR17.md) / [开发证据](evidence/m2-pr17/README.md) |
| M2-PR16 云端结构化提案接线（PR #66 已合并） | #65：显式 recorded source → 原 Owner Rust 任务/统一预算 → PR15 强类型 AST/冻结/归档 → PR62 多候选三成本；loopback、预算/撤销/取消/崩溃/未知和篡改反证。该期真实 Provider BLOCKED，0 外发/付费/新行情/Token，不解锁交易 | [契约/操作](M2_PR16.md) / [原开发证据](evidence/m2-pr16/README.md) |
| M2-PR15 自主策略研究闭环（PR #64 已合并） | #63：受限 AST、本地确定性四类提案、冻结实验与开发段反馈、PR62 同源多候选评测和匹配基准、持久失败/恢复及只读研究 Inbox 契约。原真实五年运行与开发证据保留；0 新行情/Token/云模型/付费，不解锁交易 | [契约/操作](M2_PR15.md) / [原开发证据](evidence/m2-pr15/README.md) |
| M2-PR14 多股票历史研究 V1（PR #62 已合并） | #61：只读处理 1212 会话 / 25569182 规范行，实测 5774 代码、5387 代码曾入研究子集；三策略/三基准、三成本情景及重置 Walk-forward，541 秒 / 267.5 MiB，12 项定向自测。三规则未建立相对等权优势；历史 PIT、可成交性仍未验证，研究指数不是账户 NAV 或 Paper/Live 准入 | [契约/操作](M2_PR14.md) / [原开发证据](evidence/m2-pr14/README.md) |
| M2-PR13 历史 sidecar V2（PR #60 已合并） | #59：2000 积分现有账号，四接口各 1212 日期已落地，6068 次原请求；因子 1212 日旧 PARTIAL 标签保留且不再推断数字 cap，限价 33 日 PARTIAL。历史市场覆盖仍未验证；持久预算/断点续传、只读版本查询和冻结锚点复权 | [契约/操作](M2_PR13.md) / [实际证据](evidence/m2-pr13/README.md) / [增量修复](evidence/m2-pr13/r1/README.md) |
| M2-PR12 历史仓库 V1（PR #58 已合并） | #57：独立本地证券目录/日历/未复权日线；1212 日期、6347781 行，1201 COMPLETE / 11 PARTIAL。历史身份/BSE 日历/PIT 仍未核实；4.54 GB 本地旧库保留 | [契约/操作](M2_PR12.md) / [实际证据](evidence/m2-pr12/README.md) |
| M0 Paper 内核 | Rust Risk Kernel、单账户 SQLite 事件账本、保守模拟撮合、确定性重放及六报告 | [PR #2](https://github.com/handFOOLed/Stratide/pull/2) / [#4](https://github.com/handFOOLed/Stratide/pull/4) / [#6](https://github.com/handFOOLed/Stratide/pull/6) |
| 真实来源前向 EOD | **observe-only** 独立 journal；10/28、10/29 两个有效日，`EOD_CONTINUITY_VERIFIED`；0 策略提案/成交 | [#10 独立结论](https://github.com/handFOOLed/Stratide/issues/10#issuecomment-6512598875) |
| 历史探索性回测 | 600000.SH，2026-07-17—10-28，68 个交易日、3 笔模拟成交；初始 ¥100,000，末 NAV ¥99,966.51，**不是可交易盈利证据** | [PR #12](https://github.com/handFOOLed/Stratide/pull/12) |
| 研究评价 | 固定策略、时间隔离与成本/基准评价；研究结论 `INSUFFICIENT_EVIDENCE` | [PR #14](https://github.com/handFOOLed/Stratide/pull/14) |
| 历史数据阻断审计 | 三处价格连续性断点；缺公司行为及早期费用可信依据，长窗口 `DATA_BLOCKED`，新增支持日 0 | [PR #18](https://github.com/handFOOLed/Stratide/pull/18) |
| Web Dashboard V1 | **已合并**：127.0.0.1 本地只读 Rust API + Web 总览、持仓、订单/成交、资产表现；只读取 Owner 指定的已发布单份六报告，更新需重启 | [PR #21](https://github.com/handFOOLed/Stratide/pull/21) / [使用方法](../apps/dashboard/README.md) |
| Agent V1 | **已在 main**：持久研究任务、日/月 Budget Gate、受控文本 Provider、本机 fake、EOD 去重、API；含 PR #27 状态归因修复，真实 Provider 仍未验证 | [操作](M2_PR02.md) / [API](AGENT_API.md) |
| UI 视觉基准 | PR #28 已合并，确立设计体系；不代表全部核心功能完成 | [PR #28](https://github.com/handFOOLed/Stratide/pull/28) |
| 候选冻结与历史评价 | PR #30 已合并；#31 A/B 双线分别独立 PASS；研究不足、长窗口 DATA_BLOCKED 和资格默认拒绝继续有效 | [#31 最终 B 结论](https://github.com/handFOOLed/Stratide/issues/31#issuecomment-6512910618) / [操作](M2_PR04.md) |
| EOD 研究快照 | PR #33 已合并，#32 完成；既有 observer 离线只读核验、原子持久发布、状态与只读消费 | [操作](M2_PR05.md) / [原自测](evidence/m2-pr05/README.md) |
| 显式 Fake Agent 闭环 | PR #35 已合并；EOD 快照 → 本地 fake 持久任务 → 候选研究来源；原手动路径不自动调度，scope 禁止云 Provider，资格默认拒绝 | [操作](M2_PR06.md) / [原自测](evidence/m2-pr06/README.md) |
| EOD 自动研究与归档（PR #44 已合并） | Owner 本机 opt-in，默认 OFF，前台 once/watch、原 Agent 唯一日任务/fake 调用、同源跨实例归属、自动候选归档和恢复；LOCAL_FAKE_ONLY / RESEARCH_ONLY | [操作](M2_PR07.md) / [自测](evidence/m2-pr07/README.md) |
| 候选审阅与评价闭环（PR #46 已合并） | #45：只读 Inbox → Owner 显式固定模板关联 → 原 freeze/evaluate → 持久可复核报告；含 DATA_BLOCKED、内容复用及四节点恢复；68 日研究不足、资格始终拒绝 | [操作](M2_PR08.md) / [自测](evidence/m2-pr08/README.md) |
| Forward EOD Shadow V1（PR #48 已合并） | #47：Owner 本地启停、固定 SMA5/20、来源/时点门禁、唯一不可回填日志与只读复算；原双目录 22 日 synthetic E2E / 并发 / 三节点恢复证据保留；旧真实源日预热不足 | [操作](M1_PR10.md) / [原自测](evidence/m1-pr10/README.md) |
| 自动 EOD Operator V1（PR #50 已合并） | #49：一次配置/启用，前台每日采集 → Snapshot → Shadow/可选 Fake、原证据恢复、持久停用及只读审计；15:15 检查、16:00 正式采集的授权回退分支，未知/失败槽不重发 | [操作](M2_PR09.md) / [原证据](evidence/m2-pr09/README.md) |
| Time-Series + Fusion V1（PR #52 已合并） | #51：原 Snapshot 冻结 → Naive/EWMA + 独立可替换本地时序 Adapter → 原 Rust Agent/Budget Fusion fake → 原 Registry/Inbox；双 25 日 synthetic E2E。精确任务领取、实际任务 reserve/dispatch 来源复核及失效 queued 终态已并入 main `1b2c903`。默认 OFF，真实时序/云未授权 | [操作/边界](M2_PR10.md) / [原开发自测](evidence/m2-pr10/README.md) / [P1 修复证据](evidence/m2-pr10/p1/README.md) |
| M1-PR11 前向研究资格 V1（PR #54 已合并） | #53：原 observer/PR33/PR38 只读 → 当日公司行为覆盖证据 → 逐日 21 会话收据 → 原 PR52 实际任务双门禁；完整 synthetic 正反 E2E。真实仍只有两日且缺 feed 覆盖/已过期，结果 BLOCKED；研究资格最多 ALLOW_RESEARCH_ONLY，历史 PIT 和交易权限不提升 | [契约/CLI](M1_PR11.md) / [原自测及真实审计](evidence/m1-pr11/README.md) |
| Cloud Risk Expert + Autonomous Portfolio V1（PR #56 已合并） | #55：BigQuery TimesFM 2.5 + DeepSeek flash 的生产请求/解析、原 Rust 任务与统一预算、Naive/EWMA、严格股票/现金目标组合及原 Registry/Inbox。recorded/loopback 三股票及全现金合成闭环；无真实云调用，真实数据与 BigQuery 费用上界仍 BLOCKED | [契约/CLI](M2_PR11.md) / [开发自测](evidence/m2-pr11/README.md) |

| 现金分红模型 V1（PR #40 已合并） | 登记权益→应收/扣税负债→到账，ledger v4 / NAV / Risk / 七报告 / Python独立算法 / 双基准；仅隔离 synthetic CLI | [CASH_DIVIDEND_V1](M1_PR08.md) / [原自测](evidence/m1-pr08/README.md) |
| 历史分红情景桥接 V1（PR #42 已合并） | 原冻结历史行情 + PR38 原证据 + 独立假设 → 原 SMA5/20 / v4 / 七报告 / 独立算法 / 双基准；77 会话 EXPLORATORY_EX_POST，真实准入 DENIED、PIT 新增 0 天 | [模块操作](M1_PR09.md) / [原自测](evidence/m1-pr09/README.md) |

## 仍未实现 / 未验证

- **M1-PR07B / PR #38 已合并：** [公司行为证据包](M1_PR07B.md) 保留真实 12/19 字段和 `FACTS_PARTIAL / historical_pit=NOT_VERIFIED / ELIGIBILITY_DENIED`。原证据中的 `ACCOUNTING_NOT_IMPLEMENTED` 是冻结历史快照；PR #40 已实现隔离现金分红模型，真实账户税务、到账、递延负债、PIT 和开盘仍未验证。
- **真实 Provider**：PR #72 已验证显式授权的 synthetic 风险 → DeepSeek；本期只读复验原成功 task 4。真实市场/账户数据外发仍未授权，本地历史任务明确拒绝。新增功能无需同步 UI。
- **真正连续的前向 Paper 成交/NAV**：现有两日 forward 仍是 observe-only，尚无连续前向模拟成交或账户 NAV。历史回放不能计作 forward，EOD 连续性 PASS 不等于 M1 完成。自本页顶部 2026-11-04 决策起，EOD Paper 工程可以用次日 `daily.open` 作为默认成交假设继续实现和合并，不必等待 `stk_auction` 权限。[#10](https://github.com/handFOOLed/Stratide/issues/10) 的 `OPENING_SOURCE=BLOCKED / NOT_VERIFIED` 继续保留，只阻止宣称开盘流已实收或已验证可交易。
- **真实公司行为处理和历史 PIT 认证**：未完成。[#17](https://github.com/handFOOLed/Stratide/issues/17) 的公司行为 / 历史 PIT / 早期费用继续 `DATA_BLOCKED` / `NOT_VERIFIED`；隔离模型通过不能把历史长窗口写成已验证可交易。该 Issue 不挡住工程合并或 V1 收尾。真实券商、实盘资金、公共 Web、无人值守策略自动部署均未获授权。
- [PR #15](https://github.com/handFOOLed/Stratide/pull/15) 是尚未合并的 Q01–Q69 访谈**设计参考**，其中“Web/Agent 推迟到 paper 之后”的旧排序已被 Owner [Issue #19](https://github.com/handFOOLed/Stratide/issues/19) 取代。

## 当前执行顺序

1. **Paper 时点：** T 日盘后取得并校验的 T 日 `daily.open` 可作为 T 日已知历史输入，供 T 日盘后研究并冻结 T+1 意图；T 日 open **不是** T+1 成交价。若采用 T+1 `daily.open` 作为 Paper 成交价假设，须 T+1 盘后取得该字段，按 T 日已冻结的意图、数量和撮合规则事后确认，标记 `EX_POST_OPEN_ASSUMPTION`，不得看过 T+1 数据后选择性下单、撤单或改价，也不能冒充开盘实收。现金、费用、停牌及唯一 Risk→Execution→Ledger 逐笔校验保持。
2. **最新开发顺序：** [#76](https://github.com/handFOOLed/Stratide/issues/76) 研究评价/Prompt（[PR #78](https://github.com/handFOOLed/Stratide/pull/78) 审查中）→ 合并后 [#77](https://github.com/handFOOLed/Stratide/issues/77) Dashboard/Agent/审批通知/N100 部署。#10/#17 的缺口保持，但不阻塞工程合入。
3. **个人模式合入：** Owner 本地相关绿测＋简短说明；固定 HEAD 外部审查、大包脱敏证据和先红后绿全套可选。预算、外发、凭据与 Risk/Ledger 安全变更仍建议针对性反证，实现者不得自行合并。
4. **仍待真实验证：** PIT、开盘实收、已验证可交易性及 N100 真机保持 `NOT_VERIFIED`；PR #28 是视觉参考，不指定 UI/UX 负责人。

所有任务由 Owner 定范围。不得把开发者自测写成独立验收。`REAL_MARKET_DATA_EGRESS_DENIED`、CNY ¥5/日、¥100/月与 Paper-only 保持有效。流程见 [AGENTS.md](../AGENTS.md)。[ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 保留历史决策，本页不静默改写该 ADR。
