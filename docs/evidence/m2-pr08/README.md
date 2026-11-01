# M2-PR08 开发证据

2026-11-01，Windows；base `9a981e5e115164b73fe5756d0c8ebb8547a8b3f6`。一个 worktree/分支、一个功能提交、一个 Draft PR；`agents=0`。以下是开发自测，**不是 ChatGPT 固定 HEAD 复审或独立验收**。HEAD 以本 Draft PR 为准。

## 真实运行结果

- [完整 synthetic CLI 输出](synthetic-cli-flow.json)：原 #44 测试桥实际产生 1 intent / 1 completed task / 1 settled fake call / 1 Parent registration；新 CLI 发现 `AWAITING_OWNER_TEMPLATE`，Owner 明确提供原 synthetic 模板后生成派生 registration、冻结候选、独立 Paper 测试账本、原 Evaluator receipt 及只读报告。
- [24 项 red/green 证据](review-checks.json)：12 个测试方法均通过；包含双目录、两个实际 CLI 并发、四节点真实进程 `os._exit(87)`、跨进程重启、review 目录移走后的原收据复用、Parent/SQLite task/call/intent/archive/source SHA/资格/报告/receipt/冻结输入篡改、伪造 completed 文件、参数和 junction 注入、过期/变化/缺失 EOD 继续离线审阅。
- 同一成功输入与同内容不同源目录复用原 SHA/receipt，0 新任务/调用/评价。并发退出码实际为 **2 / 0**（`REGISTRY_BUSY` / 完成）；随后重启复用，仍为 1 candidate / 1 evaluation attempt / 1 receipt。4 个中断节点恢复后各为 1 intent / 1 task / 1 fake call / 2 registrations（Parent + Owner 关联）/ 1 candidate / 1 evaluation attempt / 1 receipt；中断尝试原样保留。
- 原 #30 冻结目标来源实际完成 **68 日、47/21** 评价：`ENGINEERING_PASS / INSUFFICIENT_EVIDENCE / EX_POST`。另一路原历史回放获得 3 笔模拟成交、末 NAV 9,996,651 分、费用 1,549 分；双目录六报告一致、T+1 变异不改早期提案、kill/恢复事件一致。缺失/不合协议来源稳定 `DATA_BLOCKED`，不扩大 77 日 PIT。
- 过期源报告始终为 `SNAPSHOT_CONTENT_VERIFIED_AT_REGISTRATION`（Parent 的历史核验）与 `NOT_RECHECKED_OFFLINE_REVIEW / TASK_ORIGIN_NOT_ATTESTED`。所有结果仍为 `ELIGIBILITY_DENIED / forward_paper_allowed=false / live_allowed=false`。
- [旧文件 SHA 保全](preservation.json)：**2,379 / 2,379 未变化**；34 observer、103 原历史 68 日材料、82 原 77 日材料及账本、142 旧候选/评价、1,319 原自动 Agent、119 原自动候选、580 原快照。逐文件绝对路径清单只存本机 ignored 目录，公开文件仅保留分组数量及清单 SHA。

这只是 **Owner 固定模板的合成/受限历史评价**。没有执行 Agent 生成代码，没有证明 Agent 假设、策略 alpha、PIT 或真实前向交易。

## 实际命令与退出码

`H` 表示本机原 #30 已冻结、符合原目标查询的历史原始源；绝对路径脱敏。`A` 表示本任务新建的 `state/issue45-validation/history-audit/`。资金/风险值全部沿用原候选协议，不是新增实际资金授权。

| 命令 | 退出码 / 结果 |
| --- | --- |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 build --workspace --locked --offline` | 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 test -p stratide-research --bin eod-auto-agent --locked --offline --no-run` | 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 fmt --all -- --check` | 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 check --workspace --all-targets --locked --offline` | 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline -- -D warnings` | 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 test --workspace --all-targets --locked --offline` | 0；156 passed / 0 failed |
| `python -B scripts/test-research-review.py --evidence --historical-source H` | 0；12 passed，24 项记录 |
| `python -B scripts/test-eod-auto.py --evidence` | 0；16 passed，含跨实例 P1 |
| `python -B scripts/test-candidates.py` | 0；13 passed |
| `python -B scripts/test-data-snapshot.py` | 0；11 passed |
| `python -B scripts/test-eod-agent.py --evidence` | 0；原手动 fake 进程 E2E |
| `python -B scripts/test-eod-agent.py` | 0；6 passed |
| `python -B scripts/test-agent.py --assets-dir state/issue45-validation/assets --output state/issue45-validation/agent-result.json` | 0；原本机 fake / Budget / kill / cancel / 权限反证，静态资源仅测试桩 |
| `python -B scripts/test-research-evaluation.py` | 0；5 passed |
| `python -B scripts/test-historical-data.py` | 0；3 passed |
| `python -B scripts/research-evaluate.py audit --source-dir H --out A` | 0；选定区间完整，长目标仍 DATA_BLOCKED |
| `python -B scripts/test-historical-replay.py --exe target/debug/stratide-cli.exe --input A/input/dataset.json --source-dir H --output state/issue45-validation/historical-replay -- --initial-cash-fen 10000000 --max-order-fen 500000 --account-cap-fen 2000000 --strategy-cap-fen 2000000 --daily-loss-fen 100000 --drawdown-fen 500000` | 0；68 日实际回放/保全/恢复/无未来数据泄漏 |
| `python -B scripts/test-cash-dividend.py --exe target/debug/stratide-cli.exe --out state/issue45-validation/cash-dividend` | 0；9 passed |
| `python -B scripts/test-historical-dividend.py --exe target/debug/stratide-cli.exe --out state/issue45-validation/historical-dividend` | 0；11 passed |
| `python -I -B scripts/research-review.py --help` | 0 |
| `git diff --check` | 0 |

汇总见 [validation-summary.json](validation-summary.json)。MSVC 与测试使用既有依赖缓存，`CARGO_INCREMENTAL=0`，临时目录设为新建的 ignored 测试子目录；未付费 CI、未访问行情/云 Provider。

## 首轮失败与修复

保留每轮本机日志，没有把失败删除或记成成功：

1. 新 E2E 首轮退出 **1**（10 tests，1 failure / 1 error）：过期来源反例错误引用 fixture 的 `record` 字段；改为原 `outcome.available_at`。junction 创建收到文件沙箱 `Access is denied`；在同一任务的新 ignored 目录中运行获准的离线测试，真实创建 junction 并验证拒绝。未削弱生产路径检查。
2. 第二轮退出 **1**（11 tests，1 failure）：所选旧 M1 短区间来源不是原评价协议的冻结目标查询，原 audit 明确拒绝，实际产生 `DATA_BLOCKED / SOURCE_AUDIT_REJECTED`。没有改源或放宽协议；改用实际存在的原 #30 冻结目标来源。最终 **12 tests / 0 failures / 0 errors**。
3. 原 Agent 进程回归首轮退出 **1**：测试资源桩缺 `assets/app.js` 和 `assets/app.css`；补齐本任务 ignored 桩后退出 **0**，未改 Dashboard 或 HTTP 代码。原历史回放首次漏传脚本必需参数退出 **2**，补齐原冻结输入、来源和六个固定资金/风险参数后退出 **0**。

最终完整材料保存在本 worktree ignored `state/issue45-validation/`、`state/review-tests/` 和原测试各自的新 state 子目录；新旧 SQLite、真实原始行情、Token、绝对路径不提交 Git。

## 未验证与范围

真实前向开盘、历史 PIT/alpha、真实 Provider/账单、Linux/macOS、物理断电/OS 重启和另一审查者验收仍 **NOT_VERIFIED**。实际中断证据是进程退出与重启；不夸大为物理断电恢复。

生产改动仅 `scripts/research-review.py`、`research/review.py` 和原 `research/candidates.py` 的精确模板复用/不可变 Parent 派生接口。原 Agent/SQLite schema、预算/Provider/网络、Risk、Ledger、replay、Dashboard、observer、forward journal、真实交易权限及 Accepted ADR 未修改。Draft 等待 ChatGPT 固定 HEAD 复审，Owner 明确许可后才可合并。
