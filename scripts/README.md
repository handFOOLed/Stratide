# Local development helpers

Avoid mandatory Python/Node/Docker tooling for the trading core. Prefer a few transparent scripts over an elaborate build orchestrator. Local scripts for M0 are intentionally deferred until needed.

## 本机 Paper Dashboard

在仓库根目录执行 `pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir '<既有六报告目录>'`，构建并打开 `http://127.0.0.1:8710`；Ctrl+C 停止。没有输入时显示未配置。`test-dashboard.py --historical-report '<本机68日报告目录>'` 对真实进程验证字段、原文件只读及刷新/重启一致性，证据只含结构性摘要。见 [Dashboard 说明](../apps/dashboard/README.md)。

## EOD 连续观察

`observe-eod.ps1 -Journal <已有观察目录> -Reports <新报告根目录>` 默认执行一次 `forward-eod-step`；加 `-Watch -MaxDays 5` 在当前前台进程等到每日 Asia/Shanghai 16:00，最多处理 5 个自然日期。不会安装任务、保存 Token、自动补旧日或反复重试失败。失败停止，重启仍从原 journal 判断；完整操作和限制见 [PR04B](../docs/M1_PR04B.md)。
