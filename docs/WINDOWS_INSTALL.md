# Stratide Windows 安装、升级与卸载

> 适用于 **Stratide 0.3.0（M3-PR04 / Issue #85）**，Windows 11 x64。
> 仅 Paper 模拟；不连接券商、不使用真实资金。安装包不包含 Tushare Token、DeepSeek Key 或 TimesFM 权重。

## 1. 系统要求

- Windows 11 x64（开发验证环境：Windows 10.0.26300）。
- 当前 Windows 用户可写自己的 `%LOCALAPPDATA%`；**不要求管理员权限**。
- 安装包内含 CPython 3.12.10（embeddable）和 tzdata；日常运行不需要安装 Python、Node、Rust 或 Git。
- TimesFM CPU 研究需要 Owner 已有的 WSL2/ext4 工作树、模型和 `.venv`。安装包**不会**自动下载 GB 级模型；未配置时研究显示 **BLOCKED**，不会伪造完成。
- 只监听 `127.0.0.1`；不开放公网端口。

## 2. 安装

1. 运行 `Stratide-Setup-0.3.0-x64.exe`（与 `SHA256SUMS.txt` 同目录）。
2. 选择安装目录（默认 `%LOCALAPPDATA%\Programs\Stratide`）和数据目录（默认 `%LOCALAPPDATA%\Stratide\data`）。数据目录存放行情、Paper SQLite 账本、研究记录、日志和未知费用预留。
3. 设置本地端口（默认 8710，仅 1024–65535）。端口被占用时应用会拒绝启动并提示，不会误连或结束其他程序。
4. 桌面快捷方式默认创建。“登录 Windows 后自动启动 Stratide 后台”**默认不勾选**；勾选后仅对当前用户生效（Task Scheduler 延迟约 30 秒；若回退到当前用户 Run 键则无延迟），不自动打开浏览器。
5. 完成安装后可立即打开 Stratide。

升级：直接运行新版本安装包，使用相同的安装目录/数据目录。安装程序会先停止正在运行的后台，再替换程序文件；`runtime.json`、行情、账本、研究记录、日志和未知费用预留不会被删除或重写。

卸载：Windows 设置 → 应用 → Stratide → 卸载。卸载程序停止后台、删除登录自启任务/快捷方式/程序文件，**默认保留用户数据**。需要删除本地数据时，使用开始菜单的“删除本地数据…”单独执行；该操作会先停止服务并再次确认。WSL2 发行版、ext4 工作树、模型和任何其他目录都不会被删除。

## 3. 首次启动

双击桌面 **Stratide** 图标：

1. launcher 先探测本地实例、端口和健康状态。
2. 未运行：启动唯一后台 Supervisor → 启动 `stratided` → 健康检查通过 → 用默认浏览器打开 Dashboard。
3. 已运行：不启动第二个服务、第二个 Agent 调度链或第二个 Ledger writer，只打开现有实例。
4. 再次双击、重启后双击、休眠唤醒后双击：复用同一实例；不会重复产生付费调用或模拟成交。

首次打开会进入 **设置 → 运行与安装**：

- 查看后台服务、Supervisor、EOD watch、版本、数据目录和最近日志。
- **登录自启**开关（Task Scheduler 登录触发；若任务计划程序不可用则回退到当前用户 `Run` 键）。
- **Tushare Token**：只写入当前 Windows 用户凭据管理器，不回显、不入日志、不进入安装包。
- **EOD 行情采集**：显式初始化数据仓库并启用/安全停用采集。未初始化/未启用时不会发行情请求。
- **依赖诊断**：内置 Python、WSL2、TimesFM、Tushare 凭据、EOD 仓库、Paper 账户、研究 Agent 的真实状态；缺失时显示 `BLOCKED`。
- **WSL2 TimesFM 桥接**（可选）：填写已有 WSL 发行版、工作树、venv Python 与模型目录，保存后点“检测 WSL Worker”做一次真实前置探针。详见 §4.1。
- **首次设置完成**：标记后，双击默认打开总览。

研究自动开关、DeepSeek 预算（¥5/日、¥100/月）和真实行情云外发授权仍由既有 Owner 流程（设置 → 权限与安全）维护；安装向导不会提升预算、授予外发或代填 Paper 本金/风险限额。

### 开始菜单

- **Stratide**：同双击。
- **停止 Stratide 后台**：受控停止（不按未知 PID 猜测）。
- **启用/停用登录自启**。
- **打开数据目录 / 打开日志目录**。
- **删除本地数据…**（显式确认）。
- **安装与升级说明**、**卸载 Stratide**。

## 4.1 接入已有的 WSL2 TimesFM（可选，不重新下载模型）

安装包**不包含** TimesFM 权重，也不会自动下载 GB 级模型。若 Owner 已有 WSL2/ext4 上的 TimesFM 2.5 venv 与模型，可在“运行与安装 → WSL2 TimesFM 桥接”填入：

| 字段 | 示例 | 说明 |
| --- | --- | --- |
| WSL 发行版 | `Ubuntu-24.04` | 必须是 `wsl.exe -l -q` 列出的发行版 |
| 工作树 | `/home/owner/projects/Stratide` | WSL 内绝对路径；用来解析下面的相对路径 |
| venv Python | `.venv/bin/python` | 可写相对工作树或绝对路径；需含原锁定的 timesfm/torch/numpy 版本 |
| 模型目录 | `models/timesfm-2.5` | 含 `manifest.json`、`model.safetensors` 等；以硬链接方式复用，不复制、不修改 |

保存后 Supervisor 会重启唯一 `market watch` 使其生效（保存相同值不重启）。点“检测 WSL Worker”会实际运行一次：

- 发行版 / venv / 依赖版本 / 模型 manifest 校验；
- systemd-cgroup v2 + bubblewrap 隔离是否可用；
- 安装包里的 TimesFM 代码 SHA256 是否与 WSL 实际运行的代码一致。

检测结果只反映当时状态，`READY` 也不代表已完成真实研究或产生成交。未配置或检测失败时，研究/Paper 保持 `BLOCKED` 并显示具体原因（`TIMESFM_WSL_*`、`MODEL_NOT_PROVISIONED` 等），**EOD 采集继续**；不会伪造推理结果、不会发起替代云调用。

如需手工排查，可在装有安装版的机器上直接运行：

```powershell
$env:STRATIDE_STATE_ROOT = "$env:LOCALAPPDATA\Stratide\data"
& "$env:LOCALAPPDATA\Programs\Stratide\runtime\python\python.exe" -B -X utf8 `
  "$env:LOCALAPPDATA\Programs\Stratide\scripts\timesfm-cpu.py" preflight
```

## 4.2 日常运行与故障

- **登录自启**：后台 Supervisor 启动 `stratided` 和现有 `eod-operator.py market watch`；按 `Asia/Shanghai` 交易日和既有 16:10–18:00 窗口调度。登录自启不会自动打开浏览器。
- **停止**：开始菜单“停止 Stratide 后台”，或 `stratide-launcher.exe --stop`。停止先请求 Supervisor 退出，再由 Supervisor 结束自己的 service/watch；不会结束未知 PID。EOD 正在进行时立即停止可能留下未知云结果；重启后沿用既有 journal/预算/任务恢复规则，不盲目重发。
- **端口冲突**：若 `127.0.0.1:端口` 被其他程序占用，launcher 明确报错并以退出码 2 结束，不误连、不结束其他进程。修改 `%LOCALAPPDATA%\Stratide\runtime.json` 的 `port` 后重启（或升级时选择新端口）。
- **日志**：`%LOCALAPPDATA%\Stratide\logs\`（`supervisor.log`、`dashboard.*.log`、`eod-watch.*.log`、`launcher.log`）。安装包/日志不含 Token 正文。
- **数据位置**：`runtime.json` 的 `data_root`；默认 `%LOCALAPPDATA%\Stratide\data`。可指向带空格或中文的绝对路径（已测试）。
- **重复实例**：Supervisor 使用 OS 文件锁；launcher 通过健康检查和实例身份识别现有进程。Task Scheduler 任务使用 `IgnoreNew`，HKCU Run 回退也不会创建第二个 Supervisor。

## 5. 构建安装包（开发者）

### 固定构建依赖

| 依赖 | 版本/文件 | SHA256 |
| --- | --- | --- |
| Inno Setup | 6.7.4 `ISCC.exe` | `A549929319F9120716677C685535CA4671E4B937B5FDC87E2585F32D8EB30E8C`（安装程序） |
| CPython embeddable | 3.12.10 amd64 zip | `4ACBED6DD1C744B0376E3B1CF57CE906F9DC9E95E68824584C8099A63025A3C3` |
| tzdata | 2026.6 wheel | `0A10EEC6E13EF16B627FABED9A5F2BA61A62B1C67F327305F4E7E412A70B4AEC` |
| Rust | 1.98.1 + MSVC x64 | 本机工具链 |
| Node | 24.19.0 + npm 11 | 仅构建 Dashboard |

官方下载地址：Python `https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip`；Inno Setup `https://github.com/jrsoftware/issrc/releases/download/is-6_7_4/innosetup-6.7.4.exe`；tzdata 由 PyPI `tzdata` 项目获取。开发机将三个文件放在仓库上级的 `.tools\` 目录（`python-embed.zip`、`innosetup.exe`、`tzdata.whl`，Inno 静默安装到 `.tools\InnoSetup`）。

### 命令

```powershell
# 从仓库根目录；要求 MSVC、Node、Inno 已就绪
pwsh -NoProfile -File scripts/build-windows-installer.ps1 -Version 0.3.0
# 产物：
#   dist\installer\Stratide-Setup-0.3.0-x64.exe
#   dist\installer\SHA256SUMS.txt
```

构建脚本先构建 Rust release 二进制和 Dashboard，再组装 `dist\app`（服务端、CLI、launcher、研究 Agent 二进制、Dashboard、Python 运行时、research/scripts、文档），最后调用 ISCC。安装包不签名（无证书）；首次运行可能出现 SmartScreen 提示，请核对 SHA256。

可复现的本地 E2E（不读取凭据、不发行情/云请求、不产生 Paper 成交）：

```powershell
pwsh -NoProfile -File scripts/test-windows-product.ps1 -Port 8794
pwsh -NoProfile -File scripts/test-windows-product.ps1 -InstallTest
```

`-InstallTest` 编译同一 `[Files]/[Code]` 的测试变体（仅跳过快捷方式/卸载注册表，以适配受限开发沙箱），验证文件安装、配置写入、升级和数据保留。**真实安装包的开始菜单/桌面快捷方式和卸载注册表项需在普通 Windows 用户会话中执行**；本开发沙箱拒绝 HKCU/开始菜单写入，相关实测标记为 `NOT_RUN`。

## 6. 版本与完整性

安装包版本 `0.3.0`；SHA256 见同目录 `SHA256SUMS.txt`，并记录在 PR 说明与 `docs/evidence/m3-pr04/README.md`。安装包未签名。

## 7. 已知限制

- **研究/Paper 全自动链路**：安装包在 Windows 上运行既有 `market watch`；EOD 采集、Dashboard 和既有 Agent 配置可用。TimesFM CPU 推理仍要求 Linux/WSL 隔离环境，本安装包只做检测并报告 `BLOCKED`，**不会**自动执行 WSL Worker；因此未配置 WSL 时研究/Paper 阶段保持 BLOCKED，不伪造完成。复用既有 WSL 工作树运行研究仍是 M3-PR02 的既有流程，不在本安装包自动调度范围内。
- 真实 Tushare 全市场采集、DeepSeek 外发、TimesFM 结果和 Paper 成交均未在本次开发环境授权/执行；相关实测为 `NOT_RUN`。
- 登录/注销自启、真实 Windows 重启、休眠唤醒、浏览器自动打开和真实卸载注册表项在本开发沙箱中 `NOT_RUN`（详见证据文档）。
- 未做代码签名；未做 N100/Linux 服务器化；未新增第二套调度器、账本或预算库。