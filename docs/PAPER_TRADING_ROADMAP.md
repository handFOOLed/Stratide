# Stratide Paper 阶段路线图（当前执行版）

> 2026-10-29；最新实现与数据边界见 [STATUS](STATUS.md)。旧各 PR 实施/验收细节仍保存在 `docs/M0_*.md`、`docs/M1_*.md`、`docs/M2_PR01.md` 与 `docs/evidence/`，**本页不重复过去的 Draft 状态或整页验收日志**。

## 已完成（已并入 main）

1. **M0 Paper Core**：[PR #2](https://github.com/handFOOLed/Stratide/pull/2)、[#4](https://github.com/handFOOLed/Stratide/pull/4)、[#6](https://github.com/handFOOLed/Stratide/pull/6)：单账户 Risk Kernel、模拟撮合、持久账本、回放和六报告。
2. **M1 已实现部分**：[PR #8](https://github.com/handFOOLed/Stratide/pull/8)、[#9](https://github.com/handFOOLed/Stratide/pull/9)、[#12](https://github.com/handFOOLed/Stratide/pull/12)、[#14](https://github.com/handFOOLed/Stratide/pull/14)、[#18](https://github.com/handFOOLed/Stratide/pull/18)：真实 EOD **observe-only**、68 日历史探索性回测、独立研究评价和长窗口 DATA_BLOCKED 调查。**M1 前向 Paper 成交仍未完成**。
3. **M2 Web V1**：[PR #21](https://github.com/handFOOLed/Stratide/pull/21)：localhost 同源只读 API 与可启动 Dashboard，Owner 指定一个已发布的报告快照；历史回放不进入前向账户 NAV。

## 当前和下一个完整功能包

| 顺序 | Owner/执行责任 | 任务 / DoD |
| --- | --- | --- |
| **当前 #22** | **Sol Max** | [自主研究 Agent V1](https://github.com/handFOOLed/Stratide/issues/22)：Provider、可信日/月 Budget Gate、授权、持久任务、取消/暂停、EOD 触发、API 与可操作基础 UI。未配置授权/预算不付费。不得触碰交易账本或假称独立策略通过。 |
| **随后 #23** | **DeepSeek** | [完整 Web UI/UX](https://github.com/handFOOLed/Stratide/issues/23)：先完成信息归属/设计系统，再实施五页共享组件、字体、按钮、动效、滚动条稳定布局；**去除跨页面重复资产模块和“查看更多”跳转**。详见 [DS 交接](UI_HANDOFF_DEEPSEEK.md)。 |
| **后续（尚未授权实现）** | Owner 再定范围 | 独立评价与 Paper-only 策略联动：候选冻结 → 独立 Evaluator → 可信 Risk/Ledger；继续 [#10](https://github.com/handFOOLed/Stratide/issues/10) 真正的前向观察与 [#17](https://github.com/handFOOLed/Stratide/issues/17) 数据缺口。 |

## 一直有效的边界

- **数据语义分离**：`synthetic_test` 是测试、`historical_replay` 是事后历史模拟、`forward_paper` 必须是实际时间推进的模拟成交。当前 forward 仅 observe-only，不能制造交易/净值。
- **研究与交易分权**：Agent 只有研究提案权，没有实盘/模拟账户写入权、风险设置权或独立准入权。平台不可因 UI 或模型故障放松金融安全。
- **版本与验收**：交可运行的 Draft PR，开发者附真实自测，ChatGPT 固定 HEAD 审查；预算/凭据/账本等高风险点做针对性独立反证，Owner 明确授权后才合并。当前补充见 [AGENTS](../AGENTS.md)，历史 [ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 尚待显式修订。
- **无真钱交易**：禁止券商委托、实盘、公开远程服务以及冒充真实交易资格。真实历史样本中的 68 日/3 笔成交不能证明收益优势。

**目标：一次交付完整的可使用功能，证据不够时敢于报告 BLOCKED。**
