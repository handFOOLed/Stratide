# M1-PR10 开发自测证据

基线：`main 6c86b872360bcaa1dc92d1a02b760f1b08274295`（PR #46）。一个 Draft PR，`agents=0`；这是 Sol 开发自测，**不是独立验收、PIT 认证或合并许可**。最终 HEAD 见关联 PR。Windows / Python 3.12.10 / Rust 1.98.1 / 已有 MSVC；无新增依赖、付费 CI、行情采集或真实 Provider 调用。

## 交付与成功证据

完整操作与设计边界见 [M1_PR10](../../M1_PR10.md)。[shadow-e2e.json](shadow-e2e.json) 保存双目录 22 日标准化结果、并发/重启、三节点实际进程退出及反例摘要；[cli-commands.json](cli-commands.json) 列真实 CLI 路径的各次参数、测试时钟、退出码和精简输出；[synthetic-report.json](synthetic-report.json) 保留报告总计及最后两个有效信号的脱敏查询节选，省略前 20 个预热不足记录，完整输出保留本地。假时钟和中断只由测试入口注入，生产 CLI 没有这些选项。

| 实际命令 / 检查 | 结果 |
| --- | --- |
| `python -B scripts/test-forward-shadow.py` | 9 个测试通过；两套新目录各 22 个源日，前 20 日明确不足，第 21 日 UP_CROSS、第 22 日 DOWN_CROSS；逐日 SHA/窗口/实际决策时间与独立 Decimal 均值一致 |
| 同套 CLI `once/watch` 并发、同源别名、重启、切 cwd、disable | 每日最多一个 committed observation；禁用后的新日不追加；watch 前台同一路径，Ctrl+C exit 130 |
| 同套实际 `os._exit(86)` 三节点 | 意图前/提交前中断不假成功；已提交后中断只复用；热日志只由 writer 恢复，原意图保留并追加 interrupted 诊断 |
| 同套时点/数据反证 | 16:00 前、T+1/24h 过期、未来源版本、未 sync 源变化、同日修订、晚补与开市缺口、unknown/conflict 日历、单位/raw SHA/证券异常、snapshot SHA 和 historical/ex-post 模式均拒绝；冻结旧信号不变化 |
| `status/history/verify/report` | 原 observer、新 PR33 store 与 Shadow 全部 byte/SHA 不变；无库时不创建状态；禁止策略入口、sync、writer lock 和网络调用的反证通过 |
| `python -B scripts/test-forward-shadow.py --real-observer <PRIVATE_OBSERVER> --old-snapshot <PRIVATE_PR33_SNAPSHOT>` | 生产 CLI / 真实墙钟；原两日 observer 和 PR33 快照一致，once `MISSED_OR_STALE`，同时独立报告预热不足，0 observation/0 signal/新增真实日 0；[real-boundary.json](real-boundary.json) |
| `cargo fmt --all --check` | exit 0 |
| `powershell -NoProfile -File scripts/with-msvc.ps1 check --workspace` | exit 0 |
| `powershell -NoProfile -File scripts/with-msvc.ps1 clippy --workspace --all-targets -- -D warnings` | exit 0 |
| `powershell -NoProfile -File scripts/with-msvc.ps1 test --workspace` | 工作区临时目录下 156 tests 通过；包括 Risk / Ledger / forward / Agent / 原报表发布恢复 |
| `powershell -NoProfile -File scripts/with-msvc.ps1 build --workspace` | exit 0，供真实 CLI E2E 使用 |
| `python -B scripts/test-data-snapshot.py` | PR33：11 tests 通过 |
| `python -B scripts/test-eod-auto.py` | PR44：15/16 首轮通过；junction 用例在正常本机权限下单独重跑通过，16 项均已验证 |
| `python -B scripts/test-research-review.py` | PR46：11/12 首轮通过；junction 用例在正常本机权限下单独重跑通过，12 项均已验证 |
| `python -B scripts/test-research-evaluation.py` | 5 tests 通过 |
| `python -B scripts/test-historical-replay.py --exe target/debug/stratide-cli.exe --input <PRIVATE_68_DAY_INPUT> --source-dir <PRIVATE_RAW_SOURCE> --output <NEW_IGNORED_OUTPUT> -- --initial-cash-fen 10000000 --max-order-fen 500000 --account-cap-fen 2000000 --strategy-cap-fen 2000000 --daily-loss-fen 100000 --drawdown-fen 500000` | 原 68 日冻结输入 SHA 不变；六报告双跑逐字节一致；强杀后 35 个 committed events 前缀恢复一致；费用/现金/持仓守恒、无重复、未来行情不改过去提案。沿用原已授权 smoke 参数，无新增真实资金 |
| `python -B scripts/test-cash-dividend.py --exe target/debug/stratide-cli.exe --out <NEW_IGNORED_OUTPUT>` | 9 tests 通过；七报告、独立算术、双基准、v3 golden/旧账本兼容及真实源资格拒绝 |
| 旧材料保全 | 14,741 个已有 state/证据/报告/行情/SQLite 及原 `.gitignore` 文件前后 SHA 一致；[preservation.json](preservation.json)。本地 manifest 含私有路径，留在 gitignored state，不入 Git |

上列实际退出码、测试数量及复跑说明集中于 [regressions.json](regressions.json)。所有修改只涉及新 Shadow 模块/CLI/测试和授权 docs；原 data_snapshot/eod_journal、Rust、Risk、Ledger、Agent、候选、UI、历史 Accepted ADR 未修改。

## 环境失败与处理

原 Rust 报表 rename 测试首次在系统 Temp 返回 `Access is denied`；解除沙箱后仍有系统 Temp 创建权限失败。将 **TEMP/TMP 仅在测试进程内** 指向新工作区 ignored 目录，原封不动运行全套 Rust 测试通过，没有改生产代码或删测试。

PR44/PR46 原 junction 用例在沙箱中 `mklink /J` 失败，各自其余用例通过；只对失败项使用正常本机权限复跑，通过。首次历史回放脚本无参数启动只产生 argparse usage / exit 2，随后补齐真实冻结输入和原六项 smoke 参数完整运行通过。这些均是执行/环境失败，不是自动审批拒绝。

新模块开发中的失败轮次和隔离 fixture/evidence 均保留在本地 ignored state；最终成功摘要列于本目录，不覆盖任何旧版 `docs/evidence/` 或原真实 observer/快照/六七报告。

## 未验证与权限边界

真实 21 日连续前向 Shadow 尚未累积；原真实证据只有 2 日。真实开盘仍 BLOCKED；历史/公司行为 PIT、真实 Provider、真实收益/前向 Paper 成交/NAV、live、Linux/macOS、物理断电和独立 clone/跨主机协调均未验证。默认输出不公开行情值；完整冻结输入仅保存在新本地 ignored Shadow SQLite。

所有 Shadow 输出固定 `NO_ORDERS`、0 orders/0 fills/nav=null、forward_paper_allowed=false/live_allowed=false。历史回放回归中的 3 笔模拟成交只属于原 `historical_replay`，没有进入 Shadow 或增加真实前向覆盖。Draft 待 ChatGPT 固定 HEAD 审查及 Owner 明确合并许可；未 Ready、未合并。
