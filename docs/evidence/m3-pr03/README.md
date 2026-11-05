# Issue #84 开发验证

本页保留初次提交 `485b512` 的开发证据。当前 R1 修复与真实 EOD 假设路径、跨日估值恢复以 [R1.md](R1.md) 为准。

基线 `1677bed37db5162b8f87bd9908c57220636c90f5`，分支 `codex/issue84-multisecurity-paper`。仅开发者自测；`agents=0`，没有独立验收或合并。本期不读取生产凭据、不采集新真实行情、不调用真实/付费模型、不变更 Owner 本机资金与自动化设置。

| 验证 | 实际结果 |
| --- | --- |
| Rust Ledger / CLI / Dashboard 后端 | `scripts/with-msvc.ps1 test --locked -p stratide-ledger -p stratide-cli -p stratided`：87 项通过，含 6 项新组合测试（其中 1 项是子进程故障入口）。[日志](rust-tests.txt) |
| 新 Python runner / 来源边界 | `python -B scripts/test-paper-portfolio.py`：4 项通过。[日志](python-portfolio-tests.txt) |
| 原市场采集/覆盖/恢复 | `python -B scripts/test-market-eod.py`：23 项通过。[日志](python-market-tests.txt) |
| UI | `npm run typecheck`、`npm run build` 通过；产物 app.js 400.2 KiB、app.css 77.6 KiB。`npm test` 4 项通过。 |
| 浏览器 | `npx playwright test -c tests/portfolio.config.js`：1 项通过；1280px/375px 无卡片横向溢出、只读无写请求，原候选/订单/NO_FILL/不支持证券可见。[日志](ui-browser-tests.txt) |
| 格式 | `cargo fmt --all -- --check`、`git diff --check` 通过。 |

新 Rust 测试使用 24 个明确合成证券、跨多个交易日及休市间隔：共享资金不足拒单、4 个不支持/状态不明证券、单 writer 排斥、部分成交和 IOC 释放、买入当日禁卖/后续卖出、现金/股份/预留/费用逐分守恒、未知全账户估值阻止全部新增成交。下一日返回乱序和改变高低收/日成交量不改变假设开盘成交选择。未来研究、83 会话、日历缺日、源阻断、暂停/到期、重复事件/换 ID 重入均不能绕过准入。Freeze/Confirm 分别在预留后、提交前、提交后退出真实子进程，6 次故障后恢复至零次或恰好一次原事件，原账本守恒校验通过。

Python 验证未来日历只用于确定实际下一会话、不拉未来行情；原 task/Registry 来源与 84 会话筛选需一致；模型文字/模型权重不进入订单输入；真实确认不会凭日线或复权因子宣称公司行为核验；研究故障后原采集和 Paper 确认/新意图检查顺序继续。

环境限制与修复：首次 shell 未加载 linker，使用仓库已有 `with-msvc.ps1` 后完成构建。一次旧报表进程故障测试因沙箱临时目录权限失败，改用 worktree 内显式 TEMP/TMP 后全部 87 项通过，未修改旧断言。浏览器在受限环境启动失败，已通过自动批准的本机 Edge 无头执行完成。以上不是产品逻辑豁免。

`scripts/test-market-research.py` 在本 worktree 中按自身 `Disposable standalone checkout required` 规则拒绝启动，未执行其原全套云/CPU fixture；没有为此打开或重建 Owner Agent DB。原研究、¥5/日/¥100/月预算与外发许可代码未改动。真实行情/真实 Provider E2E 和独立验收均 **NOT_RUN**；本期无需为取得绿测购买接口/授权外发。

真实源当前缺少完整公司行为及精确规则，因此自动确认会产生可追溯 NO_FILL；有成交的工程测试全部是合成规则/价格，不能宣称真实收益。`OPENING_OBSERVED / HISTORICAL_PIT / REAL_TRADABILITY = NOT_VERIFIED`。完整契约、运行和范围见 [M3_PR03](../../M3_PR03.md)。
