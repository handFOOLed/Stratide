# V1 收尾 A：本地风险评价、前向证据与 FusionResearcherV1

> **历史参考**：本文记录旧阶段的实验、规划和问题清单；“当前/Draft”以当时版本为准。
>
> [文档中心](README.md) · [当前版本](STATUS.md) · [架构总览](ARCHITECTURE_OVERVIEW.md)

对应 [Issue #76](https://github.com/handFOOLed/Stratide/issues/76)。基于 PR #75 合并后的 main `d557aa1cd721df66accdddbe7b22afb184736ecc`，WSL Ubuntu ext4 独立工作树；Core-only、单人、唯一 Draft PR。[预先冻结的协议](V1_EVALUATION_PROTOCOL.md)与[配置](../config/risk-evaluation-v1.json)先于本期评价提交。

## 运行与读取

只使用原本机已经准入的 V1/V2 仓库、原模型权重与 venv。不需要 Token，不配置或启用云调用。Linux 运行环境沿用 [PR18](M2_PR18.md) 的 cgroup v2 + systemd user manager + bubblewrap；额定内存 6 GiB、无 swap、CPU-only、私有网络和最小只读挂载。

```bash
cargo build --workspace --locked --offline
python3 -B scripts/risk-evaluate.py freeze \
  --v1-root "$V1_ROOT" --v2-root "$V2_ROOT" \
  --out state/my-frozen-evaluation
python3 -B scripts/risk-evaluate.py run --out state/my-frozen-evaluation
python3 -B scripts/risk-evaluate.py report --out state/my-frozen-evaluation
python3 -B scripts/risk-evaluate.py verify --out state/my-frozen-evaluation
python3 -B scripts/verify-risk-evaluation.py state/my-frozen-evaluation
```

`freeze` 不读价格或评价效果：固定版本上界、已准入元数据、官方日历、资产、切分与模型/代码 SHA。读取只触及两库元数据和明确资产/日期的已准入行，不重验 2500 万行/raw。`run` 复用原 Rust `project/decode` 评价接口和原隔离 Worker；它不是第二套 Agent、预算或财务系统，不创建付费任务，也不写 Owner 的 Agent tasks/calls/meta、Registry 或 Ledger。旧 CPU task/Registry/Fusion 由原回归及只读验证单独核对。

每个资产/起点先保存并验证严格上下文，完成预测后才读取 20 个未来会话用于评分。未来公司行为/质量故障只能导致 TARGET_BLOCKED，不能改变过去的 Worker 请求。保留原 OHLC、昨收、因子、停牌、单位、实际下载时间、来源版本与质量。无检测到因子变化不等于公司行为/PIT 已认证。

stdout 只返回状态、计数、pin；完整指标和逐样本文件只在本地 ignored 目录。**不能将真实行情、风险预测、派生指标或匿名摘要复制到云模型或 GitHub。** 提交证据只包含状态、时间、计数、命令与必要哈希。

```text
state/my-frozen-evaluation/
  frozen.json / freeze.json           协议、版本/模型/代码和来源 pin
  samples/<split-day-instrument>/     严格前缀、实际 Worker 收据、未来评分输入与失败原因
  report.json                        5/20 期指标、配对差、覆盖/失败率、资源与准入矩阵
  seal.json                          所有 JSON 的不可覆盖发布清单
```

文件独占创建、flush/fsync 后封存；重复 `run` 只读核对已完成结果，不推理、不计费。未封存但已开始的运行报告 INTERRUPTED，禁止盲目重跑，必须另建冻结目录。`verify` 校验原 seal；独立脚本不导入生产算法，用 Decimal、标准库和捕获的源数据复算切分、无未来输入、RMS/EWMA、拒绝原因、指标、配对差和报告哈希。它是独立算法，不是另一位审查者的独立验收，更不是来源或历史 PIT 认证。

## 评价语义

模型固定 TimesFM 2.5 200M CPU；Naive 和 EWMA 与它预测同一个未年化 rolling20 RMS daily return ratio。5/20 期分别报告逐点 MAE/RMSE/sMAPE、均值预测误差，另有 TimesFM 与两个基准的逐资产/起点配对 MAE 差、覆盖、失败原因、supervisor/Worker 时间、CPU 和 RSS/cgroup 峰值。所有模型使用相同的已评分样本；输入/目标阻断、模型失败和 split purge 均留在分母与排除清单，不补零或按效果筛资产。

窗口重叠、资产相关；配对范围与胜率只是描述，不伪造独立置信区间。**R1 审查发现冻结协议存在结构性矛盾：每段一年、每月一个起点，最多 12 个不同起点，低于固定的 20 个最低完整起点。** 即使行情全部完美也不可达；purge、上下文和日历缺口还会降低实际容量。不能将不同资产重复计算成独立起点。

配置、20 个门槛、资产、日期和旧 seal 均不修改。新报告 schema 2 的 `protocol_capacity` 明确报告 `STRUCTURALLY_UNREACHABLE`、`maximum_monthly_origins=12` 和 `required_complete_origins=20`；每段 `sample_evidence_status` 单独报告实际样本是否不足。总 `hypothesis_verdict` 同样标记结构性不可达。对于旧 schema 1 报告，`report/verify` 和独立复算只增加当前协议的只读容量诊断，返回 `stored_report_schema_version=1`，不会改写原判定或重签报告。统计门槛若需可达，必须另立版本，在新的未观察样本上预冻结；本次不新建评价协议、不重跑已暴露的真实历史。整个历史曾用于 PR62/64 等研究，仍只可描述性 ex-post / PIT NOT_VERIFIED；时间切分不意味着保护 holdout，也不证明未进入预训练语料。不得将风险预测误差说成价格方向、Alpha、收益、账户 NAV 或交易资格。

纯本地规则 Fusion 对照标 NOT_IMPLEMENTED，不虚构排名。DeepSeek synthetic/recorded 结果单独验契约，不进入真实 OOS 指标表。

## 前向只读审计与准入矩阵

```bash
python3 -B scripts/risk-evaluate.py audit \
  --observer "$ORIGINAL_OBSERVER/forward.sqlite" --through 20261103 \
  --v1-root "$V1_ROOT" --v2-root "$V2_ROOT" \
  --out state/new-forward-audit
# 如有与原 observer 关联的既有 Operator 日志，可额外传 --operator-root <operator.sqlite>
```

重新计算原 journal 的链/raw/单位/时序，并用已取得的交易所日历逐自然日区分 ON_TIME、LATE_BACKFILL、MISSED、BLOCKED、CLOSED、NOT_VERIFIED；未知日历不由星期几代填。只读审计不采新行情、不制造新前向天数；累计两日证据与后来缺口分别展示。当前日不自动记作漏采。Operator 只验证已有摘要链与 observer 前缀关联；其 Snapshot/Shadow/Fake 下游引用、凭据和运行权限独立，不伪称均已验证。

`audit.json` 和评价 `report.json` 提供同一机器可读 admission 矩阵：历史 PIT、2026-07-06 前费用、2024/2025 公司行为、2026 事件的实际税务/到账与 PIT、开盘实收、逐日公司行为覆盖及真实前向 Paper 成交的**证据声明**仍标 BLOCKED/NOT_VERIFIED，并列外部依赖和来源文档 SHA。按 Owner 更新的 #19/#76，这些项的 scope 为 `EVIDENCE_CLAIM_ONLY`，`engineering_merge_blocked=false`、`eod_paper_integration_blocked=false`；不阻挡工程交付或 EOD Paper/Dashboard 集成。真实数据外发项单独标记 `REAL_DATA_EGRESS_AUTHORIZATION`，继续硬拒绝。这里的研究产物 `paper_allowed=false` 表示它本身不授予执行权，不代表全产品禁止 EOD Paper。#10/#17 保持 Open；N100 和实际未取得的证据不冒充通过。

T 日盘后取得并校验的 T 日 `daily.open` 是当时已知历史，可用于冻结 T+1 决策，不能拿它充当 T+1 成交价。未来若用 T+1 `daily.open` 作 Paper 成交假设，应待 T+1 盘后取得，按 T 日已冻结的意图、数量和撮合规则事后确认，标记 `EX_POST_OPEN_ASSUMPTION`；不得看价后选择下单/撤单或称为开盘窗口实收。该 EOD Paper 集成属于 #77，本 PR 不实现新的成交路径。

## FusionResearcherV1

内置的 [system](../research/agent/prompts/fusion-researcher-v1-system.txt) 与 [developer](../research/agent/prompts/fusion-researcher-v1-developer.txt) 模板组合成原 DeepSeek Chat Completions 的高优先级 system 指令，版本和精确 prompt_sha256 进入请求契约与新收据。原 receiving service/purpose/synthetic grant、¥5/日与¥100/月、预算最大预留和一次许可沿用，不扩大范围。

```bash
./target/debug/fusion-researcher-contract descriptor
# 离线 validate / validate-evidence 从 stdin 读取 JSON；不读 key、不调用 Provider。
# 原 synthetic Fusion once/report/verify 入口仍为 scripts/local-timesfm-fusion.py。
```

输入只接受固定 synthetic RMS、Naive/EWMA、来源 SHA、UNKNOWN 和已知质量字段；不可信文本标签/输入模式、工具要求或来源错配在 dispatch 前拒绝。输出采用 `controlled-conclusions-v2` 封套，内部 `portfolio` 仍是 TargetPortfolioProposal V1，保留全现金/拒绝研究方案。封套仅包含以下三个字段：

- `portfolio`：原来源、身份、资产、权重守恒与能力 Gate 继续校验。叙述字段只能使用 descriptor 中的固定命题标识，不允许任意自然语言；`proposal_id` 只作受限 ASCII 标识符。
- `conclusions`：精确匹配绑定的来源引用和保守状态，包括 synthetic、PIT NOT_VERIFIED、收益方向 UNKNOWN、收益保证 NOT_ESTABLISHED、UNCALIBRATED、账户 UNKNOWN、预算/订单权限 NONE、资格 ELIGIBILITY_DENIED。缺失、增补或升级状态均硬拒绝。
- `untrusted_hypothesis`：`classification` 必须为 `UNTRUSTED_HYPOTHESIS`，所有自由叙述、前提、反证、风险、失效条件与实验建议只放在其 `text`。这是模型原文隔离区，**即使包含错误断言也不构成已验证证据或权限**。它不会进入通用 `Research.hypothesis/evidence/risks/next_steps`、受控 portfolio 或资格结论；读取 JSON 的报告保留该分类，不能脱离分类引用正文为结论。原 wire/receipt.content 仅作未信任响应审计。

硬拒绝策略是结构化字段精确匹配及原 Schema/来源/能力 Gate，不宣称能够证明任意自然语言的语义，也不继续增加换词黑名单。中英文强断言放在受控结论位置会被拒绝，放在隔离的假说区只被保留为未信任原文。

模型响应失败/工具调用/错误 schema/错误标签/不受控结论不进入成功结果；已发送但收费不明仍为 outcome_uncertain，保留最大预留且不重发。旧 Prompt 的已完成历史请求按原 adapter pin、原 system、原冻结模型及 wire 解码，绝不以当前 Prompt 重签旧报告。R1 的旧模板与解码仅用于历史复核，报告显式标记 `LEGACY_UNTRUSTED_HYPOTHESIS_NOT_REQUALIFIED`，旧关键字检查不作为新任务保证。新任务只使用当前 pin。

开发验证仅使用 recorded/loopback 与合成 Owner，不为测试花钱。源语义参考 Tushare 官方 [daily](https://tushare.pro/wctapi/documents/27.md)、[adj_factor](https://tushare.pro/wctapi/documents/28.md)、[suspend_d](https://tushare.pro/wctapi/documents/214.md)、[trade_cal](https://tushare.pro/wctapi/documents/26.md)：daily 未复权、停牌无行；pre_close 为除权昨收，成交量手、金额千元。常规更新时间不证明某行历史首次可用。

实际测试、真实本地运行状态与失败保留记录见 [原脱敏证据](evidence/v1-closeout-a/README.md)及 [R1 修复简报](evidence/v1-closeout-a/r1-fix.md)。工程可用、ex-post 评价和真实性声明分别报告。个人模式以相关本地绿测和简短说明收尾，外部固定 HEAD 审查及大包证据不作为强制门禁；由 Owner 决定合并，开发者不自行 Ready/merge。
