# Issue #39 开发自测与财务反证

2026-11-01，Windows x64、Rust 1.98.1、Python 3.12.10，Asia/Singapore。固定 base `a02a9b0105cdadab615a6358fa32a57225669d19`，开发分支 `codex/issue39-cash-dividend-v1`，最终 HEAD 由 Draft PR 固定。**Sol 单人开发和自测；agents=0，没有 Terra/子代理，也没有独立审查或合并结论。**

本目录只含人工 synthetic 会计示范、既有公开证据字段、测试日志脱敏副本及 SHA；不含真实原始行情、SQLite/WAL、账户材料、凭据或本机绝对路径。原始运行与未脱敏日志留在本 worktree 新建的 ignored `state/issue39-*` 目录。

## 固定输入与输出

| 项目 | 实际 SHA-256 / 结果 |
| --- | --- |
| schema3 fixture | `e3bed4f9e73bb014fae0cd8d93cd505fb88a23adad7e51b21d0cbb5dad7ee750` |
| 人工事件源 | `20e801be6507ea12c974bf6288d75499f9f2b16d15b481e7020551c2e0a4df0e` |
| 独立会计算法脚本 | `1263f4d1764746277c062192c02ca2fd659c677ea87f3529deedd576fb3b56f8` |
| 新 v4 账本尾 | `336a060a1e379e0dadbb3c25e9cf3795b7119464f5344714c89091ceca893fb3` |
| 旧 68 日账本尾 | `87a12d081d69acfb2379b8ed01376b497259d355a319ed7faccee76eaeadc556`，原样保留 |

[verification.json](verification.json) 给出实际命令/退出码、可执行文件 SHA、旧 golden head、各示范产物 SHA 和测试计数。[test-results.txt](test-results.txt) 是最终命令输出，将本机 worktree 前缀替换为 `<WORKTREE>`；没有修改测试结论。`.gitattributes` 固定新输入/源及评价脚本 LF，并保留本目录证据原始字节，防止 Windows checkout 改变冻结 hash。

实际示范是 [完整七报告](sample-report/report.json)、[每日 CSV](sample-report/daily.csv)、[公司行为审计](sample-report/cash-dividends.json)、[独立评价](evaluation.json) 和 [另一路逐笔反证](counterproof.json)。示范本金 1,000,000 分是命令显式传入的合成参数，不是实际账户授权本金。

## 已执行验证

| 命令/检查 | 退出码 | 结果 |
| --- | --- | --- |
| `cargo fmt --all -- --check` | 0 | 格式通过 |
| `with-msvc.ps1 check --workspace --all-targets --locked --offline` | 0 | 全仓类型检查通过 |
| `with-msvc.ps1 clippy --workspace --all-targets --locked --offline -- -D warnings` | 0 | 无 lint 警告 |
| `with-msvc.ps1 test --workspace --locked --offline` | 0 | **152** 项通过，含原 Risk 33、Ledger 42、forward、Agent、CLI 和只读 Dashboard 回归 |
| `with-msvc.ps1 test -p stratide-ledger dividends --locked --offline` | 0 | 冻结输入规范化后再次执行 **11** 项新测试（含 1 个崩溃子进程入口） |
| `test-cash-dividend.py --exe … --out state/issue39-e2e-final` | 0 | **9** 项真实 CLI/Python E2E，通过双新目录/恢复/负例/独立复算 |
| `test-historical-data.py` | 0 | 原 3 项通过 |
| `test-corporate-action-evidence.py` | 0 | 原 15 项通过，含实际 Windows junction 拒绝 |
| `test-research-evaluation.py` | 0 | 原 5 项通过 |
| 同脚本 + 原冻结 audit/source + 新输出根目录 | 0 | 双新 68 日回放/评价/基准、未来价格反例、坏 split/缺数据/篡改报表反例通过 |
| `cash-dividend-counterproof.py --report …` | 0 | 分离的 Fraction 手算与四种错误模型反证通过 |
| `audit-cash-dividend-source` | **2（预期）** | 真实事件拒绝启用，生成只读 [source-audit.json](source-audit.json) |

完整可复制的合成 CLI 命令及环境见 [M1_PR08](../../M1_PR08.md)。运行原 68 日回归还需要 Owner 本机原冻结五来源和 audit；这些真实原始材料没有随 Git 分发。`verification.json` 中相应命令使用 `<FROZEN_SOURCE>/<FROZEN_AUDIT>/<ORIGINAL_REPORT>` 占位以保护私有位置。

P0/P1 覆盖：100 股 0.42 元、空权益、登记前/登记日买、登记后买卖、0/20%/100% 明示模拟税率、每十股转换/分数分拒绝、逐事件税向上取整与金额溢出、两个非重叠事件、重叠/版本冲突拒绝、乱序/迟到/重复/改 payload、无效估值/未除息旧价、应收不能出资、旧挂单释放及换 ID 旧提案拒绝、税后 NAV/峰值/日初基准和持久金融锁。

三个阶段分别在 `before_commit / after_commit` 注入退出 86，实际启动 **6 个**子进程。重启后完整链重放和 checkpoint 校验通过，原命令至多新增一次事件，再次重试 false；没有重复权益或支付。原报告发布的中断/原子 rename 测试同样通过。这里验证的是 Windows 进程退出/SQLite 恢复，没有声称物理断电保证。

两个全新 CLI 运行：**SQLite 文件字节、全部 events/digest、七报告、evaluation、两类基准账本/报告全部一致**。恢复后的同输入 replay 是 **0 个新事件**，账本文件 SHA 不变；`paper-dividend-report` 重导七文件逐字节相同。独立算法故意篡改 cash/NAV/应收/税/收入/peak/成交费用和 CSV 的反例全部拒绝。

## 逐笔财务反证

以下为固定人工例子的独立手算；不调用 reducer 或主 evaluator：

| 时点 | cash 分 | 持仓市值 分 | 应收 分 | 税负债 分 | NAV 分 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 登记前，买 100 股并付 31 分交易费用 | 899,969 | 100,000 | 0 | 0 | 999,969 |
| 除息后，未到账 | 899,969 | 95,800 | 4,200 | 840 | 999,129 |
| 登记后卖出并付 78 分交易费用 | 995,691 | 0 | 4,200 | 840 | 999,051 |
| 净到账 3,360 分 | 999,051 | 0 | 0 | 0 | **999,051** |

净损益 = `−4,200 价格损失 −109 交易费用 +4,200 股息收入 −840 股息税 = −949 分`。支付只是资产转换。买入持有基准独立账本末日 NAV 999,129 分；现金基准独立账本权益/股息均零、NAV 1,000,000 分。四个错误模型（漏应收、漏税、支付再获利、把股息当 Owner 入金）都与实际恒等式矛盾，见 [反证 JSON](counterproof.json)。

## 旧资产保全与实现范围

[preservation.json](preservation.json) 记录 **17 个**既有文件前后相同的 SHA：五个原来源、原 68 日 dataset、audit/split、六报告、两份评价、PR #38 公开源摘要。新 68 日运行的六报告和评价 JSON/CSV 与原 #17 产物逐字节相同；仍为 **68 日、47/21 已曝光 split、3 笔模拟成交、¥99,966.51**。没有打开原账本、forward journal 或 Agent/candidate 数据库；新测试账本全部在本任务新输出目录中。

| 共享改动 | 必要原因 |
| --- | --- |
| `crates/ledger/src/model.rs` | 新命令、仅 v4 存在且 None 不序列化的股息投影；保留 v3 原 JSON |
| `crates/ledger/src/engine.rs` / 新 reducer | 同一现金、成交、风险路径计入应收净额；交易前时间门、守恒和旧提案拒绝 |
| `crates/ledger/src/store.rs` | 显式新 v4 genesis/hash 域、按版本恢复和全量 audit；原 v3 不迁移 |
| `crates/risk/src/lib.rs` | 统一 NAV 在原风控逻辑前计入可信应收/扣税负债；不改限额或金融锁策略 |
| `apps/stratide-cli/src/replay.rs` / `report.rs` / 入口 | 显式新 schema/命令、真实三阶段命令、权威 ledger 衍生七报告；原模式原格式 |
| `scripts/research-evaluate.py` | 新协议入口；旧协议拒绝股息输入，原 68 日协议不变 |
| `.gitattributes` | 冻结字节跨 checkout 可复现；示范证据 SHA 保持实际值 |

其余为新契约/reducer、适配器、独立 evaluator/反证/测试、人工 fixture 和说明。没有改 contracts 快照结构、forward、Agent、候选或 UI 源码，没有新依赖或账本迁移。

## 失败与修复记录

- 初始普通终端构建退出 1：缺 `link.exe`；使用已有 `scripts/with-msvc.ps1` 后通过，未安装工具链。
- 新 Rust 测试首轮 9 项中 6 项失败：测试辅助沿用 10 月模拟费率却把场景移到 7 月，合法地无成交。明确测试费用有效期后剩 1 项失败，因断言写“现金”而真实拒绝原因是“可用资金不足”；改为核对实际资金拒绝原因后通过，未放宽产品风控。
- 定向检查发现登记日当天成交的 `simulated_at` 是盘后记账时间；修正为按会话收盘及输入可得性锁权益，并加入登记日成交回归。除息前旧提案换 ID 重放也显式拒绝。
- 首次 Clippy 退出 101：新 schema 的 `1 | 2 | 3` 应写成 `1..=3`；修复后 `-D warnings` 通过。
- 旧 Python 首轮默认沙箱临时目录权限失败；改用本任务 ignored 临时目录。原 junction 测试仍因沙箱拒绝 `mklink` 失败，在同一任务临时目录允许执行该原有用例后 15 项全部通过。
- 原文件比较脚本两次路径定位错误（误以为新回归复制了 audit、相对 Path 未 resolve）；修正只读定位后 17 文件保全及 8 产物字节比较完成，没有改任何旧文件。
- 固定 fixture/source 增加 LF 属性并重新冻结最终 SHA；首轮不同字节的开发运行留在 ignored 目录，未清账或重用为最终证据。

## 未完成的现实证据

PR #38 bundle SHA 仍为 `c9b15d74dd687691e9418742fefa22bf70e4843dc6a066cb5f554df43329b49b`，事件事实 `FACTS_PARTIAL`。实际公告识别的 0.42 元/股、7/15 登记、7/16 除息只作只读对照。本例的 **7/20 支付和 20% 税是人工假设**，不能补到真实公告；真实账户身份、最终/递延税负、账户到账、历史版本/PIT 和独立开盘仍缺证。

保持 `historical_pit=NOT_VERIFIED / OPENING_SOURCE=BLOCKED / ELIGIBILITY_DENIED / INSUFFICIENT_EVIDENCE`，新增真实可用历史日 **0**。同证券重叠公司行为、股份类事件、ETF、真实券商和 forward 不在 V1 支持范围。模块的 synthetic 闭环完成，真实历史/实盘资格没有授予；Draft 仍需 ChatGPT 固定 HEAD 审查与 Owner 明确授权。
