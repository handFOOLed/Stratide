# Issue #17 执行证据：BLOCKED 审计

日期：2026-10-29（Asia/Taipei）。[审计与会计缺口](../../M1_PR07_AUDIT.md)。
本次为开发者实际自测与独立算术复核，**不是独立验收 PASS**；不指定或核验执行者模型身份。

## 基线、来源与结果哈希

- 启动前 `git fetch origin main`，固定 base `00d25349df8a67caf3cd24b716d54d622014b7d0`；在新 worktree 创建 `codex/issue17-history-audit`，原 Owner checkout 未切换。交付 HEAD 在 Draft PR 正文中列明。
- 仅新增本审计文档与本证据文件；Rust/Python 产品源码、依赖、旧协议/输入、forward 及账本格式均与 base 相同。因此实际被测产品代码 SHA 就是上述 base；文档提交未改变被测代码。
- 复用 PR14 原 `issue13-source-02`，复制到新 `state/issue17/source/`；SHA 与 PR14 证据一致。原 payload、完整审计/dataset、ledger/六报告/评价及命令日志均在本任务 `state/issue17/`，受既有 `.gitignore` 保护。没有将原始价格、密钥或个人账户材料提交 GitHub。

| 文件/产物 | SHA-256 |
| --- | --- |
| `source/daily.json`（681 行） | `5689c59e8fa92b5ca2499141c3b4e199b168ea02f70b385c8a24eb81340d2075` |
| `source/calendar.json`（1032 行） | `284cbb28d12f576ae93e54b0bd8abf516a595cc668f56363cd2cfbb68a4d5bf9` |
| `source/limits.json`（681 行） | `dabd396dc7594bf90c74118d92be256c87667bc0cfd46af08b7c9f1861ceec2f` |
| `source/suspensions.json`（0 行） | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `source/extraction.json` | `5eb1abff2764e414f484d9610807af7544fa672ccf6228056796f4a5337e4075` |
| `audit/audit.json` | `0b82c878749bb44d0d06101fcaa9aab17ec7ed172fe7d5ef3e86e3b40bf83941` |
| `audit/input/dataset.json`（旧 68 日） | `ccf8eceb5e5844b32c4f6470c4dc29637c05612f779c1fcef79218ba3d5879a2` |
| 新回归 ledger HEAD（v3 链摘要） | `87a12d081d69acfb2379b8ed01376b497259d355a319ed7faccee76eaeadc556` |
| `regression/a/evaluation/evaluation.json` | `b870bfca427b50809fb4ac1e843a936ea1954053d9ef3037cdeebbe450a9aa17` |
| `financial-check.json`（独立算术结果） | `e9ab3111860cf66c6179d990dd0b2ae4730d8ea1d0fa903852e2b4c982f31442` |

原始提取时间为 `2026-10-29T05:16:51.993Z`。本轮没有新的行情请求；没有公司行为输入。断点三日仍为 20240718、20250716、20260716；所有日历/日线/价格带缺失为 0；价格断点的具体事件类型与参数 **UNKNOWN**。

## Windows 实际检查

Windows x64，Rust 1.98.1、Python 3.12.10、现有 MSVC，锁定离线依赖，无付费 CI。所有检查在本任务新 worktree 执行。

| 命令/行为 | 实际结果 |
| --- | --- |
| `cargo fmt --all -- --check` | 退出 0 |
| `with-msvc.ps1 check --workspace --locked --offline` | 退出 0 |
| `with-msvc.ps1 test --workspace --locked --offline` | 退出 0，110 项 Rust 测试通过（5+2+4+5+2+1+27+31+33） |
| `with-msvc.ps1 clippy --workspace --all-targets --locked --offline -- -D warnings` | 退出 0，无警告 |
| `with-msvc.ps1 build -p stratide-cli --locked --offline` | 退出 0 |
| `python scripts/test-historical-data.py` | 退出 0，3 项测试 |
| `research-evaluate.py audit`，同一冻结源，新目录 | 退出 0；目标 DATA_BLOCKED，所选旧 68 日 COMPLETE，新增支持日 0 |
| `historical-data.py prepare`，20260706–20261028 | 退出 2，`corporate-action/adjustment discontinuity; unsupported accounting`；未生成 dataset |
| `historical-data.py prepare`，20240101–20261028 | 退出 2，`v1 supported rule/fee dates: 20260706..20261231`；未生成 dataset |
| `historical-data.py fetch`，当前无 Token | 退出 2，`STRATIDE_TUSHARE_TOKEN not configured`；在联网前拒绝 |
| `test-research-evaluation.py`，实际 CLI 双目录流程 | 退出 0；含 5 项评价单测、实际 replay/evaluate/benchmark 和反证探针 |
| 独立算术脚本 `state/issue17/financial-check.py` | 退出 0；不导入 ledger/评价器，逐日复算费用、现金、持股、NAV、P&L 和普通买入 T+1 |
| 原保护文件哈希核对 | 222 文件全部不变，见本地 `preservation.json` |

失败记录保留：首次子 PowerShell 因脚本执行策略未运行 check（退出 1），改用仅当前子进程 `-ExecutionPolicy Bypass`，不改用户/机器策略。之后 test 在沙箱默认临时目录的报表发布恢复测试出现 `Access is denied (os error 5)`，退出 101；将子进程 `TEMP/TMP` 设为本任务 ignored 目录后全套 110 测试通过。没有为通过检查修改测试或产品源码，也没有宣称已查明该 Windows 访问错误的底层原因。失败日志为 `logs/check.log`、`logs-02/test.log`，最终成功日志为 `logs-02/fmt.log`、`logs-02/check.log` 及 `logs-03/`；参数、退出码和日志 SHA 分别存 `checks.json`、`checks-02.json`、`checks-03.json`。

## 确定性、财务与保护范围

两个**新**策略目录 `regression/a`、`regression/b` 的六报告逐字节一致；evaluation JSON/CSV 和 full/development/holdout 独立基准逐字节一致。a 的六报告及 evaluation JSON/CSV 还与原 PR14 `issue13-selftest-05/a` 逐字节相同；没有用“同盈亏”代替文件比较。

另一个只用标准库、未调用产品核算函数的脚本按每笔方向、整数股和价格计算 gross；分别核对 `max(500, ceil(gross×300/10^6))`、`ceil(gross×10/10^6)`、卖方 `ceil(gross×500/10^6)`，逐日累加现金与库存，再核对 `cash + shares×unadjusted_close = NAV`、累计费用以及 `realized + unrealized = NAV - initial`。卖出数量不超过此前交易日买入的剩余库存。68 日全部相符：

| 原窗口财务结果（整数分/股） | 实际值 |
| --- | ---: |
| 初始 NAV | 10,000,000 分 |
| 成交 / 完整买卖回合 | 3 / 1 |
| 模拟费用 | 1,549 分 |
| 末现金 / 末持股 | 9,898,151 分 / 100 股 |
| 末持仓估值 / NAV | 98,500 分 / 9,996,651 分 |
| 已实现 / 未实现 / 净变化 | -4,248 / +899 / -3,349 分 |
| development / 已暴露 holdout | 47 / 21 日，仍为原分界 |

原 222 文件保护范围：PR12 最终 source、input、selftest-03；PR14 最终 source-02、audit-02、selftest-05；原 PR04A `pr04a-r2-smoke-20261028` 与 PR04B state。逐文件列表和前后 SHA 留在本地 `protected-before.json`；原文件只读，未在原目录运行 CLI 或打开 SQLite 写连接。该核对不代表所有历史工作目录均被穷举，也不是新增真实前向观察。

实际原探针还验证了缺日线拒绝、报告篡改拒绝、冻结 split 改动拒绝、T+1 行情变异不改变之前提案、无交易/末日 pending 的诚实输出、基准失败不重择入场。这些是**原路径回归**，不是公司行为事件测试。

## 同机复现

在当前任务 worktree 根目录运行；复制的冻结源已在 ignored 的 `state/issue17/source/`，跨机须提供同一已授权输入，不能重新下载后冒充同一快照。输出路径必须选未使用的名称，旧失败目录保留。

```powershell
New-Item -ItemType Directory -Path state/review17-temp
$env:TEMP = $env:TMP = (Resolve-Path state/review17-temp).Path
cargo fmt --all -- --check
# 以下四条在子 PowerShell 中使用已有 MSVC；Bypass 仅作用于该子进程。
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 check --workspace --locked --offline
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 test --workspace --locked --offline
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline -- -D warnings
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/with-msvc.ps1 build -p stratide-cli --locked --offline
python scripts/test-historical-data.py
python scripts/research-evaluate.py audit --source-dir state/issue17/source --out state/review17-audit
python scripts/test-research-evaluation.py --exe target/debug/stratide-cli.exe --audit-dir state/review17-audit --source-dir state/issue17/source --out state/review17-regression
# 两条预期退出 2；不能将拒绝误报成扩展成功。
python scripts/historical-data.py prepare --source-dir state/issue17/source --out state/review17-event-blocked --start 20260706 --end 20261028
python scripts/historical-data.py prepare --source-dir state/issue17/source --out state/review17-fee-blocked --start 20240101 --end 20261028
```

## 未执行与完成含义

公司行为有/无持仓、权益/税款/股份/到账、重复事件、跨事件订单和新增股份可卖日期：**未实现、未测试**。本轮是在来源不足、核心会计需扩大改动时，完成 Issue 明确允许的阻断调查交付；不是扩大样本的工程 PASS。研究仍 INSUFFICIENT_EVIDENCE，独立验收 NOT VERIFIED；没有 broker/实盘、GUI、Agent、参数搜索、子代理或合并。下一步所需数据与另行授权边界见审计正文。
