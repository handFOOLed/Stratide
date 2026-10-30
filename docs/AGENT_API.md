# Agent V1 本机 API

与 [原 Paper API](DASHBOARD_API.md) 共用 127.0.0.1 同源静态服务与 `{api_version,state,snapshot,data,error}` 信封。旧账户/订单路由保持 GET，写入仍为 405。业务金额/ID/用量以十进制字符串返回；预算单位是 micro_currency_1e-6，不是 Paper 的 fen。

## 权限与请求

所有 `/api/agent/…` 读写都需 `X-Stratide-Owner: <本机owner-token>`，响应不返回令牌。POST 还必须显式带与 Host 完整一致的 `Origin: http://127.0.0.1:<port>`（localhost 需完全对应）、`Content-Type: application/json` 和不超过 8192 字节的 Content-Length；Sec-Fetch-Site 如有必须为 same-origin/none。缺失 Origin 不能因 Host 正确而通过。没有 CORS、Cookie、跨站登录或任意文件/命令/URL 参数。JSON 拒绝额外字段。

| 方法 / 路由 | data / 输入 |
| --- | --- |
| GET `/api/agent/status` | service、paused、worker_concurrency="1"、worker_error、default/backup_model、models、budget、usage_by_model、eod、input、qualification |
| GET `/api/agent/tasks` | 最近 20 个 tasks 与 next_before；每项 id/name/status/reason/provider_id、起止时间、conclusion、calls、retryable |
| GET `/api/agent/tasks?before=<正整数ID>` | 向前翻页；只支持这一精确查询格式 |
| GET `/api/agent/tasks/<id>` | 原 request、冻结 input、provider_id/hash、状态/原因/时间、已保存 result 与逐次 calls；不调用模型 |
| POST `/api/agent/tasks` | name/goal/scope、start_day/end_day（YYYY-MM-DD）、task_budget_micro（正整数字符串或 null）；返回持久 id + queued |
| POST `/api/agent/tasks/<id>/cancel` | `{}`；queued→cancelled，running→cancel_requested；不声明外部计费已撤销 |
| POST `/api/agent/tasks/<id>/retry` | `{}`；只有 failed、所有尝试确认 no_charge 且调用次数少于 2 时可重新排队 |
| POST `/api/agent/control` | `{"action":"pause"}` / resume；`{"action":"eod","enabled":true}`；`{"action":"model","model_id":"已保存ID"}` / backup |

models 只展示 id/label/kind/model/endpoint、authorization、price_version 与 verification，不含环境变量值/Key/grant 写入接口。备用仅保存，不自动 fallback。预算、价格、授权和端点只通过 Owner 本机可信设置维护，Web 不提供额度加额/清锁或 Key 写入。

### 固定状态语义（后端修复，无前端接口结构变更）

- `eod.latest` 继续为 null 或 `{source_day,disposition}`。有关联 `eod-v1:<源日>` 任务时，disposition 读取权威任务状态：queued/running/completed/failed/cancel_requested/cancelled/outcome_uncertain；过期跳过保留 skipped_superseded，没有任务的暂停跳过保留 skipped_paused。旧版遗留的 queued 调度标记无需迁移，读取时即可显示实际完成/失败状态。`eod.reason` 仍表示调度原因，不是任务执行状态。去重仍沿用原 trigger_key，不重新调用 Provider。
- `models[].availability` 保留 `not_verified / last_task_completed / unavailable_or_outcome_unknown` 三个值，仅由相同配置版本的 Provider 调用观察或 DNS/客户端连接准备故障决定。`last_reason` 对应这次 Provider 观察；从未有 Provider 观察时为 null。本地预算/授权/价格/输入拒绝，以及发送前的取消或重启，不会将模型误标为不可用，也不会覆盖此前的 Provider 故障或成功观察。
- 本地拒绝保持原任务状态与 reason 错误码（如 failed + DAILY_BUDGET_EXHAUSTED / AUTHORIZATION_REQUIRED），当前配置资格由 authorization 表示，限额及未结清预留由 budget 表示。这些字段不作为 Provider 故障统计；未知费用仍保留，失败任务的重试权限不变。

budget 中包含 currency/timezone/day/month、daily/monthly_limit_micro、daily/monthly_settled_micro、reserved_micro（所有未结清周期）、daily/monthly_remaining_micro、call_count（尝试数）、input/output_tokens、usage_estimate_micro、billing。调用详情还包含 maximum_micro/settled_micro/usage_micro、price_version、原始预留 day/month 和 state。`usage_received` 仍保留最大预留；最终账单未核定不是精确消费。

result 包含 research.hypothesis/evidence/risks/next_steps，及可信生成的 provider/model、input_summary_version/source_day/input_mode、generated_at、synthetic_provider、qualification、limitations、billing。Provider 文本没有代码、交易、文件或工具权限。详情和列表从持久结果读取，不进行二次推理。

M2-PR06 显式 `--agent-eod-store <name>` 使用独立 `forward_eod_research_summary_v1`，与旧报告/评价输入互斥；未配置时行为不变。输入版本为 `eod-agent-input-v1:<snapshot SHA>`，仅本地 fake/显式任务；真实模型返回 `EOD_SNAPSHOT_LOCAL_FAKE_ONLY`，自动 EOD 为 `EOD_SNAPSHOT_MANUAL_ONLY`，不产生调用。status.input 是最近一次已校验投影，新的任务必须重新读取当前 store；已存详情保留原 frozen input，不代表当前 store 仍可用。没有新增账户 API、Web 路由或前端。完整字段与 headless 操作见 [M2-PR06](M2_PR06.md)。

## 错误

401 OWNER_TOKEN_REQUIRED；403 LOCAL_ORIGIN_REQUIRED/EXPLICIT_ORIGIN_REQUIRED/SAME_ORIGIN_REQUIRED；413 BODY_LIMIT；415 JSON_REQUIRED；404 AGENT_ROUTE_NOT_FOUND/TASK_NOT_FOUND；405 不支持的方法。Agent 没启动或初始化失败时为 503 AGENT_NOT_CONFIGURED，Paper API 继续可用。

任务/配置拒绝通常为 409，code 指明 TASK_INPUT_INVALID、TASK_BUDGET_EXHAUSTED、MODEL_NOT_CONFIGURED、TASK_RETRY_UNSAFE_OR_EXHAUSTED 等。后台失败保存在 task.reason：BUDGET_UNCONFIGURED、PRICE_UNCONFIGURED/PRICE_UNBOUNDED、AUTHORIZATION_REQUIRED、PROVIDER_KEY_MISSING、DAILY/MONTHLY_BUDGET_EXHAUSTED、PINNED_MODEL_CONFIGURATION_CHANGED 等。真实传输错误一律保留不确定费用、不自动重发。内部 SQLite/请求调试内容不回传。

`/api/health` 的 service=online 只说明本机服务可达；agent=local_research_available 也不保证 Provider、预算或策略资格。研究完整状态由经过 Owner 认证的 status 查询。
