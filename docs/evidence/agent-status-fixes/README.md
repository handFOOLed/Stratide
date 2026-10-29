# Agent 后端状态修复：开发自测

基线：main `e320751c71f2a1f73b588bed21b106f384897090`（PR #25 已合并）。分支 `codex/agent-status-fixes`。本次仅修复研究后端的 EOD 状态与 Provider 故障归因；风险为 P1，费用/授权闸门及重试权限保持原行为。没有改动 DS 的前端、主题、构建文件或交接文档，没有付费网络调用。

## 复现与修复

同一条后端回归命令：

```powershell
pwsh -NoProfile -File scripts/with-msvc.ps1 test --locked -p stratide-research --test status_regression
```

- 修复前：**5 failed / 2 passed**。任务 completed/running/failed，EOD 却读出 queued；预算未配置、尚无任何 Provider 调用，却把模型标成 unavailable_or_outcome_unknown；本地单任务限额拒绝还覆盖此前的成功/未知 Provider 观察。
- 修复后：**7 passed**。包含完成后重启与去重、运行/取消、失败/未知费用、预算/授权/价格拒绝，以及真正的 Provider 零计费拒绝、连接准备故障。

原因是 EOD API 直接读取了仅在调度时写入的入队标记，模型健康则把所有 failed 任务都视为 Provider 故障。现在 EOD 展示关联的权威任务状态；模型健康只使用实际调用观察或连接准备故障，排除本地拒绝/发送前取消。已有状态库无需迁移，未知费用不释放，也不重新调度已完成 EOD。

## 固定接口

路由、请求体、响应字段与类型不变。`eod.latest` 仍为 null 或 `{source_day,disposition}`；disposition 使用原任务状态或 skipped 标记。`models[].availability` 仍为 not_verified / last_task_completed / unavailable_or_outcome_unknown；last_reason 对应 Provider 观察。本地拒绝保留在原 task.reason、authorization 和 budget 中。详见 [API 契约](../../AGENT_API.md)。

## 实际验证

```powershell
pwsh -NoProfile -File scripts/with-msvc.ps1 test --locked -p stratide-research -p stratided
pwsh -NoProfile -File scripts/with-msvc.ps1 clippy --locked -p stratide-research -p stratided --all-targets -- -D warnings
rustfmt --edition 2021 --check research/agent/src/service.rs research/agent/src/store.rs research/agent/tests/status_regression.rs
```

结果：**26 passed**（11 原研究安全测试 + 7 新状态回归 + 8 Daemon 测试），Clippy / rustfmt / git diff --check 全部 PASS。Windows x86_64、Rust 1.98.1/MSVC；临时隔离数据库和确定性 fake。连接准备故障是后端故障注入，不是真实 DNS 或云端调用证据。

完整工作区、前端构建及浏览器测试本次未重跑；本次不改这些实现，且前端正由 DS 独立开发。旧验收证据保持原样，本记录属于开发自测，不是独立验收。日志保存在忽略目录 `state/issue22-evidence/status-fixes-test.txt`。不自行合并。
