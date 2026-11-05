# V1 本地产品收尾（Issue #77）

> **历史模块说明｜2026-11-05**：本篇描述已由 [PR #80](https://github.com/handFOOLed/Stratide/pull/80) 合并的 **V1 当时**功能。下文“Draft / 仍单证券 / 手动 JSON / 只有旧启动脚本”的描述在该交付日期真实，但不代表当前 main：V2 #82/#83/#84 已由 PR #86/#87/#88 合并，已实现全市场 EOD、自动研究和多证券共享 Paper 的软件链路。**现在仅剩 [#85](https://github.com/handFOOLed/Stratide/issues/85)（DeepSeek 负责 Windows 安装包/后台登录自启/双击打开 Dashboard）**，不应把此文的 `local-windows.ps1` 误当已打包的应用。PIT、开盘实收、真实公司行为、收益资格仍未验证。详见 [STATUS](STATUS.md)。保留 V1 原始操作和验收记录不改写。

2026-11-04，基于 main `62a4299`（已含 PR #75/#78）。本期是 Windows 本地软件集成与开发者自测；提交 Draft，Owner 决定合并。N100 主机、Linux 服务器化、物理断电长稳不在本期范围。

## 已实装的产品链路

```text
当前 Paper 账本 ── /api/v1/account、equity、positions、orders、fills ── 总览
所选历史报告 ──── 原 /api/account 等报告接口 ──────────────────── 历史报告
原 CPU/Fusion/Registry/OOS ── /api/v1/workspace（只读） ────────── Agent / 设置
Owner 本机令牌 ── 原 Agent DB 中的审批 ── 原 Worker / Gate ────── 原任务、预算、通知
```

- 当前账本由 `--paper-ledger` 显式指定，只读打开、复算日志与摘要。历史报告由原 `--report-dir` 指定，不能成为当前账户 NAV。两者同时配置仍各读各源。原 synthetic 演示可显示在总览，但始终标合成测试。
- `/api/v1/workspace` 显示原实际研究、Naive/EWMA、RMS 5/20 日风险代理、样本外误差、来源/实际取得时间、原 Registry 和准入清单。研究组合不是当前账户持仓；本地完整性通过不等于假说成立。
- 原 `/api/agent/*` 仍返回 `api_version=1`；没有第二套任务、钱包或研究调度器。设置展示来源、时效、完整性、Provider/预算、部署与备份。凭据不返回浏览器。
- 读取页面、刷新、展开报告和任务详情都不触发推理或付费调用。真实行情、TimesFM 结果和派生摘要只留本机。真实来源误入 Fusion 在原 Gate 前明确拒绝。
- 本机审批记录、任务通知及已读收据存于原 Agent SQLite `meta`；记录操作 SHA、创建/许可/执行/完成时间。许可一小时过期；拒绝、撤销、过期与重复执行由服务端检查。启动许可先持久消费，再启动原操作。重启后未确定操作标记 `outcome_uncertain`，不自动重发。
- 五秒撤销仅用于延迟写入“本地通知已读”；离开页面会取消未提交的延迟。研究已发请求、Paper 成交或券商订单不提供这种撤销语义。
- 原模型切换、任务暂停/取消/允许范围内的重试沿用原 API。桌面附着模式不运行第二个 Agent tick，不能创建无人处理的通用任务或启用虚假的 EOD 调度；从已配置操作提交研究。CPU 任务走原 CPU Gate，不用通用云重试。

## Windows 启动、停止与健康检查

使用 PowerShell 7、当前受支持的 Rust/MSVC、Python 3.12+、Node/npm。构建复用锁文件，不新增前端组件库、CDN、外部字体或桌面壳。首次构建需要本机已有依赖缓存或正常安装依赖；`--offline` 不自动下载 Rust crate。

原生 Dashboard，无研究配置时仍可查看诚实空态：

```powershell
pwsh -NoProfile -File scripts/local-windows.ps1 start
pwsh -NoProfile -File scripts/local-windows.ps1 status
pwsh -NoProfile -File scripts/local-windows.ps1 stop
```

可加 `-ReportDir '<原历史报告目录>'`、`-PaperLedger '<当前假设成交账本>'`、`-EvaluationFile '<原评价JSON>'`。`-NoBuild` 复用已构建产物，`-Port 8711` 选择另一本机端口，`-OpenBrowser` 打开页面。只有显式 `-FakeAgent -AgentDir '<新测试目录>'` 才初始化合成 Agent，没有默认本金或真实 Provider。

已有 WSL2 TimesFM CPU 环境使用原 ext4 工作树、虚拟环境和权重，先在其中构建 Rust，并把本版 `apps/dashboard/dist` 构建到该工作树。无需另部署服务器：

```powershell
pwsh -NoProfile -File scripts/local-windows.ps1 start `
  -WslWorkspace /home/OWNER/projects/Stratide `
  -WslDistribution Ubuntu-24.04 `
  -AgentDir /path/to/original-agent `
  -AgentConfig /path/to/original-agent/settings.json `
  -DesktopConfig /path/to/local-dashboard.json -NoBuild
```

在 `config/dashboard-local.example.json` 基础上创建**本机私有配置**。`workspace` 为正在运行代码的绝对路径，`python` 为该主机 Python，显式列入原 `timesfm_batches` / `fusion_batches` / `evaluation_dirs` / `registry_dirs` / `evidence_files`。原数据无须搬迁；Registry 路径可指向旧工作树。`backup_manifest` 可指向本机已验证备份的 manifest。不要把私有配置或原产物提交 Git。

`operations` 只允许固定类型和已冻结批次：`local_timesfm`、`synthetic_fusion`、`recorded_fusion`、`risk_evaluation`。浏览器只能选择操作 ID，不能提交路径、脚本、URL 或任意命令。操作关联的 Agent 必须与桌面附着的原 Agent 一致。

本地 CPU 启动是显式的 Owner 审批；它不授予云权限。合成云 Fusion 仍要求原服务/目的/数据范围许可、未消费授权、有效价格版本以及原共享 **CNY ¥5/日、¥100/月**预算。桌面不自动重新启用已消费云授权。录制 Fusion 使用 TST，不是真实账单。费用估算、最大预留、未知结果与核验账单保持分离，不为补齐费用数字调用账单 API。

进程只监听 `127.0.0.1`。原 Host/Origin/CSRF/Owner-token 检查继续生效，Owner 令牌只在浏览器内存。启动记录在 `state/windows-local/<port>/process.json`；停止前核对实例 nonce / PID / 创建时间，避免结束其他实例。异常退出后先核对旧 PID 与状态，保留旧记录再启动；不自动抹掉恢复线索。

Dashboard 停止与独立 Worker 停止是两件事。需要停止 CPU 时使用页面的“停止本地计算”，或在原工作树执行 `python3 -B scripts/timesfm-cpu.py stop`；它持久禁用原 CPU Gate。已发送云调用不能撤回，取消/重启不会把结果未知的调用当作未发送再试。

## EOD Paper 假设成交

该能力是 **Owner CLI 提交 JSON、单证券 A 股 next-open v1**，复用原 Risk Kernel 和 SQLite Ledger；不是研究候选自动转单或多证券无人值守 Paper。它是事后 Paper 假设，不是开盘实时接收或真实可成交证据；没有券商接口。当前模型固定为 `next-open-adverse-tick-100-v1`：最多 100 股、开盘价向不利方向一分、适用限价/整手/T+1/费用/资金检查、剩余 IOC 释放。模型版本随前日意图冻结，不能事后更换。

```text
paper-eod-init    <新账本目录> <Owner PaperAccountConfig JSON> <来源版本ID>
paper-eod-intent  <原账本目录> <唯一事件ID> <前日意图JSON>
paper-eod-confirm <原账本目录> <唯一事件ID> <次日盘后来源JSON>
paper-eod-expire  <原账本目录> <唯一事件ID>
```

用 `target/debug/stratide-cli[.exe]` 调用。`init` 配置是原 `PaperAccountConfig`，必须包含 Owner 明确的本金、账户/策略风险限额、身份及估值时效，没有暗设 ¥100,000。不会修改或迁移旧账本。来源版本自动加 `paper-eod-assumption-v1:`。

- `intent` 输入仍为 `{proposal, rules, fees, marks, target_day}`；CLI 以真实本机时钟覆盖 `decision_at`。上海当天 16:00 后，原 Observe → Submit → Freeze 在**一个 `SubmitPaperIntentV1` 事件和一个 SQLite 事务**内完成；错误日期、过期窗口、写入前校验失败或 commit 前崩溃不会留下半笔订单/预留。commit 后重启及跨日同 ID/同输入重试返回原记录，改内容复用 ID 拒绝。风控拒绝是一个持久终态订单、没有冻结/预留；已观察到的损失锁照常保留。
- `target_day` 必须由 Owner 依据可信交易日历给出**下一开市日**。核心拒绝无效/非未来日期及不在提案执行/到期窗口内的目标；不能由普通周一至周五猜测，也不声称已独立校验下一开市日。本切片不新增日历下载器。错填休市日期、停牌、缺行或供应商延迟，都有下述确定性整批到期路径，不需要重建账户。
- 新意图冻结时写入目标日**上海 17:15** 的 `confirmation_deadline`，沿用既有 EOD 采集窗口的截止时点。这是 Paper 固定接收截止，不是供应商交付保证。`confirm` 仍输入 `{bar, rules, source_received_at, corporate_actions_verified}`，仅在目标日 16:00 后、截止前接受；`bar` 是原未复权 `DailyBar`，provenance 须与该账本一致。缺价格/状态/公司行为证据、错日期/来源、资金或费用不适用均不能生成相关成交。
- `expire` 不接收行情、价格或选择的订单 ID。到固定截止后，对尚未确认的**整个批次**写 `NO_FILL / DATA_UNAVAILABLE`、目标/原意图/订单 ID、截止及终结时间，释放预留并清除 pending；它表示未取得合格确认，不据此断言停牌原因。现金、持仓、旧估值时点、成交数和风险锁保持；不补价格、不增加 NAV 点、不重发旧信号。截止前不能用它撤销不利订单，截止后不能再用后来价格确认旧订单；同事件重试不重复终结。源恢复后，只有新的显式意图和原 Risk 检查才能继续。
- 对 R1 前遗留的 `:submit` 成功、`:freeze` 未写入订单，先保留原文件，过原决策日后执行 `paper-eod-expire <原账本> <新事件ID>`，记录 `NO_FILL / UNSEALED_LEGACY_INTENT` 并整批释放。旧冻结批次按目标日 17:15 进行无成交终结；旧已完成事件保留原序列化与哈希可重放，不迁移/改写旧历史。无成交终结后禁止回填早于其时间的新命令，重新提交使用新事件/提案 ID，禁止自动重放旧输入。
- SHA256 证明本机输入字节完整性；`source_received_at`、`corporate_actions_verified` 及日历/行情来源目前是 **Owner JSON 声明，非独立供应商收数或 PIT 证明**。API/CLI 保留 `OWNER_DECLARED_NOT_PROVIDER_VERIFIED`，无成交收据进入只读数据缺口/技术详情。次日实际交易规则仍须独立核验，不能把前日规则当作次日事实。
- 前日冻结原订单、数量、撮合版本和输入 SHA；冻结后不能新增/撤销/替换订单或先导入次日价格。账户风险冻结仍可写入，且继续阻止成交。`confirm` 用唯一事件 ID 幂等记账，变更输入不能复用 ID。没有有效前日冻结就拒绝。
- 成交写 `EX_POST_OPEN_ASSUMPTION`、来源 SHA 和实际取得时间，不创建 `OpeningEvidence`。历史、合成及假设成交不会升级为 `forward_observed_eod`。当前账户收益/成本来自账本和可信估值；资金流不算利润。缺估值显示 `—`，有外部资金流时简单累计收益率不可用。最大日回撤仅覆盖账本记录的日期。

[Tushare daily 官方语义](https://tushare.pro/wctapi/documents/27.md)：未复权日线通常盘后更新，价格元、量手（100 股）、额千元，停牌没有当日日线；本系统不能把接口描述当作历史逐条发布时间证明。[trade_cal](https://tushare.pro/wctapi/documents/26.md) 是交易日历来源。没有 `stk_auction` 不阻断上述盘后假设工程，但开盘实收与 PIT 仍 `NOT_VERIFIED`。

## 备份与恢复

先停止对应 Dashboard、EOD/研究 Worker 及其他写入者。复制 `config/local-backup.example.json` 到本机私有目录，把要保护的原 journal / Agent / Registry / 账本 / 研究状态逐项列入 `sources`；行情仓库和权重是否备份由 Owner 按空间决定，不自动扫描全盘。

```powershell
python -X utf8 -B scripts/local-backup.py create --config '<私有配置>' --out '<全新备份目录>' --stopped
python -X utf8 -B scripts/local-backup.py verify --bundle '<备份目录>'
python -X utf8 -B scripts/local-backup.py restore --bundle '<备份目录>' --out '<不存在的恢复目录>'
# 上一步默认 dry-run；确认目标后才实际写入新目录：
python -X utf8 -B scripts/local-backup.py restore --bundle '<备份目录>' --out '<不存在的恢复目录>' --apply
```

WSL ext4 数据在原 WSL 工作树用 `python3` 执行相同脚本。备份使用已有 OS 锁和 SQLite backup API，检查源未在复制期间变化；每文件大小/SHA 与 SQLite `integrity_check` 写入并复核 manifest。路径逃逸、篡改、链接或既有目标会拒绝。`owner-token`、已知 token/key/.env、锁、WAL/SHM、进程记录不复制；**原凭据始终保留原位**，Windows 原生凭据另由 Owner 保管。自定义任意命名的秘密文件不得列入数据源，此工具不声称识别所有秘密。

恢复只写全新隔离目录，默认 dry-run，无覆盖、无启动、无任务/调用/历史观察重放。检查 manifest、原任务结果/未知预留、账本头和授权后，再由 Owner 显式选用恢复目录并重新连接既有凭据。恢复数据可能保留原启用状态，不能直接把它当全新授权启动研究。

## UI 精修与验收范围

沿用 PR #28 的浅灰/白卡/左栏、黑主按钮、蓝焦点。调整 CSS token（系统字体、1280px 内容宽度、24px 标题/核心数字、12/8/6 圆角、弱文字对比度）、Chart、Badges、Sidebar、分页与空态；清除 Agent 光晕/装饰图标、图表渐变，设置入口固定侧栏底部。

按 Refactoring UI 的层级/留白/颜色语义检查实际页面：账户值与来源标签分层；风险卡和空表不虚撑；五行表页保持高度；自适应轴保留本金与五个等距区间（每格为显示范围 20%，不是收益率 20%）；回撤/费用/正常成功使用中性色，财务红涨绿跌；机器枚举、完整 SHA 和拒绝码在技术详情可复制。审批/通知约 60/40，窄屏单列。保留必要 Paper/权限提示。

浏览器实装检查覆盖 1920×1080、1366×768、1280px、125% 缩放、375px、深浅主题、键盘/焦点、抽屉和 reduced-motion。1920 与 1366 总览首屏无滚动。截图仅使用明确的 synthetic_test 固定数据，不代表 Owner 资金或市场收益。

## 开发者验证与真实限制

执行命令、结果和合成截图见 [本期本地绿测简报](evidence/v1-closeout-b/README.md)。全流程使用当前代码和原实际本地研究读取，云融合 E2E 使用独立测试仓库的 authorized synthetic/recorded 输入，没有新增真实云/行情请求或原账单记录改写。

软件状态可记录为 `V1_ENGINEERING_COMPLETE`；**该状态不等于已合并或独立验收**。#10 连续真实 EOD/开盘来源、#17 公司行为/PIT/早期费率仍由只读证据清单判定，交易资格 `BLOCKED`。没有新增真实前向成交、已验证收益、PIT 或开盘流实收声明。N100 为 `DEFERRED_NOT_V1_GATE`；未来部署/长稳另定范围。
