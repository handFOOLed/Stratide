# PR #44：P1 跨实例重复触发修复

对应 [最新审查意见](https://github.com/handFOOLed/Stratide/pull/44#issuecomment-6553607874)，审查基于 `625a175065122a883dae69bd7b95d36097288203`，结论 **NOT PASSED / 1 项 P1 待修**。本轮只修这一项与补充进程 E2E，沿用原分支和 Draft PR；Sol 单人开发/自测，`agents=0`，不自合并。新固定 HEAD 由 PR 正文给出，尚待复审。

## 已复现的旧行为

新增反例在旧生产代码上真正初始化两个不同名称的 Auto，绑定同一 snapshot store，随后并行 `enable`、并行 `once`。两份独立 Agent SQLite 各自研究一次，合计 **2 intent / 2 task / 2 fake call / 2 registration**。断言失败、退出 **1**，见 [before.json](before.json)。没有用 mock 结果替代 Agent 调用。

## 最小修复

在原 `state/eod-auto` 内新增 `.bindings/<binding_sha256>.json`，只记录绑定 SHA 与唯一实例名。首次 enable 持有同 binding 的 OS 文件锁，复用原原子 JSON 写入；后续 enable/once 检查持久归属。Rust 原任务桥在 `intent/queue/tick` 进入 Agent 之前也检查归属，不能绕开 Python 校验另建同源任务。没有新增预算/任务/候选账本。

同一 store 仍可 init 两个默认 OFF 实例，只有归属实例能启用和研究。竞争锁返回 `EOD_AUTO_BINDING_BUSY`；非归属实例稳定返回 `EOD_AUTO_BINDING_OWNED`。disable、退出、重启均不释放归属，不能换名称在当天重新研究；不同 binding 保持独立。`status` 只读显示 `binding_owner/ownership_state`。

旧目录尚无归属记录时，只读核查相同 binding 的原 Agent：唯一已有意图/任务的旧实例保留归属；多个实例都有意图，或相关旧状态无法核实，返回 `EOD_AUTO_BINDING_REVIEW_REQUIRED`，不替换输入、迁移/删除/重写旧库。没有自动转移归属入口，归属信息不写 observer 或 snapshot store。

生产改动仅 `scripts/eod_auto.py` 和 `research/agent/src/bin/eod-auto-agent.rs`；其余为原 E2E 的新增反例、操作说明及本证据。LOCAL_FAKE_ONLY、TST、Core-first、时间/来源门禁、原 Agent/候选能力保持原约束。

## 实际双实例 E2E

[cli-e2e.json](cli-e2e.json) 保存 **37 条实际 CLI 命令/退出码/关键输出**；[after.json](after.json) 保存完整 16 项结果。使用受限 synthetic 源与原测试专用时钟，不从生产 CLI 注入时间；“真实双实例”指两个不同名称、不同 Agent SQLite、真实独立进程和原 fake/候选链路，不表示新增真实交易日验证。

| 场景 | 实际结果 |
| --- | --- |
| 同一 store / 两个名称 / 并行 enable | 只有一个退出 0，另一个退出 2；未双启 |
| 同两实例并行 once | 合计 **1/1/1/1**；非归属实例退出 2 |
| 重新启动原实例和被拒实例 | 原实例 `ALREADY_ARCHIVED_INPUT_FROZEN`；另一实例 `EOD_AUTO_BINDING_OWNED`；0 新任务/调用/登记 |
| 原实例 disable 后另一名称 enable | 仍 `EOD_AUTO_BINDING_OWNED`；原实例再次 enable/once 后合计仍为 1/1/1/1 |
| 直接调用生产 Rust bridge 的非归属 intent | 退出 2，`EOD_AUTO_BINDING_OWNED`，未创建任务 |
| 不同来源/binding 的实例 | 独立完成自己的 1/1/1/1，不与前一 binding 串用状态 |
| 遗留两个 enabled、尚无归属记录的实例 | 新入口并行 once 收敛为一归属，合计 1/1/1/1 |
| 遗留原实例已有真实排队任务、另一新名称抢 enable | 归属保留给原实例，原 DB 在归属核查期间 SHA 不变；原任务恢复后合计 1/1/1/1 |
| 遗留两个实例都有意图 | 两者 enable/once 均 `EOD_AUTO_BINDING_REVIEW_REQUIRED`；原 DB SHA 不变，0 新任务/调用/登记 |

遗留 fixture 仅在新测试目录内模拟旧 enabled 位或旧意图；有真实任务的案例由原 CLI 创建后进程中断。没有构造 completed/result/call 作为成功证据。模拟升级缺少归属记录时，仅移除该新 synthetic fixture 的归属 JSON，不删除任何旧 Agent DB。

## 检查与保全

[verification.json](verification.json) 列出实际命令和退出码；[test-results.txt](test-results.txt) 是最终输出脱敏副本。Windows x64、Python 3.12.10、Cargo 1.98.1；`CARGO_INCREMENTAL=0`，Rust 测试 TEMP/TMP 位于新 ignored `state/pr44-p1-validation/tmp`。

| 实际执行 | 退出码 / 结果 |
| --- | --- |
| `cargo fmt --all -- --check` | 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 check -p stratide-research -p stratided --all-targets --locked --offline` | 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 clippy -p stratide-research -p stratided --all-targets --locked --offline -- -D warnings` | 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 test -p stratide-research -p stratided --locked --offline` | 0；**32 项通过** |
| `python -B scripts/test-eod-auto.py --evidence` | 0；**16 项通过**，包含原 13 项和新增 3 项跨实例/遗留状态测试 |
| 同一新增双实例测试在旧生产代码上运行 | **1（预期失败）**，合计 2/2/2/2，修复后为 1/1/1/1 |

原 27 文件保全清单再次核对，全部 SHA 仍等于 [首版保全记录](../preservation.json)。没有写旧 observer/snapshot 的归属状态，没有删除/迁移旧库。首版全仓 156 项及其他 Python/财务回归属于旧固定 HEAD 的历史证据；本轮未重复声称它们是新 HEAD 的完整重跑。

本轮无真实 Provider/付费调用/行情请求，新增真实前向天数仍为 **0**。新真实交易日自动研究、真实 Provider/账单/PIT/开盘/执行/alpha、Linux/macOS、物理掉电/OS 重启继续 **NOT_VERIFIED/BLOCKED**。本结果是开发者自测，保持 Draft，等待 ChatGPT 对新 HEAD 复审及 Owner 合并授权。
