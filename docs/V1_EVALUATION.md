# V1 收尾 A：本地风险评价、前向证据与 FusionResearcherV1

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

窗口重叠、资产相关；配对范围与胜率只是描述，不伪造独立置信区间。预冻结的有限样本可保持 INSUFFICIENT_EVIDENCE。整个历史曾用于 PR62/64 等研究；时间切分不意味着保护 holdout，也不证明未进入预训练语料。不得将风险预测误差说成价格方向、Alpha、收益、账户 NAV 或交易资格。

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

`audit.json` 和评价 `report.json` 提供同一机器可读 admission 矩阵：历史 PIT、2026-07-06 前费用、2024/2025 公司行为、2026 事件的实际税务/到账与 PIT、开盘实收、逐日公司行为覆盖、真实前向 Paper 成交及真实数据外发均保留 BLOCKED，并列外部依赖和来源文档 SHA。#10/#17 保持 Open。模型预训练重合未知、N100 真机、物理重启与真实 Provider 本期均不冒充通过。

## FusionResearcherV1

内置的 [system](../research/agent/prompts/fusion-researcher-v1-system.txt) 与 [developer](../research/agent/prompts/fusion-researcher-v1-developer.txt) 模板组合成原 DeepSeek Chat Completions 的高优先级 system 指令，版本和精确 prompt_sha256 进入请求契约与新收据。原 receiving service/purpose/synthetic grant、¥5/日与¥100/月、预算最大预留和一次许可沿用，不扩大范围。

```bash
./target/debug/fusion-researcher-contract descriptor
# 离线 validate / validate-evidence 从 stdin 读取 JSON；不读 key、不调用 Provider。
# 原 synthetic Fusion once/report/verify 入口仍为 scripts/local-timesfm-fusion.py。
```

输入只接受固定 synthetic RMS、Naive/EWMA、来源 SHA、UNKNOWN 和已知质量字段；不可信文本标签/输入模式、工具要求或来源错配在 dispatch 前拒绝。输出仍是 TargetPortfolioProposal V1，保留全现金/拒绝研究方案、前提、反证、风险、失效条件和下次实验。结构与来源、权重守恒、能力、机器可读 synthetic/PIT/UNKNOWN/uncalibrated 标签，以及明确无证据强断言分别验证；自由文字始终是未信任假说，不当成独立事实或权限。

模型响应失败/工具调用/错误 schema/错误标签/强断言不进入成功结果；已发送但收费不明仍为 outcome_uncertain，保留最大预留且不重发。旧 Prompt 的已完成历史请求按原 adapter pin、原 system、原冻结模型及 wire 解码，绝不以当前 Prompt 重签旧报告。新任务只使用当前 pin。

开发验证仅使用 recorded/loopback 与合成 Owner，不为测试花钱。源语义参考 Tushare 官方 [daily](https://tushare.pro/wctapi/documents/27.md)、[adj_factor](https://tushare.pro/wctapi/documents/28.md)、[suspend_d](https://tushare.pro/wctapi/documents/214.md)、[trade_cal](https://tushare.pro/wctapi/documents/26.md)：daily 未复权、停牌无行；pre_close 为除权昨收，成交量手、金额千元。常规更新时间不证明某行历史首次可用。

实际测试、真实本地运行状态与失败保留记录见 [脱敏证据](evidence/v1-closeout-a/README.md)。工程可用、ex-post 评价、真实 PIT 和 forward Paper 准入始终分开。
