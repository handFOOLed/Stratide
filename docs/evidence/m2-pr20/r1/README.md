# PR #75 R1：模型身份与多证券来源绑定修复

修复 [固定 HEAD 审查](https://github.com/handFOOLed/Stratide/pull/75#issuecomment-6607575041)，审查基线 `b3995b94d5c75ee47de28c8d5481fa001738aada`。本轮仍为同一 Draft PR，`stop-that-shit change hash=allow agents=0`；开发者自测，不代表审查者已接受。

## P1：重算 SHA 也不能改语义身份

Historical-only 继续使用独立验证，不套用 synthetic/PIT 门禁。现在逐项检查：

- risk model 必须为 `local-timesfm-2.5-cpu`，fingerprint 必须等于 Plan 的当前代码 pin；Plan 仍核对当前 CPU descriptor。
- prompt/strategy 版本必须为本适配器固定值；本地占位预算必须为 1；未使用的 Fusion model、fingerprint 和两个 recording SHA 必须为指定未用值，不能伪装成另一个模型/云记录。
- opportunity 必须与证券集合完全对应、无缺失/重复/外来证券，全部为 UNKNOWN 且 evidence 为空。

红测在原 b3995b9 生产代码上实际复现 **19 类 × project/begin/verify = 57 次放行**。测试不仅重算 frozen/payload SHA，还在隔离合成 Agent 库中重算 task input/provider pin、结果绑定及结果 SHA；旧 verify 确实接受篡改。修复后 57 个反例均按语义原因拒绝，原有效记录仍能复核。没有修改 Owner 的任务/来源来制造反证。

## P2：证券+日期索引与来源清单分开绑定

`payload.sources.daily["<instrument>:<YYYYMMDD>"]` 指向原 source SHA；`daily_manifests[SHA]` 保存原 availability/attempts 清单。整日下载可让多个证券共享清单，但每个证券/日期都有独立引用。Rust 同时校验引用覆盖、逐行 source SHA、原清单 SHA、原始响应/元数据 SHA 形状及下载时刻。

这样避免同日键覆盖，也避免把同一个整日清单逐证券复制后超过原 2 MiB IPC 限制。8×192 容量回归通过，输入上限未扩大。多证券 recorded 反证给每行不同回执，确认全 672 个键保留；缺引用/缺清单/跨证券串换/修改下载时刻/修改 raw SHA 的 10 个 project/begin 反例均拒绝。

已调用 tushare 1.1.12 / tushare-data 1.1.16 skills，核对官方 [daily](https://tushare.pro/wctapi/documents/27.md)、[adj_factor](https://tushare.pro/wctapi/documents/28.md)、[suspend_d](https://tushare.pro/wctapi/documents/214.md)。daily 的证券与交易日字段共同定位观测；整日请求的本地回执可共享，不能据日期索引丢掉证券维度。这里的 SHA 是本地回执/版本绑定，不是供应商签名、历史 PIT 或可交易证明。未复权、停牌无日线及实际下载时间语义均保留，0 新 Tushare 请求/Token 正文读取。

## 实际复核时发现的结果 SHA 问题

第一次新历史 task 7 的 CPU 推理完成，但归档复核返回 LOCAL_RESULT_SHA。比对发现：保存字节与 Python 重读哈希一致，较窄的 research-only 构建却会重新解析部分 float32 数字，改变校验结果；全工作区构建原先间接启用了不同的 serde_json 精度功能。

固定 seed 74 产生四个公开 float32 数字，先在 package-only 构建复现 4 个失败；没有把私人预测值当 fixture。现在显式启用 serde_json 的 arbitrary_precision / float_roundtrip，且将 research Cargo.toml 纳入 CPU 代码 pin，两种构建均保留所需数值精度。没有关闭 SHA 校验或修补已保存结果。task 7 和旧 task 6 原样保留，最终源码使用新冻结 task 8。

原 Rust 合成授权夹具在 WSL 时钟同步时两次命中 DEEPSEEK_OWNER_AUTHORIZATION_REQUIRED，导致全仓测试中断；单项复测曾通过。仅给该测试 helper 加与现有 Python 夹具相同的五分钟余量，生产授权/价格门禁未改。最终全仓 204/204。

## 最终证据

- [真实本地运行与来源统计](real-run-summary.json)：三证券 × 84，会话截至 2022-03-31；**task 8 completed / verify=true**，原 Registry、report、重复 once 均通过。**252 个证券/日期引用、84 份原始日来源清单**全部绑定。
- [红绿与回归汇总](checks.json)：历史 **12/12**（含 57 个语义反例、10 个来源反例和 4 个小数反例）、Rust 工作区 **204/204**、旧 CPU **11 pass + 1 Windows 专项 skip**、Fusion recorded/loopback **9/9**。成功命令 exit 0；红测/真实外发拒绝的非零退出为预期。
- [本轮测试源码 SHA](tested-source.json)对应当前修改；最终提交 HEAD 见 PR 正文。
- 旧 PR19 已记录 task 4 在当前代码下只读 verify=true，未重发 API。原 Owner 两笔 calls、全部 meta 和 settings SHA 未变；本轮新云/行情调用/云计费/真实 Key 正文读取均为 0。
- 未重跑五年全库/raw、旧 Linux 隔离矩阵或付费 API；未变的原证据保留。N100/独立固定 HEAD 接受/历史 PIT/样本外优势仍 NOT_VERIFIED；Paper/Live false，真实来源 Fusion 继续 REAL_MARKET_DATA_EGRESS_DENIED。
