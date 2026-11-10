# AGENTS.md — Stratide 工程与协作规则

> Stratide V2 已进入使用、数据观察和本机验收阶段。新开发以 Owner 最新授权的 Issue 或明确范围为准。涉及真实数据/PIT 前向评估、N100 或实盘的工作另行决策。

[文档中心](docs/README.md) · [当前版本](docs/STATUS.md) · [系统架构](docs/ARCHITECTURE_OVERVIEW.md) · [使用教程](docs/USER_GUIDE.md) · [验证边界](docs/KNOWN_LIMITATIONS.md)

Rust 工作区包含本地服务 `apps/stratided`、Windows 启动器 `apps/stratide-launcher` 和 `crates/` 下的核心模块。React/TypeScript Dashboard 位于 `apps/dashboard/`，研究工具位于 `research/` 和 `scripts/`。涉及运行配置或数据位置时，查阅[本机配置](config/README.md)。

## 工程协作

| 角色 | 职责 |
| --- | --- |
| **Owner** | 确定任务范围，授权费用、云外发及风险例外，指定需要本人批准的任务 |
| **实施 Agent** | 实现、测试、创建并维护 PR，处理审查意见、触发复审，满足合并条件后执行合并 |
| **审查 Agent** | 以 Codex 自动代码审查为常规入口，对具体 HEAD 报告问题；独立审查 Agent 按风险补做故障反证 |

## 不可突破的安全边界

1. **Paper-only，禁止真实券商/真实资金委托。** 不新增 live broker、未授权支付、公开服务、生产实盘许可或自动策略晋升。绝不能把 synthetic、historical_replay、observe-only forward 当作真实未见过的连续前向模拟成交/盈利。
2. **一个可信的风险/账本执行路径。** Agent 和不可信策略代码无权下单、改 Risk/资金、写权威账本、读取券商密钥；未知订单/数据或费用结果不可按“成功/没发生”猜测；不要凭超时盲目重试。
3. **资金和证据正确性高于美观。** 现金用整数分、数量用整数股，校验费用/时点/持仓、重启与幂等。复用单账户 ledger；历史数据必须保留来源、时间、复权与验证等级。未知公司行为、历史 PIT 或开盘证据按 BLOCKED 处理。
4. **云端 LLM 可替换，不在本机推理。** 未获 Owner 预算/数据共享许可，禁止付费调用与外发。Budget Gate 独立于模型，在并发、日/月限额、跨期、取消与未知账单情况下保持 fail-closed；密钥不得入 Git/前端/日志。研究产物无权自证可交易。
5. **不执行未隔离生成代码。** Worker 沙箱未经实测安全隔离前，不允许 Agent 任意 Python/shell 代码进入 Rust 核心或取得文件系统、网络和凭据权限。
6. **已有状态与凭据保护。** 不改写旧 journal、六报告/原始数据、版本化证据或历史 Accepted ADR；不要删除/重建本地账户/模型状态。精确忽略 `/STRATIDE_TUSHARE_TOKEN.md`；不得读取或打印 Token。只在明确授权范围内变更。

## PR 流程

1. **实施与自测。** 用 `git remote -v` 核对目标。默认从 `origin` 的最新 `main` 创建独立分支/worktree，交付授权范围内完整可用的改动，并按下方验证规则自测。
2. **提交审查。** 创建一个 Draft PR，写明实际 base/HEAD、变更范围、运行方式、通过和未运行的测试、相关财务或权限反证及已知限制。具备审查条件后，实施 Agent 可标记 Ready for review。仓库目标是所有 PR 每次推送触发 Codex 审查。以 GitHub 上对应当前 HEAD 的审查记录为准。自动审查未触发时，可请求 `@codex review`。服务不可用时，由独立 Agent 审查同一 HEAD，在 PR 记录审查者、结果和降级原因。
3. **返修与复审。** 实施 Agent 处理每条有效发现，记录修复或有证据的判断，推送后复跑相关测试并确认新 HEAD 已复审。涉及预算、云数据授权、凭据、Risk 或 ledger 时，由独立审查 Agent 针对受影响边界补做少量故障反证并附结果。自测、自动评论和独立反证分别记录，旧 HEAD 的结论不得当作当前 HEAD 的验收。
4. **审查通过后合并。** 在 PR 记录当前 HEAD 的审查结论、测试、独立反证（如适用）和剩余风险。P0/P1 全部处理完毕，且当前 HEAD 的审查、所需测试和必需检查均通过后，实施 Agent 可以合并授权范围内的 PR。任务明确要求 Owner 批准时，先取得该 HEAD 的批准。HEAD 变更后重新验证、复审，并按任务要求重新取得批准。

   当 GitHub 的分支规则能保证只有已通过审查的当前 HEAD 才可合并时，可为 PR 启用自动合并。推送修复前先取消已启用的自动合并，待新 HEAD 复审通过后再启用。仓库的 `Allow auto-merge` 开关只开放功能，审查门槛由分支规则执行。分支规则未强制审查时，实施 Agent 等当前 HEAD 满足上述条件后，使用指定已审查 SHA 的合并请求。

**风险分级**按影响判断。P0 包括重复下单、资金/仓位或 Risk 破坏、密钥泄漏和未经授权云消费。P1 包括数据/研究真实性、持久化/恢复或安全边界的实质回归。P2 包括一般 UI 视觉问题。P3 包括不影响决策的罕见边缘情况。按 Owner 在 #21 后明确的风险分级补做独立反证。历史 Accepted [ADR-037](docs/adr/0037-observable-paper-trading-first-and-independent-review-gates.md) 保留原文。

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
