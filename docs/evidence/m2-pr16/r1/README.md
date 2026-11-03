# PR #66 R1：recorded 来源状态修复

依据 [ChatGPT 固定 HEAD 审查](https://github.com/handFOOLed/Stratide/pull/66#issuecomment-6596011225)，修复审查基线 `eddd6a213cb223f6049333bfca945fac3bf50f2d` 的唯一 P1。沿用原分支 / Draft PR，`change hash=allow agents=0`。以下为开发者定向自测，待固定修复 HEAD 复审。

## 修复及反证

`Store::status` 的初始分类和 `Agent::status` 的成功历史覆盖只排除了 fake / PR56 recorded，遗漏 structured recorded。因此本机录制任务成功后，会把模型误标为 `REAL_PROVIDER_CALL_OBSERVED`。

生产修改仅两处状态条件：同时检查原 `risk_cloud::recorded` 和 `structured::recorded`。structured recorded 从初始状态到任务成功结算、关闭并重新打开**同一原 Owner AgentDir**后，始终显示 `RECORDED_ADAPTER_NOT_CLOUD`；`availability=last_task_completed` 和原任务/费用仍正常显示。

新结算反例实际走原 `structured::execute → Agent::tick_task → Budget reserve → recorded dispatch → settlement`，确认任务 completed、原 calls=1、settled=6,144 micro-TST、reserved=0、receipt 存在，再检查 `Agent::status` 和 `Store::status`。不是只给分类函数传一个模型名。

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 修复前两个新反例 | **预期红：2 个失败断言 / exit 101**；初始错误为 `REAL_PROVIDER_NOT_VERIFIED`，实际 recorded 成功结算后错误为 `REAL_PROVIDER_CALL_OBSERVED` | [status-red.txt](status-red.txt) |
| 同样两个反例修复后 | **2/2 / exit 0**；两层 status 均为 `RECORDED_ADAPTER_NOT_CLOUD` | [status-green.txt](status-green.txt) |
| 原 status 回归 + 新旧类型分类回归 | **9/9 / exit 0**；fake 成功仍为 `FAKE_SYNTHETIC_ONLY`，PR56 两类 recorded 在有成功历史后仍为 recorded；非 recorded 初始/已有完成历史的状态投影保持原值 | [status-regression.txt](status-regression.txt) |
| structured 全部定向测试 | **11/11 / exit 0**，含 1 个子进程驱动入口；原授权/预算/取消/暂停/崩溃/未知/跨月/loopback/幂等反例和新增状态反例均通过 | [structured-regression.txt](structured-regression.txt) |

非 recorded 类型的回归使用隔离测试库中的**合成持久历史**检查原状态投影；没有发送外部请求，不是实际 Provider 验证。原 PR56 recorded 的历史也只使用合成测试记录。精确命令和退出码见 [commands.json](commands.json)。

## 原证据复用

原 [五年结果](../real-summary.json)、[合成闭环](../synthetic-summary.json)、[旧归档收据](../old-archive-receipts.json)、AST、评价器、价格/费用算术、scope/授权、Provider 网络和交易权限均沿用原基线。R1 不打开真实 V1/V2、不重跑五年研究、不重新采集、不复验旧 raw/全库、不迁移或重签旧 archive。

`../comparison.json` 的 `frozen_code_matches_current=true` 是 **原 eddd6a2 实际研究时点**的逐文件结果，不能视为本次状态修复 HEAD 的新五年运行证明。R1 只新增以上 Rust 合成验证；原 Python、预算和历史证据不冒充本轮重新执行。

真实 Provider/付费/外发/新行情请求/Tushare Token 读取均为 0；`authorized_cloud` 仍 BLOCKED，Paper/Live=false，独立验收 NOT_VERIFIED。固定 HEAD 审查及 Owner 明确授权前，保持 Draft、不 Ready、不合并。
