# M1-PR05B：Sol 自测证据

基线：`d1b79b37592b69e35a7a1bc4b64fbc3ca3b5cae5`。最终 HEAD 见关联 Draft PR；这是实现者自测，不是 Terra 验收或小猫审查。完整操作与假设见 [M1_PR05B](../../M1_PR05B.md)。Issue #10 本轮核实仍为 OPEN，未修改。

Windows x64 / Rust 1.98.1 / Python 3.12.10 / 现有 MSVC。没有安装新依赖、运行 CI、使用真实券商或实盘资金。六项真实历史 smoke 参数由 Owner 在本会话明确选择：本金 10,000,000 分、单笔 500,000 分、账户/策略敞口各 2,000,000 分、日亏损 100,000 分、回撤 500,000 分。

## 成功检查

| 命令 | 结果与记录 |
| --- | --- |
| `cargo fmt --all -- --check` | exit 0，[fmt.txt](fmt.txt) |
| `./scripts/with-msvc.ps1 check --workspace --locked --offline` | exit 0，[check.txt](check.txt) |
| `./scripts/with-msvc.ps1 test --workspace --locked --offline` | 110 tests passed，[test.txt](test.txt) |
| `./scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline '--' -D warnings` | exit 0，[clippy.txt](clippy.txt) |
| `python scripts/test-historical-data.py` | 3 tests passed，[adapter-test.txt](adapter-test.txt) |
| `python scripts/test-historical-replay.py ... -- <六项显式参数>` | 真实冻结历史，实际强杀/恢复、去重、报告字节相同、未来价格篡改和独立费用核算通过；[脱敏结果](real-history-selftest.json) |
| 输入/raw 完整性 | [source-hashes.json](source-hashes.json)；原始市场数据只留本机 |

设置 `CARGO_INCREMENTAL=0` 仅避免本机 F 盘增量缓存硬链接回退警告，不改变测试。Rust 故障注入测试原样保留，未删除或忽略。

真实采集来自当前已连接 Tushare MCP；四份原始 text payload 和实际提取元数据在 `state/issue11-source-20261029-01/`。原查询 20260706–20261028；因 20260716 除权断点，最终冻结输入选 20260717–20261028、68 根日线。`state/issue11-input-20261029-02/dataset.json` 的 SHA 为 `9460155e70947ee3c536cc02ec81d555401f1a2b824198ab660a0e2283c33ff7`。原始 payload 不是本机 HTTPS wire response。未调用 Stockie，也没有 Token 出现在命令、文件、日志或 PR。

真实 CLI 最终自测：

```powershell
python scripts/test-historical-replay.py --exe target/debug/stratide-cli.exe --input state/issue11-input-20261029-02/dataset.json --source-dir state/issue11-source-20261029-01 --output state/issue11-selftest-03 -- --initial-cash-fen 10000000 --max-order-fen 500000 --account-cap-fen 2000000 --strategy-cap-fen 2000000 --daily-loss-fen 100000 --drawdown-fen 500000
```

两份正常新账本、重复重启和一份实际进程强杀后的账本，其最终事件一致、六报告逐字节一致。中断后恢复到 35 个已提交事件，再用原命令续算，无重复收费/成交或前缀改写。逐笔费用整数复算：佣金 1,500 分、过户 3 分、卖税 46 分，共 1,549 分；期末 NAV 9,996,651 分、现金 9,898,151 分、持股 100、已实现 -4,248 分、未实现 +899 分。篡改价格探针另存 `mutated-fixture.json` 和 `mutated-probe/`，带 synthetic 标识，不能当另一份真实市场数据。

## 已保留的失败与纠正

1. 最初 Windows 沙箱执行完整 Rust 测试时，既有 `process_death_during_write_archive_and_publish_can_resume_same_path` 在报告目录 rename 报 `Access is denied (os error 5)`。相同生产代码/测试以本机权限环境重跑通过；没有改该测试或报表发布器来掩盖失败。Python 两个临时文件测试也在沙箱 Temp 受权限拒绝，原样在本机权限环境重跑 3/3 通过。
2. 首次恢复脚本试图并发 SQL 读取新账本进度，未取得可信中途前缀；原 `state/issue11-selftest-01/` 保留，**不算恢复 PASS**。检查发现既有 ledger 为 SQLite `locking_mode=EXCLUSIVE`。脚本改为只观察文件写入标记、杀进程并等待退出、调用 CLI 恢复热日志后，再只读 SQL 检查已提交前缀。不改生产锁机制。第二/三次各用新目录实测通过。
3. 早期完整输入 SHA `f2ade83bbc923f9b3a14156eb1e9a598f683332b4efa657961f023ba191fd935` 及 `state/issue11-run-01/` 保留。补齐实际查询字段与 adapter 版本元数据后在 `issue11-input-20261029-02/` 生成最终 SHA，未覆盖第一次输入/结果，策略及财务结果未调参。
4. 实际执行原 20260706–20261028 范围的 `prepare` 得到 exit 2 / `corporate-action/adjustment discontinuity`；不生成假公司行为收益。实际执行缺 Token 的 `fetch` 得到 exit 2 / `STRATIDE_TUSHARE_TOKEN not configured`；不发空 Token 请求，不伪称本机 HTTPS 实测成功。

没有把文件系统权限失败称为自动审批拒绝。所有失败、本机输入、真实/篡改运行和旧 observer 均保留；Git 仅包含脱敏摘要与代码测试日志，没有原始价格行、真实六报告、账户资料或 Token。

## 未验证

Terra 独立验收、小猫同 SHA 代码审查、Linux/macOS、历史实际 PIT/完整修订及公司行为、本机 HTTP fetch、真实开盘/前向 Paper 买卖、交易所队列/竞价可成交性、物理断电/磁盘满及跨主机恢复未验证。三笔成交只是 ex-post 历史模型；不能证明实盘收益或完成 Issue #10 / 整个 M1。
