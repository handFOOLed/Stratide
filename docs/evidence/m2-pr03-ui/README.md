# M2-PR03 UI 改造证据与验收记录

> 分支：feat/ui-redesign · 起点 base：e320751c71f2a1f73b588bed21b106f384897090（PR #25 合并后的 main）
> 已同步 main：995605c2693397b756e3be457b466633495582aa（含 PR #27）
> 范围：apps/dashboard/**、前端测试、docs/UI_DESIGN_SYSTEM.md 与本证据说明。未修改 Risk Kernel、Ledger、forward journal、Agent 预算/权限状态逻辑、六报告或 Accepted ADR。

## 1. 交付内容

- React 19 + TypeScript + esbuild 单包前端，替换旧的原生 root.innerHTML 架构；仍只产出 Rust 静态服务允许的 index.html、assets/app.js、assets/app.css。
- 统一 App Shell（aside / topbar / main / overlay）、唯一主滚动容器、scrollbar-gutter: stable、共享组件与设计 token。
- 五个主导航页面全部保留真实功能：总览、历史与报告、Agent 管理、通知与审批、设置；所有详情抽屉、Agent 任务 Modal、主题、加载/空/错误态。
- 信息归属去重：删除总览「查看全部」、抽屉同目的深链；历史「账户表现」改为逐日核对；策略档案移入历史；通知/审批保持诚实未接入。
- 详细规范见 [UI 设计系统](../../UI_DESIGN_SYSTEM.md)。

## 2. 本地执行结果

环境：Windows 11 · Node.js 24.19.0 · Rust 1.98.1 · Edge/Chrome 已安装 · DSH 沙箱为 Low integrity。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| TypeScript 严格类型检查 | npm --prefix apps/dashboard run typecheck | **PASS** |
| 生产构建 | npm --prefix apps/dashboard run build | **PASS**：app.js 约 370 KiB、app.css 约 70 KiB；单包、无 CDN |
| 金额/图表/日期单元测试 | npm --prefix apps/dashboard test | **PASS 4/4** |
| jsdom 功能闭环（真实 Rust Paper API + fake Agent API） | node apps/dashboard/scripts/dom-e2e.mjs | **PASS**：总览、成交/订单/逐日/策略/研究、通知、主题/动效、解锁、创建、详情、暂停、取消、恢复、锁定；打开详情不增加调用；token 不在 storage/DOM |
| jsdom 诚实状态（空/坏/缺估值/离线） | node apps/dashboard/scripts/dom-states.mjs | **PASS**：NO_SNAPSHOT、INVALID_SNAPSHOT、缺失 NAV 与 gap 原因、离线 |
| Playwright 测试发现 | npm --prefix apps/dashboard run test:browser -- --list | **PASS**：12 tests / 3 files |
| 真实浏览器执行与截图 | npm --prefix apps/dashboard run test:browser -- ... | **NOT VERIFIED**（见第 3 节） |
| 旧后端 Rust 测试 | 本轮未改 Rust；PR #27 后端回归由 Sol 提交 | 由后端 PR / 既有 CI 负责 |
| 68 日冻结历史报告回归 | 本机未找到可访问的完整六报告目录，未伪造历史数据 | **NOT VERIFIED**；设置 STRATIDE_HISTORICAL_REPORT 后由 Playwright historical 场景覆盖 |

### 2026-10-29 复审补丁

- .gitignore 的 state/ 锚定为 /state/，避免忽略 apps/dashboard/src/state；遗漏的五个状态管理源文件已纳入 Git：ThemeProvider.tsx、useAgent.ts、useHealth.ts、usePaperData.ts、useResearch.ts。
- 已合并最新 main 995605c2693397b756e3be457b466633495582aa（PR #27，后端状态语义修复）；UI 新增对 last_task_completed、skipped_superseded、skipped_paused 与 last_reason 的展示。
- 在该 HEAD 新建干净 worktree（无 node_modules/dist/state），npm ci --ignore-scripts 后：typecheck PASS、build PASS、单元测试 PASS 4/4、jsdom 功能闭环 PASS、Playwright --list 12 项；该 worktree 已删除。

### jsdom 功能闭环覆盖

    OK overview
    OK history fills + drawer
    OK history orders + drawer
    OK history daily
    OK history strategies
    OK history research
    OK notifications
    OK settings theme/motion
    OK agent unlock
    OK agent create + detail
    OK agent pause + cancel
    OK agent navigation + lock
    ALL DOM E2E CHECKS PASSED

    OK empty snapshot
    OK invalid snapshot
    OK missing NAV + settings gaps
    OK offline
    ALL STATE CHECKS PASSED

这些检查使用构建后的真实 dist/assets/app.js，真实调用本机 Rust stratided 与 fake Agent API；它验证行为/状态/文本/焦点相关逻辑，但不能替代真实浏览器的布局、滚动条、字体渲染与截图。

## 3. 真实浏览器 NOT VERIFIED 的原因

本机执行环境由 DSH 以 Low integrity 运行。Chromium/Edge 需要创建 Mojo named pipe，被系统拒绝：

    FATAL:mojo/public/cpp/platform/platform_channel.cc:187
    Check failed: . : Access is denied. (0x5)

Playwright 也因 runner 需要 spawn 子进程而失败：

    Error: spawn EPERM

尝试过：Edge/Chrome headless、--no-sandbox、--single-process、绝对/临时 profile、danger-full-access 沙箱升级；主机仍以 Low integrity 执行，浏览器无法启动。因此：

- **未生成 1920/1366/375 的真实浏览器截图，也未宣称已观察真实布局。**
- 已写好并发现 12 项 Playwright 测试；在正常 Windows 用户会话（非受限沙箱）中应可直接运行。
- 在 Draft PR #28 中明确保留该限制；不以设计稿/静态模拟图冒充真实截图。

### 在正常浏览器环境生成证据

    # 1. 构建前端与 Rust 二进制
    npm --prefix apps/dashboard ci --ignore-scripts --no-audit --no-fund
    npm --prefix apps/dashboard run build
    ./scripts/with-msvc.ps1 build --locked -p stratided

    # 2. 运行全部 Playwright 场景（自动启动 fixture 服务器）
    npm --prefix apps/dashboard run test:browser

    # 3. 可选：显式 68 日冻结报告与独立研究文件
    $env:STRATIDE_HISTORICAL_REPORT = 'D:\Paper\frozen-68-day-report'
    $env:STRATIDE_EVALUATION_FILE = 'D:\Research\evaluation.json'
    npm --prefix apps/dashboard run test:browser

    # 4. 本地 jsdom 功能验收：另开终端启动 sample report + fake agent（端口 8717）
    pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report' -AgentDir state/agent-ui-test -FakeAgent -Port 8717 -NoBrowser
    node apps/dashboard/scripts/dom-e2e.mjs

    # 5. 本地 jsdom 状态验收：另开三个终端启动 fixture（8718 空 / 8720 坏 / 8719 缺估值）
    node apps/dashboard/tests/serve-fixture.mjs empty 8718
    node apps/dashboard/tests/serve-fixture.mjs invalid 8720
    node apps/dashboard/tests/serve-fixture.mjs missing-nav 8719
    node apps/dashboard/scripts/dom-states.mjs

截图输出：state/m2-pr03-browser/（gitignored）。截图脚本在 apps/dashboard/tests/dashboard.browser.js 与 apps/dashboard/tests/agent.browser.js。

## 4. 改造前 / 改造后缺陷修复清单

| # | 改造前真实问题 | 改造后 |
| --- | --- | --- |
| 1 | 固定 sidebar + margin-left，body 滚动，无 stable gutter；长短页面切换时内容水平跳动 | 唯一 .workspace 滚动容器 + scrollbar-gutter: stable；topbar/main 共享同一 max-width/padding |
| 2 | 各页面各自 padding/margin 对齐；Topbar 与内容左缘不一致 | 统一 App Shell / 12 列 grid / clamp spacing；Topbar 与页面标题同基线 |
| 3 | root.innerHTML 大段重建；点击、轮询、主题切换丢失输入焦点/滚动/动画连续 | React 状态与共享组件；轮询不重建表单；Drawer/Modal 焦点陷阱与恢复 |
| 4 | 原生 dialog 无动画；dialog 与 body scroll lock 可能造成布局变化 | 自定义 portal Overlay + inert 背景；不锁 body 滚动；动画 220–300ms |
| 5 | 旧总览「查看全部 → 历史」与抽屉跨页深链重复导航 | 全部移除；侧栏/Tab/局部展开承担导航 |
| 6 | 历史「账户表现」复制总览整张 NAV 图与资金 KPI | 改为逐日核对表 + 行抽屉；无图表、无 hero KPI |
| 7 | 总览「策略记录」与历史策略信息分割，且旧 UI 假设 /api/strategies 为数组（实际为对象） | 策略档案统一在历史；前端按对象/数组兼容归一化 |
| 8 | 按钮样式零散：.button、.text-button、原生按钮混用，无 loading/danger/focus 统一 | 共享 Button/IconButton 五种 variant 与完整状态 |
| 9 | 无统一 Empty/Error/Loading；空态/错误态各页自行拼 | 共享 EmptyState/ErrorState/Skeleton，诚实文案 |
| 10 | 主题只有下拉选择；无 reduced-motion 偏好；表格数字未全部 tabular | 顶栏快捷切换 + 设置主题卡片/动效分段；全站 tabular-nums |
| 11 | 绘图用固定 viewBox，列宽/数字容易抖动；缺估值与真实交易语义不够显式 | 响应式 SVG、稳定列宽、断线不补点、hover 十字线、明确模拟/非实时标签 |
| 12 | Agent 页 2.5s 全页重绘；无状态筛选、无 token 内存说明、错误态弱 | 6s 静默轮询（仅可见/页面激活），列表不重建表单；筛选/分页/详情/错误/预算/EOD 完整 |
| 13 | 通知/审批为两栏空态，容易被误读为已实现 | 明确「服务未接入」、API 原值与设计边界；不伪造通知 |
| 14 | 设置混入空配置卡，和总览/Agent 数据重复 | 设置只留外观/数据连接/权限边界/关于；技术摘要可折叠 |
| 15 | 移动端 375 表格不友好，Health popover 可能溢出 | 表格容器内横向滚动、移动导航、底部 modal、移动端 popover 固定边距 |

## 5. 未改动 / 保持真实

- Paper API 六端点与 Agent API 契约未修改；金额/数量/日期仍是十进制字符串；Agent token 仍只在本机内存。
- synthetic_test / historical_replay / observe-only 标签原样保留；缺失 NAV 显示 — 与原因；不生成占位证券/成交/通知。
- Agent 预算、预留、调用费用、EOD 状态按服务端原值展示；PR #27 后 last_task_completed 等新语义按原值展示；Issue #26 的后续修复不伪造。
- 无下单/券商/实盘/预算加额/密钥写入入口；未引入外部 CDN、遥测或付费请求。

## 6. 剩余问题

1. 真实浏览器截图与 Playwright 执行：**NOT VERIFIED**（环境限制）；需在普通 Windows 会话复跑。
2. 通知渠道、审批服务、真实 Provider 验证仍未实现；页面明确说明。
3. 字体为系统栈；若团队要求 Inter/Noto Sans SC 打包字体，需要新增静态资源路由/CSP 字体源与字体子集体积评估，本轮未引入。
4. 历史逐日视图受只读 API 限制，没有逐日外部资金流/费用拆分；页面不推断，仅展示报告字段与服务端 gap。