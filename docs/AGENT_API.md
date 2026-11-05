# Agent V1 本机 API

## Issue #77：本地审批与通知

沿用本节本机同源检查与 v1 信封。`GET inbox` 返回原 Agent DB 中的审批和已结束任务通知：`notifications[]` 含 `id/status/reason/at/read/name/conclusion/provider_id/kind`——`name` 是任务名，`conclusion` 是已完成任务的 `research.hypothesis`（截断到 500 字符，无结果时为 null），`provider_id=market-research-status` 的阻断记录 `kind=research_blocked_notice`，其余为 `research_task`；顶层 `unread_count`（JSON 数字）统计全部已结束且未标记已读的任务数，不受返回 50 条窗口限制。`GET operations` 列本机配置的固定研究；`GET prompts` 仅返回版本化安全内置 Prompt，不含上下文/凭据。以下路径均加 `/api/agent/`：

| POST 路径 | JSON | 持久语义 |
| --- | --- | --- |
| `approvals` | `{id,operation}` | 32 位 hex 请求 ID，同 ID 同操作幂等；记录操作 SHA，许可一小时过期 |
| `decide` | `{id,decision}` | approve/reject/revoke/start；CAS 消费一次执行许可，拒绝重复启动 |
| `read-notifications` | `{ids:["原task ID"]}` | 仅标明列出的已结束任务已读；最多 50 条 |
| `stop-local` | `{}` | 原 CPU stop/disable，不撤回已发云请求 |

通用 `POST tasks` 可带 `X-Stratide-Idempotency`（32 位 hex）；重复同内容返回原任务，变更内容拒绝。配置 `--desktop-config` 时附着原 Agent、不启动第二个任务循环，通用建任务/EOD 开关拒绝，改用已配置操作。重启将旧 running 审批标记结果未知，不重发；原任务/预算/云授权不重建。完整语义见 [V1_COMPLETION](V1_COMPLETION.md)。

与 [原 Paper API](DASHBOARD_API.md) 共用 127.0.0.1 同源静态服务与 `{api_version,state,snapshot,data,error}` 信封。旧账户/订单路由保持 GET，写入仍为 405。业务金额/ID/用量以十进制字符串返回；预算单位是 micro_currency_1e-6，不是 Paper 的 fen。

## 权限与请求

0.3.0 安装态是**单机同源、无页面令牌**模型：请求必须指向当前 `127.0.0.1:<port>` 或 `localhost:<port>`（Host 与端口完整一致）；POST 还必须显式带与 Host 完整一致的 `Origin: http://127.0.0.1:<port>`（localhost 需完全对应）、`Content-Type: application/json` 和不超过 8192 字节的 Content-Length；Sec-Fetch-Site 如有必须为 same-origin/none。缺失 Origin 不能因 Host 正确而通过。没有 CORS、Cookie、跨站登录或任意文件/命令/URL 参数。JSON 拒绝额外字段。

> 历史：M2 早期文档要求 `X-Stratide-Owner: <本机 owner-token>`，0.3.0 实现不再校验该头，也不向页面发放令牌（`4xx` 中的 `OWNER_TOKEN_REQUIRED` 仅保留为历史错误码）。本机同源不是跨用户鉴权，生产主机请保持单用户本机专用。

| 方法 / 路由 | data / 输入 |
| --- | --- |
| GET `/api/agent/status` | service、dashboard_mode、manual_research_available、paused、worker_concurrency="1"、worker_error/worker_error_text、default/backup_model、models（含 authorization/authorization_text）、budget、usage_by_model、eod（latest 含 reason_text）、input、qualification |
| GET `/api/agent/tasks` | 最近 20 个 tasks 与 next_before；每项 id/kind/name/status/reason/reason_text/provider_id、起止时间、conclusion、calls（含 reason_text）、retryable |
| GET `/api/agent/tasks?before=<正整数ID>` | 向前翻页；只支持这一精确查询格式 |
| GET `/api/agent/tasks/<id>` | 原 request、冻结 input、provider_id/hash、kind、状态/reason/reason_text/时间、已保存 result（不变）与逐次 calls（含 reason_text）；不调用模型 |
| POST `/api/agent/tasks` | name/goal/scope、start_day/end_day（YYYY-MM-DD）、task_budget_micro（正整数字符串或 null）；返回持久 id + queued。安装版 dashboard 为观察者模式（`dashboard_mode=attached_explicit_operations`、`manual_research_available=false`）时返回 409 `MANUAL_RESEARCH_UNAVAILABLE_IN_BACKGROUND_MODE`，因为后台 watch 是唯一研究执行者 |
| POST `/api/agent/budget` | `{"daily_limit_micro":"5000000","monthly_limit_micro":"100000000","confirm_below_committed":false,"currency":"CNY(仅未配置首次可写)","timezone":"Asia/Shanghai(仅未配置首次可写)"}`；成功 200 `{"budget": <与 status.budget 同结构>}`；400 `BUDGET_INPUT_INVALID`/`BUDGET_CONFIG_INVALID`，409 `BUDGET_BELOW_COMMITTED`/`BUDGET_CURRENCY_TIMEZONE_IMMUTABLE`/`BUDGET_CONFLICT_REREAD` |
| POST `/api/agent/tasks/<id>/cancel` | `{}`；queued→cancelled，running→cancel_requested；不声明外部计费已撤销 |
| POST `/api/agent/tasks/<id>/retry` | `{}`；只有 failed、所有尝试确认 no_charge 且调用次数少于 2 时可重新排队 |
| POST `/api/agent/control` | `{"action":"pause"}` / resume；`{"action":"eod","enabled":true}`；`{"action":"model","model_id":"已保存ID"}` / backup |

models 只展示 id/label/kind/model/endpoint、authorization/authorization_text、price_version 与 verification，不含环境变量值/Key/grant 写入接口。`authorization_text` 仅在 `authorization` 是可映射错误码时给中文（`authorized` 时为 null）。`reason_text`/`worker_error_text`/`eod.latest.reason_text`/`calls[].reason_text` 由后端集中中文映射：未知码一律 null，调用方保留显示“原因未记录”的兜底；原始英文码仍保留在对应 `reason`/`worker_error` 字段，供诊断区展示。备用仅保存，不自动 fallback。预算可通过 `POST /api/agent/budget` 由 Owner 在 Web 修改（原子写 settings + 审计，币种/时区首次后不可变）；价格、授权、端点和 Key 仍只通过 Owner 本机可信设置维护，Web 不提供 Key 写入、清锁或授权扩写。

### 固定状态语义（后端修复，无前端接口结构变更）

- `eod.latest` 继续为 null 或 `{source_day,disposition,reason_text}`；`reason_text` 是该记录关联任务 reason 的中文映射，无关联任务或未知码时为 null。有关联 `eod-v1:<源日>` 任务时，disposition 读取权威任务状态：queued/running/completed/failed/cancel_requested/cancelled/outcome_uncertain；过期跳过保留 skipped_superseded，没有任务的暂停跳过保留 skipped_paused。旧版遗留的 queued 调度标记无需迁移，读取时即可显示实际完成/失败状态。`eod.reason` 仍表示调度原因，不是任务执行状态。去重仍沿用原 trigger_key，不重新调用 Provider。
- `models[].availability` 保留 `not_verified / last_task_completed / unavailable_or_outcome_unknown` 三个值，仅由相同配置版本的 Provider 调用观察或 DNS/客户端连接准备故障决定。`last_reason` 对应这次 Provider 观察；从未有 Provider 观察时为 null。本地预算/授权/价格/输入拒绝，以及发送前的取消或重启，不会将模型误标为不可用，也不会覆盖此前的 Provider 故障或成功观察。
- 本地拒绝保持原任务状态与 reason 错误码（如 failed + DAILY_BUDGET_EXHAUSTED / AUTHORIZATION_REQUIRED），当前配置资格由 authorization 表示，限额及未结清预留由 budget 表示。这些字段不作为 Provider 故障统计；未知费用仍保留，失败任务的重试权限不变。

budget 中包含 currency/timezone/day/month、daily/monthly_limit_micro、daily/monthly_settled_micro、reserved_micro（所有未结清周期）、daily/monthly_remaining_micro、call_count（尝试数）、input/output_tokens、usage_estimate_micro、billing。调用详情还包含 maximum_micro/settled_micro/usage_micro、price_version、原始预留 day/month 和 state。`usage_received` 仍保留最大预留；最终账单未核定不是精确消费。

result 包含 research.hypothesis/evidence/risks/next_steps，及可信生成的 provider/model、input_summary_version/source_day/input_mode、generated_at、synthetic_provider、qualification、limitations、billing。Provider 文本没有代码、交易、文件或工具权限。详情和列表从持久结果读取，不进行二次推理。

M2-PR06 显式 `--agent-eod-store <name>` 使用独立 `forward_eod_research_summary_v1`，与旧报告/评价输入互斥；未配置时行为不变。输入版本为 `eod-agent-input-v1:<snapshot SHA>`，仅本地 fake/显式任务；真实模型返回 `EOD_SNAPSHOT_LOCAL_FAKE_ONLY`，自动 EOD 为 `EOD_SNAPSHOT_MANUAL_ONLY`，不产生调用。status.input 是最近一次已校验投影，新的任务必须重新读取当前 store；已存详情保留原 frozen input，不代表当前 store 仍可用。没有新增账户 API、Web 路由或前端。完整字段与 headless 操作见 [M2-PR06](M2_PR06.md)。

## 错误

403 LOCAL_ORIGIN_REQUIRED/EXPLICIT_ORIGIN_REQUIRED/SAME_ORIGIN_REQUIRED（0.3.0 单机同源模型不再返回 401 OWNER_TOKEN_REQUIRED，该错误码仅作历史保留）；413 BODY_LIMIT；415 JSON_REQUIRED；404 AGENT_ROUTE_NOT_FOUND/TASK_NOT_FOUND；405 不支持的方法。Agent 没启动或初始化失败时为 503 AGENT_NOT_CONFIGURED，Paper API 继续可用。

任务/配置拒绝通常为 409，code 指明 TASK_INPUT_INVALID、TASK_BUDGET_EXHAUSTED、MODEL_NOT_CONFIGURED、TASK_RETRY_UNSAFE_OR_EXHAUSTED、MANUAL_RESEARCH_UNAVAILABLE_IN_BACKGROUND_MODE、BUDGET_BELOW_COMMITTED、BUDGET_CURRENCY_TIMEZONE_IMMUTABLE、BUDGET_CONFLICT_REREAD 等；预算输入格式错误为 400 BUDGET_INPUT_INVALID。后台失败保存在 task.reason：BUDGET_UNCONFIGURED、PRICE_UNCONFIGURED/PRICE_UNBOUNDED、AUTHORIZATION_REQUIRED、PROVIDER_KEY_MISSING、DAILY/MONTHLY_BUDGET_EXHAUSTED、PINNED_MODEL_CONFIGURATION_CHANGED 等。真实传输错误一律保留不确定费用、不自动重发。内部 SQLite/请求调试内容不回传。

`/api/health` 的 service=online 只说明本机服务可达；agent=local_research_available 也不保证 Provider、预算或策略资格。研究完整状态由经过本机同源校验的 status 查询。
