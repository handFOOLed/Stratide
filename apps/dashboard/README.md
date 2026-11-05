# Stratide Dashboard｜Windows V2

> **当前可用版本：Windows 0.3.0**。安装版通过桌面 Stratide 快捷方式启动或复用本地服务，并自动在默认浏览器打开 Dashboard；支持 EOD 市场状态、研究/预算、共享 Paper 组合、通知与运行诊断。**首次使用**：[用户教程](../../docs/USER_GUIDE.md) · [Windows 安装](../../docs/WINDOWS_INSTALL.md)；服务故障/模型配置：[已知限制](../../docs/KNOWN_LIMITATIONS.md)。

本篇下面是 **Dashboard 开发/兼容模式**的历史说明：`scripts/start-dashboard.ps1` 仍用于源码调试，并非普通用户启动安装版的必需步骤。Windows V2 四个模块已合并（#86–#89），旧“#85 尚未实现”已过时。

## 历史 Dashboard 开发资料

**V1 / Issue #77：** 现已支持当前 Paper 专用 v1 接口、原研究/OOS/Registry、持久审批通知与 Windows 启停/恢复，详见 [完整操作](../../docs/V1_COMPLETION.md)。总览读取显式 `--paper-ledger`，历史页保留 `--report-dir`；历史报告不能成为当前 NAV。下面原只读报告启动方式继续兼容。

关联 [Issue #20](https://github.com/handFOOLed/Stratide/issues/20) 与 [Issue #22](https://github.com/handFOOLed/Stratide/issues/22)。本机 paper-only、同源；总览/历史展示启动时明确指定的一个完整六报告固定快照。Agent 管理已接入持久研究任务、预算、模型选择、取消/暂停和 EOD；操作见 [Agent V1](../../docs/M2_PR02.md)。下述原 M2 开发快照中的通知状态为历史记录；#77 已接入持久通知和审批，浅色/深色/系统主题与 reduced-motion 保留。UI 已按 M2-PR03 重构为 React 19 + TypeScript + 共享设计系统；信息归属、token 与动效规范见 [UI 设计系统](../../docs/UI_DESIGN_SYSTEM.md)。不提供财务写入或网页导出。

## 旧版开发态 Windows 启动（不是可分发安装包）

在本分支仓库根目录运行，需要已有 Rust、VS C++ Build Tools、Node.js 20.19+ / 22.12+ 或更新受支持版本、PowerShell 7。前端单元测试直接导入 TypeScript，建议使用 Node 24（或支持内置 type stripping 的 22.18+）；生产构建本身仍可在 Node 20.19+ 运行。无 Docker、数据库服务或云模型依赖。首次安装使用锁文件内的免费开发依赖。

```powershell
# Owner 明确选择的现有报告目录，不自动寻找“最近实验”。
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'D:\Paper\account-report'

# 合成测试样例：4 个日期、2 笔模拟成交、1 笔拒单。仅用于软件验证。
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report'

# 可选：另行指定独立研究结果，绝不合并到账户 NAV。
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'D:\Paper\account-report' -EvaluationFile 'D:\Research\evaluation.json'
```

打开 `http://127.0.0.1:8710`。脚本执行 npm ci、esbuild 前端构建、MSVC Rust 构建，健康响应后打开默认浏览器；Ctrl+C 停止该次启动的服务。`-NoBrowser` 不打开浏览器，`-NoBuild` 复用已构建产物，`-Port 8716` 更换本机端口。含空格的目录通过参数数组传递。**不传 ReportDir 会显示未配置状态，没有默认资金或默认测试账户。**

手动构建与运行：

```powershell
npm --prefix apps/dashboard ci --ignore-scripts --no-audit --no-fund
npm --prefix apps/dashboard run build
./scripts/with-msvc.ps1 build --locked -p stratided
./target/debug/stratided.exe --report-dir 'D:\Paper\account-report'
```

独立二进制可通过 `--assets-dir <dist目录>` 指定已构建前端。Node 仅用于构建/测试，运行时只需 Rust 二进制与 dist。

## 旧六报告数据与刷新契约（历史兼容；现行 Paper 使用 /api/v1/*）

- 只接收现有 `report_schema=1 / ledger_schema=3` 的完整六报告：report.json、events.json、daily.csv、orders.csv、fills.csv、positions.csv。不支持中断前缀、observe-only forward 报告或 SQLite 路径。
- 启动时交叉校验 JSON/CSV、摘要与末日、持仓/预留、成交归属与费用，读完再次核对六文件未变化。失败时账户 API 返回 503，UI 显示不可用。缺估值是显式 null+reason，和坏文件分开。
- 六报告一致性检查**不是**重放校验账本链或独立策略验收。Owner 应指定既有权威报告。Paper 投影不调用 Ledger::open、回放/撮合或财务 SQLite 写入，不取得 writer.lock。Agent 使用自己的独立 SQLite 任务/费用目录。
- 成功加载后固定在内存；网页“重新连接”与刷新只读取该快照。**新报告发布完成后，停止并以明确目录重启服务才会更新**。没有目录监视、自动择新或多个实验拼接。
- 每个响应保留模式、source_version、源日/最后有效估值日、快照摘要、证据等级、缺估值原因、历史执行假设与来源缺口计数。“服务可达”只表示本次 HTTP 请求成功；行情是最后发布快照，不能承诺实时。
- historical_replay 保留 exploratory / 未核验 PIT 等级，synthetic_test 保留引擎测试标签。当前 v3 财务报告没有 forward_paper；observe-only 日志不产生净值/成交，页面明确显示“尚无前向模拟账户”。不支持的模式拒绝载入。
- 净值/现金/成本/费用来自原报告。累计 P&L = NAV − 初始 NAV − 净外部资金流；源日 P&L 仅在最后两个相邻报告日期都有有效 NAV 时计算，并扣除期间净外部资金流。不跨空估值取“前一个有效值”。收益率沿用整数基点口径，有资金流时不凭空计算 TWR。图表范围以报告末日为右界，默认 30D，不补齐日期，记忆选择。
- 单证券持仓市值仅从有效 NAV-cash 导出；策略表只表示冻结版本记录，不声称进程正在运行。独立策略绩效、行情小图和同期基准序列没有可靠输入时显示不可用。
- 可选 evaluation-file 只在独立 Tab 展示原研究结论；研究文件坏了不会改变账户 NAV。读取不触发 LLM 或重新评价。

## API 与测试

见 [Paper API](../../docs/DASHBOARD_API.md) 与 [Agent API](../../docs/AGENT_API.md)。前端为 React 19 + TypeScript + esbuild（单包 app.js/app.css），Rust tiny_http 同源静态服务，无运行时 CDN、外部字体请求或遥测。HTTP 仅绑定 IPv4 127.0.0.1，不支持 LAN/公网；显示偏好保存于 localStorage，Owner 令牌仅留内存。仅配置并授权后的研究后端可向确定的 HTTPS Provider 发送摘要。

```powershell
cargo fmt --all -- --check
./scripts/with-msvc.ps1 test --workspace --locked --offline
./scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline '--' -D warnings
npm --prefix apps/dashboard run typecheck
npm --prefix apps/dashboard run build
npm --prefix apps/dashboard test
npm --prefix apps/dashboard run test:browser
python scripts/test-dashboard.py
```

浏览器测试默认使用已安装 Edge 的 Chromium 内核，可设置 STRATIDE_BROWSER_CHANNEL=chrome；浏览器缺失或受限沙箱无法启动时报告 NOT VERIFIED，不伪造截图。测试用临时 synthetic fixture，无正式默认 mock。Playwright 截图位于忽略目录 state/m2-pr03-browser/。首轮受限环境的 jsdom/NOT VERIFIED 记录见 [M2-PR03 证据](../../docs/evidence/m2-pr03-ui/README.md)；第二轮精修在本机 Windows 普通用户会话用真实 Edge 执行完整套件（18/18），覆盖 1920×1080 / 1366×768 单屏、375px、五行分页、消失/出现滚动条、真实开合动效与稳定截图。最终仍以 Terra 独立 worktree 复测与 Owner 本机确认为准。

若 `%TEMP%` 被策略限制、`--agent-init-fake` 无法在系统临时目录创建配置，可把临时目录指到仓库忽略目录后再跑（仅影响本机测试夹具，不改变产品行为）：

```powershell
$env:TEMP = (Resolve-Path './state/tmp').Path
$env:TMP  = $env:TEMP
npm --prefix apps/dashboard run test:browser
```

68 日冻结数据在本机可访问时显式传入，不重新采集、不覆盖原数据：

```powershell
$env:STRATIDE_HISTORICAL_REPORT = 'D:\Paper\frozen-68-day-report'
$env:STRATIDE_EVALUATION_FILE = 'D:\Research\evaluation.json' # 可选
npm --prefix apps/dashboard run test:browser
python scripts/test-dashboard.py --historical-report $env:STRATIDE_HISTORICAL_REPORT --evaluation-file $env:STRATIDE_EVALUATION_FILE
```

原 Dashboard Windows 自测、截图与只读证据见 [M2-PR01](../../docs/M2_PR01.md)。研究 Agent 的历史接口见 [M2-PR02](../../docs/M2_PR02.md)；现行通知与审批已由 #77 接入。M2-PR03 的改造前/后缺陷、jsdom 验收和 NOT VERIFIED 说明见 [UI 证据](../../docs/evidence/m2-pr03-ui/README.md)；本机 jsdom 验收脚本为 apps/dashboard/scripts/dom-e2e.mjs 与 dom-states.mjs。