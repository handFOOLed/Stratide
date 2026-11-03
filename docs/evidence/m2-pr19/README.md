# M2-PR19 脱敏证据

**真实合成完整链路已验证**：原本地 TimesFM CPU 任务 3 → 真实 DeepSeek Fusion 任务 4 → 原 TargetPortfolioProposal V1 严格校验 → 原 Registry/Inbox/report/verify。结果为合法的 100% 现金研究组合，Paper/Live 仍 BLOCKED，独立评价尚未进行。

- [追加授权的真实成功调用](real-api-smoke-r1.json)：Owner 另授权一次后发送 **1 次**，输入 **1065**、输出 **722** token；保守估算 **¥0.007906**，最大预留 **¥0.098304**。Provider model 为 `deepseek-flash`，request ID、请求/响应/来源 SHA、registration 和组合见 JSON。原始 Provider 响应仅本机私有保存，没有公开。
- [真实 CPU 任务 3](local-cpu-r1.json)：真实 pinned CPU 权重，completed + verify，`development_only=false`，0 calls。继续 systemd/cgroup 6 GiB/bwrap/无网络；N100 真机仍 NOT_VERIFIED。
- [当前共享预算](budget-after-r1.json)：**CNY ¥5/日、¥100/月，Asia/Shanghai**。累计两次授权调用共 **2086 输入 + 1406 输出 token**，估算 **¥0.015420**；两次最大预留共 **¥0.196608** 未释放，日/月剩余 **¥4.803392 / ¥99.803392**。这不是 invoice；不清空旧账或把 TST 转为 CNY。
- verify/report/Inbox 全部 exit 0；Inbox 1 条，`AWAITING_OWNER_TEMPLATE / NOT_EVALUATED`。关闭外发后重复 once 仍复用任务 4，累计 calls **仍为 2**，没有第三次调用或 EOD 自动付费研究。
- [首次真实失败](real-api-smoke.json)和[首次预算快照](budget-after-smoke.json)原样保留：`PORTFOLIO_SCHEMA`、1021/684 token、估算 ¥0.007514。核对旧结果存储 SHA 未变，旧 call 仍 `outcome_uncertain` 且预留未释放；它没有被改写为成功。
- 新请求使用原 PR 生产代码 `fbc05bbb290a35da38ce1f104ac4e8df19917e01`，adapter SHA 与首次交付最终代码一致。此次只更新文档/证据，沿用 [Rust 204/204](rust-workspace.txt)、[Fusion 6/6](fusion-regression.txt)、[精确 CNY/原共享 Budget 3+6](shared-budget.txt)。
- [PR17 5/5](pr17-regression.txt)、[PR18 11 通过 + 1 Windows 专属跳过](pr18-regression.txt)、[Linux 隔离 4/4](linux-isolation.txt)。
- [旧 PR56 完整首轮](pr56-full-initial.txt) 12/13：原 `FUTURE_OR_STALE_SNAPSHOT` 在到达 fault marker 前拒绝；未改旧测试或门禁，[单独复测 1/1](pr56-targeted.txt)通过。Rust workspace 使用 `--test-threads=1`，不扩展修复原并行锁抖动。
- [命令/退出码与追加验证](validation.json)。base `10804ea7231f24bdb84667802587c06ae8397bba`，最终 HEAD 记录在同一 Draft PR #72。

首次失败的具体回包没有留存，因此其字段差异仍无法还原。已有诊断补丁明确根字段/类型，并仅在本机私有保存有界且无 Key 回显的 HTTP 成功响应；追加调用使用该原代码通过严格校验，verify 对保存的实际字节复算 SHA，没有重新推理、补写组合或自动重发。

这里只包含合成研究输出与必要脱敏审计；无密钥、真实密钥路径、真实行情/账户、原始响应、模型权重。只外发两条合成风险摘要；无新 Tushare 请求、RAW 重解析、全量历史复验或订单。该通过结果证明工程链路，不构成 alpha、真实市场、独立资格或 Paper/Live 准入。
