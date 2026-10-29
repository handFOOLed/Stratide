# M1-PR06 研究协议 v1（先冻结规则，后读取新评价结果）

任务：[Issue #13](https://github.com/handFOOLed/Stratide/issues/13)。base `de043bf1146b8256cf5218465c9a3004e3ec24fe`。本文件先独立提交；后续实现不得按收益修改这些规则。既有 68 日/3 成交结果已公开，本轮 holdout 从来不是未见过的盲测。

## 冻结对象与数据 Gate

- 单标的 `600000.SH`，`sma5-20-cross-fixed100-v1`、SMA5/20、100 股、close±2% 限价及 `next-open-adverse-tick-100-v1` 不变。20 根 close 只预热，全部信号仅用当时及之前 close。
- 模拟初始本金 10,000,000 分；单笔 500,000 分、账户/策略敞口各 2,000,000 分、日亏损 100,000 分、回撤 500,000 分。沿用 Issue #11 的六个显式 CLI 参数；真实资金为 0。
- 采集目标固定为 20240101–20261028，使用既有授权 Tushare MCP 四接口或 Owner 原冻结源。先审计实际 SSE 日历、日线、价格带、停复牌、Decimal 分/股、`pre_close` 连续性、规则/费用适用期。原始 payload、参数/字段、实际提取时间、修订局限及 SHA 只写新 ignore 目录。
- 不跨越公司行为断点，不扩大现有 20260706–20261231 规则/费用有效期。长窗口不可支持则 `DATA_BLOCKED`，不伪造历史规则/公司行为。描述窗口取**包含固定结束日的最后连续可支持区段**：开始为规则下界与最后断点后一日的较晚者；任何缺失/未知不跳过。不能按盈亏、成交数选区间。若结束日缺失则阻断，不偷偷缩短结束日。
- 每个有效原始交易日排序后 `k=floor(N*70/100)`；development 为前 k 日，historical holdout 为剩余日。完整性通过后、调用 replay/评价前写入 split 记录。N<2 时不划分。分界不因表现移动；整个单一 ledger 连续运行，跨界订单、持仓、费用及 Risk 锁不清零。holdout 起点本金是前一交易日 NAV，缺边界估值则相关指标 null。

## 评价、独立基准和压力定义

- 只读完整生成并经原 CLI 校验的 ledger/六报告，另写 `evaluation.json/csv`。绑定输入 SHA、策略/模型/费用、protocol、ledger head、报告 SHA 及实际 split；不改六报告。
- full/development/holdout 各报有效日、缺口、提案/拒单/成交、起止现金/NAV、持仓/pending、净回报、每日最大回撤、费用、成交每交易日频度、持仓/空仓收盘比例。持仓时间为日观察数，不猜盘中时长；跨界持仓计入持仓日但不伪造新成交。回报使用精确整数分和 Decimal，窗口起点以前一日 NAV 计算，不重置账本。
- 现金基准：从该窗口起始 NAV 持有现金，零利息/零费用。独立买入持有：各窗口首日开盘独立发起固定 100 股、open+1 分模型买入，沿用原风控/费用/next-open 引擎，在**独立新模拟账本**执行；不是同时运行的资金复制，也不依赖策略首次买入。首日停牌/未知/价格带/资金或风控拒绝则显示 `NOT_EVALUATED`，不延后挑入场日。只持有不卖出、不扣假定离场费。以同窗本金比较净回报及最大回撤；明确固定 100 股、不同持仓时间，非风险匹配 alpha。
- 预定压力仅为 `posthoc_cost_bound`：在既有每笔成交上另扣 500 分、另扣 1000 分两档，使用同一已实现成交序列；不重新计算订单、风险、持仓或成交概率，不称 scenario_backtest。NAV 差额/费用拖累不是可执行组合，不能用该结果授权交易。
- Sharpe、年化、胜率、显著性一律 null+reason（本版本不做推断统计）；不以 3 笔或无交易得出统计优势。无交易/不足 504 个有效日/holdout 不足 126 日/holdout 不足 20 个完成买卖回合，研究状态为 `INSUFFICIENT_EVIDENCE`。这些是必要样本下界，达到也只标 `DESCRIPTIVE_ONLY`，永不自动证明策略有效。
- `data_coverage`（完整性/目标覆盖）、`research_evidence`、`engineering` 独立。负收益、落后基准、没有交易都是有效研究输出，不是工程失败。未知估值 null，不能补零。实际提取时间不是历史逐日 PIT；historical holdout 非 prospective OOS，已暴露窗口不能再次声称全新独立盲测。

## 边界与验收

P0：T+1 行情变异不改变 T 决策；改评价分界不改 ledger；逐日现金+有效持仓估值=NAV，费用不重扣，收益与资金流一致。P1：两个新目录产物一致；缺数据、无交易、末日 pending、短样本诚实标注；基准首日独立。执行 Windows fmt/check/test/Clippy 和 Python/实际 CLI。Sol 仅自测并创建 Draft PR；Terra 独立验收为 NOT VERIFIED，禁止合并。Issue #10 和所有旧 raw/journal/ledger/六报告只读。
