# M2-PR20 开发证据

基线 `971eb4ba90507142b1d32ca80af2d15859790933`，独立 WSL2 Ubuntu 24.04 原生 ext4 worktree。最终提交 HEAD 见 PR 正文；[tested-source.json](tested-source.json)绑定实际源码与测试。开发者自测，不是独立验收。

| 证据 | 实际结果 |
| --- | --- |
| [真实闭环](real-run-summary.json) | 所选三证券 × 84 会话、as_of 2022-03-31 → 真 TimesFM CPU → 原 task 6 completed → 原 Registry → report/verify；重复 once 同任务 |
| 真实拒绝 | 2026-10-30 前缀实际因子变化，HISTORY_RAW_ACTION_DISCONTINUITY；另在冻结真实输入安全构造缺口 83/84，BLOCKED，不改源库 |
| 费用与外发 | 原 Owner 仍为两笔既有云 calls；calls 全行、相关 meta、settings SHA 未变。新云/市场调用 0、新云计费 0、真实 Key/Token 正文读取 0；Fusion 明确拒绝真实源 |
| 模型与隔离 | 复用原固定权重/venv，0 下载；6 GiB、swap=0、无网络；Linux 原故障隔离 4/4 |
| 旧真实记录只读兼容 | 原 PR19 成功 task 4 verify=true，不重新执行 API，不改账本 |

[checks.json](checks.json)：Rust 204/204；历史 9/9（含 8×192、前缀未来突变、PIT/复权拒绝、原 Registry、重入/取消/失败）；CPU 11 pass + 1 Windows 专项 skip；Linux 4/4；Fusion recorded/loopback 9/9；V1 29 pass + 1 Windows NTFS 专项 skip；V2 18/18，成功运行均 exit 0。

## 可复现命令

真实步骤和参数见 [M2_PR20](../../M2_PR20.md)。必须使用已有 Owner 绑定，不另造费用库。真实 preflight/freeze/once/status/report/verify 与重复 once 都已执行；Fusion preflight 预期 exit 2、错误码 REAL_MARKET_DATA_EGRESS_DENIED。正常源与拒绝源的质量未升级。

Python 合成测试必须各用全新 standalone Git checkout 编译，不能在原 Owner 绑定目录初始化或重绑。CPU 与 Fusion 各自要求固定合成 Owner；不同套件分别使用隔离 checkout。复用本机 venv/权重，不重新下载：

```bash
cargo build --workspace --locked --offline
cargo test --workspace --locked --offline -- --test-threads=1
python3 -B scripts/test-timesfm-history.py
python3 -B scripts/test-timesfm-cpu.py
python3 -B scripts/test-timesfm-linux.py
cargo test -p stratide-research --lib --no-run --locked --offline
PR19_TEST_DRIVER=<实际构建的stratide_research_libtest> python3 -B scripts/test-local-timesfm-fusion.py
python3 -B scripts/test-historical-warehouse.py
python3 -B scripts/test-historical-sidecar.py
```

## 执行中修正与未验证项

首次跨挂载只读查询在检查全部 raw 路径时耗时过长，手动终止该 agent 自己的只读进程；未生成任务。新增 SQLite-only 检查参数，仍检查 DB/锁/sidecars，原默认全路径校验不变，最终真实查询正常完成。

初始回归启动时的 checkout 绑定/测试驱动定位错误均在独立合成目录修正。原 Fusion 授权夹具还在 VM 时钟同步时命中过早授权错误；仅将其 synthetic authorized_at/price_reviewed_at 留已有五分钟余量，最终 9/9。生产授权/预算规则未更改。

开发中 task 5 成功后补齐 8×192 输入容量，保留原记录，最终源码重新冻结运行 task 6。没有修改原历史 task/calls/旧冻结报告。较早中间源码的任务不冒充最终固定实现。

未重跑真实五年全库 verify/raw 解析/全指纹、未重复付费 API；原仓库使用既有准入和有界查询。完整历史身份、公司行为/PIT、样本外优势、开盘与前向 Paper、N100 真机、独立固定 HEAD 审查仍未验证。ENGINEERING_PASS 只说明本期功能可运行，不提供金融收益或安全保证。
