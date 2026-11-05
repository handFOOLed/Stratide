# Stratide 使用教程

> 适用于 Windows 11 x64 的 Stratide 0.3.0。日常操作以安装版 Dashboard 为主；开发者构建、历史实验和原始评测不属于首次使用必需步骤。
>
> Stratide 是**本地 A 股盘后研究 + Paper 模拟交易**软件，不连接真实券商账户。行情采集、本地 TimesFM、云端 DeepSeek 与模拟交易分别受数据条件、开关、授权和风险限制。

## 1. 安装和打开软件

1. 前往 [GitHub Releases](https://github.com/handFOOLed/Stratide/releases)，获取 **`Stratide-Setup-0.3.0-x64.exe`**。建议同时保存相应发布版本的校验文件；发行版本与组件说明见 [Windows 安装手册](WINDOWS_INSTALL.md)。
2. 双击安装包。一般保持默认程序目录 `%LOCALAPPDATA%\Programs\Stratide` 和数据目录 `%LOCALAPPDATA%\Stratide\data` 即可。安装过程无需自己编译 Rust、安装 Node 或配置系统 Python。
3. 选择是否创建桌面快捷方式、是否启用「登录 Windows 后启动后台」。初次使用可先保持登录自启关闭。
4. 双击桌面 **Stratide** 图标。若服务尚未运行，启动器将启动本地服务并等待就绪；已经运行则复用现有实例，在默认浏览器打开 Dashboard。
5. 首次进入 **设置 → 运行与安装**。这里可以查看服务、EOD watch、登录自启、依赖诊断、数据目录和最近日志。安装指引完成后可以点击「标记完成」，以后双击默认进入总览。

通常不需要手动启动服务，也不需要打开命令行。默认 Dashboard 地址为 `http://127.0.0.1:8710`；如果安装时改了端口，请以实际配置为准。

## 2. 配置行情采集（Tushare）

进入 **设置 → 运行与安装 → 首次设置**：

1. 将自己的 **Tushare Token** 输入对应字段，点击「保存」。程序使用当前 Windows 用户的凭据管理器保存，不把 Token 写入安装包。
2. 在「EOD 行情采集」填写起始日期，格式为 `YYYYMMDD`，然后点击「初始化」。起始日期应依据你打算从哪天开始积累有效数据设置，而不是随意声称已有全部历史行情。
3. 点击「启用采集」。安装后的唯一后台 watch 在上海交易日既定的盘后窗口（默认约 **16:10–18:00**）按原数据/权限门禁工作；不需要每天手动点击采集。
4. 回到 Dashboard 的市场/数据状态区域，查看最近源日、覆盖率和阻断原因。某一接口未授权、交易日数据未就绪、覆盖不足时，软件会显示受阻而不是编造数据。

需要暂停行情采集时，点击「安全停用采集」。**启用行情采集**不等于启用云端研究或模拟交易。

## 3. 连接本地 TimesFM（使用现有 WSL2 环境）

如果只想先体验 Dashboard 与数据采集，可以稍后再配置此项。若要启用本地 TimesFM 自动研究，需已有 WSL2 Linux/ext4 中的模型、虚拟环境及所需 Worker 隔离依赖。

进入 **设置 → 运行与安装 → WSL2 TimesFM 桥接**，填写：

| 设置项 | 示例 | 用途 |
| --- | --- | --- |
| WSL 发行版 | `Ubuntu-24.04` | Windows 中已安装的发行版名称 |
| 工作树 | `/home/owner/projects/Stratide` | WSL 内绝对路径 |
| venv Python | `.venv/bin/python` | 已安装 TimesFM 依赖的 Python |
| 模型目录 | `models/timesfm-2.5` | TimesFM 2.5 模型和 manifest 所在位置 |

点击「保存 WSL 配置」，然后点击 **「检测 WSL Worker」**。若检测成功，说明本机入口、模型和隔离前提可用；实际研究仍要等待合格行情及研究配置。

保存改变后的 WSL 配置会重启**唯一 EOD watch**，因此建议在没有正在进行的采集/研究时修改。模型不存在或 WSL 不可用时，本地研究会标为 `BLOCKED`，不影响正常 EOD 数据采集。模型权重不会随安装包自动下载。

## 4. 启用自动研究与 DeepSeek

进入 Dashboard 的研究/Agent 页面及 **设置 → 权限与安全**，按现有 Owner 流程逐项检查：

1. 确认当前 Agent 绑定和模型/Provider 设置有效。本地 TimesFM 与云端 DeepSeek 是两条不同的执行路径。
2. 按需启用 **自动 TimesFM**；如需云端 Fusion，再单独配置并启用 **自动 DeepSeek**。不希望产生模型 API 调用时保持云研究关闭。
3. 真实市场数据及其派生摘要要发给 DeepSeek，必须在对应界面**独立确认接收方、用途、来源、允许字段及有效期**。仅保存 API Key 或启用本地模型不意味着已经授权真实数据外发。
4. 检查 Agent 的统一成本上限：**CNY ¥5/日、¥100/月**。它限制的是 Stratide 内部该 Agent 的调度与预留，不是 DeepSeek 账户在其他地方的总消费。
5. 研究使用完整有效的交易日上下文。首次使用可能需要逐日积累数据；当历史快照、权限或授权不足时，查看 Dashboard 的 `BLOCKED` 原因即可，不要为“快速出结果”关闭质量门禁。

云研究产生的策略是**研究候选**，不是自动获得交易或修改账户风险的权限。查看研究任务、费用预留和通知时，请区分“请求成功 / 用量估算 / 未知结果 / 官方核销”。

更多研究配置契约见 [M3-PR02](M3_PR02.md)。

## 5. 创建或绑定 Paper 模拟账户

**重要：安装向导不会代替你创建有本金的 Paper 账户，也不会擅自批准策略。** 初次启用多证券自动模拟，需要在已有 Owner Paper 账本上明确配置本金、风险参数、策略 Policy 和必要的保守假设授权。

- 若已有 Paper 账本，优先**绑定同一个账本**，不要因迁移安装版而再造一个平行账户。
- 若没有账本，需要使用原 `paper-eod-init` 命令和自己填写的 `Owner-PaperAccountConfig.json` 建立。具体配置 schema、固定金额策略、假设许可与原始命令见 [M3-PR03：Owner 配置](M3_PR03.md#本机运行)。
- 持仓、交易、现金与收益始终来自**同一个 Risk → Execution → Ledger** 模拟账本；研究净值和历史回测报告不能拼接到当前账户。

对已创建/绑定的账户，安装版附带的命令行入口仍可用于高级配置。PowerShell 示例（使用默认安装目录，`<...>` 为占位符，不要照字面复制）：

```powershell
$App = Join-Path $env:LOCALAPPDATA 'Programs\Stratide'
$env:STRATIDE_STATE_ROOT = Join-Path $env:LOCALAPPDATA 'Stratide\data'
$env:STRATIDE_BIN_DIR = Join-Path $App 'bin'
$Python = Join-Path $App 'runtime\python\python.exe'
$PaperCli = Join-Path $App 'scripts\paper-portfolio.py'

& $Python -B -X utf8 $PaperCli bind --ledger '<已有Paper账本目录>'
& $Python -B -X utf8 $PaperCli configure --input '<Owner-Paper-policy.json>'
& $Python -B -X utf8 $PaperCli status
```

如需暂停/恢复已有策略，可在符合你的 Owner 风控流程后调用 `$PaperCli pause` / `resume`。这些是高级操作；设置文件不是通用示例，必须与 [Policy 契约](M3_PR03.md) 和账户实际风险限制匹配。

模拟交易的时间顺序是：**T 日盘后冻结意图 → T+1 盘后获得日线 → 事后模拟以开盘价假设撮合 / NO_FILL**。它不会在开盘时向真实券商下单。

## 6. 日常使用

- **打开**：双击桌面 Stratide 图标；已运行时直接打开现有 Dashboard。
- **看行情**：检查最新盘后源日期、覆盖和来源质量。
- **看研究**：查看候选证券、TimesFM/DeepSeek 研究任务、授权状态与成本。
- **看模拟账户**：查看 Paper 现金、持仓、交易、假设成交与拒绝原因；不要将历史研究曲线当作当前真实净值。
- **持续运行**：在「运行与安装」启用「登录自启」，Windows 登录后后台运行，不自动弹浏览器。
- **暂停**：可以安全停用行情采集、关闭自动研究，或使用开始菜单「停止 Stratide 后台」；这几种操作含义不同。

## 7. 维护、升级、卸载

- **查看状态/日志**：设置 → 运行与安装 → 最近后台日志；也可以点击「打开日志目录」「打开数据目录」。
- **重新登录或重启**：如已启用登录自启，无需手动重启调度器；双击图标只是打开现有服务。
- **升级**：下载安装包新版本，使用原程序/数据目录；建议先确认后台停止并备份用户数据。升级并不授权更高模型预算或放宽 Paper 风控。
- **卸载**：Windows 设置 → 应用 → Stratide → 卸载。默认保留用户数据；开始菜单中的「删除本地数据…」是**另一项主动删除操作**，不要混用。

## 8. 遇到问题怎么办？

优先进入 **设置 → 运行与安装** 查看具体诊断，不必直接清空数据库、重建 Agent 或重装模型。

- 启动后未出现 Dashboard：检查本地端口、Supervisor 与服务状态，或使用桌面图标重新打开。
- EOD 没有更新：检查仓库是否初始化/启用、Tushare Token/接口权限、上海交易日和最新日志。
- TimesFM 显示 `BLOCKED`：检查 WSL 发行版、venv、模型路径并运行「检测 WSL Worker」。
- DeepSeek 不研究：检查研究自动开关、数据外发许可、预算/额度、84 会话上下文和任务状态。
- 没有 Paper 成交：检查是否已有 Owner Paper 账户和 Policy、候选及时性、资金与风险限制；`NO_FILL` 不等于服务故障。

详细错误条件、版本/证据范围及系统运行边界见 [故障排查与已知限制](KNOWN_LIMITATIONS.md)；开发者构建见 [Windows 安装手册](WINDOWS_INSTALL.md)。 
