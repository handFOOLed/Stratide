# ADR-038：无人值守的 Agent 自动审查、返修与 SHA 锁定合并

- 状态：**已接受（Accepted）**
- 日期：**2026-11-10**
- 决策者：**Owner**
- 适用范围：`handFOOLed/Stratide` 中 **Owner 已事先授权开发范围**的 GitHub PR（默认目标 `main`）
- 取代范围：对 [ADR-037](0037-observable-paper-trading-first-and-independent-review-gates.md) 第 5、6、7 条的**执行角色、逐 PR Owner 批准与人工合并流程**进行后续修订；ADR-037 的历史正文、Paper-only、安全与独立证据要求继续保留

## 决策

Owner 明确要求 **自动审查 → 自动返修 → 自动复审 → 自动合并，全程无人值守**。不再要求 Owner 对每个 PR、每次更新的 HEAD 逐一批准，也不以 ChatGPT 人工进入聊天为执行依赖。Owner 的授权提前作用于 Issue/任务的范围、费用和数据权限，并可随时撤销。任何 PR 都不得扩大已授予的范围。

1. **自动触发**：实施 Agent 自动实现、自测、创建 Draft PR；Ready for review 及每次 `synchronize` 后，必须自动触发 Codex 审查或等价独立审查。若自动触发失败，允许自动请求 `@codex review` 或调用替代审查器；**发出请求不是 PASS**。
2. **自动返修闭环**：由实施 Agent 对可复现问题自动修改、补回归并推送；每个新 HEAD 的审查、必需 CI 和独立反证一律重跑。旧 SHA 的 PASS 不能升级为新 SHA 的 PASS。有限次数重试；出现循环失败、工具缺失、无法安全修复时标记 `BLOCKED` 并通知，不盲目继续。
3. **独立性与分级**：普通 UI/文档变更可用与实施者不同的审查 Agent 验证；预算、凭据、数据外发、Risk/ledger、恢复、隔离等高风险变更必须增加针对失败路径的独立反证。不得用同一实施 Agent 的自评替代审查记录。独立证据必须绑定确切 SHA 与实际测试环境。
4. **自动合并门禁（全部满足）**：任务范围、目标仓库/base 均在授权之内；当前 HEAD 已取得独立审查 PASS；所有相关必需检查及高风险反证通过；没有 P0/P1 或其他明确阻断；没有无授权的付费、真实数据外发、实盘或安全约束变更。由合并执行器以 `expected_head_sha` 或等价 SHA 条件请求 squash 合并，条件不匹配则重新审查。禁止未授权直推 `main`。
5. **GitHub 门禁**：应实际配置 ruleset/branch protection、当前 HEAD 检查和审查门禁；`Allow auto-merge` 仅是功能开关，不是安全约束。自动修复推送新 HEAD 前须取消任何旧合并意图。若规则未强制检查，合并执行器必须显式核验所有条件且绑定 SHA；若不能证明则停在 `BLOCKED`，**绝不能因为无人看守而跳过**。
6. **权限边界**：本决议**不是**真实交易授权，也不是对费用、凭据、数据外发、Risk、Ledger、隔离、预算上限的放宽。需要新增的外部权限或超出现有任务范围的行为，直接阻断并作为新的任务范围交由 Owner 决定；但已授权范围内的正常 PR 不再要求逐次人工批准。
7. **事实与验收**：文档只定义决策，不会自动创建 Codex Webhook、自动返修执行器或 GitHub ruleset。上线前须实测 Ready → review → 发现问题 → fix → 新 SHA review/checks → SHA 锁定 squash merge 的完整链路，并测试 reviewer 缺席、CI 失败、HEAD 竞态、权限越界、重复修复失败的 **fail-closed**。尚未通过实测时状态为 **POLICY_ACCEPTED / AUTOMATION_NOT_VERIFIED**，不得宣称运行中的无人值守系统已经启用。

## 相对于旧规则的变化

- ADR-037 原规定的「Sol 提 PR → Terra/ChatGPT 检查 → Owner 逐 PR 批准 → ChatGPT 合并」改为「实施 Agent → 独立自动审查 → 自动返修/复审 → 满足门禁后 Agent SHA 锁定合并」。
- 原本独立测试、风险与账本正确性、未知费用拒绝、Paper-only、数据时点证据规则 **没有废止**；执行职责从特定人工角色转为可审计的独立 Agent 和机器门禁。
- Owner 可以暂停工作流、撤回授权或重新定义任务，不需要为每个审查通过的 PR 参与例行合并。

## 实施验收追踪

本 ADR 决定目标流程；配套 GitHub 自动化的部署、权限配置和端到端演练由独立工程任务验收。**未建立运行机制前，不能将文档合并误报为功能上线。**
