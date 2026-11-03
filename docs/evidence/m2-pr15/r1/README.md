# PR64 R1：封存后审计与有界去重修复

依据 [ChatGPT 固定 HEAD 审查](https://github.com/handFOOLed/Stratide/pull/64#issuecomment-6594204686)，修复基线 `6ed034edf9d776efdbe96a3aab89865dac8bd353`。P1 是封存后失败文件不在原审计集合内却被 verify 放过；P2 是无敞口收缩时 seed=3 的第二轮四份提案全部重复。

本次仅修改本地控制器、确定性提案器、定向测试和相关说明。没有改 PR62 核算/运行器、Rust Agent/预算/财务、原 V1/V2、旧历史结果或交易权限。沿用 `change hash=allow agents=0`，保持同一个 Draft PR。

## 修复

- `verify` 将 `attempts/` 现存**完整文件集合**与封存收据严格对照，再逐文件核对哈希。未知、多余、缺失、篡改的尝试/失败文件不能返回 `verified=true`，旧版档案也适用。
- 封存后不再向 `attempts/` 写文件。新 archive 声明 `post-seal-audit-v1`，同时要求独立的 `post-seal.json`。日志绑定原 output/audit SHA，包含记录序号、前项 SHA、内容 SHA 和整份日志 SHA，在既有 writer 锁内只追加并原子替换。失败与状态恢复分别记录 `STAGE_FAILED` / `ARCHIVE_STATUS_RECOVERY`；日志缺失、旧项删改、链损坏均拒绝。原 `archive.json` 不覆写，恢复不重新打开源库或运行已完成研究。
- 提案器实际消费 `seen`。首选 AST 重复时，在固定 10/15/20/30 窗口中确定性回退；每类最多 4 次、整轮最多 16 次语法检查。低波动类也有有界窗口回退；不读取任何评价段收益、不执行回测来寻找回退。seed=3 / `reduce_exposure=false` 现在仍产生 4 个合法、可复现且未见过的提案。

## 实际验证

| 命令 | 结果 |
| --- | --- |
| `python -I -B scripts/test-autonomous-research.py Suite.test_post_seal_failure_audit_tamper_delete_extra_and_recovery Suite.test_seed3_without_contraction_has_bounded_novel_second_round`（修复前） | exit 1；2 项测试出现 4 个预期失败断言，见 [红色证据](review-red.txt) |
| 相同两项反例（修复后） | 2/2，exit 0，见 [绿色证据](review-green.txt) |
| `python -I -B scripts/test-autonomous-research.py` | **14/14，exit 0**，约 9.9 秒，见 [完整定向回归](tests-autonomous.txt) |
| `python -I -B state/issue64-r1-evidence.py`（ignored 聚合导出 helper） | exit 0；只读验证旧研究档案，禁止 Dataset 打开源库、凭据及 HTTP，见 [基线复用](baseline-verification.json) |

核心反例注入 `fault("archived")` 后，分别篡改/删除真实尾部失败审计、加入未知 attempt、删除已封存 attempt，确认 verify 拒绝；恢复时 mock 原库打开为失败，验证原 archive 字节不变、已完成研究不重算，并验证恢复后删除旧尾部记录仍被拒绝。原有封存前失败审计篡改反例也继续通过。

## 复用的真实基线

原真实两轮/8 AST、每轮 1212 会话/25,569,182 normalized rows 的证据继续引用初次提交 `6ed034e`，不作为本修复 HEAD 新跑的研究。两轮 `archive.json` 未改变，原 plan/output SHA 未改变；新 verifier 对这两轮的**现有研究日账与产物**只读核验通过，`source_store_open_calls=0`。新提案器对原 seed63 及原开发反馈产生的 AST 与原 8 份 AST 相同。

**真实研究重跑 0、下载 0、原库打开 0、Token 读取 0、新增付费 0。** 没有重扫旧 raw、重算 V1/V2 全库 SHA 或全状态 mtime；没有修改或重签旧 archive。旧源码的 `frozen_code_matches_current=true` 是初次运行时的历史事实，本修复不把它改写为当前 HEAD 的运行证明。

PR62 原 12 项回归与原两轮真实核算基线沿用：本次未修改 Portfolio/费用/时点实现。未运行无关 Rust 全套、Linux/macOS 或真实 Provider；开发者定向测试不是独立验收。保持 `EXPLORATORY_EX_POST / REUSED_EXPOSED_PERIOD / NOT_VERIFIED / ELIGIBILITY_DENIED / Paper=false / Live=false`，请求新的固定 HEAD 复审，不 Ready/合并。
