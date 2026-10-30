# Research / Agent

**Agent V1 与 M2-PR04 候选 CLI 已在 main；本分支新增 M2-PR05 数据快照，Draft 待审。** `candidates.py` 支持已保存研究来源/Owner 固定模板的登记、版本冻结、独立历史回放评价和默认拒绝资格。[候选操作](../docs/M2_PR04.md) 包含无需 Provider 的完整 synthetic_test 样例。Agent 操作见 [M2-PR02](../docs/M2_PR02.md)，字段见 [Agent API](../docs/AGENT_API.md)。

- `agent/`：可信研究服务与费用闸门；只有文本研究，不执行生成代码或写财务/风控。
- `eod_journal.py` / `data_snapshot.py`：原 1041 observer 只读核验、独立持久研究快照、状态和 offline 消费 adapter。[M2-PR05 契约](../docs/M2_PR05.md)；入口 `python scripts/research-data.py --store demo-eod sync --fixture`，再执行 `consume`。尚未接线到 Agent 自动调度，所有交易资格为 false。
- `agent-settings.example.json`：有效的未配置模板；没有默认供应商、资金或授权。
- `fixed-candidate.example.json`：既有 SMA5/20 历史候选，配置/窗口/费用不可由文本改变；`synthetic-candidate.example.json` 只验证既有人工模板的工程链路。所有运行记录保存在 git-ignored `state/candidates/`。
- `--agent-init-fake <新目录>`：确定性本地 fake，TST 金额为 synthetic_test。真实 HTTPS 路径需 Owner 明确配置与授权，否则 **REAL_PROVIDER_NOT_VERIFIED**、不发起付费调用。

研究不得写入 Risk Kernel/权威 Paper 账本、持有交易密钥或自己通过独立验证；未完成可信 Worker 沙箱前不得执行模型生成的任意代码。无 Owner 许可、预算或服务商配置则不发出付费调用。详见 [ADR-006](../docs/adr/0006-independent-validation-isolation.md)、[ADR-012](../docs/adr/0012-adaptive-research-daily-hard-budget.md)、[ADR-013](../docs/adr/0013-one-time-cloud-data-consent.md)、[Agent UI 交接](../docs/UI_HANDOFF_DEEPSEEK.md)。
