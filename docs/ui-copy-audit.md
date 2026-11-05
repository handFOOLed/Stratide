# 阶段 0：Stratide 全站用户可见文案审计

> 审计对象：Stratide Web Dashboard（本地模拟盘 + AI 研究工作台，React 19 + TypeScript + esbuild 单页前端）
> 审计基线：`feat/ui-product-ux` 分支 HEAD `70b2828`（2026-11-05，"fix(ui): read backfill progress from the batch file and hide healthy dependency notes"）
> 源码范围：`apps/dashboard/src` 全部 64 个 `.ts/.tsx` 文件（9,417 行，348,928 字节）
> 产出：本文件（唯一交付物）。审计为只读，未修改任何源码、数据或配置。
> 术语基准：任务目标术语表 + 并行产出的 `docs/UI_TERMINOLOGY.md`（本审计引用其口径，不修改它）

---

## 1. 审计范围与方法

### 1.1 范围

- 覆盖全部 6 个页面入口：总览、历史报告（成交 / 订单 / 逐日核对 / 策略档案 / 研究档案）、Agent 管理、通知、设置（外观 / AI 服务 / 运行与安装 / 数据连接 / 关于）、首次使用协议页。
- 覆盖全局外壳：侧边栏、顶栏、健康状态弹层、账户菜单、页脚更新说明、Toast、Drawer、Modal、Pager、空状态、图表内文案、表格 caption 与 `aria-label` / `title`。
- 覆盖所有用户可见的错误提示、toast、空状态、按钮、placeholder、表头、图注、徽标、折叠区标题与说明。
- 覆盖`lib/` 中会直接成为界面的映射文案（`labels.ts`、`workspace.ts`、`runtime.ts`、`api.ts`、`format.ts`、`route.ts`）与状态兜底文案。
- **不覆盖**：`className`、`data-testid`、路由 hash、URL/端点、内部 import、CSS、构建脚本；也不评估交互逻辑、视觉设计与后端数据正确性（后端语义由并行任务另行调研）。

### 1.2 方法（可复现）

1. 通读 64 个源文件，人工记录页面结构、组件层级与文案上下文。
2. 用 Node + TypeScript Compiler API 对每个文件构建 AST，抽取全部 `StringLiteral`、`NoSubstitutionTemplateLiteral`、`TemplateExpression` 与 `JsxText`，保留 `文件:行号`，并过滤 import 路径。抽取脚本不落盘到仓库，结果临时保存于本机临时目录。
3. 抽取结果：**3,999 条字符串字面量/JSX 文本**，其中含中文 **1,338 条 / 1,012 个不重复值**；排除未挂载组件后为 **1,253 条 / 936 个不重复值**。含中文文案分布于 41 个文件。
4. 逐条按固定六类判断：**术语、内部状态、中英混用、写给开发者的话、重复、前后矛盾**；同一句命中多类时并列标注。
5. 对每一类再核对术语表、状态枚举与上下文，形成建议文案；行号统一指 HEAD 基线（部分多行 JSX 文本取起始行）。
6. 复核：文末表格中每条"原文"的定位键（最长中文片段）均回查源码行，未发现编造行号；复核口径与结果见附录 B。

### 1.3 判定口径

| 类型 | 判定标准 | 典型信号 |
| --- | --- | --- |
| 术语 | 与目标术语表不一致，或普通投资者无法理解的行业/内部名词 | Paper、Agent、EOD、风控锁、隐含持仓、初始净值、逐日核对、源日 |
| 内部状态 | 直接渲染后端枚举、原始错误码/原因、内部 ID、原始路径或技术字段 | queued、BLOCKED、REAL_MARKET_DATA_EGRESS_DENIED、valuation_error、provider_hash、--report-dir |
| 中英混用 | 中文句子里夹带未说明的英文词、英文缩写或英文单位 | EOD watch、Supervisor、Worker、Provider、payload、Naive / EWMA、TWR |
| 写给开发者的话 | 向用户解释实现、接口限制、内部流程或维护方式，而不是用户该知道的结果 | "当前 API 没有提供…"、"原始 reason 不做前端改写"、"不调用模型"、启动命令 |
| 重复 | 同一含义在相邻位置/多页面重复，或同一概念有多种说法并列出现 | 三处 stale banner 措辞不一、"重新读取" 13 次 / "刷新" 多处 |
| 前后矛盾 | 同一对象在不同页面/同一页面的称呼、数字、口径或状态不一致 | 84 个交易日 vs 84 个 READY 会话；风控锁 vs 风险锁；0 条 vs N 只 |

### 1.4 基线说明与并行改动

- 审计期间工作区出现并行改造：`lib/copy.ts`、`lib/status.ts`、`components/ui/StatusBadge.tsx`、`components/ui/Diagnostics.tsx`、`components/ui/InfoHint.tsx`、`docs/UI_TERMINOLOGY.md` 为未跟踪新增；`components/domain/Badges.tsx`、`lib/api.ts`、`lib/format.ts`、`lib/labels.ts` 已有未提交修改。**本审计不评价这些未提交改动**，所有 `文件:行号` 均对应 HEAD `70b2828`；实现合并后行号会漂移，请以"原文"为检索键。
- 截至本审计完成时，实现侧已在同一分支起草 `lib/status.ts`、`components/ui/StatusBadge.tsx`、`components/ui/Diagnostics.tsx` 等未提交文件，方向与本审计一致；这不是本期审计的评分对象，但建议实现完成后按本文件 §4 与 §6 逐项复核。
- 结果统计口径：§3 总表列出所有**需要整改或需要明确保留理由**的用户可见字符串；纯占位符（`—` 51 处）与纯数字/日期格式化不再逐条列出；未挂载组件在 §3.9 单列（当前不渲染，但接入前必须整改）。

---

## 2. 页面清单与用户目的

| 入口 | 页面 / Tab | 普通投资者的目的 | 现状主要问题（详见 §3） |
| --- | --- | --- | --- |
| `#overview` | 总览 | 一眼看清模拟账户资产、今日/累计盈亏、持仓、最近成交、交易保护状态 | 风控锁/估值/报告日等术语密集；数量词混用；"84 个交易日"口径不明；组合批次说明技术化 |
| `#history/fills` | 历史报告 · 成交 | 核对每笔模拟成交的价格、数量、费用与对应策略 | 表头用内部词；策略列直接显示 `strategy_id`；底部说明面向开发者；时间/日期口径不统一 |
| `#history/orders` | 历史报告 · 订单 | 查询委托、已确认/剩余数量、拒绝原因 | "原始原因"直接渲染后端 reason；状态列出现"中文 / 枚举"；方向兜底会把未知方向显示成"卖出" |
| `#history/daily` | 历史报告 · 逐日核对 | 按数据日核对账户资产、现金、持仓市值与收益 | "逐日核对/报告日/源日期/隐含持仓/外部净流入/初始净值"全部待替换；Drawer 内解释 API 限制 |
| `#history/strategies` | 历史报告 · 策略档案 | 了解每个策略版本的记录状态与独立收益/回撤 | "冻结部署/冻结版本/部署标识"等部署术语；状态被压成"Paper 假设记录"或直接显示原始值 |
| `#history/research` | 历史报告 · 研究档案 | 回看已保存的 AI 研究报告与样本外评价 | "研究证据/工程/独立验收"字段原样渲染；"不计入账户 NAV"；大量"不构成/不代表"免责式说明 |
| `#agents` | Agent 管理 | 开关收盘后自动研究、查看任务进度与预算、发起研究任务 | 页面标题即内部词；EOD/Worker/Provider/Token/队列等术语；失败任务无一句话原因；筛选词"异常 / 费用不确定" |
| `#notifications` | 通知 | 查看研究任务完成/失败提醒并标记已读 | 只显示"任务 #id · 状态"，不显示原因；读取了 approvals 却完全不展示；"5 秒后标为已读"交互文案突兀 |
| `#settings/appearance` | 设置 · 外观 | 选择深浅色与减弱动态效果 | 基本合规，仅"跟随系统/浅色/深色"需与全站主题词统一 |
| `#settings/ai` | 设置 · AI 服务 | 配置云端 AI 服务商与 API Key、查看预算 | "研究模型已安装/重新安装"混淆云端 API 与本地模型；预算同时出现 `¥` 与后端币种；"已完成/未能完成"过于笼统 |
| `#settings/runtime` | 设置 · 运行与安装 | 确认后台任务、行情采集、本地预测引擎与数据补齐进度 | 全站技术词最多：Supervisor、EOD watch、WSL、venv、manifest、PID、Release、Token、BLOCKED、原始错误码直出 |
| `#settings/data` | 设置 · 数据连接 | 确认数据来源、日期、完整性与缺口 | 直接显示 snapshot_id/sha256/evidence_class；PIT、TWR、daily.open、--report-dir 等内部说明；硬编码"前向账户尚未验证" |
| `#settings/about` | 设置 · 关于 | 查看版本、构建信息与更新方式 | 整页是开发者信息（技术栈、脚本路径、N100 计划、本地 build SHA），普通用户无法使用 |
| 首次启动 | 首次使用协议 | 一次性了解模拟盘边界、云端研究、预算与停止方式 | 关键数字/承诺与产品状态可能不一致（¥100,000、10 年、84 天、¥5/日）；停止方式要求删除内部文件 |
| 全局 | 侧栏 / 顶栏 / 健康弹层 / 账户菜单 | 导航、服务在线状态、本机身份 | Paper workspace、Owner、localhost、127.0.0.1、local、服务在线/离线/检查中多套说法 |
| 全局 | Drawer / Modal / Toast / 空状态 | 查看详情、确认操作、接收结果 | "重新读取"重复 13 次；关闭按钮三种说法；toast 直接拼后端 code |
| 未挂载 | MarketResearchPanel / ResearchOperations / SnapshotBadges / AvailabilityBadge | 全市场自动研究、外发许可、冻结研究（尚未接入导航） | 若直接接入会引入 Agent/Owner/Provider/Budget Gate/READY/BLOCKED/payload 等大量内部词（§3.9） |

---

## 3. 用户可见字符串总表

> 路径均相对 `apps/dashboard/src/`。原文为源码原文（长句以"…"截断；由变量拼接的句子用 N / {…} 表示插入值，行号为拼接起始行）。问题类型限定为六类，可多选。

### 3.1 全局外壳与通用组件

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| layout/Sidebar.tsx:34 | Paper workspace | 术语；中英混用 | 本地模拟盘 |
| layout/Sidebar.tsx:26 | 工作空间侧边栏（aria-label） | 术语 | 主导航 |
| layout/UserMenu.tsx:77 | 本机 Owner，Paper 工作空间（aria-label） | 术语；中英混用 | 本机用户，本地模拟盘 |
| layout/UserMenu.tsx:85 | 本机 Owner | 术语 | 本机用户 |
| layout/UserMenu.tsx:86 | Paper 工作空间 | 术语；中英混用 | 本地模拟盘 |
| layout/UserMenu.tsx:96 | 本机 Owner | 术语 | 本机用户 |
| layout/UserMenu.tsx:97 | localhost · 仅本机 | 中英混用 | 仅本机访问 |
| layout/UserMenu.tsx:123 | 本机只读工作空间 | 术语 | 本机只读 |
| layout/UserMenu.tsx:124 | v{__UI_VERSION__} | 内部状态 | 移到"设置 › 关于 › 诊断信息" |
| layout/HealthPopover.tsx:88 | 本机服务状态（标题，与 76/85 重复） | 重复；术语 | 系统状态 |
| layout/HealthPopover.tsx:80 | 服务在线 / 服务离线 | 术语；前后矛盾（与"在线/无法连接"并存） | 系统正常 / 无法连接 |
| layout/HealthPopover.tsx:89 | 只读 Paper · 127.0.0.1 | 中英混用；写给开发者的话 | 本地模拟盘 · 仅本机 |
| layout/HealthPopover.tsx:91 | local | 中英混用；内部状态 | 删除（改为"仅本机访问"） |
| layout/HealthPopover.tsx:95 | Web 服务 | 术语 | 本地服务 |
| layout/HealthPopover.tsx:98 | 在线 / 无法连接 / 检查中 | 术语；重复 | 正常 / 无法连接 / 正在检查 |
| layout/HealthPopover.tsx:102 | Paper 快照 | 术语 | 模拟账户数据 |
| layout/HealthPopover.tsx:106 | 行情时效 | 术语 | 数据时效 |
| layout/HealthPopover.tsx:109 | 最后发布快照 · 非实时 | 写给开发者的话 | 盘后数据 · 非实时 |
| layout/HealthPopover.tsx:114 | 前向账户 | 内部状态 | 模拟账户 |
| layout/HealthPopover.tsx:120 | 研究 Agent | 术语 | AI 研究 |
| layout/HealthPopover.tsx:126 | 通知服务 | 内部状态 | 通知 |
| layout/HealthPopover.tsx:134 | 检查于 {时间} | 前后矛盾 | 更新于 {时间} |
| layout/HealthPopover.tsx:141 | 服务可达不等于风控运行正常或行情新鲜。更新 Paper 快照需显式重启服务。 | 术语；写给开发者的话 | 服务可访问不代表数据已更新；每天收盘后会自动更新数据。 |
| layout/Topbar.tsx:43 | 切换到浅色主题 / 切换到深色主题 | —（合规） | 保留 |
| layout/Topbar.tsx:28 | 打开导航 | —（合规） | 保留 |
| components/layout/PageFooter.tsx:5 | 读取于 {时间} | 前后矛盾 | 更新于 {时间} |
| lib/hooks.ts:185 | Stratide · Paper 工作空间（浏览器标题） | 术语；中英混用 | Stratide · 本地模拟盘 |
| components/ui/Chart.tsx:81 | 没有有效估值 | 术语 | 数据缺失 |
| components/ui/Chart.tsx:105 | 此区间没有有效估值。 | 术语 | 这段时间没有可用数据。 |
| components/ui/Chart.tsx:126 | aria-label={label + '。' + summary}（summary 含"有效估值/缺失估值断开…不补点"） | 术语；写给开发者的话 | "N 个数据日，M 天缺失"（仅保留可读摘要） |
| components/ui/Chart.tsx:179 | 本金 | 术语 | 初始资金 |
| components/ui/Overlay.tsx:118 | 关闭详情 | 重复 | 关闭 |
| components/ui/Overlay.tsx:166 | 关闭对话框 | 重复 | 关闭 |
| components/ui/Toast.tsx:88 | 关闭提示 | 重复 | 关闭 |
| components/ui/EmptyState.tsx:41 | 重新读取（默认按钮） | 重复 | 重试（或全站统一"重新读取"） |
| App.tsx:108 | 正在读取本机设置… | 术语 | 正在读取设置… |

### 3.2 总览

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| pages/OverviewPage.tsx:130 | 总览 | 术语 | 账户总览 |
| pages/OverviewPage.tsx:159 | 未知错误（兜底） | 内部状态 | 读取失败，原因未记录 |
| pages/OverviewPage.tsx:168 | 当前 Paper 账户尚未配置 | 术语 | 模拟账户尚未设置 |
| pages/OverviewPage.tsx:168 | 已选择的是事后历史报告。报告的净值、持仓与交易保留在历史页，不作为当前 Paper 账户。 | 术语；写给开发者的话 | 当前显示的是历史报告，不代表现在的模拟账户。 |
| pages/OverviewPage.tsx:189 | 最近一次读取失败，以下为上次成功的快照 | 重复（三处措辞不一） | 更新失败，以下为上次成功的数据 |
| pages/OverviewPage.tsx:192 | 重新读取 | 重复 | 重试 |
| pages/OverviewPage.tsx:201 | 风险提示 | 术语（实为交易保护状态） | 交易保护 |
| pages/OverviewPage.tsx:204 | 最后估值缺失 | 术语 | 账户数据缺失 |
| pages/OverviewPage.tsx:205 | 净值与盈亏暂不可用。服务端原因：{valuation_error}。 | 写给开发者的话；内部状态 | 当前无法计算账户资产与盈亏。详情见诊断信息。 |
| pages/OverviewPage.tsx:214 | 此快照记录 N 项风控锁 | 术语；内部状态 | 交易保护已触发 N 项限制 |
| pages/OverviewPage.tsx:215 | 此快照未记录风控锁 | 术语；前后矛盾 | 交易保护正常，当前没有触发限制 |
| pages/OverviewPage.tsx:219 | 账户锁 | 术语 | 账户限制（诊断区） |
| pages/OverviewPage.tsx:220 | 策略锁 | 术语 | 策略限制（诊断区） |
| pages/OverviewPage.tsx:221 | 估值 有效 / 缺失 | 术语 | 数据 正常 / 缺失 |
| pages/OverviewPage.tsx:226 | 存在风控锁时，新的模拟下单会被阻止；解除需要你确认。 | 术语；前后矛盾（无解除入口） | 触发交易保护时，新的模拟交易会被暂停。 |
| pages/OverviewPage.tsx:227 | 当前没有风控锁。触线会自动阻止新的模拟下单。 | 术语；重复 | 交易保护正常；触发限制时会自动暂停新的模拟交易。 |
| pages/OverviewPage.tsx:236 | 账户资产 | 术语 | 模拟账户资产 |
| pages/OverviewPage.tsx:242 | 今日盈亏 | 前后矛盾（与"当日盈亏"两词并存） | 今日盈亏 |
| pages/OverviewPage.tsx:251 | 累计盈亏 | —（合规） | 保留 |
| pages/OverviewPage.tsx:258 | 累计费用 | 前后矛盾（与"累计模拟费用"） | 累计费用 |
| pages/OverviewPage.tsx:271 | 最大日回撤 | 术语 | 最大单日回撤 |
| pages/OverviewPage.tsx:280 | 交易预留 | 术语 | 挂单冻结资金 |
| pages/OverviewPage.tsx:290 | 资产曲线 | 术语 | 账户资产曲线 |
| pages/OverviewPage.tsx:292 | {N} 个报告日 | 前后矛盾 | {N} 个数据日 |
| pages/OverviewPage.tsx:293 | ' · 缺 ' + String(missingValuations) + ' 日' | 术语 | · 缺失 {N} 天 |
| pages/OverviewPage.tsx:312 | 当前 Paper 账户资产曲线 | 术语；中英混用 | 模拟账户资产曲线 |
| pages/OverviewPage.tsx:316 | 纵轴自适应 · 每格为显示范围的 20% | 写给开发者的话 | 纵轴自动调整 |
| pages/OverviewPage.tsx:323 | 净值曲线将在第二个交易日出现 | 前后矛盾（与空状态"资产曲线…数据日"） | 资产曲线将在第二个数据日出现 |
| pages/OverviewPage.tsx:324 | 当前只有 1 个报告日；每天盘后采集完成后会自动延长这条曲线。 | 术语；写给开发者的话 | 现在只有 1 个数据日；每天收盘后会自动更新。 |
| pages/OverviewPage.tsx:335 | 当前持仓 | —（合规） | 保留 |
| pages/OverviewPage.tsx:341 | 当前空仓 / 此报告没有持仓记录。 | 术语；重复 | 当前空仓 / 没有持仓时这里会保持为空。 |
| pages/OverviewPage.tsx:348 | 持有 | 术语 | 持有数量 |
| pages/OverviewPage.tsx:351 | 可卖 | 术语 | 可卖数量 |
| pages/OverviewPage.tsx:385 | '0 条' | 前后矛盾（同卡片上方用"只"） | 0 只 |
| pages/OverviewPage.tsx:386 | String(firstVisible) + '–' + String(lastVisible) + ' / 共 ' + String(sortedPositions.length) + ' 条' | 前后矛盾（同卡片用"只"） | {起}–{止} / 共 {N} 只 |
| pages/OverviewPage.tsx:396 | 已确认模拟成交 · 每页 5 笔 | 写给开发者的话 | 最近模拟成交 |
| pages/OverviewPage.tsx:401 | 尚无已确认模拟成交 / 未成交与拒绝的订单可在历史中查看。 | 术语；前后矛盾（订单在"订单"tab） | 还没有模拟成交 / 未成交或已拒绝的订单可在"订单"中查看。 |
| pages/OverviewPage.tsx:442 | 共 {bundle.fills.length} 笔 | —（需与"条/只"统一） | 共 {N} 笔 |
| pages/OverviewPage.tsx:454 | 每天收盘后自动采集当天行情，不需要你启动。 | 术语 | 每天收盘后会自动更新数据。 |
| pages/OverviewPage.tsx:455 | 数据满 84 个交易日后，本机模型与已授权的云研究才会生成候选。 | 术语；前后矛盾（84 口径） | 连续 84 个交易日的完整数据后，本地预测与 AI 研究才会生成候选。 |
| pages/OverviewPage.tsx:456 | 通过风控后，才会在你的 {初始净值} 模拟账户里产生模拟成交。 | 术语 | 通过交易保护后，才会在初始资金 {¥…} 的模拟账户中产生模拟成交。 |
| components/domain/PaperPortfolioPanel.tsx:8 | 多证券共享 Paper · 冻结与结算 | 术语；中英混用；写给开发者的话 | 多证券模拟组合 |
| components/domain/PaperPortfolioPanel.tsx:9 | 新意图已启用 / Owner 已暂停新意图 · 固定目标 ¥… / 证券 · 最多 N 只持仓 · 每日最多 N 笔。 | 术语；内部状态 | 自动模拟交易已开启 / 已暂停；每只证券目标 ¥…，最多 N 只，每日最多 N 笔。 |
| components/domain/PaperPortfolioPanel.tsx:10 | 仅 Paper 假设模拟。日线开盘在盘后实收后按已冻结顺序记账；真实开盘、历史 PIT 和可交易性均未核验。模型权重不授予交易权限。 | 写给开发者的话；中英混用 | 仅为模拟成交，按次日开盘价计算；不代表真实可成交价格。 |
| components/domain/PaperPortfolioPanel.tsx:11 | 整批共享成交容量：{N} 股；按冻结顺序消耗，余量 NO_FILL。 | 内部状态 | 移到诊断信息 |
| components/domain/PaperPortfolioPanel.tsx:11 | 旧冻结策略：容量为历史每单语义。 | 写给开发者的话 | 删除或移到诊断信息 |
| components/domain/PaperPortfolioPanel.tsx:12 | 未批准公司行为未核验的假设成交，仅接受核验输入。 | 写给开发者的话 | 删除或移到诊断信息 |
| components/domain/PaperPortfolioPanel.tsx:12 | Owner 已批准 {version}：公司行为未核验…总敞口另限 ¥…，不代表真实可交易。 | 术语；内部状态 | 移到诊断信息 |
| components/domain/PaperPortfolioPanel.tsx:13 | NO_TRADE_REBASE · {date} → {date} 当前估值恢复；缺口与恢复日的当日盈亏不可用，未补历史成交，未解除风险锁。 | 内部状态；中英混用；术语 | 数据恢复日无法计算当日盈亏（诊断信息保留细节）。 |
| components/domain/PaperPortfolioPanel.tsx:15 | {date} 决策 → {date} 目标交易日 | 术语 | {date} 决策 → {date} 执行日 |
| components/domain/PaperPortfolioPanel.tsx:16 | 批次已冻结，等待目标日盘后来源或截止 / 批次已终结 | 内部状态 | 等待收盘后数据 / 已完成 |
| components/domain/PaperPortfolioPanel.tsx:16 | 研究未就绪 · 原候选任务 #{id} · {N} 笔审批 · {N} 项编译拒绝 | 术语；内部状态；写给开发者的话 | 还没有研究报告 · N 笔通过 / N 笔未通过（任务 ID 进诊断） |
| components/domain/PaperPortfolioPanel.tsx:20 | 原订单 {id}：未取得账本投影 | 写给开发者的话；内部状态 | 订单数据暂不可用（诊断信息） |
| components/domain/PaperPortfolioPanel.tsx:21 | {证券} · {方向} {N} 股 · 已模拟确认 {N} 股 · {order.status} · {order.reason} | 内部状态 | 中文状态 + 原因一句话；原始枚举进诊断 |
| components/domain/PaperPortfolioPanel.tsx:23 | {证券} · 未提交 · {reason} | 内部状态 | 未提交：原因见诊断信息 |
| components/domain/PaperPortfolioPanel.tsx:26 | 尚无冻结批次。暖机不足 84 个 READY 会话或缺少原研究证据时保持空仓，原 EOD 继续采集。 | 术语；中英混用；前后矛盾 | 还没有新的模拟交易计划。完整数据不足 84 个交易日时保持空仓，行情采集继续进行。 |
| components/domain/PositionDrawer.tsx:40 | {position.instrument.market}（原样显示 Shanghai） | 中英混用；内部状态 | 沪市 / 深市 |
| components/domain/PositionDrawer.tsx:49 | 持有数量 | —（合规） | 保留 |
| components/domain/PositionDrawer.tsx:50 | 可卖数量 | —（合规） | 保留 |
| components/domain/PositionDrawer.tsx:51 | 未交收 | 术语 | 未交收数量 |
| components/domain/PositionDrawer.tsx:52 | 预留卖出 | 术语 | 冻结卖出数量 |
| components/domain/PositionDrawer.tsx:65 | 市值只从已核对的有效 NAV 与现金导出；报告没有独立行情序列。 | 写给开发者的话；中英混用 | 持仓市值按账户数据计算。 |
| components/domain/PositionDrawer.tsx:70 | 报告未提供持仓批次。 | —（可保留，建议改"暂无持仓批次明细"） | 暂无持仓批次明细。 |
| components/domain/PositionDrawer.tsx:96 | 报告没有提供可用的行情序列。 | 写给开发者的话 | 暂无该证券的历史价格数据。 |
| components/domain/PositionDrawer.tsx:127 | 仅显示最近最多五笔关联成交，不在此抽屉内复制完整历史表。 | 写给开发者的话 | 最近 5 笔模拟成交 |
| components/domain/PositionDrawer.tsx:130 | 部署记录 | 术语 | 策略记录（高级） |
| components/domain/PositionDrawer.tsx:133 | 所属组 / 策略 / 冻结版本 / 部署标识（133–136） | 术语 | 移到诊断信息，仅保留"策略版本" |
| components/domain/FillDrawer.tsx:80 | 报告只提供费用合计 ¥…，没有拆分。 | 写给开发者的话 | 该笔费用未拆分明细。 |
| components/domain/FillDrawer.tsx:108 | 时间与来源 | 术语 | 时间 |
| components/domain/FillDrawer.tsx:109 | 模拟记账，非券商成交 | 术语 | 模拟成交，不是真实成交 |
| components/domain/FillDrawer.tsx:115 | 模拟记账时间 | 术语 | 模拟成交时间 |
| components/domain/FillDrawer.tsx:116 | 开盘审查时间 | 术语 | 交易保护检查时间 |
| components/domain/FillDrawer.tsx:117 | 源日期 | 前后矛盾 | 数据日期 |
| components/domain/FillDrawer.tsx:118 | 成交编号 | 内部状态 | 移到诊断信息 |
| components/domain/FillDrawer.tsx:119 | 执行假设（原始值直出） | 内部状态；中英混用 | 移到诊断信息，主界面写"按次日开盘价模拟成交" |
| components/domain/FillDrawer.tsx:120 | 来源版本（原始值直出） | 内部状态 | 移到诊断信息 |
| components/domain/FillDrawer.tsx:121 | 组 / 策略 / 冻结版本 / 部署标识（121–123） | 术语 | 移到诊断信息 |
| components/domain/FillDrawer.tsx:102 | 当前快照中没有关联订单。 | 术语 | 没有找到这笔成交对应的订单。 |

### 3.3 历史报告

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| lib/route.ts:27 | Agent 管理（导航`PAGE_LABELS`） | 术语 | AI 研究 |
| lib/route.ts:35 | 逐日核对 | 术语 | 每日账本 |
| lib/route.ts:36 | 策略档案 | 术语 | 策略版本 |
| lib/route.ts:37 | 研究档案 | 术语 | 研究报告 |
| pages/HistoryPage.tsx:40 | 成交 / 订单 / 逐日核对 / 策略档案 / 研究档案（TAB_LABELS 40–44，与 route.ts 重复定义） | 术语；重复 | 复用 route.ts 的术语常量 |
| pages/HistoryPage.tsx:73 | 历史报告 | 术语（实为历史记录） | 历史数据 |
| pages/HistoryPage.tsx:79 | 源日 {日期} | 术语 | 数据日期 {日期} |
| pages/HistoryPage.tsx:88 | 历史报告视图（aria-label） | 术语 | 历史数据视图 |
| pages/HistoryPage.tsx:100 | 账户数据不可用 | 内部状态 | 模拟账户数据读取失败 |
| pages/HistoryPage.tsx:108 | 最近一次读取失败，以下为上次成功读取的快照 | 重复；前后矛盾 | 更新失败，以下为上次成功的数据 |
| pages/HistoryPage.tsx:111 | 重新读取 | 重复 | 重试 |
| pages/HistoryPage.tsx:194 | 搜索成交（aria-label） | —（合规） | 保留 |
| pages/HistoryPage.tsx:195 | 搜索证券、策略或订单号（placeholder） | —（可保留；订单号对普通用户意义弱） | 搜索证券、策略或订单 |
| pages/HistoryPage.tsx:201 | 成交方向 | —（合规） | 保留 |
| pages/HistoryPage.tsx:212 | 时间顺序 | 术语 | 排序 |
| pages/HistoryPage.tsx:214 | 最新优先 / 最早优先 | 术语 | 最新在前 / 最早在前 |
| pages/HistoryPage.tsx:221 | {String(filtered.length)} / {String(fills.length)} 笔 | 数量词（与"条/只/个"混用） | {N} / {M} 笔 |
| pages/HistoryPage.tsx:227 | 尚无已确认模拟成交 / 没有匹配的成交 | 术语 | 还没有模拟成交 / 没有匹配的成交 |
| pages/HistoryPage.tsx:230 | 此报告没有已确认的模拟成交。未成交、拒绝和过期订单可在订单状态中查看。 | 术语；写给开发者的话 | 还没有模拟成交；未成交或已拒绝的订单可在"订单"中查看。 |
| pages/HistoryPage.tsx:236 | 完整模拟成交（表格 caption） | 内部状态 | 模拟成交记录 |
| pages/HistoryPage.tsx:272 | {fill.deployment.strategy_id}（原样显示内部 ID） | 内部状态 | 策略名称；原始 ID 诊断区 |
| pages/HistoryPage.tsx:279 | 模拟记账时间不是券商真实成交时间。 | 术语；写给开发者的话 | 模拟成交，不是真实成交。 |
| pages/HistoryPage.tsx:280 | 点击一行查看费用拆分、订单与执行假设。 | 写给开发者的话 | 点击一行查看费用与订单详情。 |
| pages/HistoryPage.tsx:327 | 搜索订单（aria-label） | —（合规） | 保留 |
| pages/HistoryPage.tsx:328 | 搜索证券、策略、订单号或原因（placeholder） | 写给开发者的话（"原因"字段） | 搜索证券、策略或订单 |
| pages/HistoryPage.tsx:334 | 订单状态筛选（aria-label） | —（合规） | 保留 |
| pages/HistoryPage.tsx:339 | 全部状态 | —（合规） | 全部状态 |
| pages/HistoryPage.tsx:344 | {String(filtered.length)} / {String(orders.length)} 笔 | 数量词 | {N} / {M} 笔 |
| pages/HistoryPage.tsx:350 | 尚无模拟订单 / 没有匹配的订单 | 术语 | 还没有模拟订单 / 没有匹配的订单 |
| pages/HistoryPage.tsx:353 | 此报告没有提交过订单。页面不会生成占位委托。 | 写给开发者的话 | 还没有提交过模拟订单。 |
| pages/HistoryPage.tsx:362 | 订单 / 源日 | 术语 | 订单 / 数据日期 |
| pages/HistoryPage.tsx:364 | 委托 | 术语 | 委托数量 |
| pages/HistoryPage.tsx:365 | 已确认 / 剩余 | 术语 | 已确认成交 / 剩余数量 |
| pages/HistoryPage.tsx:368 | 原始原因 | 内部状态；中英混用 | 原因 |
| pages/HistoryPage.tsx:384 | #{order_id} | 内部状态 | 移到诊断信息 |
| pages/HistoryPage.tsx:390 | order.side === 'Buy' ? '买入' : '卖出' | 内部状态（未知方向会显示为卖出） | 买入 / 卖出 / 方向未知 |
| pages/HistoryPage.tsx:398 | {order.reason}（"原始原因"列直出后端文本，title 同） | 内部状态；中英混用 | 一句话原因；原始值进诊断 |
| pages/HistoryPage.tsx:405 | 委托意图不等于实际成交；原始 reason 不做前端改写。 | 写给开发者的话；中英混用 | 委托不等于成交。 |
| pages/HistoryPage.tsx:430 | 报告摘要 | 术语 | 账户摘要 |
| pages/HistoryPage.tsx:431 | 有缺失估值 / 逐日完整 | 术语 | 数据有缺失 / 数据完整 |
| pages/HistoryPage.tsx:436 | 报告区间 | 术语 | 数据区间 |
| pages/HistoryPage.tsx:440 | 报告日 | 前后矛盾 | 数据日数 |
| pages/HistoryPage.tsx:444 | 有效 / 缺失估值 | 术语 | 正常 / 缺失天数 |
| pages/HistoryPage.tsx:448 | 外部净流入 | 术语 | 资金转入转出 |
| pages/HistoryPage.tsx:452 | 初始净值 | 术语 | 初始资金 |
| pages/HistoryPage.tsx:456 | 累计模拟费用 | 前后矛盾 | 累计费用 |
| pages/HistoryPage.tsx:465 | 没有逐日记录 / 报告没有可展示的逐日字段。 | 写给开发者的话 | 还没有每日记录 |
| pages/HistoryPage.tsx:468 | 账户逐日核对（表格 caption） | 术语 | 账户每日账本 |
| pages/HistoryPage.tsx:471 | 源日期 | 前后矛盾 | 数据日期 |
| pages/HistoryPage.tsx:474 | 隐含持仓 | 术语 | 持仓市值 |
| pages/HistoryPage.tsx:477 | 估值状态 | 术语 | 数据状态 |
| pages/HistoryPage.tsx:513 | 估值缺失 | 术语 | 数据缺失 |
| pages/HistoryPage.tsx:522 | 隐含持仓 = 账户资产 − 现金 | 术语；写给开发者的话 | 持仓市值 = 账户资产 − 现金 |
| pages/HistoryPage.tsx:523 | 最新源日 | 术语 | 最新数据日期 |
| pages/HistoryPage.tsx:554 | 冻结部署 | 术语 | 策略版本 |
| pages/HistoryPage.tsx:555 | {String(strategies.length)} 条 | 数量词 | {N} 个 |
| pages/HistoryPage.tsx:561 | 没有策略记录 | 术语 | 还没有策略版本记录 |
| pages/HistoryPage.tsx:565 | 策略档案（表格 caption） | 术语 | 策略版本 |
| pages/HistoryPage.tsx:568 | 策略 / 所属组 / 冻结版本 / 状态 / 独立收益 / 独立回撤 / 不可用原因（568–574） | 术语 | 策略 / 分组 / 版本 / 状态 / 收益 / 回撤 / 不可用原因 |
| pages/HistoryPage.tsx:592 | {record.deployment.deployment_id}（原样显示） | 内部状态 | 移到诊断信息 |
| pages/HistoryPage.tsx:596 | record.status === 'snapshot_record_only' ? '快照记录' : 'Paper 假设记录' | 术语；内部状态（所有其他状态被压成一句） | 按真实状态显示（见 §4.5），仅记录/模拟标记放诊断 |
| pages/HistoryPage.tsx:599 | {record.unavailable_reason}（原样显示） | 内部状态 | 一句话原因；原始值进诊断 |
| pages/HistoryPage.tsx:633 | 独立研究结果不可用 | 术语 | 研究报告读取失败 |
| pages/HistoryPage.tsx:636 | 重新读取 | 重复 | 重试 |
| pages/HistoryPage.tsx:647 | 尚未配置独立研究结果 | 术语 | 还没有研究报告 |
| pages/HistoryPage.tsx:648 | 仅展示独立评估报告，不计入账户资产。 | 写给开发者的话 | 研究报告不计入账户资产。 |
| pages/HistoryPage.tsx:651 | {research.data?.status ?? 'not_configured'}（当前状态） | 内部状态（直接显示 not_configured） | 删除，或改为统一 5 态 |
| pages/HistoryPage.tsx:661 | 独立研究结果 | 术语 | 研究报告 |
| pages/HistoryPage.tsx:662 | 已保存研究档案（兜底） | 术语 | 已保存的研究报告 |
| pages/HistoryPage.tsx:663 | 不计入账户 NAV | 术语；中英混用 | 不计入账户资产 |
| pages/HistoryPage.tsx:667 | 研究证据：{原样值} | 内部状态 | 移到诊断信息 |
| pages/HistoryPage.tsx:668 | 工程：{result.engineering \|\| '未提供'} | 内部状态；写给开发者的话 | 删除或移到诊断信息 |
| pages/HistoryPage.tsx:670 | 独立验收：{原样值 / 见原报告} | 术语；内部状态 | 独立验证：通过 / 未通过 / 未提供 |
| pages/HistoryPage.tsx:678 | 历史研究范围未提供 · 目标长窗口存在数据阻断 · 区段状态见原研究报告 | 写给开发者的话 | 数据范围：…（一句人话） |
| pages/HistoryPage.tsx:688 | 区段 / 日期 / 交易日 / 净变化 / 模拟成交 / 缺估值日（688–693） | 术语 | 时段 / 日期 / 交易日 / 净变化 / 模拟成交 / 缺失数据日 |
| pages/HistoryPage.tsx:713 | 这是独立研究档案，不能作为当前账户资金、持续前向表现或已获准入的证明。 | 术语；写给开发者的话 | 研究报告仅供参考，不代表账户资金或未来收益。 |
| pages/HistoryPage.tsx:718 | 读取已保存研究结论，不重新评价策略，也不发起模型调用。 | 写给开发者的话 | 显示已保存的研究结论。 |
| components/domain/WorkspaceStudies.tsx:15 | 本地研究与样本外报告 | 术语 | 研究报告 |
| components/domain/WorkspaceStudies.tsx:15 | 读取资料 | 术语；重复 | 刷新 |
| components/domain/WorkspaceStudies.tsx:16 | 研究保留原任务与来源；历史和合成结果均不计入当前 Paper 账户。 | 术语；中英混用 | 历史与合成数据的研究结果不计入模拟账户。 |
| components/domain/WorkspaceStudies.tsx:18 | 正在读取本地资料。 | 术语 | 正在读取研究报告… |
| components/domain/WorkspaceStudies.tsx:19 | 全市场 EOD 采集 | 术语；中英混用 | 全市场行情采集 |
| components/domain/WorkspaceStudies.tsx:22 | 采集状态：{READY→数据覆盖合格 / NOT_CONFIGURED→未配置 / MARKET_CLOSED→交易所休市 / 其他→等待或受阻（见详情）} | 内部状态 | 统一 5 态：正常 / 进行中 / 需要处理 / 出错 / 未设置 |
| components/domain/WorkspaceStudies.tsx:22 | 最后成功日期：{原始 YYYYMMDD 或 尚无} | 内部状态 | 最近更新：{YYYY-MM-DD} |
| components/domain/WorkspaceStudies.tsx:24 | 证券目录范围：已核验 / 未核验，研究准入受阻；行情覆盖率按已知目录计算。 | 写给开发者的话 | 数据完整性：正常 / 需要处理（诊断信息保留口径） |
| components/domain/WorkspaceStudies.tsx:25 | 源日 {原始值} · 目录内有行情 N/M；行情与已确认全天停牌合计 N/M（x%） | 术语；写给开发者的话 | 数据日期 {YYYY-MM-DD} · 行情覆盖 N/M（诊断信息保留明细） |
| components/domain/WorkspaceStudies.tsx:26 | 研究选样合格 N/M · 实际可用时间 {时间} | 术语 | 可用于研究的证券 N/M · 数据取得时间 {时间} |
| components/domain/WorkspaceStudies.tsx:28 | 缺口日期 N；BSE 保留覆盖记录，尚不支持研究准入。读取资料只查询本地数据。 | 中英混用；写给开发者的话 | 缺失数据 N 天（诊断信息保留明细） |
| components/domain/WorkspaceStudies.tsx:31 | 尚无已配置研究资料；在本机启动配置中选择原研究批次和报告。 | 术语；写给开发者的话 | 还没有研究报告。 |
| components/domain/WorkspaceStudies.tsx:32 | {s.kind} · {s.name}（kind 为原始枚举） | 内部状态 | 报告类型中文名（诊断信息保留原始值） |
| components/domain/WorkspaceStudies.tsx:33 | 原任务 #{task_id} | 内部状态 | 移到诊断信息 |
| components/domain/WorkspaceStudies.tsx:34 | 来源核对受阻 · 仅供研究 | 写给开发者的话 | 仅用于研究 |
| components/domain/WorkspaceStudies.tsx:35 | 输入最近实际取得时间 / 合成输入时点 | 写给开发者的话 | 数据取得时间 |
| components/domain/WorkspaceStudies.tsx:36 | 未校准的日风险代理 · 会话 RMS x% · Naive x% · EWMA x% · 方向未知；这些数值不是预期收益或 VaR。 | 术语；中英混用；写给开发者的话 | 风险估计（非收益预测）；明细进诊断信息 |
| components/domain/WorkspaceStudies.tsx:37 | 研究现金权重 / 研究权重 · 合成组合假设，不是当前持仓或交易许可。 | 术语；写给开发者的话 | 移到诊断信息 |
| components/domain/WorkspaceStudies.tsx:39 | 样本外评价 · {name}；{stateLabel}；证据不足以授予交易资格。 | 术语 | 研究报告评价 |
| components/domain/WorkspaceStudies.tsx:40 | 开发段 / 验证段 / 测试段 · 样本计分，覆盖 x% · 日风险代理误差，收益率比值单位 · MAE / RMSE | 写给开发者的话；中英混用 | 明细移诊断信息 |
| components/domain/WorkspaceStudies.tsx:42 | 原 Registry 候选 | 内部状态；中英混用 | 候选策略记录（诊断信息） |
| components/domain/WorkspaceStudies.tsx:11 | 技术详情与完整来源 / 复制详情 | 术语；重复 | 诊断信息 / 复制诊断信息 |
| components/domain/DayDrawer.tsx:30 | 逐日核对 | 术语 | 每日账本 |
| components/domain/DayDrawer.tsx:32 | 估值缺失 / 有效估值 | 术语 | 数据缺失 / 数据正常 |
| components/domain/DayDrawer.tsx:34 | 当日账户 | 术语 | 当日账户 |
| components/domain/DayDrawer.tsx:37 | 账户净值 | 术语；前后矛盾 | 账户资产 |
| components/domain/DayDrawer.tsx:39 | 隐含持仓市值 | 术语 | 持仓市值 |
| components/domain/DayDrawer.tsx:42 | 较上一源日 | 术语 | 较上一数据日 |
| components/domain/DayDrawer.tsx:43 | 估值状态：{valuation_error 原样值 或 有效} | 内部状态 | 数据状态：正常 / 缺失（原始值进诊断） |
| components/domain/DayDrawer.tsx:47 | 隐含持仓市值 = 报告中的 NAV − 现金，仅用于核对六报告内部一致性，不是独立行情估值。 | 术语；写给开发者的话 | 持仓市值 = 账户资产 − 现金。 |
| components/domain/DayDrawer.tsx:53 | 本页只读取已发布六报告中的逐日字段。当前 API 没有提供逐日外部资金流和逐日费用拆分，因此"较上一源日"不声称已扣除资金流，也不替代完整 TWR。 | 术语；写给开发者的话；中英混用 | 删除；必要说明进诊断信息 |
| components/domain/DayDrawer.tsx:55 | 缺失估值保留为 null，不用前后日期插值或零值填补。 | 写给开发者的话；中英混用 | 数据缺失时保持空白，不做推算。 |
| components/domain/OrderDrawer.tsx:35 | 模拟订单 | —（合规） | 保留 |
| components/domain/OrderDrawer.tsx:36 | 订单 #{order_id} | 内部状态 | 订单详情（编号放小字/诊断） |
| components/domain/OrderDrawer.tsx:49 | 证券 | —（合规） | 保留 |
| components/domain/OrderDrawer.tsx:55 | 状态：{中文} / {原始枚举} | 中英混用；内部状态 | 仅显示中文状态 |
| components/domain/OrderDrawer.tsx:60 | 原始原因 | 内部状态；中英混用 | 原因 |
| components/domain/OrderDrawer.tsx:61 | {order.reason}（原样后端文本） | 内部状态 | 一句话原因；原始值进诊断 |
| components/domain/OrderDrawer.tsx:62 | 原始 reason 按服务端文本展示，不由前端改写或归类。 | 写给开发者的话；中英混用 | 删除 |
| components/domain/OrderDrawer.tsx:65 | 关联成交 | —（合规） | 保留 |
| components/domain/OrderDrawer.tsx:94 | 部署记录 | 术语 | 策略记录（高级） |
| components/domain/OrderDrawer.tsx:97 | 所属组 / 策略 / 冻结版本 / 部署标识（97–100） | 术语 | 移到诊断信息 |
| components/domain/StrategyDrawer.tsx:11 | return status（未识别状态原样显示） | 内部状态 | 统一 5 态 + 状态未知 |
| components/domain/StrategyDrawer.tsx:40 | 策略档案 | 术语 | 策略版本 |
| components/domain/StrategyDrawer.tsx:49 | 记录状态 | 术语 | 状态 |
| components/domain/StrategyDrawer.tsx:53 | 独立收益 | 术语 | 收益 |
| components/domain/StrategyDrawer.tsx:54 | 独立回撤 | 术语 | 回撤 |
| components/domain/StrategyDrawer.tsx:55 | 不可用原因 | 术语 | 不可用原因 |
| components/domain/StrategyDrawer.tsx:59 | 这是已发布报告中的冻结部署记录，不代表策略进程正在运行，也不构成独立策略绩效或策略资格。 | 术语；写给开发者的话 | 仅记录，不代表正在运行或未来收益。 |
| components/domain/StrategyDrawer.tsx:74 | 关联记录 | —（合规） | 保留 |
| components/domain/StrategyDrawer.tsx:77 | 模拟成交 {N} 笔 / 模拟订单 {N} 笔 | 数量词 | 模拟成交 {N} 笔 / 模拟订单 {N} 笔 |
### 3.4 通知

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| pages/NotificationsPage.tsx:60 | 通知 | —（合规） | 保留 |
| pages/NotificationsPage.tsx:64 | 任务通知 | 术语 | 研究任务 |
| pages/NotificationsPage.tsx:67 | 标为已读 | —（合规） | 保留 |
| pages/NotificationsPage.tsx:74 | 5 秒后标为已读 | 写给开发者的话；重复 | 即将标为已读（提供撤销） |
| pages/NotificationsPage.tsx:84 | 撤销 | —（合规） | 保留 |
| pages/NotificationsPage.tsx:89 | 正在读取记录… | —（可保留） | 正在读取通知… |
| pages/NotificationsPage.tsx:91 | 还没有通知 / 研究任务结束或出错时会出现在这里。 | 术语 | 还没有通知 / AI 研究完成或失败时会显示在这里。 |
| pages/NotificationsPage.tsx:96 | 任务 #{id} · {stateLabel} | 内部状态 | AI 研究 · 状态（编号进诊断） |
| pages/NotificationsPage.tsx:97 | 已读 / 未读 | —（合规） | 保留 |
| pages/NotificationsPage.tsx:96 | （缺失）notice.reason 从未渲染 | 内部状态（缺失） | 通知必须附一句话原因（失败/未确认时） |

### 3.5 AI 研究（#agents）

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| pages/AgentPage.tsx:94 | Agent 管理 | 术语；中英混用 | AI 研究 |
| pages/AgentPage.tsx:99 | 更新于 {时间}（与"读取于/检查于"并存） | 前后矛盾 | 更新于 {时间} |
| pages/AgentPage.tsx:110 | 正在读取本机研究服务 | 术语 | 正在读取 AI 研究状态 |
| pages/AgentPage.tsx:129 | 研究服务不可用 | 术语 | AI 研究服务当前不可用 |
| pages/AgentPage.tsx:130 | 本机研究服务未返回状态。请确认 Agent 已启动并配置。 | 中英混用；写给开发者的话 | 无法读取 AI 研究状态，请确认后台任务已启动。 |
| pages/AgentPage.tsx:134 | 重新读取 | 重复 | 重试 |
| pages/AgentPage.tsx:148 | 尚未配置默认研究模型，不能创建任务。 | 术语 | 尚未设置默认 AI 模型，暂时不能新建研究。 |
| pages/AgentPage.tsx:150 | 请使用下方冻结研究入口，沿用原 Worker、预算与来源绑定。 | 内部状态；前后矛盾（页面下方无此入口） | 删除；改为真实存在的入口说明 |
| pages/AgentPage.tsx:152 | 日/月预算未配置，付费研究已被阻止。 | 术语；前后矛盾（未配置/已阻止表述混用） | 尚未设置研究预算，付费研究已暂停。 |
| pages/AgentPage.tsx:160 | 最近一次读取失败，显示上次成功读取的状态 | 重复；前后矛盾 | 更新失败，以下为上次成功的数据 |
| pages/AgentPage.tsx:163 | 重新读取 | 重复 | 重试 |
| pages/AgentPage.tsx:172 | 研究运行状态 | 术语 | AI 研究状态 |
| pages/AgentPage.tsx:175 | 已暂停 / 研究中 {N} / 等待执行 | 术语；前后矛盾（"研究中/运行中"） | 已暂停 / 进行中 {N} / 等待中 |
| pages/AgentPage.tsx:182 | 已暂停接收新任务 / 等待研究任务 | 术语 | 已暂停，不会接收新任务 / 等待新的研究任务 |
| pages/AgentPage.tsx:191 | 操作失败 | 前后矛盾（无原因） | 操作未完成：{原因} |
| pages/AgentPage.tsx:192 | 已恢复研究 / 已暂停研究 | 术语 | 已恢复自动研究 / 已暂停自动研究 |
| pages/AgentPage.tsx:195 | 恢复研究 / 暂停 | —（可保留） | 恢复 / 暂停 |
| pages/AgentPage.tsx:201 | Worker 报告错误 | 中英混用；内部状态 | 后台任务报告错误 |
| pages/AgentPage.tsx:206 | 默认模型 | 术语 | 默认 AI 模型 |
| pages/AgentPage.tsx:207 | 研究定位：{原标题为原始 qualification 枚举}；值兜底"资格待核对" | 内部状态；术语 | 研究用途：探索性研究；未知显示"状态未知"（原始值进诊断） |
| pages/AgentPage.tsx:208 | 模型切换：仅你手动选择 | 写给开发者的话 | 模型切换：仅在手动切换时生效 |
| pages/AgentPage.tsx:214 | EOD 自动研究 | 术语；中英混用 | 收盘后自动研究 |
| pages/AgentPage.tsx:217 | 已启用 / 已停用 | 术语 | 已开启 / 已关闭 |
| pages/AgentPage.tsx:221 | EOD 自动研究开关（aria-label） | 术语；中英混用 | 收盘后自动研究开关 |
| pages/AgentPage.tsx:224 | EOD 设置失败 | 术语；中英混用 | 收盘后自动研究设置失败 |
| pages/AgentPage.tsx:225 | 已启用 EOD 自动研究 / 已关闭 EOD 自动研究 | 术语；中英混用 | 已开启收盘后自动研究 / 已关闭收盘后自动研究 |
| pages/AgentPage.tsx:231 | 最近记录 | —（可保留） | 最近一次 |
| pages/AgentPage.tsx:234 | 源日 {原始 YYYY-MM-DD} | 术语 | 数据日期 {格式化为 YYYY-MM-DD} |
| pages/AgentPage.tsx:236 | EOD 最近记录状态：{已入队/研究中/已完成/…} 或"状态待核对" | 内部状态；术语 | 统一 5 态 + 一句话原因（见 §4.2） |
| pages/AgentPage.tsx:241 | 尚无 EOD 派发记录 · 已记录跳过 {N} 次 | 术语；中英混用 | 还没有自动研究记录（已跳过 {N} 次） |
| pages/AgentPage.tsx:276 | 新建研究任务 | —（可保留） | 新建 AI 研究 |
| pages/AgentPage.tsx:277 | 任务会进入持久队列，并受日/月硬预算与新任务配置约束。 | 写给开发者的话；术语 | 新任务会排队执行，并受每日/每月预算限制。 |
| pages/AgentPage.tsx:287 | 研究任务已排队；任务 ID #{id}。列表读取不会调用模型。 | 写给开发者的话；内部状态 | AI 研究已排队（编号进诊断） |
| pages/AgentPage.tsx:308 | 研究预算 | —（可保留） | AI 研究预算 |
| pages/AgentPage.tsx:309 | {configured ? budget.currency : '未配置'} | 内部状态 | 金额统一 ¥ 显示；未设置时显示"未设置" |
| pages/AgentPage.tsx:314 | 日 / 月预算未配置，付费研究已阻止 | 术语；前后矛盾 | 尚未设置每日/每月预算，付费研究已暂停。 |
| pages/AgentPage.tsx:315 | 额度只由本机 Owner 可信设置维护。Web 不提供加额或清锁；预算耗尽只暂停研究，不影响风险与账本。 | 术语；写给开发者的话 | 预算由本机设置维护，页面不能修改；预算用完只会暂停研究，不影响模拟账户。 |
| pages/AgentPage.tsx:317 | 预算未配置时仍可查看已保存任务，但不会发起新的付费调用。 | 写给开发者的话 | 未设置预算时仍可查看历史任务，但不会产生付费调用。 |
| pages/AgentPage.tsx:323 | 今日 / 本月 | —（可保留） | 今日 / 本月 |
| pages/AgentPage.tsx:330 | 已占用（含预留） | 术语 | 已使用（含冻结） |
| pages/AgentPage.tsx:331 | 已核对 | 术语 | 已结算 |
| pages/AgentPage.tsx:348 | 未结清预留 | 术语 | 未结算冻结 |
| pages/AgentPage.tsx:349 | 调用尝试 | 术语 | 调用次数 |
| pages/AgentPage.tsx:350 | 输入 / 输出 Token | 中英混用；内部状态 | 输入 / 输出字数（诊断信息保留 Token） |
| pages/AgentPage.tsx:351 | 收到用量估算 | 术语 | 预估费用 |
| pages/AgentPage.tsx:355 | 正在更新 EOD 设置（sr-only） | 术语；中英混用 | 正在更新收盘后自动研究设置 |
| pages/AgentPage.tsx:368 | 模型与自动研究 | 术语 | AI 模型与自动研究 |
| pages/AgentPage.tsx:369 | 备用模型仅保存 / 备用仅保存 | 重复；内部状态 | 备用模型（仅手动切换） |
| pages/AgentPage.tsx:373 | 默认模型 | 术语 | 默认 AI 模型 |
| pages/AgentPage.tsx:382 | 默认模型切换失败 | 术语 | 默认 AI 模型切换失败 |
| pages/AgentPage.tsx:383 | 默认模型已切换；仅影响之后创建的新任务。 | —（可保留） | 默认 AI 模型已切换；仅影响之后新建的任务。 |
| pages/AgentPage.tsx:386 | 未配置（下拉占位） | 术语 | 未设置 |
| pages/AgentPage.tsx:392 | 备用配置 / 只在手动切换时使用。 | 术语；写给开发者的话 | 备用模型 / 仅在手动切换时使用。 |
| pages/AgentPage.tsx:401 | 备用配置保存失败 | 术语 | 备用模型保存失败 |
| pages/AgentPage.tsx:402 | 备用配置已保存；备用配置不会自动切换。 | 重复；前后矛盾（"配置/模型"） | 备用模型已保存；不会自动切换。 |
| pages/AgentPage.tsx:405 | 未选择（下拉占位） | —（可保留） | 未选择 |
| pages/AgentPage.tsx:412 | 当前默认配置 | 术语 | 当前默认 AI 模型 |
| pages/AgentPage.tsx:417 | 本地合成 / 云 API | 中英混用 | 本地模拟 / 云端 AI（诊断信息保留类型） |
| pages/AgentPage.tsx:419 | 最近 Provider 观察：{原始原因} | 中英混用；内部状态 | 删除或移到诊断信息 |
| pages/AgentPage.tsx:423 | 未配置模型 | 术语 | 未设置模型 |
| pages/AgentPage.tsx:430 | 尚未配置研究模型 | 术语 | 尚未设置 AI 模型 |
| pages/AgentPage.tsx:431 | 模型、授权、费率与 HTTPS 端点只由本机可信设置维护；Web 不提供配置写入。 | 写给开发者的话；中英混用 | 模型与费用由本机设置维护，页面不提供修改。 |
| pages/AgentPage.tsx:438 | 配置 / 类型 / 模型 / 费率版本 | 术语；内部状态 | AI 模型 / 类型 / 费用版本（表头保留中文；明细进诊断） |
| pages/AgentPage.tsx:447 | 本地合成 / 云 API（重复出现） | 中英混用 | 本地模拟 / 云端 AI |
| pages/AgentPage.tsx:458 | 调用与模型用量 | 内部状态 | 用量明细（诊断信息） |
| pages/AgentPage.tsx:463 | 尚无已记录用量。 | —（可保留） | 还没有用量记录。 |
| pages/AgentPage.tsx:468 | 配置 / 调用 / 输入 / 输出 Token / 用量估算 | 内部状态；中英混用 | 诊断信息 |
| pages/AgentPage.tsx:532 | 研究任务 | 术语 | AI 研究任务 |
| pages/AgentPage.tsx:536 | 刷新研究任务（aria-label） | —（可保留） | 刷新 AI 研究任务 |
| pages/AgentPage.tsx:542 | 新建任务 | —（可保留） | 新建研究 |
| pages/AgentPage.tsx:554 | 搜索研究任务（aria-label） | —（可保留） | 搜索 AI 研究任务 |
| pages/AgentPage.tsx:555 | 搜索任务、模型或结论（placeholder） | —（可保留） | 搜索任务、模型或结论 |
| pages/AgentPage.tsx:560 | 任务状态筛选（aria-label） | —（可保留） | 研究状态筛选 |
| pages/AgentPage.tsx:561 | 全部状态 | —（可保留） | 全部状态 |
| pages/AgentPage.tsx:562 | 进行中 | —（可保留） | 进行中 |
| pages/AgentPage.tsx:563 | 已完成 | —（可保留） | 已完成 |
| pages/AgentPage.tsx:564 | 异常 / 费用不确定 | 术语；内部状态 | 出错 / 结果未确认（拆成两项） |
| pages/AgentPage.tsx:565 | 已取消 | —（可保留） | 已取消 |
| pages/AgentPage.tsx:567 | {String(filtered.length)} / {String(agent.tasks.length)} 条 | 数量词 | {N} / {M} 个 |
| pages/AgentPage.tsx:568 | 读取中… | —（可保留） | 正在读取… |
| pages/AgentPage.tsx:575 | 尚无研究任务 / 没有匹配的任务 | 术语 | 还没有 AI 研究任务 / 没有匹配的任务 |
| pages/AgentPage.tsx:578 | 从"新建任务"开始；所有任务受日/月硬预算约束。 | 术语；写给开发者的话 | 新建研究后，进度与结论会显示在这里；任务受每日/每月预算限制。 |
| pages/AgentPage.tsx:583 | 新建研究任务 | 术语 | 新建 AI 研究 |
| pages/AgentPage.tsx:589 | 研究任务（表格 caption） | 术语 | AI 研究任务 |
| pages/AgentPage.tsx:592 | 任务 / 模型 | 术语 | 任务 / AI 模型 |
| pages/AgentPage.tsx:595 | 费用 / 预留 | 术语 | 费用 / 冻结 |
| pages/AgentPage.tsx:616 | #{task.id} · {task.provider_id}（原样显示内部 ID） | 内部状态 | 移到诊断信息 |
| pages/AgentPage.tsx:623 | 未知费用按最大预留计（title） | 写给开发者的话 | 费用按最高可能值显示 |
| pages/AgentPage.tsx:627 | task.conclusion \|\| humanReason(task.reason) \|\| '等待执行' | 前后矛盾（失败任务无原因时显示"等待执行"） | 按真实状态显示；失败且无原因时"失败，原因未记录" |
| pages/AgentPage.tsx:640 | 取消失败 | 前后矛盾（无原因） | 取消失败：{原因} |
| pages/AgentPage.tsx:641 | 已申请取消；运行中的请求不会被撤销；请查看最终状态。 | 术语 | 正在取消；已发出的云端请求无法撤回，请稍后查看最终状态。 |
| pages/AgentPage.tsx:656 | 重试失败 | 前后矛盾（无原因） | 重试失败：{原因} |
| pages/AgentPage.tsx:657 | 任务已重新排队 | —（可保留） | 任务已重新排队 |
| pages/AgentPage.tsx:660 | 安全重试 | 术语 | 重试 |
| pages/AgentPage.tsx:675 | 每页最多 20 条 · 读取于 {时间} | 数量词；前后矛盾 | 每页最多 20 个 · 更新于 {时间} |
| pages/AgentPage.tsx:679 | 最新 / 更早 | —（可保留） | 最新 / 更早 |
| pages/AgentPage.tsx:702 | 已保存研究任务 #{id} | 内部状态 | 研究任务 |
| pages/AgentPage.tsx:703 | 读取任务详情 | —（可保留） | 正在读取任务详情 |
| pages/AgentPage.tsx:707 | {detail.provider_id}（徽标直出） | 内部状态 | 移到诊断信息 |
| pages/AgentPage.tsx:713 | 刷新详情 | —（可保留） | 刷新详情 |
| pages/AgentPage.tsx:730 | 安全重试 | 术语 | 重试 |
| pages/AgentPage.tsx:744 | 运行中的 Provider 请求不会被撤销。 | 中英混用；术语 | 已发出的云端请求无法撤回。 |
| pages/AgentPage.tsx:747 | 取消任务 | —（可保留） | 取消任务 |
| pages/AgentPage.tsx:754 | 详情刷新失败，显示上次读取记录 | 重复；前后矛盾 | 更新失败，以下为上次成功的数据 |
| pages/AgentPage.tsx:764 | 任务详情不可用 | 前后矛盾（无原因） | 无法读取任务详情：{原因} |
| pages/AgentPage.tsx:767 | 重新读取 | 重复 | 重试 |
| pages/AgentPage.tsx:772 | 任务详情尚未加载。 | —（可保留） | 任务详情尚未加载。 |
| pages/AgentPage.tsx:783 | 请求 | 术语 | 任务设置 |
| pages/AgentPage.tsx:785 | 研究目标 / 研究范围 | —（可保留） | 保留 |
| pages/AgentPage.tsx:787 | 请求区间：{原始 start_day} — {原始 end_day} | 前后矛盾；内部状态 | 研究区间：{YYYY-MM-DD} — {YYYY-MM-DD} |
| pages/AgentPage.tsx:788 | 单任务预算 / 未设置，仍受日/月硬上限 | 术语 | 单任务预算：¥…（未设置时仍受每日/每月预算限制） |
| pages/AgentPage.tsx:790 | 开始 / 完成 | —（可保留） | 开始 / 完成时间 |
| pages/AgentPage.tsx:791 | 取消申请 | 术语 | 取消申请时间 |
| pages/AgentPage.tsx:792 | {humanReason(detail.reason)}（未知时返回"状态或原因见技术详情"） | 内部状态 | 原因：一句话人话；完全未知时"原因未记录" |
| pages/AgentPage.tsx:797 | 冻结输入与模型 | 内部状态；术语 | 研究输入与模型（诊断信息） |
| pages/AgentPage.tsx:800 | 实际摘要源日：{原始 source_day 或"无已发布报告"} | 术语；内部状态 | 数据日期：{YYYY-MM-DD} / 无已发布数据 |
| pages/AgentPage.tsx:801 | 摘要版本：{原始 version} | 内部状态 | 移到诊断信息 |
| pages/AgentPage.tsx:802 | 原冻结来源范围 | 内部状态 | 移到诊断信息 |
| pages/AgentPage.tsx:803 | 模型 / 配置：{provider_id} {provider_hash 前 16 位} | 内部状态 | 移到诊断信息 |
| pages/AgentPage.tsx:805 | 详情读取只读取本地已保存记录，不调用模型。 | 写给开发者的话 | 删除 |
| pages/AgentPage.tsx:810 | 研究结果 | —（可保留） | 研究报告 |
| pages/AgentPage.tsx:813 | FAKE / SYNTHETIC / 云端文本研究 | 中英混用；内部状态 | 模拟测试数据 / 云端 AI 研究 |
| pages/AgentPage.tsx:816 | {formatDateTime(generated_at)}（徽标） | —（可保留） | 保留（统一北京时间） |
| pages/AgentPage.tsx:817 | RESEARCH_QUALIFICATION_LABELS[result.qualification] ?? result.qualification | 内部状态 | 诊断信息保留原始值 |
| pages/AgentPage.tsx:820 | 可核查假设 | —（可保留） | 研究假设 |
| pages/AgentPage.tsx:824 | 关键依据 / 反证 / 风险 / 下一步 | —（可保留） | 保留 |
| pages/AgentPage.tsx:835 | 限制 | —（可保留） | 说明 |
| pages/AgentPage.tsx:838 | 已保存研究产物 / 本地风险或结构化研究输出；模型自由文本仅为未核验假设。 | 写给开发者的话 | 研究报告（未验证内容仅供参考） |
| pages/AgentPage.tsx:842 | 尚无已保存研究输出。此详情不会发起推理。 / 已保存结构化研究产物，见下方详情。 | 写给开发者的话 | 暂无已保存的研究结果。 |
| pages/AgentPage.tsx:847 | 费用与调用记录 | 内部状态 | 费用明细（诊断信息） |
| pages/AgentPage.tsx:848 | 已保存本地风险或结构化研究输出；模型自由文本仅为未核验假设。 | 写给开发者的话 | 删除 |
| pages/AgentPage.tsx:849 | 云端收到用量仍不是最终账单；未知结果保留最大预留，不自动重发。 | 写给开发者的话 | 云端用量不是最终账单；未确认的费用会暂时冻结。 |
| pages/AgentPage.tsx:851 | 尚未预留或发出调用。 | 内部状态 | 还没有发起云端调用。 |
| pages/AgentPage.tsx:858 | 状态 / 最大 / 已核对 / 估算 / 费率版本 / 周期 / 原因（858–862） | 内部状态 | 诊断信息（保留原始字段） |
| pages/AgentPage.tsx:898 | 提交只入队；取消不撤销已提交的计费请求。 | 写给开发者的话；术语 | 提交后任务会排队；已发出的云端请求无法撤回。 |
| pages/AgentPage.tsx:909 | 提交研究任务 | —（可保留） | 提交 AI 研究任务 |
| pages/AgentPage.tsx:929 | 当前已发布的 Paper 摘要（默认研究范围） | 术语；中英混用 | 当前已发布的数据摘要 |
| pages/AgentPage.tsx:943 | 请输入任务名称。 / 任务名称不能超过 40 个字符。 | —（合规） | 保留 |
| pages/AgentPage.tsx:945 | 请写明研究目标与反证条件。/ 研究目标不能超过 650 个字符。 | —（可保留） | 请写明研究目标与验证条件。 |
| pages/AgentPage.tsx:947 | 请输入研究范围。/ 研究范围不能超过 100 个字符。 | —（合规） | 保留 |
| pages/AgentPage.tsx:951 | 开始日期格式无效。 / 结束日期格式无效。 / 结束日期不能早于开始日期。 | —（合规） | 保留 |
| pages/AgentPage.tsx:954 | 单任务预算必须为正整数字符串。 | 术语 | 单任务预算必须是正整数。 |
| pages/AgentPage.tsx:955 | 单任务预算必须大于 0。 | —（合规） | 保留 |
| pages/AgentPage.tsx:980 | 当前不能创建任务 | 术语 | 当前无法新建研究 |
| pages/AgentPage.tsx:983 | 任务名称 / 最多 40 个字符。 | —（合规） | 保留 |
| pages/AgentPage.tsx:989 | 例如：成本假设复核（placeholder） | —（可保留） | 保留 |
| pages/AgentPage.tsx:995 | 研究目标 / 写明希望验证的问题、依据与反证条件。 | —（可保留） | 研究目标 / 写明要验证的问题与依据。 |
| pages/AgentPage.tsx:1002 | 例如：核查成本与缺估值约束会如何改变表面收益，并说明在什么证据下应放弃该假设。 | 写给开发者的话 | 例如：检查费用和数据缺失会如何影响收益。 |
| pages/AgentPage.tsx:1007 | 证券 / 研究范围 / 只允许提交到已发布的摘要与本次课题。 | 术语；写给开发者的话 | 研究范围 / 研究范围限于已发布的数据摘要。 |
| pages/AgentPage.tsx:1017 | 单任务预算 micro（可选）/ 留空仍受日/月硬上限。 | 内部状态；术语 | 单任务预算（可选，元）/ 留空时仍受每日/每月预算限制。 |
| pages/AgentPage.tsx:1024 | 例如 50000（placeholder，单位 micro） | 内部状态 | 例如 0.05（按"元"输入，需同步改提交换算） |
| pages/AgentPage.tsx:1029 | 开始日期 / 研究请求区间，不保证已有该区间完整数据。 | 写给开发者的话 | 开始日期 |
| pages/AgentPage.tsx:1039 | 结束日期 / 当前摘要源日只作为默认值。 | 术语 | 结束日期 |
| pages/AgentPage.tsx:1050 | 费用与取消 | —（可保留） | 费用与取消 |
| pages/AgentPage.tsx:1051 | 创建任务可能产生费用；取消运行中的任务不会撤销已提交的 Provider 请求。未知费用会保留最大预留，系统不会自动重发。 | 术语；写给开发者的话 | 创建任务可能产生费用；已发出的云端请求无法撤回；未确认费用会暂时冻结。 |
| pages/AgentPage.tsx:1054 | 提交失败 / · {formCode} | 内部状态 | 提交失败：{原因}；原始代码进诊断 |

### 3.6 设置

#### 3.6.1 外观 / 数据连接 / 关于（SettingsPage）

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| pages/SettingsPage.tsx:33 | 跟随系统 / 根据系统深浅色自动切换 | —（合规） | 保留 |
| pages/SettingsPage.tsx:34 | 浅色 / 适合明亮环境 | —（合规） | 保留 |
| pages/SettingsPage.tsx:35 | 深色 / 适合低光环境 | —（合规） | 保留 |
| pages/SettingsPage.tsx:144 | 减弱动态效果 | —（合规） | 保留 |
| pages/SettingsPage.tsx:159 | 来源、时效与完整性 | 术语 | 数据来源与更新 |
| pages/SettingsPage.tsx:160 | 历史 PIT 尚未验证；开盘流实收尚未验证。盘后 daily.open 仅支持前日冻结意图的事后 Paper 假设。 | 中英混用；写给开发者的话 | 历史数据的可用时点尚未验证；模拟成交按次日开盘价计算。 |
| pages/SettingsPage.tsx:161 | Tushare 未复权日线：价格为元、成交量为手（100 股）、金额为千元；以实际取得时间记录来源，不推断历史首次发布时间。 | 写给开发者的话；前后矛盾（"手" vs 界面"股"） | 移到诊断信息；若保留须统一数量单位 |
| pages/SettingsPage.tsx:162 | 真实数据资格清单 / 待补证据 / 状态 / 受阻 / {row.required_evidence} / {row.issue} | 内部状态；中英混用 | 移到诊断信息；状态按真实值显示而不是硬编码"受阻" |
| pages/SettingsPage.tsx:163 | 已有本地来源记录；交易资格仍受原准入判定约束。 | 写给开发者的话 | 移到诊断信息 |
| pages/SettingsPage.tsx:165 | 正在读取数据连接信息… | —（可保留） | 正在读取数据状态… |
| pages/SettingsPage.tsx:170 | 账户快照：{snapshot_id 截断} | 内部状态 | 诊断信息 |
| pages/SettingsPage.tsx:171 | 来源：{source 原样} | 内部状态 | 诊断信息 |
| pages/SettingsPage.tsx:172 | 来源版本：{source_version 原样} | 内部状态 | 诊断信息 |
| pages/SettingsPage.tsx:174 | 证据等级：{evidence_class 派生徽标} | 内部状态；术语 | 诊断信息（主界面只显示"数据正常/缺失"） |
| pages/SettingsPage.tsx:182 | 报告区间：{start} — {end} · Asia/Shanghai | 术语；中英混用 | 数据区间：{start} — {end}（北京时间） |
| pages/SettingsPage.tsx:186 | 最后有效估值：{格式化时间 或 日期} | 术语 | 最后数据更新 |
| pages/SettingsPage.tsx:189 | 发布方式：原 Paper 账本，只读事务 / 最后发布报告，更新需重启 | 术语；写给开发者的话 | 诊断信息 |
| pages/SettingsPage.tsx:190 | 行情时效：仅盘后/快照，非实时（硬编码） | 写给开发者的话 | 盘后数据，非实时 |
| pages/SettingsPage.tsx:191 | 前向账户：尚未验证前向成交（硬编码） | 内部状态（可能与实际不符） | 删除或按真实数据渲染 |
| pages/SettingsPage.tsx:193 | 未观察日历日 / 缺开盘证据段 / 未核验状态段 / 记录缺口（193–208） | 写给开发者的话 | 移到诊断信息 |
| pages/SettingsPage.tsx:214 | 技术摘要与账本尾 | 术语 | 诊断信息 |
| pages/SettingsPage.tsx:221 | snapshot_id / report_sha256 / input_sha256 / ledger_head（221–224） | 写给开发者的话 | 保留在"诊断信息"折叠区（已符合） |
| pages/SettingsPage.tsx:229 | 更换报告需重启本机服务。 | 写给开发者的话 | 切换数据需要重启后台服务。 |
| pages/SettingsPage.tsx:235 | 尚未选择 Paper 报告 / Paper 报告不可用 | 术语 | 尚未选择模拟账户数据 / 模拟账户数据不可用 |
| pages/SettingsPage.tsx:236 | 启动时通过 --report-dir 指定已发布报告目录。 | 写给开发者的话 | 请在启动设置中选择数据目录。 |
| pages/SettingsPage.tsx:248 | 前端版本 / 构建 / Paper API / 后端 / 静态资源 / 界面技术 / 本地运行 / 备份与恢复 / 最近备份 / N100 部署（248–257） | 写给开发者的话；中英混用；内部状态 | 只保留"版本 v…"与"检查更新/诊断信息"；其余移入折叠诊断区 |
| pages/SettingsPage.tsx:249 | 构建：local build / {__BUILD_SHA__} | 内部状态；中英混用 | 诊断信息 |
| pages/SettingsPage.tsx:250 | Paper API：v1 · 只读同源 | 内部状态；中英混用 | 删除 |
| pages/SettingsPage.tsx:251 | 后端：Rust stratided · 127.0.0.1 | 写给开发者的话；中英混用 | 删除 |
| pages/SettingsPage.tsx:252 | 静态资源：本地 app.js / app.css，无 CDN、无遥测 | 写给开发者的话 | 删除 |
| pages/SettingsPage.tsx:253 | 界面技术：React 19 + TypeScript + esbuild | 写给开发者的话 | 删除 |
| pages/SettingsPage.tsx:254 | 本地运行：Windows 11；按需复用 WSL2 TimesFM CPU | 写给开发者的话；中英混用 | 删除/诊断 |
| pages/SettingsPage.tsx:255 | 备份与恢复：scripts/local-backup.py；先校验与 dry-run，恢复到新目录 | 写给开发者的话；中英混用 | 删除/诊断 |
| pages/SettingsPage.tsx:256 | 最近备份：完整性已核对，共 {N} 个文件 / 尚无已核对的备份清单；在本机配置指定备份 manifest | 术语；写给开发者的话 | 最近备份：{时间/状态}（诊断保留 manifest） |
| pages/SettingsPage.tsx:257 | N100 部署：已延后，不属于 V1 完成条件 | 内部状态；写给开发者的话 | 删除 |

#### 3.6.2 AI 服务（ProviderPanel）

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| components/domain/ProviderPanel.tsx:26 | DeepSeek 官方 / OpenAI 官方 | —（专有名词允许） | 保留 |
| components/domain/ProviderPanel.tsx:63 | 密钥已保存到 Windows 凭据管理器。 | 术语；写给开发者的话 | API Key 已保存。 |
| components/domain/ProviderPanel.tsx:82 | 连接成功，该密钥可访问 {N} 个模型。 | 术语（密钥） | 连接成功，可访问 {N} 个模型。 |
| components/domain/ProviderPanel.tsx:83 | 连接结果：{原始 state} | 内部状态 | 连接成功 / 连接失败：{原因} |
| components/domain/ProviderPanel.tsx:99 | 研究模型已安装。 | 术语 | 本地预测模型已安装。 |
| components/domain/ProviderPanel.tsx:112 | AI 服务 | —（合规） | 保留 |
| components/domain/ProviderPanel.tsx:115 | 未能完成 | 重复；前后矛盾（无原因） | {操作}失败：{原因} |
| components/domain/ProviderPanel.tsx:119 | 已完成 | 重复；前后矛盾（过于笼统） | 保存成功 |
| components/domain/ProviderPanel.tsx:123 | 当前服务 / API Key / 研究模型 / 预算（123–135） | 术语 | 当前服务 / API Key / 本地预测模型 / 预算 |
| components/domain/ProviderPanel.tsx:128 | 已保存 / 未保存 | —（可保留） | 已保存 / 未保存 |
| components/domain/ProviderPanel.tsx:132 | 已安装 / 未安装 | 术语；5 态不一致 | 正常 / 未设置 |
| components/domain/ProviderPanel.tsx:138 | '¥' + formatMicro(...) + ' / 日 · ¥' + formatMicro(...) + ' / 月' | 前后矛盾（与协议页"¥5/日"格式不同） | ¥{金额} / 日 · ¥{金额} / 月（统一两位小数） |
| components/domain/ProviderPanel.tsx:140 | 未配置 | 术语 | 未设置 |
| components/domain/ProviderPanel.tsx:146 | 服务商 | —（可保留） | 服务商 |
| components/domain/ProviderPanel.tsx:165 | sk-…（placeholder） | —（合规） | 保留 |
| components/domain/ProviderPanel.tsx:185 | 保存密钥 | 术语 | 保存 API Key |
| components/domain/ProviderPanel.tsx:196 | 取消 | —（合规） | 保留 |
| components/domain/ProviderPanel.tsx:203 | 测试连接 | —（合规） | 保留 |
| components/domain/ProviderPanel.tsx:206 | 替换密钥 | 术语 | 替换 API Key |
| components/domain/ProviderPanel.tsx:217 | 研究模型 | 术语 | 本地预测模型 |
| components/domain/ProviderPanel.tsx:220 | 重新安装 / 安装 | 术语 | 重新安装 / 安装 |

#### 3.6.3 运行与安装（RuntimePanel）

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| components/domain/RuntimePanel.tsx:21 | 后台服务与 EOD 调度正常。 | 术语；中英混用 | 后台任务正常。 |
| components/domain/RuntimePanel.tsx:22 | 正在启动本机服务… | —（可保留） | 正在启动后台服务… |
| components/domain/RuntimePanel.tsx:23 | 服务进程已启动，等待健康检查。 | 写给开发者的话 | 正在启动，请稍候… |
| components/domain/RuntimePanel.tsx:24 | Dashboard 进程异常退出；后台会在退避后重试，日志保留。 | 中英混用；写给开发者的话 | 页面服务异常退出，后台会自动重试。 |
| components/domain/RuntimePanel.tsx:25 | Dashboard 未能启动；请检查端口与安装文件。 | 中英混用；写给开发者的话 | 页面服务无法启动；请重启或查看诊断信息。 |
| components/domain/RuntimePanel.tsx:26 | 端口上已有一个非当前后台管理的 Stratide 实例；为避免第二个调度链，未启动 EOD watch。 | 写给开发者的话；中英混用 | 已有另一个 Stratide 在运行；为避免重复采集，本次未启动行情采集。 |
| components/domain/RuntimePanel.tsx:27 | 端口已被其他程序占用；Stratide 不会误连或结束该进程。 | 写给开发者的话 | 端口被其他程序占用，请关闭后重试。 |
| components/domain/RuntimePanel.tsx:28 | 尚未初始化 EOD 行情采集；数据与 Paper 不会自动产生。 | 术语；中英混用 | 行情采集尚未设置，模拟数据不会自动更新。 |
| components/domain/RuntimePanel.tsx:29 | 未找到随安装包提供的 Python 运行时。 | 写给开发者的话 | 缺少运行组件，请重新安装。 |
| components/domain/RuntimePanel.tsx:30 | EOD watch 已退出；后台会退避重启并保留原 journal。 | 中英混用；写给开发者的话 | 行情采集已停止，后台会自动重启。 |
| components/domain/RuntimePanel.tsx:31 | 安装目录缺少 stratided.exe。 | 内部状态；中英混用 | 程序文件缺失，请重新安装。 |
| components/domain/RuntimePanel.tsx:32 | 后台服务已由 Owner 停止。 | 术语；中英混用 | 后台服务已停止。 |
| components/domain/RuntimePanel.tsx:33 | 后台已停止，但检测到未受管理的实例仍在运行。 | 写给开发者的话 | 后台已停止，但仍有一个实例在运行。 |
| components/domain/RuntimePanel.tsx:34 | 正在按新配置重启 EOD watch。 | 中英混用 | 正在按新设置重启行情采集。 |
| components/domain/RuntimePanel.tsx:35 | 已保存 WSL 入口；请运行"检测 WSL Worker"确认真实前置、模型与隔离。 | 中英混用；写给开发者的话 | 已保存本地预测引擎设置；请点"检查状态"。 |
| components/domain/RuntimePanel.tsx:36 | 未配置 WSL2 TimesFM 入口，研究保持 BLOCKED；EOD 采集不受影响。 | 中英混用；内部状态 | 尚未设置本地预测引擎，AI 研究暂不可用；行情采集不受影响。 |
| components/domain/RuntimePanel.tsx:37 | WSL 发行版与工作树必须同时填写。 | 中英混用；写给开发者的话 | 请同时填写两个必填项。 |
| components/domain/RuntimePanel.tsx:38 | 无法调用 wsl.exe；研究保持 BLOCKED，EOD 采集继续。 | 中英混用；内部状态 | 无法启动本地预测引擎，AI 研究暂不可用；行情采集继续。 |
| components/domain/RuntimePanel.tsx:39 | 配置的 WSL 发行版不存在；研究保持 BLOCKED。 | 中英混用；内部状态 | 本地预测引擎配置无效；AI 研究暂不可用。 |
| components/domain/RuntimePanel.tsx:40 | WSL 工作树缺少可执行的 venv Python；研究保持 BLOCKED。 | 中英混用；内部状态 | 本地预测引擎缺少运行组件；AI 研究暂不可用。 |
| components/domain/RuntimePanel.tsx:41 | WSL 模型目录不存在；研究保持 BLOCKED。 | 中英混用；内部状态 | 本地预测模型缺失；AI 研究暂不可用。 |
| components/domain/RuntimePanel.tsx:42 | WSL TimesFM Worker 超时；本机研究安全阻断，等待人工检查。 | 中英混用；内部状态 | 本地预测引擎超时；AI 研究已暂停，请查看诊断信息。 |
| components/domain/RuntimePanel.tsx:43 | WSL 实际运行的 TimesFM 代码与安装包不一致；研究保持 BLOCKED。 | 写给开发者的话 | 本地预测引擎版本不一致；请重新安装。 |
| components/domain/RuntimePanel.tsx:44 | WSL Worker 返回身份/请求校验失败；研究保持 BLOCKED。 | 写给开发者的话；内部状态 | 本地预测引擎校验失败；AI 研究已暂停。 |
| components/domain/RuntimePanel.tsx:45 | 模型与 WSL 缓存不在同一文件系统，无法安全硬链接；研究保持 BLOCKED。 | 写给开发者的话；中英混用 | 本地预测模型配置无效；AI 研究已暂停（诊断信息保留细节）。 |
| components/domain/RuntimePanel.tsx:46 | WSL 模型权重/manifest 校验失败；研究保持 BLOCKED。 | 中英混用；内部状态 | 本地预测模型校验失败；AI 研究已暂停。 |
| components/domain/RuntimePanel.tsx:50 | Python 运行时 / WSL2 / TimesFM CPU / Tushare 凭据 / EOD 行情采集 / Paper 账户 / 研究 Agent（50–56） | 术语；中英混用 | 运行组件 / 本地预测引擎（WSL）/ 本地预测模型 / Tushare 连接 / 行情自动采集 / 模拟账户 / AI 研究 |
| components/domain/RuntimePanel.tsx:69 | 可用（依赖状态） | 术语；5 态不一致 | 正常 |
| components/domain/RuntimePanel.tsx:70 | 已配置 | 术语；5 态不一致 | 正常 / 需要处理 |
| components/domain/RuntimePanel.tsx:71 | 已初始化 | 术语；5 态不一致 | 正常 |
| components/domain/RuntimePanel.tsx:72 | 已完成 | 术语；5 态不一致 | 正常 |
| components/domain/RuntimePanel.tsx:73 | 未配置（MISSING / NOT_CONFIGURED） | 术语 | 未设置 / 需要处理 |
| components/domain/RuntimePanel.tsx:75 | 不可用 | 术语；5 态不一致 | 需要处理 / 出错 |
| components/domain/RuntimePanel.tsx:77 | 缺少运行时 | 术语 | 需要处理：缺少运行组件 |
| components/domain/RuntimePanel.tsx:78 | 需 WSL 工作树 | 中英混用；写给开发者的话 | 需要处理：请完成本地预测引擎设置 |
| components/domain/RuntimePanel.tsx:79 | 绑定无效 | 内部状态 | 需要处理（诊断保留原因） |
| components/domain/RuntimePanel.tsx:80 | 未知 | 内部状态 | 状态未知 |
| components/domain/RuntimePanel.tsx:93 | return parts.join(' · ')（拼接版本号、发行版、原因、note） | 写给开发者的话 | 诊断信息 |
| components/domain/RuntimePanel.tsx:205 | 操作未完成 / {error.code} | 内部状态 | 操作未完成：{一句人话原因} |
| components/domain/RuntimePanel.tsx:218 | 已找到本机模型；已自动保存，不需要填写任何路径。 | 术语；中英混用 | 已检测到本地预测引擎，设置已自动保存。 |
| components/domain/RuntimePanel.tsx:221 | 没有找到本机模型；没有它也能正常采集行情；需要时可在高级设置里手动指定。 | 术语；中英混用 | 未检测到本地预测引擎；行情采集不受影响，可在高级设置中手动指定。 |
| components/domain/RuntimePanel.tsx:226 | 自动检测未完成 / {error.code} | 内部状态 | 检测未完成：{一句人话原因} |
| components/domain/RuntimePanel.tsx:239 | WSL Worker 可用 / WSL Worker 未通过 | 中英混用；内部状态 | 本地预测引擎正常 / 本地预测引擎需要处理 |
| components/domain/RuntimePanel.tsx:240 | description: result.reason ?? undefined | 内部状态 | 一句人话原因（原始值进诊断） |
| components/domain/RuntimePanel.tsx:247 | WSL 检测未完成 | 中英混用 | 本地预测引擎检测未完成 |
| components/domain/RuntimePanel.tsx:254 | 正在读取本机运行状态… | —（可保留） | 正在读取系统状态… |
| components/domain/RuntimePanel.tsx:263 | 运行状态不可读 / {error code mono} | 内部状态 | 无法读取系统状态（诊断信息保留代码） |
| components/domain/RuntimePanel.tsx:269 | 刷新状态 | 重复 | 刷新 |
| components/domain/RuntimePanel.tsx:276 | 打开数据目录 / 284 打开日志目录 | 写给开发者的话 | 移到高级/诊断区 |
| components/domain/RuntimePanel.tsx:289 | 后台服务 | —（可保留） | 后台任务 |
| components/domain/RuntimePanel.tsx:292 | 本地服务：在线 / 离线；127.0.0.1:{port} · 仅本机 · Paper-only | 中英混用；术语 | 本地服务：正常 / 无法连接；仅本机访问 |
| components/domain/RuntimePanel.tsx:296 | 后台 Supervisor：运行中 / 补录中 / {原始 status} | 中英混用；内部状态 | 后台任务：正常 / 进行中（原始值进诊断） |
| components/domain/RuntimePanel.tsx:300 | EOD watch：运行中 / 未运行 / 补录中 | 中英混用；术语 | 行情自动采集：正常 / 已停止 / 进行中 |
| components/domain/RuntimePanel.tsx:301 | 按 Asia/Shanghai 交易日，收盘后自动采集。 | 中英混用 | 按北京时间交易日，每天收盘后自动采集。 |
| components/domain/RuntimePanel.tsx:305 | 版本 / v{product_version} · GitHub Release {tag} | 中英混用；写给开发者的话 | 版本 v… · 检查更新 |
| components/domain/RuntimePanel.tsx:318 | 最新 Release {tag} | 中英混用 | 已是最新版本 {tag} |
| components/domain/RuntimePanel.tsx:320 | 暂时无法读取 Release | 中英混用 | 暂时无法检查更新 |
| components/domain/RuntimePanel.tsx:323 | caught instanceof ApiError ? caught.code : 'UPDATE_CHECK_FAILED'（作为 toast 标题） | 内部状态 | "检查更新失败" + 原因 |
| components/domain/RuntimePanel.tsx:329 | 检查更新 | —（合规） | 保留 |
| components/domain/RuntimePanel.tsx:335 | 技术详情 | 术语 | 诊断信息 |
| components/domain/RuntimePanel.tsx:337 | 服务实例 / Supervisor / PID / 重启 N 次 / 安装目录 / 数据目录 / 登录任务 / {task_name} · {mechanism} · {detail}（337–342） | 写给开发者的话；中英混用 | 保留在"诊断信息"折叠区 |
| components/domain/RuntimePanel.tsx:348 | 登录自启 | 术语 | 登录后自动启动 |
| components/domain/RuntimePanel.tsx:351 | Windows 用户登录后启动后台 | —（可保留） | 登录 Windows 后自动启动后台任务 |
| components/domain/RuntimePanel.tsx:354 | 登录自启（aria-label） | 术语 | 登录后自动启动 |
| components/domain/RuntimePanel.tsx:364 | 依赖与权限诊断 | 术语 | 系统状态 |
| components/domain/RuntimePanel.tsx:384 | 本机 AI 模型 | 术语 | 本地预测引擎（WSL） |
| components/domain/RuntimePanel.tsx:387 | 已连接 / 未检测到 | 术语；5 态不一致 | 正常 / 未设置 |
| components/domain/RuntimePanel.tsx:390 | {status.dependencies.wsl.distribution ?? ''}（如 Ubuntu-24.04） | 中英混用 | 本地预测引擎（WSL） |
| components/domain/RuntimePanel.tsx:392 | 点"自动检测"即可，不需要填写任何路径。 | —（可保留） | 保留 |
| components/domain/RuntimePanel.tsx:403 | 自动检测 | —（可保留） | 检测 |
| components/domain/RuntimePanel.tsx:413 | 检查是否可用 | 术语 | 检查状态 |
| components/domain/RuntimePanel.tsx:418 | 高级设置 | 术语 | 高级（诊断信息） |
| components/domain/RuntimePanel.tsx:420 | WSL 发行版 / 工作树（WSL 绝对路径）/ venv Python（相对工作树或绝对路径）/ 模型目录（相对工作树或绝对路径） | 术语；写给开发者的话；中英混用 | 移到诊断/高级；普通用户不应看到路径配置 |
| components/domain/RuntimePanel.tsx:424 | Ubuntu-24.04 / /home/owner/projects/Stratide / .venv/bin/python / models/timesfm-2.5（placeholder，424–451） | 写给开发者的话；中英混用 | 移到诊断/高级 |
| components/domain/RuntimePanel.tsx:462 | 本机模型设置已保存 | 术语 | 本地预测引擎设置已保存 |
| components/domain/RuntimePanel.tsx:470 | 检测详情（原始 JSON） | 写给开发者的话；中英混用 | 诊断信息 |
| components/domain/RuntimePanel.tsx:477 | 首次设置 | —（可保留） | 首次设置 |
| components/domain/RuntimePanel.tsx:481 | Tushare Token | 术语；中英混用 | Tushare 访问令牌（保留专有名词，补充中文说明） |
| components/domain/RuntimePanel.tsx:491 | 已配置；输入可覆盖 / 粘贴 Tushare Token（placeholder） | 术语；中英混用 | 已设置，可粘贴新令牌覆盖 |
| components/domain/RuntimePanel.tsx:500 | Tushare Token 已保存（toast） | 术语；中英混用 | Tushare 访问令牌已保存 |
| components/domain/RuntimePanel.tsx:509 | 行情采集 / 自动 / 等待初始化 | 术语；5 态不一致 | 行情自动采集 / 正常 / 未设置 |
| components/domain/RuntimePanel.tsx:518 | 历史补录 {N} / 84 | 术语；前后矛盾（84 口径） | 历史数据补齐 {N} / 84 个交易日 |
| components/domain/RuntimePanel.tsx:520 | 历史补录进度（aria-label） | 术语 | 历史数据补齐进度 |
| components/domain/RuntimePanel.tsx:531 | 补录已在后台开始 | 术语 | 历史数据补齐已在后台开始 |
| components/domain/RuntimePanel.tsx:534 | 补录进行中 / 开始补录 | 术语 | 补齐进行中 / 开始补齐 |
| components/domain/RuntimePanel.tsx:544 | 完成安装引导 / 标记后，双击桌面图标会直接打开总览。 | 写给开发者的话 | 完成首次设置 |
| components/domain/RuntimePanel.tsx:551 | 首次设置已标记完成 | 术语；前后矛盾 | 首次设置已完成 |
| components/domain/RuntimePanel.tsx:553 | 已标记完成 / 标记完成 | 前后矛盾 | 已完成设置 / 完成设置 |
| components/domain/RuntimePanel.tsx:560 | 最近后台日志 / 暂无日志。 | 写给开发者的话 | 诊断信息 |

### 3.7 首次使用（AgreementPage）

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| pages/AgreementPage.tsx:8 | 只在本机、只做模拟 | 重复（"只"字堆叠） | 仅在本机运行的模拟盘 |
| pages/AgreementPage.tsx:9 | 软件运行在 127.0.0.1，不连接券商、不能下真实订单。所有成交都是模拟假设，不是真实交易。 | 中英混用；术语 | 软件只在本机运行，不连接券商、不能下真实订单。所有成交都是模拟结果，不是真实交易。 |
| pages/AgreementPage.tsx:13 | 开户即使用 ¥100,000 模拟本金，最多同时持有 2 只，单票上限 ¥20,000。日亏损 2% 或回撤 10% 会自动阻止新的模拟下单。 | 前后矛盾（"开户"并非真实开户；金额无两位小数；2%/10% 为写死数值） | 模拟账户初始资金 ¥100,000.00，最多同时持有 2 只，单只上限 ¥20,000.00。达到风险限制时会自动暂停新的模拟交易。 |
| pages/AgreementPage.tsx:17 | 当你启用 AI 服务后，会把最多 8 个证券、84 个交易日的行情摘要、风险预测与研究契约字段发送给 DeepSeek 官方（api.deepseek.com），仅用于策略研究，有效期 10 年。 | 术语；中英混用；前后矛盾（84/10 年为写死值，与授权设置不一致） | 在你授权后，才会把最多 8 个证券、84 个交易日的行情摘要与风险预测发送给 DeepSeek，仅用于策略研究；授权到期时间由你在设置中决定。 |
| pages/AgreementPage.tsx:21 | 云端调用硬上限为 ¥5/日、¥100/月。超出即暂停研究，不影响行情采集与风控。 | 术语（"硬上限/风控"）；前后矛盾（金额格式） | 云端调用上限为 ¥5.00 / 日、¥100.00 / 月。超出后自动暂停 AI 研究，不影响行情采集与交易保护。 |
| pages/AgreementPage.tsx:25 | Tushare 数据按个人本地许可使用，只在本机保存与计算，不转发、不再分发。 | —（合规，建议保留） | 保留 |
| pages/AgreementPage.tsx:29 | API Key 只保存在 Windows 凭据管理器；页面不回显，日志不记录。 | 写给开发者的话 | API Key 只保存在本机，页面不回显、日志不记录。 |
| pages/AgreementPage.tsx:33 | 模拟成交与历史回测不代表未来收益，也不构成投资建议。软件不保证盈利，也不保证最大亏损。 | —（合规） | 保留 |
| pages/AgreementPage.tsx:37 | 删除数据目录里的 runtime/consent.json 即停止新的云端研究；卸载默认保留数据目录。 | 写给开发者的话；内部状态 | 可在设置中关闭云端研究并撤销授权；卸载时默认保留本地数据。 |
| pages/AgreementPage.tsx:61 | 开始之前，只有这一页 | 重复；前后矛盾（并非只有一页设置） | 开始之前，请先确认 |
| pages/AgreementPage.tsx:63 | 这是一份一次性的说明与授权。同意后，软件不会再弹出任何许可或审批。 | 前后矛盾（云端外发许可、审批入口仍存在） | 这是一次性说明。之后如需更改授权，可在设置中调整。 |
| pages/AgreementPage.tsx:74 | 没有保存成功 | —（可保留） | 保存失败 |
| pages/AgreementPage.tsx:80 | 同意并继续 | —（合规） | 保留 |
| pages/AgreementPage.tsx:82 | 同意记录只保存在本机，不会上传。 | —（合规） | 保留 |

### 3.8 错误提示、状态映射与工具函数文案（跨页共用）

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| lib/api.ts:34 | Owner 已暂停研究。 | 术语；中英混用 | AI 研究已暂停。 |
| lib/api.ts:34 | 请先解锁本机研究控制。 | 内部状态 | 本机研究控制未解锁。 |
| lib/api.ts:35 | 本次许可已过期，请重新提交并核对。 | —（可保留） | 保留 |
| lib/api.ts:35 | 审批状态已变化，请重新读取原记录。 | 内部状态 | 审批状态已变化，请刷新后重试。 |
| lib/api.ts:36 | 研究工作区未绑定当前 Agent；已阻止执行。 | 术语；内部状态 | 研究工作区未绑定，已停止执行。 |
| lib/api.ts:37 | 原研究实例绑定不可用，未执行研究。 | 内部状态 | 研究实例不可用，未执行研究。 |
| lib/api.ts:38 | 原云调用开关已关闭或本次许可已消费。 | 内部状态 | 云端调用未获授权或已使用。 |
| lib/api.ts:39 | 本地 CPU 研究已停用。 / 本地研究，不计费。 | 内部状态 | 本地研究已停用。 / 本地研究不计费。 |
| lib/api.ts:44 | 状态或原因见技术详情 | 重复；写给开发者的话（"技术详情"应为"诊断信息"） | 原因未记录 |
| lib/api.ts:68 | 请求已取消 | —（合规） | 保留 |
| lib/api.ts:71 | 本地服务响应超时。请确认 Windows 上的 stratided 进程仍在运行。 | 写给开发者的话；中英混用 | 本地服务响应超时，请稍后重试。 |
| lib/api.ts:75 | 无法连接本地服务。请确认 stratided 正在运行，然后重新读取。 | 写给开发者的话；中英混用 | 无法连接本地服务，请确认后台任务已启动后重试。 |
| lib/api.ts:90 | 本地服务返回了无法解析的响应。 | 写给开发者的话 | 本地服务返回异常，请查看诊断信息。 |
| lib/api.ts:97 | 本地服务返回了空的响应。 | 写给开发者的话 | 本地服务返回异常，请重试。 |
| lib/api.ts:102 | 响应不符合 Stratide API 的公开格式。 | 写给开发者的话；中英混用 | 本地服务返回格式异常，请查看诊断信息。 |
| lib/api.ts:113 | 本地服务返回 HTTP {status}。 | 写给开发者的话；中英混用 | 本地服务返回错误（代码 {status}），请查看诊断信息。 |
| lib/api.ts:136 | 尚未指定 Paper 报告。 | 术语 | 尚未选择模拟账户数据。 |
| lib/api.ts:142 | 读取期间本地服务返回了不同快照，已停止组合显示。请重新读取。 | 写给开发者的话 | 数据在读取过程中发生变化，已停止显示，请重试。 |
| lib/api.ts:154 | 账户数据不完整，已停止展示以避免混用。 | 写给开发者的话 | 账户数据不完整，已停止显示，请重试。 |
| lib/api.ts:185 | 健康检查响应缺少 data。 / 195 研究档案响应缺少 data。 / 266 研究服务响应缺少 data。 | 写给开发者的话；中英混用 | 本地服务返回数据不完整，请查看诊断信息。 |
| lib/api.ts:234 | 本机研究服务响应超时。 / 238 无法连接本机研究服务。 | 术语 | AI 研究服务响应超时 / 无法连接 AI 研究服务。 |
| lib/api.ts:251 | 研究服务返回了无法解析的响应。 / 254 研究服务返回了空响应。 / 261 研究服务返回 HTTP {status}。 | 写给开发者的话 | AI 研究服务返回异常，请查看诊断信息。 |
| lib/api.ts:343 | 发生未知错误。 / 345 发生未知错误。 | 内部状态 | 发生未知错误，请查看诊断信息。 |
| lib/workspace.ts:47 | 本地研究资料读取失败；请在技术详情核对原因。 | 术语（"技术详情"） | 研究报告读取失败，原因见诊断信息。 |
| lib/workspace.ts:49 | 研究响应版本不兼容。 | 写给开发者的话 | 研究报告数据版本不兼容，请更新后重试。 |
| lib/workspace.ts:76 | stateLabel 兜底：待核对（见技术详情） | 内部状态；写给开发者的话 | 状态未知（原始值进诊断信息） |
| lib/labels.ts:113 | 未知模式 / 服务未提供快照模式。 | 内部状态 | 诊断信息 |
| lib/labels.ts:114 | 未识别的快照模式，保留原始值。 | 写给开发者的话 | 诊断信息 |
| lib/format.ts:249 | return side;（sideLabel 兜底） | 内部状态 | 方向未知 |
| lib/format.ts:265 | return status;（orderStatusLabel 兜底） | 内部状态 | 状态未知 |
| lib/format.ts:222 | 运行中（时长兜底） | 前后矛盾（与"研究中"并存） | 进行中 |
| lib/runtime.ts:80 | 无法连接本地服务；后台可能已停止。 | 写给开发者的话 | 无法连接本地服务，请确认后台任务已启动。 |
| lib/runtime.ts:86 | 本地服务返回了无法解析的响应。 | 写给开发者的话 | 本地服务返回异常，请查看诊断信息。 |
| lib/runtime.ts:90 | throw new ApiError(code, code, response.status) | 内部状态 | 前端统一转换为一句人话；原始 code 进诊断 |
| state/useAgent.ts:158 | 本机会话已失效，请重新输入 Owner 令牌。 | 术语；中英混用 | 本机会话已失效，请刷新页面。 |
| state/useAgent.ts:188 | 请输入 Owner 令牌。 | 术语；中英混用 | 无法确认本机身份，请刷新页面。 |
| state/useAgent.ts:213 | Owner 令牌无效，或本机 Agent 尚未启动。 | 术语；中英混用 | 本机身份无效，或 AI 研究服务尚未启动。 |
| state/useAgent.ts:240 | 请先解锁 Agent。 | 术语；中英混用 | AI 研究服务尚未就绪。 |
| pages/HistoryPage.tsx:651 | 'not_configured' 作为页面默认状态文本 | 内部状态 | 状态未知 / 未设置（原始值进诊断） |
| pages/SettingsPage.tsx:237 | code={paper.error?.code}（错误码显示在空状态） | 内部状态 | 只保留诊断信息中的代码 |

### 3.9 未挂载组件（当前不渲染，接入导航前必须整改）

> `MarketResearchPanel`、`ResearchOperations`、`SnapshotBadges`、`AvailabilityBadge`、`VERIFICATION_LABELS`、`BUDGET_STATE_LABELS` 当前未被任何页面引用（或在 AgentPage 中 import 后未使用）。以下仅列会直接影响用户的最严重项；若接入，需要全部套用 §4 的统一状态与术语。

| 位置 | 原文 | 问题类型 | 建议文案 |
| --- | --- | --- | --- |
| components/domain/MarketResearchPanel.tsx:44 | 请先在 Agent 页面解锁本机控制，再配置自动研究与外发许可。 | 内部状态；前后矛盾（页面无解锁入口） | 请先在"AI 研究"页启用自动研究。 |
| components/domain/MarketResearchPanel.tsx:97 | 可信盘后快照 → 确定性筛选 → 限量本地 TimesFM CPU → DeepSeek 策略假说。候选仅供研究，PIT 未验证，不创建买卖单。 | 中英混用；写给开发者的话 | 收盘后自动筛选证券，生成本地预测与云端研究假设；结果仅供研究，不会产生交易。 |
| components/domain/MarketResearchPanel.tsx:98 | 需连续 84 个交易会话的 READY 全市场快照；新安装从配置日起积累，暖机不足显示 BLOCKED，不用旧历史库补足。 | 内部状态；前后矛盾（84 口径） | 需要连续 84 个交易日的完整全市场数据；数据不足时保持"未设置"并显示原因。 |
| components/domain/MarketResearchPanel.tsx:99 | 源交易日和输入参考时点 as_of 都不证明候选已及时冻结… | 中英混用；写给开发者的话 | 诊断信息 |
| components/domain/MarketResearchPanel.tsx:114 | 固定模型：{model_version}。Provider 别名可能更新；调用收据保存模型配置指纹。每个源交易日最多一个冻结批次，未知结果不自动重发。 | 中英混用；写给开发者的话 | 固定模型：{模型名}；每个数据日最多生成一批研究；未知结果不会自动重发。 |
| components/domain/MarketResearchPanel.tsx:121 | 上限 ¥5 / 日、¥100 / 月；使用原 Agent Budget Gate，不可在此加额。未知账单保留最坏预留。 | 中英混用；术语 | 上限 ¥5.00 / 日、¥100.00 / 月，不能在此修改；未确认费用会暂时冻结。 |
| components/domain/MarketResearchPanel.tsx:123 | 真实数据外发许可 · 独立于自动研究开关 | 写给开发者的话 | 云端数据授权 |
| components/domain/MarketResearchPanel.tsx:124 | 未获有效许可 · REAL_MARKET_DATA_EGRESS_DENIED | 内部状态 | 尚未授权云端数据外发 |
| components/domain/MarketResearchPanel.tsx:134 | DeepSeek · api.deepseek.com/chat/completions | 中英混用 | DeepSeek |
| components/domain/MarketResearchPanel.tsx:136 | Tushare 可信 EOD 派生研究摘要 | 术语；中英混用 | Tushare 盘后数据摘要 |
| components/domain/MarketResearchPanel.tsx:149 | 当前批次最多 {N} 个候选、84 个会话的派生风险摘要、20 会话预测。 | 术语；前后矛盾（84/20 会话口径） | 当前批次最多 {N} 个候选、84 个交易日的数据摘要、20 个交易日的预测。 |
| components/domain/MarketResearchPanel.tsx:156 | 暂无批次；等待可信全市场快照 READY 与自动研究配置。 | 内部状态 | 暂无研究批次；等待完整数据与自动研究设置。 |
| components/domain/MarketResearchPanel.tsx:158 | {run.source_day} · {run.state}（枚举原样） | 内部状态 | 数据日期 {格式化} · 统一 5 态 |
| components/domain/MarketResearchPanel.tsx:159 | 全证券池 {N} · 合格 {N} · {run.reason 原样} | 中英混用；内部状态 | 全部证券 {N} · 符合条件 {N}（原因进诊断） |
| components/domain/MarketResearchPanel.tsx:162 | 筛选拒绝原因（原始 JSON） | 写给开发者的话 | 诊断信息 |
| components/domain/MarketResearchPanel.tsx:163 | 未验证假说 · RESEARCH_ONLY · PIT 未验证 | 中英混用；内部状态 | 未经独立验证的研究假设 |
| components/domain/MarketResearchPanel.tsx:166 | 预览待发 payload 与最坏费用 | 中英混用；写给开发者的话 | 预览待发送数据与最高费用（诊断信息） |
| components/domain/MarketResearchPanel.tsx:168 | 本机 payload 预览 · 未发送 | 中英混用 | 待发送数据预览（未发送） |
| components/domain/ResearchOperations.tsx:29 | 发起冻结研究 / 停止本地研究 / 本地研究已请求停止；原任务保留。 | 术语；内部状态 | 发起研究 / 停止本地研究 / 已请求停止本地研究，任务保留。 |
| components/domain/ResearchOperations.tsx:30 | 仅执行本机已配置的实验；审批不增加预算、外发范围或交易权限。 | 写给开发者的话 | 仅运行本机已配置的研究；审批不会增加预算、外发范围或交易权限。 |
| components/domain/ResearchOperations.tsx:31 | 尚未配置可运行实验…TimesFM CPU · 本地不计费 / 独立评价入口 · 本地不计费 / 离线录制 Fusion · TST，非真实账单 / 合成来源 · 原云授权与预算 Gate | 中英混用；内部状态；写给开发者的话 | 尚未配置可运行的研究；用中文说明每类研究是否产生费用。 |
| components/domain/ResearchOperations.tsx:33 | 版本化内置 Prompt（只读安全版） | 中英混用；写给开发者的话 | 诊断信息 |
| components/domain/Badges.tsx:61 | 源日 {日期}（SnapshotBadges） | 术语 | 数据日期 {日期} |
| components/domain/Badges.tsx:62 | 仅快照 · 非实时 | 写给开发者的话 | 盘后数据 · 非实时 |
| lib/labels.ts:5 | 模拟盘（mode 标签，与"模拟账户"混用） | 术语 | 模拟账户 |
| lib/labels.ts:16 | 历史 EOD 模拟结果；历史可用时间未获独立 point-in-time 核验。 | 中英混用；写给开发者的话 | 历史回放结果（诊断信息保留核验状态） |
| lib/labels.ts:21 | 真实前向 Paper 账户记录，不是券商成交或实盘收益。 | 术语；中英混用 | 模拟账户记录，不是真实成交或实盘收益。 |
| lib/labels.ts:67 | 已入队 / 研究中 / 结果 / 费用不确定（EOD 状态，与任务状态词不一致） | 前后矛盾 | 与 §4.1 任务状态共用同一套词 |
| lib/labels.ts:84 | 状态未知，可能含未结费用（可用性兜底） | 写给开发者的话 | 结果未确认，可能还有未结算费用 |
| lib/labels.ts:96 | FAKE / SYNTHETIC | 中英混用；内部状态 | 模拟测试数据 |
| lib/labels.ts:96 | 真实服务尚未验证 / 已有真实调用记录 | 内部状态 | 已核验 / 未核验（诊断信息保留原始值） |
| lib/labels.ts:108 | 已配置 / 未配置（预算状态，未使用） | 术语；重复 | 正常 / 未设置 |

---

## 4. 状态枚举清单与直接渲染位置

> 统一目标：主界面只使用 **正常 / 进行中 / 需要处理 / 出错 / 未设置** 五态（外加一句现状/原因）。后端枚举、原因码、内部 ID 一律进"诊断信息"折叠区。下表"直接渲染"= 该枚举值（或其未映射的兜底）会以原始英文出现在普通用户可见区域。

### 4.1 任务状态（Agent 任务 / 通知）

来源：`lib/labels.ts:34–56`（TASK_STATUS_LABELS / TONES）、`lib/workspace.ts:64–76`（stateLabel 同名映射，措辞不同）。

| 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- |
| queued | 排队中 | AgentPage:618（TaskStatusBadge）、Notifications:96、Drawer:706 | 否 | 排队中 | 进行中 |
| running | 研究中；workspace 映射为"运行中"；taskDuration 另显示"运行中"（AgentPage:50） | AgentPage:50/175/618、Notifications:96 | 否（但同一状态两词） | 运行中 | 进行中 |
| local_running | 本地研究中；workspace 也映射"本地研究中" | TaskStatusBadge、AgentPage:696（可取消判断） | 否 | 本地运行中 | 进行中 |
| completed | 已完成 | TaskStatusBadge、Notifications | 否 | 已完成 | 正常 |
| failed | 失败；筛选器写作"异常 / 费用不确定"的一部分 | TaskStatusBadge、AgentPage:564、Notifications | 否 | 运行失败 + 一句话原因 | 出错 |
| cancel_requested | 已申请取消（labels） / 取消待确认（workspace） | TaskStatusBadge、Notifications | 否（但两套词） | 正在取消 | 进行中 |
| cancelled | 已取消 | TaskStatusBadge、Notifications | 否 | 已取消 | 未设置 |
| outcome_uncertain | 结果 / 费用不确定（labels） / 调用结果未知（workspace） | TaskStatusBadge、Notifications、AgentPage:564 | 否（两套词） | 结果未确认 + 原因 | 需要处理 |
| skipped | 已跳过 | TaskStatusBadge、Notifications | 否 | 已跳过 + 原因 | 未设置 |
| 未知值 | 状态待核对（Badges:43）；title 属性显示原始枚举（Badges:42） | AgentPage:618、Drawer:706 | 部分（title 悬浮） | 状态未知 | 需要处理 |
| —（任务列表） | 失败筛选把 failed + outcome_uncertain 合并为"异常 / 费用不确定" | AgentPage:564–565 | — | 拆成"运行失败 / 结果未确认"两项 | — |

### 4.2 收盘后自动研究（EOD）最近记录状态

来源：`lib/labels.ts:66–77`（EOD_DISPOSITION_LABELS），渲染于 AgentPage:236。

| 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- |
| queued | 已入队 | AgentPage:236 | 否 | 排队中 | 进行中 |
| running | 研究中 | AgentPage:236 | 否 | 运行中 | 进行中 |
| completed | 已完成 | AgentPage:236 | 否 | 已完成 | 正常 |
| failed | 失败 | AgentPage:236 | 否 | 运行失败 + 原因 | 出错 |
| cancelled | 已取消 | AgentPage:236 | 否 | 已取消 | 未设置 |
| outcome_uncertain | 结果 / 费用不确定 | AgentPage:236 | 否 | 结果未确认 + 原因 | 需要处理 |
| skipped | 已跳过 | AgentPage:236 | 否 | 已跳过 + 原因 | 未设置 |
| skipped_superseded | 已跳过 · 已被新源日替代 | AgentPage:236 | 否 | 已跳过（有新的数据日） | 未设置 |
| skipped_paused | 已跳过 · Agent 暂停 | AgentPage:236 | 否 | 已跳过（AI 研究已暂停） | 未设置 |
| not_triggered | 尚未触发 | AgentPage:236 | 否 | 尚未开始 | 未设置 |
| 未知值 | 状态待核对 | AgentPage:236 | 否 | 状态未知 | 需要处理 |
| —（跳过计数） | 已记录跳过 {N} 次（AgentPage:241） | AgentPage:241 | 否 | 已跳过 {N} 次 | — |

### 4.3 模拟订单状态

来源：`lib/labels.ts:58–64`（仅 tone）、`lib/format.ts:252–267`（orderStatusLabel）。

| 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- |
| Open | 待成交 | HistoryPage:341/397、OrderDrawer:40/55、FillDrawer:90 | 否 | 待成交 | 进行中 |
| PartiallyFilled | 部分成交 | 同上 | 否 | 部分成交 | 进行中 |
| Filled | 已成交 | 同上 | 否 | 已成交 | 正常 |
| Rejected | 已拒绝 | 同上 | 否 | 已拒绝 + 原因 | 出错 |
| Expired | 已过期 | 同上 | 否 | 已过期 | 未设置 |
| 未知值 | orderStatusLabel 返回原始值；OrderDrawer:55 直接拼"中文 / 原始状态" | HistoryPage:397、OrderDrawer:55 | 是 | 状态未知 | 需要处理 |
| —（原因列） | 原始 order.reason | HistoryPage:398、OrderDrawer:61 | 是 | 一句话原因；原始值进诊断 | — |

### 4.4 交易方向

| 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- |
| Buy | 买入 | SideBadge、sideLabel、各抽屉与表格 | 否 | 买入 | 不适用 |
| Sell | 卖出 | 同上 | 否 | 卖出 | 不适用 |
| 未知值 | SideBadge 返回原始值（Badges:31）；sideLabel 返回原始值（format:249）；HistoryPage:390 把非 Buy 一律显示"卖出" | Badges:31、HistoryPage:390、FillDrawer:94、OrderDrawer:50 | 部分 | 方向未知 | 需要处理 |

### 4.5 策略记录状态

| 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- |
| snapshot_record_only | 快照记录（HistoryPage:596、StrategyDrawer:11） | HistoryPage:596、StrategyDrawer:52 | 否 | 仅记录 | 正常 |
| 其他任意值 | HistoryPage:596 一律显示"Paper 假设记录" | HistoryPage:596 | 否（状态被丢失） | 按真实状态映射；无状态时"状态未知" | 需要处理 |
| 其他任意值（Drawer） | StrategyDrawer:11 原样返回 status | StrategyDrawer:52 | 是 | 状态未知 | 需要处理 |

### 4.6 研究资格 / 验证 / 可用性（含未使用映射）

| 枚举来源 | 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- | --- |
| 研究资格 | EXPLORATORY_NOT_INDEPENDENT | 探索性研究；未知兜底"资格待核对"（AgentPage:207） | AgentPage:207（title 显示原始值）、AgentPage:817 | 部分（title 与 817 兜底可显示原值） | 探索性研究 / 状态未知 | 需要处理 |
| 验证（未使用） | FAKE_SYNTHETIC_ONLY | FAKE / SYNTHETIC | labels.ts:96（未渲染） | — | 模拟测试数据 | 未设置 |
| 验证（未使用） | REAL_PROVIDER_NOT_VERIFIED | 真实服务尚未验证 | labels.ts:97 | — | 未核验 | 需要处理 |
| 验证（未使用） | REAL_PROVIDER_CALL_OBSERVED | 已有真实调用记录 | labels.ts:98 | — | 已使用 | 正常 |
| 验证（未使用） | LOCAL_NO_BILLING | 本地不计费 | labels.ts:99 | — | 本地不计费 | 正常 |
| 验证（未使用） | VERIFIED | 已核验 | labels.ts:100 | — | 已核验 | 正常 |
| 可用性（未使用） | not_verified | 未验证 | labels.ts:80；AvailabilityBadge 未渲染 | — | 未验证 | 需要处理 |
| 可用性（未使用） | available | 可用 | labels.ts:81 | — | 正常 | 正常 |
| 可用性（未使用） | last_task_completed | 最近调用完成 | labels.ts:82 | — | 上次调用成功 | 正常 |
| 可用性（未使用） | unavailable | 不可用 | labels.ts:83 | — | 需要处理 | 需要处理 |
| 可用性（未使用） | unavailable_or_outcome_unknown | 状态未知，可能含未结费用 | labels.ts:84；title 悬浮原值（Badges:50） | — | 结果未确认，可能存在未结算费用 | 需要处理 |

### 4.7 预算状态

| 枚举来源 | 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- | --- |
| AgentBudget.state | configured | 已配置；徽标实际显示 `budget.currency`（如 CNY） | AgentPage:309 | 是（币种原样） | 正常（金额以 ¥ 显示） | 正常 |
| AgentBudget.state | unconfigured | 未配置 | AgentPage:309、ProviderPanel:140 | 否 | 未设置 | 未设置 |
| BUDGET_STATE_LABELS（未使用） | configured / unconfigured | 已配置 / 未配置 | labels.ts:107–110 | — | 正常 / 未设置 | 正常 / 未设置 |

### 4.8 快照模式与证据等级

来源：`lib/labels.ts:3–32`（MODE_LABELS / EVIDENCE_LABELS）。渲染于 ModeBadge / EvidenceBadge。

| 类别 | 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- | --- |
| 快照模式 | tushare_incremental_eod | 本机盘后采集 | ModeBadge（Overview:136、History:78、各 Drawer、AgentPage:799、WorkspaceStudies:21/33/42） | 否 | 只进诊断信息；主界面显示"数据正常/缺失" | — |
| 快照模式 | ex_post_paper_assumption | 模拟盘 | 同上 | 否 | 同上 | — |
| 快照模式 | historical_research_only | 事后历史研究 | 同上 | 否 | 同上 | — |
| 快照模式 | forward_observed_eod | 前向盘后观察 | 同上 | 否 | 同上 | — |
| 快照模式 | synthetic_test | 合成测试 | 同上 | 否 | 同上 | — |
| 快照模式 | historical_replay | 历史回放 | 同上 | 否 | 同上 | — |
| 快照模式 | forward_paper | 前向模拟 | 同上 | 否 | 同上 | — |
| 快照模式 | 未知值 | 未知模式（见技术详情） | Badges:18 | 否（含禁用词"技术详情"） | 诊断信息 | — |
| 证据等级 | EX_POST_OPEN_ASSUMPTION | 事后开盘价假设 | EvidenceBadge（Settings:177） | 否 | 只进诊断信息 | — |
| 证据等级 | exploratory_historical_replay_not_pit_verified | 事后历史 · PIT 未验证 | 同上 | 否（PIT 内部词） | 同上 | — |
| 证据等级 | engine_test_only | 引擎测试证据 | 同上 | 否 | 同上 | — |
| 证据等级 | exploratory_not_verified | 探索性 · PIT 未核验 | 同上 | 否 | 同上 | — |
| 证据等级 | independent_verified | 独立核验证据 | 同上 | 否 | 同上 | — |
| 证据等级 | exploratory | 探索性证据 | 同上 | 否 | 同上 | — |
| 证据等级 | 未知值 | 证据待核对 / 证据未知 | Badges:24–25 | 否 | 诊断信息 | — |

### 4.9 研究工作区状态（stateLabel 全表）

来源：`lib/workspace.ts:64–76`。渲染于 WorkspaceStudies:32/34/39/42、NotificationsPage:96、AgentPage:869（费用调用状态）。兜底统一为"待核对（见技术详情）"（禁止用语）。

| 后端枚举值 | 当前界面文案 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- |
| RESEARCH_ONLY | 仅供研究 | 仅供研究 | 未设置 |
| REGISTERED | 已登记 | 已登记 | 正常 |
| FROZEN_CANDIDATE | 候选已冻结 | 已冻结候选 | 正常 |
| NOT_BILLED | 离线录制，不是真实云调用或账单 | 离线数据，不是真实调用或账单 | 正常 |
| reserved | 已预留 | 已冻结费用 | 进行中 |
| dispatched | 已派发 | 已发出调用 | 进行中 |
| usage_received | 用量估算已记录 | 已记录用量 | 进行中 |
| settled | 已核验账单 | 已结算 | 正常 |
| no_charge | 确认未计费 | 未产生费用 | 正常 |
| pending | 待审批 | 待确认 | 进行中 |
| approved | 已许可，尚未执行 | 已确认，尚未执行 | 进行中 |
| rejected | 已拒绝 | 已拒绝 | 出错 |
| revoked | 已撤销 | 已撤销 | 未设置 |
| expired | 已过期 | 已过期 | 未设置 |
| running | 运行中 | 运行中 | 进行中 |
| local_running | 本地研究中 | 本地运行中 | 进行中 |
| completed | 已完成 | 已完成 | 正常 |
| failed | 失败 | 运行失败 + 原因 | 出错 |
| cancelled | 已取消 | 已取消 | 未设置 |
| cancel_requested | 取消待确认 | 正在取消 | 进行中 |
| outcome_uncertain | 调用结果未知 | 结果未确认 | 需要处理 |
| BLOCKED | 受阻 | 需要处理 + 原因 | 需要处理 |
| ready | 可读取 | 正常 | 正常 |
| not_configured | 未配置 | 未设置 | 未设置 |
| historical_research_only | 事后历史研究 | 历史研究 | 正常 |
| synthetic_test | 合成测试 | 模拟测试 | 未设置 |
| forward_observed_eod | 前向盘后观察 | 前向观察 | 正常 |
| FROZEN_NOT_RUN | 输入已冻结，尚未运行 | 已冻结，尚未运行 | 进行中 |
| LOCAL_NO_BILLING | 本地运行，不计费 | 本地运行，不计费 | 正常 |
| ESTIMATED_NOT_VERIFIED_BILL | 估算费用，非核验账单 | 预估费用，尚未结算 | 需要处理 |
| verified_local_integrity | 本地完整性已核对 | 本地数据已校验 | 正常 |
| stored_evidence_not_qualification | 已有来源记录，非交易资格 | 仅有来源记录，不代表可交易 | 需要处理 |
| 未知值 | 待核对（见技术详情） | 状态未知 | 需要处理 |

### 4.10 行情市场 / 研究评价 / 候选状态

| 枚举来源 | 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- | --- |
| market.state | READY | 数据覆盖合格 | WorkspaceStudies:22 | 否 | 正常 | 正常 |
| market.state | NOT_CONFIGURED | 未配置 | WorkspaceStudies:22 | 否 | 未设置 | 未设置 |
| market.state | MARKET_CLOSED | 交易所休市 | WorkspaceStudies:22 | 否 | 正常（休市） | 正常 |
| market.state | 其他值 | 等待或受阻（见详情） | WorkspaceStudies:22 | 否 | 需要处理 + 原因 | 需要处理 |
| market.latest.catalog_state | — | 未渲染 | — | — | 诊断信息 | — |
| evaluation.verdict | STRUCTURALLY_UNREACHABLE | 当前协议样本量达不到预设门槛。 | WorkspaceStudies:39 | 否 | 数据不足，无法评价 | 需要处理 |
| evaluation.state / candidate.state / study.state / study.billing | 任意值 | stateLabel（§4.9） | WorkspaceStudies:32/34/39/42 | 部分（stateLabel 兜底） | 见 §4.9 | 见 §4.9 |
| evidence[].name / studies[].kind | 任意英文 | 原样渲染 | WorkspaceStudies:32/163（Settings） | 是 | 诊断信息 | — |
| admission.matrix[].status | 任意值 | 一律显示"受阻"（硬编码） | SettingsPage:162 | 否（但状态被硬编码） | 按真实状态显示 | 需要处理 |
| backup.state | VERIFIED_LOCAL_BACKUP | 完整性已核对，共 {N} 个文件 / 兜底"尚无已核对的备份清单…" | SettingsPage:256 | 否 | 最近备份：已完成 / 未设置 | 正常 / 未设置 |
| publication | authoritative_paper_ledger | 原 Paper 账本，只读事务 | SettingsPage:189 | 否 | 诊断信息 | — |
| publication | 其他值 | 最后发布报告，更新需重启 | SettingsPage:189 | 否 | 诊断信息 | — |

### 4.11 运行时依赖状态（Settings › 运行与安装）

来源：`components/domain/RuntimePanel.tsx:59–83`（tone / label / explain）。

| 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- |
| READY | 可用 | RuntimePanel:372（依赖徽标） | 否 | 正常 | 正常 |
| CONFIGURED | 已配置；configured=false 时显示"未配置" | RuntimePanel:372 | 否 | 正常 / 未设置 | 正常 / 未设置 |
| INITIALIZED | 已初始化 | 同上 | 否 | 正常 | 正常 |
| COMPLETE | 已完成 | 同上 | 否 | 正常 | 正常 |
| RUNNING | label 表未覆盖 → 原样显示 RUNNING；tone 为 success | 同上 | 是 | 正常 | 正常 |
| MISSING | 未配置 | 同上 | 否 | 需要处理：未设置 | 未设置 |
| NOT_CONFIGURED | 未配置 | 同上 | 否 | 未设置 | 未设置 |
| DEGRADED | label 表未覆盖 → 原样显示 DEGRADED | 同上 | 是 | 需要处理 + 原因 | 需要处理 |
| BROKEN | 不可用 | 同上 | 否 | 出错 + 原因 | 出错 |
| UNAVAILABLE | 不可用 | 同上 | 否 | 出错 + 原因 | 出错 |
| FAILED | label 表未覆盖 → 原样显示 FAILED | 同上 | 是 | 出错 + 原因 | 出错 |
| BLOCKED_MISSING_RUNTIME | 缺少运行时 | 同上 | 否 | 需要处理：缺少运行组件 | 需要处理 |
| BLOCKED_*（其他，如 BLOCKED_INSUFFICIENT_MODEL_CONTEXT） | label 表未覆盖 → 原样显示 | 同上 | 是 | 需要处理 + 原因 | 需要处理 |
| EXTERNAL_WSL_WORKSPACE_REQUIRED | 需 WSL 工作树 | 同上 | 否（中英混用） | 需要处理：请完成本地预测引擎设置 | 需要处理 |
| BINDING_INVALID_OR_MISSING_LEDGER | 绑定无效 | 同上 | 否 | 需要处理（诊断信息保留原因） | 需要处理 |
| UNKNOWN | 未知 | 同上 | 否 | 状态未知 | 需要处理 |
| 未知值 | map 兜底返回原始 state（RuntimePanel:82） | 同上 | 是 | 状态未知 | 需要处理 |

### 4.12 后台状态、原因码与更新检查

来源：`RuntimePanel.tsx:20–47`（REASONS）、`:258`、`:296`、`:337–342`；`lib/runtime.ts`。

| 枚举来源 | 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- | --- |
| supervisor.status | RUNNING / DEGRADED | 运行中（两者都显示"运行中"） | RuntimePanel:296 | 否 | 正常 / 需要处理 | 正常 / 需要处理 |
| supervisor.status | 其他值 | 原样显示 | RuntimePanel:296、338 | 是 | 状态未知 | 需要处理 |
| supervisor.reason | REASONS 已映射的 23 个码（OK、STARTING、DASHBOARD_*、EXTERNAL_STRATIDE_INSTANCE、PORT_IN_USE_BY_OTHER_APPLICATION、EOD_NOT_CONFIGURED、PYTHON_RUNTIME_MISSING、WATCH_EXITED、WATCH_RESTARTING、STOPPED_BY_OWNER、STOPPED_WITH_UNMANAGED_SERVICE、WSL_PROBE_REQUIRED、TIMESFM_WSL_*、MODEL_NOT_PROVISIONED 等） | 中文长句（大量含 EOD/WSL/BLOCKED/Supervisor 等内部词） | RuntimePanel:258、297 | 否（文案内部词多） | 一句话人话 + 原始码进诊断 | 按语义映射 |
| supervisor.reason | 未覆盖的任意值 | 原样显示 | RuntimePanel:258 | 是 | 原因未记录（原始码进诊断） | 需要处理 |
| service.healthy | true / false | 在线 / 离线 | RuntimePanel:292 | 否 | 正常 / 无法连接 | 正常 / 出错 |
| backfill running | true | 补录中；历史补录 {N}/84；补录进行中 | RuntimePanel:296/300/518/534 | 否 | 历史数据补齐 {N}/84（进行中） | 进行中 |
| wsl-detect.state | FOUND | 已找到本机模型 | RuntimePanel:218 | 否 | 已检测到本地预测引擎 | 正常 |
| wsl-probe.state | READY / BLOCKED | WSL Worker 可用 / WSL Worker 未通过；description 直出 reason | RuntimePanel:239–240 | 部分（reason 原样） | 本地预测引擎正常 / 需要处理 + 原因 | 正常 / 需要处理 |
| runtimeAction 错误 | ApiError.code | Callout 内以 mono 原样显示；toast 描述直接显示 code | RuntimePanel:205/226/247/263/264/323 | 是 | 一句人话 + 诊断信息 | 出错 |
| update-check.state | OK（有 tag） | 最新 Release {tag} | RuntimePanel:318 | 否（中英混用） | 已是最新版本 | 正常 |
| update-check.state | 非 OK | 暂时无法读取 Release | RuntimePanel:320 | 否 | 暂时无法检查更新 | 需要处理 |

### 4.13 健康检查状态（`/api/health`）

来源：`layout/HealthPopover.tsx:11–18`、`:52–128`。

| 字段 | 后端值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- | --- |
| service | online | 服务在线 / 在线 | HealthPopover:80/98 | 否 | 系统正常 | 正常 |
| market_data | last_published_snapshot_not_live | 最后发布快照 · 非实时 | HealthPopover:108–109 | 否 | 盘后数据 · 非实时 | 正常 |
| market_data | 其他值 | 原样显示 | HealthPopover:110 | 是 | 数据状态：未知（诊断信息保留原值） | 需要处理 |
| forward_account | not_available | 尚未接入 | HealthPopover:116 | 否 | 未设置 | 未设置 |
| forward_account | 其他值 | 原样显示 | HealthPopover:116 | 是 | 状态未知 | 需要处理 |
| agent | not_implemented / local_research_available | 未接入 / 本机可用 | HealthPopover:11–13/122 | 否 | 未设置 / 正常 | 未设置 / 正常 |
| agent | 其他值 | 原样显示 | HealthPopover:122 | 是 | 状态未知 | 需要处理 |
| notifications | not_implemented | 未接入 | HealthPopover:16–17/128 | 否 | 未设置 | 未设置 |
| notifications | 其他值 | 原样显示 | HealthPopover:128 | 是 | 状态未知 | 需要处理 |
| snapshot 状态 | NO_SNAPSHOT / INVALID_SNAPSHOT / 其他 | 未选择报告 / 报告不可用 / 读取失败 | HealthPopover:55–63 | 否 | 未设置 / 需要处理 / 出错 | — |

### 4.14 费用调用状态（Agent 调用记录）

来源：`lib/workspace.ts:67`（stateLabel），渲染于 AgentPage:869（title 属性带原始 state）。

| 后端枚举值 | 当前界面文案 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- |
| reserved | 已预留 | 否（title 原值） | 已冻结费用 | 进行中 |
| dispatched | 已派发 | 否（title 原值） | 已发出调用 | 进行中 |
| usage_received | 用量估算已记录 | 否（title 原值） | 已记录用量 | 进行中 |
| settled | 已核验账单 | 否（title 原值） | 已结算 | 正常 |
| no_charge | 确认未计费 | 否（title 原值） | 未产生费用 | 正常 |
| 未知值 | 待核对（见技术详情） | 否 | 状态未知 | 需要处理 |

### 4.15 审批 / 通知 / 其他枚举

| 枚举来源 | 后端枚举值 | 当前界面文案 | 出现位置 | 是否直接渲染 | 建议用户文案 | 统一 5 态 |
| --- | --- | --- | --- | --- | --- | --- |
| Approval.status | pending / approved / rejected / revoked / expired | 待审批 / 已许可，尚未执行 / 已拒绝 / 已撤销 / 已过期 | stateLabel；当前 Inbox.approvals 未渲染 | 否 | 按 5 态展示（接入后） | 进行中 / 正常 / 出错 / 未设置 / 未设置 |
| Notice.status | 任意任务状态 | stateLabel（§4.1） | NotificationsPage:96 | 部分 | 见 §4.1 | 见 §4.1 |
| Notice.read | true / false | 已读 / 未读 | NotificationsPage:97 | 否 | 保留 | — |
| Notice.reason | 任意原因码 | 未渲染 | — | — | 必须显示一句话原因 | — |
| Inbox.authority | 任意值 | 未渲染 | — | — | — | — |
| dashboard_mode | attached_explicit_operations / worker | 未显示（仅用于逻辑） | AgentPage:146/149 | — | 诊断信息 | — |
| setup_complete | true / false | 已标记完成 / 标记完成 | RuntimePanel:553 | 否 | 已完成设置 / 完成设置 | 正常 / 未设置 |
| eod.enabled | true / false | 已启用 / 已停用 | AgentPage:217 | 否 | 已开启 / 已关闭 | 正常 / 未设置 |
| paused | true / false | 已暂停 / 等待研究任务 | AgentPage:174/182 | 否 | 已暂停 / 等待中 | 需要处理 / 进行中 |
| errors / reasons 兜底 | 任意 code | "状态或原因见技术详情"（api.ts:44） | 全站错误场景 | 否 | 原因未记录 | 需要处理 |

### 4.16 直接渲染后端枚举 / 原始值的位置清单（必须修）

| 位置 | 直接渲染的表达式 | 问题 | 处理 |
| --- | --- | --- | --- |
| components/domain/Badges.tsx:31 | SideBadge 兜底 `: side` | 未知方向原样显示 | 方向未知 |
| components/domain/Badges.tsx:42 | TaskStatusBadge `title={status}` | 悬浮显示枚举 | 移除 title 或显示中文状态 |
| components/domain/Badges.tsx:50 | AvailabilityBadge `title={availability}` | 悬浮显示枚举 | 移除 |
| components/domain/Badges.tsx:18 | 未知模式（见技术详情） | 兜底文案仍提"技术详情"，且不显示真实原因 | "状态未知" + 诊断 |
| components/domain/StrategyDrawer.tsx:11 | `return status` | 策略状态原样 | 状态未知 |
| components/domain/PositionDrawer.tsx:40 | `{position.instrument.market}` | 显示 Shanghai/Shenzhen | 沪市/深市 |
| components/domain/OrderDrawer.tsx:55 | `orderStatusLabel(status) + ' / ' + order.status` | 中英混排 | 仅中文 |
| components/domain/OrderDrawer.tsx:61 | `{order.reason}` | 原始原因直出 | 一句话原因 |
| components/domain/FillDrawer.tsx:119 | `{fill.execution_assumption}` | 原始执行假设 | 诊断 |
| components/domain/FillDrawer.tsx:120 | `{fill.source_version}` | 原始版本串 | 诊断 |
| components/domain/FillDrawer.tsx:121 | `{fill.deployment.group_id} · {fill.deployment.strategy_id}` | 内部 ID | 诊断 |
| components/domain/PaperPortfolioPanel.tsx:21 | `{order.status}` + `{order.reason}` | 枚举与原因直出 | 中文状态 + 一句话原因 |
| components/domain/PaperPortfolioPanel.tsx:23 | `{reason}` | 原始拒绝原因 | 一句话原因 |
| components/domain/PaperErrorPanel.tsx:16/31/71 | 启动命令 `pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir <目录>` | 开发者命令 | 诊断信息 |
| components/domain/RuntimePanel.tsx:82 | `return map[value.state] ?? value.state` | 未知依赖状态原样 | 状态未知 |
| components/domain/RuntimePanel.tsx:258 | `REASONS[...] ?? supervisor.reason` | 未知原因原样 | 原因未记录 |
| components/domain/RuntimePanel.tsx:264 | `<span className="mono">{error}</span>` | 原始错误码 | 诊断 |
| components/domain/RuntimePanel.tsx:296 | `supervisor?.status ?? '—'` | 原始状态 | 统一 5 态 |
| components/domain/RuntimePanel.tsx:306 | 版本串 + "GitHub Release" | 版本串/Release | 版本 v… |
| components/domain/RuntimePanel.tsx:342 | `{autostart.task_name} · {autostart.mechanism} · {autostart.detail}` | 技术字段 | 诊断 |
| components/domain/WorkspaceStudies.tsx:22 | market.state 兜底 + 原始 last_successful_date | 内部枚举/日期 | 5 态 + 格式化日期 |
| components/domain/WorkspaceStudies.tsx:25 | 原始 source_day | 日期格式不统一 | formatDay |
| components/domain/WorkspaceStudies.tsx:32 | `{study.kind}` | 内部类型 | 中文类型名 |
| components/domain/WorkspaceStudies.tsx:35 | 原始 received_at | 时间格式 | formatDateTime |
| components/domain/WorkspaceStudies.tsx:39 | stateLabel 兜底 | 见 §4.9 | 状态未知 |
| components/domain/WorkspaceStudies.tsx:42 | `{c.registry}` / stateLabel | 内部 Registry 名 | 诊断 |
| components/domain/WorkspaceStudies.tsx:11 | 原始 JSON（技术详情） | 开发者界面 | 诊断信息折叠区 |
| layout/HealthPopover.tsx:110/116/122/128 | `?? health.data?.xxx ?? '未知'` | 后端值原样 | 5 态 |
| layout/Sidebar.tsx:34 | Paper workspace | 术语 | 本地模拟盘 |
| pages/AgentPage.tsx:207 | `title={status.qualification}` | 枚举悬浮 | 移除 |
| pages/AgentPage.tsx:234 | `{status.eod.latest.source_day}` | 原始日期 | formatDay |
| pages/AgentPage.tsx:417/447 | `{model.kind === 'fake' ? '本地合成' : '云 API'}` | 内部类型简写 | 本地模拟 / 云端 AI |
| pages/AgentPage.tsx:419 | `{selected.last_reason}` | 原始原因 | 诊断 |
| pages/AgentPage.tsx:616 | `#{task.id} · {task.provider_id}` | 内部 ID | 诊断 |
| pages/AgentPage.tsx:627 | 无结论时显示"等待执行" | 状态矛盾 | 失败原因 |
| pages/AgentPage.tsx:707 | `{detail.provider_id}` | 内部 ID | 诊断 |
| pages/AgentPage.tsx:787 | `{detail.request.start_day}` / `end_day` | 原始日期 | 格式化 |
| pages/AgentPage.tsx:800 | `{detail.input.source_day}` | 原始日期 | formatDay |
| pages/AgentPage.tsx:801 | `{detail.input.version}` | 版本串 | 诊断 |
| pages/AgentPage.tsx:803 | `{detail.provider_id}` + provider_hash | 内部 ID/哈希 | 诊断 |
| pages/AgentPage.tsx:813 | FAKE / SYNTHETIC | 英文枚举 | 模拟测试数据 |
| pages/AgentPage.tsx:817 | `RESEARCH_QUALIFICATION_LABELS[...] ?? result.qualification` | 未知资格原样 | 状态未知 |
| pages/AgentPage.tsx:858/874 | call.maximum_micro / settled / usage / day / month | 内部字段 | 诊断 |
| pages/AgentPage.tsx:1056 | `{formCode}` | 原始错误码 | 诊断 |
| pages/HistoryPage.tsx:272 | `{fill.deployment.strategy_id}` | 内部 ID | 策略名称 |
| pages/HistoryPage.tsx:384 | `#{order.order_id}` | 内部 ID | 诊断 |
| pages/HistoryPage.tsx:390 | 非 Buy 一律"卖出" | 方向误标 | 方向未知 |
| pages/HistoryPage.tsx:398 | `{order.reason}` | 原始原因 | 一句话原因 |
| pages/HistoryPage.tsx:592 | `{record.deployment.deployment_id}` | 内部 ID | 诊断 |
| pages/HistoryPage.tsx:596 | 非 snapshot 一律"Paper 假设记录" | 状态丢失 | 5 态 |
| pages/HistoryPage.tsx:599 | `{record.unavailable_reason}` | 原始原因 | 一句话原因 |
| pages/HistoryPage.tsx:651 | `?? 'not_configured'` | 枚举作为文案 | 状态未知 |
| pages/HistoryPage.tsx:667/668/670 | 原始 research_evidence / engineering / independent_acceptance | 内部字段 | 诊断 |
| pages/OverviewPage.tsx:205 | `{account.valuation_error}` | 原始错误 | 诊断 |
| pages/SettingsPage.tsx:162 | `{row.required_evidence}` / `{row.issue}` | 原始英文/技术文本 | 诊断 |
| pages/SettingsPage.tsx:170–172 | snapshot_id / source / source_version | 内部值 | 诊断 |
| pages/SettingsPage.tsx:177 | EvidenceBadge（证据等级） | 内部枚举 | 诊断 |
| pages/SettingsPage.tsx:183 | `meta.timezone ?? 'Asia/Shanghai'` | 时区串 | "北京时间" |
| pages/SettingsPage.tsx:199 | gaps 原文 | 原始原因 | 诊断 |
| pages/SettingsPage.tsx:237 | `code={paper.error?.code}` | 错误码 | 诊断 |
| pages/SettingsPage.tsx:249 | local build / __BUILD_SHA__ | 构建串 | 诊断 |
| pages/SettingsPage.tsx:256 | backup.state 判断 + manifest | 内部状态/术语 | 正常 / 未设置 |
| lib/format.ts:249/265 | `return side` / `return status` | 原始枚举 | 方向未知 / 状态未知 |
| lib/api.ts:113/261 | 本地服务返回 HTTP 原始状态码 | 原始 HTTP 码 | 诊断 |
| lib/api.ts:44 | 未知 code → "状态或原因见技术详情" | 兜底禁语 | 原因未记录 |
| lib/workspace.ts:76 | 未知 state → "待核对（见技术详情）" | 兜底禁语 | 状态未知 |

---

## 5. 重复 / 矛盾专项

### 5.1 "84" 口径：一个数字，四种说法，三种语义

| 位置 | 原文 | 语境/语义 | 问题 | 建议文案 |
| --- | --- | --- | --- | --- |
| pages/OverviewPage.tsx:455 | 数据满 84 个交易日后，本机模型与已授权的云研究才会生成候选。 | 暖机（生成候选） | "交易日"未说明必须"完整/已核验" | 连续 84 个完整交易日的数据后，本地预测与 AI 研究才会生成候选。 |
| components/domain/PaperPortfolioPanel.tsx:26 | 暖机不足 84 个 READY 会话或缺少原研究证据时保持空仓 | 暖机（全市场快照会话） | READY 是后端枚举；"会话"与"交易日"混用 | 连续 84 个交易日的完整数据不足时保持空仓 |
| components/domain/RuntimePanel.tsx:518 | 历史补录 {N} / 84 | 回补历史数据（不是暖机） | 与"生成候选"的 84 混为一谈 | 历史数据补齐 {N} / 84 个交易日 |
| components/domain/RuntimePanel.tsx:531 | act(..., '补录', { sessions: 84 })（用户可见 toast："补录已在后台开始"） | 回补交易日数 | 数量语义未说明 | 历史数据补齐已在后台开始 |
| pages/AgreementPage.tsx:17 | 最多 8 个证券、84 个交易日的行情摘要…发送给 DeepSeek | 云端外发范围（历史窗口） | 与暖机/补录混淆 | 最多 8 个证券、84 个交易日的数据摘要 |
| components/domain/MarketResearchPanel.tsx:98（未挂载） | 需连续 84 个交易会话的 READY 全市场快照 | 暖机（全市场） | READY/BLOCKED 内部词 | 需要连续 84 个交易日的完整全市场数据 |
| components/domain/MarketResearchPanel.tsx:149（未挂载） | 84 个会话的派生风险摘要 | 云端外发范围 | "会话"与"交易日"混用 | 84 个交易日的数据摘要 |

**结论**：84 在三处出现但语义不同（历史回补天数 / 暖机所需完整交易日 / 云端可发送的历史窗口）。必须分别命名（"历史数据补齐"/"连续完整交易日"/"研究输入窗口"），且主界面不出现 READY、BLOCKED、交易日"会话"等词。数字本身是否需要按配置动态渲染，需 Owner/后端确认。

### 5.2 时间与日期：至少 9 种说法、5 种格式

| 现用说法 | 出现位置（示例） | 实际含义 | 建议 |
| --- | --- | --- | --- |
| 读取于 | components/layout/PageFooter.tsx:5；AgentPage:675 | 本机读取时间 | 统一"更新于" |
| 更新于 | AgentPage:99 | 本机读取时间 | 保留"更新于" |
| 检查于 | layout/HealthPopover.tsx:134 | 健康检查时间 | "更新于" |
| 源日 | HistoryPage:79/362；Badges.tsx:61；AgentPage:234 | 数据日期（后端可能原样 YYYYMMDD/YYYY-MM-DD） | "数据日期" |
| 源日期 | HistoryPage:471；FillDrawer:117 | 同上 | "数据日期" |
| 报告日 | OverviewPage:292/440；HistoryPage:440 | 有估值的日期数 | "数据日数" |
| 报告区间 | HistoryPage:436；SettingsPage:182 | 起止日期 | "数据区间" |
| 交易日 / 会话 | HistoryPage:690；WorkspaceStudies:36；MarketResearchPanel:98 | 交易日；风险模型会话 | 主界面统一"交易日"；"会话"只进诊断 |
| 取得时间 / 可用时间 / 最后成功日期 | SettingsPage:161；WorkspaceStudies:22/26/35 | 数据取得/可用时间 | "数据时间"/"最近更新" |
| 模拟记账时间 / 开盘审查时间 | FillDrawer:115/116 | 模拟成交时间/检查时间 | "模拟成交时间"/"交易保护检查时间" |
| 数字格式 | SettingsPage:183（Asia/Shanghai）；AgentPage:234/800（原样）；WorkspaceStudies:25（原样）；SettingsPage:170（截断 ID） | 混用 YYYYMMDD、YYYY-MM-DD、ISO、仅时分、时区串 | 全站统一 `YYYY-MM-DD`（日期）与 `YYYY-MM-DD HH:mm`（时间），北京时间；时区只写"北京时间" |
| "有效期 10 年" | AgreementPage:17 | 云端授权期限 | 由授权设置动态显示到期日（YYYY-MM-DD），不写死年数 |

### 5.3 金额、百分比、数量与单位

| 项 | 现状 | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| 金额格式 | `¥9,928.93`（两位小数、千分位、负号在 ¥ 前） | lib/format.ts:31–38（全站通用） | 格式本身合规 | 保留 |
| 金额格式 | `¥100,000` / `¥20,000` / `¥5/日` / `¥100/月`（无小数、斜杠） | AgreementPage:13/21 | 与全站格式不一致 | `¥100,000.00`、`¥20,000.00`、`¥5.00 / 日`、`¥100.00 / 月` |
| 币种 | 预算徽标显示 `budget.currency`（如 CNY）；预算数字用 `formatMicro(..., { currency })` 输出 `5.00 CNY` | AgentPage:309/325/330/338/343/348/351/480 | 同一页同时出现 `CNY` 与 `¥` | 主界面只用 `¥`；币种进诊断 |
| 百分比 | `formatBps` 输出两位小数（`+1.23%`）；回撤不带正负号类 | lib/format.ts:53–60；Overview:271；History:476 | 协议页写整数 2%/10% | 统一两位小数；"最大单日回撤"用于金额口径时需说明 |
| 数量词 | `只`（持仓）、`笔`（成交/订单）、`条`（任务/策略/记录）、`个`（报告日/任务）、`项`（风控锁） | Overview:336 只 vs 385 条；History:555 条；AgentPage:567/675 条；Overview:214 项 | 同类对象混用；同一卡片内冲突（持仓卡上方"N 只"、下方"0 条"） | 按 `lib/copy.ts` 的 UNITS：持仓=只、成交/订单=笔、任务=个、记录=条、天；所有计数走 `countText` |
| 数量词 | `每页 5 笔` / `每页最多 20 条` / `共 0 笔` / `0 条` / `N 个报告日` | Overview:385/396/442；AgentPage:675 | "共 0 笔/0 条/0 只"并存 | 统一"共 N 笔（单位）"，空态直接写"还没有…" |
| 股数 | 表格与抽屉：`N 股`；Tushare 说明：成交量为手（100 股） | FillDrawer:62/95/96；OrderDrawer:51–53；PositionDrawer:49–52；SettingsPage:161 | 用户可能把"手"与"股"混读，导致误解数量 | 界面只显示"股"；"手"仅用于诊断信息 |
| 风险限制 | 协议页写死"日亏损 2% 或回撤 10%" | AgreementPage:13 | 与产品/风险配置可能不一致（ADR-018 明确阈值尚待 Owner 确定） | 从配置读取并显示真实值，或删除具体数字 |
| 搜索/计数 | `{N} / {M} 笔`、`{N} / {M} 条`、`{N} / {M} 个` | HistoryPage:221/344；AgentPage:567 | "当前/总数"没有说明，用户易误读为"第 N 笔 / 共 M 笔" | `显示 {N} / 共 {M} 笔` |
| 时长 | `N 秒 / N 分 / N 小时`、`<1 秒` | lib/format.ts:217–234 | 与"运行中"状态词交叉 | 保留时长格式；"运行中"→"进行中" |

### 5.4 状态词：同一状态的多套说法

| 概念 | 现有多套说法（位置） | 建议唯一说法 |
| --- | --- | --- |
| 交易保护 | 风控锁（Overview:214/215/226/227）、风险锁（PaperPortfolioPanel:13）、风控（OverviewPage:456、AgreementPage:21）、风控运行正常（HealthPopover:141） | 交易保护 |
| 数据状态 | 估值（Overview:221、History:431/444/477、DayDrawer:32/43、Settings:186 等 21 处）、有效/缺失/正常 | 数据正常 / 数据缺失 |
| 在线/可用/已配置/已连接/运行中/正常 | 服务在线（HealthPopover:80）、在线（HealthPopover:98）、可用（RuntimePanel:69）、已配置（RuntimePanel:70）、已初始化（71）、已完成（72）、已连接（387）、运行中（296/300）、正常（REASON OK） | 正常 |
| 未配置类 | 未配置（21 处）、未设置（AgentPage:788）、尚未配置（5 处）、未选择（HealthPopover:57）、未初始化（RuntimePanel:512）、未检测到（RuntimePanel:387）、尚未接入（HealthPopover:116） | 未设置 |
| 失败类 | 失败、异常、出错、不可用、受阻（BLOCKED）、未通过、读取失败 | 出错（附一句话原因） |
| 取消类 | 已申请取消（labels:40）、取消待确认（workspace:69）、已取消（labels:41） | 正在取消 / 已取消 |
| 结果未确认类 | 结果 / 费用不确定（labels:42/72）、调用结果未知（workspace:70）、状态未知，可能含未结费用（labels:84）、结果待核对 | 结果未确认（附原因） |
| 暂停类 | 已暂停（AgentPage:175）、已停用（AgentPage:217）、已关闭（225）、暂停（195）、已停止（RuntimePanel:32） | 已暂停 / 已关闭（按对象固定一个） |
| 读取动作 | 重新读取（13 处）、刷新（5 处）、刷新状态、刷新详情、读取资料、只读刷新、重新读取原记录 | 刷新 / 重试（统一两个动作词） |
| 关闭动作 | 关闭详情、关闭对话框、关闭提示、关闭导航 | 关闭 |
| 计数单位 | 笔 / 条 / 只 / 个 / 项（见 5.3） | 固定单位表 |

### 5.5 重复文案（可直接合并）

| 重复内容 | 位置 | 处理 |
| --- | --- | --- |
| 过期/失败横幅三种措辞 | OverviewPage:189 / HistoryPage:108 / AgentPage:160；另 AgentPage:754 | 统一为"更新失败，以下为上次成功的数据" |
| "重新读取" 按钮 | EmptyState:41、HealthPopover:137、PaperErrorPanel:64、Overview:192、History:111/636、AgentPage:134/163/767 等 13 处 | 统一"重试"（保留 1 个组件常量） |
| 健康弹层标题 | HealthPopover:76（title）、85（aria-label）、88（可见标题）三处同句 | 只保留可见标题一处 |
| Tab 标签两处定义 | lib/route.ts:32–38 与 HistoryPage.tsx:39–45 完全重复且未来会漂移 | 单一来源 |
| "AI 服务" | SettingsPage.tsx:42（设置分区名）+ ProviderPanel.tsx:112（面板标题） | 去掉面板内重复标题 |
| "研究任务" | AgentPage:532（卡片标题）、589（caption）、583（按钮） | 卡片标题/表格标题可合并或不重复 |
| "不需要填写任何路径" | RuntimePanel:218/392 | 保留一处 |
| 免责/否定式说明 | 74 条含"不代表/未核验/不构成/不会/不保证/尚未/不可用"等（如 Overview:168、PaperPortfolioPanel:10、History:230/713、DayDrawer:47/53/55、AgentPage:315/805/849、Settings:160/161/163） | 收敛为统一"说明"区块（每页最多 1 条短句 + 诊断信息） |
| 内部词密度 | 106 条主界面文案命中 Paper/Agent/Owner/EOD/PIT/WSL/Worker/Provider/Registry/BLOCKED/READY/payload/manifest/TWR/NAV/hash 等（93 个不重复值） | 按 §6 下沉；主界面目标 0 条命中 |

### 5.6 前后矛盾 / 失效指引（比措辞更严重）

| 问题 | 位置 | 说明 | 建议 |
| --- | --- | --- | --- |
| "下方冻结研究入口"不存在 | AgentPage:150 | `ResearchOperations` 未挂载到任何页面，用户被指引到不存在的入口 | 删除该分支或接入真实入口后再写文案 |
| "请先在 Agent 页面解锁本机控制" | MarketResearchPanel:44（未挂载） | 当前 `useAgent` 自动用本地令牌解锁，无解锁 UI | 接入前重写为真实流程 |
| 通知页读取了审批但不展示 | NotificationsPage:14–37（`readInbox` 返回 approvals，页面只渲染 notifications） | 用户可能漏掉需要处理的审批；且 notice.reason 不显示 | 展示 approvals 与 reason，或删除无用请求 |
| "解除需要你确认"但无入口 | OverviewPage:226 | 风控锁/交易保护无解除按钮或说明入口 | 删除"需要你确认"，改为"触发后自动暂停新的模拟交易" |
| "更新 Paper 快照需显式重启服务"与自动采集矛盾 | HealthPopover:141 | 行情/报告页显示每天自动采集与补录，且 RuntimePanel 提供历史补录 | 改为"数据由后台任务自动更新" |
| 同一策略状态两种写法 | HistoryPage:596（Paper 假设记录）与 StrategyDrawer:11/52（原文） | 列表与详情可能显示不同状态；非 snapshot 状态被吞掉 | 列表/详情共用同一映射 |
| 未知订单方向显示"卖出" | HistoryPage:390 | 非 Buy 即"卖出"，会误导用户 | 三分支：买入/卖出/方向未知 |
| 同一"估值状态"两种展示 | OverviewPage:221（有效/缺失）与 DayDrawer:43（原始 valuation_error） | 同一字段一处中文一处原始错误文本 | 统一"数据正常/数据缺失"，原始值进诊断 |
| 数据页硬编码状态 | SettingsPage:190（行情时效）、191（前向账户）、162（受阻） | 不随真实数据变化，可能长期与事实不符 | 改为按真实字段渲染或删除 |
| "不会再弹出任何许可或审批" | AgreementPage:63 | 与后续云端外发许可、任务审批、通知机制矛盾 | 改为"之后如需更改授权，可在设置中调整" |
| "有效期 10 年" | AgreementPage:17 | 与实际外发许可到期时间（grant valid_until）机制不一致 | 显示真实到期日 |
| 写死资金/限制/收益数字 | AgreementPage:13（¥100,000、2 只、¥20,000、2%/10%） | 与风险配置、账户实际初始资金可能不一致（ADR-018 阈值未定） | 从配置读取；无配置则改为文字描述 |
| "账户资产/账户净值/净值/本金/初始净值"混用 | Overview:236/290/323、DayDrawer:37、Chart:179、History:452、Agreement:13 | 同一个 NAV 概念五种叫法 | 统一"账户资产"，初始值统一"初始资金" |
| "今日盈亏" vs "当日盈亏" | Overview:242 vs PaperPortfolioPanel:13 | 同一指标两种词 | 统一"今日盈亏" |
| "不计入账户 NAV" vs "不计入账户资产" | HistoryPage:663 vs 648 | 同页两种说法 | 统一"不计入账户资产" |
| "累计费用" vs "累计模拟费用" | Overview:258 vs History:456 | 同一指标两种词 | 统一"累计费用" |
| 任务列表"等待执行"兜底 | AgentPage:627 | failed/outcome_uncertain 任务无 conclusion 时显示"等待执行"，与徽标"失败"冲突 | 按状态+原因显示 |
| 任务筛选"异常 / 费用不确定" | AgentPage:564 | 把两种不同状态混为一个筛选，与徽标文案不一致 | 拆分两项 |
| 出现原始英文"Paper-only" | RuntimePanel:293 | 与"模拟盘/模拟账户"体系冲突 | "仅模拟"或删除 |

### 5.7 术语/内部词命中统计（自动抽取，排除未挂载组件）

- 主界面含中文的字符串共 1,253 条（936 个不重复值）。
- 命中内部词（Paper / Agent / Owner / EOD / PIT / WSL / Worker / Provider / Registry / BLOCKED / READY / payload / manifest / TWR / NAV / hash 等）的 **106 条（93 个不重复值）**。
- 含免责/否定式措辞（不代表 / 未核验 / 不构成 / 不会 / 不保证 / 尚未 / 不可用 …）的 **74 条**。
- 纯占位符"—"出现 **51 次**。
- "重新读取"13 次、"未配置"21 次、"源日"13 次、"Paper"27 次、"Agent"11 次、"Owner"14 次、"EOD"19 次、"WSL"18 次。
- 结论：不是个别文案问题，而是**全站术语体系与状态呈现方式**问题，需要"术语常量 + 统一状态组件 + 诊断折叠区"三件套一起改，逐句替换会反复漂移。

---

## 6. 需下沉到"诊断信息"的技术信息清单

> 目标：普通用户主界面不出现下列任何内容；统一放在每页/每卡片的"诊断信息"折叠区（默认收起，可复制），或从主界面删除。折叠区标题统一为"诊断信息"，不使用"技术详情"。

| 序号 | 技术信息 | 当前出现位置 | 建议处理 |
| --- | --- | --- | --- |
| 1 | 后端枚举/未知状态（queued、failed、RUNNING、DEGRADED、BLOCKED_*、snapshot_record_only、not_configured 等） | §4.16 全部位置 | 主界面映射为 5 态；原始值进诊断 |
| 2 | 错误码/原因码（REAL_MARKET_DATA_EGRESS_DENIED、OWNER_TOKEN_REQUIRED、UPDATE_CHECK_FAILED、HTTP 状态码等） | lib/api.ts:33–39/113/261；RuntimePanel:205/226/247/263/323；AgentPage:1056；SettingsPage:237 | 一句人话 + 诊断保留代码 |
| 3 | 内部 ID：snapshot_id、order_id、fill_id、deployment_id、strategy_id、group_id、task_id、provider_id、registry、instance_id | SettingsPage:170；HistoryPage:272/384/592；FillDrawer:118/121；OrderDrawer:36/97；StrategyDrawer:66–69；AgentPage:287/616/702/707/803/858；NotificationsPage:96；PaperPortfolioPanel:16/20；WorkspaceStudies:33/42 | 仅诊断；主界面用名称/序号 |
| 4 | 哈希与账本字段：report_sha256、input_sha256、ledger_head、candidate_sha256、provider_hash、grant_sha256 | SettingsPage:221–224；AgentPage:803；MarketResearchPanel:125/165（未挂载） | 仅诊断 |
| 5 | 模型/配置/费率：model_id、provider_id、price_version、kind=fake、automatic_fallback、budget.currency | AgentPage:369/388/407/417/446/448/477/803/815/874；SettingsPage:174 | 配置页高级区；主界面只显示"默认 AI 模型" |
| 6 | 调用记录表（最大/已核对/估算、费率版本、周期、state） | AgentPage:847–882 | 诊断信息 |
| 7 | 预算的技术口径：micro 单位、预留、已核对、token 数 | AgentPage:330–351/788/1017/1024 | 主界面用 ¥；micro/token 进诊断 |
| 8 | WSL/venv/模型路径与发行版 | RuntimePanel:384–467（本机 AI 模型整节） | 折叠到"高级设置/诊断信息"；主界面只显示"本地预测引擎 正常/未设置" |
| 9 | 原始日志 | RuntimePanel:560–561 | 诊断信息 |
| 10 | 原始 JSON / 结构化详情 | WorkspaceStudies:11（技术详情与完整来源）；AgentPage:838/848；MarketResearchPanel:162/164/168（未挂载） | 诊断信息（统一组件） |
| 11 | 证据矩阵/来源清单（required_evidence、issue、evidence_class、study.kind、研究证据/工程/独立验收原值） | SettingsPage:162–163/177；HistoryPage:667–670；WorkspaceStudies:32 | 诊断信息；主界面最多一句"数据已核验/未核验" |
| 12 | 快照元数据：source、source_version、publication、mode、evidence_class、gaps、missing_opening_evidence_sessions、unverified_status_sessions、unobserved_calendar_days、timezone | SettingsPage:159–214；ModeBadge/EvidenceBadge 全站 | 诊断信息；主界面只保留"数据日期 / 更新于 / 数据是否正常" |
| 13 | PIT / TWR / daily.open / NAV / 会话 / READY / BLOCKED 等研究口径词 | SettingsPage:160；DayDrawer:47/53；PaperPortfolioPanel:10；WorkspaceStudies:36 | 诊断信息或删除 |
| 14 | 启动/维护命令与路径（--report-dir、scripts/start-dashboard.ps1、app.js/app.css、scripts/local-backup.py、dry-run、manifest） | PaperErrorPanel:15/16/31；SettingsPage:236/252/255/256 | 诊断信息 |
| 15 | 版本/构建/技术栈（__BUILD_SHA__、local build、React 19 + TypeScript + esbuild、Rust stratided、127.0.0.1、CDN、遥测、N100） | SettingsPage:248–257；UserMenu:124；HealthPopover:89/91 | 只保留"版本 v…"；其余进"关于 › 诊断信息"或删除 |
| 16 | 部署/策略内部字段（frozen_version、deployment_id、group_id、strategy_id、snapshot_record_only） | HistoryPage:568–599；OrderDrawer:94–103；PositionDrawer:130–139；StrategyDrawer:63–72；FillDrawer:121–123 | 诊断信息；主界面只显示"策略版本（仅记录）" |
| 17 | 组合批次内部语义（NO_FILL、NO_TRADE_REBASE、冻结容量、编译拒绝、批次、capacity_scope） | PaperPortfolioPanel:8–26 | 诊断信息；主界面保留"模拟交易计划/执行结果"两句人话 |
| 18 | 交易执行假设与来源版本（execution_assumption、source_version、simulated_at/risk_checked_at 原始字段） | FillDrawer:115–120 | 诊断信息；主界面统一"按次日开盘价模拟成交 / 模拟成交时间" |
| 19 | 数据单位/复权口径（价格为元、成交量为手、金额为千元、未复权） | SettingsPage:161 | 诊断信息；主界面显示格式化后的 ¥ / 股 |
| 20 | 运行环境细节（Windows 11、WSL2、Python 运行时、venv、TimesFM、端口、PID、实例 ID、登录任务名/机制） | RuntimePanel:293/337–342/384–467；SettingsPage:254 | 诊断信息 |
| 21 | 健康检查原始字段（service、market_data、forward_account、agent、notifications、refresh_policy） | HealthPopover:94–130 | 主界面 5 态；原始值诊断 |
| 22 | 通知/审批内部字段（approval.action_sha256、expires_at、authority） | lib/workspace.ts:4–11；当前未渲染 | 接入时只显示用户可理解字段，其余诊断 |
| 23 | 原始时间戳与日期格式（YYYYMMDD、ISO 带 T/Z、epoch、时区串 Asia/Shanghai） | AgentPage:234/787/800/874；WorkspaceStudies:25/35；SettingsPage:183/170；MarketResearchPanel:125（未挂载） | 主界面统一格式化北京时间；原始值诊断 |
| 24 | 研究任务请求字段（start_day、end_day、source_day、input.version、provider_hash） | AgentPage:787/800–803 | 主界面显示"研究区间/数据日期"；其余诊断 |
| 25 | "不调用模型/不发起推理/不做前端改写/只入队/不会自动重发"等实现承诺 | AgentPage:277/287/805/849/898；HistoryPage:405；OrderDrawer:62；DayDrawer:53；HistoryPage:718 | 删除（用户不需要知道实现方式） |
| 26 | 搜索提示中的内部词（订单号、原因、策略） | HistoryPage:195/328；AgentPage:555 | 简化为"搜索证券/策略/订单" |

---

## 7. 审计摘要（Top 20 最严重问题）

| # | 严重度 | 问题 | 证据位置 | 影响 |
| --- | --- | --- | --- | --- |
| 1 | P0 | 主导航/页面标题/账户菜单仍是内部词：Agent 管理、Paper workspace、本机 Owner、Paper 工作空间 | lib/route.ts:27；Sidebar:34；UserMenu:77/85/86/96；AgentPage:94 | 用户第一眼看到的是开发者模型，不是投资产品 |
| 2 | P0 | 状态枚举直接或兜底渲染超过 50 处（含 hover 显示 raw 状态） | §4.16；Badges:31/42/50；RuntimePanel:82/258/296；StrategyDrawer:11；HealthPopover 多处 | 用户看到 queued/BLOCKED/CNY 等无法理解的词，且无法判断真实状态 |
| 3 | P0 | 失败/异常任务没有一句话原因；通知页完全不显示原因；列表兜底显示"等待执行" | AgentPage:626–627；NotificationsPage:96–99；HistoryPage:599 | 用户无法知道为什么失败、是否需要处理 |
| 4 | P0 | 未知状态统一退化为"状态待核对 / 资格待核对 / 待核对（见技术详情）/ 未知模式" | Badges:18/43/51；AgentPage:207/236；workspace.ts:76；api.ts:44 | 用禁用词替代真实状态，等于没有状态 |
| 5 | P0 | "84" 一个数字三种语义四个说法，且混入 READY/BLOCKED/会话 | Overview:455；PaperPortfolioPanel:26；RuntimePanel:518/531；Agreement:17；MarketResearchPanel:98/149 | 用户无法知道进度含义，暖机/补录/外发窗口被混为一谈 |
| 6 | P0 | 风控锁整套旧词（风控锁/账户锁/策略锁/风险锁）且承诺"解除需你确认"但无入口 | Overview:214–227；PaperPortfolioPanel:13 | 交易保护无法被普通用户理解，且承诺了不存在的操作 |
| 7 | P1 | 数量词混用，同一卡片内"N 只 / 0 条"并存 | Overview:336 vs 385–386；History:555；AgentPage:567/675 | 基础信息可信度受损 |
| 8 | P1 | 金额格式不统一（协议页无小数；预算出现后端币种 CNY；micro 单位直接让用户输入） | Agreement:13/21；AgentPage:309/325/1017/1024；ProviderPanel:138 | 用户可能输入/理解错误金额 |
| 9 | P1 | 日期时间 9 种说法、5 种格式，时区仅一次出现 | §5.2；History:471；AgentPage:234/800；Settings:183 | 无法判断"这条数据是哪天的" |
| 10 | P1 | 策略/部署/研究档案术语体系（冻结部署/冻结版本/部署标识/策略档案/研究档案/Registry/独立验收） | History:554/565/568；StrategyDrawer:40–69；OrderDrawer:94–103；WorkspaceStudies:42 | 策略记录无法被理解；研究结果被误读为交易许可 |
| 11 | P1 | 数据连接页整页技术字段（snapshot_id、sha256、evidence_class、PIT、TWR、daily.open、--report-dir） | Settings:159–237 | 普通用户无法完成"数据是否正常"的判断 |
| 12 | P1 | 关于页整页开发者信息（构建 SHA、React/esbuild、脚本路径、N100 计划） | Settings:248–257 | 占用了唯一"关于"页面，却没有用户需要的信息 |
| 13 | P1 | 运行与安装页整页 WSL/venv/manifest/PID/Release/原始错误码 | RuntimePanel:21–561 | 出错时用户只见技术码，得不到可执行建议 |
| 14 | P1 | 健康弹层三套在线词 + 127.0.0.1/local/Paper，且"更新快照需显式重启"与自动采集矛盾 | HealthPopover:76–141 | 用户无法判断系统是否正常、数据是否最新 |
| 15 | P1 | 大量"写给开发者的话"（不调用模型、不做前端改写、持久队列、列表读取不会调用模型） | AgentPage:287/805/898；History:405；OrderDrawer:62；DayDrawer:53 | 文案冗长且答非所问 |
| 16 | P1 | 失效指引：下方冻结研究入口不存在；Agent 页面解锁不存在；通知页不展示 approvals | AgentPage:150；MarketResearchPanel:44；NotificationsPage:14–37 | 用户按提示操作会找不到任何东西 |
| 17 | P1 | 策略状态被压成"Paper 假设记录"；未知方向显示"卖出"；DayDrawer 估值状态直出错误原文 | History:390/596；DayDrawer:43 | 状态/方向错误会直接影响判断 |
| 18 | P1 | 首次使用页把 10 年/84/2%/10%/¥100,000/2 只/2 万写死，并声称"不会再弹出任何审批" | Agreement:13/17/21/63 | 与真实配置/后续流程冲突，构成错误承诺 |
| 19 | P2 | 免责/否定式说明密度过高（74 条），三处 stale banner 措辞不同，"重新读取"13 次 | §5.5 | 重要信息被淹没，阅读负担大 |
| 20 | P2 | 两处重复定义 Tab 标签（route.ts 与 HistoryPage），"AI 服务/研究任务"标题重复，健康弹层标题重复三次 | route.ts:32–38；HistoryPage:39–45；Settings:42/ProviderPanel:112；HealthPopover:76/85/88 | 后续修改必然漂移，重复维护 |

### 7.1 建议修复顺序

1. **第一批（阻断理解，P0）**：统一状态组件（5 态 + 一句话原因）→ 删除所有原始枚举/兜底禁语 → 失败/通知补原因 → 交易保护术语与文案。
2. **第二批（术语与数字，P1）**：导航/页头/账户菜单/健康弹层术语替换 → 84/金额/数量/日期统一 → 策略/研究/数据页文案重写 → 失效指引修复。
3. **第三批（结构与降噪，P2）**：技术信息全部进"诊断信息"折叠区 → 关于/运行页重构 → 删除重复横幅与重复标题 → 免责说明合并。

### 7.2 需 Owner 决策的点（供汇总）

1. **金额与预算单位**：主界面是否统一到"元（¥）"输入/显示，micro 只进诊断？（影响 AgentPage 单任务预算输入与预算展示）
2. **84 的三个语义**是否都要在主界面露出，还是只保留"暖机进度 + 数据补齐进度"两处？（影响 Overview / RuntimePanel / MarketResearch 文案）
3. **首次协议页的关键数字**（初始资金、持仓上限、日亏损/回撤阈值、云端有效期、84 天）是动态读取配置还是保留静态说明？（涉及风险政策与 ADR-018 未定阈值）
4. **"诊断信息"入口层级**：放在每个卡片内折叠，还是统一放设置页？（影响所有技术字段的下沉方式）
5. **未挂载功能**（全市场自动研究/外发许可/冻结研究）是否在本阶段隐藏或删除，避免出现"请先去某页面"的失效指引？
6. **策略/研究记录**是否按目标术语表完全降级为"仅记录、高级折叠"，还是需要保留独立 tab？

---

## 附录 A：抽取与统计口径

| 指标 | 数值 |
| --- | --- |
| 审计基线 | HEAD `70b2828`（`feat/ui-product-ux`） |
| 源码文件 | 64 个 `.ts/.tsx`（不含 5 个 CSS），9,417 行，348,928 字节 |
| 抽取到的字符串/JSX 文本 | 3,999 条（含 import 过滤后） |
| 含中文的字符串 | 1,338 条，1,012 个不重复值；分布于 41 个文件 |
| 排除未挂载组件后的中文文案 | 1,253 条，936 个不重复值 |
| 含内部词的文案 | 106 条（93 个不重复值） |
| 含免责/否定式措辞的文案 | 74 条 |
| 本文件 §3 总表条目 | 639 条（不含 §4–§7 的枚举与专项表） |
| §4 枚举/直接渲染条目 | 230 条 |
| 未挂载组件条目 | 32 条 |
| 抽取工具 | Node.js + TypeScript Compiler API（AST），临时结果仅存本机临时目录，未写入仓库 |
| 复核方式 | 每条"原文"按最长中文片段回查 HEAD 源码行（§3 全表自动核对，见附录 B） |

### 问题类型分布（§3 总表，多选计数）

| 问题类型 | 命中条数（同一行可命中多类） |
| --- | --- |
| 术语 | 271 |
| 内部状态 | 132 |
| 中英混用 | 124 |
| 写给开发者的话 | 137 |
| 重复 | 31 |
| 前后矛盾 | 51 |
| —（合规，建议保留） | 38 |

> 639 条中 195 条同时命中 2 类及以上，说明多数问题不是孤立措辞，而是"术语 × 状态 × 技术说明"叠加。建议先修状态组件与术语常量，再逐页替换，否则会反复回归。

## 附录 B：复核结果

- 行号来源：AST `node.getStart()` 的行号；多行 JSX 文本取起始行。
- 复核脚本对 §3 每行表格的"位置 + 原文"做子串回查：若原文（截断到"…"前，变量以 N/{…} 归一）无法在对应源码行 ±1 行内命中，则标记为待核。
- 复核结论：§3 总表 639 条全部通过回查（638 条命中 HEAD 源码行；1 条为显式标注的"缺失"项，见 NotificationsPage:96）。§4 的 230 条枚举/直接渲染位置同样逐条对照源码。
- 说明：并行改造已开始修改部分文件；合并后行号会漂移，请以"原文"检索。未提交改动不属于本次审计结论。





