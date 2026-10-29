# Stratide 当前状态

> 截至 2026-10-29，基于 `main` merge `527c4469`（[PR #24](https://github.com/handFOOLed/Stratide/pull/24)），附本分支 Agent Draft 状态。这是**当前实现快照**，不是实盘或独立验收承诺。

## 已实现

| 领域 | 实际状态 | 证据 |
| --- | --- | --- |
| M0 Paper 内核 | Rust Risk Kernel、单账户 SQLite 事件账本、保守模拟撮合、确定性重放及六报告 | [PR #2](https://github.com/handFOOLed/Stratide/pull/2) / [#4](https://github.com/handFOOLed/Stratide/pull/4) / [#6](https://github.com/handFOOLed/Stratide/pull/6) |
| 真实来源前向 EOD | **observe-only** 独立 journal；现有证据 1 个有效前向观察日，0 策略提案/成交 | [PR #8](https://github.com/handFOOLed/Stratide/pull/8) / [#9](https://github.com/handFOOLed/Stratide/pull/9) |
| 历史探索性回测 | 600000.SH，2026-07-17—10-28，68 个交易日、3 笔模拟成交；初始 ¥100,000，末 NAV ¥99,966.51，**不是可交易盈利证据** | [PR #12](https://github.com/handFOOLed/Stratide/pull/12) |
| 研究评价 | 固定策略、时间隔离与成本/基准评价；研究结论 `INSUFFICIENT_EVIDENCE` | [PR #14](https://github.com/handFOOLed/Stratide/pull/14) |
| 历史数据阻断审计 | 三处价格连续性断点；缺公司行为及早期费用可信依据，长窗口 `DATA_BLOCKED`，新增支持日 0 | [PR #18](https://github.com/handFOOLed/Stratide/pull/18) |
| Web Dashboard V1 | **已合并**：127.0.0.1 本地只读 Rust API + Web 总览、持仓、订单/成交、资产表现；只读取 Owner 指定的已发布单份六报告，更新需重启 | [PR #21](https://github.com/handFOOLed/Stratide/pull/21) / [使用方法](../apps/dashboard/README.md) |

## 仍未实现 / 未验证

- **Agent V1 本分支 Draft 已完成开发自测、尚未进入 main：** 持久任务、日/月预算、受控云文本路径、本地 fake、EOD 与基础 Web 交互可运行；[操作/API](M2_PR02.md) 和 [129 Rust / 4 前端 / 8 浏览器自测证据](evidence/m2-pr02/README.md) 已保存。真实 Provider **REAL_PROVIDER_NOT_VERIFIED**；同 HEAD 审查及付费/外发专项独立风险核查待完成。
- **正式 UI/UX**：现有 Web 仍是原生 JS/CSS/Vite 功能版；[Issue #23](https://github.com/handFOOLed/Stratide/issues/23) 由 **DeepSeek** 主导全站信息架构、字体、设计系统、共享组件与动画，待 Agent API 稳定后执行。见 [DeepSeek 交接说明](UI_HANDOFF_DEEPSEEK.md)。
- **真正连续的前向 Paper 成交/NAV**：现有 forward 是 observe-only；[Issue #10](https://github.com/handFOOLed/Stratide/issues/10) 仍需新的真实观察和可信开盘/成本证据。历史回放不能计作 forward。
- **公司行为处理和历史 PIT 认证**：未完成；不能因审计 PASS 误称长窗口已贯通。真实券商、实盘资金、公共 Web、无人值守策略自动部署均未获授权。
- [PR #15](https://github.com/handFOOLed/Stratide/pull/15) 是尚未合并的 Q01–Q69 访谈**设计参考**，其中“Web/Agent 推迟到 paper 之后”的旧排序已被 Owner [Issue #19](https://github.com/handFOOLed/Stratide/issues/19) 取代。

## 当前执行顺序

1. **Sol / #22：** Agent 功能闭环、权限、预算、持久任务、API 和风险测试；不负责视觉精修。
2. **DeepSeek / #23：** 在稳定 API 基础上统一整个 Web 的信息归属、组件、字体、按钮、动效和滚动布局。
3. **之后：** 研究候选 → 独立评价 → 风控约束的 **paper-only** 联动；数据不足则诚实 BLOCKED。

所有任务由 Owner 定范围。Sol/DeepSeek 不自行合并；ChatGPT 对固定 HEAD 做风险分级审查，Owner 明确批准后 SHA 锁定合并。高风险预算/凭据/财务改动需针对性独立反证；不将开发者自测冒充独立验收。流程现行补充见 [AGENTS.md](../AGENTS.md)，原 [ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 保留历史决策，待显式协调新版验收规则。
