# M2-PR04 Windows 开发自测证据

日期：2026-10-30。关联 [Issue #29](https://github.com/handFOOLed/Stratide/issues/29)。实际 main base：`34ab2761483b95fef53a9316f95fae9ce6fb8d97`。这是开发者自测及可信评价代码的输出，**不是 Terra/另一审查者的独立验收**；PR 保持 Draft，不授权合并或交易。

## 可复现验证

详见 [操作与命令](../../M2_PR04.md)。在 Windows/MSVC、Python 3.12、本地缓存、无市场/付费 Provider 请求的环境实际执行：

| 检查 | 结果 |
| --- | --- |
| `build -p stratide-cli --locked --offline` | PASS |
| `fmt -p stratide-cli -- --check` | PASS |
| `check -p stratide-cli --locked --offline` | PASS |
| `test -p stratide-cli --locked --offline` | 18 PASS；包括 SMA 无前视、报告发布进程中断、账本恢复和风险拒绝 |
| `clippy -p stratide-cli --locked --offline --all-targets -- -D warnings` | PASS |
| `python scripts/test-candidates.py` | 13 PASS；含真实 CLI/进程 kill/重启、两个独立新目录、缓存不写、输入/协议/产物/资格篡改反证 |
| `python scripts/test-research-evaluation.py` | 5 PASS |
| `python scripts/test-historical-data.py` | 3 PASS |
| 原研究评价脚本的 `--exe/--audit-dir/--source-dir/--out/--preserve-dir` 实际历史模式 | PASS；两个 ledger/六报告、评价及基准一致；T+1 变异不改 T 提案；分界变更和篡改报告拒绝；缺数据/公司行为阻断、无交易/末日 pending 及基准一次失败诚实保留 |

环境问题已处理：沙箱默认临时目录无法发布测试文件，改用本工作树 `state/test-tmp`；构建与正在使用同一 `.exe` 的操作串行执行。未修改 Rust、账本或发布逻辑来绕过环境问题。

## 真实冻结历史候选的最终结果

从既有本机冻结源只读重建；没有补抓行情、重选收益窗口或改变原研究协议。

- 模板：`sma5-20-cross-fixed100-v1`；数据 SHA `ccf8eceb5e5844b32c4f6470c4dc29637c05612f779c1fcef79218ba3d5879a2`。
- 候选 SHA：`036ccb8edc2c956d2722453a58fec78cd0c0479e60351dd242e57fbdb89a3c8d`。
- 独立评价引用 SHA：`6c92db85b6db1dee7ab443cfc44b477449c942c2c92e358e58c657b513a6ed85`。
- 68 日支持区段：2026-07-17—10-28；development/已暴露 historical holdout = 47/21。初始 10,000,000 分；3 笔模拟成交、模型费用 1,549 分；末现金 9,898,151 分、100 股、无 pending；末 NAV 9,996,651 分。净回报 `-0.000334900000`，每日最大回撤 `0.000674786572`，均为比例值。
- 固定首日收盘/次日开盘买入持有基准净回报 `0.000939900000`；只作独立假设比较，不代表额外真实资金或风险匹配 alpha。压力仍为原 `posthoc_cost_bound`。
- `engineering=ENGINEERING_PASS`；`research_status=RESEARCH_INSUFFICIENT`；`research_evidence=INSUFFICIENT_EVIDENCE`；支持区段完整，长窗口 `DATA_BLOCKED`；`eligibility=ELIGIBILITY_DENIED`；`qualification=NOT_ELIGIBLE`。
- `forward_paper_allowed=false`，`live_allowed=false`，`independent_acceptance=NOT_VERIFIED`。短样本、历史 PIT、公司行为/早期费率和真实开盘可得证据未因工程通过得到认证。

原始源 5 文件、原 audit 4 文件、原历史评价/ledger/报告 29 文件、前向状态 98 文件、Agent SQLite 1 文件，共 **137 文件 SHA 不变**。另用一轮全新历史候选评价验证原始前向 `forward.sqlite` 的前后 SHA 不变，两个 registry 的候选及评价 ID 一致。最终候选重复启动 evaluate 命中可校验缓存，整个新 registry 文件内容不变，没有第二份资金/订单写入。

完整本机产物：`state/candidates/history-20261030-final/`、`state/m2-pr04-validation/`、`state/m2-pr04-history-validator/`，全部 Git ignored。本文件仅保留脱敏摘要，不提交原始行情、Agent 私有任务、账户身份、密钥、数据库或本机绝对路径。旧候选/评价记录不原地迁移或改写。

## 范围和未验证项

变更限于 `research/candidates.py`、两个固定候选 JSON 样例、`scripts/research-candidate.py`、现有研究评价器的窄 synthetic 适配、相关测试和说明/状态文档。既有 SMA/历史评价分支与财务计算未替换；合成路径使用原固定 v1 模板和原财务一致性函数，结果始终 `SYNTHETIC_TEST_ONLY`。

Dashboard、视觉、Risk Kernel、v3 ledger schema、撮合、前向 journal、真实 Provider/预算/数据共享许可、Accepted ADR 均未修改。没有真实前向订单/NAV、券商或自动晋升入口。Linux/macOS、真实 Provider、物理掉电和同 HEAD 的另一审查者独立反证为 **NOT VERIFIED**。Owner 明确授权前不得合并。
