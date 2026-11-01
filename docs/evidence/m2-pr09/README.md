# M2-PR09 开发证据

基线 `main` `6e3448d15b6e5fe47678d7aec37f4cf06980fd26`；按 [Issue #49](https://github.com/handFOOLed/Stratide/issues/49) 2026-11-01 09:30:30 UTC 最新正文执行。**开发者自测，不是独立验收。** 操作见 [M2_PR09](../../M2_PR09.md)。

以下保留初始 PR HEAD `5efcf624ff71a3b95c192b9000432a0ab14f6594` 的 15 项开发证据。PR #50 授权撤销竞态的修复、最新实现 SHA 与多进程反证另见 [R1](r1/README.md)，原 JSON/报告不重写。

## 实际结果

| 验证 | 结果 / 退出码 |
| --- | --- |
| `python -X utf8 -B scripts/test-eod-operator.py` | **15/15，exit 0**；冻结实现 SHA 见 [operator-e2e.json](operator-e2e.json)，原输出见 [operator-test.txt](operator-test.txt) |
| 双隔离目录，各 22 日 | 同一暖机/上交叉/下交叉序列；原 Snapshot/Shadow + 原 Rust Fake CLI；合计 44 tasks / 44 settled fake calls / 44 registrations；84 次 loopback HTTP，公共行情请求 0 |
| 四阶段真实进程中断 | Collector/Snapshot/Shadow/Fake 提交后 `os._exit(86)`；重启后各只采集一次、Fake 只结算一次 |
| 原 collector Started 后强杀 | 原 journal 标记未知；重启不请求、不重发 |
| Operator 自身 receipt 事务强杀 | 真实 hot DELETE journal；只读 report 不恢复/不改字节，once writer 自动回滚后复用原提交，不重跑子系统 |
| 单次 enable / 不同进程 once/watch / disable | 15:14 无请求；15:15 起 `EARLY_SOURCE_UNVERIFIED`；16:00 原单槽执行；无逐次授权标志；中途 disable 阻断下游，重启持续停用 |
| Windows 原生凭据 | 正常 Windows 用户会话下，唯一 synthetic test credential 写入/读取/删除通过；没有读取或配置真实 Token |
| 最重要反例 | 空行/未知/错误源日/休市/日历未知/限速/权限拒绝/缺 Token、双 writer、别名与 observer 复制、junction、源修订/坏 raw、T+1 晚补、Shadow/Auto 关闭、早期数据到 16:00 不升级；全部在上述 15 项中 |
| 只读审计 | status/history/verify/report 不调用 collector/sync/Shadow/Auto/凭据 API；原文件集合、字节、mtime 均不变；refs 与原提交、独立 Decimal 复算一致 |
| `python -X utf8 -B scripts/test-data-snapshot.py -v` | **11/11，exit 0** |
| `python -X utf8 -B scripts/test-forward-shadow.py --evidence` | **9/9，exit 0** |
| `python -X utf8 -B scripts/test-eod-auto.py --evidence` | 15 项通过；1 项因沙箱禁止创建 junction，exit 1。该项在正常 Windows 权限下单独重跑 **1/1，exit 0**，故全部 16 项覆盖通过 |
| `python -X utf8 -B scripts/test-research-review.py --evidence` | 正常 Windows 权限下 **12/12，exit 0**；沙箱首次同样在 junction 创建处受阻 |
| 原 Rust 全 workspace 安全回归 | **exit 0**，含原 forward 单槽/失败/未知、财务/账本/回放/研究权限测试；未修改任何 Rust |
| 原 CLI/Fake 构建；新生产入口 `--help`；`git diff --check` | 均 **exit 0** |

## 命令与环境

实际 Rust 命令（Windows PowerShell，已有工具链与缓存，未安装依赖）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 test -p stratide-research --bin eod-auto-agent --no-run --locked --offline
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 build -p stratide-cli -p stratide-research --bins --locked --offline

# 默认用户 TEMP 的原报告重命名测试出现 Access denied；改用本 worktree 的隔离 TEMP 后完整通过。
New-Item -ItemType Directory -Path state/test-tmp -Force | Out-Null
$env:TEMP = (Resolve-Path -LiteralPath state/test-tmp).Path
$env:TMP = $env:TEMP
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 test --workspace --locked --offline

# 唯一受阻的原 Auto 测试：正常 Windows 权限下补测，无需改原生产代码。
python -X utf8 -B scripts/test-eod-auto.py --test test_init_existing_directory_binding_and_junction_are_rejected
```

没有 Rust 修改，因此未另跑 fmt/check/clippy；实际 build 和完整安全 test 已执行。原生 Credential Manager 与部分 junction 创建在受限沙箱不可用，使用正常用户会话验证，仅操作新增 synthetic 状态/凭据。生产用户不需要每日重新配置凭据。

[cli-commands.json](cli-commands.json) 保留 215 条实际 CLI 命令、synthetic 时钟、故障点和退出码；observer 绝对路径用占位符脱敏，完整本地输入留在 gitignored 测试目录。[synthetic-report.json](synthetic-report.json) 是完整 22 日只读报告，含原 journal、snapshot、Shadow、Fake 的实际 SHA/ref；没有价格或 Token。不是预先手写的“成功样例”。[validation-summary.json](validation-summary.json) 列出命令、环境修复和明确未验证项。

## 红绿与原证据保全

- 模块实现前 `python -I -B scripts/eod-operator.py --help`：入口缺失，exit 1；实现后同命令 exit 0。
- `test_own_hot_receipt_recovers_only_in_writer_without_rerunning_children` 首次真实强杀后，重启 once 因 `STORE_BUSY_OR_RECOVERY_REQUIRED` exit 2，测试 exit 1；修复自身 writer 恢复后，针对性测试和最终完整 15 项均 exit 0。
- [preservation.json](preservation.json)：325 个基线受保护 tracked 文件（crates/apps/research Agent/samples/已有 evidence）与原 Git blob 内容一致；原 68/77 日证据与既有测试证据均未改。真实本机 runtime 数据未被选取、打开或重做 SHA 对比；本次没有真实采集，也未把旧保全结论冒充新真实账户验收。

## 解释范围

V1 采用 Issue 允许的 **16:00 正式单槽回退**，15:15 只做本地状态检查。未实现提前正式采集、明确 NOT_READY 的有限重试或 source revision 授权新分支。测试中的 collector 是严格限制到本机 loopback 的 schema-1041 协议夹具；真实 Rust collector 完全未改，另由原 Rust 回归覆盖。生产入口没有 clock/fault/HTTP endpoint 选项。

真实 Tushare 账户可用性、长期连续 watch、Linux/macOS、物理断电、真实新增 21 日前向观察仍 **NOT_VERIFIED**。公共行情 API 请求 **0**、真实 LLM 调用 **0**、真实新增前向日 **0**、orders/fills **0**、NAV **null**。`opening_source=BLOCKED`、`historical_pit=NOT_VERIFIED`、`forward_paper_allowed=false`、`live_allowed=false`。
