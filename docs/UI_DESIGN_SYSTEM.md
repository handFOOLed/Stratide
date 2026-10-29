# Stratide UI 设计系统与信息架构

> 适用范围：M2-PR03（Issue #23）之后的前端。实现位于 [apps/dashboard](../apps/dashboard)。Paper/Agent API、Risk Kernel、Ledger、预算 Gate 与 Accepted ADR 均未改写。

## 1. 目标与边界

- 目标：克制、清晰、统一、流畅的本地 Paper 工作空间；参考 Linear 的交互连贯性、Vercel 的排版精度、DeepSeek Usage 的简洁信息密度，但不复制具体界面，也不做 Three.js 炫技大屏。
- 前端选型：**React 19 + TypeScript + esbuild**。选择理由：组件状态、焦点保持、共享组件与过渡可维护；esbuild 单进程构建产出 Rust 服务只允许的 `app.js` / `app.css`，无需新增静态路由。
- 非目标：新增财务写入、下单、券商、风险配置、预算加额、密钥读写或审批 API；把历史/合成结果伪装成连续前向收益。
- 本设计只改变信息架构、视觉、交互与前端测试；所有真实数据语义保持原样。

## 2. 页面—信息归属矩阵

原则：**一个数据块/业务目标只有一个主要归属页**。同一字段可在不同上下文出现，但必须承担不同用途，不得复制整块卡片、KPI 或图表。

| 信息块 | 唯一主页 | 存在理由 | 旧位置 / 重复 | 本轮处理 |
| --- | --- | --- | --- | --- |
| 账户 NAV、现金、可用、预留、当日/累计盈亏、收益率、最大日观察回撤 | 总览 | Owner 每次打开先看账户是否安全、资金在哪里 | 旧总览 hero + 历史「账户表现」KPI 条 | 历史 KPI 条删除；历史只保留逐日明细 |
| 资产曲线 | 总览 | 判断账户轨迹与估值缺口 | 旧总览 + 旧历史「账户表现」各一整张同图 | 历史图表删除；历史改为逐日核对表 + 行抽屉 |
| 持仓、可卖/未交收/预留、批次、成本、浮动盈亏、行情不可用原因 | 总览（表格 + 行抽屉） | 账户当前风险敞口与可执行数量 | 旧总览 compact 表 + 抽屉 | 保留在总览；抽屉只展示该持仓上下文，不复制账户页 |
| 风控锁、估值完整性、缺失估值 | 总览风险卡 / 顶部告警 | 先于收益展示「当前能不能新开风险」的只读证据 | 旧总览 warning + 散落 footnote | 统一风险卡与告警；服务可达不等于风控正常 |
| 最近最多五笔成交 | 总览 | 时间线摘要，不承担完整审计 | 旧总览 + 「查看全部」跳历史 | 保留五笔；**删除跨页「查看全部」** |
| 完整成交、订单与原因、费用拆分、执行假设 | 历史与报告 → 成交 / 订单 | 可追溯审计与对账 | 旧历史成交/订单 | 保留；共享行抽屉；搜索/筛选/本地排序 |
| 逐日净值、现金、隐含持仓、累计收益率、估值状态 | 历史与报告 → 逐日核对 | 独立核对用途：NAV 与现金是否对得上、哪一天缺估值 | 旧历史「账户表现」复制总览曲线 | **改为独立逐日核对视图，不放整张 NAV 曲线或大 KPI 卡** |
| 冻结部署记录、策略组、独立收益/回撤不可用原因 | 历史与报告 → 策略档案 | 报告中的冻结版本记录，不是运行状态 | 旧总览「策略记录」卡 | **移至历史**；总览不再重复 |
| 独立研究/回测档案（evaluation-file） | 历史与报告 → 研究档案 | 与账户 NAV 严格分离的保存结论 | 旧历史研究 Tab | 保留；明确「不计入 NAV、不重新评价」 |
| Agent 持久任务、结果、取消/暂停、模型、日/月预算、Token、费用、EOD | Agent 管理 | 研究控制台，不承担账户视图 | 旧 Agent 页 | 保留；增加状态筛选、分页、详情抽屉、预算/EOD 如实状态 |
| 通知渠道、待办、审批 | 通知与审批 | 只显示真实需要处理的事件 | 旧两栏空态 | 保持诚实未接入；**不伪造通知，不复制仪表盘** |
| 主题、动效、数据连接/来源证据、本机权限边界、关于 | 设置 | 偏好与可信配置，不放业务数据 | 旧设置 + 顶部主题选择 | 主题/动效可访问设置；数据摘要移入 disclosure；删除空卡片 |
| Web/快照/行情/Agent/通知服务可达性 | 顶栏服务状态浮层 | 全局上下文；不是业务数据看板 | 旧 health details | 保留为紧凑 popover；详细 provenance 只在设置 |
| Owner token | Agent 页面内存 | Owner 本机会话授权 | 旧 Agent 页 | 仅 React 内存；不进 URL/storage/DOM 持久文本 |

### 明确删除的重复入口

1. 总览「最近模拟成交 → 查看全部 → 历史」：删除。左侧导航已经是唯一主入口。
2. 策略/持仓 Drawer 内「查看完整订单 / 查看交易记录」：删除；抽屉只展示与所点对象相关的少量上下文。
3. 总览「策略记录」卡：移入历史「策略档案」，不保留两个入口。
4. 历史「账户表现」整张 NAV 图与资金 KPI：删除，改为「逐日核对」。
5. 任何页面标题右侧不再放装饰性 CTA；只有真正的业务动作（新建研究任务、暂停/恢复、取消、重试、刷新）才出现按钮。
6. 图表区间、指标、筛选、分页、Tab 属于当前页面局部操作，保留。

### 与旧 Q66 的明确偏差

旧 Q66 在「历史与报告」放置账户表现图与资金 KPI。本轮将其改为**逐日核对/明细**：保留源日期、NAV、现金、隐含持仓、累计盈亏、累计收益率与逐日估值状态；不再绘制与总览相同的资产曲线，也不重复 hero/KPI 卡。这样历史页面回答的是「每一天是否对得上」，而不是第二遍「账户现在怎么样」。

## 3. 视觉系统

### 3.1 字体

- 字族：`Inter, "SF Pro Text", "Segoe UI Variable Text", "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", sans-serif`。
- 数字/代码：`"SFMono-Regular", "Cascadia Mono", "Cascadia Code", Consolas, "Liberation Mono", monospace`。
- 不依赖运行时 CDN 字体，也不拷贝不明授权字体。Windows 上优先 Segoe UI Variable / Microsoft YaHei UI；安装 Inter 或 Noto Sans SC 时自动使用，未安装时诚实降级。
- 金额、百分比、股数、Token 使用 `font-variant-numeric: tabular-nums`，表格列宽稳定；数字变化不引起列重排或假滚动。

| Token | 值 | 用途 |
| --- | --- | --- |
| `--fs-2xs` / `--fs-xs` | 10.5px / 11.5px | 标签、表头、脚注 |
| `--fs-sm` / `--fs-md` | 12.5px / 13.5px | 辅助文字、正文密集区 |
| `--fs-base` | 14px | 正文 |
| `--fs-lg` / `--fs-xl` | 16px / 18px | 卡片标题、抽屉标题 |
| `--fs-3xl` / `--fs-display` | 26px / 42px | 页面标题、账户 NAV |
| `--lh-base` / `--lh-relaxed` | 1.55 / 1.68 | 中文正文可读性 |

### 3.2 色彩

Light：

| Token | 值 | 说明 |
| --- | --- | --- |
| `--page-bg` | `#f5f5f2` | 暖中性页面底色 |
| `--surface` | `#ffffff` | 卡片/表格表面 |
| `--sidebar-bg` | `#fbfbf9` | 侧栏 |
| `--text` / `--text-secondary` / `--text-muted` | `#181817` / `#555550` / `#73736c` | 三级文字 |
| `--border` / `--border-strong` | `#e5e5df` / `#d2d2ca` | 常规/强调边框 |
| `--accent` / `--accent-soft` | `#2f6fed` / `#eef3ff` | 链接、选中、图表 |
| `--gain` / `--loss` | `#b83a30` / `#0e7a4f` | A 股习惯：涨/正为红，跌/负为绿 |
| `--warning` / `--danger` | `#92570a` / `#b8332b` | 警告/危险 |

Dark：`#09090a` 页面、`#111113` 表面、`#26262a` 边框、`#f1f1ed` 主文字、`#82a8ff` 强调、`#ff9a90` / `#62d9a6` 涨跌色。完整值在 [tokens.css](../apps/dashboard/src/styles/tokens.css)。

### 3.3 空间、圆角、阴影

- 间距：4/8/12/16/20/24/32/40/48/64px。卡片内边距 16–24px；表格行高 52px（紧凑 46px）。
- 圆角：控件 5–9px；卡片 13px；弹层 18px；状态 pill 999px。
- 阴影克制：默认卡片仅 1px 边框 + 极轻阴影；Popover/Drawer/Modal 使用 `--shadow-pop` / `--shadow-drawer`，不用大面积发光。
- 背景层级：page → sidebar/surface-subtle → card → raised（弹层）。

## 4. App Shell 与滚动契约

```text
app-shell (grid, height 100dvh)
├─ sidebar (236px / 76px rail / hidden <960)
└─ workspace (唯一主滚动容器, overflow-y:auto, scrollbar-gutter:stable)
   ├─ sticky topbar (58px, 与内容同一 max-width/padding)
   ├─ main#main-content (max-width 1340px, 12 列 grid, clamp padding)
   │  ├─ page header / sticky tabs
   │  ├─ page content
   │  └─ footer
   └─ overlays / toast 通过 portal 渲染到 body
```

- **唯一主滚动容器**：`.workspace`。`html/body` 高度 100% 且 `overflow:hidden`，不存在 body 滚动。
- `scrollbar-gutter: stable` 常驻滚动条槽位。长短页面、Tab、Drawer、Modal 开合不改变内容盒宽度。
- 不使用逐页 `margin-left` / `padding-right: 17px` / 绝对定位补丁。Topbar、页面标题、卡片共享同一 `max-width` + `--page-pad`。
- Drawer/Modal 打开时：portal 到 body + 固定遮罩 + `inert` 背景，不锁 body 滚动、不修改 padding，因此没有横向抖动。
- 断点：`1199px`（侧栏变 icon rail）、`959px`（侧栏隐藏、出现移动导航）、`860px`、`760px`、`720px`、`560px`。表格只在自身容器内横向滚动，页面本身永不横向滚动。

## 5. 共享组件

| 组件 | 变体/行为 | 使用位置 |
| --- | --- | --- |
| Button / IconButton | primary / secondary / ghost / danger / link；sm/md/lg；loading、disabled、focus-visible、press | 全站 |
| Card / CardHead / CardBody / CardFoot | 普通、quiet、flush | 全站 |
| PageHeader | eyebrow、标题、说明、右侧 meta；标题可作为页面切换焦点 | 五个页面 |
| Tabs | 键盘 ←/→/Home/End、计数、动画下划线、sticky | 历史与报告 |
| SegmentedControl | 图表指标/区间、筛选、设置 | 总览、历史、设置 |
| Table | caption、满宽/横向滚动、行抽屉、数字右对齐、响应式 min-width | 全站数据表 |
| Field / TextInput / TextArea / Select | label、hint、error、invalid、focus ring、role=alert 错误 | 表单 |
| Badge / StatusDot | neutral/accent/success/gain/loss/warning/danger/outline/mono | 来源、订单、任务、模型 |
| EmptyState / ErrorState / Skeleton | 空态、错误态、加载骨架；诚实说明 | 全站 |
| Dialog / Drawer / Overlay | portal、focus trap、Escape、背景 inert、开合动画、移动端 bottom sheet | 详情、表单、导航 |
| Popover | 服务状态，Escape/外部点击关闭 | Topbar |
| Toast | success/danger/warning/info、可关闭、aria-live | 真实操作反馈 |
| ChartFrame / EquityChart | SVG、缺失值断开、hover 十字线、键盘可读摘要、零基线 | 总览 |
| ProgressBar | 预算占用、aria progressbar | Agent |
| Switch | role=switch、禁用/忙态 | EOD |
| Kv / Disclosure | 元数据、技术摘要折叠 | 抽屉、设置 |

## 6. 动效

| 场景 | 时长 | 缓动 |
| --- | --- | --- |
| Hover / Press / Focus | 140ms | `cubic-bezier(0.4, 0, 0.2, 1)` |
| Tab / 导航下划线 | 200ms | `cubic-bezier(0.22, 1, 0.36, 1)` |
| 页面/Tab 内容进入 | 240ms | `cubic-bezier(0.22, 1, 0.36, 1)` |
| Drawer / 移动导航 | 300ms（含关闭 240ms） | `cubic-bezier(0.22, 1, 0.36, 1)` |
| Modal / bottom sheet | 220ms / 180ms | `cubic-bezier(0.22, 1, 0.36, 1)` |
| Toast | 200ms / 160ms | `cubic-bezier(0.22, 1, 0.36, 1)` |

- 仅对 opacity/transform/颜色做动画；不改变布局，不做数字滚动、假收益跳动或持续闪烁。
- 图表进入只做轻微淡入，不延迟数据可读性；hover 由指针直接驱动。
- `prefers-reduced-motion: reduce` 和设置中的「减少动效」都会把动效降至 0.01ms；Toast/Drawer 仍可操作。
- 打开/关闭遮罩不会移动页面基线；关闭后焦点回到触发元素。

## 7. 数据真实性与安全

- 来源标签必须真实：`synthetic_test`、`historical_replay`、observe-only/forward 的差异在页面与设置中明确；历史收益不冒充连续前向账户。
- 金额用整数分、股数用整数股、收益率用整数基点；前端只在最终 SVG 投影时使用相对浮点，不经过 Number 改变展示金额。
- 缺失 NAV/估值：显示 `—`、告警与服务端原始原因；不插值、不补零、不用外部行情。
- 订单原 status/reason 保留；成交时间明确标注「模拟记账」与「开盘审查」，不称为券商成交时间。
- Agent：token 仅 React 内存；任务详情与列表只读取持久记录，不触发模型；预算/价格/授权只由本机可信设置维护。
- 未知费用、EOD 终态、Provider 可用性按服务端原值展示；不自行改写为「已完成」或「Provider 连接失败」。Issue #26 的后端语义修复不在前端伪造。

## 8. 可访问性

- Landmarks：`aside` 侧栏、`main#main-content`、`nav`、页面 `h1`；标题层级 h1 → h2 → h3。
- Skip link 跳到主内容；页面切换后焦点落到新 `h1`；Tab 切换后焦点停留在 Tab。
- Dialog/Drawer：`role=dialog`、`aria-modal`、labelledby、focus trap、Escape、关闭后恢复焦点。
- Tabs 支持方向键/Home/End；主题使用原生 radio；EOD 使用 `role=switch`；表单错误 `role=alert`。
- 所有图标 `aria-hidden` 且有文字/aria-label；状态不只靠颜色（同时显示文字/符号）。
- 数字表格右对齐、tabular-nums；正文对比度按 light/dark token 设计。

## 9. 响应式与验收矩阵

| 宽度 | 侧栏 | 内容 | 表格 | 弹层 |
| --- | --- | --- | --- | --- |
| 1920×1080 | 236px 全量 | max 1340px，12 列 | 完整 | 右侧 Drawer / 居中 Modal |
| 1366×768 | 236px 全量 | 流体，12 列 | 完整/局部横向 | 右侧 Drawer / 居中 Modal |
| 960–1199 | 76px icon rail | 流体 | 局部横向 | 同上 |
| 375×812 | 隐藏，顶部菜单 | 单列 | 卡片内横向滚动 | 全宽 Drawer / bottom sheet Modal |

必须实测：长表格 vs 短空态、Dashboard vs Agent vs 设置、Light/Dark、Drawer/Modal 开关、有无滚动条、reduced motion。验收以真实浏览器测量页面标题/侧栏/主卡片左缘坐标与 `scrollbar-gutter` 为准。

## 10. 验证与已知限制

- 本地已通过：`npm run typecheck`、`npm run build`、`npm test`（4/4）、jsdom 真实 API 功能验收（总览/历史/五类抽屉/设置/Agent 创建-详情-取消-暂停/令牌不落地）、空/坏/缺估值/离线状态验收。
- Playwright 测试已写好 12 项，覆盖 1920/1366/375、长/短页面、Drawer/Modal、Light/Dark、reduced motion、焦点与令牌安全；本机 DSH 沙箱为 Low integrity，Chromium 启动被拒绝（Mojo named pipe / `platform_channel` Access denied），因此 **真实浏览器截图与 Playwright 执行标为 NOT VERIFIED**，详见 [证据说明](evidence/m2-pr03-ui/README.md)。
- 未实现/不伪造：通知渠道、审批 API、真实 Provider 验证、后端 Issue #26 的 EOD/Provider 语义修复；这些保持后端原值并显式说明。
- 字体采用系统栈而非打包字体：避免新增静态路由、CSP 字体源与体积成本；在 Windows/macOS 中文环境下分别落到 Segoe UI Variable / Microsoft YaHei UI 与 SF/PingFang，安装 Inter/Noto 时自动提升。