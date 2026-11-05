# Stratide 真实安装自动化链路只读诊断（2026-11-05 夜）

- 诊断对象：本机唯一运行实例（Supervisor pid 11368 → dashboard pid 25932 @127.0.0.1:8710 → eod watch pid 24060），程序目录 `F:\Stratide`，数据根 `C:\Users\wsj20\AppData\Local\Stratide\data`，版本 0.3.0。
- 方式：只读 GET、只读 SQLite（`file:...?mode=ro`）、日志、配置/锁文件只读检查、WSL 只读文件检查；未改代码/数据/配置，未停止实例，未发起任何 Tushare/DeepSeek 请求。密钥仅检查“存在性”，未读取/打印任何值。
- 重要限制（必须先看）：诊断期间检测到**另一个并行任务**在 `state\automation-probe\` 中复制数据根并向**真实 Agent DB 写回**（`state\automation-probe\restore-real-db.py` 在 2026-11-05T15:18:49Z 执行；`patch-impl-hash.py` 15:13:12Z）。真实 run 元数据因此被改写：当前 `market_research_run:20261105.screen.implementation_sha256=bb5203f1…`，而安装目录 `F:\Stratide\research\market_research.py` 实际 SHA256=`a0440172…`，两者不一致，导致实例从 23:12:59 起新增 `SCREEN_IMPLEMENTATION_CHANGED_NEW_RUN_REQUIRED` 阻断与 task #232。**23:12Z 之后的真实运行态证据不可作为产品缺陷依据**；本报告以 13:05–13:06Z 首次失败及其持久记录为主，并注明污染。建议 lead 立即要求并行任务停止写真实数据根。

## 0. 结论速览

1. **20261030/20261102 的 LATE_OR_FUTURE_CATALOG_NOT_DECISION_EVIDENCE 是预期规则，不是 bug**：这两天的行情快照是在 2026-11-05 20:52–21:05 才由历史补录取回（`late_backfill=true`），晚于其决策时点；规则明确禁止把晚到/回填目录当作当日决策证据。它们**不会事后自动恢复**。
2. **20261105 的 MARKET_RESEARCH_LOCAL_FAILURE 不是 available_at/晚到规则**：该日已通过 84 会话前缀校验、完成筛选（5926 只证券、3669 只合格、选出 8 只）并冻结 plan（`plan.json` 1,209,865 字节，13:06:24.571Z），随后在写 Agent 本地任务**之前**的本地阶段失败（13:06:25.609Z）。代码把所有 `OSError/ValueError/subprocess.SubprocessError` 折叠成该通用码，**丢弃了异常类型、消息和 traceback**（`research/market_research.py:304-318`，`eod-watch.err.log` 为空），因此无法从现状断言具体调用点。隔离回放显示 WSL 发行版/路径/模型/venv/preflight、plan、bridge `enable/project/begin` 全部正常，问题更可能是当时本地子进程/文件/桥调用的瞬时或未分类异常，但**必须先补诊断再断言**。
3. **即使修好本地异常，当前链仍有 3 个结构性缺口**：
   - dashboard 进程以 `Agent::open` 持有 `agent.lock`（实测 HELD），而 watch 的 TimesFM 本地步骤在 `cli.once` 中要求同一把 `agent.lock`（`research/timesfm_cpu/cli.py:160`），会得到 `WORKER_BUSY`；
   - 已安装 0.3.0 的 `market_eod.py` **没有** `paper_portfolio.ensure_policy()` 调用（工作区新版本已加、未安装），Paper 账本缺少 portfolio policy，Paper 步骤被隐藏成 `PAPER_LOCAL_INPUT_OR_LEDGER_UNAVAILABLE`；
   - 研究失败码没有冷却：`LOCAL_FAILURE` 每 ~30 秒重试，`eod-watch.out.log` 已 90,040,148 字节且每轮继续增长（全量 screen JSON 每次重打）。
4. **云与密钥并非当前第一阻断点**：market-research 授权 grant_active（version 9，有效期至 2036-11-02，84 会话/8 证券/20 会话预测）、共享预算 CNY ¥5/日、¥100/月已配置且 0 调用；DeepSeek 凭据目标在 Windows Credential Manager **存在**；模型配置/价格/grant scopes 与代码期望一致。`/api/agent/status` 里的 `MARKET_RESEARCH_SCOPE_INVALID` 是**误报**（`store.rs:411` 用 `["owner_task"]` 校验 market 模型），不代表真实派发被拒；但真实云 E2E 从未跑过（`real_market_e2e=NOT_AUTHORIZED_NOT_RUN`，calls=0）。
5. **84 暖机已满足**：`backfill.progress.json` = sessions_ready 87 / remaining 0 / state READY；20261105 的 84 会话 READY 前缀校验与筛选已成功完成，说明暖机与数据可用性达标。被阻断的 30/02 不会恢复；新交易日（如 11-06）在链路修好后可自然尝试。

## 1. 20261030 / 20261102：为什么是 LATE_OR_FUTURE

### 规则（源码）

`research/market_research.py:86-97` `prefix()`：

```python
current = market.load_snapshot(db, day)
j.require(current is not None and current["state"] == "READY", "MARKET_DAY_NOT_QUALIFIED")
j.require(current["catalog_state"] == "VERIFIED" and current["market_denominator_verified"], "CATALOG_SCOPE_NOT_VERIFIED")
j.require(current["catalog_source_day"] == day and not current["late_backfill"],
          "LATE_OR_FUTURE_CATALOG_NOT_DECISION_EVIDENCE")
```

即：目录源日必须等于决策源日，且该快照不能是补录/晚到数据。该检查发生在研究真正开始前，属于 ADR-005/数据时点纪律。

### 证据

- run 元数据（`data/agent/agent.sqlite` meta `market_research_run:20261030/20261102`）：`state=BLOCKED`、`events=["EOD_RECEIVED"]`、reason 即该码；`as_of` 分别为 `2026-11-05T12:57:39.402869Z` / `13:03:51.071218Z`，都在 11-05 晚上。
- `/api/agent/market-research` 的 runs：source_day 20261030/20261102 均 `events=["EOD_RECEIVED"]`、`cloud_status=CLOUD_RESEARCH_BLOCKED`、`selected=null`、`research=null`。
- 补录证据：`logs/market-backfill.out.log` 第 5–6 行显示补录从 `WAITING_RETRY/remaining=4` 到 `state=COMPLETE, sessions=84, remaining=0, last_successful_date=20261105, target_start=20260630`；`supervisor.log` 显示 2026-11-05T13:04:40Z 补录启动、13:05:39Z 以 0 退出，13:05:40Z 才启动当前 watch（pid 24060）。也就是说 30/02 的数据是在 11-05 晚上补回的。
- 两个阻断通知 task #1/#10（`provider_id=market-research-status`，无 calls、无 result）就是该规则产生的可见回执，不是付费调用，也不是普通研究失败。

### 结论

- 预期规则；**不能**通过改数据/绕过 `late_backfill` 让这两天“恢复”，也不应删除通知来假装成功。
- 唯一的自然路径是新的交易日：当日 EOD 在 16:10–18:00 窗口内以 READY、source_day=当日、available_at≤决策时点进入，才会被允许研究。

## 2. 20261105：本地失败的证据边界与已排除项

### 已记录事实

- run 元数据（污染前快照，task #20 创建于 2026-11-05T13:06:25.609Z）：
  - `state=BLOCKED`，`reason=MARKET_RESEARCH_LOCAL_FAILURE`；
  - `events=["EOD_RECEIVED","SCREENED"]`；
  - `as_of=2026-11-05T13:05:43.285867Z`；
  - `screen_sha256=cd560482…`，`plan_sha256=d217672cef…`。
- 冻结计划文件存在：`data/state/timesfm-cpu/market-20261105/plan.json`，1,209,865 字节，mtime `2026-11-05T13:06:24.571Z`。
- 筛选确实成功：`/api/agent/market-research` 第一个 run 显示 `universe_count=5926, qualified_count=3669, selected=8`（300502.SZ、002384.SZ、688012.SH、603986.SH、688256.SH、002371.SZ、002428.SZ、600183.SH），`context_snapshots` 长度 84。
- `tasks` 表中**没有任何** `local-timesfm-2.5-cpu` 任务（当时只有 #1/#10/#20）；说明失败发生在 `cli.bridge("begin")` 创建本地任务之前。
- `logs/eod-watch.err.log` 0 字节，没有 traceback；`eod-watch.out.log` 只有状态 JSON。

### 代码为何无法给出原因

`research/market_research.py:304-318`：

```python
except (j.Rejected, c.Rejected, m.Error, timesfm_model.Rejected, OSError, ValueError, subprocess.SubprocessError) as error:
    code = str(error) if isinstance(error, (j.Rejected, c.Rejected, m.Error, timesfm_model.Rejected)) else "MARKET_RESEARCH_LOCAL_FAILURE"
    ...
    run.update(reason=code, cloud_status="CLOUD_RESEARCH_BLOCKED")
    if isinstance(code, str) and code.startswith(("TIMESFM_WSL_", "WORKER_")):
        run["blocked_at"] = m.h.now()
```

- 所有本地 `OSError/ValueError/SubprocessError` 都被压成通用码，异常文本/traceback 不落库、不打 stderr；
- 只有 `TIMESFM_WSL_*/WORKER_*` 才写 `blocked_at` 并触发 600s 冷却，所以 `LOCAL_FAILURE` 每 ~30s 重试一次（watch 循环 `market_eod.py:646-681`：采集状态非 BLOCKED 时 sleep 30s），
  `eod-watch.out.log` 在 23:22:46Z 已达 **90,040,148 字节**，其中 `MARKET_RESEARCH_LOCAL_FAILURE` 行 223 条、`LATE_OR_FUTURE…` 19 条；每轮都把完整 screen（数千条 rejection）打进日志，磁盘与 I/O 风险持续增长（C: 剩余约 106GB）。

### 已排除（隔离回放）

在 `%TEMP%\stratide-diag` 复制数据根（只读 SQLite backup 复制 agent DB，复制 state/risk-portfolio、state/timesfm-cpu，编辑**副本**的 binding 路径与副本 DB meta），使用安装版 Python 与安装版 research 代码，按 `cli.once` 的相同顺序逐步执行：

| 步骤 | 结果 | 耗时 |
| --- | --- | --- |
| `cli.bridge("enable")` | OK（写副本 DB） | 0.009 s |
| `cli.read_plan("market-20261105")` | OK（plan 可解析） | 0.004 s |
| `cli.model_manifest()`（WSL manifest） | OK | 2.406 s |
| `cli.bridge("project", plan)` | OK（返回 8 只 baselines） | 0.016 s |
| `runtime.preflight(2)`（WSL preflight） | OK（platform=linux、venv/model 路径存在） | 0.335 s |
| `cli.bridge("begin", plan)`（副本 DB） | OK | 0.064 s |

说明：WSL 模型路径/venv/preflight、plan 完整性、bridge 二进制、DB binding 都没有普遍性损坏；失败更可能是当时本地调用的一次性异常或未被分类的错误。**但这只是排除，不是根因证明；根因必须靠补 traceback + 复现获得。**

### 实时重试观测（污染前）

- 每 ~30s 一轮，子进程观测到每轮顺序：`wsl --mode manifest`（约 23:16:24）→ `wsl --mode preflight`（约 23:16:26.9），之后没有 `timesfm-risk-agent.exe` 继续出现的证据；run 元数据保持 `LOCAL_FAILURE`、无 `blocked_at`、无本地任务。说明每轮都走到 preflight 附近后失败，并再次被通用码吞掉。
- 真实实例的 `agent.lock` 实测 **HELD_BY_OTHER_PROCESS**（dashboard 的 `Agent::open` 持有；`research/agent/src/service.rs:20-28,48-61,106-114` 把 `_lock` 保存在 Inner 生命周期内；supervisor 启动 dashboard 时未传 `--desktop-config`，`apps/stratided/src/main.rs:93-97` 因此走 `Agent::open`）。`timesfm_cpu/cli.py:160` 却要求同一把 `agent.lock`，正常结果应是 `WORKER_BUSY`；当前记录不是该码，说明失败发生在更早阶段/被错误分类，这是**独立于本地异常的结构性阻断**。
- 同时观察到 23:12:59Z 起出现 `SCREEN_IMPLEMENTATION_CHANGED_NEW_RUN_REQUIRED`：正是并行探测任务改写真实 run 元数据（`screen.implementation_sha256=bb52…` ≠ 安装文件 `a044…`）后，真实 watch 立即检测到不一致。此后的 live 状态不能用于归因。

## 3. 收盘后自动研究链路逐环状态

| 环节 | 当前状态 | 证据 |
| --- | --- | --- |
| Supervisor / dashboard / watch | 正常 | `/api/runtime/status`：supervisor RUNNING，dashboard pid 25932，watch pid 24060；`supervisor.log` 最近记录 13:05:40Z watch 启动 |
| 行情采集（Tushare EOD） | 正常 | 20261105 EOD_RECEIVED、snapshot READY；Tushare 凭据目标在 Credential Manager 存在；依赖 `tushare_credential=CONFIGURED`、`market_eod=INITIALIZED` |
| 历史补录 / 84 暖机 | 满足 | `backfill.progress.json` sessions_ready 87、remaining 0、state READY；20261105 run 已完成 84 会话 prefix + screen（selected 8） |
| WSL 环境 / TimesFM 模型 | 路径与文件正常，**未持久化探测通过状态** | runtime status: `wsl=READY`、`timesfm=CONFIGURED` 但 reason=`WSL_PROBE_REQUIRED`；WSL 内：Ubuntu-24.04、Python 3.12.3、`.venv`、`models/timesfm-2.5`（timesfm 2.0.2 / torch 2.8.0+cpu）、systemd-run/systemctl/bwrap、cgroup v2 均存在；独立 preflight 回放通过 |
| 本地 TimesFM CPU 执行 | **当前阻断** | `MARKET_RESEARCH_LOCAL_FAILURE`（原因未记录）；无本地 Agent 任务行；watch 每 ~30s 重试 |
| DeepSeek 云端 | 未尝试；配置/凭据/授权齐备 | grant_active=true（v9，valid_until 2036-11-02，84 sessions/8 symbols/20 horizon，fields 与代码一致）；budget CNY ¥5/日、¥100/月，calls=0、reserved=0；Credential Manager 目标 `Stratide/0e70e6…/research-deepseek-v1` 存在；`real_market_e2e=NOT_AUTHORIZED_NOT_RUN`；当前状态字段 `MARKET_RESEARCH_SCOPE_INVALID` 是 store.rs:411 用 owner_task scope 误报 |
| Paper（多证券共享模拟账本） | **当前阻断，且是独立缺口** | 账本存在且已配置（`paper-account.json`、`paper.sqlite`、`stratide-cli paper-portfolio <ledger> status` 显示 equity=10,000,000 分、risk 无锁），但 `state.portfolio` 为空 → `OWNER_PORTFOLIO_POLICY_REQUIRED`；已安装 0.3.0 的 `market_eod.py` 没有 `ensure_policy()` 调用（工作区新版已加、尚未安装）。Paper 步骤把它吞成 `PAPER_LOCAL_INPUT_OR_LEDGER_UNAVAILABLE`（`research/paper_portfolio.py:237-243`） |
| Agent EOD（另一条 forward 路径） | 未运行，非本链阻断 | `/api/agent/status.eod`：enabled=true、latest=null、reason=`NO_NEW_VALID_CURRENT_EOD_SOURCE`；dashboard 以无报告目录启动，Agent 输入为 no_input（health snapshot=null, state=no_input）；这是 forward EOD auto 路径，不能替代 market-research，也不应据此判断链已跑通 |
| 锁 | 存在三把：`agent.lock`（dashboard HELD）、`state/timesfm-cpu/worker.lock`（空闲）、`agent/market-research.lock`（空闲） | 实测：用 `msvcrt.locking` 只读式 try-lock 检查（不写数据）。`agent.lock` 被占是结构性冲突 |

## 4. 修代码还是改配置（最小方案与风险）

### 4.1 先修“可诊断性 + 冷却”（P1，代码，最小）

`research/market_research.py` except 分支：

1. 增加 `run["local_error"] = {"type": type(error).__name__, "message": str(error)[:200], "stage": current_stage}` 并保存；`current_stage` 在 `enable/project/preflight/begin/worker/complete` 前赋值。
2. 把 traceback 写 stderr（`traceback.print_exc(file=sys.stderr)`）——不含 token/密钥；eod-watch.err.log 为空正是当前无法定位的原因。
3. 对 `MARKET_RESEARCH_LOCAL_FAILURE` 也设置 `blocked_at` 并进入 600s 冷却（参考已出现在工作区未安装版本的 `WSL_BLOCK_COOLDOWN_SECONDS` 分支），停止每 30s 重试与日志膨胀。
4. 保留原始码，不把异常文本直接塞进 UI 的 reason 字段；UI 用状态映射 + diagnostics。

风险：低（只增加诊断与限流），不改变财务/授权/时点证据规则。工作区 `research/market_research.py` 已于 23:21 被并行任务加入部分冷却逻辑，需先与 lead 协调避免重复/冲突。

### 4.2 解决 agent.lock 所有权（P1，设计/代码，需 Owner 决策）

现状：dashboard 作为 Agent worker 持有 `agent.lock`；watch 的 TimesFM CPU 也是 Agent worker 语义，要求同一把锁。二选一：

- 方案 A（最小代码）：TimesFM 本地执行改到 dashboard 的 Agent worker 内（watch 只负责采集后触发一次本地任务），或 dashboard 的 supervisor 启动参数改为只读 attach（但会失去 dashboard 调度研究的能力，需要另立 owner API 路由），两者都要重审“single writer/task recovery”语义。
- 方案 B（更小但需明确风险）：给本地 CPU 任务使用独立的 `timesfm-worker.lock`，不拿 `agent.lock`；依赖 `agent.sqlite` 的 IMMEDIATE 事务 + `trigger_key` 唯一键串行化任务创建（`risk_cpu.rs:241-289` 已有事务与 gate）。这是 P1 变更：不涉及券商/资金账本，但会让同一 Agent DB 出现两个 worker 写入者，必须评估任务恢复/预算/风险语义后再做。

**不得**用“删除 run 元数据/绕过 late_backfill/跳过 grant 或预算”的方式让链路变绿。

### 4.3 Paper 初始策略（P1/P2，安装包缺口）

- 已安装 0.3.0 的 `F:\Stratide\research\market_eod.py` 不含 `ensure_policy`；工作区未安装版本已增加（`market_eod.py:649-661` 会调用 `paper_portfolio.ensure_policy(market)` 并把失败 traceback 打到 stderr）。应随下次修复构建一起部署，并确认 `paper_portfolio.ensure_policy()` 成功创建 `fixed-ticket-paper-v1` policy；否则 `state.portfolio` 永远为空。
- 风险：中低（Paper 只读模拟账本，police 初始化只写本机账本；不触真实资金）。

### 4.4 配置侧（不涉及密钥/预算变更）

- 在设置页执行一次“检测 WSL Worker”以把 `timesfm=CONFIGURED/WSL_PROBE_REQUIRED` 从“已保存未探测”变成“已探测通过”，并持久化 probe 结果；这是状态记录，不是链路的唯一阻断（隔离 preflight 已通过）。
- DeepSeek grant/budget/凭据无需修改；Tushare 凭据存在。禁止为“让它跑”而提高预算/扩大数据范围/跳过授权。
- 若要验证云路径，必须先有 TimesFM 成功结果；一次真实调用会产生计费，且当前 `real_market_e2e=NOT_AUTHORIZED_NOT_RUN`，应在 Owner 明确授权和预算窗口内做，不在本诊断中执行。

风险分级：自动化不运行且日志持续膨胀为 **P1**；不涉及 P0（未真实下单、未付费、未外发）。但若并行任务继续向真实 DB 写回，任何“修复后验证”都可能被污染，属于协作风险。

## 5. 不打扰真实实例/不产生未授权付费的验证方法

已执行的安全验证（本诊断）：

1. **隔离数据根**：在 `%TEMP%\stratide-diag` 复制最小数据根——`agent/agent.sqlite` 用 `sqlite3.Connection.backup` 从真实库只读备份，复制 `state/risk-portfolio`、`state/timesfm-cpu/market-20261105/plan.json`；编辑**副本** binding 路径与副本 DB `risk_portfolio_settings_path`。
2. 用安装版 `F:\Stratide\runtime\python\python.exe -I -B` 与安装版 `F:\Stratide\research` 代码执行；环境只设 `STRATIDE_STATE_ROOT=<副本>`、`STRATIDE_BIN_DIR=F:\Stratide\bin`、WSL 四项配置。
3. 逐步调用 `cli.bridge("enable")`、`read_plan`、`model_manifest`、`bridge("project")`、`runtime.preflight`、`bridge("begin")`（全部只写副本 DB），结果见第 2 节表格。
4. 全程未向 DeepSeek/Tushare 发起网络请求；真实库仅只读打开，事后检查真实 DB 无本诊断写入（真实 DB 的变动来自并行 `restore-real-db.py`，非本诊断）。

建议的后续安全验证（修复后）：

1. **完整本地链复现**：在隔离副本中把 run 状态重置为 `EOD_RECEIVED`（只改副本）并复制/硬链接 warehouse 只读 SQLite；在副本 `market_research_config_v1` 中把 `automatic_deepseek=false`（只改副本）以禁止云外发；执行 `market_research.once(market)`，验证到 `TIMESFM_DONE`/本地 candidate，不产生付费调用。
2. **锁冲突复现**：在副本用另一个进程持有 `agent.lock`（模拟 dashboard），对副本执行 `cli.once`，断言返回专用码（当前会是 `WORKER_BUSY`）。
3. **本地失败诊断复现**：复制一份 `research/` 到副本，在 `except` 中打印 traceback；用同一副本+隔离运行，捕获具体异常后再决定是否需要改代码。
4. 只有副本全部通过后，才在维护窗口停止真实 Supervisor/副本切换真实数据根；由 Owner 执行，验证真实安装点后检查 `/api/agent/market-research` 的 runs、calls=0 与 `eod-watch.err.log` 无异常；不要手工删除 run 元数据强制重跑，也不要重跑 30/02。
5. 真实付费/外发验证必须另行获得 Owner 授权，单独记录预算/账单；本诊断未产生任何云调用或行情请求。

## 6. 84 暖机与 natural recovery

- `data/backfill.progress.json`：`{"sessions":84,"sessions_ready":87,"remaining":0,"state":"READY","updated_at":"2026-11-05T21:05:38.714262+08:00"}`；`market-backfill.out.log` 第 6 行：`last_successful_date=20261105, remaining=0, state=COMPLETE, sessions=84`。
- 20261105 的 run 已完成 `prefix()` 的 84 会话校验并生成 screen（selected 8 / universe 5926 / context_snapshots=84），所以“连续 84 个已核验交易日”的暖机与数据可用性对该日满足；当前阻断是本地执行阶段，不是 84 不足。
- 20261030/20261102 的 LATE 是**不可逆的时点证据问题**：补录数据永远不能变成“当时可用”，不会随新数据自然恢复。它们应保持 BLOCKED 并作为历史回执；下一次 11-06 交易日收盘后如果能及时进入 READY 目录，会自动产生新的 run。
- 注意：`sessions_ready=87` 是仓库中 READY 总数（可 >84），不是暖机进度；UI 不应显示 87/84 或 min(x,84)/84。

## 7. 关键证据索引

| 证据 | 路径/命令 |
| --- | --- |
| 运行态/依赖/进程 | 只读 GET `/api/health`、`/api/runtime/status`、`/api/agent/status`、`/api/agent/tasks`、`/api/agent/market-research`、`/api/agent/inbox`（127.0.0.1:8710） |
| run 元数据/任务/预算 | 只读 SQLite `file:C:/Users/wsj20/AppData/Local/Stratide/data/agent/agent.sqlite?mode=ro`：meta `market_research_run:20261105`、`market_research_config_v1`、`market_research_grant:9`、tasks #1/#10/#20/#232、calls=0 |
| 补录/收盘采集 | `data/backfill.progress.json`；`logs/market-backfill.out.log:5-6`；`logs/supervisor.log` 13:04:40–13:05:40Z |
| 当前 watch 轮询/失败重复 | `logs/eod-watch.out.log`（23:22:46Z 90,040,148 B；LOCAL_FAILURE 223 行、SCREEN… 6 行） |
| 本地失败规则/冷却缺口 | `research/market_research.py:86-97, 304-318`；`research/market_eod.py:646-681` |
| 本地任务前置步骤 | `research/timesfm_cpu/cli.py:154-177`；`research/timesfm_cpu/runtime.py:36-61, 196-230` |
| 锁状态/所有权 | `research/timesfm_cpu/cli.py:160`；`research/agent/src/service.rs:20-28,48-61,106-114`；`apps/stratided/src/main.rs:93-97`；`apps/stratide-launcher/src/supervisor.rs:405-431, 604-648`；实测 try-lock：agent.lock HELD、worker.lock/market-research.lock FREE |
| Paper policy 缺口 | `F:\Stratide\research\market_eod.py`（无 ensure_policy）；工作区新版 `research/market_eod.py:649-661`；`research/paper_portfolio.py:104-130, 237-243`；`stratide-cli paper-portfolio <ledger> status`（state.portfolio 为空） |
| WSL/模型 | `runtime.json` wsl 段（Ubuntu-24.04 / /home/wsj20/projects/Stratide-pr70 / .venv/bin/python / models/timesfm-2.5）；WSL 只读检查输出（python 3.12.3、model 目录、systemd-run/systemctl/bwrap、cgroup v2） |
| 云凭据/授权（仅存在性） | meta `provider_profile_v1` 与 `local_timesfm_fusion_config_v1` 的 credential_target；CredReadW 存在性检查：DeepSeek=True、Tushare=True；未打印任何密钥值 |
| 并行任务污染证据 | `state/automation-probe/restore-real-db.py`（2026-11-05T15:18:49Z 写真实 DB）、`patch-impl-hash.py`（15:13:12Z）、`research-probe*.err.log`；真实 run 的 screen implementation_sha256=bb52… ≠ 安装文件 a044… |
| 隔离回放 | `%TEMP%\stratide-diag`（诊断后已删除，仅报告留证）：enable/read_plan/model_manifest/project/preflight/begin 全部 OK，耗时见第 2 节 |

## 8. 需要 lead 立即协调

1. **停止并行任务写真实数据根**：`state/automation-probe/restore-real-db.py` 已改真实 Agent DB；在问题闭环前，真实 live 证据与“修复后验证”都会被污染。建议保留该目录只读、不再执行。
2. 明确由谁改 `research/market_research.py` / `market_eod.py`（工作区 23:21–23:23 已有并行修改，尚未安装）；诊断与修复需在**不同副本**验证，避免互相覆盖。
3. 真实实例的 run 元数据已被改写为 `SCREEN_IMPLEMENTATION_CHANGED` 且 task #232 被并行脚本删除/重建；恢复或清理必须由 lead/Owner 统一操作，且不应在诊断阶段继续动真实 DB。

---

**安全声明**：本诊断未执行任何实盘/模拟下单，未发起 Tushare/DeepSeek 网络请求，未修改代码/配置/真实数据；所有实验写入仅发生在 `%TEMP%` 副本（诊断后已清理），真实库仅以只读方式打开。密钥只检查存在性，未读取或打印内容。
