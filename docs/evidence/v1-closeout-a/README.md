# V1 收尾 A 开发者证据（Issue #76）

- **基线：** `d557aa1cd721df66accdddbe7b22afb184736ecc`（PR #75 merge）。
- **协议先行提交：** `7c42a67`；配置字节 SHA `fab03053a63963c06c904f2f421886cadd9f541edb2f698e2d1caed6c94fc8a1`，canonical JSON SHA `471d7e7136ec2645ce7210025f47fddcb18b372bacbc6ee2bdeb904435689cec`。
- **最终实现源码：** `e9fd6878816f10e0be22b869322242340349edb1`。其后提交只增加本目录证据，最终 PR HEAD 可用 [tested-source.json](tested-source.json) 逐文件 SHA 对照。单人、agents=0、WSL2 Ubuntu 原生 ext4。
- **身份：开发者自测 + 独立算法复算，不是独立审查者验收。** 不 Ready、不 merge；N100 真机 NOT_VERIFIED。

## 真实本地评价

预先固定原三证券、36 月度起点与分段，最终 108 个样本：**37 SCORED、49 INPUT_BLOCKED、7 TARGET_BLOCKED、15 PURGED**。排除和失败没有删除、补零或按效果替换资产。TimesFM、Naive、EWMA 使用相同已评分样本、5/20 期 rolling20 RMS daily return ratio。

最终冻结 pin `1a23f823e1cd48bddb18d8b8c245ef6afb059f1998a43739f8bc0651203c0388`。实际完成 `freeze/run/report/verify`，独立标准库程序复算 108 样本、37 个评分、137 项源质量判定、切分、RMS/EWMA/误差/配对差与报告哈希；exit 0。封存后重复 run 的 runner 被禁止，仍只读验证成功；无新推理。首轮旧 pin 的本地报告原样保留，两个实际运行的逐样本预测 SHA 相同，协议/模型/窗口未调优。

**真实指标、预测、完整冻结源和逐样本数据仅保留本地** `state/real-oos-v1-final/`，不提交，不复制到云模型。这里的 JSON 只含状态、计数、时间、允许的哈希和必要元数据；没有 MAE/RMSE 数值、行情、账户数据、SQLite、权重或密钥。外发状态一直是 REAL_MARKET_DATA_EGRESS_DENIED。

[真实运行脱敏摘要](real-run-summary.json)绑定本地完整报告和 seal 的 SHA。解释固定为 EX_POST_RESEARCH_ONLY / PIT_NOT_VERIFIED / INSUFFICIENT_EVIDENCE：历史已被既往研究暴露，重叠目标和相关资产不能当独立 holdout。没有同目标的本地规则 Fusion 预测器，明确 NOT_IMPLEMENTED；旧合成/云 Fusion 不进入真实排名。无 Alpha、盈利或真实交易能力结论。

## 前向观察与阻断

只读原 #10 journal，重算链/raw/单位/时序。**2026-10-28、10-29 两个当日有效 EOD** 的累计连续性保留 EOD_CONTINUITY_VERIFIED；截至 2026-11-03，后来日期有漏采或未知日历，当前连续性 GAPS_OR_UNVERIFIED。没有根据星期几编造开市日，没有新增观察、提案、成交或 NAV。没有与该原 observer 对应的已验证 Operator 日志，Operator=NOT_VERIFIED；不因此伪造管线成功。

[前向与机器可读准入矩阵](forward-audit-summary.json)保留 #10/#17：PIT、历史费用、公司行为、实际税务/到账、开盘实收、完整 action feed、前向 Paper 与真实外发均 BLOCKED，列出所需外部证据与文档 SHA。尚未结束的采集按日标 BLOCKED；只有自身链但没有 observer ref 的 Operator 不算 observer 验证。

## Prompt 先红后绿与兼容性

[精确反证](prompt-counterproof.json)：在原 main 生产代码加同一合成 loopback 反例，**无证据“保证盈利”和伪造 PIT 标签原来 completed**，新断言 exit 1。当前 FusionResearcherV1 将二者分别拒绝为 FUSION_UNSUPPORTED_CLAIM_OR_CAPABILITY / FUSION_PROVENANCE_LABELS_REQUIRED；工具调用原已被拒绝，继续由 DEEPSEEK_RESPONSE_PROTOCOL 拒绝。新 Prompt 的 system/developer 模板、版本与 SHA 可离线读取，仍用 TargetPortfolioProposal V1。

新旧路径均不把响应拒绝误当“肯定未计费”：已发送的非法响应保持 outcome_uncertain 和最大预留，重复调用不重发。合成输入中的指令文本、错误来源/单位和真实模式在 dispatch 前拒绝。原已完成 Fusion task 4 用原 Prompt/模型/wire 只读 verify=true；原 CPU task 9 与原 PR75 工作树的 Registry 也只读核对成功，没有迁移或重建。

## 检查与保全

| 检查 | 实际结果 |
| --- | --- |
| Rust fmt / build / clippy | exit 0；clippy 有 5 条旧警告，未声称 `-D warnings` |
| Rust workspace，串行 | **205 pass**，0 fail / ignored |
| 新评价与只读审计 | **11 pass** |
| Fusion recorded/loopback | **11 pass** |
| 旧历史 / 来源 / Registry / 真实外发拒绝 | **13 pass** |
| 旧 CPU 合成回归 | **11 pass + 1 Windows 专项 skip** |
| Linux 原隔离实测 | **4 pass、0 skip**：网络/文件/环境、OOM、超时崩溃、控制器退出回收 |
| 最终真实本地独立复算及只读重复 | exit 0 |

精确命令、退出码、未运行项见 [checks.json](checks.json)。未运行付费云、行情下载、N100、物理重启/断电、Windows 专项与独立人工验收。没有把旧结果冒充本轮新跑。

原 Owner **9 个 task、2 笔 calls 全列、meta 与 settings SHA** 前后相同；V1/V2 选定 DB/锁/sidecar 文件收据未变。新云调用、计费、市场请求、预算写入和真实 key/token 正文读取均为 0。监督进程拒绝 IP connect（实际尝试 0），原 Worker 的私有网络/最小挂载由 Linux 实测证明；Rust bridge 只调用 project/decode。

保留的早期失败：共享 target 复用旧编译路径导致绑定拒绝，改用每个合成 checkout 自身的原生 target；非登录 WSL 缺 Cargo PATH、合成元数据事务未提交、测试预期 failed 而原协议返回 outcome_uncertain 均已修正。真实评价持有源锁时并行审计被 WAREHOUSE_WRITER_BUSY 拒绝，待其结束后审计成功；旧 Registry 最初按新工作树查找失败，随后指向原拥有工作树只读核验。没有降低门禁、重建数据或抹除失败日志来获得通过。
