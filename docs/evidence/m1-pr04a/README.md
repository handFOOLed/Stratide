# M1-PR04A Sol 自测证据

**历史记录：首次自测只描述当时提交。** 当前以 [R2](../m1-pr04a-r2/README.md) 和 Issue #7 的 Owner 更新为准：个人本机用途已由 Owner 接受，供应商独立授权未核实仅作限制披露，不自动要求书面证明或 Token 轮换。旧开发工具执行记录曾含明文 Token；“未进 Git/应用日志/报告”不能理解为零暴露，本文不重现值。旧 FAIL/BLOCKED 事实保留。

日期：2026-10-28，Windows x64 / Asia/Taipei。**Sol 自测，非 Terra 独立验收。** 源码基于 `main` 的 `4b53cf8`，PR 头提交单独在 PR 描述中准确列明；文档和证据提交不改变已测试的代码。

## 真实来源探测

先对现有 Tushare MCP 各执行一次 `daily(600000.SH,20261028)` 和 `trade_cal(SSE,20261028..20261028)`，均返回 1 行。这只证明该 MCP 通道，未保存包装响应、未当成本地 HTTP 原始字节证据，也没有把结果导入 journal。

随后 Owner 为本任务提供凭证；未读取 Stockie 或其他项目配置。本地只在命令进程设置 `STRATIDE_TUSHARE_TOKEN`，通过 `try/finally` 清除；凭证未加入 Git、应用日志或报告；开发工具执行记录曾包含明文，不能称为零暴露。本地 CLI `forward-source-check state/pr04a-owner-observer` 在开发中和最终代码上各进行一轮、每轮只有 daily/trade_cal 两个小请求，均成功，无购买、充值、重试循环。真正的 HTTP 原始响应只在内存解析后丢弃。`http-probe.json` 为最终一次的状态/哈希记录，不包含行情行或 Token。

最终 `provider.rs` SHA-256：`875d0111886afdb17b3ae81373d31ab5422cc5a099c6245931bfddcc048cb5ac`。`received_at` 为 UTC epoch 毫秒；最终探测 daily 为 2026-10-28 19:54:28.102 +08:00，trade_cal 为 19:54:28.973 +08:00。`clock_verified=true` 只表示 HTTPS Date 的粗粒度校验通过。实际账户积分总数、全部接口权限、长期稳定性未知；这两个端点在上述时刻的访问与关键字段可用已核验。

## 实际本地观察与报告

```text
forward-init state/pr04a-owner-observer samples/m1-pr04a-observer.json
  exit=0; started_at=2026-10-28T19:50:00.071+08:00
forward-collect-once state/pr04a-owner-observer
  exit=2; blocked_source_license_unverified (两次实际人工运行)
forward-status state/pr04a-owner-observer
  exit=0; events=5; attempts=2; valid_forward_days=0; proposals=0; fills=0
  HEAD=441f008e8eb1632010e7b96e0964958f941c72ceb12706843029de060e8a22c1
forward-report state/pr04a-owner-observer state/pr04a-blocked-report-final
  exit=0; 三文件导出；同 HEAD 重复导出 exit=0
```

`blocked-status.json`、`blocked-report.json` 和 `blocked-daily.csv` 是这些真实 CLI 输出的副本，内容只包含许可阻断，没有市场价格。原本地 `state/pr04a-blocked-report` 早期报告保留；代码字段细化后用新目标 `state/pr04a-blocked-report-final`，没有覆盖或重新解释旧文件。日志 `forward.sqlite` 未上传。有效真实 forward 采集入 journal **没有发生**，不是“成功空仓策略”。

## 合成/故障测试

`self-test.txt` 是最终 fmt/check/test/Clippy 输出，共 86 项通过；其中 9 项 forward 单测（包括子进程辅助测试）、1 项真实 CLI 跨进程集成测试。provider fixture 为测试代码内冻结的人工 JSON，证券日期和价格均为 **synthetic_test** 输入，不能算真实市场采集或真实未来观察。

覆盖精确整数分/股转换、字段/日期/日历缺口/权限拒绝、重复/修订/backfill、摘要/原响应篡改与尾事件丢失、SQLite 事务回滚、提交前后真实子进程退出、挂起意图恢复、单写入者、持久时钟倒退锁、immutable 报表和现有资金/持仓/风险回归。没有模拟真实 API 成功来消除许可阻断。

## 独立验收前的明确缺口

**BLOCKED**：本地自动化采集/持久保存的适用许可仍需明确依据。公开用户/数据服务协议及第三方数据限制见来源报告。持有 Token 和请求成功不能解除此门槛。

**NOT VERIFIED**：成功真实响应入 journal、两天真实未来持续观察、实际限流/停牌/节假日/修订、Linux/macOS、物理断电/磁盘满、独立开盘/交易规则/费用及任何策略成交。没有后台自动采集或付费 CI。等 Terra 同 SHA 独立验收、小猫审查和 Owner 合并授权；Sol 不合并。
