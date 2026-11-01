# M2-PR10 开发自测证据

2026-11-01，Issue #51，起点 main `c3904a5eb31f40209b32beba559e82ba4e47fd8a`。这是单人开发自测，**independent_acceptance=NOT_VERIFIED**。真实付费模型调用 0、公共行情/模型请求 0、新增真实前向日 0；测试网络只有旧 Agent API/Operator 的 loopback fixture。

## 两套实际生产 CLI

两套独立新建 schema-1041 合成 journal，经**原 PR33 sync CLI** 发布，各含 25 个明确 synthetic 日历会话；生产 CLI 使用当天实际盘后时钟。原 Rust Agent 建立/执行/预留/结算，原 Registry 登记；没有手工构造完成的 task JSON。原 Inbox 可读；第一套另以测试中的显式 Owner 操作验证原模板关联与原 Evaluator，资格仍拒绝。`once` 自身不执行模板或评价。

| synthetic E2E | 冻结实验 task_id | report_sha256 |
| --- | --- | --- |
| A | `e75c3dc79ff3bdcf1ef8b4d2342bc8796449fddc8d29bf1cb0a20aa318965a64` | `a251d8a209435a84112ff7b8d5ab34c93fa01aa2708606fe20c8dc7b360f6645` |
| B | `a8e99e26bc39360074351a5d64a2b43974e7610df2a9cf1463d3ce65d9b481ec` | `1beffeae5d246e0bfb4ed7db3af9250c5d80fd2a4a7931c0db45e5a0c32287bc` |

[A 完整研究报告](e2e-a-report.json)、[B 完整研究报告](e2e-b-report.json) 含 Snapshot/窗口/专家/Fusion/原 task/原登记 SHA、基线与时序数值、独立 Decimal 校验、TST 预留/结算与 token/耗时来源、四个后续合成标签。`report_sha256` 对不含自身字段的紧凑 canonical JSON 计算；原 Registry/task-detail 继续使用原带缩进与换行的编码。

两套各有 4 个时间正序前缀比较点，缺失/拒答率均为 0。A 的 Naive/时序 MAE 为 `0.002397174285 / 0.001943327206`，B 为 `0.002408255894 / 0.001971238455`，单位是每会话收益比例。它们来自确定生成且已曝光的合成趋势，**不能推出真实策略优势、胜率、独立 holdout 表现或收益**。Fusion 只报告假设，不打价格预测正确率分。

## 执行结果

精确 CLI、退出码和逐项摘要见 [checks.json](checks.json)、[regressions.json](regressions.json)。路径仅作 `<checkout>/<authority>` 脱敏；原始本地执行记录保存在新 ignored state。

| 检查 | 最终结果 |
| --- | --- |
| `python -B scripts/test-multimodal-research.py --evidence docs/evidence/m2-pr10` | **10/10，exit 0**，含双 25 日完整 E2E |
| `cargo fmt --all -- --check` | exit 0 |
| `cargo check --workspace` | exit 0，[输出](rust-check.txt) |
| `cargo clippy --workspace --all-targets -- -D warnings` | exit 0，[输出](rust-clippy.txt) |
| `cargo test --workspace` | **160 passed / 0 failed / 0 ignored，exit 0**，[输出](rust-test.txt) |
| `cargo build --workspace` | exit 0，[输出](rust-build.txt) |
| 原 PR33 Snapshot | 11/11 |
| 原 PR35 EOD Agent | 6/6 |
| 原 Candidate Registry | 13/13 |
| 原 PR44 自动研究 | 16/16 |
| 原 PR46 Inbox/Owner Review | 12/12 |
| 原 PR48 Shadow | 9/9 |
| 原 PR50 Operator | **18/18 唯一用例**：沙箱内 16 项通过，2 项原生 junction/合成 Windows Credential Manager 用例移出沙箱重跑通过 |
| 原 Agent API 真实进程验证 | [6 项检查 PASS](agent-regression.json)，仅 loopback + local fake |
| Python syntax / `git diff --check` | exit 0 |

Windows 使用已安装的 VS Build Tools `VsDevCmd.bat -arch=x64 -host_arch=x64` 加载 MSVC。系统 TEMP 曾拒绝测试目录创建/重命名，最终将该进程的 `TEMP/TMP` 指向新建 `state/rust-temp` 后完成 Rust 全套及 Agent API。Agent API 仅使用 `state/agent-api-assets` 三个静态 stub，无 UI 构建。原链接测试仅在其隔离合成目录运行，原生凭据测试只写入并删除随机测试 target，不读取真实凭据。没有为通过测试修改旧生产逻辑或旧测试定义。

## 反证和恢复

- [红→绿记录](red-green.txt)：复制新 scope grant 给云 Provider 的测试，修改前继续到 `PROVIDER_KEY_MISSING`，修改后在密钥/DNS 前按 `MULTIMODAL_LOCAL_FAKE_ONLY` 拒绝。旧 EOD scope 回归继续通过。
- 强类型专家/Fusion 拒绝 `authority=TRADE`、工具/资金/价格/预算额外字段、命令/脚本/URL/路径、长 JSON、错误时区、未来生成时间、错误源 SHA、NaN、伪造数值、校准区间、冒充原 Agent task。独立 Decimal 复算确实检出不一致 Adapter；失败不会改写成成功。
- 日/月不足、撤销、云配置、未知调用及未决占额均通过原 Rust Agent/Budget 验证；未知结果不自动重试。同源改名不能抢归属，所有实例共用一个原 Agent 预算库，不能改名清零。
- 两个并发进程只产生一个原 task/call；禁用与启用交错时停用边界阻止后续排队/dispatch，不伪造已经提交的调用被取消。
- `after_freeze / after_experts / after_queue / after_fusion` 四阶段 `os._exit(86)` 后，由新生产 CLI 进程恢复为唯一任务/调用/登记。最后一阶段故意在原 fake settled、尚无 Candidate 时修改并重新同步源；恢复只使用旧保留 Snapshot 与原 settled 记录，不重发。
- 21 日不足、缺口、未来 bar/as-of、标签泄漏、修订/晚补、过期、模式混用和时钟回退均拒绝；真正 forward 模式不足显示 `INSUFFICIENT_FORWARD_HISTORY`。forward 模式负例来自明确标注的测试 journal，不是新真实观察。
- `status/history/verify/report` 的 bytes、mtime、sidecar 均保持；原 Snapshot/observer 和旧 evidence/samples 的文件指纹保全。原财务内核、撮合、账户账本、NAV、采集协议、Accepted ADR 未修改。

## 未验证

真实外部时序 Provider、云 Fusion、报价/账单、数据外发授权/许可、真实公司行为 PIT、开盘来源、真实前向 Paper、长期无人值守、物理断电、Linux/macOS 与独立策略价值均未验证。本期未接可选 #50 Operator 自动研究阶段，保留显式 `once`；未实现 text_event 专家/完整多模态消融。所有结论仍为 `RESEARCH_ONLY / ELIGIBILITY_DENIED`，Draft 待固定 HEAD 独立审查，不 Ready、不合并。
