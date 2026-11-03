# Stratide 当前状态

**2026-11-03 / #74 / M2-PR20（本分支 Draft）：** 基于最新 main `971eb4ba90507142b1d32ca80af2d15859790933`（含已合并 PR #60/#70/#72），[真实历史 → 本地 TimesFM](M2_PR20.md) 已实际跑通三证券 84 会话 → CPU → 原 Agent task 6 / Registry / report/verify。真实因子变化与缺口样本 BLOCKED；原 calls/预算/授权未变，新市场请求/云调用/计费为 0，真实风险外发 `REAL_MARKET_DATA_EGRESS_DENIED`。数据仍 PARTIAL、PIT 未验证，Paper/Live 禁止，N100 未验收。[本期开发证据](evidence/m2-pr20/README.md)。以下旧条目保留其发生时的状态，本段是当前增量。

**2026-11-03 / #69 / PR #70 Linux R1：** 基于最新 main `b62c1171d8503e1f21e4b470847944c6fbe8dbf4`（PR #68 已合并），新增 [M2-PR18 本地 TimesFM 2.5 CPU](M2_PR18.md)，默认 OFF、独立 Worker、原任务/RiskExpertResult/Naive/EWMA，无新增计费或交易权限。开发/真实模型/Linux/N100 的实际验证状态分别记录于 [m2-pr18 evidence](evidence/m2-pr18/README.md)，N100 尚未验收；本分支保持 Draft。WSL2 Ubuntu ext4 已完成 Linux 隔离 4/4、0 skipped，真实 CPU 生产闭环、calls=0 与 Linux 16 点压力矩阵；[R1 命令/指标/回归限制](evidence/m2-pr18/linux-r1/README.md)。下方既有模块开发证据保留。

> 截至 2026-11-03，基于开始时最新 `main e24f30f69b12fa303221ccd4fc6b8ea9084dc989`，PR #66 已合并；附本分支 #67 DeepSeek HTTPS 开发状态。这是**当前实现快照**，不是实盘承诺。Owner 已决定 **Core-first、UI-later**：后续核心功能先用 CLI/持久报告验收，最后按 PR #28 设计体系统一集成 UI。

## 已实现

| 领域 | 实际状态 | 证据 |
| --- | --- | --- |
| M2-PR20 真实历史本地风险（本分支 Draft） | #74：显式 1–8 证券、前缀冻结/单位/版本/来源与质量，原 TimesFM CPU/任务/Registry；真实正常与拒绝样本及零云调用验证。ENGINEERING_PASS，PIT/样本外优势/前向资格不升级 | [操作](M2_PR20.md) / [证据](evidence/m2-pr20/README.md) |
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
- **真正连续的前向 Paper 成交/NAV**：现有两日 forward 是 observe-only；#47 只增加 NO_ORDERS Shadow 模块，真实 21 日观察尚未累积。[#10](https://github.com/handFOOLed/Stratide/issues/10) 的 `OPENING_SOURCE=BLOCKED / NOT VERIFIED`，可信开盘/费用门槛未解锁。历史回放不能计作 forward，EOD 连续性 PASS 不等于 M1 完成。
- **真实公司行为处理和历史 PIT 认证**：未完成；隔离模型通过不能开放真实历史长窗口。真实券商、实盘资金、公共 Web、无人值守策略自动部署均未获授权。
- [PR #15](https://github.com/handFOOLed/Stratide/pull/15) 是尚未合并的 Q01–Q69 访谈**设计参考**，其中“Web/Agent 推迟到 paper 之后”的旧排序已被 Owner [Issue #19](https://github.com/handFOOLed/Stratide/issues/19) 取代。

## 当前执行顺序

1. **Sol / #74：** 真实历史数据与质量 → 本地 TimesFM 核心闭环，单个 Draft PR；开发者验证已完成，等待固定 HEAD 审查与 Owner 明确合并授权。
2. **后续独立 Issue：** 预冻结样本外协议并比较 Naive/EWMA；继续真实前向 EOD。历史 PIT、公司行为、开盘与 N100 真机限制保留。
3. **核心完成后：** 再按 PR #28 设计统一集成 UI，本期不改 Dashboard。

所有任务由 Owner 定范围。Sol/DeepSeek 不自行合并；ChatGPT 对固定 HEAD 做风险分级审查，Owner 明确批准后 SHA 锁定合并。高风险预算/凭据/财务改动需针对性独立反证；不将开发者自测冒充独立验收。流程现行补充见 [AGENTS.md](../AGENTS.md)，原 [ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 保留历史决策，待显式协调新版验收规则。
