# PR #75 R2：Rust historical 盘后时点门禁

针对 [R2 审查](https://github.com/handFOOLed/Stratide/pull/75#issuecomment-6621187959)，基线 `7db63a069a8e06522e82e0a3bc6352cb6bcad925`。同一 Draft PR、单人、`stop-that-shit change hash=allow agents=0`。本页是开发者反证，不是独立验收。

## 修复

Python assemble 已要求上海时间 16:00 或以后，但直接 Rust bridge 的 historical 校验原先没有同等门禁。现在将 as_of 转成 `Asia/Shanghai`，先要求 `hour >= 16`，再从同一时区对象取得决策日期，复用原观测日期/末日/context_cutoff 一致性校验；拒绝代码沿用 `HISTORY_CLOSE_NOT_AVAILABLE`。

生产改动仅在 risk_history.rs：导入 Timelike、转换上海时间、检查小时、从同一对象取日期。Risk/Ledger、付费/外发授权、模型/来源约束不变。

## 先红后绿及时间边界

用 2022-03-31 同一日收盘前缀，仅改变 as_of 并更新 payload.as_of、Frozen/payload 的全部自描述 SHA；每个变异都直接调用 Rust project/begin，绕开 Python 冻结入口：

| 变异 as_of | 上海时间 | 结果 |
| --- | --- | --- |
| 2022-03-31T00:00:00Z | 当日 08:00 | 拒绝 |
| 2022-03-31T07:59:59Z | 当日 15:59:59 | 拒绝 |
| 2022-03-31T15:59:59+08:00 | 当日 15:59:59 | 拒绝 |

原 HEAD 上实际复现 6 次放行；修复后全部以 HISTORY_CLOSE_NOT_AVAILABLE 拒绝。测试还验证三个等价的上海 16:00 瞬间：`2022-03-31T08:00:00Z`、`2022-03-31T16:00:00+08:00`、`2022-03-30T23:00:00-09:00`，均完成 fixture task/原 Registry/archive/verify。即使输入字符串的日历日期不同，也以转换后的上海日期为准。将同一收盘前缀改到下一上海日期的两个入口继续拒绝。

新增方法包含在 `scripts/test-timesfm-history.py`。负向 begin 只针对独立 checkout 的 fake Agent，不污染 Owner 任务。

## 来源语义

沿用已读取的 tushare 1.1.12、tushare-data 1.1.16 Skills，并重新核对官方 [daily](https://tushare.pro/wctapi/documents/27.md)：未复权日线常规 15–16 点入库，停牌不提供数据。上海 16:00 是本模块使用当日收盘的保守输入契约，不是历史行首次发布时间或 PIT 认证。实际下载时刻、PARTIAL、历史 PIT NOT_VERIFIED 标签保留。没有请求新行情或读取 Token。

## 最终验证

- [checks.json](checks.json)：历史套件 **13/13**；负责的 research crate **71/71**；旧 synthetic CPU **11 pass + 1 Windows 专项 skip**。成功命令 exit 0，红测 exit 1 为预期。旧 R1 的 57 个元数据、10 个来源和 4 个小数反例继续包含在历史套件中。
- [真实复核](real-run-summary.json)：原已授权三证券 × 84 会话，2022-03-31 上海 16:00 → 真实 TimesFM CPU → 原 **task 9 completed** → Registry/report/verify，重复 once 同一任务。另对这个实际冻结输入重算 SHA 后，在隔离 fake Agent 做同样 6 个早盘反例，均拒绝。
- 原 8 个任务逐行哈希、原两笔 calls、全部 meta 与 settings 哈希未变。本轮只增加新本地任务；新云/行情调用、云计费、真实 Key/Token 正文读取均为 0。真实输入 Fusion 仍拒绝，旧 PR19 已记录 task 4 只读 verify=true。
- [tested-source.json](tested-source.json)绑定本轮源码，最终 HEAD 见 PR 正文。原 R1 全仓/recorded Fusion 和未变的隔离、仓库证据保留，不把它们写成本轮重跑。
- 未重跑全库/raw、付费 API、物理 N100。PIT、样本外优势、Paper/Live 资格未提升，等待新固定 HEAD 复审；不 Ready/merge。
