# PR #50 R1 — 停用与任务启动的同步边界

修复基线 `5efcf624ff71a3b95c192b9000432a0ab14f6594`，对应 [P1 审查及最小修复要求](https://github.com/handFOOLed/Stratide/pull/50#issuecomment-6555880267)。仅调整 Operator 启动边界、对应测试及说明；原 collector、Snapshot、Shadow、Auto、Rust、Risk、Ledger 和原证据 JSON 均保留。**这是开发者自测，等待新 HEAD 的固定 SHA 复审，不代表独立验收或允许合并。**

## 原因与修复

旧 `start()` 在短事务中检查 enabled 并提交 `stage_started`，随后才实际调用子系统。别的进程可以在两者之间完成 disable，导致返回 `DISABLED` 后仍发请求或写下游。

`stage_started` 现在明确是可撤回意图。`dispatch()` 另在原 DB `BEGIN IMMEDIATE` 中做最后一次 enabled 检查并实际调用 `Popen`，同 `control(False)` 的事务互斥。Popen 已成功创建、交给 OS 的步骤是 in-flight；事务在等待子进程前释放。四步均调用原受信 CLI，没有修改其算法/状态协议，也没有新增任意命令或 URL 选项。成功停用之后不再派发新步骤；先派发的原步骤可完成，其后只读取权威证据并写 Operator 的停用 receipt。

## 确定性多进程反证

| 交错 | 断言 |
| --- | --- |
| Collector 意图已提交、尚未实际启动 → B disable 已返回 → 释放 A | 不产生新 collector HTTP/原 Started；原 observer、snapshot、shadow、Agent SQLite SHA 和计数全部不变 |
| Snapshot 意图已提交、尚未实际启动 → disable → 释放 | 不 sync；原 snapshot、Shadow、Agent 和其余数据库 SHA 不变 |
| Shadow 意图已提交、尚未实际启动 → disable → 释放 | 不产生 observation；全部原数据库 SHA 不变 |
| Fake 意图已提交、尚未实际启动 → disable → 释放 | 不产生 task/call/registration；全部原数据库 SHA 不变 |
| 原采集已实际发出两次 loopback HTTP、尚未保存 Finished → disable 返回 → 释放采集 | 原 Started/Finished/raw SHA 完整保存；Snapshot/Shadow/Agent SHA 不变，任务/调用/归档均为 0 |
| 最后 enabled 检查已完成、在 spawn 内紧邻实际 Popen 前暂停 | 另一个 DB writer 实际得到 `database is locked`，disable 尚不能返回；释放 Popen 后，disable 能在 collector 仍暂停时成功返回，证明锁覆盖实际启动且不等待整步完成 |

修复后的测试使用两个独立 Operator CLI 进程、文件屏障和真实阶段子进程，HTTP 仅发至本机 fixture。没有靠固定睡眠碰撞竞态；启动前意图和在途采集反例用 10 秒 communicate deadline，要求停用能在释放被暂停的步骤之前返回；实际 Popen 临界区反例则要求停用先等待派发完成。逐例真实退出码、原 SQLite 及 sidecar SHA、写入数量和 HTTP 次数见 JSON。

**最终完整结果：18/18，exit 0**，见 [test-results.txt](test-results.txt) 与 [after.json](after.json)。[before.json](before.json) 保留旧生产代码的四处失败交错；[verification.json](verification.json) 记录命令、原生产文件的 SHA 保全与未重跑范围。18 项包含原 15 项和新增 3 项；其中启动前方法逐一覆盖四个阶段，共 6 个新增同步交错。双目录各 22 日链路仍为 44 tasks / 44 settled fake calls / 44 registrations，Decimal 复算一致。

红灯命令（生产代码仍为旧 HEAD，exit **1**，四个启动前交错均失败；in-flight 保全用例已通过）：

```powershell
python -X utf8 -B scripts/test-eod-operator.py `
  --test test_disable_return_before_dispatch_fences_all_four_stages `
  --test test_disable_during_collector_keeps_raw_without_starting_downstream
```

实际最后检查/Popen 互斥的针对性命令（exit **0**）：

```powershell
python -X utf8 -B scripts/test-eod-operator.py `
  --test test_last_enabled_check_through_actual_popen_is_one_transaction
```

完整验证命令：

```powershell
python -X utf8 -B scripts/test-eod-operator.py
git diff --check
```

新增阶段子进程后，原 Started 强杀反例的退出码改为 collector 子进程 **86**、Operator 父进程 **3 / OUTCOME_UNKNOWN**；重启仍拒绝重发，没有放宽未知结果语义。此前所有四阶段与自身 hot receipt 恢复、双目录 22 日、跨进程去重、只读和原生凭据反例继续覆盖。旧子系统生产代码及 Rust 未改，此轮不重复全 Rust workspace/无关历史或 UI 测试；原结果明确属于上一固定 HEAD。

原生 Windows synthetic 凭据测试在正常用户会话运行并删除测试凭据；没有读取/配置真实 Token。真实行情请求、真实 LLM、真实新增前向日、orders/fills 均为 **0**，NAV **null**。16:00 正式单槽回退、15:15 `EARLY_SOURCE_UNVERIFIED`、NOT_READY 不自动重试及交易资格拒绝均保持。
