# M1-PR04B：连续真实 EOD 观察流程与开盘证据研究

**R2：R1 HEAD `36bcbb80e1a5c4eec629543e753ff07fd83f1a8f` 独立验收暂不通过。** 新发现的“旧日补录引入当日日历冲突后仍 ready”已修复；[R2 回归与证据](evidence/m1-pr04b-r2/README.md) 保留原探针失败和开发自测。当前新 HEAD 仍须独立复验，以下 R1 是历史修复记录。

**R1 修复状态：原 HEAD `945b2501ec4fb3b02f02da6c7253a77a525c2be1` 独立验收不通过，三项 P1 已修复并补充开发回归；需对 PR 新 HEAD 重新独立验收。** [拒绝结论及修复证据](evidence/m1-pr04b-r1/README.md) 保留旧失败与新自测边界。仍为 Draft、未合并、未接入 Paper 成交。

状态：**工程自测完成后提交 Draft；真实连续多交易日及独立开盘尚待验证，M1 未完成，不合并。** 基线为 2026-10-28 fetch 的最新 `main`：`e41adc7`。开发分支 `codex/m1-pr04b-eod`；不改既有 Owner 分支、PR04A 日志或财务内核。自测不是 Terra 独立验收或小猫源码审查。

## 范围与风险

按 P0 守住时间可得性和成交权限：真实 EOD 的 `open` 不能回填开盘执行，后到修订不能改变旧时点输入。按 P1 完成连续操作、缺口完整性和恢复。继续复用 PR04A 的 `1041` journal、原始响应、时间戳、单写入者、摘要链、采集限制与不可覆盖报告；没有修改 genesis、迁移数据库、增加凭据或引入新数据供应商。

`crates/forward` 仍不依赖 contracts/risk/ledger，不生成订单、资金或策略提案；M0 撮合、Risk Kernel 和财务账本未修改。没有 GUI、Agent、券商、后台服务、任务计划安装、付费 API 采购或 CI。来源许可继续沿用 Owner 已接受的个人非商业本地用途声明，未宣称独立供应商认证；旧明文 Token 执行记录风险继续保留，程序只使用当前进程环境变量。

## 每日流程

```text
forward-eod-step <原 journal> <新报告根目录>
  校验并恢复未完成意图（只追加 Interrupted，不重建未知响应）
  16:00 前：waiting，不请求 HTTP、不耗采集次数
  当日16:00后已有针对当日的持久化意图（含中断/未知）：跳过请求
  否则：复用 collect-once -> trade_cal + daily -> 原始响应事务
  按 HEAD 发布 report.json / daily.csv / events.json
```

日界线为 Asia/Shanghai。已提交的盘后 Started 即占用自动槽位，包含未完成和恢复后 Interrupted；重启只追加中断诊断，不自行再次请求。显式 `forward-collect-once` 可在每日最多 8 次的既有总限额内重试。16:00 前人工探测和旧交易日 backfill **不占用当日盘后槽位**。跨午夜收到的响应只记 late，不算当日有效观察或 ready。每天最多一次正常 EOD 步进不等于供应商长期稳定性已验证。

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

R2 的 readiness 使用**当前全部已知的当日日历证据**，包括其他交易日补录返回的日历；冲突会撤销原有 ready，并返回 `already_attempted_today:calendar_conflict`。这是当前操作状态，不回写原成功尝试或释放/重复消费自动槽位。旧日补录仅引入其他日期冲突时，不因此撤销当日已有成功结果。

“逐日期隔离”仅指**已有有效 EOD 的读取及上述当日 readiness 校验**。新采集依然保守地整次拒绝：同一日历响应中任意日期与旧证据冲突，整个新 outcome 记 `calendar_conflict` 并丢弃标准化 bar；即使新 bar 所属日期本身无冲突，也不会被接纳。这可能造成连续观察缺口，本轮未放宽它，不能宣称新采集已完全按日期隔离。

`report.json.continuity` 对初始化至**日志最后事件时刻**逐自然日汇总：`valid_eod / missing_valid_eod / market_closed / calendar_unknown / calendar_conflict / awaiting_eod_window`，包含同日尝试数、晚到数、日历实收时间及最长已知开市日缺口。休市不打断已知开市缺口，未知/冲突打断可确认的连续性；不能把未知日历视为休市或完整覆盖。晚到补录不修复当日覆盖，失败的当日尝试与从未尝试的缺口仍分别留在原 CSV/JSON。

报告是 journal 的冻结视图，不是当前市场状态。无新事件时，10/29 上午导出的报告范围仍截至 10/28；CLI 步进 JSON 单独说明当前日期与 waiting。后续真实采集取得覆盖漏掉日期的日历时，原有缺口检测会补充诊断和真实取得时间，不能补造旧日观察。既有 `status.actual_valid_forward_days` 保留历史成功计数；`continuity` 再考虑后来发生的日历冲突，因此两者在冲突时可能不同，不能拿历史计数宣称当前无缺口。

新增只读审计命令：

```powershell
# as-of 是 UTC epoch 毫秒；只选已有日志中当时可得的版本，不改变采集时间。
& $cli forward-eod-at $observer 20261028 1793192840089 # 原实际可得前1毫秒：view=null
& $cli forward-eod-at $observer 20261028 1793192840090 # 恰好可得：可读旧EOD版本
```

读取须同时满足记录的完成时间、`available_at` 与原始接收时间不晚于 as-of；只选有效 EOD，晚到或修订不能提前出现。`available_at` 表示进程完成校验后、提交 SQLite 前采样的墙钟，**不等于原始接收时间，也不是精确的事务提交/其他读取者持久可读时刻**。此命令审计的是已提交日志中记录的进程内时间；不能据此证明某读取者恰好在该毫秒读到数据。输出及报告提供 `available_at_semantics`，旧事件与字段不回写。

日历冲突逐目标日期累计判断：其他日期的冲突不遮蔽本日期已有的有效 EOD。时钟回拨按追加顺序处理：保留故障前有序事件前缀中不晚于 `previous_high_water` 的历史视图；超过该边界则因时间关系不明返回 null，故障之后的事件不混入旧前缀。`clock_uncertainty` 说明故障序号、前缀边界和回拨后的原始检测值；`detected_at` 不能用作故障发生的精确墙钟。历史前缀不表示系统时钟获外部认证，采集仍永久 halt，不自动解锁。输出始终 `opening_execution_eligible=false`，仅用于审计，**没有订单执行能力**。生产采集 CLI 没有 `--now`、历史时钟注入或原始数据导入入口；测试内部时间 seam 不对外暴露。

R1 报告增加上述语义元数据，journal schema 1041 不变；报告仍 schema 2 的追加字段。为保留原报告，本次修复后请使用新的报告根目录（如 `state/pr04b-r1/reports`），不要覆盖 `state/pr04b/reports`。

## 实际验证与仍需等真实日期的项目

[自测和保留证据](evidence/m1-pr04b/README.md) 区分三类：人工 `synthetic_test` 故障回归、PR04A 已有真实原始 journal 的离线续用、待将来取得的真实市场观察。2026-10-28 同日跳过及 10/29 上午 waiting 均未发新 HTTP；已有真实日志仍 **3 事件、1 有效前向日、0 提案、0 成交、NAV/回撤 unavailable**，旧数据库及三份旧报告哈希未变。真实整数时间戳边界检查通过；初次 PowerShell 辅助脚本丢毫秒的失败单独保留。

独立开盘研究见 [来源、时段、费用和接入条件](M1_PR04B_OPENING_EVIDENCE.md)：当前官方 `stk_auction` 窗口是 09:26–09:29，`stk_auction_o` 是 20:00 盘后更新。文档不是窗口内实收证据；9:26 后生成的新提案不能回填9:25集合竞价。未购买权限或调用它们。交易所现行时段已有出处；实际开盘可得性、完整费用假设/取整和当日证券可交易规则尚未验明，因此**本 PR 当时不接入 Paper 成交**。

**2026-11-04 现行补充：** T 日盘后取得并校验的 T 日 `daily.open` 是 T 日已知的可信历史输入，可用于研究并冻结 T+1 决策；**T 日的 open 不能作为 T+1 成交价**。若采用 T+1 `daily.open` 作为 Paper 成交价假设，需待 T+1 盘后取得该字段，并按 T 日已冻结的意图、数量和撮合规则事后确认，标 `EX_POST_OPEN_ASSUMPTION`；不得观察 T+1 结果后选择性下单、撤单或改价，也不能冒充开盘实收。停牌、费用、公司行为、现金/股数及唯一 Risk→Execution→Ledger 的逐笔检查不放宽。 `stk_auction` 是可选增强，未取得时继续标 `NOT_VERIFIED`，不挡工程合并。

Draft 后仍待：连续至少两个真实未来交易日采集及隔日复核；真实晚到/缺数/修订/网络异常现场；独立开盘实收；具体费用/时段/可成交性条件。Linux/macOS、物理断电/磁盘满未验证，Terra 同 SHA 独立验收和小猫源码审查未进行。只完成可立即复验的工程增量，不宣称 M1 完成或投资表现。
