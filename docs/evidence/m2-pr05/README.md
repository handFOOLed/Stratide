# M2-PR05 Windows 开发自测证据

日期：2026-10-30。Base：`05ab0b92106149d65fa865ad5e1837606a4b7d58`。本期依 Owner / [#32](https://github.com/handFOOLed/Stratide/issues/32) 决定，**仅 Sol 实现、自测与故障反证，agents=0**；没有 Terra、第三方测试模型或独立验收。本分支交 Draft PR，ChatGPT 审查固定 HEAD，Owner 授权后才可合并。

## 最终结果

Windows / Python 3.12.10，仅标准库、离线执行：

| 检查 | 实际结果 |
| --- | --- |
| `python -B scripts/test-data-snapshot.py -v` | **11/11 PASS**，exit 0；原输出 [self-test.txt](self-test.txt) |
| 固定 synthetic_test CLI sync/status/snapshot/consume，重复启动 | PASS；源日 20261027，2 日；内容/身份/首次 verified_at 不变，store 仅 1 个快照 |
| 独立合成 journal：新日、重复、晚补、修订 | PASS；新有效日推进，修订保留实际可得时间，晚补不修复当日观察缺口 |
| 冲突、未知日历、pending、ClockFault、raw/SQLite 损坏、回滚/换源 | PASS；失败保留上次快照，独立报告阻断状态，不获得研究/交易许可 |
| 核验中源文件追加、本机刷新时钟回退 | PASS；分别 SOURCE_CHANGED_DURING_READ / SYNC_CLOCK_REGRESSED，保留原 as-of |
| 消费者篡改 | PASS；SHA 不符拒绝；重算 SHA 的未知版本、synthetic 改 real 分别被版本/来源绑定拒绝 |
| 真进程 kill 与并发 | PASS；终止**本测试子进程**时已经写入但尚未提交的新快照不可见，旧快照仍可读；running 不冒称成功；重试发布；并发另一个进程 exit 2 STORE_BUSY |
| 模型/网络/子进程与交易边界 | PASS；同步/消费在网络和 Popen 拒绝替身下运行；交易字段 false，不导入 Agent/Provider/Risk/ledger |
| 原真实 observer 离线 sync → 重启 sync → consume | **PASS**；[实际脱敏 JSON](real-offline-e2e.json)，真实两日/5事件/4raw；没有新行情请求 |
| 包导入 adapter `from research.data_snapshot import Store` → consume | PASS；与真实 CLI 产生的 snapshot SHA 和源日相同 |
| 原 observer、历史 ledger、六报告、Agent SQLite 保全 | **9/9 前后 SHA 一致**；始末均无 WAL/SHM/journal；只读哈希比对，未停止服务 |

真实读取的最新源日是 **20261029**，不是本机 10/30。Journal HEAD：`28a8f562c7df902ced5fe03a38ceb22f8f44190da3df67944771e075effa8b66`；原库 SHA：`d4020489f0485554ec092e9e8e84026998aa54248ac3268df46aeb040ee0585e`；发布的内容 SHA：`3def7bf43e54d889a68db292b09cfe0885782f650438792b01baff70f44cde03`。原库和 raw 摘要与 #10 的既有冻结锚点一致。两个 snapshot 版本的实际时间与 raw 摘要在本地持久保存，公开证据只含元数据。

原历史/Agent 文件只用于有针对性的哈希保全，没有读取私有任务内容、行情 raw 正文到证据或拷贝数据库。9 文件是本轮明确覆盖范围，**不声称复验了过去全部 98/137 文件**。JSON 的保护清单摘要只含有序 SHA 列表的哈希，不含路径或文件内容。

## 首轮失败与修复

首轮实际执行 10 个测试，结果 **FAIL：1 个断言失败、10 个 tearDown 错误**，未当作环境跳过或 PASS：

- Python `with sqlite3.Connection` 只完成事务，不关闭连接。原只读 reader 和合成 fixture writer 的句柄未及时释放，Windows 删除新测试目录报 WinError 32。改用显式 `closing()`，fixture 写入显式提交。原 journal 未被删除/修复；失败目录留在本分支 git-ignored 测试区。
- 初版锁在获取 Windows 字节锁前读取锁字节；竞争者先报通用 `LOCAL_STORE_OR_INPUT_ERROR`，没有得到预期 `STORE_BUSY`。改为仅在空文件初始化字节，之后直接获取进程锁。最终测试实际进入并发拒绝、kill 和恢复断言。
- 新 snapshot store 使用标准 SQLite WAL/FULL 事务，避免中断后只读消费者无法处理 DELETE 模式热回滚日志；原 observer 模式/文件不变。

最终上述同名测试均 PASS，另增加 1 项必要的源追加/本机时钟故障测试，共 11 项。失败记录未写成独立验收结论。

## 未验证与停止边界

没有 Rust 改动，因此未重跑 Rust fmt/check/test/Clippy 或全仓测试；没有 paid CI。未读取 Token / 其他项目凭据，未采新 EOD、请求真实云 Provider 或运行任意生成策略。无真实开盘证据、forward Paper fill/NAV、物理掉电、OS 重启或跨平台证明。`historical_pit=NOT_VERIFIED`，`opening_source=BLOCKED`，`can_execute_forward_paper=false`，`live_allowed=false`。

本期提供稳定 adapter + offline consumer；Agent 自动输入接线和 Dashboard 集成未实施。原始行情、财务 DB、私有任务及本机绝对路径不上传。CLI/字段/恢复语义见 [M2_PR05](../../M2_PR05.md)。
