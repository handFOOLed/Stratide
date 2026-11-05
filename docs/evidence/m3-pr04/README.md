# M3-PR04 证据：Windows 安装与本地运行（2026-11-05）

基线：`origin/main cbae6ca`（含 PR #86 `cf86668`、#87 `1677bed`、#88 `9a6a6ed`）。
环境：Windows 10.0.26300 / Windows 11 用户态，Rust 1.98.1 + MSVC x64，Node 24.19.0，
CPython 3.12.10（构建机），Inno Setup 6.7.4。**开发沙箱为 workspace-write**，对
`%APPDATA%`、开始菜单、桌面、HKCU 注册表和 Task Scheduler 的写入被拒绝；因此部分
“普通用户桌面会话”测试只能标记 `NOT_RUN`，不能冒充通过。

## 1. 产物

| 文件 | 值 |
| --- | --- |
| 安装包 | `dist\installer\Stratide-Setup-0.3.0-x64.exe` |
| SHA256 | `E9EC3032AF315A38DEE6C4E4ABFAC7094EB7A96171C2EC96E8652E203920CA83` |
| 大小 | 23,853,684 bytes（约 22.7 MiB） |
| 版本 | `0.3.0` |
| 签名 | 无（unsigned） |
| 组件清单 | `dist\installer\SHA256SUMS.txt`、`dist\app\BUILD_INFO.json` |

构建命令：

```powershell
pwsh -NoProfile -File scripts/build-windows-installer.ps1 -Version 0.3.0
```

构建脚本从固定输入构建：CPython embeddable 3.12.10（`4ACBED6…A3C3`）、tzdata 2026.6
（`0A10EEC6…4AEC`）、Inno 6.7.4（`A5499293…0E8C`）。安装包不包含 Token、Key、模型权重或真实账户。

## 2. 实际执行的测试

### 2.1 Rust 单元/集成

```text
cargo test -p stratide-runtime                 7 passed, 0 failed
cargo test -p stratided                        2 lib + 2 agent + 7 dashboard, 0 failed
```

覆盖：配置文件读取/写回、runtime.json 无 BOM、端口占用探测、状态文件原子替换、
Autostart XML 单一 LogonTrigger/LeastPrivilege/转义、诊断 JSON 契约、既有 Dashboard
只读/账本回归（未修改其语义）。

### 2.2 产品 E2E（无凭据、无行情/云/成交）

命令（在仓库根目录）：

```powershell
pwsh -NoProfile -File scripts/test-windows-product.ps1 -Port 8794
```

实际结果：**22/22 PASS**，摘要：

```text
PASS configure exit=0 home=...\state\issue85-test\e2e-20261105-125018
PASS config-bom-free
PASS first-launch exit=0
PASS health
PASS second-launch-same-instance
PASS single-dashboard
PASS runtime-status version=0.3.0 python=READY
PASS token-length
PASS runtime-write-requires-token status=401
PASS stop exit=0
PASS no-leftovers-after-stop
PASS port-conflict-refused exit=2
PASS no-service-on-foreign-port
PASS restart-after-stop
PASS dashboard-auto-restart
PASS one-dashboard-after-restart
PASS job-kills-children
PASS health-down-after-supervisor-kill
PASS restart-after-supervisor-crash
PASS upgrade-simulation-restart
PASS config-preserved
PASS data-preserved
RESULT PASS
```

该脚本通过 `--configure` 建立隔离 home，使用内置 Python 与 release 二进制；
它不创建 market 仓库、不读取凭据、不启动研究，因此不产生 Tushare/DeepSeek/TimesFM/Paper 事件。
“dashboard-auto-restart”在 dashboard 被强杀后等待 Supervisor 的 10 秒退避，确认只恢复 1 个实例。
“job-kills-children”强杀 Supervisor，确认 Windows Job Object 连带结束 service，健康检查变为 down。

### 2.3 Inno 测试变体（与真实安装包同一 [Files]/[Code]）

```powershell
pwsh -NoProfile -File scripts/test-windows-product.ps1 -Port 8793 -InstallTest
```

结果：`PASS installer-test-install exit=0`、`PASS installer-test-config`、`PASS installer-test-files`，RESULT PASS。
另一次独立的测试变体安装运行得到：

```text
INSTALL_EXITED=True CODE=0 FILES=800 CONFIG=True
HEALTH=11141ee9… PID=14044 LAUNCH=0
SECOND_SAME=True DASH_COUNT=1
RUNTIME managed=True version=0.3.0 python=READY market=NOT_CONFIGURED paper=NOT_CONFIGURED tushare=MISSING
STOP=0
UPGRADE_EXITED=True CODE=0 CONFIG_SAME=True MARKER=survives-upgrade FILES=800
AFTER_UNINSTALL_APP=False HOME=True DATA=True MARKER=True
```

测试变体只跳过 `[Icons]`、`[UninstallRun]`/`[UninstallDelete]` 和卸载注册表（`TestMode=1` 下
`Uninstallable=no`），以适配拒绝 HKCU/开始菜单写入的沙箱；`[Files]` 和 `[Code]` 与真实安装包相同。
真实安装包的快捷方式/卸载注册表见 `NOT_RUN`。

### 2.4 内置 Python 与安装态路径

```text
python -B scripts/test-stratide-paths.py
PASS installed and checkout path selection

<dist>\runtime\python\python.exe -B -c "import market_eod, market_research, paper_portfolio, candidates, stratide_paths; ..."
IMPORTS_OK <data root>

<dist>\runtime\python\python.exe -B scripts/eod-operator.py market status --root <empty>
{"state":"BLOCKED","reason":"WAREHOUSE_NOT_INITIALIZED", ... "cloud_egress":false}

<dist>\runtime\python\python.exe -B scripts/stratide-credential.py check
{"state":"MISSING","configured":false}
```

证明未配置时是明确的 BLOCKED 空态，没有行情/云请求；也证明 embeddable Python 可加载
sqlite3/ctypes/zoneinfo+tzdata 和既有 research 模块。

### 2.5 中文/空格路径、配置与升级保全

```text
CONFIGURE1=0 / HEALTH_OK / STOP1=0
CONFIG_PRESERVED=True（再次 --configure 不覆盖）
UPGRADE_HEALTH_OK MARKER=original-study-data VERSION=0.3.1
STOP2=0
AFTER_UNINSTALL app=False home=True data=True marker=True
```

路径为 `state\issue85-test\升级 测试\安装 目录\app` 与 `...\home\数据 目录`。
测试变体安装升级后 `CONFIG_SAME=True`、`MARKER=survives-upgrade`。

### 2.6 UI

```text
npm --prefix apps/dashboard run typecheck   PASS
npm --prefix apps/dashboard run build       PASS（v0.3.0，app.js 413.9 KiB / app.css 79.1 KiB）
```

新增“运行与安装”页复用既有 Card/Badge/Callout/Field/Switch/Toast 设计令牌；未改整站视觉。
**浏览器截图/交互 NOT_RUN**：Playwright 的 Chromium 未安装，系统 Edge 在
`chromium.launch({channel:'msedge'})` 和 headless 直接启动时均被本沙箱以
`spawn EPERM`/无输出阻止；因此不宣称做过浏览器实测。

## 3. NOT_RUN（明确未执行）

| 项目 | 原因 |
| --- | --- |
| 真实安装包创建开始菜单/桌面快捷方式、卸载注册表项 | 沙箱拒绝 `HKCU\...\Uninstall`、`%APPDATA%\Microsoft\Windows\Start Menu`、桌面写入；Inno 在 `Access is denied` 后回滚并以 exit 4 结束。日志：`state\issue85-test\install2.log`（见下） |
| 登录/注销自启实际触发、Task Scheduler 查询/创建 | 沙箱对 `schtasks` 与 ScheduledTasks CIM 返回 Access denied；HKCU `Run` 写入也被拒。代码/单元测试覆盖 XML，但真实任务未创建 |
| 真实卸载器（unins000.exe）流程 | 依赖上面的卸载注册表项；测试变体无卸载器 |
| 浏览器自动打开与实际页面截图 | Playwright 浏览器缺失；Edge 子进程 EPERM。仅验证 HTTP 页面/API 和构建 |
| Windows 真实重启、休眠/唤醒 | 环境不允许；只验证进程崩溃/重启、Job 清理 |
| 真实 Tushare 全市场 EOD | 未提供凭据，未授权；不发行情请求 |
| DeepSeek 实际外发/计费 | 未授权；保持默认 DENIED、¥5/日 ¥100/月 |
| TimesFM/WSL 真实推理与 Paper 成交 | 无 WSL 访问（`wsl.exe` 被沙箱拒绝）；安装态研究显式 BLOCKED，不伪造 |
| N100/Linux 服务化 | 不在本期范围 |

真实安装包失败摘录（**这是沙箱 ACL，而不是安装脚本编译/文件复制失败**）：

```text
Setup was unable to create the directory
"C:\Users\wsj20\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Stratide".
Error 5: Access is denied.
...
IPersistFile::Save failed; code 0x80070005. Access is denied.   （桌面 .lnk）
RegCreateKeyEx failed; code 5. Access is denied.                 （HKCU Uninstall）
```

同一次安装中 800 个程序文件已复制，随后因注册表失败回滚；这解释了为什么真实安装包在本机
不能完成“安装→快捷方式→卸载”，而不是应用逻辑失败。Owner 需在普通用户会话复测。

## 4. 限制与诚实声明

- 本模块**没有**把 Windows 上的 research 阶段自动转发到 WSL TimesFM Worker。安装包只做检测；
  未配置 WSL 时研究/Paper 明确 BLOCKED。完整 EOD→研究→Paper 自动链路仍待后续设计/实测。
- 安装包未签名。
- 未执行任何真实行情、云模型、Paper 成交或真实 Tushare 账户操作；本文中的任何 PASS 都不代表
  策略收益、PIT、可交易性或实盘资格。
- 开发自测不等于独立验收；Draft PR 不自行 Ready/merge。

## 5. 复现

1. 准备 `.tools\python-embed.zip`、`.tools\tzdata.whl`、`.tools\InnoSetup\ISCC.exe`（见 WINDOWS_INSTALL 的固定 SHA）。
2. `pwsh -NoProfile -File scripts/build-windows-installer.ps1 -Version 0.3.0`。
3. `pwsh -NoProfile -File scripts/test-windows-product.ps1 -Port 8794` 与 `-InstallTest`。
4. 在普通 Windows 用户会话手动执行真实安装包，验证开始菜单/桌面/卸载/登录自启；未执行前保持 NOT_RUN。
