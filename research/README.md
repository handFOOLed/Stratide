# Research / Agent

**本分支已实现 Agent V1，Draft 待审。** [Issue #22](https://github.com/handFOOLed/Stratide/issues/22) 的 Provider、日/月预算、持久任务、取消/暂停、EOD 和 Web 基础交互形成完整闭环；正式视觉仍交由 DeepSeek 的 [#23](https://github.com/handFOOLed/Stratide/issues/23)。操作见 [M2-PR02](../docs/M2_PR02.md)，字段见 [Agent API](../docs/AGENT_API.md)，真实 [自测证据](../docs/evidence/m2-pr02/README.md) 不等于独立验收。

- `agent/`：可信研究服务与费用闸门；只有文本研究，不执行生成代码或写财务/风控。
- `agent-settings.example.json`：有效的未配置模板；没有默认供应商、资金或授权。
- `--agent-init-fake <新目录>`：确定性本地 fake，TST 金额为 synthetic_test。真实 HTTPS 路径需 Owner 明确配置与授权，否则 **REAL_PROVIDER_NOT_VERIFIED**、不发起付费调用。

研究不得写入 Risk Kernel/权威 Paper 账本、持有交易密钥或自己通过独立验证；未完成可信 Worker 沙箱前不得执行模型生成的任意代码。无 Owner 许可、预算或服务商配置则不发出付费调用。详见 [ADR-006](../docs/adr/0006-independent-validation-isolation.md)、[ADR-012](../docs/adr/0012-adaptive-research-daily-hard-budget.md)、[ADR-013](../docs/adr/0013-one-time-cloud-data-consent.md)、[Agent UI 交接](../docs/UI_HANDOFF_DEEPSEEK.md)。
