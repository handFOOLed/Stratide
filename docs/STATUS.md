# Project status

[← 文档](README.md) · [安装](WINDOWS_INSTALL.md) · [项目历程](PROJECT_HISTORY.md)

**Stratide V2 · Windows · Paper-only**

| 项目 | 当前状态 |
| :--- | :--- |
| 源码版本 | **0.3.1**，`main` 已合并 [PR #91](https://github.com/handFOOLed/Stratide/pull/91) |
| 公开下载 | 已核实的 Releases 附件为 **v0.3.0-rc2**；0.3.1 发布附件尚未核实 |
| 本地安装 | Windows 11 x64 · 单实例 Launcher / Dashboard |
| 研究 | Tushare EOD、WSL2 TimesFM、受控 DeepSeek |
| 交易 | 多证券、统一 Ledger 的 **Paper 模拟** |
| 运行验证 | 开发者报告已做隔离测试；真实连续运行与收益资格需单独观察 |

## 已合并的工作

| 阶段 | PR | 交付 |
| :--- | :--- | :--- |
| Market | [#86](https://github.com/handFOOLed/Stratide/pull/86) | 全市场增量 EOD 与来源快照 |
| Research | [#87](https://github.com/handFOOLed/Stratide/pull/87) | TimesFM + 有范围限制的 DeepSeek 研究 |
| Paper | [#88](https://github.com/handFOOLed/Stratide/pull/88) | 多证券 Paper 账本与 T+1 事后假设 |
| Desktop | [#89](https://github.com/handFOOLed/Stratide/pull/89) | Windows 安装、单实例与 WSL2 桥 |
| Usability | [#90](https://github.com/handFOOLed/Stratide/pull/90) | 首次自动初始化、Dashboard 与后台研究可靠性 |
| Release | [#91](https://github.com/handFOOLed/Stratide/pull/91) | 0.3.1 版本标记与构建修复 |

## 下一步

当前版本可以作为本地研究/模拟工具使用。接下来应在实际 Windows 环境观察行情与研究任务是否按交易日推进，并确认下一次 Release 附件与源码版本一致。

- 用户操作：[使用指南](USER_GUIDE.md)
- 公开发行与校验：[Windows 安装](WINDOWS_INSTALL.md)
- 技术边界：[问题排查](KNOWN_LIMITATIONS.md)
- 历史实施记录：[项目历程](PROJECT_HISTORY.md) · [验收证据](evidence/README.md)

没有新的开发模块被默认授权；历史任务/ADR 记录不应被误读为当前已启用的券商或实盘交易功能。
