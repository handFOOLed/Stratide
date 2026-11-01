# Issue #41 / M1-PR09：开发自测与脱敏证据

2026-11-01，Windows x64、Python 3.12、现有 Rust/MSVC。base `287dfe8583fe63f199215d0fb2f440864572974a`；分支 `codex/issue41-historical-dividend`，固定 HEAD 见 Draft PR。Sol `agents=0` 单人开发、自测及修复；没有 Terra、其他代理、独立审查者验收或合并。

**EXPLORATORY_EX_POST / PIT_NOT_VERIFIED / ELIGIBILITY_DENIED / OPENING_SOURCE=BLOCKED / REAL_PROVIDER_NOT_VERIFIED。真实 PIT 新增 0 天。**

## 实际运行结果

| 维度 | 结果 | 证据 |
| --- | --- | --- |
| 原冻结行情情景 | 20260706–20261028，原日历得到 77 会话，包含 20260716 已观察断点 | [real-summary.json](real-summary.json) |
| 人工合成系列 | 20260706–20260828，40 会话、明确人工价格和人工日历 | [synthetic-summary.json](synthetic-summary.json) |
| 完整工程链路 | `ENGINEERING_RUNNABLE`，双新冻结 / v4 账本 / 七报告 / 评价一致 | 同上 |
| 真实历史准入 | `DENIED`，`INSUFFICIENT_EVIDENCE`，PIT 新增 0 | 同上 |
| 旧记录保全 | 17 文件 SHA 前后相同；原六报告、评价 JSON/CSV 字节相同 | [preservation.json](preservation.json) |
| PR40 兼容 | 原 synthetic 七报告与已提交的 PR40 sample-report 逐字节相同 | [preservation.json](preservation.json) |
| 独立手算反例 | 人工 100 股除息日净值变动 -1640 分；支付不再计收益 | [counterproof.json](counterproof.json) |
| 新 CLI 反例 | 11 个针对性测试通过，包括多个失败输入与恢复分支 | [self-test.json](self-test.json) |
| 命令、退出码 | Rust、Python、真实行情 CLI 及旧区段回归 | [verification.json](verification.json) |

实际的 681 行原 daily、原提取时间、PR38 原文/文本、实际公告取得时间和模型假设完整 manifest 均保留在本机新 ignored 输出；没有提交原始行情、SQLite、全套私有报告、个人路径或凭据。公开内容限于日期、状态、源 SHA、会计恒等式、反例和 blocker。

真实情景冻结 input SHA：`213e63578695cbecd1e782d31d5930fe98a9f97d5447ae38434614f8bcdbd956`；独立模型清单 SHA：`270ef5dcfe49bc48e9627b84d5eefa6eea42138ba0cb836aaec0dec635edd6af`；PR38 原业务 SHA：`c9b15d74dd687691e9418742fefa22bf70e4843dc6a066cb5f554df43329b49b`。

## 执行与覆盖

完整操作见 [M1_PR09](../../M1_PR09.md)。执行日志保存在本任务的 ignored `state/issue41-checks/`；最终人工 E2E 在 `state/issue41-delivery-tests/`，真实行情 E2E 在 `state/issue41-commit-real/`。所有账本和报告都新建，没有读取原旧账户数据库或 forward journal。

- `cargo fmt --all -- --check`、`cargo check --workspace --locked --offline`、`cargo clippy --workspace --all-targets --locked --offline -- -D warnings`、`cargo test --workspace --locked --offline`、CLI build 均退出 0；全仓 **155** 项测试通过。Windows 通过现有 `with-msvc.ps1` 注入工具链，Clippy 参数用数组 splat 保留 `--`。
- `test-historical-dividend.py`：**11** 项及真实子进程 CLI 链路通过；坏 SHA、缺日、错日历、重复/额外断点、负数/溢出、错误单位/版本、税/支付模型、旧路径拒绝、前缀 SMA/未来价格、独立现金/NAV/应收/税/风险峰值/预留篡改、无源退出 2、三阶段提交前后前缀恢复与重复重放不加事件。还执行 0%、20%、100% 模型税与同开盘 ex/payment 比较。
- 原 PR40 `test-cash-dividend.py`：**9** 项通过；有/无仓、登记后买卖、应收不可买、金融锁、旧 v3 golden、双基准及七报告均兼容。新 Rust 历史 v4 用例验证旧挂单释放、同开盘阶段接线、真实进程退出于提交前/后及恢复；原三阶段崩溃和保守撮合用例也通过。
- 原 `test-historical-data.py` **3** 项、`test-research-evaluation.py` **5** 项通过。另用原 audit/source 执行真实旧 68 日 CLI 双回放、评价、基准与反例，输出与旧冻结结果逐字节相同：68 日、3 笔、末 NAV 9,996,651 分；原 47/21 split 未变。
- PR38 `test-corporate-action-evidence.py` 原 **15** 项：首轮 14 通过，实际 junction 创建被沙箱拒绝；仅该用例在允许的本任务临时目录中复跑后通过。晚披露、冲突修订、源引用/金额单位及原 status 防篡改测试均保留。
- 真实原源实际执行 `historical-dividend.py run`：离线准备、独立预检、第二份冻结、两个 v4 replay、每份七报告、两组独立现金/持有 v4 基准、SQLite 副本重导出、独立 Python 时间/会计复算全部退出 0。公开命令中的旧私有输入位置用占位符脱敏，实际输入 SHA 已固定；没有数据请求。

Python 算术审计与 Rust reducer 分开实现，仍由同一个 Sol 执行，**不是独立审查者 PASS**。下一步仅为 ChatGPT 对该 PR 固定 HEAD 审查；Owner 明确授权后才可合并。

## 开发中失败与修复

首次新 E2E 因历史 fill 的 `opening_evidence` 字段按 serde 规则省略，Python 直接索引触发 KeyError；改为按缺席语义读取，保持不伪造开盘证据，最终 E2E 和反例通过。一次新增 Rust 断言多写右括号，fmt 报错后修复。

原 Python 临时目录和 Rust 报告发布恢复测试在沙箱默认 TEMP 下遇到权限拒绝，改用本任务 ignored TEMP 后通过；junction 用例的具体限制和复跑如上。Clippy 初次脚本调用丢失 `--`，改为数组 splat；一次构建与正在使用 exe 的 CLI 测试重叠导致 Windows 文件占用，等待测试结束后按顺序构建/测试通过。没有通过删测试或放宽产品规则消除这些失败。

调用方检查补上旧 `paper-benchmark` 对 schema4 的显式拒绝，并以参数正确的实际 CLI 命令验证；新基准分别记录独立的买入持有和纯现金版本。原 SMA 数值算法、费用和信号时序不变，仅将限价 offset 的加法改为溢出时返回错误，避免坏整数输入发生 panic。

## 未取得的现实资格

原真实 `FACTS_PARTIAL` 和 PR38 `audit/status` 输出不变。模型 20% 扣税、7/20 支付、零股份变化及无其他动作都是显式人工假设，原事实未补齐。没有新 OOS、真实账户税/递延税/到账认证、前向开盘、实盘、云 Provider 或候选资格提升；其他 OS 与物理断电未验证。
