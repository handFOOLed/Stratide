# M2-PR19 脱敏证据

真实首验 **BLOCKED / PORTFOLIO_SCHEMA**，不是通过的真实组合。最终 HEAD 的本地工程回归通过，真实完整链路的组合验收尚缺。

- [唯一真实调用](real-api-smoke.json)：原 CNY Agent 任务 2，一次请求，1021 输入 + 684 输出 token，按高峰全 cache miss 估算 **¥0.007514**；最大预留 **¥0.098304** 仍占用，未冒充 invoice。原任务/调用记录不重置；重复 once 后仍 1 次调用。
- [预算](budget-after-smoke.json)：整个真实 Agent 的 **CNY ¥5/日、¥100/月，Asia/Shanghai**。日剩 **¥4.901696**，月剩 **¥99.901696**；旧 TST 没有换币种。Fusion 已 OFF，没有开启 EOD 自动付费研究。
- [真实本地 CPU](local-cpu.json)：原任务 1，真实 pinned TimesFM CPU 完成并 verify，0 calls，`development_only=false`；维持 cgroup 6 GiB/bwrap/无网络。N100 真机仍 NOT_VERIFIED。
- [新 Fusion 回归](fusion-regression.txt)：**6/6**，合成 loopback 完整经过原 Registry/Inbox/report/verify；本地失败、跨 Owner/来源变化、全现金/非法组合、撤销竞态、重复 once、429/500/超时/断开/缺 usage、Key 回显及私有响应 SHA 改动均有断言。libtest 不调用外网，也不编译进生产 CLI。
- [Rust workspace](rust-workspace.txt)：**204/204**，串行运行，含 Risk、Ledger、研究数据校验；[精确 CNY/原共享预算](shared-budget.txt)为 **3+6**。
- [PR17](pr17-regression.txt) **5/5**；[PR18](pr18-regression.txt) **11 通过 + 1 Windows 专属项跳过**；[Linux 隔离](linux-isolation.txt) **4/4**。
- [旧 PR56 完整首轮](pr56-full-initial.txt) **12/13**：原 `FUTURE_OR_STALE_SNAPSHOT` 在撤销测试到达 fault marker 前拒绝；未改门禁或旧测试。[单独复测](pr56-targeted.txt) **1/1** 通过。原 Ledger 默认并行锁抖动不扩展修复，workspace 使用 `--test-threads=1`。
- [命令和退出码](validation.json)。base `10804ea7231f24bdb84667802587c06ae8397bba`；最终 HEAD 记录在 Draft PR，避免自引用提交哈希。

首验在响应诊断补丁前运行，只保留了 SHA 和 usage，没有具体响应或 Provider request ID。其 decoder 已经过官方 model/usage 检查后在 Portfolio schema 处拒绝，但无法确定实际缺少/多出哪个字段。最终补丁保留本机私有有界 HTTP 成功响应供离线诊断，并提示精确根字段/类型；原 V1 严格校验、费用未知预留和禁止自动重试均保留。**补丁没有再次真实调用，不能宣称最终 HEAD 已解决真实返回格式。**

这里没有密钥、真实密钥路径、账户/真实行情、模型权重或原始 Provider 响应。只外发两条合成风险摘要；无新 Tushare 请求、RAW 解析、全量历史复验、订单、Paper/Live 准入。真实失败没有进入 Registry，合成归档不能替代真实成功。

后续若要补齐真实组合验收，需 Owner **另授权一次**有界合成请求；不能沿用已消费的单次许可或通过新 batch 重放。
