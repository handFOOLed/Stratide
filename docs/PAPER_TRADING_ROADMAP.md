# Stratide Paper 阶段路线图（历史背景归档）

> **历史参考**：本文记录旧阶段的实验、规划和问题清单；“当前/Draft”以当时版本为准。
>
> [文档中心](README.md) · [当前版本](STATUS.md) · [架构总览](ARCHITECTURE_OVERVIEW.md)

> **现行进度｜2026-11-05**：V2/Windows 0.3.0 四模块已由 PR #86/#87/#88/#89 合并，可用版使用方式请看 [使用教程](USER_GUIDE.md)。本文只归档旧 Paper/V1 研发顺序，原“当前 #85”“Draft”均为历史称谓。当前状态见 [STATUS](STATUS.md)，运行边界见 [KNOWN_LIMITATIONS](KNOWN_LIMITATIONS.md)；后续新任务由 Owner 确定。

**2026-11-04 / #77 产品集成已实装（Draft）：** [V1 本地产品闭环](V1_COMPLETION.md) 已达到工程收尾，含当前/历史独立来源、原研究/任务/预算、审批通知、假设成交与 Windows 恢复。Owner 合并决定仍待进行。#10/#17 缺证据与真实交易资格保持原判定；N100/Linux 服务器化暂缓，不计本次 Done。后续真实观察不得由合成测试补齐。[本地检查](evidence/v1-closeout-b/README.md)。

**2026-11-04 最新规则 / #19 → #76 → #77：** 先完成 PR #78 的评价/Fusion 修复，再推进产品集成；[本期说明](V1_EVALUATION.md)。个人模式以相关本地绿测和简报验收，大包证据、先红后绿和外部固定 HEAD 审查可选，开发者不自行合并。#10/#17 仍记录证据缺口，但不阻挡工程交付、EOD Paper 或 Dashboard 集成，不可冒称 PIT/开盘实收/已验证可交易。T 日已知数据可冻结 T+1 意图；T+1 盘后确认的开盘价撮合须标 `EX_POST_OPEN_ASSUMPTION`，不得看到价格后改意图。唯一 Risk→Execution→Ledger、真实数据不外发、¥5/日 ¥100/月、Paper-only 和 N100 NOT_VERIFIED 保持。下方为历史阶段记录，与本段冲突时以本段为准。

**PR #75 R1 / 2026-11-04：** 模型身份、UNKNOWN opportunity 集合和多证券来源绑定修复已完成开发验证，见 [R1 反证与真实复核](evidence/m2-pr20/r1/README.md)；保持同一 Draft，等待固定 HEAD 复审。历史 PIT、Paper/Live 与 N100 状态不升级。

**当前 #74 / M2-PR20（本分支 Draft）：** [真实历史 → 本地 TimesFM](M2_PR20.md) 已完成实际三证券 CPU 推理、原任务/Registry 和 report/verify；[开发证据](evidence/m2-pr20/README.md)。真实数据外发拒绝，新云调用/计费/行情请求为 0。ENGINEERING_PASS 不提升 PIT、样本外优势、Paper/Live 或 N100 资格。PR #70/#72 已在当前 main；下方旧阶段记录保留原发生时状态。

> 2026-11-03；最新实现与数据边界见 [STATUS](STATUS.md)。Owner 已决定 **Core-first、UI-later**：后续核心功能不要求同期 Dashboard/UI，最终按已合并 PR #28 的视觉基准统一集成。旧各 PR 实施/验收细节仍保存在 `docs/M0_*.md`、`docs/M1_*.md`、`docs/M2_PR01.md` 与 `docs/evidence/`。

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

**M1-PR11 已合并（PR #54）：** [#53](https://github.com/handFOOLed/Stratide/issues/53) 的 [真实前向 EOD 研究资格 V1](M1_PR11.md) 已并入 `main a27f466`：只读原 observer/PR33/PR38，冻结独立事件源契约与实际取得覆盖，逐日核验 21 连续会话并接入原 PR52。完整 synthetic 正反/修订/恢复只证明工程路径；真实两日、事件覆盖缺失且已过期，仍 BLOCKED。历史 PIT、开盘、Paper/Live 均不解锁。

**M2-PR11 已合并（PR #56）：** [#55](https://github.com/handFOOLed/Stratide/issues/55) 的 [Cloud Risk Expert + Autonomous Portfolio V1](M2_PR11.md)：独立 scope、BigQuery/DeepSeek 两套生产 Adapter、原 Rust 任务/统一预算、Naive/EWMA 风险代理、严格股票/现金组合及原 Inbox。3 股票+现金/全现金、策略版本变化和费用/基线对照走 recorded/loopback 完整路径。无真实云/资金/订单；真实数据、完整 query 费用和模型能力仍 BLOCKED/NOT_VERIFIED。

**审查修复 R1：** 新链路显式绑定已有 Owner AgentDir 与配置，共享原费用库；177 Rust、13 新 E2E 开发自测通过。PR52/54 三套原完整回归于 2026-11-02 盘后有效时间实际运行，**10+4+13 项均 exit 0**，该段记录当时开发证据；PR #56 后续已并入 main，原记录保留；[修复证据](evidence/m2-pr11/r1/README.md) / [盘后运行](evidence/m2-pr11/r1/afternoon/README.md)。

**M2-PR12 已合并（PR #58）：** [历史仓库 V1](M2_PR12.md) 已真实下载 1212 日期、6347781 行；历史身份/BSE 日历/PIT 仍未核实，本地旧库保留。

**M2-PR13 已合并（PR #60）：** [四接口历史 sidecar V2](M2_PR13.md)，原五年回填 4848 个 API×日期分区及 6068 次请求保留；支持持久预算、恢复、只读版本和冻结复权。旧因子 PARTIAL 标签不重写，也不依据未声明 cap 推断截断，见 [增量修复](evidence/m2-pr13/r1/README.md)。

**M2-PR14 已合并（PR #62）：** [多股票历史研究 V1](M2_PR14.md) 只读消费上述本机 V1/V2，交三策略/三基准、三个成本情景、开发/验证/后期时间隔离和逐年重置 Walk-forward，以及冻结/复现报告。真实运行与资源见 [原证据](evidence/m2-pr14/README.md)。历史 PIT、开盘可成交性及无偏历史 Universe 未获证；不连接 Agent、资格门禁或资金账本。

**M2-PR15 已合并（PR #64）：** [自主策略研究闭环 V1](M2_PR15.md)：可信本地确定性提案 → 强类型受限 AST → 评价前冻结 → PR62 同源多候选/匹配基准 → 成功与失败封存 → 仅开发段反馈的下一轮有界研究。原真实五年结果与资源见 [原证据](evidence/m2-pr15/README.md)，不以正收益作为工程 PASS 条件。旧 seed63/两轮/8 AST 和 post-seal 证据保留。

**M2-PR16 已合并（PR #66）：** [云端结构化提案接线 V1](M2_PR16.md)：原 Owner Agent/共享 Budget → 受控 recorded/loopback → PR15 AST/冻结/持久控制器 → PR62 同源评测/失败审计。该期真实 Provider BLOCKED；0 付费/外发/新行情/Token/旧 raw 或全库复验，不解锁 Paper/Live。原运行与反证见 [开发证据](evidence/m2-pr16/README.md)。

**当前 M2-PR17 Draft（#67）：** [DeepSeek 受控 HTTPS](M2_PR17.md)：内部 `ds4.1flash` / API `deepseek-flash`，默认 OFF；原 CNY Agent/Budget、受控密钥、纯合成输入的一次请求许可、PR15 AST/PR62 离线闭环。开发采用 recorded/loopback，未获 Owner 具体费用与外发授权，真实请求 `REAL_PROVIDER_NOT_RUN_OWNER_AUTHORIZATION_MISSING`。不重复旧五年研究或全库验收，Paper/Live 保持 BLOCKED；[本期证据](evidence/m2-pr17/README.md)。

| 顺序 | Owner/执行责任 | 任务 / DoD |
| --- | --- | --- |
| **当前 #74** | **Sol** | M2-PR20 真实历史/质量 → 本地 TimesFM → 原任务/Registry；单个 Draft，固定 HEAD 审查及 Owner 明确批准后才可合并，真实数据不外发。 |
| **后续核心** | Owner 再定范围 | #10 真实开盘、PIT、账户税/到账仍受阻；#36 完整多模态消融及真实供应商未验证。 |
| **核心全部完成后** | **Sol** | 按 PR #28 的设计体系统一集成 UI；本期不改 UI。 |

## 一直有效的边界

- **数据语义分离**：`synthetic_test` 是测试、`historical_replay` 是事后历史模拟、`forward_paper` 必须是实际时间推进的模拟成交。当前 forward 仅 observe-only，不能制造交易/净值。
- **研究与交易分权**：Agent 只有研究提案权，没有实盘/模拟账户写入权、风险设置权或独立准入权。平台不可因 UI 或模型故障放松金融安全。
- **版本与验收**：交可运行的 Draft PR，开发者附真实自测，ChatGPT 固定 HEAD 审查；预算/凭据/账本等高风险点做针对性独立反证，Owner 明确授权后才合并。当前补充见 [AGENTS](../AGENTS.md)，历史 [ADR-037](adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 尚待显式修订。
- **无真钱交易**：禁止券商委托、实盘、公开远程服务以及冒充真实交易资格。真实历史样本中的 68 日/3 笔成交不能证明收益优势。

**目标：一次交付完整的可使用功能，证据不够时敢于报告 BLOCKED。**
