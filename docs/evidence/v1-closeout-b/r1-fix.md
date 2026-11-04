# PR #80 R1：Paper 意图原子提交与无行情终结

2026-11-04；修复基线 `8112927a9fd0b368abd9065f3cb9c019dd976c05`；对应 [R1 P1 审查](https://github.com/handFOOLed/Stratide/pull/80#issuecomment-6630253115)。本轮单 Agent 开发自测，继续同一 Draft；没有独立验收、Ready 或合并。

## 修复结果

- 原 CLI 的 `:observe → :submit → :freeze` 三次提交替换为一个 `SubmitPaperIntentV1` 事件。先检查目标日期/提案时间窗口与输入，再在同一原账本事务中沿原 Observe、Risk/Submit、Freeze 执行；校验失败和 commit 前崩溃不遗留活跃订单或预留。风控拒绝按业务事实持久保存终态订单及新观察到的损失锁，既不冻结、也不保留预留。
- 新冻结意图记录目标日上海 **17:15** 截止。截止后拒绝后来价格确认；`paper-eod-expire <原账本> <唯一事件ID>` 无行情/价格/挑单参数，整批写 `NO_FILL / DATA_UNAVAILABLE`，清 pending 并释放预留。它表示到窗口结束未取得合格确认，不把缺行推断成已知停牌，不发明成交/估值。
- 旧版成功 Submit、未成功 Freeze 的订单过原决策日后可用同一 expire 入口记 `UNSEALED_LEGACY_INTENT`。旧已完成命令的序列化不变，新 deadline/无成交字段在旧状态中省略，不重写旧日志或重建账户。旧部分提交的原 ID 不自动重放；恢复后用新事件/提案 ID 显式发起新决策。
- 无成交终结不改变现金、持仓、marks、估值时点和风险锁；终结时间独立阻止之后的回填命令。只读 API 保留无成交数据缺口/技术收据和 `OWNER_DECLARED_NOT_PROVIDER_VERIFIED`。源恢复和风险检查通过后才能继续新决策。

## 本地定向绿测

```powershell
$env:TEMP=(Resolve-Path state/issue77/test-temp).Path
$env:TMP=$env:TEMP
pwsh -NoProfile -File scripts/with-msvc.ps1 test -p stratide-ledger -p stratide-risk -p stratide-cli -p stratided --locked --offline -- --test-threads=1
pwsh -NoProfile -File scripts/with-msvc.ps1 fmt --all -- --check
pwsh -NoProfile -File scripts/with-msvc.ps1 clippy -p stratide-ledger -p stratide-risk -p stratide-cli -p stratided --all-targets --locked --offline
```

相关包 **114 passed / 0 failed**，包括原账本、风险、历史/公司行为、CLI、当前/历史账户分离及本机 API 回归；fmt、check 和普通 Clippy 完成。Clippy 仍报告此前披露的 Agent 基线告警，本轮没有新增 Clippy 告警。Windows 增量缓存仍有 hard-link 失败后正常复制的构建提示。

只新增三组核心生命周期回归，以及一项 CLI 参数/输入与幂等回归（注入测试时钟，没有新增生产时钟参数）：

| 场景 | 核验事实 |
| --- | --- |
| 错误目标日期/执行期限及事件冲突 | 原状态/账本头/事件数不变；有效提交只有一个新事件，一份订单/预留；重复输入不重提、改内容不复用 ID |
| 意图及无成交终结在 commit 前/后杀进程 | 四个真实子进程 exit 86；恢复后分别为全无/全有；重试不重复预留或终结，现金/股数/成交保持一致 |
| 无 bar、迟到价格与旧 orphan 恢复 | 截止前不能 expire、截止后不能成交、终结后不能重用旧 bar/回填时间；无价格也能释放预留；后续新意图实际通过原撮合；新观察损失仍持久锁定；旧订单恢复不清风险锁 |
| CLI 调用与重启 | 同一参数/JSON 解析与账本路径在测试时钟下错误日期不写；一次意图只新增一个事件；跨日重试返回原结果；expire 同 ID 重试只有一张无成交收据 |

所有新增输入均为 `synthetic_test`。本轮没有执行真实市场采集、TimesFM/云推理、付费 API、预算修改、旧账户写入或 UI 改动；不重跑无关浏览器/部署矩阵。首次测试的一个测试 helper 参数编译错误已更正，未削弱断言。

## 语义与范围

按 `tushare`、`tushare-data` Skills 核对 [daily 官方说明](https://tushare.pro/wctapi/documents/27.md)：日线通常盘后入库，停牌没有当日数据；缺行也可能是源故障，不能据此补价格或伪造停牌事实。[trade_cal](https://tushare.pro/wctapi/documents/26.md) 的开市日必须来自原可信来源，核心的日期/到期窗口校验不等于独立日历资格。17:15 是预先冻结的 Paper 接收规则，不是供应商按时供数证明。

产品仍是 **Owner CLI JSON + 单证券 next-open 假设**，不是研究候选自动转多证券订单。来源取得时间和公司行为核验是 Owner 声明，SHA 是本机输入完整性证据；PIT/真实开盘实收仍 NOT_VERIFIED，交易资格仍 BLOCKED。#10/#17、真实外发/共享预算、Paper-only 和 N100 暂缓边界保持。操作及恢复步骤见 [V1_COMPLETION](../../V1_COMPLETION.md#eod-paper-假设成交)。
