# 技术说明（原“关于”页开发笔记）

> 本文件承接原先放在 Dashboard「关于」页的开发笔记。产品界面只保留版本、检查更新与
> 反馈入口；以下信息面向开发者/Owner，不再出现在 UI 中。

## 技术栈与运行方式

- 前端：React 19 + TypeScript + esbuild 单包；构建产物只有 `index.html`、
  `assets/app.js`、`assets/app.css`，由本机 `stratided` 同源静态提供。
- 后端：Rust `stratided`（默认 `127.0.0.1`，只读 Paper API + 本机研究 Agent）。
- 本地资源：无 CDN、无外部字体、无遥测；所有请求只到本机端口。
- 桌面形态：Windows 11 安装包 + 登录自启后台（Supervisor/Launcher）；
  缓存/预测计算可在 WSL2 Ubuntu 上复用 TimesFM CPU。
- 数据：Tushare 盘后行情，不接实时行情、不接券商。

## 版本与构建

- 产品版本来自安装目录 `VERSION`（通过 `/api/runtime/status.product_version` 读取）。
- 前端版本/构建 SHA 由构建注入（`__UI_VERSION__` / `__BUILD_SHA__`）；
  `STRATIDE_UI_BUILD_SHA` 可覆盖，默认 `local`。
- 安装包构建：`pwsh -NoProfile -File scripts/build-windows-installer.ps1 -Version <semver>`，
  产物在 `dist/installer/`，同时生成 `BUILD_INFO.json` 与 `SHA256SUMS.txt`。

## 备份与恢复

- 脚本：`scripts/local-backup.py`（先校验、支持 dry-run，恢复到新目录）。
- 卸载默认保留数据目录：`%LOCALAPPDATA%\Stratide\data`。
- 运行态文件：`runtime/supervisor.json`、`runtime/setup-complete`、
  `runtime/consent.json`、`backfill.progress.json` 等。

## 部署与范围

- N100 / Mac mini 等低功耗部署已延后，不属于 V1 完成条件。
- 当前仍是 Paper-only：不提供实盘、不接券商、不自动晋升策略。
- 研究外发与预算约束见 `docs/UI_BACKEND_REQUIREMENTS.md` 与 ADR-012/013。

## 相关文档

- `docs/UI_TERMINOLOGY.md`：界面术语唯一口径
- `docs/ui-copy-audit.md`：改造前文案审计
- `docs/UI_BACKEND_REQUIREMENTS.md`：需要后端配合的事项
- `docs/UI_KNOWN_ISSUES.md`：遗留问题
- `docs/ui-redesign-summary.md`：按页面的改造说明
