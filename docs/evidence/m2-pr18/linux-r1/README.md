# PR #70 Linux R1 验收证据

2026-11-03，接续初版 HEAD `e8ef8b8d97488432872b4ac224cbd5780f3a11af`，对应[固定 HEAD 审查](https://github.com/handFOOLed/Stratide/pull/70#issuecomment-6600432131)。**Linux 隔离 4/4 PASS、0 skipped；真实 TimesFM CPU 生产闭环 PASS；N100_ACCEPTANCE=NOT_VERIFIED。** 这是开发者 WSL2 实测，仍需 ChatGPT 对最新 HEAD 独立复审；PR 保持 Draft。

所有 checkout、编译目录、Python venv、模型、synthetic AgentDir 均在 Ubuntu 原生 ext4。实际为 Ubuntu 24.04.5 / Python 3.12.3 / systemd user 255 / bubblewrap 0.9.0 / cgroup v2（memory controller 可用）/ Ryzen 7 9700X / 16 逻辑线程 / WSL 分配约 15.45 GiB RAM。使用非 root UID 1000 运行；未关闭 AppArmor、user namespace 或网络隔离规则，未放宽 runtime 权限。[环境、全部依赖版本及实际模型四文件 SHA](environment.json)。

## 本次修复与反证

- systemd 255 不接受原 `MemoryOOMGroup=yes`，启动前即失败：[原错误](red-systemd-assignment.json)。移除无效属性，保留 `OOMPolicy=kill`，Worker 和宿主均核对内核 `memory.oom.group=1`、`memory.max=6442450944`、`memory.swap.max=0`；没有降低 OOM 要求。
- 原 heartbeat daemon 使用 buffered stdin，正常输出后可能在 Python 退出时持有锁，导致 `_enter_buffered_busy` / exit 134：[原 stderr](red-worker-shutdown.json)、[稳定失败用例](red-worker-shutdown.txt)。改用 raw FD 读取请求和心跳，并保留同一次读取中预取的心跳字节；新增正常 production probe 退出回归。管道关闭遇 BrokenPipe 不再遮盖原 Worker 错误。
- `--collect` 已回收的 unit 在再次 `stop` 时返回非零：[原错误](red-collected-unit-stop.json)。现在只把宿主确认的 `not-found + inactive` 视为已停止；active 或无法查询仍拒绝。实际生产链最后的 `stop` 已通过。
- 隔离探针不再把固定的安全开关 `HF_HUB_DISABLE_IMPLICIT_TOKEN=1` 误判为凭据，并实际注入 synthetic secret 验证清理。OOM 测试读取宿主 `Result=oom-kill` / signal 9，控制器死亡测试等待真实模型进程 RSS ≥1 GiB 后再杀控制器，核对宿主 Worker PID 消失。
- 原回归脚本仅修正 Windows `.exe` 文件发现方式以便在 Linux 执行；原 Agent/Budget/DeepSeek/BigQuery/Risk/Ledger 生产代码未改。[源码 SHA 和原模块比对](source-sha256.json)。

## Linux 4 项隔离

实际执行 `python3.12 -B scripts/test-timesfm-linux.py`，exit **0**，**4 tests / 0 failures / 0 errors / 0 skipped**，耗时 **4.833 s**。[完整日志](linux-isolation.txt)、[结构化宿主/Worker 事实](linux-isolation.json)。

| 用例 | 实测结果 |
| --- | --- |
| 网络 / 文件 / 环境 / 6 GiB | 网络连接被拒绝、模型只读、home 隐藏、synthetic secret 不可见；内核 cap 6 GiB / swap 0 / oom.group 1；正常 production probe 退出成功 |
| OOM / 回收 / 再启动 | 测试 cgroup 缩至 128 MiB，宿主 Result=oom-kill、ExecMainStatus=9、MemoryPeak=134217728；随后受限 Worker 可再次正常启动 |
| 超时 / 崩溃 / 恢复 | 实际 hang / crash 返回错误，完成清理，后续 Worker 成功 |
| 控制器意外死亡 | 真实模型 Worker RSS ≥1 GiB 后 SIGKILL 控制器；随后 unit inactive、该 Worker PID 不存在；具体回收秒数见结构化事实 |

OOM 用例仅为保留失败 unit 的宿主元数据而在该测试去掉 `--collect`，断言后清理自己的 unit；生产启动器仍使用 `--collect`。没有 mock 或跳过替代 Linux 隔离验收。

## 真实生产闭环与宿主证据

独立 Git checkout 内创建一次性的 `--agent-init-fake` synthetic AgentDir，然后用原 `risk-portfolio.py init` 绑定该目录。未绑定 Owner 真实费用库，也未配置任何真实 cloud Provider。

`preflight → enable → synthetic-freeze --series 4 → once → status → verify → stop` **全部 exit 0**。这里的 `once` 使用真正固定权重及完整 systemd + bubblewrap 启动链，`development_only=false`。[逐步命令/原 RiskExpertResult V1 完整输出](production-steps.json)、[宿主采样/数据库核对/Naive 与 EWMA](production-proof.json)、[实际执行的验证 harness](production-harness.py)。

- 原 tasks 表：1 个任务，`completed / LOCAL_NO_BILLING`；整个一次性 Agent DB 的 `calls=0`。
- `verify=true`，stop 后开关 false；原 settings 文件前后 SHA 一致。
- 4 序列、64 RMS context、配置 max_context 256、batch 1、2 threads、horizon 20；输出原 RiskExpertResult V1 与 Naive/EWMA，不调用 fake Engine。
- 宿主在真实推理期间采样 **60 次**，直接检查 `/proc/<pid>/ns/net`、`net/dev`、`mountinfo` 和 cgroup 文件。实际 Python 网络命名空间与宿主不同、接口仅 `lo`、模型挂载为 `ro`；unit 为 MemoryMax=6 GiB / swap 0 / OOMPolicy=kill / KillMode=control-group / CPUQuota=200%。这些检查独立于 Worker JSON 自述。
- 停止后所有 **3 个宿主观测 PID 均不存在**，unit `not-found / inactive`，无孤儿进程。安装完成后的模型推理没有联网下载路径；Worker 没有可外连网络接口。
- 保持 `RESEARCH_ONLY / ELIGIBILITY_DENIED / paper_allowed=false / live_allowed=false / can_execute_forward_paper=false`。

| 4 序列生产 once 指标 | 实测 |
| --- | ---: |
| CLI once 总耗时 | 4.380 s |
| Worker wall / CPU | 2.988 / 2.917 s |
| 模型 load | 1.032 s |
| Worker getrusage 峰值 RSS | 2,076,774,400 bytes（1.93 GiB） |
| 宿主采样最大 Worker RSS | 1,471,303,680 bytes |
| cgroup memory.peak（宿主与 Worker 一致） | 1,411,121,152 bytes（1.31 GiB） |
| cgroup CPU | 2.954 s |
| fail / orphan PID | 0 / 0 |

RSS、离散采样 RSS、cgroup charged memory 是不同口径，不能互换。峰值均低于 6 GiB；cgroup cap 和 swap 限制由内核执行。生产代码组合 SHA 为 `26c92639fd78b143c4bd400988f447f29fcb52294319734555bae14efe669f2a`，已逐文件确认本次生产 checkout 与提交源码一致，见 source-sha256。

## Linux 压力矩阵与对照

真正 Linux 受限 Worker：**10/30/50/100 × 64/128/256/512，16/16 PASS、0 failures，各点三次相同预测一致**。[完整矩阵和 sequential as-of 合成对照](cpu-linux-benchmark.json)、[运行进度](cpu-linux-benchmark-progress.txt)。总矩阵峰值 RSS **2,080,792,576 bytes（1.94 GiB）**，最大 cgroup peak **1,389,416,448 bytes（1.29 GiB）**。结束后 unit inactive、Worker PID 列表为空。

100×512、batch 1、2 threads：进程 wall **24.096 s**、Worker CPU **45.380 s**、模型加载 **0.689 s**、热预测每序列 p95 **0.07669 s**。冷启动是新进程重新加载，未清空 OS 文件页缓存；不是物理 N100 或延迟承诺。三折 walk-forward 的未来目标未进入 Worker，Naive/EWMA 和模型误差原样保留；合成工程结果不构成真实 alpha、PIT 或独立 holdout。

## 回归、退出码和未解决项

[逐项命令/退出码](validation.json) 是当前记录；原 Windows 首轮证据仍在父目录，未覆盖。

| 检查 | 本轮结果 |
| --- | --- |
| TimesFM synthetic E2E | exit 0，11 PASS + 1 Windows Job-only skipped；Linux 对应隔离另有上方 **4/4、0 skipped**，[日志](synthetic-tests.txt) |
| 原 Risk/Budget Rust | exit 0，8+6 PASS，[日志](risk-budget-tests.txt) |
| 原 Risk Kernel | exit 0，33 PASS，[日志](risk-kernel-tests.txt) |
| 原 DeepSeek Python | 最后一次 exit 0，5/5 PASS；[最终日志](deepseek-tests.txt)；更早发生过 AUTHORIZATION_REQUIRED，保留[失败记录](deepseek-intermittent-failure.txt) |
| 原 BigQuery/风险 Fusion Python | **最后一次 exit 1，12 PASS / 1 FAIL**；`unknown_position` 用例预期 instrument 拒绝，实际先收到 FUTURE_OR_STALE_SNAPSHOT，[原日志](risk-portfolio-tests.txt) |
| 完整 Rust 串行 | 最后一次 exit 0，**200 PASS**，[日志](rust-workspace-serial.txt) |
| 完整 Rust 默认并行 | **exit 101**，旧 Ledger 测试遇本机 writer lock / os error 11，[日志](rust-workspace-parallel-failure.txt)；更早串行出现过旧 DeepSeek 授权拒绝，[记录](rust-workspace-earlier-serial-failure.txt) |
| 未修改 main 对照 | shared_budget 6/6、对应 Ledger 单项 1/1、DeepSeek composite 1/1，均 exit 0；[预算](main-shared-budget.txt)、[Ledger](main-ledger-targeted.txt)、[DeepSeek](main-deepseek-targeted.txt) |
| build / fmt / 普通 clippy | exit 0；[clippy 既有警告](clippy.txt)；未为严格 warning 门槛修旧文件 |

原 Windows 全仓 shared_budget 失败没有在 Linux 未修改 main 的 6 项中复现，支持其与平台/测试环境相关，未证明具体根因。旧 Python 时间门禁仍有间歇拒绝；500 次 Rust SystemTime/Python 前后时钟比较未发现越界（[结果](clock-comparison.json)、[小程序](clock-comparison.rs)），因此**不把原因写死为 WSL 时钟问题**。未改授权、预算、时间可得性门禁或 Ledger 来消除这些失败，也不声称全仓所有默认执行方式均绿。

安全限制：本轮仅 synthetic 输入；真实行情、历史五年全量、真实 DeepSeek/BQ 请求、费用和订单均未触发。没有物理 N100 证据，`N100_ACCEPTANCE=NOT_VERIFIED`。WSL2 实测与开发者自测都不代替最新固定 HEAD 的独立审查，PR 不 Ready、不合并。

## 复跑命令

只在 Linux 原生 ext4 中准备环境。联网安装与推理分开；模型和 venv 必须已固定并核验。

```bash
# 独立安装阶段（公开依赖/模型）；推理阶段不执行下载。
bash scripts/install-timesfm-cpu.sh
cargo fetch --locked
cargo build --workspace --locked --offline
.venv/bin/python -m pip check

# PR worktree：四项硬隔离及真实压力矩阵。
STRATIDE_TIMESFM_TEST_EVIDENCE=state/linux-isolation.json \
  python3.12 -B scripts/test-timesfm-linux.py
python3.12 -B scripts/timesfm-cpu.py bench > state/cpu-linux-benchmark.json
```

生产闭环必须使用有自己 `.git` 的一次性 checkout，不能将 linked worktree 的 Git common root 绑定到 Owner 真实库。将 [production-harness.py](production-harness.py) 复制到 ignored `state/linux-r1/run-production.py`；在同目录下准备 `production-checkout/`，内含本提交源码、已安装的原生 `.venv`、已核验 `models/timesfm-2.5` 和原生构建的 `target/debug/stratided` / `timesfm-risk-agent` / `risk-portfolio-agent`，再运行：

```bash
python3.12 -B state/linux-r1/run-production.py
# harness 内部实际执行：
target/debug/stratided --agent-init-fake state/disposable-synthetic-owner
python3.12 -B scripts/risk-portfolio.py init --agent-dir "$SYNTHETIC_AGENT_DIR"
python3.12 -B scripts/timesfm-cpu.py preflight
python3.12 -B scripts/timesfm-cpu.py enable
python3.12 -B scripts/timesfm-cpu.py synthetic-freeze --name linux-real-risk --series 4
python3.12 -B scripts/timesfm-cpu.py once --name linux-real-risk
python3.12 -B scripts/timesfm-cpu.py status --name linux-real-risk
python3.12 -B scripts/timesfm-cpu.py verify --name linux-real-risk
python3.12 -B scripts/timesfm-cpu.py stop
```

回归同样在独立 synthetic checkout 运行；旧风险套件所需 `$LIBTEST` 是本机 `cargo test -p stratide-research --lib --no-run --locked --offline` 生成的 `target/debug/deps/stratide_research-*` 可执行文件（排除 `.d`）。

```bash
python3.12 -B scripts/test-timesfm-cpu.py
python3.12 -B scripts/test-risk-portfolio.py --driver "$LIBTEST"
python3.12 -B scripts/test-deepseek-structured.py
cargo test -p stratide-research --test risk_portfolio --test shared_budget --locked --offline
cargo test -p stratide-risk --locked --offline
cargo test --workspace --locked --offline -- --test-threads=1
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --locked --offline
```

证据中的主机用户/绝对 checkout 路径已替换为 `$HOME` / `$PR_WORKTREE` / `$SYNTHETIC_CHECKOUT` / `$REGRESSION_CHECKOUT` / `$BASELINE_MAIN`；原 stdout、错误码、指标、合成数值和 hash 保留。没有上传数据库、owner-token、API key、模型或 wheel。
