# M2-PR12 开发自测与真实取数证据

范围为 Issue [#57](https://github.com/handFOOLed/Stratide/issues/57)，基于实际 fetch 的 main **`a27f466e643cb7dd05e3be72b83402a4599a301f`**，分支 `codex/issue57-historical-warehouse`，独立 worktree。唯一 Draft PR 的实际固定 HEAD 在 PR 正文；本目录的 [tested-source.json](tested-source.json) 绑定生产模块、CLI 和测试文件的 SHA256 / Git blob SHA。

这是开发者自测与实际下载记录，**不是独立验收、PIT 认证或交易授权**。完整契约与操作见 [M2_PR12](../../M2_PR12.md)。

## 真实预检、试采和回填

先核对本机凭据。进程、用户/系统环境和原 Windows Credential Manager 条目未配置，正常用户权限复核同样未取得，均 **0 网络请求**。随后只读复用本机已连接 Tushare MCP 配置的同一账号；3 次 MCP 窄查询成功，但转换文本不作为 HTTP 原响应。正式仓库使用固定 Tushare 原始 HTTPS 接口，所有 raw、请求审计、SQLite、目录快照和行情查询明细都留在 ignored `state/`。

实际 HTTPS 已确认 `stock_basic`、`trade_cal`、`daily` 可读。证券目录完成 SSE/SZSE/BSE × L/D/P/G/UN 组合查询，日历保存沪深各 1,825 个自然日。缺北交所独立日历和可信全历史证券身份名录，**全市场 coverage 始终 PARTIAL**；不能因为日期都已下载就宣布全市场历史完整。

五个不连续交易日先行试采，共 **25,845 行**：

| 日期 | 原返回行数 | HTTP body 字节 |
| --- | ---: | ---: |
| 2021-11-01 | 4,647 | 435,482 |
| 2022-11-01 | 4,978 | 465,242 |
| 2023-11-01 | 5,300 | 497,635 |
| 2024-11-01 | 5,349 | 512,277 |
| 2026-10-30 | 5,571 | 541,246 |

五次原响应 SHA 及真实失败响应见 [source-receipts.json](source-receipts.json)。完整请求和日版本索引保存在本机，公开其整体 SHA，不再分发行情原文。

授权区间的 **1,212 个交易日均已下载并发布**，合计 **6,347,781 行**：**1,201 日 COMPLETE，11 日共 12 条供应商 NULL 昨收使日期为 PARTIAL**，不补值、不宣称质量齐全。0 未尝试/未提交/当前查询失败日期。实际 1,235 次 HTTPS + 3 次 MCP = **1,238 次**，低于合计上限 1,358；本地约 4.54 GB。全市场证券身份和北交所日历的缺口独立存在，整体 coverage 仍 PARTIAL。

试采后有 **1,212** 个已知沪深开放日，余 **1,207** 日；实际落盘 23,052,968 bytes，保守追加空间估算 **8,347,479,712 bytes**，当时可用 **280,079,380,480 bytes**。按余量计算 native HTTPS 累计上限 **1,355 次**（含预检/失败），另有 3 次 MCP 窄探测，合计界限 **1,358 次**。预检 10 次/分钟，批量最多 30 次/分钟，单 worker；没有购买、提档或付费模型调用。

最终真实范围、日期/市场/记录数、失败与缺口、磁盘量、权限、首次/最后实际取得时间、命令与 UTC/UTC+8 时间以 [real-summary.json](real-summary.json) 为准。记录中的 `state` 描述按日发布状态，`coverage` 描述市场证据；两者不能混用。`failed_dates` 是当前未有发布版本的失败日期，历史失败尝试另列；成功收到 raw 但未提交的日期单列，不冒充 COMPLETE 或未尝试。

本次实际执行命令（精确起止时间、退出码和源 SHA 在 JSON 中）：

```powershell
python -I -B scripts/historical-warehouse.py preflight `
  --credential-source existing-tushare-mcp-config `
  --max-calls 32 --total-call-cap 1600 --rpm 10

python -I -B scripts/historical-warehouse.py backfill `
  --credential-source existing-tushare-mcp-config `
  --max-calls 1328 --total-call-cap 1355 --rpm 30

python -I -B scripts/historical-warehouse.py resume `
  --credential-source existing-tushare-mcp-config --retry-failed `
  --max-calls 1296 --total-call-cap 1355 --rpm 30
```

## 保留的失败及修复

- 首轮离线脚本暴露 SQLite 插入列数、拒绝状态和跨进程 429 冷却问题；[首轮 red](initial-red.txt) 保留，没有计为通过。
- 首次真实目录在区间外旧临时代码停止；第二次在北交所 `symbol != ts_code` 停止。原响应、时间和 SHA 没改。修复为“区间外退市/B 股保留 raw，不进入本期视图；北交所保留两种代码并标历史映射未验证”。首次旧 CLI 曾错误 exit 0，最终测试明确验证数据失败 exit 2。
- 首次批量新增 31 日后，在 2021-12-15 的一条供应商 `pre_close=null` 停止，没有提交该日。修复保留 NULL 和明确质量标记，日期 PARTIAL，不补价，随后在原总预算内显式续传。原失败尝试仍保留。
- [交易所日历 red](calendar-red.txt) 复现“另一市场开市不能授权本市场休市行”；最终按自身交易所日历校验，真实仓库 verify 也检查这一规则。缺 BSE 日历不伪造结论。
- 补充截断 HTTP body 的异常测试时，模块名被本地状态变量遮蔽；[异常处理 red](http-exception-red.txt) 保留，修正后超时和协议失败均持久为未知结果。此中间版本未进入正在运行的真实采集进程。
- 本 worktree 的未发布开发仓库做过两次局部 schema 修正：首次尚无 day version 时移除错误的全历史内容唯一约束，允许 A→B→A 的修订时间线；已有 171,119 行时将 `pre_close` 改为可空，逐行数量及 FK 守恒，未重写原 HTTP body、来源时间或旧行内容。最终从零建库 E2E 使用相同最终 DDL；这不是旧 Observer 或 Agent 的迁移。
- 实际 635 万行规模报告暴露 checkpoint 版本关联缺索引：查询计划逐次 `SCAN c`。仅给新仓库补 `checkpoints(version_id)` 索引，单证券关联查询约 23.5ms → 0.59ms，完整报告约两分钟 → 8.56s，数值不变；见 [实测计划/耗时](checkpoint-index-performance.json)。

## 离线 E2E 与真实只读复核

最终 [24 项测试输出](synthetic-final.txt)、[准确命令/exit/环境及源码](validation.json) 覆盖：

- 15 个交易日、至少两个交易所、存续/期间退市/期间上市三类证券的生产解析→事务→查询全流程。
- 无 Token、接口拒绝、0/累计上限、空间不足、超时未知、429 跨进程冷却；拒绝接口只探一次。
- 原返回恰好 6,000 行、重复计数、200 代码多分区重查/合并，一直保持未知全历史名录的 PARTIAL。
- 空开放日、缺证券行不冒充停牌，非法 OHLC/代码/精度/单位、NULL 昨收不填值。
- 同日重复、修订以及修订回原值；旧 raw、旧 as-of 内容不丢。
- 真子进程在日期事务第一条记录后 `_exit(73)`；重启后该日 0 行/无 checkpoint，成功数不增加，跨日续传不重行。
- 真双进程争写只允许一个；写入中读命令拒绝过期视图。
- source/attempt 元数据篡改、raw→canonical→发布版本复算；凭据回显不入 raw/SQLite，鉴权请求不跟随重定向。
- 五个只读 CLI 命令不读取凭据、不联网、不改文件 bytes/mtime/SHA。

真实仓库进一步完整执行 `verify`、`report/status/plan`、三证券固定 20 日查询、单日全市场扫描、as-of 重查；实际文件 bytes/mtime/SHA 前后一致。还对已完成的固定 20 日窗口显式 resume，证明 **0 新请求、0 新行/版本**。数值查询只存在本机，公开输出 SHA、行数和命令。

```powershell
python -I -B scripts/test-historical-warehouse.py
python -I -B scripts/historical-warehouse.py verify
python -I -B scripts/historical-warehouse.py query --start 20211101 --end 20211126 `
  --symbols 600000.SH,000001.SZ,600519.SH --limit 100
python -I -B scripts/historical-warehouse.py query --trade-date 20261030 --limit 10000
```

## 原状态、许可和交接边界

[preservation.json](preservation.json) 记录任务开始前 14,902 个原文件（270,189,557 bytes）的保全结果，核对 bytes + mtime_ns + SHA256；明细仅留本机，避免公开 Owner 状态和私有路径。包括原相关生产源码、Observer/Snapshot/Agent 等状态。原 PR #56 分支/HEAD、原测试及 17:10 等待脚本保持独立，不运行或替换其待盘后回归。

未改 Rust 核心，按 Issue 不机械重跑 Rust workspace；未运行旧 PR56/PR52/PR54 E2E。平台仅本机 Windows/Python 3.12，Linux/macOS、物理掉电、供应商账单、完整历史身份/代码/停牌/公司行为及历史 PIT 均未独立验证。程序没有购买能力，实际购买次数 **0**；这不表示已独立核对供应商历史账单或取得再分发许可。

所有历史记录继续是 `historical_backfill_ex_post`；`historical_pit_status=NOT_VERIFIED`、`forward_research_readiness=BLOCKED`、`paper_allowed=false`、`live_allowed=false`，0 新前向观察、0 交易指令/订单/成交/NAV。唯一 Draft PR 等待固定 HEAD 风险审查；未经 Owner 授权不得 Ready/合并。
