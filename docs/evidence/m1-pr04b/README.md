# PR04B：工程自测、真实日志续用及未完成观察

**历史记录：本目录对应原提交 `945b250` 的自测，不代表独立验收通过。** 后续独立验收发现中断自动重试、回拨历史查询、跨日期冲突三项 P1 并拒绝该 SHA；见 [R1 拒绝记录、修复和新自测](../m1-pr04b-r1/README.md)。本目录旧结果与失败保留。

2026-10-28 至 2026-10-29，Windows x64、既有 Rust/Cargo/MSVC，基线 `e41adc71b3d28e02dc8a642c6b21101ca263ac0f`。**本目录是 Sol 工程自测，不是 Terra 独立验收 PASS 或 ChatGPT 独立源码审查。PR 保持 Draft，不合并。**

## 实际执行的离线验证

```powershell
cargo fmt --all -- --check
./scripts/with-msvc.ps1 check --workspace --locked --offline
./scripts/with-msvc.ps1 test --workspace --locked --offline
./scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline '--' -D warnings
```

最终 **97 项测试通过**（PR04A 的 89 + 7 项 forward 单测 + 1 项 CLI 集成测试），无删除/忽略旧测试。见 [完整测试输出](test.txt)、[check](check.txt)、[Clippy](clippy.txt)；fmt 无输出且 exit=0。Clippy exit=0，日志保留沙箱中增量缓存无法 hard-link、改为复制的环境警告，不把它当代码诊断或隐藏。Windows 工具链与源码指纹见 [自测元数据](self-test-metadata.json)。

新增回归全部使用显式 **synthetic_test** fixture，人工日期推进不计真实观察天数：

- 盘后失败占用自动槽位，跨进程重开不自动重试；早盘探测/旧日 backfill 不占当天 EOD 槽位。
- 跨午夜响应保留原实际时间、标记 late，不计当日完整性或 ready。
- 实际子进程在 **Finished 响应事务提交前/后**退出：提交前仍是 pending、原始响应未知；提交后只出现一次已提交响应。恢复不得重建未知响应或伪造成功。
- EOD 在开盘/可得前不可读，实际可得后读取正确版本；后到修订/晚到只能从各自可得时间出现，旧 HEAD 和旧版本不被改写。
- 多日开市缺口、当日失败、休市、晚到并存；JSON 完整性摘要准确，重开后 CSV/JSON/原始事件逐字节一致。
- 未知日历/后来冲突不能认证完整覆盖，冲突不能改变更早的 as-of 视图；CLI 拒绝采集 `--now`。

首次沙箱执行在既有报告原子目录改名测试失败（Access denied），见 [失败摘录](sandbox-test-first-failure.txt)；同代码在获准本机环境完整通过。没有放宽断言或删除失败测试。

## 已有真实 PR04A journal 原位续用

复用本机 `../m1-pr04a-worktree/state/pr04a-r2-smoke-20261028/observer`，不创建/复制新的真实观察，不改既有 genesis 或行情事实。本次没有可用进程 Token，也未从其他项目取密钥。**新行情 HTTP 调用为 0**；公开网页研究不等于行情实收。

2026-10-28 盘后实际执行 `forward-eod-step` 后，再经 `observe-eod.ps1` 独立进程执行一次，均返回 `already_attempted_today:valid_eod / collected=false`，HEAD 相同。2026-10-29 07:38 再运行返回 `waiting_eod_publication_window / collected=false`，没有追溯补造第二天。日报仍按日志最后事件截至 10/28，与当前日期分开显示。

旧日志仍 **3 事件、1 尝试、1 有效前向日、0 提案、0 成交、NAV/回撤 null**，HEAD `dd145c62834bc68f2a16ed2c06a7f18a106a4550c37864f401b90f0a47f6d19a`。新报告只写本 PR 忽略的 `state/pr04b/reports/<HEAD>/`，不覆盖原报告；旧数据库及三份旧报告 SHA-256 全部不变。

首次辅助检查把 `ConvertFrom-Json` 得到的时间对象转成默认字符串再解析，丢失 90 毫秒，错误地查询了 `1793192840000`，导致“可得时刻应有值”断言失败。保留 [首次失败元数据](real-continuation-first-probe-failed.json)，不把它改写为 PASS。随后直接使用 events.json 的 **整数 `available_at=1793192840090`**：前 1 毫秒无数据、恰好可得有数据、`opening_execution_eligible=false`，见 [成功复验元数据](real-continuation-metadata.json)。这是辅助检查时间转换问题，没有修改应用时间语义或旧日志。

真实 raw/价格/CSV/events/SQLite 只保留本机；Git 只收脱敏计数、时间、哈希和诊断。远端哈希不能代替对本机 raw 的独立复算；Terra 验收需合法访问本机来源证据，不把人工 fixture 当真实源。

## 未验证与下一次真实检查

第二个真实 EOD 尚未到来；至少两个连续真实交易日的稳定采集、真实晚到/断线/停牌/修订、窗口内 `stk_auction` 访问与实际原始开盘证据、具体证券规则及完整费用假设/计费取整均 **NOT VERIFIED**。开盘研究只给出了官方资料与接入条件，不能解除成交暂停。

可在本人已授权的当前进程配置凭据后使用 [PR04B 前台命令](../../M1_PR04B.md) 继续观察；本次没有安装任务或启动无人值守进程。Linux/macOS、磁盘满/物理断电、Terra 独立验收及小猫源码审查未运行。Paper 财务账本没有接入这些 EOD 数据，M1 未完成，没有收益或实盘安全结论。
