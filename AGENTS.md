# AGENTS.md — Stratide 工程与协作规则

> 当前执行状态见 [STATUS](docs/STATUS.md)，已接受设计与金融安全依据见 [PRODUCT](docs/PRODUCT.md)、[RISK_POLICY](docs/RISK_POLICY.md) 和 [ADR](docs/adr/)。旧 M0-only 的“禁止 UI/研究 Agent”规则已过时：**Owner 已授权在 paper 阶段交付 Web 与研究 Agent，但未授权实盘。**

## 角色、任务与接口

| 角色 | 唯一主要职责 |
| --- | --- |
| **Owner** | 产品范围、支出/外发许可、风险授权、是否合并 |
| **Sol Max** | Rust/数据/Agent、API、预算和权限、安全测试及相关功能交付 |
| **ChatGPT（小猫）** | 设计与代码审查、风险分级；个人模式下固定 HEAD 外部审查为可选。合并由 Owner 决定 |
| **Terra / 其他独立审查者（按风险需要）** | 只在财务/凭据/研究付费等高风险改动中做**针对性独立反证**，不机械重跑全部开发者测试，也不自动合并 |

**当前开发顺序：** [#76](https://github.com/handFOOLed/Stratide/issues/76) 研究评价与 Prompt（[PR #78](https://github.com/handFOOLed/Stratide/pull/78) 审查中）→ [#77](https://github.com/handFOOLed/Stratide/issues/77) Dashboard/Agent/部署。PR #28 仅作为现有视觉设计参考，不指定 UI/UX 负责人。

## 不可突破的安全边界

1. **Paper-only，禁止真实券商/真实资金委托。** 不新增 live broker、未授权支付、公开服务、生产实盘许可或自动策略晋升。绝不能把 synthetic、historical_replay、observe-only forward 当作真实未见过的连续前向模拟成交/盈利。
2. **一个可信的风险/账本执行路径。** Agent 和不可信策略代码无权下单、改 Risk/资金、写权威账本、读取券商密钥；未知订单/数据或费用结果不可按“成功/没发生”猜测；不要凭超时盲目重试。
3. **资金和证据正确性高于美观。** 现金整数分、股数整数股、唯一 Risk→Execution→Ledger，费用、时点、停牌、公司行为、持仓和幂等约束逐笔执行。#10/#17 缺口保持 `BLOCKED`/`NOT_VERIFIED`，不挡工程合并，也不免除单笔交易校验。T 日盘后实际取得并校验的 T 日 `daily.open` 是已知历史输入，可用于研究并冻结 T+1 意图；T 日 open **不是** T+1 成交价。若按 T+1 `daily.open` 模拟成交，须于 T+1 盘后取得该字段，按 T 日已冻结的订单意图、数量及撮合规则事后确认，标记 `EX_POST_OPEN_ASSUMPTION`，不得看到 T+1 结果后选择性下单/撤单，也不能冒充开盘实收。现金、费用、停牌及唯一 Risk→Ledger 逐笔校验保持。
4. **云端 LLM 可替换，不在本机推理。** 未获 Owner 预算/数据共享许可，禁止付费调用与外发。Budget Gate 独立于模型，在并发、日/月限额、跨期、取消与未知账单情况下保持 fail-closed；密钥不得入 Git/前端/日志。研究产物无权自证可交易。
5. **不执行未隔离生成代码。** Worker 沙箱未经实测安全隔离前，不允许 Agent 任意 Python/shell 代码进入 Rust 核心或取得文件系统、网络和凭据权限。
6. **已有状态与凭据保护。** 不改写旧 journal、六报告/原始数据、版本化证据或历史 Accepted ADR；不要删除/重建本地账户/模型状态。精确忽略 `/STRATIDE_TUSHARE_TOKEN.md`；不得读取或打印 Token。只在明确授权范围内变更。

## 工程流程（Owner 当前补充）

- 从最新 `main` 创建独立分支/worktree；交付**完整可用的纵向功能包**，避免只交空壳或无关重构。尊重相关 Issue 的改动文件白名单、Stop That Shit 模式及 `agents=0`；实现用 `$stop-that-shit change hash=allow agents=0`，审查用 `$stop-that-shit review hash=allow agents=0`。
- **P0**：重复下单、资金/仓位或 Risk 破坏、密钥泄漏、未经授权云消费；**P1**：数据/研究真实性、持久化/恢复、安全边界；**P2**：一般 UI 视觉；**P3**：不会影响决策的罕见边缘情况。按真实风险强度设计测试，不付费跑 CI，不为普通 UI 编造大矩阵。
- Sol/DS 必须给出实际 base/HEAD、变更范围、运行方式、通过和未运行的测试、关键财务/权限反证及已知限制；不自合并。
- **2026-11-04 个人自用门限（[#19 评论](https://github.com/handFOOLed/Stratide/issues/19#issuecomment-6623136559)，[#10](https://github.com/handFOOLed/Stratide/issues/10#issuecomment-6623136884)，[#17](https://github.com/handFOOLed/Stratide/issues/17#issuecomment-6623137271)）：** 日常合入 = Owner 本地相关绿测 + 简短说明。大包脱敏证据、先红后绿全套、强制固定 HEAD 外部审查为可选。预算、外发、账本安全改动仍建议针对性反证。不放宽 `REAL_MARKET_DATA_EGRESS_DENIED`、Agent 预算 CNY ¥5/日与 ¥100/月（Asia/Shanghai）、Paper-only / 无实盘真钱。缺 `stk_auction` 或 #10/#17 的 `BLOCKED` 不挡 EOD Paper 工程合并、V1 收尾或 Dashboard 集成；这些标签只挡已验证可交易、PIT 已过、开盘流已实收的宣称。EOD Paper 按上文 T 日已知输入／T+1 盘后确认假设成交的时点约定执行。
- 普通 UI、只读展示与其他非高风险改动：开发者自测即可进入 Owner 合入判断；ChatGPT 同 HEAD 审查可选。**涉及预算、云数据授权、风险/ledger 的安全改动**：仍建议少量针对性独立故障反证。不得把开发者自测写成独立验收或复制别人 PASS；合并仍由 Owner 决定。
- **历史规范差异**：Accepted [ADR-037](docs/adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 原定 Terra 每 PR 复测；Owner 已在 #21 及后续明确调整为**风险分级**。2026-11-04 个人模式进一步把固定 HEAD 外部审查改为可选。本文件记录当前执行补充，**不静默篡改原 ADR**；正式新 ADR/修订另行提交决定。
- 用简体中文写 Owner 交流、Issue 和新说明；`README.md` 中文、`README.en.md` 英文同步。代码标识/API 字段保持规范英文。保留历史证据，不为了更新状态大量删除旧报告。
