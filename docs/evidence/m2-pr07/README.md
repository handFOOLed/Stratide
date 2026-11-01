# Issue #43 开发自测与反证

2026-11-01，Windows x64、Python 3.12.10、Cargo 1.98.1。固定 base `dd39133d656298d1bef6f5b799e28284f627783f`，分支 `codex/issue43-eod-auto-research`，最终固定 HEAD 写在唯一 Draft PR 正文。**Sol 独立开发、自测及修复，agents=0；没有 Terra/子代理、独立验收或合并结论。**

本目录只含 synthetic 自动研究过程、脱敏命令/结果、计数与 SHA。实际 SQLite/WAL、原行情、Owner token、来源路径及未脱敏命令保留在新 ignored `state/`。完整操作与恢复规则见 [M2-PR07](../../M2_PR07.md)。

## 完整 CLI E2E 与重复触发

[cli-e2e.json](cli-e2e.json) 保留两个新隔离目录的完整纵向命令与 JSON 结果：原 PR33 synthetic observer → 原 sync → init 默认 OFF → once 拒绝 → enable → watch 单轮/原 Agent `tick` → 保存 fake calls/result → 原候选 register → task/candidate/status 查询 → 进程重启后 once → 不变 sync → 同日修订 sync → 再次 once。没有人工制造 completed/result，也没有新策略执行能力。

该 synthetic 源日固定为 **2026-10-27 18:00 Asia/Shanghai** 的测试时钟，原观察仍为原 17:00 源时间。Python 测试入口注入时钟，Rust 使用仅 `cfg(test)` 编译的同一桥接逻辑；该桥还检查新测试目录及原 fixture 的 `host=synthetic_test`。生产 Python/Rust CLI 不接受 `--now`，测试环境变量也不能覆盖生产时钟。

两份目录的冻结输入、研究内容、资格限制及最终逻辑计数一致；忽略目录/来源身份、内容寻址任务/归档身份和进程墙钟。每份最终均为 **1 intent / 1 task / 1 fake call / 1 registration**。不变同步、同日 snapshot SHA 修订和重启后的重复触发均 **0 新任务、0 新 fake call、0 新登记**，返回 `ALREADY_ARCHIVED_INPUT_FROZEN`。原 task 查询仍为同一冻结详情。

`status/task/candidate` 跨进程查询前后 Agent SQLite 主文件 SHA 一致；断言输出没有原价格、instrument、raw、账户、token 或绝对路径。候选维持 `SNAPSHOT_CONTENT_VERIFIED_AT_REGISTRATION / TASK_ORIGIN_NOT_ATTESTED / RESEARCH_ONLY / NOT_EVALUATED / ELIGIBILITY_DENIED`。

## 进程中断、并发与跨日

[auto-e2e.json](auto-e2e.json) 是实际 **13 项测试全通过** 的结构化结果；五个节点均由测试进程 `os._exit(86)` 真正中断，使用原目录重启，不删除旧状态：

| 中断节点 | 中断后 intent/task/call/registration | 重启后 |
| --- | --- | --- |
| `after_intent` | 1 / 0 / 0 / 0 | 1 / 1 / 1 / 1 |
| `after_task` | 1 / 1 / 0 / 0 | 1 / 1 / 1 / 1 |
| `after_research` | 1 / 1 / 1 / 0 | 1 / 1 / 1 / 1 |
| `after_registration` | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1，补记同一 SHA |
| `after_archive` | 1 / 1 / 1 / 1 | 1 / 1 / 1 / 1，直接去重 |

并行 `watch --cycles 1` 与 `once`，竞争者返回 `STORE_BUSY`，最终仍为 1 / 1 / 1 / 1。fake 已 dispatched 时另一进程执行 `disable`，状态立即持久关闭；已提交 fake 正常保存与归档，后续 once 为 `OWNER_DISABLED`。pause/resume 跨进程保留原 Agent 状态；已排队取消不产生调用或登记。

追加 10/28 synthetic on-day 观察后，可在下一测试源日继续研究：正常两日为 2 / 2 / 2 / 2；第一日排队后错过的场景为 2 / 2 / 1 / 1，旧任务保持 `cancelled / AUTO_MISSED_OR_STALE`，没有回填旧日。未提交的意图事务不会被只读 status 看见，rollback 后只创建一个真实意图。

任务完成后来源变化且尚未登记，`SOURCE_CHANGED_REVIEW_REQUIRED`，保留原 1 task / 1 call / 0 registration；不换新输入、不重复研究。登记已提交但 SHA 未写回时，即使来源后来修订，也可通过原真实任务定位已有内容寻址登记，幂等补记同一 SHA。

## 时间、来源、权限与预算反证

- 16:00 前、跨日、超 24h、历史 late backfill、源日不等于上海当天、没有新源日、未知日历/缺有效日：SKIPPED/BLOCKED，0 新任务；生产 `--now` 被 argparse 拒绝。
- 原 observer 在最新 sync 后改变：`SOURCE_CHANGED_SINCE_SYNC`，显式 sync 后才消费已发布新版本。来源身份、摘要 SHA、最近 running sync、权限提升、缺内容与损坏 WAL 均拒绝；实际 Windows junction 指向也被拒绝。
- cloud kind/endpoint/key、真实预算币种：`EOD_AUTO_LOCAL_FAKE_ONLY`；同时直接调用生产 Rust `check` 验证同一阻断。错误模型配置、撤销 grant 也在研究前拒绝。对应 Agent DB SHA 保持不变，0 task / 0 call / 0 registration；没有 DNS、Key 或真实预算预留。
- TST 日预算不足：原 Agent task 为 `failed / DAILY_BUDGET_EXHAUSTED`，0 call / 0 registration。伪造 `task-export.json` 不能驱动归档；下一次从真实 Agent DB 重建，只有实际完成的 fake 结果进入原注册器。自然语言候选不能提升账户或策略资格。
- 原 Agent 的真正 dispatch kill/未知费用持久化、无盲重试与 HTTP 权限反证仍由原 `test-agent.py` 进程测试验证。新自动模块面对 running/failed/cancelled/uncertain 原任务保留人工复核状态，不冒充 completed。

## 实际命令与退出码

[verification.json](verification.json) 列出命令、计数、可执行文件 SHA 与未验证项；[test-results.txt](test-results.txt) 是最终原输出的脱敏副本。所有构建/测试离线，无 paid CI。Python regression 使用新输出目录，原报表/账本作为只读输入。

| 命令 | 最终退出码 / 结果 |
| --- | --- |
| `cargo fmt --all -- --check` | 0 |
| `with-msvc.ps1 check --workspace --all-targets --locked --offline` | 0 |
| `with-msvc.ps1 clippy -p stratide-research -p stratided --all-targets --locked --offline -- -D warnings` | 0 |
| `with-msvc.ps1 test --workspace --locked --offline` | 0；**156** 项通过 |
| `python -B scripts/test-eod-auto.py --evidence` | 0；**13** 项实际跨进程/CLI 测试通过 |
| `python -B scripts/test-eod-agent.py -v` | 0；原 **6** 项通过 |
| `python -B scripts/test-data-snapshot.py -v` | 0；原 **11** 项通过 |
| `python -B scripts/test-candidates.py -v` | 0；原 **13** 项通过 |
| `python -B scripts/test-agent.py --assets-dir state/issue43-validation/assets --output state/issue43-validation/agent-result.json` | 0；原真实进程认证/暂停/取消/预算/dispatch kill/保全检查通过 |
| `python -B scripts/test-historical-dividend.py --exe target/debug/stratide-cli.exe --out state/issue43-validation/historical-dividend` | 0；PR42 原 **11** 项通过 |
| `python -B scripts/test-cash-dividend.py --exe target/debug/stratide-cli.exe --out state/issue43-validation/cash-dividend` | 0；PR40 原 **9** 项通过 |
| `python -B scripts/test-historical-data.py` | 0；原 **3** 项通过 |
| `python -B scripts/test-research-evaluation.py` | 0；原 **5** 项通过 |
| `test-historical-replay.py` + 原冻结 68 日/source + 新输出目录 + 六个显式合成风险/本金参数 | 0；双目录六报告一致、kill/restart、原 raw SHA、财务守恒与未来价格反例通过 |
| `test-eod-agent.py --observer <既有observer>` | 0；原手动 fake/候选链路仍可消费原两日研究材料；没有采集新日 |
| 生产 `research-data sync` → auto init/enable/once/status/disable，真实时钟 | **3（预期）**；`BEFORE_EOD_WINDOW`，0 新 task / fake call / registration |

原 Agent 服务测试无需构建 Dashboard。本次仅给测试脚本增加 `--assets-dir`，在新 ignored `state/issue43-validation/assets` 放三个静态 stub，运行真实 Rust API/Agent 测试；没有修改 `apps/dashboard/**` 或验证新 UI。原默认测试资产路径不变。

## 旧数据保全与真实时钟

[preservation.json](preservation.json) 列出 **27** 个实际读取的旧文件/sidecar 逐项前后 SHA，全部一致：原真实 observer；68 日冻结 dataset、五来源、ledger/六报告；旧手动 Agent、snapshot 及其原 WAL/SHM；旧 registration/固定 candidate；既有 v4 财务与 77 会话情景 dataset/ledger/report。没有打开旧 Agent writer、停止服务、复制在线数据库、重建或迁移旧库。保护范围只指这 27 个文件，不泛称所有历史材料都已复验。

前后清单 SHA 均为 `1d0ac53c0ba544e15dbb80bd805e5d7505b25fc98f53e9b68f00c14612ceaba2`。真实路径仅保存在本机 `state/issue43-validation/protected-local.json`。

[real-auto-skip.json](real-auto-skip.json) 记录实际生产时钟的反例：重新只读 sync 既有 `forward_observed_eod`（最新原源日 10/29），新自动目录显式 enable 后 once 返回 `BEFORE_EOD_WINDOW`，task/call/registration 均为 **0**；最后关闭这个测试目录。没有把旧两日、68 日 replay 或 77 会话 EX_POST 情景变成 11/1 前向观察。

## 开发中实际发现并修复的问题

首轮解析旧 snapshot CLI 的 pretty JSON 错误，修正测试消费方式；Windows pipe 中文采用系统编码，生产入口显式使用 UTF-8。授权撤销检查曾发生在 Agent 打开之后，现前移到 Store/恢复之前，拒绝时旧 Agent DB 字节不变。

并发测试实际捕获 Owner 控制与 fake 结果写入竞争，原 500ms 等待产生 `AGENT_STORAGE_UNAVAILABLE`；控制事务缩短、仅新 auto DB 增加到 5s 等待后，同一反证通过。损坏 WAL 与已有 SHM 的组合会被 SQLite 忽略，现打开 SQLite 前检查非空 WAL 头；缺 SHM 和坏头分别确定拒绝。

Windows 沙箱内创建 junction 失败，测试在允许创建隔离 junction 的宿主权限下执行并验证真实拒绝。原全仓报表恢复测试在系统临时目录出现 `Access is denied`，原 Agent init 临时路径也退出 1；测试 TEMP/TMP 放到本 worktree 新 ignored 目录后均通过。测试安排曾使 Cargo 与正在运行的测试服务竞争 `stratided.exe` 文件；等待测试服务退出、串行重新执行全仓测试后 156 项通过。上述失败没有记为 PASS；原始失败日志留在本机 `state/`。

## 未验证项目

没有新真实交易日的自动 EOD 研究验证，**新增真实前向天数为 0**。真实 Provider/DNS/Key/费用、第三方账单、实时数据延迟、实际开市、真实 PIT/开盘、真实成交/NAV、策略 alpha 与自动晋升均 **NOT_VERIFIED/BLOCKED**。新模块没有这些能力或许可；TST 只是原 fake 合成记账。

Linux/macOS、物理掉电、OS 重启和长期 watch 稳定性未验证。原 Risk、Ledger、replay、forward observer/wire、真实 Provider/计费机制、Dashboard 与 HTTP 权限路由均未修改。固定 HEAD 的 ChatGPT 审查与 Owner 合并授权尚未完成。
