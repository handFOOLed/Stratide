# 前端产品化：后端需求清单

> **工程参考**：本页含原阶段协议或设计；当前已交付能力请以 0.3.1 源码为准。
>
> [文档中心](README.md) · [当前版本](STATUS.md) · [架构总览](ARCHITECTURE_OVERVIEW.md)

> 本轮改造只改前端展示层（文案/布局/交互/组件），未修改任何后端 API、数据语义、
> 风控与账本逻辑。下面列出“要让界面能完整、诚实地回答用户问题”所需的后端改动，
> 按优先级排序，交 Owner 决策；每条都说明现状、对用户的影响、建议契约。
>
> 依据：`docs/ui-copy-audit.md`（文案审计）、`state/ui-contract-notes.md`（后端契约调研，
> 含 file:line/实测证据）与 `docs/UI_TERMINOLOGY.md`（术语口径）。

## P0：阻塞验收或影响用户判断

### B1. 预算编辑接口（阻塞“用户能自己修改预算”这条验收）

- **现状**：没有任何修改日/月预算的 HTTP API。预算唯一来源是 Agent 目录
  `settings.json` 的 `budget {currency, timezone, daily_limit_micro, monthly_limit_micro}`，
  产品内只能由安装初始化写一次，之后需 Owner 手工改文件；币种/时区创建后不可变
  （`budget_identity`）。现行 `docs/AGENT_API.md` 明确“Web 不提供额度加额”。
- **用户影响**：设置页与 AI 研究页只能只读展示“今日/本月已用”，无法修改上限；
  验收标准“找到并修改预算”本轮无法真正完成。UI 已用诚实文案说明“页面暂不支持修改”。
- **建议契约**（需 Owner 先批准产品/安全边界变更）：
  `POST /api/agent/budget`，复用 `/api/agent` 的 Host/Origin/Sec-Fetch-Site 本机同源校验：
  ```json
  { "daily_limit_micro": "5000000", "monthly_limit_micro": "100000000",
    "confirm_below_committed": false,
    "currency": "CNY(仅首次未配置时可写)", "timezone": "Asia/Shanghai(仅首次未配置时可写)" }
  ```
  校验：正整数 micro 且 1..=1e12；日 ≤ 月；已有预算时币种/时区必须匹配
  `budget_identity`（否则 409 `BUDGET_CURRENCY_TIMEZONE_IMMUTABLE`）；新上限低于
  “已结算 + 未结预留”时默认拒绝，需 `confirm_below_committed=true` 才允许。
  写入：读取 settings → 校验 → 临时文件 + `sync_all` + rename 原子替换；写前比对
  原文件 sha256，变化则 409 `BUDGET_CONFLICT_REREAD`；成功后写审计记录
  `budget_audit:<time>`（old/new/at/source），不改 calls 账本、不释放预留。
  返回：200 + 与 `GET /api/agent/status.budget` 同结构的预算视图；错误码
  `BUDGET_INPUT_INVALID / BUDGET_CONFIG_INVALID / BUDGET_BELOW_COMMITTED /
  BUDGET_CONFLICT_REREAD`。
- **前端就绪度**：预算卡已按只读视图实现并共用 `agent.status.budget` 数据源；接口
  提供后只需把只读卡换成编辑表单（约 1 个组件）。

### B2. 研究失败/阻断原因的可读文本

- **现状**：`task.reason`、`calls[].reason`、`worker_error`、`eod.reason`、
  `runs[].reason`、`models[].authorization` 全部是英文码。前端 `lib/status.ts` 已集中
  映射约 150 个已知码，但真实安装出现的
  `MARKET_RESEARCH_LOCAL_FAILURE`、`LATE_OR_FUTURE_CATALOG_NOT_DECISION_EVIDENCE`、
  `MARKET_RESEARCH_SCOPE_INVALID` 等仍只能靠前端补码，未知码只能显示“原因未记录”。
- **用户影响**：研究失败/被阻止时，一句话原因可能缺失；用户不知道为什么、该做什么。
- **建议契约**：上述字段增加可选 `reason_text`（后端集中维护中文），或提供
  `GET /api/agent/reasons` 静态映射；同时给任务增加 `failure_kind`
  （`retryable_no_charge | charged_failure | outcome_uncertain | blocked_by_local_policy`）
  与 `billing_state`，避免前端从 calls 推断计费语义。前端已有映射可在过渡期继续用。

### B3. 交易保护锁定原因与记录状态

- **现状**：`AccountData.risk.account_freezes/strategy_freezes` 只是
  `DailyLoss|Drawdown|OrderUncertainty|Manual` 字符串数组；`risk` 或数组为
  `null` 表示“未记录”，`[]` 才表示“未触发”。没有触发时间、触发值、中文原因，
  也没有解除状态；且没有任何清锁 API。
- **用户影响**：触发时界面只能解释到“当日亏损/回撤/订单不确定/人工暂停”这一层，
  无法回答“何时触发、锁到什么程度、需要谁处理”；`null` 场景下必须显示“未记录”
  而不能假装正常（前端已这样做）。
- **建议契约**：`risk.freezes: [{scope:"account|strategy", reason, reason_text,
  triggered_at:"RFC3339|null", source:"risk_kernel|manual_freeze"}]?`；`null` 语义保持
  “未记录”。触发时间是 P1 账本 schema 变更，需单独评审。

### B4. 研究暖机进度的权威字段（84 天口径）

- **现状**：84 在系统里是三个不同计数器：①历史补录目标 84（权威字段
  `progress.sessions_ready/remaining`，完成 = `remaining==0`，真实安装已 87/84）；
  ②研究暖机要求**连续** 84 个 READY 交易日（无独立 API 字段，只有 `gaps` 可间接反映）；
  ③研究上下文 = 最近 84 个交易日（报告字段）。`sessions_ready` 是仓库 READY 总数，
  不能用来画“暖机 N/84”。
- **用户影响**：UI 无法诚实显示“研究还需要多少天”。本轮已删掉“数据满 84 个交易日”
  的错误说法，只显示真实的补录状态，不伪造暖机进度。
- **建议契约**：`GET /api/runtime/market` 或 `/api/runtime/status` 增加
  `research_warmup: {required_sessions:84, consecutive_ready_sessions, ready_sessions_total,
  missing_days:[{day,reason}], status:"ready|warming|calendar_unavailable|not_configured",
  source_day}`，由可信 warehouse + 交易日历计算。

## P1：体验完整性

### B5. 通知卡片字段

- **现状**：`inbox.notifications[]` 只有 `id(=task id)/status/reason/at/read`，无任务名、
  结论、分类、跳转目标、全量未读数；最多 50 条且无分页。
- **用户影响**：通知页只能显示“发生了什么 + 已有原因”，任务名/结论靠前端 join 已加载的
  任务列表（最多 20 条）；超过 50 条的历史未读会丢失；研究阻断通知与普通任务无法分类。
- **建议契约**：增加 `name`、`conclusion`（截断）、`provider_id/kind`、
  `target:"agent_task|research_report|market_research"`、可选 `created_at`；
  增加全量 `unread_count` 或分页；`{all:true}` 原子全部已读（可选）。

### B6. 首次设置“已标记完成”的撤销

- **现状**：`POST /api/runtime/setup-complete` 只写标记，没有撤销接口。
- **用户影响**：设置页无法提供“可撤销的已完成状态”，只能说明当前版本不支持撤销。
- **建议契约**：`POST /api/runtime/setup-complete {completed:false}` 或
  `DELETE /api/runtime/setup-complete`，删除标记并返回状态。

### B7. 数据“更新于”时间

- **现状**：快照/账本只提供源交易日 `last_day`、最后有效估值日 `as_of` 与毫秒时间戳
  `last_valid_valuation_at`；没有行情接收/发布时刻。
- **用户影响**：只能显示“数据更新至 YYYY-MM-DD”，无法显示今天几点更新的。
- **建议契约**：snapshot 增加 `data_received_at`（UTC 毫秒）与 `published_at`。

### B8. 运行时诊断字段

- **现状**：动态 reason（`PYTHON_EXIT_{-1}`、`WSL_EXIT_{code}`、
  `WSL_NOT_INSTALLED_OR_BLOCKED:{error}` 等）无法稳定翻译；
  `supervisor.status` 的 DEGRADED/BLOCKED/STOPPED/NOT_STARTED 没有统一文案；
  `tushare_credential` 缺 helper 时返回 UNKNOWN；`/api/runtime/status` 不暴露
  BUILD_INFO 的 commit/built_at 与仓库/反馈地址。
- **建议契约**：动态码结构化（固定 code + detail 字段）；依赖项增加
  `reason_text` 与 `overall: ok|progress|attention|error|unset`；增加
  `build {version, commit, built_at}`、`repo_url/issues_url`（供关于页）。
- **前端现状**：`lib/status.ts` 已覆盖固定码与 5 类动态码回退；原始码只进诊断折叠区。

### B9. 阻断型“伪任务”分类

- **现状**：Python 直接向 tasks 表插入 `status=blocked,
  provider_id=market-research-status` 的阻断通知记录（真实安装 #1/#10/#20），
  `calls=[]`、`result=null`，无 `kind` 字段。
- **用户影响**：如果不识别 `provider_id`，会被误读成“研究任务失败/重复任务”。
  本轮 UI 已按 `provider_id=market-research-status` 归类为“研究未运行”，并保留数据不删除。
- **建议契约**：任务增加 `kind:"research_blocked_notice"` 与可读摘要；inbox 顶层按天聚合。

## P1（补充）：本轮页面改造新发现的缺口

### B13. 研究模型“重新配置”动作

- **现状**：`install-model` 在模型已存在时返回 `MARKET_MODEL_ALREADY_INSTALLED`，
  没有覆盖/更新既有模型配置的接口。已配置后页面只能展示状态，无法重新配置。
- **用户影响**：更换研究模型/端点后，界面没有恢复路径。
- **建议契约**：`POST /api/agent/market-research/install-model {replace:true}` 或独立
  `POST /api/agent/research-model`，带原子写、审计与“是否会中断进行中任务”的明确语义。

### B14. 收盘后自动研究最近记录的完整字段

- **现状**：`eod.latest` 只有 `source_day/disposition`，缺执行时间与失败/跳过原因；
  页面暂用 `status.eod.reason` 兜底，可能与那次记录不一致。
- **建议契约**：`eod.latest` 增加 `at/started_at/finished_at` 与 `reason_text`。

### B15. 未配置桌面桥时的 workspace 响应形状

- **现状**：`/api/v1/workspace` 未配置时返回 `{"state":"not_configured"}`，缺
  `schema_version` 与集合字段；前端 hook 已做空态归一化（不伪造报告），但这属于契约
  不一致。
- **建议契约**：统一返回 `schema_version:1, state:"not_configured",
  studies:[], evaluations:[], evidence:[], candidates:[], paper_allowed:false,
  live_allowed:false`。

## P2：可选

- **B10.** 聚合诊断接口 `GET /api/diagnostics`（一次性返回 runtime/health/snapshot/agent
  摘要并统一脱敏），供“复制诊断信息”使用；当前前端拼接 4 个只读响应亦可。
- **B11.** 未配置预算时 `budget` 返回显式 null 字段而非缺字段，便于强类型消费。
- **B12.** 契约文档漂移：`docs/AGENT_API.md` 描述 Owner token 鉴权，但 0.3.0 实现与实测
  均不校验该头（单机同源模型）。请 Owner 决定保留哪种模型，再同步文档/实现。

## 明确不改的后端边界（本轮遵守）

- 不改 Risk Kernel、账本、订单路径、Paper 语义与数据来源。
- 不改 `/api/v1/*` 现有字段含义；新增字段必须可选、向后兼容。
- 不新增任何自动重试、自动清锁、自动加预算或实盘能力。
## 实现状态（2026-11-06 更新）

> Owner 已批准修改后端。以下需求已按最小契约落地并通过交叉编译、API 与实际安装验证；
> 原“建议契约”保留作为设计依据，不再表示未实现。

| 需求 | 状态 | 落地位置 / 说明 |
| --- | --- | --- |
| B1 预算编辑 | 已实现 | `POST /api/agent/budget`（research/agent/src/budget_admin.rs、apps/stratided/src/agent_api.rs）；前端 BudgetEditor |
| B2 原因中文 | 已实现 | research/agent/src/reasons.rs（165+ 条）；tasks/calls/eod/models 返回 `reason_text` |
| B3 交易保护详情 | 已有字段；无新增触发时间 | 不伪造时间，界面继续显示“未记录” |
| B4 暖机 N/84 | 已实现 | 以 `backfill.progress.remaining==0` 为准；不混用 84 语义 |
| B5 通知字段 | 已实现 | inbox `name/conclusion/provider_id/kind` + 顶层 `unread_count`，不再由前端 join 任务 |
| B6 撤销首次设置 | 已实现 | `POST /api/runtime/setup-complete {completed:false}`（幂等） |
| B7 数据接收时刻 | 保留现状 | 不展示未提供的接收时刻 |
| B8 运行时动态原因码 | 已实现 | 后端 reason_text + 前端映射双保险；未知码只进诊断 |
| B9 阻断伪任务 kind | 已实现 | `provider_id=market-research-status` → `research_blocked_notice` |
| B10 构建信息/反馈入口 | 已实现 | runtime status `build{version,commit,built_at}` + `repo_url/issues_url` |
| B11 未配置预算字段 | 已实现 | `state=unconfigured` 时返回可编辑初值；首次配置可写币种/时区 |
| B12 契约文档漂移 | 已修正 | `docs/AGENT_API.md` / `docs/DASHBOARD_API.md` 已同步 0.3.0 现实契约 |
| B13-B15 | 见 `docs/UI_KNOWN_ISSUES.md` 的更新段 | — |

新增（本轮自动化可用性）后端行为：

- 安装版 dashboard 以 `--agent-observer` 附加模式运行，不再持有 `agent.lock`，后台 watch 是唯一研究执行者；
  `POST /api/agent/tasks` 在观察者模式返回 409 `MANUAL_RESEARCH_UNAVAILABLE_IN_BACKGROUND_MODE`，
  `/api/agent/status` 增加 `manual_research_available`。
- 首次成功采集后自动启用默认模拟交易策略（Paper-only，¥100,000 名义本金、最多 2 只、单票 ¥20,000、
  批次容量 100 股、不接券商）；策略写入原 Paper 账本，只能暂停/恢复。
- 本地研究代码更新不再永久卡死：未派发云端任务的 BLOCKED 运行会在当前时点重建 screen/plan；
  云端 JSON 模式字段回显在边界剥离；本地模型 pin 变化仅允许在无付费调用时审计后替换。
