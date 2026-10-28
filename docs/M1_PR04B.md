# M1-PR04B：连续真实 EOD 观察流程与开盘证据研究

状态：**工程自测完成后提交 Draft；真实连续多交易日及独立开盘尚待验证，M1 未完成，不合并。** 基线为 2026-10-28 fetch 的最新 `main`：`e41adc7`。开发分支 `codex/m1-pr04b-eod`；不改既有 Owner 分支、PR04A 日志或财务内核。自测不是 Terra 独立验收或小猫源码审查。

## 范围与风险

按 P0 守住时间可得性和成交权限：真实 EOD 的 `open` 不能回填开盘执行，后到修订不能改变旧时点输入。按 P1 完成连续操作、缺口完整性和恢复。继续复用 PR04A 的 `1041` journal、原始响应、时间戳、单写入者、摘要链、采集限制与不可覆盖报告；没有修改 genesis、迁移数据库、增加凭据或引入新数据供应商。

`crates/forward` 仍不依赖 contracts/risk/ledger，不生成订单、资金或策略提案；M0 撮合、Risk Kernel 和财务账本未修改。没有 GUI、Agent、券商、后台服务、任务计划安装、付费 API 采购或 CI。来源许可继续沿用 Owner 已接受的个人非商业本地用途声明，未宣称独立供应商认证；旧明文 Token 执行记录风险继续保留，程序只使用当前进程环境变量。

## 每日流程

```text
forward-eod-step <原 journal> <新报告根目录>
  校验并恢复未完成意图（只追加 Interrupted，不重建未知响应）
  16:00 前：waiting，不请求 HTTP、不耗采集次数
  当日16:00后已有针对当日的完成尝试：跳过请求
  否则：复用 collect-once -> trade_cal + daily -> 原始响应事务
  按 HEAD 发布 report.json / daily.csv / events.json
```

日界线为 Asia/Shanghai。失败的盘后尝试也占用当日自动槽位，重启不会自行再请求；显式 `forward-collect-once` 可在每日最多 8 次的既有总限额内重试。16:00 前人工探测和旧交易日 backfill **不占用当日盘后槽位**。跨午夜收到的响应只记 late，不算当日有效观察或 ready。每天最多一次正常 EOD 步进不等于供应商长期稳定性已验证。

失败/时钟 halt 仍尝试导出已提交诊断；导出失败不会撤销已提交的采集，原目录保留。报告按 `<报告根目录>/<journal HEAD>` 发布，相同 HEAD 可重报，新 HEAD 新目录。报告格式升至 schema 2，仅增加完整性摘要；**journal schema 仍为 1041**。旧报告不能用新格式覆盖，应选新的报告根目录。报告根目录应与 journal、旧报告目录分开。

```powershell
./scripts/with-msvc.ps1 build -p stratide-cli --locked --offline
$cli = './target/debug/stratide-cli.exe'
# 从本 PR 工作树运行，复用已授权 PR04A 真实目录；不要重新初始化它。
$observer = '../m1-pr04a-worktree/state/pr04a-r2-smoke-20261028/observer'
& $cli forward-status $observer
& $cli forward-eod-step $observer state/pr04b/reports

# 可选：当前 PowerShell 前台等待，每日16:00后做一次，最多5个自然日期。
# 使用已有本人合法凭据，在当前进程安全设置 STRATIDE_TUSHARE_TOKEN；不要打印/写入文件。
./scripts/observe-eod.ps1 -Journal $observer -Reports state/pr04b/reports -Watch -MaxDays 5

# 失败后先查 status / 新报告；确认后显式重试并重新导出。
& $cli forward-collect-once $observer
& $cli forward-eod-step $observer state/pr04b/reports
# 若补录漏采日，只保留今天真实取得时间，不把它算过去当日覆盖。
& $cli forward-collect-once $observer --trade-day 20261028
```

前台脚本默认只执行一次；`-Watch` 每分钟只查本机时钟，达到窗口才启动 CLI。失败立即退出，Ctrl+C 可停，进程退出/电脑休眠期间没有观察承诺；重启脚本继续读原 journal，不追溯补造漏掉的价格。`MaxDays` 是处理的自然日期数，含休市日，不是成功交易日数。本次**没有启动无人值守采集、安装调度任务或持久保存 Token**。当前进程没有 Tushare Token；2026-10-29 上午步进只验证 waiting，不假装第二个 EOD 已发生。

## 日报完整性与未来函数防护

`report.json.continuity` 对初始化至**日志最后事件时刻**逐自然日汇总：`valid_eod / missing_valid_eod / market_closed / calendar_unknown / calendar_conflict / awaiting_eod_window`，包含同日尝试数、晚到数、日历实收时间及最长已知开市日缺口。休市不打断已知开市缺口，未知/冲突打断可确认的连续性；不能把未知日历视为休市或完整覆盖。晚到补录不修复当日覆盖，失败的当日尝试与从未尝试的缺口仍分别留在原 CSV/JSON。

报告是 journal 的冻结视图，不是当前市场状态。无新事件时，10/29 上午导出的报告范围仍截至 10/28；CLI 步进 JSON 单独说明当前日期与 waiting。后续真实采集取得覆盖漏掉日期的日历时，原有缺口检测会补充诊断和真实取得时间，不能补造旧日观察。既有 `status.actual_valid_forward_days` 保留历史成功计数；`continuity` 再考虑后来发生的日历冲突，因此两者在冲突时可能不同，不能拿历史计数宣称当前无缺口。

新增只读审计命令：

```powershell
# as-of 是 UTC epoch 毫秒；只选已有日志中当时可得的版本，不改变采集时间。
& $cli forward-eod-at $observer 20261028 1793192840089 # 原实际可得前1毫秒：view=null
& $cli forward-eod-at $observer 20261028 1793192840090 # 恰好可得：可读旧EOD版本
```

读取须同时满足完成时间、`available_at` 与原始接收时间不晚于 as-of；只选有效 EOD，晚到或修订只能从其真正可得时间开始出现。该时点已知的日历冲突/时钟故障拒绝返回数据，未来冲突不能改写之前的审计视图。输出始终 `opening_execution_eligible=false`，仅用于审计，**没有订单执行能力**。生产采集 CLI 没有 `--now`、历史时钟注入或原始数据导入入口。当地摘要链的信任局限与 PR04A 一致，不承诺防御完整权限重写或外部授时认证。

## 实际验证与仍需等真实日期的项目

[自测和保留证据](evidence/m1-pr04b/README.md) 区分三类：人工 `synthetic_test` 故障回归、PR04A 已有真实原始 journal 的离线续用、待将来取得的真实市场观察。2026-10-28 同日跳过及 10/29 上午 waiting 均未发新 HTTP；已有真实日志仍 **3 事件、1 有效前向日、0 提案、0 成交、NAV/回撤 unavailable**，旧数据库及三份旧报告哈希未变。真实整数时间戳边界检查通过；初次 PowerShell 辅助脚本丢毫秒的失败单独保留。

独立开盘研究见 [来源、时段、费用和接入条件](M1_PR04B_OPENING_EVIDENCE.md)：当前官方 `stk_auction` 窗口是 09:26–09:29，`stk_auction_o` 是 20:00 盘后更新。文档不是窗口内实收证据；9:26 后生成的新提案不能回填9:25集合竞价。未购买权限或调用它们。交易所现行时段已有出处；实际开盘可得性、完整费用假设/取整和当日证券可交易规则尚未验明，因此**本 PR 不接入 Paper 成交**。

Draft 后仍待：连续至少两个真实未来交易日采集及隔日复核；真实晚到/缺数/修订/网络异常现场；独立开盘实收；具体费用/时段/可成交性条件。Linux/macOS、物理断电/磁盘满未验证，Terra 同 SHA 独立验收和小猫源码审查未进行。只完成可立即复验的工程增量，不宣称 M1 完成或投资表现。
