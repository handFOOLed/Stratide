# UI 产品化改造：改造前后截图与验收证据

> 状态：2026-11-05 本轮改造完成后生成。截图与日志均为本机实际运行产物，
> 未使用设计稿、静态模拟图或占位数据。

## 1. 对比基线

| 项目 | 值 |
| --- | --- |
| 改造前代码 | 分支 `feat/ui-product-ux` 的基线提交 `70b2828`（另建独立 worktree 构建，未改动原分支） |
| 改造后代码 | 本轮工作树 `feat/ui-product-ux` 的最终提交（见 `git log --oneline`） |
| 页面矩阵 | 1280×900 / 1440×900 / 1920×1080 × 浅色/深色 × 13 个页面 + 首次使用协议页 = 每状态 84 张 |
| 入库存档 | `before/` 16 张、`after/` 26 张（含交互/抽屉/弹窗，见文件序号） |

## 2. 截图环境与数据来源（务必先读）

- 环境：Windows 11、Node.js 24.19.0、Edge（Playwright `channel: "msedge"`，headless）、
  前端由 esbuild 构建为单包静态资源。
- 后端：仓库发布产物 `dist/app/stratided.exe`（v0.3.0）以只读方式服务
  `docs/evidence/m0-pr03/sample-report` 六报告 fixture；另用本机可信研究 fixture
  （`--agent-init-fake` 生成的本地测试 Agent，CNY ¥5/日 / ¥100/月测试预算）展示
  AI 研究页的已配置状态。
- 未发生：真实 Tushare 请求、真实 DeepSeek 请求、付费调用、真实成交；fixture 的
  模拟成交与研究结论只用于展示界面，不能当作收益/研究证据。
- 本机真实安装数据（`%LOCALAPPDATA%\Stratide\data`，127.0.0.1:8710）全程只读，
  未修改、未删除；任务 #1/#10/#20 的判断见 `docs/UI_KNOWN_ISSUES.md` 第 3 节。
- 顶栏显示“后台任务未运行”是因为 fixture 以命令行启动、未启用登录自启；
  安装版产品在后台服务运行时显示“运行正常”。

## 3. 改造前（before/）

1. [总览 1440 浅色](before/01-overview-1440-light.png)
2. [总览 1280 浅色](before/02-overview-1280-light.png)
3. [总览 1920 浅色](before/03-overview-1920-light.png)
4. [总览 1440 深色](before/04-overview-1440-dark.png)
5. [交易记录·成交 1440 浅色](before/05-trade-fills-1440-light.png)
6. [交易记录·订单 1440 浅色](before/06-trade-orders-1440-light.png)
7. [交易记录·每日账本 1440 浅色](before/07-daily-ledger-1440-light.png)
8. [Agent 管理 / AI 研究 1440 浅色](before/08-ai-research-1440-light.png)
9. [通知 1440 浅色](before/09-notifications-1440-light.png)
10. [设置·外观 1440 浅色](before/10-settings-appearance-1440-light.png)
11. [设置·AI 服务 1440 浅色](before/11-settings-ai-1440-light.png)
12. [设置·数据连接 1440 浅色](before/12-settings-data-1440-light.png)
13. [设置·运行与安装 1440 浅色](before/13-settings-system-1440-light.png)
14. [设置·运行与安装 1440 深色](before/14-settings-system-1440-dark.png)
15. [设置·关于 1440 浅色](before/15-settings-about-1440-light.png)
16. [首次使用协议 1440 浅色](before/16-first-run-agreement-1440-light.png)

## 4. 改造后（after/）

前 16 项与改造前一一对应：

1. [总览 1440 浅色](after/01-overview-1440-light.png)
2. [总览 1280 浅色](after/02-overview-1280-light.png)
3. [总览 1920 浅色](after/03-overview-1920-light.png)
4. [总览 1440 深色](after/04-overview-1440-dark.png)
5. [交易记录·成交 1440 浅色](after/05-trade-fills-1440-light.png)
6. [交易记录·订单 1440 浅色](after/06-trade-orders-1440-light.png)
7. [交易记录·每日账本 1440 浅色](after/07-daily-ledger-1440-light.png)
8. [AI 研究 1440 浅色](after/08-ai-research-1440-light.png)
9. [通知 1440 浅色](after/09-notifications-1440-light.png)
10. [设置·外观 1440 浅色](after/10-settings-appearance-1440-light.png)
11. [设置·AI 服务与预算 1440 浅色](after/11-settings-ai-1440-light.png)
12. [设置·数据与行情 1440 浅色](after/12-settings-data-1440-light.png)
13. [设置·系统与诊断 1440 浅色](after/13-settings-system-1440-light.png)
14. [设置·系统与诊断 1440 深色](after/14-settings-system-1440-dark.png)
15. [设置·关于 1440 浅色](after/15-settings-about-1440-light.png)
16. [首次使用协议 1440 浅色](after/16-first-run-agreement-1440-light.png)

交互与详情（仅改造后）：

17. [成交详情抽屉（含诊断折叠）](after/17-fill-drawer-1440-light.png)
18. [订单详情抽屉](after/18-order-drawer-1440-light.png)
19. [每日账本详情抽屉](after/19-day-drawer-1440-light.png)
20. [高级记录（策略版本仅作记录）](after/20-advanced-records-1440-light.png)
21. [研究任务详情抽屉（结论→做了什么→花费→诊断）](after/21-task-drawer-1440-light.png)
22. [新建研究弹窗](after/22-new-task-modal-1440-light.png)
23. [数据质量详情（默认折叠，可复制）](after/23-data-quality-1440-light.png)
24. [重新补录二次确认](after/24-backfill-confirm-1440-light.png)
25. [通知全部标为已读后](after/25-notifications-read-1440-light.png)
26. [AI 研究 1440 深色](after/26-ai-research-1440-dark.png)

## 5. 本轮验收执行结果

| 检查 | 命令/方法 | 结果 |
| --- | --- | --- |
| TypeScript 严格类型检查 | `npm run typecheck` | PASS |
| 生产构建 | `npm run build` | PASS（app.js 445.1 KiB / app.css 114.5 KiB，单包本地资源） |
| 单元测试（金额/图表/日期） | `npm test`（tests/model.test.js） | PASS 4/4 |
| 新增状态与格式单测 | `npm test`（tests/status.test.js） | PASS 7/7 |
| 全站 UI 一致性巡检 | 本地 Playwright 巡检：3 宽度 × 2 主题 × 11 页面，扫描主界面禁用词、横向溢出、每页主按钮数、表格对齐、pageerror | **FINDINGS 0**（诊断折叠区按规范排除） |
| 截图矩阵 | 本地 Playwright 截图工具：13 页面 + 协议页 × 3 宽度 × 2 主题 | 每状态 84 张，无 pageerror |
| 真实浏览器交互 | 抽屉、弹窗、取消确认、全部已读、诊断展开、复制按钮 | PASS（截图见 after/17–25） |

说明：

- 巡检中唯一的控制台信息是 `/api/current/...` 返回 409（当前模拟账户未配置），
  这是 fixture 的真实状态，不是前端错误；界面已显示“尚未配置模拟账户”的空态。
- 仓库既有的 Playwright 浏览器用例针对 0.3.0 之前的 Owner 令牌解锁流程与旧文案，
  与本轮 UI 不匹配；本轮以新增单元测试 + 上述浏览器巡检/截图工具作为验收证据，
  旧用例的迁移列入 `docs/UI_KNOWN_ISSUES.md`。
- 截图生成脚本按仓库既有约定不入库（`apps/dashboard/scripts/ui-*.mjs` 被 .gitignore
  忽略，见提交 `775c60f`），生成步骤：构建 `dist` → 以 `--report-dir` 指向 fixture、
  `--assets-dir` 指向构建产物启动 `stratided` → Playwright 打开
  `#overview/#history/fills/#history/orders/#history/daily/#agents/#notifications/#settings...`
  逐页截图。完整 84 张原图保留在本机 `state/ui-product/shots/`（gitignored）。

## 6. 这些截图能证明 / 不能证明什么

能证明：页面信息架构、术语、状态徽标、空态/错误态、响应式布局、浅色/深色对比度、
诊断折叠区与复制入口、关键交互（抽屉/弹窗/确认）在真实渲染下工作。

不能证明：真实行情/真实研究收益、真实成交或券商能力、真实云端调用与账单、
安装包在干净机器上的 E2E（属于 #85 安装验收范围）。本产品仍是 Paper-only。
