# Research / Agent

**当前 main 尚无可运行的研究 Agent。** [Issue #22](https://github.com/handFOOLed/Stratide/issues/22) 由 Sol 实现云模型 Provider、受信任日/月预算闸门、持久任务队列、EOD 调度与本地 API；基础交互先可用，正式视觉交由 DeepSeek 的 [#23](https://github.com/handFOOLed/Stratide/issues/23)。

研究不得写入 Risk Kernel/权威 Paper 账本、持有交易密钥或自己通过独立验证；未完成可信 Worker 沙箱前不得执行模型生成的任意代码。无 Owner 许可、预算或服务商配置则不发出付费调用。详见 [ADR-006](../docs/adr/0006-independent-validation-isolation.md)、[ADR-012](../docs/adr/0012-adaptive-research-daily-hard-budget.md)、[ADR-013](../docs/adr/0013-one-time-cloud-data-consent.md)、[Agent UI 交接](../docs/UI_HANDOFF_DEEPSEEK.md)。
