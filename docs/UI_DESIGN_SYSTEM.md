# Stratide UI 设计系统与信息架构

> 适用范围：M2-PR03（Issue #23）之后的前端。实现位于 [apps/dashboard](../apps/dashboard)。Paper/Agent API、Risk Kernel、Ledger、预算 Gate 与 Accepted ADR 均未改写。**本版为 2026-10-29 Owner 首轮体验后的第二轮精修记录**：桌面单屏首页、资产曲线刻度与平滑、字号基线、成交详情层级、传统设置结构、DeepSeek Usage 风格背景、排序闪线与侧栏档案入口。

## 1. 目标与边界

- 目标：克制、清晰、统一、流畅的本地 Paper 工作空间；参考 Linear 的交互连贯性、Vercel 的排版精度、DeepSeek Usage 的背景与信息密度，不复制具体界面，也不做炫技大屏。
- 前端选型：**React 19 + TypeScript + esbuild**。组件状态、焦点保持、共享组件与过渡可维护；esbuild 单进程产出 Rust 服务只允许的 `app.js` / `app.css`，无需新增静态路由。
- 非目标：新增财务写入、下单、券商、风险配置、预算加额、密钥读写或审批 API；把历史/合成结果伪装成连续前向收益。
- 本设计只改变信息架构、视觉、交互与前端测试；所有真实数据语义保持原样。

## 2. 页面—信息归属矩阵

原则：**一个数据块/业务目标只有一个主要归属页**。同一字段可在不同上下文出现，但必须承担不同用途，不得复制整块卡片、KPI 或图表。

| 信息块 | 唯一主页 | 存在理由 |
| --- | --- | --- |
| 账户 NAV、现金/可用/预留、当日与累计盈亏、收益率、最大日回撤、累计费用、风控锁状态、账户身份与最后估值 | 总览上层左卡 | Owner 打开即看账户是否安全、资金在哪里 |
| 资产曲线（净值/盈亏/收益率） | 总览上层右卡 | 判断账户轨迹与估值缺口；历史页不再复制整图 |
| 持仓（数量/市值/浮动盈亏/可卖） | 总览下层左卡 | 当前敞口与可执行数量；固定五行、超出分页 |
| 最近最多五笔成交 | 总览下层右卡 | 时间线摘要，不承担完整审计 |
| 完整成交、订单与原因、费用拆分、执行假设 | 历史与报告 → 成交 / 订单 | 可追溯审计与对账；共享行抽屉 |
| 逐日净值、现金、隐含持仓、累计收益率、估值状态 | 历史与报告 → 逐日核对 | 独立核对用途，不放整张 NAV 曲线 |
| 冻结部署记录、策略组、独立收益/回撤不可用原因 | 历史与报告 → 策略档案 | 报告中的冻结版本记录，不是运行状态 |
| 独立研究/回测档案 | 历史与报告 → 研究档案 | 与账户 NAV 严格分离的保存结论 |
| Agent 持久任务、结果、取消/暂停、模型、日/月预算、Token、费用、EOD | Agent 管理 | 研究控制台，不承担账户视图 |
| 通知渠道、待办、审批 | 通知与审批 | 只显示真实需要处理的事件 |
| 外观、数据连接、权限与安全、关于 | 设置 | 传统桌面软件设置结构：左侧分类，右侧一次只显示一类 |
| 服务可达性 | 顶栏服务状态浮层 | 全局上下文，不是业务数据看板 |
| 本机身份与设置/关于入口 | 侧栏左下角档案菜单 | Codex 风格头像入口，不硬编码私人资料 |

### 明确删除的重复与冗长内容

1. 首页整块「数据说明」、每张卡片下的「不是实盘/不伪造/不补点」脚注、抽屉重复说明：删除。真实状态改由短 badge、真实字段与必要错误态表达（模式 badge、`只读快照`、缺失估值告警、风控锁条）。
2. 全局页脚（版本/构建/免责声明）：删除。版本与构建进入「设置 → 关于」与侧栏档案菜单；服务状态保留在顶栏浮层。
3. 总览「最近模拟成交 → 查看全部 → 历史」、抽屉内跨页 CTA：删除。左侧导航是唯一主入口。
4. 历史「账户表现」整张 NAV 图与资金 KPI：保留为「逐日核对」表，不复制首页资产曲线。
5. 成交详情中重复的日期、费用合计：删除重复字段；保留成交摘要、费用分项与关联订单。

## 3. 视觉系统

### 3.1 字体

- 字族：`Inter, "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", sans-serif`。不依赖 CDN 字体，Windows 落到 Segoe UI Variable / Microsoft YaHei UI 时诚实降级。
- 数字/代码：`"SFMono-Regular", "Cascadia Mono", "Cascadia Code", Consolas, "Liberation Mono", monospace`，金额、百分比、股数与 Token 使用 `tabular-nums`。
- **最小字号基线**：正文 15px，表格与次要文本不低于约 14px，标签类最小 12.5px。紧凑化通过压缩留白（内边距/行高）实现，不缩小字号硬塞内容。

| Token | 值 | 用途 |
| --- | --- | --- |
| `--fs-2xs` / `--fs-xs` | 12.5px / 13px | 大写标签、极小徽标、图表轴 |
| `--fs-sm` / `--fs-md` | 14px / 14.5px | 表格、次要文本、设置行标签 |
| `--fs-base` | 15px | 正文 |
| `--fs-lg` / `--fs-xl` | 16px / 18px | 卡片标题、抽屉标题 |
| `--fs-3xl` / `--fs-2xl` | 24px / 21px | 常规页面标题、单屏紧凑标题 |
| `--fs-display` | 38px | 账户 NAV（视口高度可放大至 46–54px） |

### 3.2 色彩（DeepSeek Usage 风格背景层次 + Stratide 自有品牌色）

Light：页面 `#f6f7f9`、侧栏 `#fbfbfc`、卡片 `#ffffff`、次级表面 `#f6f7f9`、下沉表面 `#eceef1`、边线 `#e5e7eb`（淡 `#eef0f3`）、主文字 `#191a1c`、次文字 `#4d5157`、弱文字 `#6a6f78`。

Dark：页面 `#0a0a0b`（近黑）、侧栏 `#0e0e10`、卡片 `#141416`、抬升表面 `#191a1c`、下沉表面 `#232427`、边线 `#26272b`、主文字 `#ededee`、次文字 `#b3b6bc`、弱文字 `#9aa0a9`。

品牌与语义色保留 Stratide 自身特征：强调蓝 `#2f6fed`（dark `#7ba5ff`）；**A 股习惯：涨/正为红 `#b3352c`，跌/负为绿 `#0b7350`**（dark `#ff9d94` / `#66d9a8`）；警告 `#8a5a08`、危险 `#b32e26`。仅借鉴背景与表面层级，不照搬外部品牌配色。

### 3.3 空间、圆角、阴影

- 间距 4/8/12/16/20/24/32/40/48/64px；卡片内边距 14–18px；数据表头 32px、行高 44px（紧凑 42px）。
- 圆角：控件 5–9px、卡片 12px、弹层 16px、状态 pill 999px。
- 阴影克制：卡片仅 1px 边线 + 极轻阴影；Popover/Drawer/Modal 使用 `--shadow-pop` / `--shadow-drawer`。
- 背景层级：page → sidebar → card/surface-subtle → raised（弹层）。

## 4. App Shell 与滚动契约

```text
app-shell (grid, height 100dvh)
├─ sidebar (236px / 76px rail / hidden <960, 左下角档案按钮)
└─ workspace (唯一主滚动容器, overflow-y:auto, scrollbar-gutter:stable)
   ├─ sticky topbar (56px, 与内容同一 max-width/padding)
   ├─ main#main-content (max-width 1600px, clamp padding 12–32px)
   └─ overlays / toast 通过 portal 渲染到 body
```

- **唯一主滚动容器**：`.workspace`；`html/body` 高度 100% 且 `overflow:hidden`。
- `scrollbar-gutter: stable` 常驻滚动条槽位；长短页面、Tab、Drawer、Modal 开合不改变内容盒宽度。
- 断点：1180px（首页双层降为单列）、1199–960px（侧栏 icon rail）、959px（侧栏隐藏 + 顶部菜单）、860px、760px、720px、560px。
- Drawer/Modal：portal + 固定遮罩 + 背景 `inert`，不锁 body、不改 padding，因此没有横向抖动。

### 4.1 首页单屏契约

- **两级布局**：上层「账户余额/风险 + 资产曲线」，下层「当前持仓 + 最近成交」。
- 1920×1080 与 1366×768 常规缩放**不产生纵向滚动**；通过压缩留白、图表高度与栅格实现，不缩小字号、不溢出裁切。
- 首页容器 `min-height: calc(100dvh - topbar - 26px)`、`max-height: 820px`；栅格两行 `0.95fr / 1.05fr`，窄于一档宽度时降为单列并正常纵向滚动（375px 与用户放大字体时）。
- 持仓表**固定五行可见高度**（`--table-row-h: 44px`）：少于五条维持容器高度但不造假行；超过五条用「上一页 / 页码 / 下一页」分页，页脚显示「第 a–b 条 / 共 n 条」。
- 最近成交只取最近五笔，**不分页**。

### 4.2 设置结构

- 左侧分类导航（外观 / 数据连接 / 权限与安全 / 关于），右侧**一次只呈现选中类别**；`role="tablist"` + `role="tab"` + `role="tabpanel"`，支持 ↑↓/Home/End 与 URL `#settings/<section>` 深链。
- 小屏（<860px）分类变为横向可滚动条，内容单列；不隐藏真实功能，不新增后端不存在的配置。

## 5. 共享组件

| 组件 | 变体/行为 | 使用位置 |
| --- | --- | --- |
| Button / IconButton | primary / secondary / ghost / danger / link；sm/md/lg；loading、disabled、focus-visible、press | 全站 |
| Card / CardHead / CardBody / CardFoot | 普通、quiet、flush、`card__head--compact` | 全站 |
| PageHeader | eyebrow、标题、说明、右侧 meta；`--compact` 单行版本（首页/设置） | 五个页面 |
| Tabs / SegmentedControl | 键盘、计数、下划线；图表区间/指标、筛选、设置 | 历史、总览、设置 |
| Table | caption、`border-collapse: separate`、行抽屉、数字右对齐、横向滚动 | 全站数据表 |
| Pager | 上一页 / 页码 / 下一页；`role="group"`、`aria-current` | 首页持仓 |
| Badge / StatusDot | neutral/outline/accent/success/gain/loss/warning/danger/mono | 来源、订单、任务 |
| EmptyState / Skeleton | 空态、错误态、加载骨架 | 全站 |
| Dialog / Drawer / Overlay | portal、focus trap、Escape、背景 inert、开合动画、移动端 bottom sheet | 详情、表单、导航 |
| Popover | 服务状态、侧栏档案菜单（`role="menu"`、Esc、点外关闭、焦点还原） | Topbar、Sidebar |
| Toast | success/danger/warning/info、可关闭、aria-live | 真实操作反馈 |
| EquityChart | 单条平滑曲线、hover/focus 单点、20% 淡虚线网格、缺失断开 | 总览 |
| Kv / Disclosure | 元数据、技术摘要折叠 | 抽屉、设置 |

### 5.1 资产曲线规则

- 轻微平滑：Fritsch–Carlson 单调三次插值；曲线在每段内不越过端点，因此不会制造新的高点或低点。
- 无常驻数据点；仅 hover / 键盘焦点出现一个提示点与竖直游标。
- **NAV 模式 Y 轴 0 → 10^ceil(log10(max)) **，max 取当前账户 NAV 与展示区间有效 NAV 的较大值（历史峰值不被截断）：560→1000、5600→10000；5 等分（每 20% 一条淡虚线）。
- 非 NAV 指标（累计盈亏、收益率）沿用含 0 的对称区间，不套用只支持正净值的 10 次幂刻度。
- 缺失估值保持断线：不插值、不补零、不改变金额；金额仍以整数分计算，仅最终 SVG 投影使用浮点。

### 5.2 成交详情层级

1. 头部：证券代码 + 方向/日期/模式 badge。
2. 成交摘要：成交金额（数量 × 价格）、费用合计、证券全名。
3. 费用分项：佣金 / 印花税 / 过户费；报告未拆分时如实说明，不显示重复合计。
4. 关联订单：订单号、状态、方向、委托/成交数量、限价、原始原因。
5. 折叠「时间与来源」：模拟记账/开盘审查时间、成交编号、执行假设、来源版本、组/策略/版本/部署。

## 6. 动效

| 场景 | 时长 | 缓动 |
| --- | --- | --- |
| Hover / Press / Focus | 140ms | `cubic-bezier(0.4, 0, 0.2, 1)` |
| Tab / 导航下划线 / 档案菜单 | 160–200ms | `cubic-bezier(0.22, 1, 0.36, 1)` |
| 页面 / Tab 内容进入 | 240ms | `cubic-bezier(0.22, 1, 0.36, 1)` |
| Drawer / 移动导航 | 300ms（关闭 240ms） | `cubic-bezier(0.22, 1, 0.36, 1)` |
| Modal / bottom sheet | 220ms / 180ms | `cubic-bezier(0.22, 1, 0.36, 1)` |
| Toast | 200ms / 160ms | `cubic-bezier(0.22, 1, 0.36, 1)` |

- 仅动 opacity/transform/颜色；不做数字滚动、假收益跳动或持续闪烁。
- `prefers-reduced-motion: reduce` 与设置中的「减少动效」把时长降到 0.01ms；内容仍可操作。
- **表格行不参与任何边框/背景过渡**：`border-collapse: separate` + 行分隔线由单元格独占，排序重排时不会出现一帧深色横线。

## 7. 数据真实性与安全

- 来源标签真实：`synthetic_test`、`historical_replay`、observe-only/forward 的差异以短 badge 呈现；历史收益不冒充连续前向账户。
- 缺失 NAV/估值：显示 `—`、告警与服务端原始原因；不插值、不补零、不用外部行情。
- 订单原 status/reason 保留；成交时间标注「模拟记账 / 开盘审查」，不称为券商成交时间。
- 风控锁：以短条展示真实锁数量与账户/策略分项；服务可达不代表风控正常。
- Agent：token 仅 React 内存；任务详情与列表只读持久记录，不触发模型。

## 8. 可访问性

- Landmarks：`aside` 侧栏、`main#main-content`、`nav`、页面 `h1`；标题层级 h1 → h2 → h3。
- Skip link 跳到主内容；页面切换后焦点落到新 `h1`；Tab/设置分类支持方向键与 Home/End。
- Dialog/Drawer：`role=dialog`、`aria-modal`、labelledby、focus trap、Escape、关闭后恢复焦点；背景 `inert`。
- 侧栏档案：`aria-haspopup="menu"`、`aria-expanded`、`role="menu"/"menuitem"`、Esc 与点外关闭、焦点还原。
- 图表可通过键盘聚焦并用 ←/→/Home/End 检查数值；所有状态不只靠颜色。

## 9. 响应式与验收矩阵

| 宽度 | 侧栏 | 首页 | 表格 | 弹层 |
| --- | --- | --- | --- | --- |
| 1920×1080 | 236px 全量 | 双层单屏，不滚动 | 完整 | 右侧 Drawer / 居中 Modal |
| 1366×768 | 236px 全量 | 双层单屏，不滚动 | 完整 | 右侧 Drawer / 居中 Modal |
| 960–1199 | 76px icon rail | 单列纵向滚动 | 局部横向 | 同上 |
| 375×812 | 隐藏，顶部菜单 | 单列纵向滚动 | 卡片内横向滚动 | 全宽 Drawer / bottom sheet Modal |

必须实测：单屏无滚动、长短页切换不位移、五行分页、Y 轴刻度、缺失估值断线、字号、主题、焦点与 reduced motion。

## 10. 验证与已知限制

- 本轮本机真实 Edge（Playwright，项目 `apps/dashboard/tests/*.browser.js`）18/18 通过；typecheck、build、单元测试 4/4 通过。证据截图写入被忽略目录 `state/m2-pr03-browser/`。
- 截图在动画稳定后捕获（`getAnimations().finished` + Playwright `animations:'disabled'`），另有独立用例验证 Drawer/Modal 真实动画与落位。
- 仍由 Terra 在独立 worktree 复测：真实 Edge 全量套件、1920/1366 单屏、375 适配、五行分页、排序无闪线、主题对比度；Owner 最终本机确认后才授权合并。
- 未实现/不伪造：通知渠道、审批 API、真实 Provider 验证；这些保持后端原值并显式说明。
- 字体采用系统栈而非打包字体：避免新增静态路由、CSP 字体源与体积成本。
