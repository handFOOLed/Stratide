# PR #9 R2：旧日补录引入当日冲突必须撤销 readiness

原 HEAD `36bcbb80e1a5c4eec629543e753ff07fd83f1a8f`、基线 `e41adc71b3d28e02dc8a642c6b21101ca263ac0f`。Owner 提供的 R1 独立验收为**暂不通过**：原三项修复及 102 项原测试通过，但旧日补录返回的当日日历冲突未撤销当日 `ready=true`。这一结论保留，不能用原测试绿灯替代。原报告中的真实 journal 复核属于独立执行的离线复核，不是新行情采集或供应商认证。

本目录为 **Sol R2 修复、自测和保全检查**。新准确 SHA 见 PR HEAD，需重新独立验收；PR 保持 open/Draft、未合并，Paper 成交未接入。

## 修复

P1，生产修改仅在 `eod_existing_step`：继续由当天盘后持久化 Started/Finished/Interrupted 决定自动槽位，同时累计**全部已知 CollectionFinished 中针对当天的日历证据**，不受采集目标交易日限制。若当天证据冲突，当前步进改为 `ready=false / already_attempted_today:calendar_conflict / collected=false`。既有 CLI 对该非 waiting 的失败状态走错误出口；不产生新 HTTP、不释放槽位、不修改原成功事件、原 bar 或补录诊断。

此处按当前证据判断操作 readiness，不是历史 as-of 查询。冲突不能被后续有利日历覆盖；其他日期的冲突不因本修复撤销当日已有成功结果。原 R1 的中断槽位、回拨边界、已有 EOD 的逐日期读取保持。

**保守接纳边界未改变：** 新采集的任意日期日历与旧证据冲突时，store 仍整次拒绝新 outcome，保留 `calendar_conflict` 并丢弃标准化 bar。即使新 bar 所属日期未冲突，也不会接纳；这可能造成连续观察缺口。“逐日期隔离”仅适用于已有有效 EOD 的读取和当前 readiness 证据校验，不表示新采集完全按日期隔离。

## 探针与测试

从 Owner 指定的本机只读文件 `terra-pr09-36bcbb8/audit-r1-with-probe.rs.txt` 提取原函数 `audit_backfill_conflict_must_invalidate_current_ready`，保留测试逻辑，仅作 rustfmt；未修改该独立副本。原文件 SHA-256 为 `f99ecb96036ccefbc02fe9f7319ec11449cb1f7e658a0e421cd0b569bbfff83a`。该函数纳入 `crates/forward/src/tests/r2.rs` 永久回归。

- [修复前](probe-before.txt)：在 R1 生产逻辑下实际 FAIL，错误为 `conflicting same-day calendar must invalidate readiness`。
- [修复后](regression-after.txt)：独立原探针与两个补充测试共 3 项 PASS。
- 补充测试检查当日冲突与其他日期冲突、实际自动步进、原槽位/事件不变、as-of 与日报一致、重启后 readiness 不回到成功、三份报告逐字节一致。
- 另一补充测试明确锁定“首次 EOD 因响应内其他日期冲突仍整次拒绝”的保守边界，不把它包装成新采集完全隔离。

以上全部 **synthetic_test**，不增加真实观察日。

```powershell
./scripts/with-msvc.ps1 test -p stratide-forward --locked --offline audit_backfill_conflict_must_invalidate_current_ready
./scripts/with-msvc.ps1 test -p stratide-forward --locked --offline tests::r2::
cargo fmt --all -- --check
./scripts/with-msvc.ps1 check --workspace --locked --offline
./scripts/with-msvc.ps1 test --workspace --locked --offline
./scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline '--' -D warnings
```

最终 Windows 离线全量 **105 项测试通过**（R1 的 102 + R2 的 3），fmt、check、严格 Clippy exit=0，见 `test.txt / fmt.txt / check.txt / clippy.txt` 与源码指纹 `self-test-metadata.json`。报告目录改名测试使用已授权本机执行；环境 hard-link 警告保留，未压制检查或删除测试。R1 的失败证据不覆盖。

## 真实证据与保全边界

本轮只核对原数据库和三份旧报告的文件 SHA-256，与初始元数据相同；**没有重新打开/重算真实 journal 的链与 raw，也没有新发行情请求**，不把文件哈希检查称作新的完整来源复验。上轮已完成的开发侧/独立执行离线复核各保留原边界。数据库、journal schema 1041、原始响应、旧报告、provider、风险、财务账本与依赖均未修改。

真实证据仍只有 1 有效观察日、0 提案/成交；NAV/回撤 unavailable。连续真实日、真实晚到/修订、独立开盘实收和费用/当日规则仍 **NOT VERIFIED**。R2 开发自测通过不能替代新 HEAD 独立验收或源码审查；不合并。
