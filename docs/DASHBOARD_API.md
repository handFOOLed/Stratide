# Dashboard V1 只读 API

## Issue #77：当前账户与研究扩展

`GET /api/v1/{account,equity,positions,strategies,fills,orders}` 读取显式 `--paper-ledger` 的当前 Paper 账本。未配置时返回 409 `CURRENT_PAPER_ACCOUNT_UNCONFIGURED`；所选历史报告不会替代当前 NAV。原 `GET /api/{account,...}` 保持所选报告语义；同时配置时历史页仍读原报告。显式 synthetic 演示始终保留合成标记。账本写入者保持原 SQLite EXCLUSIVE 生命周期；写入尚未退出时读取可失败，不能用旧报告冒充新数据。

`GET /api/v1/workspace` 返回 `schema_version=1` 的原 CPU/Fusion/OOS/Registry、证据和备份状态，`paper_allowed/live_allowed=false`；读取不会推理、创建任务或调用 Provider。研究数值保持原报告的比值/计数单位；Paper 金额/股数仍按下节十进制字符串。操作、配置和恢复见 [V1_COMPLETION](V1_COMPLETION.md)。

仅用于 127.0.0.1 本地 paper-only Dashboard，默认端口 8710。Owner 启动时选定一个已发布六报告目录。没有 HTTP 文件路径参数、账户切换或财务写入路由。M2-PR02 的研究任务写操作单独限定在经过本机同源校验的 `/api/agent/…`，见 [Agent API](AGENT_API.md)；下文 Paper 账户路由仍只读。

## 响应与数字

金额单位为人民币分，股份为整数股，收益率为整数基点。**业务整数全部以十进制字符串返回**，包括金额、股数、日期、时间戳、订单 ID；只有 api_version 是 JSON 数字。显式缺值为 null，数组为空不代表缺文件。

以下为仓库 synthetic_test 样例响应节选（实际接口包含完整 metadata）：

```json
{
  "api_version": 1,
  "state": "ready",
  "snapshot": {
    "mode": "synthetic_test",
    "source_version": "fixture-v1",
    "as_of": "20261102",
    "last_day": "20261102",
    "evidence_class": "engine_test_only",
    "publication": "last_published_snapshot",
    "refresh_policy": "explicit_process_restart",
    "forward_account": "not_available",
    "market_freshness": "snapshot_only_not_live",
    "gaps": []
  },
  "data": {
    "nav_fen": "992893",
    "cash_fen": "992893",
    "available_cash_fen": "992893",
    "session_pnl_fen": "-76",
    "cumulative_pnl_fen": "-7107"
  },
  "error": null
}
```

snapshot 还含 snapshot_id（固定六文件内容摘要）、report_sha256、input_sha256、ledger_head、source、first_day、timezone、last_valid_valuation_at（毫秒字符串或 null）、validation、execution_model、historical_assumptions、missing_opening_evidence_sessions、unverified_status_sessions、unobserved_calendar_days_including_weekends。后者包含休市日，不能称为丢失交易日。as_of 是最后有效 NAV 日，last_day 是报告末日；缺估值时可能不同。不同请求的 snapshot_id 不一致时前端拒绝组合显示。

state 为 ready / no_input / invalid_snapshot；健康、研究和路由错误也保留该账户状态。没有有效账户快照时 snapshot 为 null。业务失败时 data 为 null，error 为 `{ "code": "…", "message": "…" }`，不回传内部路径或原始 JSON。

## GET 端点

| 路由 | data |
| --- | --- |
| `/api/health` | service=online、paper_only、快照/前向账户/Agent/通知/刷新状态；不等于风控运行正常或市场新鲜 |
| `/api/account` | account_id、day、NAV/cash/available/reserved、源日/累计 P&L、total_return_bps、max_daily_observation_drawdown_bps、total_fee_fen、valuation_error、initial_nav_fen、external_flow_total_fen、原快照 risk、deployment |
| `/api/equity` | 按日期排列的 day、nav_fen、cash_fen、cumulative_pnl_fen、return_bps、valuation_error；保留 null |
| `/api/positions` | 单证券持仓 instrument、quantity、sellable/unsettled/reserved_sell_shares、market_value_fen、cost_basis_fen、unrealized_pnl_fen、原 lots、deployment；price_series=null+reason |
| `/api/strategies` | report config 的 deployment，status=snapshot_record_only，独立 pnl/drawdown=null+reason |
| `/api/fills` | 仅原 fills：fill_id、order_id、day、instrument、side、quantity、price_fen、fee_fen、费用拆分、simulated_at、risk_checked_at、deployment、execution_assumption、source_version |
| `/api/orders` | 原 orders：order_id、day、instrument、side、quantity、remaining、limit_fen、status、reason、deployment、confirmed_filled_shares（只汇总原有模拟 fills） |
| `/api/research` | results + status；未配置为空数组。配置后 kind=independent_research_result、account_inclusion=false、原证据等级与区段摘要，绝不汇入其余端点 |

当前财务格式仅接受 synthetic_test / historical_replay。forward_paper 需要未来真实前向财务格式与独立验证；observe-only schema 1041 报告明确拒绝。

订单保持原始枚举 Open / PartiallyFilled / Filled / Rejected / Expired，中文翻译仅用于 UI。原 reason 原样以文本展示。simulated_at 是模拟记账时间，risk_checked_at 是开盘审查/历史模型时间，都不是券商真实成交时间。

## 状态码与边界

| HTTP | code / 用途 |
| --- | --- |
| 200 | 成功；health 在报告未配置/损坏时仍说明 Web 服务可达 |
| 409 | NO_SNAPSHOT：没有明确指定报告 |
| 503 | INVALID_SNAPSHOT / INVALID_RESEARCH：缺文件、损坏、不支持格式、读取期间变化、金额/摘要或六报告不一致 |
| 403 | LOCAL_ORIGIN_REQUIRED：Host 不在本机白名单，或提供了不同源 Origin |
| 405 | READ_ONLY：所有非 GET 请求 |
| 404 | NOT_FOUND：未列出的精确路径，含查询参数、编码路径和目录穿越 |

无宽松 CORS、无 cookie/远程登录、无任意磁盘静态目录。静态资源仅允许 `/`、`/assets/app.js`、`/assets/app.css`。响应 Cache-Control: no-store，并设置 CSP、禁止 frame 与 nosniff。API 来自启动时固定内存快照。远程访问、写权限和敏感配置需另立任务。

## /api/runtime/status 与首次设置标记（Windows 安装包）

安装态另有 `/api/runtime/*` 诊断/配置接口（见 [M3_PR04](M3_PR04.md)），只监听本机并由 Supervisor 注入的 `runtime.json` 提供布局。响应同为 `{api_version,state,snapshot,data,error}` 信封，但字段为安装态诊断而非 Paper 账本。

`GET /api/runtime/status` 在 0.3.0 新增以下字段（既有字段语义不变）：

| 字段 | 含义 |
| --- | --- |
| `build` | `{version, commit, built_at}`，读安装目录 `BUILD_INFO.json`；源码树运行没有该文件时三个字段均为 null，不伪造构建信息 |
| `repo_url` | 固定 `https://github.com/handFOOLed/Stratide`，供“关于”页打开项目主页 |
| `issues_url` | 固定 `https://github.com/handFOOLed/Stratide/issues`，供“反馈”入口 |
| `setup_complete` | 首次设置完成标记是否存在；语义不变 |

`POST /api/runtime/setup-complete`（本机同源 + JSON；0.3.0 原行为是只写标记）：

- `{}` 或省略 `completed`：写入标记，返回 `{state:"COMPLETE", setup_complete:true, completed_at:"<RFC3339>"}`，向后兼容。
- `{"completed":false}`：删除标记以撤销“已标记完成”，返回 `{state:"INCOMPLETE", setup_complete:false, completed_at:null}`；标记本就不存在时同样返回成功（目标状态已成立，幂等）。
- `completed` 存在但不是布尔值：`400 SETUP_INPUT_INVALID`；写/删标记失败：`409 SETUP_MARKER_WRITE_FAILED` / `SETUP_MARKER_DELETE_FAILED`。
- 写接口仍要求同源 `Origin`、`Content-Type: application/json` 与有界 Content-Length；读取 `/api/runtime/status` 不受影响。撤销只删除该标记文件，不动设置、账本、研究任务或预算。

## 安装版观察者模式（2026-11-06）

- Supervisor 启动 dashboard 时传 `--agent-observer`；dashboard 使用 `Agent::attach`，不持有 `data/agent/agent.lock`，
  也不启动内置研究 worker。后台 `eod watch` 是唯一研究执行者（本地 TimesFM + 云端全市场研究 + Paper 模拟）。
- `GET /api/agent/status` 新增 `dashboard_mode`（`worker` / `attached_explicit_operations`）与
  `manual_research_available`（安装版为 false）。观察者模式仍可读取、暂停、撤销首次设置、编辑预算，
  但 `POST /api/agent/tasks` 返回 409 `MANUAL_RESEARCH_UNAVAILABLE_IN_BACKGROUND_MODE`。
- 开发/测试直接运行 `stratided`（不带 `--agent-observer`）保持原 worker 行为，便于手动研究联调。
