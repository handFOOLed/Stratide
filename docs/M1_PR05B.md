# M1-PR05B：真实历史 EOD 驱动的探索性回测

状态：**Sol 开发与自测完成，Draft；待 Terra 同 SHA 独立验收、小猫审查。不得合并。**
任务：[Issue #11](https://github.com/handFOOLed/Stratide/issues/11) 及其中最新 Codex 启动提示词。固定 base 为 `d1b79b37592b69e35a7a1bc4b64fbc3ca3b5cae5`（已含 PR #9），最终 HEAD 由 Draft PR 的提交引用确定。Issue #10 的真实前向观察独立继续，不以本回测结果替代。

## 共享执行契约的必要改动与隔离

P0：未来函数、资金/持仓/费用守恒、风险权限与证据误标；P1：数据缺失、重启、报告可复现。

旧 `Command::Match` 要求独立 opening 并以完整日线穿越判断成交，不能诚实表示本 Issue 允许的历史 next-open。新增 **`HistoricalNextOpenV1`**，只接受 `historical_replay`，在独立 reducer 内构造明确标为假设的模型估值/规则时间；**不构造 `OpeningEvidence`**。历史 Fill 省略 `opening_evidence`，携带 `historical_execution=historical_ex_post_execution_assumption/next-open-adverse-tick-100-v1`。`risk_checked_at` 是模型开盘审查时刻，`simulated_at` 为模型盘后入账时刻，均不是过去本机实收或真实成交时间。

两种撮合复用同一 `fill_order` 财务路径：原费用上界/预留、最新全账户/策略 Risk Kernel 再审查、整数份额、T+1、实付费用、现金/持仓与一次性记账。Risk Kernel 未修改。新命令的成交价格为历史 open 加/减不利一分，原决策限价、现金、敞口与风险锁继续约束执行；不看次日 high/low/close/全日成交量来选择开盘成交。每时段共享预先固定 100 股模型容量，余量在该时段末按 next-session IOC 释放，保留原因。此容量不是市场可成交量证明。原日线模型仍要求到期严格晚于完整时段收盘；历史模型只在开盘尚未到期时尝试，不能拿全天极值证明盘中成交。

v3 schema/摘要域不变：新命令有独立名字；原 Fill 的 Some opening 序列化仍是原对象，新增可选字段为 None 时省略。旧样例回放的 ledger head 与已提交 PR03 结果完全相同。旧程序不能识别新命令，不能用它打开本分支新历史账本。原 forward 模块、journal schema 1041、所有旧账本/raw/报告不改，不做迁移、清空或重建。

## 来源冻结与可用性

实际来源是当前连接的 **Tushare MCP** 的 `daily / trade_cal / stk_limit / suspend_d`。保存的是工具返回的 **原始文本 payload 字节**，不是本地 HTTPS wire response；本轮没有取得本机 HTTP Token，也没有访问其他项目的凭据或数据。另提供 `fetch` 子命令供本人已配置环境变量时进行本地 HTTPS 采集，但本轮未实测该子命令。Owner 已有个人非商业本地研究授权按 Issue 复用；不声称供应商正式许可已独立认证，不把原始行情上传 GitHub。

- 原查询：`ts_code=600000.SH`，`exchange=SSE`，`start_date=20260706`、`end_date=20261028`；daily 77 行、calendar 115 行、涨跌停 77 行、停复牌结果空。精确字段、实际提取 UTC 时间、响应类型随本机 `extraction.json` 及冻结输入保留。
- 检测到 2026-07-16 `pre_close` 与前一 close 的除权断点，本模型不支持公司行为核算。明确选择其后的 **20260717–20261028：68 根日线、104 个完整自然日日历记录**，不是按策略收益筛选窗口。
- Python Decimal 精确转换：元 ×100→整数分，`vol` 手 ×100→整数股。非整数、负数、溢出、NaN、无效 OHLC、重复日期、缺交易日/行情、价格带冲突、除权断点明确阻断。空行不当停牌、不补零。日历用 SSE 实际开闭市及 `pretrade_date`，不猜周一至周五。
- 输入 schema v2 仅支持普通沪市 `600000.SH`、本轮规则/费用适用期。涨跌停带来自 `stk_limit`；停复牌事件所在日保守不成交。标准单位为 100 股、1 分价格跳动、T+1。数据完整性与市场规则核对不证明历史时点发布、排队或本账户可成交。
- 每根历史 bar 的信号可用时间统一假设为当日 **Asia/Shanghai 18:00**（UTC+08:00，epoch 毫秒）。标签固定 `assumed_historical_eod_availability_not_pit_verified`；历史逐 bar 实际 `received_at` 与供应商历史发布时间均为 **null**。真实提取时间另记，不将其反写为过去实收。修订历史、分红/复权、短暂停牌/竞价排队和投资者订单执行均不由日线证明。

官方字段说明：[Tushare daily](https://tushare.pro/document/2?doc_id=27)、[trade_cal](https://tushare.pro/document/2?doc_id=26)。daily 的 `pre_close` 是除权昨收，不能直接当连续未复权 close；`vol` 是手。规则/费用参考与有效期研究沿用 [PR04B 官方来源记录](M1_PR04B_OPENING_EVIDENCE.md)。本轮没有购买权限或调用券商。

| 冻结内容 | SHA-256 |
| --- | --- |
| 原 daily MCP payload | `d479248a0a712e043e7ea533a6e6bc7ab48418798037ad60397bf773400717be` |
| 原 calendar MCP payload | `6d1ac48d6340ca96c9f02e921dc222e5eb4dadacb72162c3747c02365b2148d2` |
| 原 limits MCP payload | `fadbd383650c753e00448054066a4447000aa1e53d497374de5d5e1c0db50598` |
| 原 suspensions MCP payload | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| 最终 `dataset.json` | `9460155e70947ee3c536cc02ec81d555401f1a2b824198ab660a0e2283c33ff7` |

## 固定策略、费用与实际结果

策略 `sma5-20-cross-fixed100-v1`：20 根已可用 close 预热；用整数和比较 `sum(last5)*4 > sum(last20)`，布尔关系由 false→true 买 100 股，true→false 卖 100 股。第 20 根只初始化关系，不补做早期交易。限价为决策日 close ± 向上取整 2%，夹在当日已知价格带内部；有效期为决策后 14 天。决策只读截至该日的 close；即使未来会停牌、开盘跳空或无后续行情，信号也不提前改变。无参数优化或样本外有效性主张。买单未成交后出现卖信号，仍由原 Risk 路径如实拒绝无库存卖单。

费用模型 `paper-cost-assumption-20260706-v1`，适用 20260706–20261231：含规费佣金 300ppm、每笔最低 500 分；过户费 10ppm 双向；卖出印花税 500ppm。各项独立向上取整到分、每次模拟成交收一次最低费；不另加已含佣金中的经手/证管费。这是显式模拟假设，不是 Owner 券商合同费率。成交价不利一分是固定滑点假设，限价不支持则不成交；没有从 OHLC 反推触价成交。

Owner 本会话明确授权：模拟初始本金 **¥100,000**、单笔上限 **¥5,000**、账户/策略敞口各 **¥20,000**、日亏损熔断 **¥1,000**、回撤熔断 **¥5,000**。仅为本轮研究模拟配置，不是实际入金或实盘授权。

| 最终真实历史输入运行结果 | 整数分 / 股 |
| --- | ---: |
| 初始 / 期末 NAV | 10,000,000 / 9,996,651 分 |
| 期末现金 / 持仓 / 未完成订单 | 9,898,151 分 / 100 股 / 0 |
| 提案 / 模拟成交 / 风控拒单 | 3 / 3 / 0 |
| 佣金 / 过户 / 印花税 / 合计 | 1,500 / 3 / 46 / 1,549 分 |
| 已实现 / 未实现 / 总 P&L | -4,248 / +899 / -3,349 分 |
| 累计回报 / 日观察最大回撤（整数基点截断） | -3 / 6 bps |
| 现金持有基准 / 同首笔买入持有基准 NAV | 10,000,000 / 10,004,399 分 |

末期 NAV = 现金 + 末期持仓市值；总 P&L = 已实现 + 未实现；未实现仍不是可提款收益。现金基准从期初覆盖全窗；买入持有比较复用本策略首笔实际模型买入的股数、价格和买入费，不估离场费用、不称独立可执行 alpha 基准。缺估值仍输出 null；本冻结窗口完整且实际得出上述结果。

本机最终六报告在 `state/issue11-selftest-03/a/report/`，账本在相邻 `ledger/`：`report.json / events.json / daily.csv / orders.csv / fills.csv / positions.csv`，只留本机。最终账本尾摘要 `22c6de93ebb52d5f1242eda56a28242437273a319e7e0933a483d8dbd2ba60e6`。历史假设、source manifest、费用配置、策略/输入/配置哈希均入报告；历史 fills.csv 另带执行假设标签。

## Windows 复现

从本 worktree 根目录运行。已有原始 payload 位于忽略目录 `state/issue11-source-20261029-01/`，不是随仓市场数据样例。Terra 可在本机读取该冻结目录，用**新目录**复现；换机器需 Owner 在本机配置已有权限的环境变量再自行采集，重新取得的修订响应可能产生不同输入 SHA，不能冒充同一快照。

```powershell
# 可选：已有 STRATIDE_TUSHARE_TOKEN 进程环境变量时，本人本地 HTTPS 采集。
# 不将 Token 放入参数/终端命令/输出。此 fetch 路径本轮未实测。
python scripts/historical-data.py fetch --out state/my-historical-source --start 20260706 --end 20261028

# 本轮已冻结的真实 MCP payload → 新输入目录；不会覆写。
python scripts/historical-data.py prepare --source-dir state/issue11-source-20261029-01 --out state/my-historical-input --start 20260717 --end 20261028
$dataset = 'state/my-historical-input/dataset.json'
$sha = (Get-FileHash $dataset -Algorithm SHA256).Hash.ToLowerInvariant()
$limits = @('--initial-cash-fen','10000000','--max-order-fen','500000',
  '--account-cap-fen','2000000','--strategy-cap-fen','2000000',
  '--daily-loss-fen','100000','--drawdown-fen','500000')
./scripts/with-msvc.ps1 run --locked --offline -p stratide-cli -- paper-replay $dataset state/my-historical-run/ledger state/my-historical-run/report --sha256 $sha @limits
./target/debug/stratide-cli.exe paper-status state/my-historical-run/ledger
./target/debug/stratide-cli.exe paper-report $dataset state/my-historical-run/ledger state/my-historical-run/report --sha256 $sha
Import-Csv state/my-historical-run/report/daily.csv | Format-Table
Import-Csv state/my-historical-run/report/orders.csv | Format-Table
Import-Csv state/my-historical-run/report/fills.csv | Format-Table

# 相同命令/目录可断点续算；不能更换输入/配置或清空目录重跑。
# 独立的新账本、字节一致性、强杀恢复、资金复算与未来价格篡改探针：
python scripts/test-historical-replay.py --exe target/debug/stratide-cli.exe --input $dataset --source-dir state/issue11-source-20261029-01 --output state/my-historical-selftest -- @limits
```

首次文件创建/采集若中断或失败，保留原目录，选新目录重试采集；完整已提交 paper 事件则用原命令续算。禁止删锁/数据库绕过初始化。旧报表与前向日志一律只读。`prepare` 缺来源、日期、日历、价格带或公司行为核算条件时退出 2 / BLOCKED，不输出假成功数据；未配置 Token 的 `fetch` 同样阻断。

## 自测及边界

Windows x64、Rust 1.98.1、Python 3.12.10、既有 MSVC；无新依赖或 CI。`cargo fmt --all -- --check`、locked/offline workspace check、**110 项 Rust 测试**、严格 `clippy --workspace --all-targets -- -D warnings`、3 项 Python adapter 单测均通过。完整命令、日志与失败过程见 [脱敏证据](evidence/m1-pr05b/README.md)。

- 合成代码探针：篡改 T+1 的 OHLC 不改变 T 日提案；扩展未来会话不回填预热交易。次日 high/low/close/成交量变化不选择开盘成交；open 可改变模型价格。opening 伪装、假 PIT 标签、未知交收、停牌、限价不利跳空、共享容量、风险冻结、费用精度、T+1 和重复会话均覆盖。
- 真实冻结输入：两个新账本的六报告逐字节相同；跨进程重复运行无新增事件；实际强杀子进程后恢复到 **35 个已提交事件**，保留前缀、续算后的全部事件/报告与正常运行相同；逐笔独立复算分股/费用/现金/持仓守恒。另一个目录中的价格篡改输入明确为合成探针，不是市场观察。
- 旧 v3 合成样例回放的账本尾摘要与原提交 golden report 相同。forward 测试原样保留，通过不增加真实观察日数。

这是 **Sol 自测，不是 Terra 独立 PASS**。Linux/macOS、真实前向开盘实收、历史 PIT/修订全史、真实市场可成交性、公司行为账本、本机 HTTPS fetch、物理断电/磁盘满/跨主机恢复未验证。未接券商、实盘、GUI、LLM Agent，未合并；历史亏损/收益不提供实盘资格。
