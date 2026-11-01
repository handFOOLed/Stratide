# Stratide Paper 阶段路线图（当前执行版）

> 2026-11-01；最新实现与数据边界见 [STATUS](STATUS.md)。Owner 已决定 **Core-first、UI-later**：后续核心功能不要求同期 Dashboard/UI，最终由 Sol 按已合并 PR #28 的视觉基准统一集成。旧各 PR 实施/验收细节仍保存在 `docs/M0_*.md`、`docs/M1_*.md`、`docs/M2_PR01.md` 与 `docs/evidence/`。

## 已完成（已并入 main）

1. **M0 Paper Core**：[PR #2](https://github.com/handFOOLed/Stratide/pull/2)、[#4](https://github.com/handFOOLed/Stratide/pull/4)、[#6](https://github.com/handFOOLed/Stratide/pull/6)：单账户 Risk Kernel、模拟撮合、持久账本、回放和六报告。
2. **M1 已实现部分**：[PR #8](https://github.com/handFOOLed/Stratide/pull/8)、[#9](https://github.com/handFOOLed/Stratide/pull/9)、[#12](https://github.com/handFOOLed/Stratide/pull/12)、[#14](https://github.com/handFOOLed/Stratide/pull/14)、[#18](https://github.com/handFOOLed/Stratide/pull/18)：真实 EOD **observe-only**、68 日历史探索性回测、独立研究评价和长窗口 DATA_BLOCKED 调查。**M1 前向 Paper 成交仍未完成**。
3. **M2 Web V1**：[PR #21](https://github.com/handFOOLed/Stratide/pull/21)：localhost 同源只读 API 与可启动 Dashboard，Owner 指定一个已发布的报告快照；历史回放不进入前向账户 NAV。
4. **Agent V1 与视觉基准**：#22 核心及 PR #27 状态修复已在 main；[PR #28](https://github.com/handFOOLed/Stratide/pull/28) 确立视觉基准，不代表功能全部完成。真实 Provider 未验证。
5. **M2-PR04 候选链路**：[PR #30](https://github.com/handFOOLed/Stratide/pull/30) 已合并于 `05ab0b9`；[#31](https://github.com/handFOOLed/Stratide/issues/31#issuecomment-6512910618) A/B 双线独立 PASS。真实两日 `EOD_CONTINUITY_VERIFIED`；`OPENING_SOURCE` 仍 BLOCKED，研究仍不足，不产生前向成交权限。
6. **M2-PR05 研究快照**：[PR #33](https://github.com/handFOOLed/Stratide/pull/33) 已合并于 `2fdd05d`，#32 完成；既有 EOD 离线只读核验、持久快照、状态和消费，见 [契约](M2_PR05.md)。
7. **M2-PR06 显式 Fake Agent 闭环**：[PR #35](https://github.com/handFOOLed/Stratide/pull/35) 已合并于 `a522c29`，#34 完成；显式 EOD 快照 → 本地 fake 持久任务 → 候选研究来源。保留独立 scope、禁止云外发/自动 EOD 和资格拒绝，见 [契约](M2_PR06.md)。

8. **M1-PR07B 公司行为证据**：[PR #38](https://github.com/handFOOLed/Stratide/pull/38) 已合并于 `a02a9b0`；真实事实 `FACTS_PARTIAL`、PIT 未核实，原证据包只读保留。

9. **M1-PR08 现金分红模型**：[PR #40](https://github.com/handFOOLed/Stratide/pull/40) 已合并于 `287dfe8`；隔离 synthetic v4 / 七报告 / 独立算术与双基准，现实资格仍拒绝。

## 当前和下一个完整功能包

PR #42 的[历史公司行为桥接 V1](M1_PR09.md)、PR #44 的[EOD 自动研究](M2_PR07.md)、PR #46 的[候选审阅评价](M2_PR08.md) 均已并入 main。77 个历史会话仍为 EXPLORATORY_EX_POST，真实 PIT 新增 0 天；原证据保留。

**M1-PR10 已合并（PR #48）：** [Forward EOD Shadow V1](M1_PR10.md) 提供 Owner 本机启停、原当日 EOD/连续 21 日固定 SMA5/20、不可回填决策与只读 Decimal 复算。原真实两日证据及暖机不足限制保留。

**M2-PR09 已合并（PR #50）：** [#49](https://github.com/handFOOLed/Stratide/issues/49) 交付 [自动 EOD Operator V1](M2_PR09.md)：一次安全配置/enable → 前台每日检查/原采集器 → Snapshot → Shadow/可选 Fake → 原提交 ref 审计。15:15 检查并报告 `EARLY_SOURCE_UNVERIFIED`，按 Issue 允许的回退保留 16:00 正式单槽；不改变原未知/失败重发语义。默认 OFF、持久 disable、四阶段恢复、只读查询；synthetic 测试不增加真实前向日。**NO_ORDERS / NO_FILLS / NO_NAV**。

**M2-PR10 已合并（PR #52）：** [#51](https://github.com/handFOOLed/Stratide/issues/51) 的 [Time-Series + Fusion V1](M2_PR10.md) 已并入 main `1b2c903`：可信 Snapshot 冻结 → 数学基线/独立可替换本地时序测试 Adapter → 原 Rust Agent/预算/Fusion fake → 原候选 Inbox。精确任务领取和实际任务 reserve/dispatch 双门禁保留，默认 OFF、LOCAL_FAKE_ONLY；不改变 #50 Operator 或财务权限。[原开发自测](evidence/m2-pr10/README.md) 保留其当时记录。

**本分支 M1-PR11 Draft：** [#53](https://github.com/handFOOLed/Stratide/issues/53) 的 [真实前向 EOD 研究资格 V1](M1_PR11.md)：只读原 observer/PR33/PR38，冻结独立事件源契约与实际取得覆盖，逐日核验 21 连续会话并将收据接入原 PR52。完整 synthetic 正反/修订/故障恢复通过只证明工程路径；真实仅两日、事件覆盖缺失且已过期，仍 BLOCKED。历史 PIT、开盘、Paper/Live 均不解锁。

| 顺序 | Owner/执行责任 | 任务 / DoD |
| --- | --- | --- |
| **当前 #53** | **Sol** | M1-PR11 前向来源证据、逐日研究资格、原双模型安全接线；真实只读审计与合成正反/修订/恢复，唯一 Draft，固定 HEAD 审查后由 Owner 决定是否合并。 |
| **后续核心** | Owner 再定范围 | #10 真实开盘、PIT、账户税/到账仍受阻；#36 完整多模态消融及真实供应商未验证。 |
| **核心全部完成后** | **Sol** | 按 PR #28 的设计体系统一集成 UI；本期不改 UI。 |

## 一直有效的边界

- **数据语义分离**：`synthetic_test` 是测试、`historical_replay` 是事后历史模拟、`forward_paper` 必须是实际时间推进的模拟成交。当前 forward 仅 observe-only，不能制造交易/净值。
- **研究与交易分权**：Agent 只有研究提案权，没有实盘/模拟账户写入权、风险设置权或独立准入权。平台不可因 UI 或模型故障放松金融安全。
- **版本与验收**：交可运行的 Draft PR，开发者附真实自测，ChatGPT 固定 HEAD 审查；预算/凭据/账本等高风险点做针对性独立反证，Owner 明确授权后才合并。当前补充见 [AGENTS](../AGENTS.md)，历史 [ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 尚待显式修订。
- **无真钱交易**：禁止券商委托、实盘、公开远程服务以及冒充真实交易资格。真实历史样本中的 68 日/3 笔成交不能证明收益优势。

**目标：一次交付完整的可使用功能，证据不够时敢于报告 BLOCKED。**
