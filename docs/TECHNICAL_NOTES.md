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

## 2026-11-06 自动化与后端补充

- **安装版 dashboard 观察者模式**：supervisor 启动 dashboard 时传 `--agent-observer`；dashboard 使用
  `Agent::attach` 且不启动内置 worker，释放 `data/agent/agent.lock` 给后台 watch 的本地 TimesFM 与
  云端 bridge。开发期直接运行 `stratided`（无该 flag）行为不变。
- **预算编辑**：`POST /api/agent/budget` 原子写 `settings.json`（临时文件+fsync+rename+sha256 重读），
  写 `budget_audit:<RFC3339>` 审计；不改 calls/预留；币种/时区首次后不可变；低于 committed 需确认。
- **Paper 默认策略**：`research/paper_portfolio.py:ensure_policy()` 在首次成功采集后以最新 READY 快照的
  5217 只沪深主板证券构建 universe、逐证券费率与 `fixed-ticket-paper-v1` 策略；幂等，已存在只读。
- **研究健壮性**：本地失败记录异常类型/摘要并写 stderr；本地失败与 WSL/bridge 失败有 600s 冷却；
  代码/规则更新时未派发云任务的 BLOCKED run 可重建 screen/plan；本地 TimesFM pin 变化在无 calls 时
  审计替换；市场桥接的 parent `as_of` 用 RFC3339 解析比较，避免 Python `Z` 与 Rust `+00:00` 字符串误判；
  云端内容若回显 `type:"json_object"` 在解析边界剥离。
- **通知/原因/构建字段**：见 `docs/AGENT_API.md` 与 `docs/DASHBOARD_API.md` 的 0.3.0 后字段说明。
