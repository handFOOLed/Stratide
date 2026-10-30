# Stratide 当前状态

> 截至 2026-10-30，基于 `main` `34ab276`（[PR #28](https://github.com/handFOOLed/Stratide/pull/28)），附本分支 M2-PR04 开发自测状态。这是**当前实现快照**，不是实盘或独立验收承诺。Owner 已决定 **Core-first、UI-later**：后续核心功能先用 CLI/持久报告验收，最后由 Sol 按 PR #28 设计体系统一集成 UI。

## 已实现

| 领域 | 实际状态 | 证据 |
| --- | --- | --- |
| M0 Paper 内核 | Rust Risk Kernel、单账户 SQLite 事件账本、保守模拟撮合、确定性重放及六报告 | [PR #2](https://github.com/handFOOLed/Stratide/pull/2) / [#4](https://github.com/handFOOLed/Stratide/pull/4) / [#6](https://github.com/handFOOLed/Stratide/pull/6) |
| 真实来源前向 EOD | **observe-only** 独立 journal；现有证据 1 个有效前向观察日，0 策略提案/成交 | [PR #8](https://github.com/handFOOLed/Stratide/pull/8) / [#9](https://github.com/handFOOLed/Stratide/pull/9) |
| 历史探索性回测 | 600000.SH，2026-07-17—10-28，68 个交易日、3 笔模拟成交；初始 ¥100,000，末 NAV ¥99,966.51，**不是可交易盈利证据** | [PR #12](https://github.com/handFOOLed/Stratide/pull/12) |
| 研究评价 | 固定策略、时间隔离与成本/基准评价；研究结论 `INSUFFICIENT_EVIDENCE` | [PR #14](https://github.com/handFOOLed/Stratide/pull/14) |
| 历史数据阻断审计 | 三处价格连续性断点；缺公司行为及早期费用可信依据，长窗口 `DATA_BLOCKED`，新增支持日 0 | [PR #18](https://github.com/handFOOLed/Stratide/pull/18) |
| Web Dashboard V1 | **已合并**：127.0.0.1 本地只读 Rust API + Web 总览、持仓、订单/成交、资产表现；只读取 Owner 指定的已发布单份六报告，更新需重启 | [PR #21](https://github.com/handFOOLed/Stratide/pull/21) / [使用方法](../apps/dashboard/README.md) |
| Agent V1 | **已在 main**：持久研究任务、日/月 Budget Gate、受控文本 Provider、本机 fake、EOD 去重、API；含 PR #27 状态归因修复，真实 Provider 仍未验证 | [操作](M2_PR02.md) / [API](AGENT_API.md) |
| UI 视觉基准 | PR #28 已合并，确立设计体系；不代表全部核心功能完成 | [PR #28](https://github.com/handFOOLed/Stratide/pull/28) |

## 仍未实现 / 未验证

- **M2-PR04 本分支 Draft：** [候选 CLI](M2_PR04.md) 已实现登记 → 冻结 → 可信独立评价 → 隔离历史回放/拒绝报告。68 日样例 `ENGINEERING_PASS / RESEARCH_INSUFFICIENT`，长窗口 `DATA_BLOCKED`，资格 `ELIGIBILITY_DENIED`；开发自测不是另一审查者验收，未接入前向交易。见 [证据](evidence/m2-pr04/README.md)。
- **真实 Provider** 仍为 **REAL_PROVIDER_NOT_VERIFIED**；无 Owner 预算/接收方/数据范围授权不付费。既有 Agent 自测见 [证据](evidence/m2-pr02/README.md)。新增功能无需同步开发 UI，后续统一集成。
- **真正连续的前向 Paper 成交/NAV**：现有 forward 是 observe-only；[Issue #10](https://github.com/handFOOLed/Stratide/issues/10) 仍需新的真实观察和可信开盘/成本证据。历史回放不能计作 forward。
- **公司行为处理和历史 PIT 认证**：未完成；不能因审计 PASS 误称长窗口已贯通。真实券商、实盘资金、公共 Web、无人值守策略自动部署均未获授权。
- [PR #15](https://github.com/handFOOLed/Stratide/pull/15) 是尚未合并的 Q01–Q69 访谈**设计参考**，其中“Web/Agent 推迟到 paper 之后”的旧排序已被 Owner [Issue #19](https://github.com/handFOOLed/Stratide/issues/19) 取代。

## 当前执行顺序

1. **Sol / #29：** M2-PR04 核心候选冻结与隔离历史评价，交 Draft PR 和可复现实证，不开发 Dashboard。
2. **后续核心任务：** 由 Owner 另定；真正前向 Paper 仍受开盘/时间可得性和研究证据门槛约束，不因本次工程通过解锁。
3. **全部核心功能完成后：** Sol 按 PR #28 的设计体系统一集成全部 UI；旧同步 UI 要求被本 Owner 决定取代。

所有任务由 Owner 定范围。Sol/DeepSeek 不自行合并；ChatGPT 对固定 HEAD 做风险分级审查，Owner 明确批准后 SHA 锁定合并。高风险预算/凭据/财务改动需针对性独立反证；不将开发者自测冒充独立验收。流程现行补充见 [AGENTS.md](../AGENTS.md)，原 [ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 保留历史决策，待显式协调新版验收规则。
