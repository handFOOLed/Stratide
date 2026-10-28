# M1-PR04A：真实 EOD 来源探测与 observe-only 观察日志

**当前进展（2026-10-28，R2）：** 已修复晚到补录隐藏当日漏采的 P1，补充 JSON/CSV、重新打开日志后的报告回归和新路径真实 CLI smoke，见 [R2 修复记录](evidence/m1-pr04a-r2/README.md)。既有真实 EOD 已入本机 journal，仍只有 1 个有效前向日，0 提案/成交。按 Owner 最新决定，个人非商业本机研究可继续开发与验收，不额外强制供应商书面证明、旧 Token 轮换、密码库、迁移目录或虚拟机；Owner 用途声明与未经独立核实的供应商许可分别披露。开发工具执行记录曾含 Token 明文，不能把“未进 Git/应用日志”泛化为未暴露。Sol 不合并，等待最终 SHA 独立复验与小猫审查。

**历史状态：首次提交 f801dd5 时为 Draft / BLOCKED。** 当时：**本机真实 HTTPS 接口访问及关键字段通过 Sol 自测；自动盘后采集与持久保存许可仍未核验。没有成功真实采集入 journal，不能宣称 PR04A 真实数据验收完成。** 任务 [Issue #7](https://github.com/handFOOLed/Stratide/issues/7)，基线为 fetch 后的 `main`：`4b53cf8`（完整基线见 PR）。Sol 不合并；Terra 对准确 HEAD 独立验收，小猫同 SHA 源码审查并经 Owner 授权后受控合并。

## 已交付边界

P1：时间可得性、来源证据、恢复和缺口；P0：错误行情不得产生交易、不得泄漏凭证或触碰财务账本。新增 `crates/forward` 不依赖 contracts/risk/ledger，也没有提案、撮合、成交或资金写入 API。现有 `DataMode::{SyntheticTest, HistoricalReplay}`、v3 账本、Risk Kernel 和历史回放代码/摘要不改；观察存储单独使用 schema `1041`、`forward_observation_only_v1`。观察身份不创建 funded paper account，本金、风险参数、NAV、回撤都不可用，不默认赋值为零或十万元。

```text
forward-init -> 冻结观察配置 + 实际初始化时刻
forward-source-check -> 官方 HTTPS 小范围权限/字段探测 -> 只输出时间、状态、计数、哈希
forward-collect-once -> 提交 Started -> 许可检查 -> trade_cal / daily -> 提交 Finished + 原始响应
forward-status / forward-report -> 校验全部摘要链与尾标 -> 状态 / CSV + JSON
                                            没有通往订单或资金账本的路径
```

## 可运行命令

在仓库根目录，现有 Rust/MSVC 工具链；不安装服务，不启用任务计划，不产生付费 CI。

```powershell
./scripts/with-msvc.ps1 build -p stratide-cli --locked
New-Item -ItemType Directory -Force state | Out-Null
$cli = './target/debug/stratide-cli.exe'
& $cli forward-init state/my-observer samples/m1-pr04a-observer.json

# 仅在当前进程配置 STRATIDE_TUSHARE_TOKEN；不要粘贴到日志或提交 .env。
# 此命令只探测已有权限，不购买权限、不保存原始行情，也不产生 forward 证据。
& $cli forward-source-check state/my-observer

& $cli forward-collect-once state/my-observer
# 当前样例应返回 exit=2、blocked_source_license_unverified；诊断已持久记录。
& $cli forward-status state/my-observer
& $cli forward-report state/my-observer state/my-observer-report-1
Import-Csv state/my-observer-report-1/daily.csv | Format-Table
Get-Content state/my-observer-report-1/report.json

# 后续每次新进程打开同一日志目录；新 HEAD 用新报告目录。
# 晚到数据只能作为今天实际取得的 backfill，不能冒充昨天曾收到：
& $cli forward-collect-once state/my-observer --trade-day 20261027
```

许可配置是 genesis 内冻结的 Owner 声明，不是 API 成功即可自动升级的合规认证。`license_note` 应引用适用协议/供应商确认及范围，`local_automation_and_raw_storage_authorized` 当前为 **false**，本轮未私自设 true。未来确认许可后，Owner 用带有效依据的配置创建**新观察目录**；旧目录、初始化时刻、失败事件保留。不能编辑配置文件改变已有观察，也不把先前探测包装响应导入为原始 HTTP 观察。GitHub 原始行情存储权未确认，因此本 PR 只提交脱敏元数据和没有行情值的 blocked 日报。

## 时间、响应与恢复语义

- 日界线固定 `Asia/Shanghai`，UTC epoch 毫秒与带 `+08:00` 的可读时间并存。时间来自真实墙钟，没有生产 CLI 的 `--now` 或历史时间注入选项。初始化不能追溯前移。
- 同机目录 OS 文件锁覆盖网络和事务全过程，数据库 `synchronous=FULL`。每个采集开始先持久提交；退出后未完成意图显示 incomplete，下次采集追加 interrupted，不假设请求成功或未发生。网络无自动重试、每请求 20 秒、每响应 1 MiB；collect 每个本地自然日最多 8 次人工尝试。无跨机互斥承诺。
- 许可不明/Token 缺失记录 blocked；网络、HTTP 429/权限错误、字段变更、无日线、日历不完整分别记录诊断。仅请求固定 `https://api.tushare.pro`，禁止重定向，不接受任意目标 URL，不用 HTTP 明文降级。
- 许可确认后的响应实体原字节、SHA-256、HTTP 状态、接口/版本、接收时刻及服务端 `Date` 存在同一个 Finished 事务内；摘要链包括这些字节。`provider_published_at=null`；文档更新窗口不是逐条发布时间。日线 `available_at` 在校验完成时取本机实际完成时间，不早于原始接收；不借接口 `trade_date` 回填。
- 墙钟倒退、采集中墙钟与单调钟偏差超过 5 秒会追加诊断并持久 halt；重启不自动清除。只有所有原始响应的 HTTPS `Date` 与接收时间偏差在 5 分钟内才记 `valid_eod`；缺失/不一致记 `clock_unverified`。这是粗粒度异常检测，**不是第三方授时证明**；跨进程时钟向前跳且随后与服务端一致、精细时钟误差未独立验证。Owner 校验时钟后可新开观察目录，不改旧证据。
- 同日相同标准化 OHLCV 追加 attempt 并指向 `duplicate_of`；不同值指向 `revision_of`，原始响应和原事件保留。raw-response SHA 仍区分原始字节的变化。有效日数按交易日去重，同日修订不增加天数。昨日数据今天首次取得、跨午夜才完成的数据标记 `late_backfill`，不计有效当日前向日数。
- 日历从上次成功取得的日历日界线到今天查询，包含未运行日期；超过 366 天只记范围过大需核查。晚到补录不会遮蔽观察起点以后开市日当天的漏采；日报同时保留缺口行与晚到 attempt，观察起点以前不虚构缺口，当天失败尝试仍显示实际错误。晚到日历对未观察日期只能补充“今天才查明当时开市/休市”的诊断，并附实际日历接收时刻；不能补造当日行情。相互矛盾日历标记 conflict，不挑有利版本。没有日历的日期保持 unknown；日线缺行不等于停牌或零价。
- 16:00 前当日 collect 即使日历开市也只记发布窗口未就绪；不会把盘中字段当完整日线。单次验证成功不代表长期稳定。未复权价格精确换算整数分，成交量由手乘 100 为整数股；拒绝更细的非整分/非整股值、无效 OHLC 和溢出，不舍入或浮点补正。
- 每次打开验证 schema、SQLite 完整性、事件连续序列、摘要链、raw SHA 和提交尾标；不自动初始化空/坏/旧日志。SQL 触发器拒绝 UPDATE/DELETE。普通改写/截断可检测；**本地链不能防止具备完整文件写权限者重算整个链、替换完整备份或控制系统时间**。未接入外部不可变锚点，不声称绝对不可篡改。

## 日报与实际结果

每个 HEAD 导出 `report.json`、`daily.csv`、`events.json`。CSV 每条尝试含交易日/观察和接收时刻、原始 daily JSON（仅许可允许后）、标准化整数分/股、单位、source/endpoint/timezone、校验状态、日历实际取得时刻、尝试序号、重复/修订/晚到标记、原始响应哈希和暂停原因。日报没有策略提案或模拟成交；没有市场参考收益、账户收益或虚构费用。NAV/回撤为 `null`/空 CSV，原因随报告提供。缺口表覆盖初始化至日志最新事件时刻，报告不是后台监控当前市场状态。

报表先在同级暂存目录完整写入同步，再改名发布。相同 HEAD 重报逐字节一致；新 HEAD 不覆盖旧报告，需显式新目录。不完整/冲突目录保留，换新目录重报；进程意外中断留下的暂存目录不当作成功发布。

以下为首次提交时的历史实际输出（不是合成行情）；当前真实入库见 R1/R2：

| 检查 | 实际结果 |
| --- | --- |
| 本地 HTTPS daily/trade_cal | 均成功 1 行，价格/量/日期/证券及日历字段校验通过；只保留元数据，[探测输出](evidence/m1-pr04a/http-probe.json) |
| observe-only journal | 初始化实际本地时刻；2 次许可阻断 attempt，共 5 个持久事件；[实际状态](evidence/m1-pr04a/blocked-status.json) |
| 有效前向日数 / 策略提案 / 模拟成交 | **0 / 0 / 0** |
| NAV / 回撤 | **unavailable** |
| 本地运行目录 | `state/pr04a-owner-observer`；原始凭证从未写入此目录 |
| 本地最终日报 | `state/pr04a-blocked-report-final`；[脱敏 JSON 副本](evidence/m1-pr04a/blocked-report.json)、[CSV 副本](evidence/m1-pr04a/blocked-daily.csv) |

完整 [来源报告](M1_PR04A_SOURCE_FEASIBILITY.md) 和 [自测说明](evidence/m1-pr04a/README.md) 分开记录权限成功、许可未确认及没有真实采集入 journal 的限制。探测响应没有保留原字节，哈希不能让验收者离线复算该响应，只能由 Owner/Terra 在合法授权范围内重新探测；不把它说成完整原始证据归档。

## 首次提交的历史自测与未覆盖范围（当前以 R2 为准）

Windows x64/MSVC、Rust/Cargo 1.98.1；[最终命令原始输出](evidence/m1-pr04a/self-test.txt)：fmt、check --locked、test --workspace --locked（86 项）、Clippy `-D warnings` 通过。依赖已下载后使用 `--offline` 固定本地验证。新增 9 项单测（包含一个子进程辅助入口）和 1 项跨进程 CLI 集成测试；synthetic fixture 只验证解析/时间/故障，不计真实市场前向日数。既有 76 项测试保留，财务内核、v3 schema、撮合和回放源码未修改。

最初沙箱下测试遇到原子目录改名 `Access is denied (os error 5)`，同时影响原有回放和新增报告测试；相同代码在已授权完整本机环境通过，未靠删测试解决。初次依赖下载因沙箱 DNS 失败，获准联网后下载成功。首次 PowerShell Clippy 未把 `--` 传给 Cargo，改为字面量 `'--'` 后严格检查成功；最终记录仅包含正确命令。

**未验收**：自动盘后持久保存许可、真实响应入 journal 的成功路径、连续两个真实未来交易日、真实限流/超时/停牌/节假日/修订现场、Linux/macOS、物理断电/磁盘满、独立开盘/时段覆盖/费用规则、任何可信 paper 买卖或收益。接口探测和合成单测都不能代替这些。Terra 独立验收与小猫审查尚未进行。本 PR 按 Issue 约定留 Draft/Blocked；下一步只解除来源许可门槛后开始真实 EOD journal 观察，仍不启用交易。
