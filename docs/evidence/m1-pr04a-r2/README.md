# PR #8 R2：晚到补录不再隐藏当日漏采

2026-10-28，Windows x64，Codex 既有工作树；起点 `27f349d3adb61af5dbdf52c0b4f66f2b21ea3a9d`，回应 [P1 FAIL](https://github.com/handFOOLed/Stratide/pull/8#issuecomment-6469292633)。**Sol 修复与自测，不是独立验收 PASS；最终 HEAD 见 PR，Sol 不合并。**

## 修复与边界

旧日报把“目标交易日下存在任意 attempt”作为当天覆盖，次日首次补录便会隐藏当天漏采。`report.rs` 改为仅使用当日实际发起、且未跨日成为 late_backfill 的尝试判断覆盖；该内部字段不序列化，不改变 journal/schema/时间/原始响应或摘要链。

- 开市日漏采后补录：同一交易日同时显示 `gap_no_collection_on_open_day` 与原 `valid_eod / late_backfill=true`。
- gap 行无虚构 run、observed/received/available、价格或 NAV；日历实际后到时间单列，晚到 attempt 的原实际时间与哈希保留。
- 当日确实尝试但失败：保留原错误，不伪称从未尝试。观察开始以前的补录不虚构开始前缺口。
- 既有报表不覆盖；修复后报告内容有变化时用新目录。v3 财务账本、Risk Kernel、撮合、provider 与资金权限未改。

## 合成复现与回归

新增 `late_backfill_keeps_missed_day_gap_in_json_csv_and_after_restart`：人工起点为 10/27、当天未采，10/28 才收到人工日历及 10/27 日线。原报告逻辑实际运行该测试 FAIL/exit=101：[修复前](regression-before.txt)。相同回归修复后 PASS：[修复后](regression-after.txt)。

```powershell
./scripts/with-msvc.ps1 test -p stratide-forward --locked --offline late_backfill_keeps_missed_day_gap_in_json_csv_and_after_restart
```

实际导出的 [JSON](synthetic-gap-report/report.json)、[CSV](synthetic-gap-report/daily.csv)、[events](synthetic-gap-report/events.json) **全部是人工 synthetic fixture，不是另一真实市场日**。10/27 同时存在无取得时刻的 gap 行及 `2026-10-28T17:00:00+08:00` 的晚到行，均由测试实际导出并断言。关闭 journal 后重新打开，三份报告逐字节一致，日志 HEAD 不变。另增“当日失败保留”和“观察起点以前不造 gap”两项边界回归。

可选 `STRATIDE_SYNTHETIC_GAP_REPORT=<绝对新目录>` 仅在测试程序中导出人工报告，生产 CLI 不支持此开关/历史时间注入。首次辅助导出相对路径因 Cargo 测试 cwd 在 crate 下失败，见 [记录](artifact-export-path-failure.txt)；改为绝对路径后通过，未删除该记录。

Rust/Cargo 1.98.1、现有 MSVC；本次修改 Rust 后重新运行以下命令，**89 项测试通过（原 86 + 新增 3；forward 单测 12）**，详见 [最终输出](self-test.txt)，不以旧测试冒充新执行：

```powershell
cargo fmt --all -- --check
./scripts/with-msvc.ps1 check --workspace --locked --offline
./scripts/with-msvc.ps1 test --workspace --locked --offline
./scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline '--' -D warnings
```

## 真实 CLI smoke 与旧证据

新目录 `state/pr04a-r2-smoke-20261028/observer` 实际开始于 `2026-10-28T21:07:07.808+08:00`。实际执行 source-check（HTTPS daily/trade_cal 各一行）、collect-once、跨进程 status/report 和同 HEAD 重报；共 4 次小请求，无轮询/采购/券商。见 [脱敏探测](http-probe.json)、[状态](real-status.json)、[哈希校验](real-collection-metadata.json)。

新日志 **3 事件、1 尝试、1 有效前向日、0 提案、0 成交，NAV/回撤 null**，HEAD `dd145c62834bc68f2a16ed2c06a7f18a106a4550c37864f401b90f0a47f6d19a`。只读重算链/尾标/两个 raw SHA、Decimal 整数分/股和时间先后通过。真实价格、原始响应、CSV/JSON 与 SQLite 仅留本机。报告：`state/pr04a-r2-smoke-20261028/report/report.json`、`daily.csv`。

原 R1 真实日志仍为 7 事件和 HEAD `b7ba4a86e05c8ce3cf71c755afa8e7db2ff31fd3056b8b2ff6d12c610c084f52`；原 5 事件 blocked 日志、旧报告也核对未变。新旧日志都是同一真实交易日，不能合计声称第二个前向日。远端仅凭哈希不能复算未上传的 raw，独立复验需合法访问本机证据。

## 当前流程和限制披露

**开发工具执行记录曾包含明文 Token。** Owner 已接受提供 Token 及执行记录风险，不要求书面许可、旧 Token 轮换、密码库、目录迁移或虚拟机作为本轮个人本机开发/验收前置；是否轮换由 Owner 决定。本文不重现值。保留环境变量入口，Token 不进 Git、PR/Issue、应用输出、应用日志或外部错误消息；文件搜索未命中不等于历史没有暴露。

Owner 对个人非商业本机用途的确认、供应商授权未经独立核实、未获原始行情公开分发范围分别披露。旧 FAIL/BLOCKED 保留并标为历史。一次真实当日采集加完整测试/报告可申请 PR04A 验收；多日持续观察和独立开盘成交留 PR04B。真实限流/停牌/修订、Linux/macOS、磁盘满/物理断电、开盘/时段/费用与可信买卖仍未验证。等待最终 SHA 独立复验、小猫审查及 Owner 合并授权。
