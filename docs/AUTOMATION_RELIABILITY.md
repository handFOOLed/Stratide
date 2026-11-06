# 自动化可用性修复记录（2026-11-06）

> **工程资料**：本页包含已发生的诊断或实现记录，不代替产品手册与当前源码。
>
> [文档中心](README.md) · [当前版本](STATUS.md) · [架构总览](ARCHITECTURE_OVERVIEW.md)

> Owner 要求“产品真正自动化可用”，并允许修改后端。本文件记录真实安装的阻断原因、
> 修复、在隔离数据副本上的端到端验证、以及仍然存在的诚实限制。
> 独立只读诊断报告见 [`evidence/automation/independent-diagnosis.md`](evidence/automation/independent-diagnosis.md)。

## 1. 真实安装观察到的阻断

| 现象 | 根因 | 修复 |
| --- | --- | --- |
| 20261105 研究 `MARKET_RESEARCH_LOCAL_FAILURE`，无 traceback | 安装版 dashboard 以 `Agent::open` 持有 `data/agent/agent.lock`；watch 的本地 TimesFM（`research/timesfm_cpu/cli.py` 同时取 worker.lock + agent.lock）拿不到锁，异常被压成通用码 | supervisor 启动 dashboard 加 `--agent-observer`；dashboard `Agent::attach` 且不启动内置 worker，后台 watch 成为唯一研究执行者；Python 记录异常类型/摘要并转写 bridge stderr |
| 研究失败无冷却、日志爆炸 | 通用本地失败不在冷却列表 | `MARKET_RESEARCH_LOCAL_FAILURE`/bridge/WSL/worker 失败统一 600s 冷却 |
| 代码更新后 `SCREEN_IMPLEMENTATION_CHANGED_NEW_RUN_REQUIRED` 永久卡死 | 已运行 run 固定旧实现哈希，拒绝重建 | 未派发云端任务的 BLOCKED run 在代码/规则变化时重建 screen/plan；一旦有 `fusion_task_id` 仍严格拒绝 |
| 旧本地 TimesFM 任务与更新后的 plan 不一致 → `LOCAL_PIN_CHANGED_NEW_TASK_REQUIRED` | 本地任务过期但输入不同 | 无 calls 的本地任务允许审计替换（meta `timesfm_cpu_superseded:*`），付费任务仍不可重放 |
| paper confirmation/freeze 永远 `PAPER_LOCAL_INPUT_OR_LEDGER_UNAVAILABLE` | 账本已创建但从未配置 `fixed-ticket-paper-v1` Policy；`paper_portfolio.once` 抛 `OWNER_PORTFOLIO_POLICY_REQUIRED` 被吞 | 新增 `paper_portfolio.ensure_policy(market)`：首次成功采集后按最新 READY 快照自动写入默认 Paper-only 策略（幂等）；watch 每轮先 ensure 再 confirm/freeze |
| 云端桥 `MARKET_PARENT_BINDING` | run 的 `as_of`（`+00:00`）与 plan 的 `as_of`（`Z`）字符串比较 | 边界改为解析 RFC3339 后比较 |
| 云端返回 `PORTFOLIO_SCHEMA`（首次真实计费调用） | DeepSeek JSON 模式回显顶层 `"type":"json_object"`；严格结构体拒绝未知字段 | 解析边界仅剥离该传输回显字段；其余契约校验不变；失败响应写本地 stderr（不重发、不影响审计） |
| Paper freeze `TASK_ID_INVALID` | `fusion_task_id` 是字符串，桥接需要整数 | `int(run["fusion_task_id"])` |

## 2. 隔离副本端到端验证（真实数据复制，不改真实账本）

数据副本：`state/automation-probe/data`（520 MB，复制真实安装数据根）；Paper binding 指向副本账本；
诊断期间发现并修复过一次误写真实 Agent DB 的诊断脚本，已按失败前快照恢复运行记录并删除误建伪任务；
后续所有写验证均在副本执行。

时间：2026-11-05 23:10–2026-11-06 00:30（Asia/Shanghai）。

| 步骤 | 结果 |
| --- | --- |
| 原始 BLOCKED run（旧实现哈希 + 已冻结 plan，无 `fusion_task_id`）直接重跑 | 自动重建 screen/plan → `TIMESFM_DONE`，reason `AUTOMATIC_CLOUD_DISABLED`（副本关闭云端时） |
| `paper_portfolio.ensure_policy`（真实快照 5217 只主板证券、逐证券费率、Batch/100 股、¥100,000 名义、2 只、单票 ¥20,000） | `CONFIGURED`；再次调用 `EXISTS`；`confirm` → `CONFIRMATION_CHECKED` |
| 打开副本云端、固定同日盘后决策时间后重放真实研究 | 最新桥接二进制下：`CANDIDATE_FROZEN`、`cloud_status=FUSION_DONE`、`events=[EOD_RECEIVED,SCREENED,TIMESFM_DONE,FUSION_DONE,CANDIDATE_FROZEN]`、`fusion_task_id=258`；本地 registry 已写 candidate |
| Paper freeze（副本） | 通过 task id 修复后不再 `TASK_ID_INVALID`；剩余时间校验只受“诊断用固定时钟 vs 真实注册时间”影响，真实同日晚间流程不受影响 |

云端请求与响应：真实 DeepSeek 调用成功返回 HTTP 200；响应 `model=deepseek-flash`、`finish_reason=stop`；
内容为契约 JSON 但多出 `"type":"json_object"` 回显。剥离后通过严格 portfolio/结论/未验证假说校验。

## 3. 真实安装更新与接口验证

- 备份：`F:\Stratide-backup-20261105-2340`（应用文件、bin、dashboard、research、scripts；不含 data/runtime）。
- 已安装：新 `stratided.exe`、`stratide-cli.exe`、`stratide-launcher.exe`、`bin/*` worker、冻结前端 dist、
  research/scripts Python 模块；保留原数据目录与凭据。
- 真实 dashboard：`dashboard_mode=attached_explicit_operations`、`manual_research_available=false`、
  `agent.lock` 不再由 dashboard 持有；health 200。
- API 端到端（新 exe fixture，`scripts/test-dashboard-api.py --expect-new-fields`）：**57 checks / 0 failures / 2 skips**；
  覆盖预算 POST、低于 committed 确认、币种不可变、通知字段与 unread_count、撤销首次设置、runtime build 字段。
- 前端：`npx tsc --noEmit`、`npm test`（7/7）、`npm run build` 通过；Playwright **20/20**（含真实 exe fixture、
  协议接受、失败态、移动端、主题、键盘与 11 页术语巡检）。
- Rust：WSL 交叉 `cargo build/check --target x86_64-pc-windows-gnu` 通过；budget_admin 10/10、desktop 6/6、
  status_regression 11/11 等 Windows 测试二进制在 Windows 主机执行通过（依赖仓库相对型 sample fixture 的几个旧测试
  在交叉 exe 下因 Linux 编译期绝对路径不可用而失败，属测试环境限制，未能据此判定代码失败）。

## 4. 真实计费/外发记录（诚实披露）

| 调用 | 结果 | 计费状态 |
| --- | --- | --- |
| 2026-11-05 15:48Z 真实安装 market research | `outcome_uncertain`，原因 `MARKET_PROVIDER_RESPONSE_REJECTED_NO_RETRY`；calls=1，maximum held 98,304 micro CNY | 计费未核定；按产品规则不自动重试 |
| 诊断用隔离副本云调用（固定时点重放） | 最终成功 `CANDIDATE_FROZEN`；另有 1 次失败用于捕获响应体 | 通过副本 Agent 预算配置，不写真实 calls 账本；为工程诊断额外少量费用，未用于任何自动交易 |

## 5. 仍未解决 / 下一步

1. **20261105 不补跑**：已有 `outcome_uncertain` 的付费任务按“未知结果不重试”保留；下一个交易日（2026-11-06）
   晚间 watch 会用修复后的代码创建新 run。
2. **Paper 成交确认**：冻结批次后需 T+1 开盘日线；本记录验证到冻结，成交/费用/NAV 由后续真实 EOD 确认。
3. **观察者模式下手动研究禁用**：产品当前以自动研究为唯一执行者；UI 已解释，不提供假按钮。
4. **跨日补跑**：研究要求同日盘后 84 会话上下文，午夜后不补跑（时点规则，非缺陷）。
5. `docs/UI_BACKEND_REQUIREMENTS.md` 的 B3/B7 仍保持“不伪造时间”的现状，不因自动化改造而放宽。
