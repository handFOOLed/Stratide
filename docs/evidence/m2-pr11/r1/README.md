# PR56 审查修复 R1 开发证据

对应 [审查意见](https://github.com/handFOOLed/Stratide/pull/56#issuecomment-6567321469)，原固定 HEAD `a24c8feba1811d474db19db28628b95898963191`，base `a27f466e643cb7dd05e3be72b83402a4599a301f`。当前修复提交的固定 HEAD 以唯一 Draft PR #56 描述为准；[tested-source.json](tested-source.json) 绑定 17 个实际测试源码的 SHA-256，并在提交后与 Git blob 核对。以下均为开发者测试，独立定向复审仍为 **NOT_VERIFIED**。

## P1：现有 Owner Agent 与新云研究共用费用权威

原问题是新链路只在自己的新库内共享两模型预算。现在首次 `init` 必须显式提供已有 Owner AgentDir 和原配置路径；持久绑定指向该原费用库，并在原 `meta` 绑定 authority ID/配置路径。所有新阶段在 reserve/dispatch 核对该库；原 Agent 也不接受另一配置路径。未绑定时不初始化另一费用库。旧 multimodal/EOD fake-only scope 不允许通过绑定扩大权限。

原 `tasks/calls`、日/月上限、已消费与未结算预留保持原权威，新增阶段显式选模型，原默认/备用选择不改变。显式 `configure-recorded` 仅追加 TST 模型，不设置预算。测试在物理隔离、源码一致的 Git checkout 内先通过原 `stratided --agent-init-fake` 创建原 Agent，再绑定新链路；生产 common root 保持未绑定，原 `.agent` 状态不删除、不迁移。没有用清空 calls、抬 cap、换费用库或伪造真实账单解决拒绝。

| 检查 | 结果与证据 |
| --- | --- |
| 修复前原命令 | 显式绑定参数原来不可用，exit 2：[red-binding.txt](red-binding.txt) |
| 跨入口预算独立断言 | 6 项 Rust tests，通过；[shared-budget-test.txt](shared-budget-test.txt)。含原默认保留、旧消费叠加日/月上限、旧未知跨月重启、错配置/错库拒绝、两个真实进程竞争同一 SQLite reserve，独立 SQL 汇总 |
| 当前 workspace Rust | **177/177 PASS**（原 171 + 6），隔离 ignored TEMP/TMP；[fixture-rust-test.txt](fixture-rust-test.txt) |
| 当前新链路 Python E2E | **13/13 PASS**，保留原 10 项并增加旧 Agent 实际消费叠加两阶段、原未知跨月和绑定不可替换；[portfolio-test.txt](portfolio-test.txt) / [checks.json](checks.json) |
| 编译/静态检查 | build、fmt、check、clippy `-D warnings` 结果见本目录日志 |
| 原 Agent / Candidates / Review | 原 Agent API 6 组检查、Candidates 13/13；Review 首轮 11 项通过，junction 单项正常 Windows 权限复跑通过，共 12 个唯一用例通过；[原命令/退出码](original-regressions.json)、[首轮 Review](original-review.txt)、[单项复跑](review-junction-rerun.txt) |
| 原状态与测试定义 | 20 个受保护文件 SHA/长度/mtime 不变；[preservation.json](preservation.json)。PR52/54 三套原测试及 snapshot 夹具未改，SHA 见 [original-test-source.json](original-test-source.json) |

新用例 11 在同一原库先运行原 fake Agent 实际结算，再运行两个 cloud 阶段；合计超过原日/月测试 cap 时，Fusion 分别精确返回 `DAILY_BUDGET_EXHAUSTED`/`MONTHLY_BUDGET_EXHAUSTED`，默认模型仍为原 fake。用例 12 将原 fake-unknown 保留在前月，重启后最大预留继续占用新期预算；新请求被拒绝，无旧请求重试。该独立预算用例的显式历史时间只用于预算算法，不涉及 PR52/54 的真实安全时钟测试。

原生产 API 认证/请求/解析、loopback、kill/restart、撤销/输入变更/预算复核、整份非法组合拒绝、原 Registry/Inbox 接线均在这次 13 项中重跑。三股票/现金和全现金当前运行报告见本目录 `synthetic-calm*`、`synthetic-stress*`；原 evaluator 仅评价既有 synthetic 模板，不证明新组合策略具有独立资格。

## P1：PR52/54 三套原始回归

**PENDING / NOT PASSED。** 原首轮无效时间失败仍保留在上级证据目录，不以历史 PASS 替代。本次不修改原测试定义、系统时钟或安全时钟门禁。原 `scripts/test-data-snapshot.py:stamp()` 使用当日 **17:00 UTC+8**，比 suite 的 16:00 提示更晚；已在本聊天安排 2026-11-02 **17:10 UTC+8** 单次续跑原 multimodal 10 项、routing 4 项、forward-readiness 13 项。准确条件、命令和状态保全方式见 [HANDOFF.md](HANDOFF.md)。三套实际通过前，本审查项不关闭。

## 失败保留与验证边界

[check-first.txt](check-first.txt) 为修复开发中的首次 `cargo check` 成功日志。[portfolio-first.txt](portfolio-first.txt) 保留首次扩充 E2E 的失败：旧测试假设模型下标 0 是云模型，但修复后必须保留原模型；测试改用模型 ID。原测试 SQLite 连接补充关闭，解除夹具造成的 WAL busy。未放宽生产只读边界。第二次沿用同一 synthetic 原 Agent 费用库，保留前次消费/未知预留后 13 项通过。

原 Review 首轮仅 junction 创建被沙箱拒绝；不修改原用例，正常 Windows 权限复跑单项通过。ignored 复跑驱动最初缺少原 `scripts` 导入路径，两次在导入阶段退出；`review-junction-harness-*.txt` 保留该驱动错误，最终单项日志独立记录实际执行结果。

**0 真实云调用、0 真实收费、0 Tushare 外发/新行情请求、0 新 Paper/Live 订单或金融账本写入。** BigQuery HTTPS 仍 `BIGQUERY_BILLING_BOUND_NOT_VERIFIED`。真实 Provider 凭据/网络/计费/留存、实际模型版本/能力、真实跨股票 PIT/前向输入、alpha、其他 OS、独立复审均 **NOT_VERIFIED**。旧真实来源、原收据和 fake-only Agent 状态不改。保持 Draft，不 Ready、不合并。
