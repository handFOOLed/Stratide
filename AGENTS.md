# AGENTS.md — Stratide 工程与协作规则

> **现行基线｜2026-11-05**：Stratide V2 / Windows 0.3.0 已可安装使用，四个 M3 模块分别由 PR #86/#87/#88/#89 **全部合并至 `main`**。当前没有已授权的下一模块开发任务；未来先由 Owner 确认 Issue/范围，再创建独立 Draft PR。用户操作见 [使用教程](docs/USER_GUIDE.md)；工程现状见 [STATUS](docs/STATUS.md)；运行前提与验证边界见 [KNOWN_LIMITATIONS](docs/KNOWN_LIMITATIONS.md)。

> 原 #22/#23 的 UI/后端角色分工，以及 #85 “DeepSeek 正在实施 Windows 安装”均为**历史安排**。安全边界、独立审查、Owner 明确授权合并的原则仍有效；N100/实盘后续另行决策。

## 工程协作

| 角色 | 职责 |
| --- | --- |
| **Owner** | 确定产品目标、任务范围、费用/云外发/风险授权和最终合并 |
| **实施者（Codex / DeepSeek 等）** | 根据 Owner 最新 Issue 完整实现选定模块，提交一个 Draft PR；不自行 Ready/merge |
| **ChatGPT** | 审阅固定 HEAD、风险分级、在 Owner 明确授权后执行合并 |
| **其他独立审查者** | 对凭据、费用、持久账本等高风险修改做定向反证（按需） |

**当前交付**：V2 工程完结，进入使用、日常数据观察和 Owner 本机验收阶段。新功能不沿用旧 #85 开发指令；是否开展真实数据/PIT 前向评估、N100 或其他优化，由 Owner 另发任务。

## 不可突破的安全边界

1. **Paper-only，禁止真实券商/真实资金委托。** 不新增 live broker、未授权支付、公开服务、生产实盘许可或自动策略晋升。绝不能把 synthetic、historical_replay、observe-only forward 当作真实未见过的连续前向模拟成交/盈利。
2. **一个可信的风险/账本执行路径。** Agent 和不可信策略代码无权下单、改 Risk/资金、写权威账本、读取券商密钥；未知订单/数据或费用结果不可按“成功/没发生”猜测；不要凭超时盲目重试。
3. **资金和证据正确性高于美观。** 现金用整数分、数量用整数股，校验费用/时点/持仓、重启与幂等。复用单账户 ledger；历史数据必须保留来源、时间、复权与验证等级。未知公司行为、历史 PIT 或开盘证据按 BLOCKED 处理。
4. **云端 LLM 可替换，不在本机推理。** 未获 Owner 预算/数据共享许可，禁止付费调用与外发。Budget Gate 独立于模型，在并发、日/月限额、跨期、取消与未知账单情况下保持 fail-closed；密钥不得入 Git/前端/日志。研究产物无权自证可交易。
5. **不执行未隔离生成代码。** Worker 沙箱未经实测安全隔离前，不允许 Agent 任意 Python/shell 代码进入 Rust 核心或取得文件系统、网络和凭据权限。
6. **已有状态与凭据保护。** 不改写旧 journal、六报告/原始数据、版本化证据或历史 Accepted ADR；不要删除/重建本地账户/模型状态。精确忽略 `/STRATIDE_TUSHARE_TOKEN.md`；不得读取或打印 Token。只在明确授权范围内变更。

## 工程流程（Owner 当前补充）

- 从最新 `main` 创建独立分支/worktree；交付**完整可用的纵向功能包**，避免只交空壳或无关重构。尊重新任务的明确变更范围；若执行环境安装了 Stop That Shit Skill 可用 `$stop-that-shit change hash=allow agents=0`，否则按相同的最小变更/证据纪律实现，不把另一工具的 Skill 当作 DeepSeek 必备依赖。
- **P0**：重复下单、资金/仓位或 Risk 破坏、密钥泄漏、未经授权云消费；**P1**：数据/研究真实性、持久化/恢复、安全边界；**P2**：一般 UI 视觉；**P3**：不会影响决策的罕见边缘情况。按真实风险强度设计测试，不付费跑 CI，不为普通 UI 编造大矩阵。
- Sol/DS 必须给出实际 base/HEAD、变更范围、运行方式、通过和未运行的测试、关键财务/权限反证及已知限制；**Draft PR，不自合并**。
- 普通 UI/只读展示：Sol 或 DS 自测 + ChatGPT 同 HEAD 审查；**涉及预算、云数据授权、风险/ledger 等高风险变更**：补少量针对性独立故障反证。不得把开发者自测写成独立验收或复制别人 PASS；Owner 仍须显式授权合并。
- **历史规范差异**：Accepted [ADR-037](docs/adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 原定 Terra 每 PR 复测；Owner 已在 #21 及后续明确调整为**风险分级**。本文件记录当前执行补充，**不静默篡改原 ADR**；正式新 ADR/修订另行提交决定。
- 用简体中文写 Owner 交流、Issue 和新说明；`README.md` 中文、`README.en.md` 英文同步。代码标识/API 字段保持规范英文。保留历史证据，不为了更新状态大量删除旧报告。
