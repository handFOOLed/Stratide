# M2-PR06 Windows / Sol 开发自测

2026-10-30；固定 base `2fdd05d5eb2ffa8f2d5c25267ffcc9204b7a1370`，独立分支 `codex/m2-pr06-snapshot-agent`。Owner / [Issue #34](https://github.com/handFOOLed/Stratide/issues/34) 指定 **仅 Sol 开发和测试，agents=0**；没有 Terra、子代理或其他模型测试。开发自测不等于独立验收；Draft 的固定 HEAD 交 ChatGPT 源码审查，Owner 单独授权才可合并。

## 实际结果与退出码

Windows、Python 3.12.10、rustc 1.98.1；Cargo 全部 `--locked --offline`，使用已有 MSVC。没有依赖下载、行情请求或真实模型调用。

| 实际命令 | 结果 |
| --- | --- |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 build -p stratide-research -p stratided -p stratide-cli --locked --offline` | exit 0；实际构建 headless Fake Agent、原服务及既有 replay CLI |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 fmt -p stratide-research -p stratided -- --check` | exit 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 check -p stratide-research -p stratided --all-targets --locked --offline` | exit 0 |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 test -p stratide-research -p stratided --locked --offline` | exit 0，**31/31 PASS**：research 22、stratided 9；[脱敏日志](rust-tests.txt) |
| `pwsh -NoProfile -File scripts/with-msvc.ps1 clippy -p stratide-research -p stratided --all-targets --locked --offline -- -D warnings` | exit 0；[脱敏 check/Clippy 日志](checks.txt) |
| `python -B scripts/test-eod-agent.py -v` | exit 0，**6/6 PASS**；[日志](eod-agent-tests.txt) |
| `python -B scripts/test-candidates.py -v` | exit 0，**13/13 PASS**；[日志](candidate-tests.txt)，含原 register/freeze/evaluate/status、隔离 ledger、费用/NAV、kill/重启、缓存及篡改拒绝 |
| `python -B scripts/test-data-snapshot.py -v` | exit 0，**11/11 PASS**；[日志](snapshot-tests.txt)，含原 observer 时间/重复/修订/质量/发布恢复 |
| `python -B scripts/test-eod-agent.py --evidence` | exit 0，固定 synthetic 快照 → 真正 Agent/fake 完成任务 → 新进程读取任务 → 候选 CLI register/source；[脱敏 JSON](synthetic-e2e.json) |
| `test-eod-agent.evidence_run(existing_observer, protected_files)` | exit 0，同一实际 pipeline 消费既有真实两日 observer，只读保全 11 个旧文件；[脱敏 JSON](real-e2e.json)。同函数可用下述 CLI 复现 |

最终 Rust 验证使用 `CARGO_INCREMENTAL=0`，避免当前沙箱不支持增量缓存 hardlink 而退化为复制的工具链提示；没有修改生产源码解决环境权限。Windows junction 测试由宿主执行权限运行，链接仅位于新测试目录，测试完成后删除；没有跳过安全断言。

真实只读验证的公开可复现入口（路径由 Owner 本机提供，不写入仓库）：

```powershell
python -B scripts/test-eod-agent.py --observer '<既有forward.sqlite>' --protect '<旧ledger.sqlite>' --protect '<旧Agent SQLite>'
```

`--protect` 可重复指定。此次实际清单是原 observer、旧历史 ledger、六报告、旧 Agent SQLite、旧 candidate.json、旧 registration JSON，共 **11 文件**；始末没有 WAL/SHM/journal，SHA 全部一致。没有停止真实服务、打开在线 Agent writer 或复制旧库；旧 Agent/历史文件只做哈希，真实任务在新隔离库执行。保护清单摘要：`fc0fb8b88db30191486c5788d43d1dc7940c131612f45601bae090fd3ddd419f`，前后一致。这里只证明列明的 11 个静止文件，不泛称过去全部旧记录已复验。

## 真实运行的来源链

| 维度 | 仓库固定 synthetic | Owner 已保存的真实 EOD |
| --- | --- | --- |
| 模式 | `synthetic_test` | `forward_observed_eod` |
| 有效源日 | 10/26–10/27，最新 `2026-10-27` | 10/28–10/29，最新 `2026-10-29` |
| Snapshot SHA | `130d08df702c94c4cfa782e3202c7843ca90e562421a5719f1980edc3b57ff3b` | `3def7bf43e54d889a68db292b09cfe0885782f650438792b01baff70f44cde03` |
| 任务/调用 | task `1` completed，1 个 fake settled 调用 | task `1` completed，1 个 fake settled 调用；不同隔离 run |
| 冻结详情 SHA | `c6765dc623f5bce56f7b0637f3049ae450affd096be56816706d9097abef7c62` | `db0a56dfe551971ddc8142e4069aced9802dfee0a27158e68590f8c5325af056` |
| 登记 SHA | `e0e249425784245ee65dbf157b142bfd176f2c541c924f04930af5d7ebd61f75` | `176166755782b13f4ebd9e680ccc5012c1d4dc0857e754d2e9be57e1dc20c5e6` |
| 结果 | `RESEARCH_ONLY / NOT_EVALUATED / ELIGIBILITY_DENIED` | 同左 |

真实原 observer SHA 为 `d4020489f0485554ec092e9e8e84026998aa54248ac3268df46aeb040ee0585e`，来源与 PR #33 的已保存绑定相同。重新 sync 只验证已有记录，没有采集 10/30，不能把本机“今天”作为新交易日。原 observer 和新 snapshot store 仍分开，Agent DB 只保存有限摘要、课题、文本和合成调用记录，没有原始行情。

两个 pipeline 都比较 Rust/Python 完整投影，真正调用 `Agent::create/tick` 后保存任务；新进程 `task` 返回同一 request/input/result/calls，库内仍为 1 task / 1 call / 0 eod 自动记录。候选 `register` 重跑复用同一登记 SHA，`source` 返回冻结研究文本。没有模板的来源不能 `freeze` 为 historical replay，返回原 `UNSUPPORTED_CANDIDATE`。

来源标为 **`SNAPSHOT_CONTENT_VERIFIED_AT_REGISTRATION`**，但任务始终为 **`TASK_ORIGIN_NOT_ATTESTED`**：本机快照匹配不等于 JSON 作者或 Agent 签发认证。没有重新开拓 Agent 数据库认证机制。未指定 store 的来源只能 `SOURCE_UNVERIFIED`；所有来源仍是研究材料。

## 已执行的拒绝与旧行为回归

- 真实 Provider 携带新 scope 时，无论旧 grant 或手工补齐 scope，均在 Key/DNS/预算预留前 `EOD_SNAPSHOT_LOCAL_FAKE_ONLY`；任务 failed、calls 空、reserved_micro=0，Provider health 不误报。旧 fake grant 不能借已有 paper/owner scope 使用新类别。
- 新显式快照永远不自动 EOD；旧开关 ON 也不创建任务。已排队冻结输入不随当前 store 失败而被改写；新任务在 60 秒旧缓存期内也重新校验。
- running/blocked/超过 24 小时、缺内容、未知 store/content 版、SHA 错误、源日/模式/质量/权限篡改均拒绝；即使同步把 fixture 的可变 mode 字段改成 forward，也不能冒充真实来源。
- 未提交 WAL 更新不可见，已提交而尚在 WAL 的 running 必须可见并拒绝；缺 SHM 不忽略 WAL。路径穿越与真实 Windows junction 被拒绝。
- 内部字段自洽但 snapshot SHA 与本机不匹配的任务仍拒绝；新 EOD 任务伪造 `qualification=PASS` 被拒绝。恶意自然语言只是冻结文本，不执行、不授予资格。
- 原报告摘要、历史评价 scope、费用/未知账单、Provider 状态、EOD 同日去重、账户 pinned API 与旧候选独立 evaluator 均由上述原测试覆盖；未修改其财务/账本实现。

## 首轮失败与修复

首轮 `python -B scripts/test-eod-agent.py -v` **exit 1：6 项中 1 failure + 3 errors**，没有记为 PASS。完整首次日志保存在 git-ignored `state/m2-pr06-validation/eod-agent-first.txt`；公开仅保留脱敏原因：

1. 候选 CLI 在 Windows pipe 使用系统编码输出中文冻结研究文本，UTF-8 消费者 `UnicodeDecodeError`，影响两项真实 CLI 流程。入口明确使用 UTF-8 stdout 后，同一来源/文本往返测试通过。
2. WAL 测试先提交 running，再重复写同一值，SQLite 未形成新的 WAL，断言 `0 > 0` 失败。测试先恢复 succeeded 基线，再持有 writer 提交 running，实际看到非空 WAL；确认 reader 读到已提交状态而不是主文件的旧状态。
3. 沙箱拒绝创建 Windows junction，后续聚焦诊断确认为 `Access is denied`。以宿主权限执行同一隔离测试后，成功创建 junction 并验证 reader 拒绝，没有把测试跳过或更改为普通路径。

## 未完成与风险边界

没有自动 Agent EOD/同步、真实 Provider 权限或请求、真实账单/预算预留、可信前向 Paper 订单/成交/NAV、策略晋升、Dashboard、历史 PIT 或独立开盘来源。原 Risk Kernel、权威 Ledger、历史撮合、forward schema、费用账本与 Accepted ADR 未改。fake 的 TST 预留/结算是原合成测试流程。

快照 SHA/本机路径规则证明本地一致性，不能防御拥有整个受信目录写权限者重写源和程序，也不认证供应商授权/远端身份。没有把只有研究来源的两日观察变成策略回测；本期未评价该候选，因此显示 `NOT_EVALUATED`，原历史候选的 `INSUFFICIENT_EVIDENCE` 不变。`historical_pit=NOT_VERIFIED`、`opening_source=BLOCKED`，所有执行字段 false。

Linux/macOS、物理掉电、OS 重启、真实云连通性及 ChatGPT 固定 HEAD 审查尚未完成；不安排 Terra 或机械独立复测。操作与字段见 [M2-PR06](../../M2_PR06.md)。
