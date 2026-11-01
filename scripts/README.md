# Local development helpers

Avoid mandatory Python/Node/Docker tooling for the trading core. Prefer a few transparent scripts over an elaborate build orchestrator. Local scripts for M0 are intentionally deferred until needed.

## 离线候选与独立历史评价

`python scripts/research-candidate.py --registry <名称> register/freeze/evaluate/status` 提供 M2-PR04 完整核心链路；固定白名单模板、输入/协议冻结、隔离新 ledger/report、默认拒绝前向和实盘资格。用 `research/synthetic-candidate.example.json` 可无行情离线运行；真实历史只读既有冻结源。`python scripts/test-candidates.py` 验证端到端、持久化/重复执行、进程中断和权限/证据反证。完整命令与状态见 [M2-PR04](../docs/M2_PR04.md)。

## 离线 EOD 同步与研究快照

Python 3.12+：`python -B scripts/research-data.py --store <名称> sync --observer <既有observer目录>` 只读核验原 journal，生成新 `state/data-sync/` 状态；同名称可重复 `sync`、`status`、`snapshot`、`consume`。`sync --fixture` 提供固定 synthetic_test 样例。无行情/Provider 调用；`consume` 不创建 Agent 任务。`python -B scripts/test-data-snapshot.py -v` 运行聚焦自测。schema、错误/恢复及真实离线命令见 [M2-PR05](../docs/M2_PR05.md)。

M2-PR06 的 `eod-research summary/run/task` 显式运行本地 fake 研究并保存真实任务，`register --snapshot-store` 复核来源，`research-candidate.py source <registration SHA>` 查询冻结文本与拒绝资格。先构建 `stratide-research`，再运行 `python -B scripts/test-eod-agent.py --evidence` 完成无 UI E2E；故障测试为 `python -B scripts/test-eod-agent.py -v`，Windows junction 测试需要允许创建测试目录链接。详见 [操作/边界](../docs/M2_PR06.md)。

## EOD 自动研究与候选归档

`python -B scripts/eod-auto-research.py --name <新名称> init --snapshot-store <已绑定store>` 创建独立本地 fake 自动研究目录，默认 OFF。Owner 通过 `enable/disable/pause/resume` 控制，`once [--sync]` 与前台 `watch [--sync]` 复用原 Agent 和候选注册；`status/task/candidate` 只读。仅上海当天 16:00 后的原 on-day EOD、新鲜同步可触发，每源日一个任务。`python -B scripts/test-eod-auto.py --evidence` 执行实际 synthetic CLI/中断恢复/并发反证；构建与完整操作见 [M2-PR07](../docs/M2_PR07.md)。

## 本机 Paper Dashboard

在仓库根目录执行 `pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir '<既有六报告目录>'`，构建并打开 `http://127.0.0.1:8710`；Ctrl+C 停止。没有输入时显示未配置。`test-dashboard.py --historical-report '<本机68日报告目录>'` 对真实进程验证字段、原文件只读及刷新/重启一致性，证据只含结构性摘要。见 [Dashboard 说明](../apps/dashboard/README.md)。

## EOD 连续观察

`observe-eod.ps1 -Journal <已有观察目录> -Reports <新报告根目录>` 默认执行一次 `forward-eod-step`；加 `-Watch -MaxDays 5` 在当前前台进程等到每日 Asia/Shanghai 16:00，最多处理 5 个自然日期。不会安装任务、保存 Token、自动补旧日或反复重试失败。失败停止，重启仍从原 journal 判断；完整操作和限制见 [PR04B](../docs/M1_PR04B.md)。

## 自动 EOD Operator

`python -B scripts/eod-operator.py --snapshot-store <已有store> init --observer <已有observer>` 默认 OFF，绑定同源 Shadow 和可选 `--auto-name <已有FakeAuto>`。Windows 用 `credential` 一次配置当前用户原生凭据，`enable` 一次授权后运行前台 `watch --interval-seconds 300`，跨进程无需逐次确认；`disable` 持久阻止后续批次/阶段。15:15 起检查，V1 保留原 collector 16:00–17:15 正式采集窗口，未知或失败槽不自动重发。`status/history/verify/report` 严格只读；完整配置、恢复与状态见 [M2-PR09](../docs/M2_PR09.md)。`python -X utf8 -B scripts/test-eod-operator.py` 运行隔离 synthetic/loopback HTTP/原 Rust Fake 的 E2E，不调用公共行情。
