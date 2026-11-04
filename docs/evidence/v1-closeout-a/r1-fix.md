# PR #78 R1 修复简报

修复起点：`152443eb62f4b447decd05ddc0b281da668bbcdf`。按 2026-11-04 更新后的 #19/#76 个人模式规则，同一 Draft PR、本地相关绿测，由 Owner 决定合并；无子代理。

P1：新增 `controlled-conclusions-v2` 封套，保留内部 TargetPortfolioProposal V1。结论命题、保守状态和来源引用精确匹配；自由文字仅保存在 `UNTRUSTED_HYPOTHESIS` 区域，不投射到通用研究摘要、证据或资格。新路径不依靠关键词证明自然语言语义。旧 Prompt/解码仅供原 pin 只读复核，标记未重新认定资格。

P2：冻结配置、原协议、20 个起点门槛和旧报告不改。每段一年、每月最多一个起点，容量上界 12，故新报告明确 `STRUCTURALLY_UNREACHABLE`，另列实际样本不足状态；旧 schema 1 只读返回容量诊断，不重签 seal。真实历史仍仅为描述性 ex-post / PIT NOT_VERIFIED，本轮未重新推理或复验真实库。

更新规则：审计矩阵中的 #10/#17 缺口标记 `EVIDENCE_CLAIM_ONLY`，不阻挡工程合并或 EOD Paper 集成；真实数据外发仍是独立授权禁令。研究产物自身不授予执行权。T+1 开盘价的事后 Paper 假设须标 `EX_POST_OPEN_ASSUMPTION`，不冒充开盘实收；本 PR 不实现新撮合路径。

本地验证在无 Owner 数据的 WSL2 Ubuntu 原生 ext4 独立副本执行：

| 命令/检查 | 结果 |
| --- | --- |
| `cargo fmt --all --check` | exit 0 |
| `cargo build --workspace --locked --offline` | exit 0 |
| `cargo test --workspace --locked --offline -- --test-threads=1` | exit 0 |
| `cargo clippy --workspace --all-targets --locked --offline` | exit 0；5 条既存警告，未使用 `-D warnings` |
| `python3 -B scripts/test-local-timesfm-fusion.py`，使用当前源码的 libtest 驱动 | 14 pass，exit 0 |
| `python3 -B scripts/test-risk-evaluation.py` | 13 pass，exit 0；包含独立复算、旧 seal 和更新后的声明范围 |
| `python3 -B scripts/test-timesfm-history.py` | 13 pass，exit 0；含 Registry 与真实数据外发拒绝 |
| `python3 -B scripts/test-timesfm-cpu.py` | 11 pass、1 Windows 专项 skip，exit 0 |
| 原 HEAD 实际生成的两条合成记录，用新 libtest 只读 verify | 2/2；旧 Prompt/结果 SHA 保留，key 不可用时仍通过，DB/calls/meta/settings/wire/model 字节及内容未变 |
| `git diff --check`；冻结配置/协议与修复起点比较 | exit 0，无配置/协议变更 |

反证：原 HEAD 的英文 PIT/99% 收益与中文每月 20% 确定收益改写均被记为 completed，新增断言 exit 1；完美行情、12 起点/年也仅笼统报 INSUFFICIENT_EVIDENCE，新增断言 exit 1。修复后受控字段中的两种改写均拒绝为 `FUSION_CONTROLLED_CONCLUSION_REQUIRED`，已发送失败保留最大预留、重复 once 不重发。测试另覆盖自由叙述隔离、PIT/收益/置信/来源/资格/预算/订单状态升级拒绝、工具调用及原 grant/预算回归。

测试中曾使用过期 libtest 驱动、以及用生产解码器复核 loopback 收据；分别按当前源码重建专用驱动、改用原收据对应的 libtest 复核后通过，未降低生产门禁。

本轮未调用真实 Provider、行情 API、真实 key/token，未改 Owner 预算/授权或财务状态，未下载权重。Linux Worker 隔离实现未改，未重跑其原物理资源测试；N100、Windows 专项、物理重启和独立人工验收不在本轮声称完成。
