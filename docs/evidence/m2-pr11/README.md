# M2-PR11 开发证据

以下为首轮提交 `a24c8feba1811d474db19db28628b95898963191` 的历史证据，保留原始结果。针对审查的预算权威修复与当前测试源码见 [R1](r1/README.md)，盘后 PR52/54 原完整回归 **10+4+13 项均 exit 0** 见 [盘后证据](r1/afternoon/README.md)。首轮“同一数据库”仅涵盖新链路两模型，不足以证明与已有 Owner Agent 共享费用库，该缺口由 R1 修复。

实际 base：`a27f466e643cb7dd05e3be72b83402a4599a301f`（PR #54 已合并）。本证据来自开发者自测；独立验收为 **NOT_VERIFIED**。固定 HEAD 记录于本模块唯一 Draft PR 和交付回复；[validation.json](validation.json) 绑定实际测试源码 SHA、Adapter SHA 和命令结果。运行方法与未验证项见 [M2_PR11](../../M2_PR11.md)。

## 已通过

| 检查 | 实际结果 |
| --- | --- |
| `cargo fmt --all -- --check` | exit 0 |
| `scripts/with-msvc.ps1 check --workspace --all-targets --locked --offline` | exit 0 |
| `scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline -- -D warnings` | exit 0 |
| `scripts/with-msvc.ps1 test --workspace --locked --offline` | exit 0，**171** 个 Rust tests，包括 8 个新协议/数值/schema 用例和 libtest driver |
| `scripts/with-msvc.ps1 build --workspace --locked --offline` | exit 0 |
| `scripts/test-risk-portfolio.py --driver <current-library-libtest> --evidence docs/evidence/m2-pr11` | exit 0，**10/10**；[日志](portfolio-test.txt)、[结构化反证/实际命令](checks.json) |
| 原 `scripts/test-agent.py` | PASS，6 组进程/API/SQL 断言；[结果](agent-regression.json) / [复跑日志](test-agent-rerun.txt) |
| 原 `scripts/test-candidates.py` | 13/13；[日志](test-candidates-regression.txt) |
| 原 `scripts/test-research-review.py` | 11 项首轮通过；原 junction 单项正常 Windows 权限复跑通过，**12 个唯一用例均通过**；[首轮](test-research-review-regression.txt) / [复跑](review-junction-rerun.txt) |
| PR54 原真实 receipt 回放 + 当前源重审 | 原 receipt 可回放，当前仍 **BLOCKED / 两日 / INSUFFICIENT_MODEL_CONTEXT**；[审计](real-audit.json) |
| 原状态保全 | 原 observer、PR33、PR38、PR54 和旧 multimodal Agent 共 **20** 个文件，byte SHA + size + mtime 不变；[清单](preservation.json) |

所有新调用使用同一原 Rust Agent 数据库、原 `budget::reserve`、双门禁与任务审计。两种 Adapter 都构造生产 API 请求、经过认证头与响应/schema 解析；recorded 仅替代传输，libtest 的 loopback/故障点不编入生产 executable。**0 真实云调用、0 真实收费、0 新链路 Paper/Live 订单/资金写入**；纯统计基线不冒充云专家。

## 可核对的完整链

| 场景 | 原任务 / 调用 ID | 原 Registry |
| --- | --- | --- |
| 正常波动，三股票各 2,000 bps + 4,000 bps 现金 | risk task `86` / call `71`；Fusion task `87` / call `72` | `a88c3b4d0e6f487aee08bbaca675740afe6e3c38d343dbf707ac5e8ccb61e415` |
| 高波动，100% 现金，策略 v2 | risk task `88` / call `73`；Fusion task `89` / call `74` | `4b2b8a449c0642436814c31a6df7b9b65f25d4356a15b98b1e98fee38d8caf1c` |

[正常报告](synthetic-calm.json)、[高波动报告](synthetic-stress.json)、各自 `*-input.json` 保留 synthetic 输入、源码/Prompt/模型 pin 和 SHA；`*-inbox.json` 是原 #46 Inbox 的实际只读结果。模型可发现未持有的 `300999.SZ`，但它仅为 `DISCOVERY_UNVERIFIED`，不能成为持仓目标或执行候选。

[checks.json](checks.json) 含独立 Decimal 算法对未发送给模型的合成后缀进行误差复算，以及 Naive/EWMA/录制响应的费用/误差比较。时延和 TST 费用来自原调用，真实费用/校准/alpha 未验证。[original-evaluator.json](original-evaluator.json) 证明原 Owner 模板关联 → freeze → 独立 evaluator 的接线；评价对象仅是原固定 synthetic 模板，不能当作新组合策略已获得独立资格。

## P0/P1 反证

- 新 scope 不继承旧 fake grant；无预算/价格/Key、错接收方/字段/协议/原 scope、未核实 query 费用上界均拒绝。真实 BigQuery HTTPS 始终 `BIGQUERY_BILLING_BOUND_NOT_VERIFIED`。
- 固定 SQL/project/dataset/location/model/列/行数/horizon；无任意 URL/SQL/工具、生成代码执行或原始行情字段外发。DeepSeek 实际字段为 `max_tokens`，不沿用旧兼容字段。
- 两个实际 loopback 请求分别到 query/chat 路径；检查假认证头、请求字段和原始 bars 不进入 Fusion。测试进程设置不可用系统代理仍到达 loopback；重定向只收到一次请求，没有跟随。
- 单批次、单次、日/月、跨日/月未知承诺上限；双真实进程互斥；复制批次和改变 Git 环境不能重新创建预算权威或重复领取冻结输入。
- reserve 前撤销、reserve 后撤销/降低 cap/变更 receipt/**Owner CLI disable** 均阻止 dispatch；已知未发送的 reserved call 为 `no_charge`，不是未知调用退款。
- dispatch 后 timeout、HTTP redirect、坏 schema、非法权重/未知持仓/无限数字保留最大预留；不重试、不切模型、不自动修复权重、不登记候选。每个负例断言具体拒绝原因，预算耗尽不能替代 schema 验证。
- 真正 kill 原 Agent/libtest 进程，覆盖 dispatch 后、收到响应后、settled commit 后；原 `Store::recover` 保留未知/已结算状态，同一任务不二次调用或计费。
- 敏感错误正文不保存/不输出，保留原结果 SHA 和安全错误码；真正环境 Key 不被录制传输读取或发送。
- 84 closes/64 rolling context、未来/过期/坏输入、原结果 SHA、模型实际执行 pin、单位、交易日映射、权限和策略版本均验证。Naive/EWMA 与云响应分别留痕；VaR/ES/协方差不编造。

先红后绿见 [red.txt](red.txt)：原配置不认识真实 Adapter，且复制旧 grant 可通过新 scope 检查；最终 8 项 Rust 新协议测试和 10 项进程测试通过。

## 保留的环境失败与未验证回归

**没有声称全量 Python 回归通过。** [regressions.json](regressions.json) 和各 `*-regression.txt` 保留实际退出码/失败。

- PR52 原 `test-multimodal-research.py` 在 `setUpClass` 明确要求当天 16:00 后，上午执行为 **0 tests / precondition failed**。原路由 4 项的合成源时间也在当天 16:xx，早于该时点运行得到 `CLOCK_BEFORE_SOURCE_OR_PREVIOUS_SYNC`。原测试定义未修改。
- PR54 原完整 13 项 synthetic suite 的 fixture clock 高于上午 wall clock，出现 `READINESS_CLOCK_REGRESSED`；该完整 suite 当前 **NOT_VERIFIED**。本次原真实 receipt 内容回放及当前 BLOCKED 审计已单独通过。
- 全 workspace Rust 首轮使用沙箱外 TEMP，原报表 kill/recovery 用例遇到 Access denied，见 [首轮](rust-test-sandbox-first.txt)；改用新 ignored workspace TEMP/TMP 后 171/171 通过，没有改金融核心或测试。
- 原 Agent 进程/API 首轮缺完整静态资源；补充隔离测试 stub 的 `index.html/assets/app.js/assets/app.css` 后通过，没有构建/修改 Dashboard。原审阅 junction 首轮沙箱拒绝，仅原失败用例正常权限复跑通过。

重复开发的早期 TST 故障用例先证明跨期预留被保留，再通过**原 `stratided --agent-settle` 可信接口**记录仅针对本机录制/loopback 的显式合成零账单，[synthetic-invoice-test.json](synthetic-invoice-test.json) 保留 23 次调用引用。没有删除 calls/tasks、改变 cap 或重建数据库，也没有声称真实账单已核实。最终测试产生的未知预留继续保留；运行结束仅将新研究开关 disable。

真实网络/OAuth/IAM/Provider Key/供应商权重版本、完整 BigQuery 费用与账单、留存/再分发许可、真实跨股票 PIT/前向前缀、校准和预测优势均 **NOT_VERIFIED**。没有付费/外发/交易授权。保持 Draft；费用/凭据高风险点待固定 HEAD 的针对性独立复核，Owner 显式批准前不 Ready/合并。
