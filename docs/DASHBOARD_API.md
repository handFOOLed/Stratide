# Dashboard V1 只读 API

仅用于 127.0.0.1 本地 paper-only Dashboard，默认端口 8710。Owner 启动时选定一个已发布六报告目录。没有 HTTP 文件路径参数、账户切换或财务写入路由。M2-PR02 的研究任务写操作单独限定在经过 Owner 认证的 `/api/agent/…`，见 [Agent API](AGENT_API.md)；下文 Paper 账户路由仍只读。

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
