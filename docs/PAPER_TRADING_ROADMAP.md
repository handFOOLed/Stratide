# Stratide Paper 阶段路线图（当前执行版）

> 2026-10-30；最新实现与数据边界见 [STATUS](STATUS.md)。Owner 已决定 **Core-first、UI-later**：后续核心功能不要求同期 Dashboard/UI，最终由 Sol 按已合并 PR #28 的视觉基准统一集成。旧各 PR 实施/验收细节仍保存在 `docs/M0_*.md`、`docs/M1_*.md`、`docs/M2_PR01.md` 与 `docs/evidence/`。

## 已完成（已并入 main）

1. **M0 Paper Core**：[PR #2](https://github.com/handFOOLed/Stratide/pull/2)、[#4](https://github.com/handFOOLed/Stratide/pull/4)、[#6](https://github.com/handFOOLed/Stratide/pull/6)：单账户 Risk Kernel、模拟撮合、持久账本、回放和六报告。
2. **M1 已实现部分**：[PR #8](https://github.com/handFOOLed/Stratide/pull/8)、[#9](https://github.com/handFOOLed/Stratide/pull/9)、[#12](https://github.com/handFOOLed/Stratide/pull/12)、[#14](https://github.com/handFOOLed/Stratide/pull/14)、[#18](https://github.com/handFOOLed/Stratide/pull/18)：真实 EOD **observe-only**、68 日历史探索性回测、独立研究评价和长窗口 DATA_BLOCKED 调查。**M1 前向 Paper 成交仍未完成**。
3. **M2 Web V1**：[PR #21](https://github.com/handFOOLed/Stratide/pull/21)：localhost 同源只读 API 与可启动 Dashboard，Owner 指定一个已发布的报告快照；历史回放不进入前向账户 NAV。
4. **Agent V1 与视觉基准**：#22 核心及 PR #27 状态修复已在 main；[PR #28](https://github.com/handFOOLed/Stratide/pull/28) 确立视觉基准，不代表功能全部完成。真实 Provider 未验证。
5. **M2-PR04 候选链路**：[PR #30](https://github.com/handFOOLed/Stratide/pull/30) 已合并于 `05ab0b9`；[#31](https://github.com/handFOOLed/Stratide/issues/31#issuecomment-6512910618) A/B 双线独立 PASS。真实两日 `EOD_CONTINUITY_VERIFIED`；`OPENING_SOURCE` 仍 BLOCKED，研究仍不足，不产生前向成交权限。
6. **M2-PR05 研究快照**：[PR #33](https://github.com/handFOOLed/Stratide/pull/33) 已合并于 `2fdd05d`，#32 完成；既有 EOD 离线只读核验、持久快照、状态和消费，见 [契约](M2_PR05.md)。

## 当前和下一个完整功能包

**本分支 M2-PR06 Draft：** 显式可信快照 → 本地 fake Agent 实际持久任务 → 候选来源登记/查询已有可运行 CLI，见 [契约/操作](M2_PR06.md) 和 [Sol 自测证据](evidence/m2-pr06/README.md)。固定 synthetic 与真实两日只读输入均完成闭环；新数据 scope 禁止云 Provider 和自动 EOD。保持 `RESEARCH_ONLY / NOT_EVALUATED / ELIGIBILITY_DENIED`，没有可信 forward 交易、真实模型权限或 UI。Owner 本轮指定仅 Sol 自测，`agents=0`；ChatGPT 固定 HEAD 审查，合并仍需 Owner 授权。

| 顺序 | Owner/执行责任 | 任务 / DoD |
| --- | --- | --- |
| **当前 #34** | **Sol** | [M2-PR06](https://github.com/handFOOLed/Stratide/issues/34)：显式 EOD 输入、独立外发 scope、本地 fake 任务到研究候选来源；Core-only，仅 Sol 自测，Draft 待审；不改 Risk/权威 Ledger/前向交易权限。 |
| **后续核心** | Owner 再定范围 | 继续 [#10](https://github.com/handFOOLed/Stratide/issues/10) 前向证据与 [#17](https://github.com/handFOOLed/Stratide/issues/17) 数据缺口；证据不足保持 BLOCKED，新的交易联动需独立授权。 |
| **核心全部完成后** | **Sol** | 按 PR #28 已确定的设计体系统一集成全部 UI；当前各功能任务无需同步前端。 |

## 一直有效的边界

- **数据语义分离**：`synthetic_test` 是测试、`historical_replay` 是事后历史模拟、`forward_paper` 必须是实际时间推进的模拟成交。当前 forward 仅 observe-only，不能制造交易/净值。
- **研究与交易分权**：Agent 只有研究提案权，没有实盘/模拟账户写入权、风险设置权或独立准入权。平台不可因 UI 或模型故障放松金融安全。
- **版本与验收**：交可运行的 Draft PR，开发者附真实自测，ChatGPT 固定 HEAD 审查；预算/凭据/账本等高风险点做针对性独立反证，Owner 明确授权后才合并。当前补充见 [AGENTS](../AGENTS.md)，历史 [ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 尚待显式修订。
- **无真钱交易**：禁止券商委托、实盘、公开远程服务以及冒充真实交易资格。真实历史样本中的 68 日/3 笔成交不能证明收益优势。

**目标：一次交付完整的可使用功能，证据不够时敢于报告 BLOCKED。**
