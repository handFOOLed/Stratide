# PR #72 P1：历史模型/计价证据独立复验

修复[评论 #6604866896](https://github.com/handFOOLed/Stratide/pull/72#issuecomment-6604866896)，基准 HEAD `0b24575aba343194ce14ec5f72cc5330286600c5`。仅离线修复历史读路径、必要快照与定向测试；没有再次调用真实 DeepSeek，没有改已有两笔调用或预留。

## 问题与修复

原代码从当前 Settings 取 Model 重建旧 provider hash 和费用回执。只更新 `authorized_at`，旧 wire/源/任务未变，verify 就失败。[原代码红测](red-history.txt)实际复现 `FUSION_RESULT_CHANGED`，exit 1。

新任务在原 Agent 创建任务前保存完整 Model 的不可覆盖私有快照（`local-fusion-model.json`，0600），包括原模型版本、grant、Price 与 token/费用边界；其 fingerprint 必须等于原任务/context 的 model pin。派发仍按最新配置检查 grant、价格有效期和原共享 Budget，并要求快照存在；历史快照不能授权新调用。

旧任务读取直接定位保存的 task/context，不再加载当前 Model。verify 由冻结模型、原请求重建、保存的响应字节、原来源 pin 与原 call 的 price_version/预留/usage 独立复验；撤销、续期、价格/模型版本轮换或移除当前模型都不改旧结论。只读兼容原 PR 已实际使用的 V1 adapter SHA，保留原 receipt 的 adapter pin，不重签原结果；未知 adapter 仍拒绝。

## 已有记录与迁移限制

旧记录此前只有模型 fingerprint，没有完整快照。本次显式运行 `capture-model`：当前仍保有的 Model 与 task 2、4 的原 provider/context pin 完全相同，才写入两个新的本机快照文件。该命令不读 Key、不调用 Provider、不写 SQLite。

缺快照报 `FUSION_HISTORICAL_MODEL_SNAPSHOT_REQUIRED`。若当前配置已轮换且找不到原 pin，则 `capture-model` 报 `FUSION_ORIGINAL_MODEL_UNAVAILABLE`；必须从原可信配置/备份找回完全匹配的模型描述，不能用新配置猜测、覆盖或修改旧任务来通过。此次不存在这个未解决缺口，两个旧 Model 都精确匹配。

[本机原记录只读复验](owner-readonly-proof.json)：原 task 4 的 status/verify/report/Inbox 全部 exit 0，registration 仍为 `024e0ceb6f47d507a99bfb094baf758bfa48130138d666362effe2a176599b04`。补存及读取前后 **tasks/calls/meta 所有行哈希一致**；仍 2 calls，预留 **196608 micro CNY**，usage 估算 **15420 micro CNY**。首次失败、成功组合、日/月 cap、许可状态均未重写。新增真实 API 调用 **0**、Key 正文读取 **0**。

## 离线回归

- [新 Fusion 9/9](green-history-and-fusion.txt)：保留原 6 项，并增加 3 项 P1 测试。先 loopback 产生并归档现金组合，再续期/撤销 grant、改变 Price/模型版本或移除当前 Model，隐藏测试 Key 后 status/verify/report/Inbox 仍得到原结果；快照/原 task/call 不变，server count 不增加。
- 缺快照、错误 pin 捕获、篡改快照价格、wire、源、receipt 或 call price_version 均拒绝；恢复原夹具后可复验。
- 新任务使用当前 grant/价格期限/预算：撤销、未复核价格、过期、已消费许可及降低的日 cap 均在发送前阻断，0 HTTP。
- [Rust workspace 204/204](rust-workspace.txt)，含 CNY 3 项与原 shared-budget 6 项。
- PR17 首轮 [4/5](pr17-initial.txt) 在旧夹具授权时间门禁拒绝；[原失败项复测 1/1](pr17-targeted.txt)通过。
- [PR18 11 通过 + 1 Windows 专属项跳过](pr18-regression.txt)，[Linux 隔离 4/4](linux-isolation.txt)。
- PR56 首轮 [11/13](pr56-initial.txt)：临时 target 软链接触发原路径门禁，另有既有快照时间门禁。改用原生 target 目录后，[原失败项 01/07 复测 2/2](pr56-targeted.txt)通过，未改旧测试/生产门禁。

[完整命令、退出码](validation.json)。按项目文档使用 `cargo build --workspace --locked --offline` 构建实际旧记录复验；没有扩展修复局部包构建/旧时间门禁或并行 Ledger 问题。最终 HEAD 记录在同一 Draft PR #72，等待独立复审，不 Ready/merge。Paper/Live 仍 BLOCKED。
