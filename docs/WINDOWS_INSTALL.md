# Windows · 安装与升级

[← 文档](README.md) · [使用指南](USER_GUIDE.md) · [常见问题](KNOWN_LIMITATIONS.md)

## 获取安装包

从 [GitHub Releases](https://github.com/handFOOLed/Stratide/releases) 下载与所需版本匹配的 `Stratide-Setup-<version>-x64.exe` 及校验文件，核对 SHA256 后运行。

| 内容 | 当前状态 |
| :--- | :--- |
| `main` 源码 | **0.3.1**（PR [#91](https://github.com/handFOOLed/Stratide/pull/91)） |
| 已核实的公开 Release 附件 | **0.3.0-rc2** |
| 0.3.1 安装包 | 开发者已报告本机构建成功；**尚未在 GitHub Releases 中核实附件上传** |
| 系统 | Windows 11 x64，当前用户安装 |

因此，**不要只根据 README 的源码版本假定 Releases 里已经有相应安装包**。若要运行最新 0.3.1 源码，可按本文下方构建。

## 首次安装

1. 运行安装程序，选择程序目录与数据目录。建议保留默认值：

   | 目录 | 默认位置 |
   | :--- | :--- |
   | 程序 | `%LOCALAPPDATA%\Programs\Stratide` |
   | 用户数据 | `%LOCALAPPDATA%\Stratide\data` |
   | 运行日志 | `%LOCALAPPDATA%\Stratide\logs` |

2. 默认端口为 **8710**，只监听 `127.0.0.1`。
3. 按需创建桌面图标；可选开启 **Windows 登录后后台启动**，默认无需开启。
4. 安装结束后双击桌面图标或开始菜单项，进入 Dashboard 并按 [使用指南](USER_GUIDE.md) 完成首次设置。

安装包自带 Python 运行时、服务和前端，不要求日常安装 Rust/Node。TimesFM 所需的 WSL2/ext4、venv 和模型权重需要自行配置。

## 升级、停止与卸载

- **升级**：建议先停止后台、备份原数据，再运行新版本安装包，沿用已有安装与数据路径。安装器按原本机配置迁移，避免创建平行的模拟账本。
- **停止后台**：开始菜单选择“停止 Stratide 后台”，或在软件的运行页面查看状态。
- **卸载**：Windows 应用列表卸载，默认**保留用户数据**。开始菜单“删除本地数据…”才是明确的删除动作，请谨慎使用。
- **WSL 模型**：升级与卸载不会自动删除用户的 WSL2 发行版和 TimesFM 权重。
- **日志**：诊断从运行页面和 `%LOCALAPPDATA%\Stratide\logs` 开始，不需要公开 API Key、Token、完整账本或私有配置文件。

## 从源码构建

开发依赖：PowerShell 7、Rust MSVC 工具链、Node/npm、Inno Setup 6.7.4、CPython 3.12.10 embeddable、tzdata wheel。具体固定哈希与下载说明见 [M3-PR04 工程记录](M3_PR04.md)。

在仓库根目录运行：

```powershell
pwsh -NoProfile -File scripts/build-windows-installer.ps1 -Version 0.3.1
```

**必须显式传入 `-Version 0.3.1`**：截至 PR #91，脚本默认参数仍是 `0.3.0`。

脚本会重新构建 Rust release 二进制与 Dashboard，然后由 Inno Setup 输出：

```text
dist/installer/
├─ Stratide-Setup-0.3.1-x64.exe
└─ SHA256SUMS.txt
```

PR #91 开发者报告的安装包为 **32,671,816 bytes**，SHA256：

```text
70589BDFD7EDDA5622584AC4E117A2A51F2179815450945DED244FC587BAA615
```

该哈希是**开发者报告**，不是仓库目前已验证的 Release 附件；自行重新构建或重打包可能产生不同 SHA。请以拿到的实际文件计算值为准。

## 验证

```powershell
# 运行本机隔离式产品检查（不使用真实凭据）
pwsh -NoProfile -File scripts/test-windows-product.ps1 -Port 8794

# 检查下载文件的哈希
Get-FileHash -Algorithm SHA256 "Stratide-Setup-0.3.1-x64.exe"
```

首次运行的接口权限、自动研究、T+1 Paper 假设、系统要求和已知技术边界集中在 [问题排查](KNOWN_LIMITATIONS.md)。项目为个人本地 **Paper-only** 应用；不连接券商执行真实资金订单。
