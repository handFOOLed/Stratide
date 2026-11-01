# Stratide 当前状态

> 截至 2026-11-01，基于已核验 `main` `c3904a5eb31f40209b32beba559e82ba4e47fd8a`（[PR #50](https://github.com/handFOOLed/Stratide/pull/50) 已合并），附本分支 #51 Time-Series + Fusion V1 开发状态。这是**当前实现快照**，不是实盘承诺。Owner 已决定 **Core-first、UI-later**：后续核心功能先用 CLI/持久报告验收，最后由 Sol 按 PR #28 设计体系统一集成 UI。

## 已实现

| 领域 | 实际状态 | 证据 |
| --- | --- | --- |
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
| Time-Series + Fusion V1（本分支 Draft） | #51：原 Snapshot 冻结 → Naive/EWMA + 独立可替换本地时序 Adapter → 原 Rust Agent/Budget Fusion fake → 原 Registry/Inbox；25 日 synthetic 双 E2E、数值复算、并发与四阶段恢复。默认 OFF；真实时序/云模型未配置，真实 forward 不足时拒绝 | [操作/边界](M2_PR10.md) / [开发自测](evidence/m2-pr10/README.md) |

| 现金分红模型 V1（PR #40 已合并） | 登记权益→应收/扣税负债→到账，ledger v4 / NAV / Risk / 七报告 / Python独立算法 / 双基准；仅隔离 synthetic CLI | [CASH_DIVIDEND_V1](M1_PR08.md) / [原自测](evidence/m1-pr08/README.md) |
| 历史分红情景桥接 V1（PR #42 已合并） | 原冻结历史行情 + PR38 原证据 + 独立假设 → 原 SMA5/20 / v4 / 七报告 / 独立算法 / 双基准；77 会话 EXPLORATORY_EX_POST，真实准入 DENIED、PIT 新增 0 天 | [模块操作](M1_PR09.md) / [原自测](evidence/m1-pr09/README.md) |

## 仍未实现 / 未验证

- **M1-PR07B / PR #38 已合并：** [公司行为证据包](M1_PR07B.md) 保留真实 12/19 字段和 `FACTS_PARTIAL / historical_pit=NOT_VERIFIED / ELIGIBILITY_DENIED`。原证据中的 `ACCOUNTING_NOT_IMPLEMENTED` 是冻结历史快照；PR #40 已实现隔离现金分红模型，真实账户税务、到账、递延负债、PIT 和开盘仍未验证。
- **真实 Provider** 仍为 **REAL_PROVIDER_NOT_VERIFIED**；无 Owner 预算/接收方/数据范围授权不付费。既有 Agent 自测见 [证据](evidence/m2-pr02/README.md)。新增功能无需同步开发 UI，后续统一集成。
- **真正连续的前向 Paper 成交/NAV**：现有两日 forward 是 observe-only；#47 只增加 NO_ORDERS Shadow 模块，真实 21 日观察尚未累积。[#10](https://github.com/handFOOLed/Stratide/issues/10) 的 `OPENING_SOURCE=BLOCKED / NOT VERIFIED`，可信开盘/费用门槛未解锁。历史回放不能计作 forward，EOD 连续性 PASS 不等于 M1 完成。
- **真实公司行为处理和历史 PIT 认证**：未完成；隔离模型通过不能开放真实历史长窗口。真实券商、实盘资金、公共 Web、无人值守策略自动部署均未获授权。
- [PR #15](https://github.com/handFOOLed/Stratide/pull/15) 是尚未合并的 Q01–Q69 访谈**设计参考**，其中“Web/Agent 推迟到 paper 之后”的旧排序已被 Owner [Issue #19](https://github.com/handFOOLed/Stratide/issues/19) 取代。

## 当前执行顺序

1. **Sol / #51：** Time-Series + Fusion 完整 Core 模块；`agents=0`，唯一 Draft 待固定 HEAD 审查，Owner 明确许可前不 Ready/合并。新 scope 仅本地 fake，未授权真实付费/数据外发/交易。
2. **后续核心任务：** Owner 再定范围；真实公司行为/PIT/开盘及多模型真实供应商仍未验证。[#36](https://github.com/handFOOLed/Stratide/issues/36) 的完整多模态消融尚未实现，本分支只覆盖时序与 Fusion 核心 V1。
3. **全部核心功能完成后：** Sol 按 PR #28 的设计体系统一集成全部 UI；旧同步 UI 要求被本 Owner 决定取代。

所有任务由 Owner 定范围。Sol/DeepSeek 不自行合并；ChatGPT 对固定 HEAD 做风险分级审查，Owner 明确批准后 SHA 锁定合并。高风险预算/凭据/财务改动需针对性独立反证；不将开发者自测冒充独立验收。流程现行补充见 [AGENTS.md](../AGENTS.md)，原 [ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 保留历史决策，待显式协调新版验收规则。
