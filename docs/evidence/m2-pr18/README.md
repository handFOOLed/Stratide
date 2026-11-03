# M2-PR18 初版 Windows 开发证据

**当前 Linux 状态（2026-11-03 R1）：4/4 PASS、0 skipped，真实 TimesFM CPU 生产闭环与 Linux 16 点压力矩阵完成。见 [Linux R1 证据 / 回归限制 / 复跑命令](linux-r1/README.md)。N100 仍 NOT_VERIFIED，PR 保持 Draft。** 本页其余内容保留初版 Windows 的历史记录，其中 Linux NOT_RUN 是初次交付时的状态。

Base：最新 main `b62c1171d8503e1f21e4b470847944c6fbe8dbf4`，提交前再次只读核对远端未变。实现位于独立 `issue69-worktree` / `codex/issue69-timesfm-cpu`。这些是开发者自测，**不是独立验收**。源码精确字节见 [source-sha256](source-sha256.json)，最终 Git HEAD 见该 Draft PR；不将未提交工作树的 base SHA 冒充测试实现的 HEAD。

| 验收项 | 实际结果 |
| --- | --- |
| 真 TimesFM 2.5 CPU、原风险字段 | **PASS（Windows 开发诊断）**；[1/4/8 序列输出](real-risk-contract.json)，真实权重、无 fake 预测，生产 decoder 对该未沙箱诊断全部拒绝 |
| 10/30/50/100 × 64/128/256/512 | **16/16 PASS，0 failures**；每组新进程加载，加载后三次输出完全相同；[完整 benchmark](cpu-development-benchmark.json) |
| 实际 CPU-only | `torch=2.8.0+cpu`、`cuda_build=null`、`cuda_available=false`；[实际检查](actual-cpu-facts.json) |
| 离线加载/预测 | 真模型执行时对 HTTP/socket connect 设置拒绝探针，**0 HTTP / 0 connect**；[结果](real-offline-probe.json)、[探针源码](real-offline-probe.py) |
| 新合成 E2E/故障反证 | **12/12 PASS**；[日志](synthetic-tests.txt)，测试替身只测试接口/失败，不计入真模型 PASS |
| 原 BigQuery / 风险 Fusion | **13/13 PASS**；[原录制/loopback 回归](risk-portfolio-regression.txt)，0 真实云请求 |
| 原 DeepSeek | **5/5 PASS**；[原 loopback/费用/只读回归](deepseek-regression.txt)，0 真实云请求 |
| Rust Risk Kernel | **33/33 PASS**；[日志](risk-kernel.txt) |
| 全仓 Rust | **非全绿：147 passed / 1 failed 后停止**。旧 `shared_budget` 子进程输出缺 `SHARED_RESULT`，在[未修改 main 副本](baseline-shared-budget-failure.txt)也复现；[全仓日志](rust-workspace.txt)。[定点六项曾通过](shared-budget-targeted-pass.txt)，不覆盖或抹去失败 |
| build / fmt / clippy | build/fmt、普通 clippy exit 0；严格 `-Dwarnings` 被 **4 个未修改文件中的既有 lint** 阻断；[普通 clippy](clippy.txt)、[严格失败](strict-clippy-existing-failures.txt)。未为消除 lint 改写旧 adapter SHA |
| Linux 6 GiB cgroup/bubblewrap | **NOT_RUN / NOT_VERIFIED**；此机无 Linux/WSL，4 项 Linux 实测全部明确跳过；[日志](linux-isolation-not-run.txt)。生产 preflight 在 Windows [exit 2 拒绝](unsupported-platform-preflight.json) |
| N100 | **N100_ACCEPTANCE=NOT_VERIFIED**；没有物理 N100，不外推 SLA |

## 实际硬件与资源

Ryzen 7 9700X，8 physical cores / 16 logical threads，33,997,303,808 bytes RAM，Windows 11 / AMD64，Python 3.12.10。Worker batch 1、Torch/OMP/MKL threads 2、interop 1。CPU 依赖均固定，`pip check` exit 0。

整个矩阵最大 RSS **2,054,328,320 bytes（约 1.91 GiB）**，整个 Windows Job 最大提交内存 **3,450,064,896 bytes（约 3.21 GiB）**，Job 上限 6,442,450,944 bytes（6 GiB）。RSS 与 Job commit 是不同指标；这不是 Linux cgroup 或 N100 的实测。Windows Job 的 64 MiB 小预算 OOM 以及 timeout 后杀死孙进程由第 12 项测试反证。Linux 内存/禁网络/隐藏文件系统/控制器被杀的测试代码已提供，但本机未执行。

100 序列、每组加载后 3 次推理的开发机实测：

| context | model load 秒 | 整个进程 wall 秒 | 热批次每序列 p50 秒 | p95 秒 |
| ---: | ---: | ---: | ---: | ---: |
| 64 | 0.733 | 13.299 | 0.03295 | 0.03358 |
| 128 | 0.730 | 23.094 | 0.06801 | 0.06987 |
| 256 | 0.712 | 27.184 | 0.08216 | 0.08326 |
| 512 | 0.725 | 35.163 | 0.10757 | 0.10982 |

“冷启动”指新 Python 进程和重新加载模型；未清空 OS 文件页缓存。Model load 不含 import/文件校验，进程 wall 包含它们。热 p95 使用 nearest rank。正常数值/性能路径的 model.py、worker.py、benchmark.py 没有随后改动；最终补充的 Linux unit 清理所有权与 stop 失败回收不在 Windows benchmark 的执行分支，最终 12 项 E2E 和真实 1/4/8 接线均已重跑。

同一次 benchmark 期间，原 Rust `risk-demo` 以明确的 synthetic 分值参数运行，**exit 0 / 0.089 秒**；[原输出](core-liveness.json)。这是核心可继续响应的开发证据，不是 N100 SLA 或实际资金授权。

## 数值结果与反证

三折前缀为 84/104/124 synthetic closes，对应 64/84/104 RMS 输入，每折 20 个未来目标不送 Worker，合计 60 个预测点，缺失 0、失败 0。原 Naive/EWMA 在相同前缀/目标上对比：

| 方法 | MAE（daily ratio） | RMSE（daily ratio） |
| --- | ---: | ---: |
| TimesFM | 0.0000755504 | 0.0000897813 |
| Naive | 0.0000694902 | 0.0000981002 |
| EWMA | 0.0001059853 | 0.0001344290 |

TimesFM 的 MAE 比 Naive 差，RMSE 较低；全部保留。这些仅是合成 sequential as-of 工程对照，不是真实历史、独立盲测或 alpha。5/20 均值误差、原 RiskExpertResult 字段和开发隔离 blocker 在 benchmark JSON 中。模型仍不产收益方向/可交易标志，负值不 clamp，而是拒绝。

[未来数据红→绿](red-green.json)：在隔离测试副本中故意移除 `Plan.validate → Frozen.validate`，`Tests.test_02_future_observation_rejected` 先 **exit 1**；恢复校验后 **exit 0**。这是高风险故障注入，不声称基线曾有该漏洞。[红日志](red-future-gate.txt) / [绿日志](green-future-gate.txt) / [可复用注入脚本](future-gate-mutation.py)。

原 Frozen 1–8 限额未扩大；真实 input_mode、未来可得时点、非法日历/单位/缺数据、负值/NaN、模型 pin/代码变化、默认 OFF、重启/重复 once、崩溃/OOM/超时、输入/输出超限、两个进程争用、重复 unit 清理不能停止其他 Worker、Owner stop、零 `calls`、原配置/权限均有定向断言。

## 重复执行

Linux 安装/预热、原 Owner AgentDir 绑定、离线 once/status/verify/stop 见 [M2_PR18](../../M2_PR18.md)。本期不执行 EOD 自动调度，不将本地风险发送给 DeepSeek。

```powershell
# 此分支工作树中：
scripts/with-msvc.ps1 build --workspace --locked --offline
scripts/with-msvc.ps1 fmt --all --check
python -X utf8 -B scripts/test-timesfm-cpu-real.py
python -X utf8 -B scripts/timesfm-cpu.py bench --development-cpu-diagnostic

# 新 E2E / 原云回归必须在独立 synthetic Git checkout 内构建并运行，不能绑定 Owner 费用库。
python -X utf8 -B scripts/test-timesfm-cpu.py
scripts/with-msvc.ps1 test -p stratide-research --lib --no-run --locked --offline
python -X utf8 -B scripts/test-risk-portfolio.py --driver <stratide_research-libtest.exe>
python -X utf8 -B scripts/test-deepseek-structured.py

# Linux（有模型、cgroup v2、systemd user manager 和 bubblewrap）：
python3.12 -B scripts/test-timesfm-linux.py
python3.12 -B scripts/test-timesfm-cpu-real.py
python3.12 -B scripts/timesfm-cpu.py bench
```

`future-gate-mutation.py` 只修改当前分支的 `state/test-tree` 测试副本，并在 finally 恢复；先以 main archive + 当前改动创建该隔离 Git checkout。离线探针源码保留的是实际执行的 ignored `state/real-offline-probe.py`；宿主用 `runtime.communicate_bounded` + Windows `Job`、标准 synthetic 请求驱动它，没有假模型。

[validation.json](validation.json) 逐项记录命令/退出码、基线失败和未运行项。[模型 manifest](model-manifest.json) 固定 revision/四文件 SHA，[Windows wheel SHA](dependency-wheel-sha256.json) 固定本次实际安装字节，未冒充 Linux wheel 验收。证据不含模型/wheels、凭据、主机绝对路径或真实行情。

本期新增真实行情请求 0、真实付费 Provider 请求 0、旧 RAW 重解析 0、旧全库复验 0、真实前向观察新增 0。原 Risk/Ledger/旧云路径及预算/交易权限未改，`RESEARCH_ONLY / ELIGIBILITY_DENIED / paper_allowed=false / live_allowed=false`。初版时 Linux 未运行；R1 已补 Linux 实测，N100 与独立固定 HEAD 审查仍未完成，保持唯一 Draft，不 Ready/合并。
