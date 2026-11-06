# Developer scripts

[← 文档](../docs/README.md) · [Windows 构建](../docs/WINDOWS_INSTALL.md) · [工程档案](../docs/ARCHIVE.md)

此目录用于构建、故障排查、研究和回归测试。**正常安装后不需要手动运行这些脚本。**

## Windows release

```powershell
# 发布时显式传入 -Version，与标签一致。脚本默认值是 0.3.2。
pwsh -NoProfile -File scripts/build-windows-installer.ps1 -Version 0.3.2

# 不使用正式账户数据的本地产品测试
pwsh -NoProfile -File scripts/test-windows-product.ps1 -Port 8794
```

产物保存在 `dist/installer/`。公开附件由 `.github/workflows/windows-release.yml` 在标签 `v*` 推送时构建并上传到 GitHub Releases。构建依赖、版本及校验方式详见 [安装手册](../docs/WINDOWS_INSTALL.md)。

## Core tools

| 用途 | 脚本 |
| :--- | :--- |
| EOD 数据 | `scripts/eod-operator.py` |
| 市场研究 | `scripts/market-research.py` |
| Paper 模拟 | `scripts/paper-portfolio.py` |
| 本地 TimesFM | `scripts/timesfm-cpu.py` |
| 本地备份/恢复 | `scripts/local-backup.py` |
| Dashboard API 回归 | `scripts/test-dashboard-api.py` |
| 自动研究回归 | `scripts/test-market-research.py` |

其它 `test-*.py` 对应历史模块，可能需要固定 fixture。不要在正式数据目录上运行会写状态的合成测试；优先使用隔离数据根。更完整的历史实验见 [M0–M3 工程档案](../docs/ARCHIVE.md)。
