# AGENTS.md — Stratide 工程与协作规则

> **Owner 决议｜2026-11-10**：对已经授权范围内的 PR，采用 **Agent 自动审查 → 自动返修 → 当前 HEAD 复审 → 满足门禁后自动合并**，不再逐 PR 等待人工批准。遇到权限越界、缺失可信审查/检查或无法安全修复时 **fail-closed，保持未合并**。新开发仍以 Owner 最新授权的 Issue/范围为准；真实数据/PIT、N100、实盘等超范围事项另行决策。决议详见 [ADR-038](docs/adr/0038-unattended-agent-review-repair-and-sha-locked-merge.md)。

[文档中心](docs/README.md) · [当前版本](docs/STATUS.md) · [系统架构](docs/ARCHITECTURE_OVERVIEW.md) · [使用教程](docs/USER_GUIDE.md) · [验证边界](docs/KNOWN_LIMITATIONS.md)

Rust 工作区包含本地服务 `apps/stratided`、Windows 启动器 `apps/stratide-launcher` 和 `crates/` 下的核心模块。React/TypeScript Dashboard 位于 `apps/dashboard/`，研究工具位于 `research/` 和 `scripts/`。涉及运行配置或数据位置时，查阅[本机配置](config/README.md)。

## 工程协作

| 角色 | 职责 |
| --- | --- |
| **Owner** | 预先确定任务范围与费用/数据外发/风险权限，可随时暂停或撤销授权；授权范围内的 PR 无须逐次确认 |
| **实施 Agent** | 无人值守实现、自测、发 PR、根据独立审查结果返修；检查通过后以当前 HEAD SHA 锁定合并 |
| **审查 Agent** | 针对每次更新的 HEAD 自动评审；高风险变更由不同于实施者的独立审查/故障反证验证，不允许实施者自评代替审查 |

## 不可突破的安全边界

1. **Paper-only，禁止真实券商/真实资金委托。** 不新增 live broker、未授权支付、公开服务、生产实盘许可或自动策略晋升。绝不能把 synthetic、historical_replay、observe-only forward 当作真实未见过的连续前向模拟成交/盈利。
2. **一个可信的风险/账本执行路径。** Agent 和不可信策略代码无权下单、改 Risk/资金、写权威账本、读取券商密钥；未知订单/数据或费用结果不可按“成功/没发生”猜测；不要凭超时盲目重试。
3. **资金和证据正确性高于美观。** 现金用整数分、数量用整数股，校验费用/时点/持仓、重启与幂等。复用单账户 ledger；历史数据必须保留来源、时间、复权与验证等级。未知公司行为、历史 PIT 或开盘证据按 BLOCKED 处理。
4. **云端 LLM 可替换，不在本机推理。** 未获 Owner 预算/数据共享许可，禁止付费调用与外发。Budget Gate 独立于模型，在并发、日/月限额、跨期、取消与未知账单情况下保持 fail-closed；密钥不得入 Git/前端/日志。研究产物无权自证可交易。
5. **不执行未隔离生成代码。** Worker 沙箱未经实测安全隔离前，不允许 Agent 任意 Python/shell 代码进入 Rust 核心或取得文件系统、网络和凭据权限。
6. **已有状态与凭据保护。** 不改写旧 journal、六报告/原始数据、版本化证据或历史 Accepted ADR；不要删除/重建本地账户/模型状态。精确忽略 `/STRATIDE_TUSHARE_TOKEN.md`；不得读取或打印 Token。只在明确授权范围内变更。

## PR 流程

1. **实施与自测。** 用 `git remote -v` 核对目标。默认从 `origin` 的最新 `main` 创建独立分支/worktree，交付授权范围内完整可用的改动，并按下方验证规则自测。
2. **自动提交与审查。** 实施 Agent 创建 Draft PR，说明 base/HEAD、变更、测试、财务/权限反证、未验证项目；达到审查条件后自动标记 Ready。为 PR 首次 Ready 和后续每次 `synchronize` 配置 Codex 自动审查触发；未触发时自动请求 `@codex review` 或调用已部署的独立审查 Agent。**必须得到绑定当前 HEAD 的实际审查结论**，不得把已发送请求、历史评论或 GitHub 的 `Allow auto-merge` 当作审查通过。
3. **自动返修与复审。** 返修执行器自动读取审查意见、修复有效问题、补最小必要回归，推送新 HEAD 后重新触发全部必需审查与检查；记录每个 SHA 的测试/修复/独立反证证据。涉及预算、费用/凭据、云数据授权、Risk、ledger、持久恢复或隔离的变更，**必须由非实施 Agent 对相关失败路径做独立反证**。设置有限返修次数和退避；重复失败、能力缺失或有无法解决的阻断项，标记 `BLOCKED` 并通知 Owner，但**不得绕过门禁或盲目重试**。
4. **自动受控合并。** Owner 对已授权任务的 PR **一次性授权无人值守合并**，不要求每个 PR 再确认；必须同时具备：① base 和目标仓库符合授权；② 当前 HEAD 已取得独立 PASS（非同一实施者自评）；③ 受影响的全部必需检查、对应风险反证均通过；④ 无未解决的 P0/P1 或其他明确阻断；⑤ 无范围扩大、隐含付费调用或新数据外发/实盘权限；⑥ 对合并操作显式传递 `expected_head_sha`（或等价的 HEAD 条件）。任何 SHA 漂移都取消已有结论并重审。默认 squash；不直接推送 `main`。
   
   **自动合并防护。** 优先通过 GitHub ruleset / branch protection 强制阻断未通过的检查和当前 SHA 审查；仅启用 `Allow auto-merge` 不构成门禁。未建立可靠机器门禁的阶段，合并执行器仍必须逐项核验上述条件并进行 SHA 锁定；若无法证明，**停止而非猜测 PASS**。修复推送前取消旧的自动合并意图，避免旧审查对应新代码。不可用时发布阻断状态，不产生无人看守的危险合并。

**风险分级**按影响判断：P0 为重复执行/真实资金风险、密钥泄漏和未经授权付费云调用；P1 为研究真实性、持久恢复、授权、隔离和 Risk/Ledger 重大回归；P2 为一般功能可用性/交互/状态正确性；P3 为非决策性罕见边界。高风险同样可以无人值守地修复、复测并自动合并，**但不可跳过独立反证**。被阻断不等于等待 Owner 逐 PR 审批，而是要求自动化修复或保持未合并。原 [ADR-037](docs/adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 保留历史原文，**其第 5、6、7 条关于合并者与逐 PR Owner 授权的旧流程由 [ADR-038](docs/adr/0038-unattended-agent-review-repair-and-sha-locked-merge.md) 取代**；其他 Paper/Risk/数据证据约束不变。

**部署与事实边界**：以上是 Owner 的目标工作流和合并授权；`AGENTS.md` 本身不会启动常驻 Agent。启用之前必须在 GitHub/执行平台实际接通审查触发、返修执行器、独立反证和分支检查，完成端到端测试。**未验证这些机制前，不得对外称“无人值守自动合并已经上线”。**

### Git 与改动范围

- 默认向 `handFOOLed/Stratide` 的 `origin` 推送任务分支，PR 目标为同仓库 `main`。推送前再次核对远端与分支，首次推送使用 `git push -u origin <branch>`。经授权的任务由 Agent 完成推送和 PR，禁止直接推送 `main`。目标与任务指定不一致时，先向 Owner 核实。
- 提交用 Conventional Commits，例如 `fix:`、`feat:`、`docs:`。每次提交聚焦一件事，标题一行，可用中文。提交钩子失败后修复并重试。改写历史、跳过钩子、强推、硬重置、清理分支或工作树、修改 Git 配置均须明确授权。保留已有的用户改动。
- 变更依赖、CI、构建或发布入口、删除已有文件，须在任务授权范围内。运行配置与密钥通过本机配置入口管理，仓库中的示例只使用通用名称与虚构值。

## 设计、验证与文档

- **设计。** 改动持久化格式、新增或调整公开 API、改变跨模块信任边界前，在 Issue 或 PR 草稿写清契约、对已有数据和调用者的影响、失败恢复和验证方案。有多条合理实现路径时，记录选择依据。需要持久记录架构决策时，查阅 [ADR 索引](docs/adr/README.md)。涉及授权范围变化时先由 Owner 确认。范围内的局部修复直接实施。
- **验证。** 按影响选择现有入口。Rust 运行 `cargo test -p <package> --locked` 并选取相关集成测试。Dashboard 按[开发说明](apps/dashboard/README.md)运行类型检查和测试。用户可见的交互用 `npm --prefix apps/dashboard run test:browser` 的本地 fixture 验证主要流程与相关边界。Python、Windows 安装或恢复场景从[工具脚本](scripts/README.md)选对应检查。`scripts/test-windows-product.ps1` 会停止本机匹配的 Stratide 进程，应在独立测试环境用新建的测试数据根运行。
- **验证记录。** 在 PR 区分构建、类型检查、自动测试、浏览器验证和安装版验证。标明未运行的项目及原因，并标明证据来自 fixture、回放还是真实环境。优先使用隔离数据和本地模拟，未经授权不使用付费 CI。
- **同步说明。** 行为或配置变更时更新相关[使用教程](docs/USER_GUIDE.md)或[安装手册](docs/WINDOWS_INSTALL.md)。接口或架构变更时更新对应的 [Dashboard API](docs/DASHBOARD_API.md)、[Agent API](docs/AGENT_API.md)或[系统架构](docs/ARCHITECTURE_OVERVIEW.md)。导航目标变更时同步索引。新增文档前先检查能否更新已有页面，保留历史证据。
- **语言与注释。** 用简体中文写 Owner 交流、Issue、PR 和新说明。`README.md` 中文与 `README.en.md` 英文同步。代码标识与 API 字段使用规范英文。注释用来解释代码本身难以看出的约束和取舍。

## Code Review Rules

- **Paper、Risk 与账本。** 检查所有纸面订单是否经过现有 Risk 和单账户 ledger，金额与数量是否使用整数。对重复请求、未知结果、部分失败或重启会造成重复执行或资金、仓位偏差的改动报 P0/P1，并指出触发条件。
- **授权、费用与隔离。** 检查任何云调用和数据外发是否在已授权范围内，Budget Gate 在并发、跨期、取消和未知账单时是否仍拒绝越权。检查凭据是否会进入 Git、前端或日志，以及不可信策略是否获得文件、网络、凭据或账本权限。审查证据限于仓库差异、已提交上下文和脱敏验证结果。
- **数据、证据与恢复。** 检查历史数据的来源、时点、复权、验证等级是否可追溯，未知 PIT、公司行为或开盘证据是否保持 BLOCKED，模拟和记录证据是否被误报成真实结果。对可能破坏账户状态、历史证据或重启恢复的改动，要求覆盖失败路径的证据。

审查意见用简体中文，标出 P0/P1、改动位置、触发条件与可观察影响。格式与机械规则交由已有检查处理。
