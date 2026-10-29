# Stratide 本地 Web Dashboard V1

关联 [Issue #20](https://github.com/handFOOLed/Stratide/issues/20)。本机 paper-only、只读、同源；展示启动时明确指定的一个完整六报告快照。总览与历史页面已实现，Agent / 通知 / 业务设置显示尚未实现；浅色、深色、系统主题可用。不提供网页导出或交易写入。

## Windows 启动

在本分支仓库根目录运行，需要已有 Rust、VS C++ Build Tools、Node.js 20.19+ / 22.12+ 或更新受支持版本、PowerShell 7。无 Docker、数据库服务或云模型依赖。首次安装使用锁文件内的免费开发依赖。

```powershell
# Owner 明确选择的现有报告目录，不自动寻找“最近实验”。
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'D:\Paper\account-report'

# 合成测试样例：4 个日期、2 笔模拟成交、1 笔拒单。仅用于软件验证。
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'docs/evidence/m0-pr03/sample-report'

# 可选：另行指定独立研究结果，绝不合并到账户 NAV。
pwsh -NoProfile -File scripts/start-dashboard.ps1 -ReportDir 'D:\Paper\account-report' -EvaluationFile 'D:\Research\evaluation.json'
```

打开 `http://127.0.0.1:8710`。脚本执行 npm ci、Vite 构建、MSVC Rust 构建，健康响应后打开默认浏览器；Ctrl+C 停止该次启动的服务。`-NoBrowser` 不打开浏览器，`-NoBuild` 复用已构建产物，`-Port 8716` 更换本机端口。含空格的目录通过参数数组传递。**不传 ReportDir 会显示未配置状态，没有默认资金或默认测试账户。**

手动构建与运行：

```powershell
npm --prefix apps/dashboard ci --ignore-scripts --no-audit --no-fund
npm --prefix apps/dashboard run build
./scripts/with-msvc.ps1 build --locked -p stratided
./target/debug/stratided.exe --report-dir 'D:\Paper\account-report'
```

独立二进制可通过 `--assets-dir <dist目录>` 指定已构建前端。Node 仅用于构建/测试，运行时只需 Rust 二进制与 dist。

## 数据与刷新契约

- 只接收现有 `report_schema=1 / ledger_schema=3` 的完整六报告：report.json、events.json、daily.csv、orders.csv、fills.csv、positions.csv。不支持中断前缀、observe-only forward 报告或 SQLite 路径。
- 启动时交叉校验 JSON/CSV、摘要与末日、持仓/预留、成交归属与费用，读完再次核对六文件未变化。失败时账户 API 返回 503，UI 显示不可用。缺估值是显式 null+reason，和坏文件分开。
- 六报告一致性检查**不是**重放校验账本链或独立策略验收。Owner 应指定既有权威报告。服务没有 Ledger::open、SQLite 连接、回放/撮合调用或文件写入，不取得 writer.lock。
- 成功加载后固定在内存；网页“重新连接”与刷新只读取该快照。**新报告发布完成后，停止并以明确目录重启服务才会更新**。没有目录监视、自动择新或多个实验拼接。
- 每个响应保留模式、source_version、源日/最后有效估值日、快照摘要、证据等级、缺估值原因、历史执行假设与来源缺口计数。“服务可达”只表示本次 HTTP 请求成功；行情是最后发布快照，不能承诺实时。
- historical_replay 保留 exploratory / 未核验 PIT 等级，synthetic_test 保留引擎测试标签。当前 v3 财务报告没有 forward_paper；observe-only 日志不产生净值/成交，页面明确显示“尚无前向模拟账户”。不支持的模式拒绝载入。
- 净值/现金/成本/费用来自原报告。累计 P&L = NAV − 初始 NAV − 净外部资金流；源日 P&L 仅在最后两个相邻报告日期都有有效 NAV 时计算，并扣除期间净外部资金流。不跨空估值取“前一个有效值”。收益率沿用整数基点口径，有资金流时不凭空计算 TWR。图表范围以报告末日为右界，默认 30D，不补齐日期，记忆选择。
- 单证券持仓市值仅从有效 NAV-cash 导出；策略表只表示冻结版本记录，不声称进程正在运行。独立策略绩效、行情小图和同期基准序列没有可靠输入时显示不可用。
- 可选 evaluation-file 只在独立 Tab 展示原研究结论；研究文件坏了不会改变账户 NAV。读取不触发 LLM 或重新评价。

## API 与测试

见 [API 契约](../../docs/DASHBOARD_API.md)。原生 JavaScript + Vite，Rust tiny_http 同源服务静态资源。生产端无 UI 框架、CDN、遥测或外部网络调用。HTTP 仅绑定 IPv4 127.0.0.1，不支持 LAN/公网；偏好仅保存在 localStorage。

```powershell
cargo fmt --all -- --check
./scripts/with-msvc.ps1 test --workspace --locked --offline
./scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline '--' -D warnings
npm --prefix apps/dashboard run build
npm --prefix apps/dashboard test
npm --prefix apps/dashboard run test:browser
python scripts/test-dashboard.py
```

浏览器测试默认使用已安装 Edge 的 Chromium 内核，可设置 STRATIDE_BROWSER_CHANNEL=chrome；浏览器缺失时报告 NOT VERIFIED，不伪造截图。测试用临时 synthetic fixture，无正式默认 mock。截图位于忽略目录 state/issue20-browser/。

68 日冻结数据在本机可访问时显式传入，不重新采集、不覆盖原数据：

```powershell
$env:STRATIDE_HISTORICAL_REPORT = 'D:\Paper\frozen-68-day-report'
$env:STRATIDE_EVALUATION_FILE = 'D:\Research\evaluation.json' # 可选
npm --prefix apps/dashboard run test:browser
python scripts/test-dashboard.py --historical-report $env:STRATIDE_HISTORICAL_REPORT --evaluation-file $env:STRATIDE_EVALUATION_FILE
```

实际 Windows 自测、截图、只读证据与局限见 [交付记录](../../docs/M2_PR01.md)。研究 Agent 是下一项独立任务入口，当前不存在 Agent 活跃、预算消费、通知发送或审批能力。
