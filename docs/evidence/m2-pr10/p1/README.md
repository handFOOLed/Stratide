# PR #52 P1 修复与回归

2026-11-01；针对 [审查评论](https://github.com/handFOOLed/Stratide/pull/52#issuecomment-6558243819) 修复初始 HEAD `be37953f07e6f1bd9b25521151d6e004b3b9ce27`。**开发自测，不是独立验收**；原固定 HEAD 的 CHANGES REQUESTED / NOT PASSED 结论不改写，新 HEAD 待复审。原 `m2-pr10` 证据保留，本轮材料仅追加在本目录。

## 原因与最小修复

原 bridge 验证 B 后调用全局 `Agent::tick`，而 `Store::claim` 领取最早 queued task A。A 自己的当前来源和时点没有在原 reserve/dispatch 路径复查；Python 将 A 标失败时也可能留下原 queued task。

- 新 `Agent::tick_task / Store::claim_exact` 在原 SQLite 事务内匹配 **ID + trigger_key**，不匹配/暂停明确阻断，不能回退到其他任务。原非 multimodal 全局任务选择语义保持。
- 实际 multimodal task 在原预算预留前和 dispatch 事务内重查自身绑定、source identity、PR33 最新已核验 SHA、source_day/mode、上海当天 16:00 和原 on-day 时间。原全局 `Agent::tick` 也经过相同门禁。失效任务持久取消，预留后失效的原 call 保留为未发送的 `no_charge`。
- Python 原 observer/窗口校验失败后，经 Rust 原 Store 按对应 ID/trigger 取消 queued intent。操作只针对未 dispatch 的原 queued 任务；不删除审计、不重写 completed/未知费用、不建立第二套队列或预算。
- PR33 原 reader 只增加同一读取事务返回 source identity 的入口，旧 `InputSummary`、scope 与 canonical 投影不变。旧 `LOCAL_FAKE_ONLY` 未放宽，Budget Gate 算术/结算未修改。

## 红→绿与原 SQLite 事实

复现命令：

```powershell
python -B scripts/test-multimodal-routing.py --test test_two_sources_tick_targets_b
```

修改前 **exit 1**：B tick 返回 `queued`，断言 `queued != completed`。原 SQLite 显示 A(task **48**) 已 completed、call **40** settled；B(task **49**) 仍 queued、没有 call。见 [原失败输出](red.txt) 与 [执行后的原任务事实](red-facts.json)。这证明校验 B 后实际执行了 A，故障不是单纯输出显示错。

同一测试修改后 **exit 0**。完整新增回归运行 **4/4，exit 0**，见 [输出](routing-test.txt)、[精确 CLI/退出码、源日/输入 SHA/当前 SHA、task/trigger/call/登记事实](routing.json)：

| 场景 | A 原任务 | B 原任务 | 最终事实 |
| --- | --- | --- | --- |
| 实际全局 tick：A 源已修订 | 88 | 89 | A cancelled，`MULTIMODAL_SNAPSHOT_CHANGED`，0 call/0 登记；B completed，1 settled call/1 登记 |
| 实际全局 tick：A 已过源日 | 90 | 91 | A cancelled，`MISSED_OR_STALE`，0 call/0 登记；B 1 call/1 登记 |
| 实际全局 tick：A 被 Owner disabled | 92 | 93 | A cancelled，`OWNER_DISABLED`，0 call/0 登记；B 1 call/1 登记 |
| A after_queue 中断→合法新 Snapshot/sync→Python 重查失败→显式 B 新实验 | 94 | 95 | A cancelled，0 call/0 登记；B 使用不同输入 SHA，1 call/1 登记 |
| A/B 均 after_queue 中断；B settled 后再次突然退出、再恢复登记 | 96 | 97 | B 的恢复不领取 A、不重复调用；随后显式处理 A，最终各 1 call/1 登记 |
| 两个独立来源都正常 queued；先 tick B | 98 | 99 | B 独立 completed 时 A 的 task/calls 原样不动；之后分别完成归档，最终各 1 call/1 登记 |

`os._exit(86)` 为实际子进程突然退出；所有 queued/completed、call/预留/结算与 Candidate 登记均来自原生产 Rust Agent/SQLite 和 Python CLI。只读导出的事实同时包含 frozen input SHA 与当前 PR33 SHA，不手工拼接完成的 task JSON。

过期及原全局 tick 的时间点注入仅存在于 `cfg(test)` libtest，先核对当前原 PR33 确为 `synthetic_test`，并断言指定 A 就是全局队头，不能执行其他已有任务。生产可执行文件没有时钟或 global-tick 测试参数；正常 B 和其他跨任务链路使用生产 CLI/真实盘后时钟。

## 本轮兼容性回归

精确命令、exit code、耗时与代码 SHA 见 [validation.json](validation.json)。

| 检查 | 本轮结果 |
| --- | --- |
| 新 P1 路由/来源回归 | 4/4 |
| 原双模型全套，含双 25 日 E2E、预算/未知费用/恢复反证 | 10/10；[本轮命令与结果](multimodal/checks.json)，[A](multimodal/e2e-a-report.json)、[B](multimodal/e2e-b-report.json) |
| Rust workspace test | **162 passed / 0 failed / 0 ignored**；[输出](rust-test.txt)，含原 Budget/Agent 与新增精确 claim 用例 |
| Rust fmt/check/clippy/build | 全部 exit 0；clippy `--workspace --all-targets -- -D warnings`；[check](rust-check.txt)、[clippy](rust-clippy.txt)、[build](rust-build.txt) |
| 原 Snapshot / EOD Agent / Candidate | 11 / 6 / 13 全通过 |
| 原 #44 EOD Auto / #46 Inbox / #50 Operator | 16 / 12 / 18 全通过 |
| 原 Agent API 真实进程 | [6 项 PASS](agent-api.json)，仅 loopback / fake / TST |
| Python syntax / git diff --check | 通过 |

本轮原 Python 回归共 **76 个唯一用例**；原 Shadow 未修改，沿用上一轮 9/9 证据，不声称本轮重跑。Windows 使用原 MSVC 环境；Rust 与 Agent API 测试 TEMP/TMP 为任务 ignored `state/rust-temp`。含 junction/合成 Credential Manager 的旧套件在沙箱外执行，只使用原测试随机 target，不读取真实凭据。没有更改旧测试定义以通过。

## 边界与未验证

本轮只修复 P1 路由和已入队任务来源门禁；公共请求、真实模型调用、真实费用与新增交易权限均为 0。所有数值/调用均 synthetic/fake，仍为 `RESEARCH_ONLY / ELIGIBILITY_DENIED`；真实外部模型、PIT、开盘、前向 Paper、物理断电、其他 OS 和独立策略价值继续未验证。未 Ready、未合并，等待新固定 HEAD 复审。
