# PR #9 R1：三项 P1 修复与重新验收交接

**后续状态：本目录对应 R1 HEAD `36bcbb8`，独立验收暂不通过。** 原三项修复对应的回归通过，但新发现旧日补录引入当日冲突后 readiness 未撤销。见 [R2 修复与复验记录](../m1-pr04b-r2/README.md)。原 102 项自测和本目录失败记录不改写。

原验收 SHA `945b2501ec4fb3b02f02da6c7253a77a525c2be1`，基线 `e41adc71b3d28e02dc8a642c6b21101ca263ac0f`。**Owner 提供的独立验收结论为不通过**：中断后自动重试、后续回拨改写历史 as-of、响应级日历冲突遮蔽其他日期。原 97 项测试通过不能反证这些缺陷。验收方当时只检查真实 SQLite 完整性及计数，没有完整重算链/raw；本记录不扩大其声明。

本目录为 **Sol 开发修复、自测及离线只读复核**，不是新的独立验收 PASS。新准确 SHA 以 PR HEAD 为准，需重新独立验收。PR 保持 open/Draft，不合并；Paper 成交仍未接入。

## 修复与回归

1. **中断槽位**：盘后针对当天的持久化 Started 即占自动槽位，包含 pending 和 Interrupted。恢复先记 Interrupted，再返回 `already_attempted_today:interrupted_response_unknown`，不进入网络。显式 collect-once 仍可重试；早盘探测、旧日 backfill 和前一日中断不占新一天槽位。测试内部 `eod_step_at` 只为无网络的确定性回归，不暴露生产 CLI 时钟注入。
2. **回拨历史**：按事件追加序列遇到 ClockFault；回拨后的 `detected_at` 只作为诊断值。故障前有序前缀内 `as_of <= previous_high_water` 的视图保持不变；边界之后不推定时间顺序，返回 null。故障后的事件不进入旧前缀。CLI/报告的 `clock_uncertainty` 明示序号/前缀/检测值与限制；采集仍 halt，不清除故障。
3. **逐日期冲突**：as-of 对目标日期累计比较日历证据，与完整性摘要逐日规则一致；10/27 冲突只阻断该日期，10/28 已有有效 EOD 保留，10/27 更早时点视图也不被后到冲突重写。整次响应仍保留原 `calendar_conflict` 诊断，不重新接受被拒新 bar 或改写旧事件。
4. **可得时间定义**：`available_at` 是进程完成校验时、SQLite 提交前采样的墙钟，不是准确提交时间或另一个读取者当时可读的证明。字段/schema/旧事实不回写；EodView、CLI、报告显式给出语义。不宣称提交延迟有已知上界。

四项最小回归先在旧生产逻辑运行，全 FAIL（包括分别检查 pending 槽位和自动恢复路径），见 [修复前实际输出](regression-before.txt)。修复后再补一项子进程测试，覆盖 Started/Finished 各自提交前后真实进程退出，**5 项全部通过**，见 [修复后输出](regression-after.txt)。本轮 sandbox 在报告目录改名处再次 Access denied，见 [保留失败](regression-after-sandbox-failed.txt)；同源码在本机权限下通过。所有日期/数据为 **synthetic_test**，未变成真实观察证据。

```powershell
./scripts/with-msvc.ps1 test -p stratide-forward --locked --offline tests::r1::
cargo fmt --all -- --check
./scripts/with-msvc.ps1 check --workspace --locked --offline
./scripts/with-msvc.ps1 test --workspace --locked --offline
./scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline '--' -D warnings
```

最终 Windows 离线全量 **102 项测试通过**（原 97 + R1 新增 5），fmt、workspace check 与严格 Clippy 均 exit=0。原始输出见本目录 `test.txt / fmt.txt / check.txt / clippy.txt`，源码指纹见 `self-test-metadata.json`。首次严格 Clippy 发现单分支 match 应使用 if-let，实际修改后通过，原失败输出保留为 `clippy-first-failed.txt`；没有 suppress/删除检查，环境 hard-link 警告也保留。新实现不改 provider、风险、财务账本或依赖；旧自测/失败及真实数据保留。R1 增加报告语义元数据后，请用新报告根目录，不覆盖旧报告。

## 真实 journal 的完整只读复核

```powershell
python scripts/verify-forward-readonly.py ../m1-pr04a-worktree/state/pr04a-r2-smoke-20261028/observer/forward.sqlite
```

本轮通过标准库 SQLite **mode=ro + query_only + 只读事务**实际复算完整事件序列与 SHA-256 链、checkpoint、2 份 raw 摘要、交易日历及 1 行日线整数分/股换算、实际时间先后和服务端 Date 粗校验。见 [脱敏元数据](real-journal-readonly.json)。数据库前后 SHA-256 均 `c86536eee8bcdc2dd0d22cc7505d5fb9d5e8569c3e288bf6b7a79e2f796762f8`，原文件未变。仍为 3 事件/1 checkpoint、1 有效真实前向日；没有新 HTTP、没有上传行情原始值，也没有新增前向观察。脚本不导出 raw 或证券价格，不写源数据库。

这比仅做 integrity_check/计数覆盖更多，但仍是开发侧离线复核，不是独立供应商认证、重新实时采集或第二真实交易日。连续真实日、真实晚到/修订、独立开盘实收、费用/当日规则仍 **NOT VERIFIED**；Linux/macOS、物理断电/磁盘满未验证。新 SHA 的独立测试和源码审查需另行进行，不能沿用旧 SHA 的结论。
