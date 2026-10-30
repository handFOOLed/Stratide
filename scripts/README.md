# Local development helpers

Avoid mandatory Python/Node/Docker tooling for the trading core. Prefer a few transparent scripts over an elaborate build orchestrator. Local scripts for M0 are intentionally deferred until needed.

## 离线候选与独立历史评价

`python scripts/research-candidate.py --registry <名称> register/freeze/evaluate/status` 提供 M2-PR04 完整核心链路；固定白名单模板、输入/协议冻结、隔离新 ledger/report、默认拒绝前向和实盘资格。用 `research/synthetic-candidate.example.json` 可无行情离线运行；真实历史只读既有冻结源。`python scripts/test-candidates.py` 验证端到端、持久化/重复执行、进程中断和权限/证据反证。完整命令与状态见 [M2-PR04](../docs/M2_PR04.md)。

## 离线 EOD 同步与研究快照

Python 3.12+：`python -B scripts/research-data.py --store <名称> sync --observer <既有observer目录>` 只读核验原 journal，生成新 `state/data-sync/` 状态；同名称可重复 `sync`、`status`、`snapshot`、`consume`。`sync --fixture` 提供固定 synthetic_test 样例。无行情/Provider 调用；`consume` 不创建 Agent 任务。`python -B scripts/test-data-snapshot.py -v` 运行聚焦自测。schema、错误/恢复及真实离线命令见 [M2-PR05](../docs/M2_PR05.md)。

## 本机 Paper Dashboard

在仓库根目录执行 `pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir '<既有六报告目录>'`，构建并打开 `http://127.0.0.1:8710`；Ctrl+C 停止。没有输入时显示未配置。`test-dashboard.py --historical-report '<本机68日报告目录>'` 对真实进程验证字段、原文件只读及刷新/重启一致性，证据只含结构性摘要。见 [Dashboard 说明](../apps/dashboard/README.md)。

## EOD 连续观察

`observe-eod.ps1 -Journal <已有观察目录> -Reports <新报告根目录>` 默认执行一次 `forward-eod-step`；加 `-Watch -MaxDays 5` 在当前前台进程等到每日 Asia/Shanghai 16:00，最多处理 5 个自然日期。不会安装任务、保存 Token、自动补旧日或反复重试失败。失败停止，重启仍从原 journal 判断；完整操作和限制见 [PR04B](../docs/M1_PR04B.md)。
