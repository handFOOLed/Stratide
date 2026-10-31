# Stratide 当前状态

> 截至 2026-10-31，基于 `main` `a522c2925ac3163358bb2b32c84119f2a3ef4a3f`（[PR #35](https://github.com/handFOOLed/Stratide/pull/35) 已合并），附本分支 #37 公司行为证据包自测状态。这是**当前实现快照**，不是实盘承诺。Owner 已决定 **Core-first、UI-later**：后续核心功能先用 CLI/持久报告验收，最后由 Sol 按 PR #28 设计体系统一集成 UI。

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
| 显式 Fake Agent 闭环 | PR #35 已合并；EOD 快照 → 本地 fake 持久任务 → 候选研究来源；新 scope 禁止云 Provider 与自动 EOD，资格默认拒绝 | [操作](M2_PR06.md) / [原自测](evidence/m2-pr06/README.md) |

## 仍未实现 / 未验证

- **M1-PR07B / #37 本分支 Draft：** [离线证据包](M1_PR07B.md) 已取得巨潮原始实施公告并实际运行 `audit/status`：12/19 字段有原文支持，事件事实 `FACTS_PARTIAL`，历史 PIT `NOT_VERIFIED`，共享会计 `NOT_IMPLEMENTED`。断点日期和已取金额只作一致性核对；`historical_replay_eligible=false / ELIGIBILITY_DENIED`。Sol 单人自测及旧文件保全见 [证据](evidence/m1-pr07b/README.md)，等待固定 HEAD 审查和 Owner 合并授权。
- **真实 Provider** 仍为 **REAL_PROVIDER_NOT_VERIFIED**；无 Owner 预算/接收方/数据范围授权不付费。既有 Agent 自测见 [证据](evidence/m2-pr02/README.md)。新增功能无需同步开发 UI，后续统一集成。
- **真正连续的前向 Paper 成交/NAV**：现有两日 forward 是 observe-only；[#10](https://github.com/handFOOLed/Stratide/issues/10) 的 `OPENING_SOURCE=BLOCKED / NOT VERIFIED`，可信开盘/费用门槛未解锁。历史回放不能计作 forward，EOD 连续性 PASS 不等于 M1 完成。
- **公司行为处理和历史 PIT 认证**：未完成；不能因审计 PASS 误称长窗口已贯通。真实券商、实盘资金、公共 Web、无人值守策略自动部署均未获授权。
- [PR #15](https://github.com/handFOOLed/Stratide/pull/15) 是尚未合并的 Q01–Q69 访谈**设计参考**，其中“Web/Agent 推迟到 paper 之后”的旧排序已被 Owner [Issue #19](https://github.com/handFOOLed/Stratide/issues/19) 取代。

## 当前执行顺序

1. **Sol / #37：** 公司行为源证据包 V1；独立开发、自测、Draft PR；不改账本、不扩展窗口。#34 / PR #35 已完成并在 main。
2. **后续核心任务：** 公司行为会计须另行授权；[#36](https://github.com/handFOOLed/Stratide/issues/36) 是未来多模型研究提案。真正前向 Paper 仍受开盘/时间可得性和研究证据门槛约束。
3. **全部核心功能完成后：** Sol 按 PR #28 的设计体系统一集成全部 UI；旧同步 UI 要求被本 Owner 决定取代。

所有任务由 Owner 定范围。Sol/DeepSeek 不自行合并；ChatGPT 对固定 HEAD 做风险分级审查，Owner 明确批准后 SHA 锁定合并。高风险预算/凭据/财务改动需针对性独立反证；不将开发者自测冒充独立验收。流程现行补充见 [AGENTS.md](../AGENTS.md)，原 [ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 保留历史决策，待显式协调新版验收规则。
