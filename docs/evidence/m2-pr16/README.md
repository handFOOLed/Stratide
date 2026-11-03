# M2-PR16 开发证据

Issue [#65](https://github.com/handFOOLed/Stratide/issues/65)，base `7f12f12b321cdd7c24c90458f4ae4859f59ec3bd`，独立分支 `codex/issue65-cloud-structured`。单人、`agents=0`，以下为开发自测，不是独立验收。CLI 和授权/数据契约见 [M2_PR16](../../M2_PR16.md)。唯一 Draft，Owner 授权前不 Ready/merge。

**审查修复 R1：** 修复原 Agent status 将 structured recorded 成功任务误标为真实 Provider 调用的 P1。两层状态保持 `RECORDED_ADAPTER_NOT_CLOUD`，新增同一原 AgentDir 实际结算后的红绿反例；本轮 structured 11/11、status 9/9 均 exit 0。详见 [R1 证据](r1/README.md)。以下五年研究与原测试继续保留其 `eddd6a2` 冻结基线，没有在 R1 重跑真实数据。

## 运行结果

| 验证 | 实际结果 | 收据 |
| --- | --- | --- |
| 原 Agent → 本机 HTTP loopback → 4 AST → PR15/PR62 | 90 synthetic 会话 / 8 个 fixture 代码 / 4 个新 AST / 三成本 × 4 候选和 3 基准；1 次 loopback、1 个原任务/调用，结算 12,288 micro-TST | [synthetic-summary.json](synthetic-summary.json) |
| 新录制 AST → 一轮真实五年本地研究 | 2021-11-01—2026-10-30；1212 会话，实测 5774 代码、5387 曾合格；4 AST / 0 拒绝。6,347,781 daily + 19,221,401 sidecar = 25,569,182 行由原 streaming evaluator 读取一次 | [real-summary.json](real-summary.json) |
| 真实运行资源 | Windows / Python 3.12.10；293.462 秒，CPU 281.766 秒，峰值 440.883 MiB；1 worker / 1 thread。未复制原库 | [real-summary.json](real-summary.json) |
| 同一个原 TST Owner/预算 | 上述两个实验共享一个显式 `stratided --agent-init-fake` Owner；总计 2 tasks/calls，结算 **24,576 micro-TST**，本次成功演示未知预留为 0。故障测试另有 81,920 micro-TST 未知预留保留反证 | [run-totals.json](run-totals.json) / [rust-structured.txt](rust-structured.txt) |
| 重复与只读 | 两个实验均实际执行 init/once/status/history/report/verify/重复 once，全部 exit 0；重复 once 所有既有实验文件逐字节不变，不再发送/评测 | [commands.json](commands.json) |
| 原数据/原 archive | 原已知 DB/lock/WAL/SHM/journal 大小和 mtime 收据前后相同；旧 PR15 两份 archive SHA 未变。只读小型旧收据和 AST，不重解析 raw 或跑旧全库 verify/fingerprint | [old-archive-receipts.json](old-archive-receipts.json) / [comparison.json](comparison.json) |

真实 Provider 调用、付费、数据外发、新行情请求、Tushare Token 读取均 **0**。loopback 只访问 `127.0.0.1`，测试传输开关仅在 libtest 编译；生产 CLI 不接受该开关。录制产物来自明确的 synthetic wire fixture，**不声称实际云模型生成能力已验证**。

全部 AST、任务和结果在评价前冻结。4 个新 AST 与旧 seed63 两轮的 **8 个 AST 没有交集**；现金、同 50 持仓上限等权、简单正收益的 base 结果与旧 PR15 第一轮逐值一致。没有重新跑旧两轮来制造这项比较。[比较收据](comparison.json)

新真实研究全期 **base 假设收益**：

| 冻结规则 / 基准 | 结果 |
| --- | ---: |
| 候选 1：3 日成交额 rank | -58.2493% |
| 候选 2：7 日收益逆向 rank + 流动性 | -62.5000% |
| 候选 3：收益/成交额 rank 混合 + AND | -87.3090% |
| 候选 4：9 日低波动 + OR | -5.7730% |
| 现金 | 0% |
| 同上限确定性等权 | +1.6064% |
| 简单正收益 | -55.0657% |

这四个录制假设没有建立优势。全部候选和失败均保留，不选赢家、放宽语法或加轮次找盈利；三成本/分窗/Walk-forward 完整指标在 [真实聚合](real-summary.json)，拒绝/stale/负收益在 [失败聚合](failure-summary.json)。完整逐日/逐股票归因、信号、源 locator 和行情保持 ignored 本机文件。

## 定向测试与红绿反证

| 命令 / 范围 | 结果 | 输出 |
| --- | --- | --- |
| 移除新 scope 拒绝这一处边界，再执行 `old_grants_cannot_authorize_new_scope` | **预期红：exit 101 / 1 个失败断言**；旧 paper Grant 错误接受新 scope。finally 恢复源文件 | [scope-upgrade-red.txt](scope-upgrade-red.txt) / [精确命令和变异](scope-upgrade-red.json) |
| `cargo test -p stratide-research --lib structured_tests -- --test-threads=1`（已有 MSVC） | **绿：9/9，exit 0**，含 1 个子进程驱动入口 | [rust-structured.txt](rust-structured.txt) |
| 原 Rust Agent/预算/旧 scope 定向回归 | **38/38，exit 0**：eod_scope 3、multimodal_scope 1、risk_portfolio 8、safety 11、shared_budget 6（含子进程入口）、status_regression 8、task_routing 1 | [rust-agent-regression.txt](rust-agent-regression.txt) / [命令](rust-agent-regression.json) |
| `python -I -B scripts/test-cloud-structured.py` | **9/9，exit 0** | [python-cloud.txt](python-cloud.txt) |
| `python -I -B scripts/test-autonomous-research.py` | **14/14，exit 0** | [python-pr15.txt](python-pr15.txt) |
| `python -I -B scripts/test-multistock-research.py` | **12/12，exit 0** | [python-pr62.txt](python-pr62.txt) |

新 Rust/Python 反证实际覆盖：旧 Grant/旧模型无法升级；原队头任务不被误领取；原预算不足或撤销时无 calls/dispatch；预留后取消/撤销无发送并记 no_charge；暂停后显式恢复只结算一次；loopback 成功/超时；dispatch 后子进程强制退出保留未知；跨月仍计原预留；用量越界/重复 wire key 不清锁；结果与录制不可替换；原结果被篡改后 verify 拒绝；未来特征/错误单位/未知字段/权限/source/injection/非有限/重复 JSON/代码拒绝；部分通过、全拒绝、拒答、非法内层 JSON 保留成本和审计；第二轮只有开发反馈且无确定性 fallback。PR15 原冻结/post-seal/日账守恒/成本/时点反证仍通过。

测试细目及 exit 汇总：[checks.json](checks.json) / [python-tests.json](python-tests.json)。仓库无 `.github` workflow，本次没有 CI 或付费 CI；Windows 增量编译的 hard-link 警告回退复制，不影响测试。Linux/macOS、实际外部 Provider/价格/保留与数据许可、物理断电、历史 PIT/开盘可成交性、独立 Alpha 和前向资格未验证。

## 固定 SHA 与复核入口

| 对象 | SHA-256 |
| --- | --- |
| 录制模型配置 | `cf9af136d42b43495295ee2ee7dedfb2d2604cbfbc5304bad92eebfc1bce3550` |
| prompt | `36da01924d7ddaffdd6f63ccebf8a02042e42f87fc05735668e163740ea65522` |
| parser | `e179cbd92351899f7d1bc17b172387a08c02fd17677fd65edfeb62d443e62ac8` |
| 真实实验 plan | `3dbc3211978f32b866614e5e97cc2eef48257993e95fef981367cb036006f33e` |
| 真实实验数据源 | `f8eafe09ebce5538775faa7539ceb466f2284205f32f689f95c0d95570f58a96` |
| 真实实验任务请求文件 | `5bb9f81dc54848a8b27d08594b734a7674143f311faf4db520479a62c6368f84` |
| 真实实验 wire / 模型 content | `c0df82ebc65de4eaefe50c05864727c7c7b2d4f876f9bca4eb0758adcfb39959` / `351edd8358b555f857a6c5f33258677a9a49efdc49970f825781c6d437ab75a7` |
| 原真实研究任务 result 字节 | `69274e074c25dde279b5cb9bc462a4fb51e0f1993f85d7cdd7d027b0e9e98f8b` |
| 真实研究 output | `f8424942de56d2581e136f21faf8ad06a7b0e9163a5b240b3c42fb8ff9b09ba9` |
| 合成 loopback output | `4f1b4dede9411ba18e4bafec6c9c01691bc0735b03261ed7aae0d0731d403d6f` |

四个 AST、每份代码、原 task/call ID、模型/价格/Grant/TST 上限和三费用指标都在两份 summary；[comparison.json](comparison.json) 的 `frozen_code_matches_current=true` 描述原 `eddd6a2` 运行时点，不作为状态修复 HEAD 的新五年证据。Git 不包含真实原始 payload、行情、证券序列、账户本金、密钥和源库绝对路径。

```powershell
# 完整本机演示；真实历史仅显式提供已有 locator 时跑一轮：
python -I -B scripts/run-cloud-structured-evidence.py --tag <new-tag> --real-locators '<EXISTING_PR15_LOCAL_LOCATORS>'
# 本次已有档案，只读复核；不会打开历史行情库或再次调用 Agent：
python -I -B scripts/autonomous-research.py verify --out state/autonomous-research/issue65-20261103-v1-real
python -I -B scripts/autonomous-research.py report --out state/autonomous-research/issue65-20261103-v1-real
```

固定 `historical_backfill_ex_post / EXPLORATORY / NOT_VERIFIED / forward BLOCKED / ELIGIBILITY_DENIED / Paper=false / Live=false`。开发测试和历史结果均不授予交易权限。
