# V1 风险预测评价冻结协议

对应 Issue #76。冻结配置为 `config/risk-evaluation-v1.json`；本文件与配置先于任何本期预测误差运行提交。资产沿用 Owner 原三证券，日期按日历规则选取，不查看效果更换窗口或剔除资产。2022 开发、2023 验证、2024 测试，每月 15 日及之后首个已知开市日；84 个收盘价上下文，后续 20 会话全部在同一分段，否则记录 PURGED_SPLIT_BOUNDARY。缺源、停牌、因子变化、昨收断点和异常跳变拒绝整个资产/起点，不补值。

目标固定为未年化 rolling20 RMS daily return ratio，未来每会话的目标只用于预测完成后的评分，不送入 Worker。Naive 延续最后 rolling20 RMS；EWMA 用全部上下文日收益平方，lambda=0.94，初始化为第一日收益平方，作为常数预测。5/20 期分别报告逐点 MAE、RMSE、sMAPE 及均值预测误差；相同资产/起点做配对 MAE 差。每个资产/起点等权，每个目标会话等权；零/零 sMAPE=0，无除零填充。

滚动目标相互重叠、资产相关，范围和胜率仅描述，不输出假独立置信区间。每分段不足 20 个完整起点为 INSUFFICIENT_EVIDENCE。整个历史曾被 PR62/64 等研究暴露，全部标记 previously_exposed；时间切分可复算，但不能重命名为独立保护 holdout。真实本地结果为 EX_POST_RESEARCH_ONLY / PIT_NOT_VERIFIED；不足或失败也必须封存。

数据读取复用 V1/V2 已准入版本和 PR75 质量语义，固定版本上界、元数据 SHA、模型和代码 pin。不重验 2500 万行、不读取 Token、不下载权重、不发新行情或云请求。每次运行在新 ignored 目录冻结协议、来源与起点，文件独占写入；完成后 seal 绑定全部报告与输入文件，重复 run 只读复核，未封存中断运行禁止自动重跑。修改配置、来源版本、模型或代码产生新 pin，旧结果只按旧快照核验，不覆盖。

TimesFM 是本地 CPU 风险预测；未实现的纯本地规则 Fusion 明确 NOT_IMPLEMENTED，不编造对照。DeepSeek FusionResearcherV1 只走 synthetic recorded/loopback，与真实 OOS 隔离，任何真实行情、风险结果、派生统计/匿名摘要均不得云外发。GitHub 只交状态、计数、时间、来源/报告哈希和合成反证；真实指标及逐样本文件留本机。

工程完成、事后评价、PIT 可用与前向 Paper 资格分别报告。#10/#17 不因本软件合并关闭；N100 真机 NOT_VERIFIED。无 Risk Kernel/Ledger、券商、订单、UI 或部署变更。
