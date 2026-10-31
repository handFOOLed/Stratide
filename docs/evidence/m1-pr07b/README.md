# Issue #37：公司行为证据包执行记录

2026-10-31，Windows x64 / Python 3.12.10，Asia/Singapore。固定 base `a522c2925ac3163358bb2b32c84119f2a3ef4a3f`，分支 `codex/m1-pr07b-evidence`，固定交付 HEAD 见 Draft PR。以下为开发自测及人工来源核对，**不是独立验收**；无子代理、Terra、云模型、付费 API 或 CI。

## 真实来源及实际结论

已下载并核对[巨潮公告 PDF](https://static.cninfo.com.cn/finalpage/2026-07-10/1225416710.PDF)，108,034 bytes / 3 页，临 2026-021；保存精确字节与实际获取回执。PyMuPDF 仅用于本次本机转写/目视核对，不是产品依赖。完整可公开输出见 [real-summary.json](real-summary.json)。

| 产物 | SHA-256 |
| --- | --- |
| 原始实施公告 PDF | `afe3ee2cf61dcd1e9e76d2b8d4a93a2cc16fd7ea27eb89da815b8a808f8de386` |
| 人工核对的逐页文本 | `af6d8832c28939476735818780d82d3976ff20af4d023c1cacf370216890ae86` |
| 最终真实证据包业务 SHA | `c9b15d74dd687691e9418742fefa22bf70e4843dc6a066cb5f554df43329b49b` |

实际获得为 `2026-10-31T13:50:22.362722Z`，即本地 21:50:22；首次最终核验 `2026-10-31T14:00:46.858000Z`。文档落款为 2026-07-09，巨潮 URL 日期为 2026-07-10；精确披露时刻 `published_at=null`，仅将落款标为 `document_signed_date`。两者均未冒充当年本机实收时间。

原文已支持：证券、公告号、现金分红事件、落款日期、登记日 7/15、除息日与安排发放日 7/16、每股税前人民币 0.42 元及派发时暂不扣缴的局部税务条款，共 **12/19** 个字段。账户净现金额/实际到账、送股/转增/配股比例、股份上市/可卖日仍为 null，逐项列 blocker；本轮不认定这些股份事件实际存在，也不替未知值填零。首次预案原文和修订全史没有取得；搜索结果仅用于定位，未作为原始公告入包。

| 独立维度 | 实际结果 |
| --- | --- |
| `event_fact_status` | `FACTS_PARTIAL` |
| `historical_pit_status` | `NOT_VERIFIED` |
| `accounting_support_status` | `NOT_IMPLEMENTED` |
| `historical_replay_eligible / eligibility` | `false / ELIGIBILITY_DENIED` |
| `opening_source` | `BLOCKED` |
| 日期及来源金额一致性 | `DATE_MATCH`；已取得现金额与断点价格差相符；未由价格生成事件参数 |

上交所定位到的[同题 PDF URL](https://static.sse.com.cn/disclosure/listedinfo/announcement/c/new/2026-07-10/600000_20260710_23SH.pdf) 实际返回 3,872 bytes HTML，不是 PDF，未作为证据入包。发行人索引搜索能定位该题，但本次直接读取未得到可用公告正文；不把索引/二手摘要当首次披露原文。仅调查本证券最近断点，未调用新增出现的 Tushare 事件工具、读取 Token 或扩展抓取。

## 最终 Windows 自测

原始材料、失败/成功日志、清单、恢复副本与 SHA 保全记录均在本任务 ignored `state/issue37-final/`；首轮开发包仍保留在 `state/issue37/`。未提交原 PDF/全文、原始行情、本机绝对路径、SQLite、凭据或账户材料。

| 实际命令/流程 | 退出码及证据 |
| --- | --- |
| `python scripts/test-corporate-action-evidence.py` | 0；最终 15 项测试通过 |
| `audit --source-manifest … --out state/issue37-final/real-v1` | 1；真实 `PARTIAL` 包，业务 SHA 如上 |
| `status --bundle …/real-v1` | 1；从包内源文件重算，公开输出与 audit 逐字节相同 |
| 同输入/同输出再次 audit | 1；原包不写，时间和输出字节保持不变 |
| 包内 `manifest.json` → `real-restored-v1` | 1；新目录业务 SHA 相同，独立核验时间不参与业务 hash |
| 固定缺证清单 audit | 2；生成真正 `DATA_BLOCKED` 包及具体依赖缺单，status 可重读 |
| `python scripts/test-historical-data.py` | 0；原 3 项测试通过 |
| `research-evaluate.py audit`，旧冻结五输入，新 ignored 输出 | 0；681 日、三断点，旧安全后缀 68 日，目标仍 DATA_BLOCKED |
| `test-research-evaluation.py --exe … --audit-dir … --source-dir … --out …` | 0；5 项单测及实际 CLI 双目录 replay/evaluate/benchmark 与原反证通过 |
| `historical-data.py prepare … --start 20260706 --end 20261028` | 2；原公司行为断点拒绝仍有效，无 dataset 发布 |
| 同 CLI `--start 20240101 --end 20261028` | 2；原 20260706 费用/规则下界仍有效 |

15 项测试涵盖完整合成事件（只能 `SYNTHETIC_PASS`）、缺公告/日期/单位、冲突及显式更正版本、重复公告、源 SHA/quote 不符、晚披露（含同日晚于决策一分钟）、上海事件日期与 UTC 时刻比较、业务 SHA 与核验/获取时间分离、半写入及 rename 失败重试、不可覆盖旧包、source/summary 篡改、schema/单位/日期/大小/路径、**实际 Windows junction** 拒绝，以及合成历史断点匹配/不匹配、不能从价格补造金额。合成 PASS 没有增加真实历史 PIT 或前向观察日数。

失败与修复：首轮 13 项中 12 项通过，junction 创建被沙箱拒绝，测试退出 1；允许在本任务 ignored 临时目录执行该必测文件系统操作后通过，随后补入历史一致性和时区用例成为最终 15 项。新增时区测试曾因晚披露断言放错测试方法而失败，归回正确方法后全部通过，失败日志保留。转写首次打印因 Windows GBK 无法编码 PDF 项目符号失败，已设置子进程 `PYTHONIOENCODING=utf-8`，未改原 PDF。增加精确披露时间字段后另起 `issue37-final` 证据目录，未重写首轮包。没有通过删除测试来处理失败。

## 旧文件保全与回归范围

实际读取的 15 个旧文件 SHA 前后全相同：五份原冻结 source、旧 68 日 dataset、旧六报告、旧评价 JSON/CSV，以及复用的既有 CLI exe。**没有读取/复制旧 ledger SQLite、WAL、EOD journal、Agent 或候选数据库**；回归中的 ledger/benchmark 仅在新 ignored 目录生成。新代码不导入 Agent/Provider 或财务执行 API。

| 原 source | SHA-256（本次前后一致） |
| --- | --- |
| `daily.json` | `5689c59e8fa92b5ca2499141c3b4e199b168ea02f70b385c8a24eb81340d2075` |
| `calendar.json` | `284cbb28d12f576ae93e54b0bd8abf516a595cc668f56363cd2cfbb68a4d5bf9` |
| `limits.json` | `dabd396dc7594bf90c74118d92be256c87667bc0cfd46af08b7c9f1861ceec2f` |
| `suspensions.json` | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| `extraction.json` | `5eb1abff2764e414f484d9610807af7544fa672ccf6228056796f4a5337e4075` |

原 extraction 实际时间仍为 `2026-10-29T05:16:51.993Z`。原始五文件只有只读 SHA/解析访问；包内副本没有重写其提取时间。

本次新回归的 dataset、六报告及 evaluation JSON/CSV **分别与原 #17 产物逐字节相同**，双新目录产物也相同。仍是 20260717–20261028 的 68 日、3 笔历史模拟成交和 47/21 已暴露 split；没有新收益或扩大窗口。Rust 和依赖未修改，因此未机械重跑 Rust 全仓/构建；回归复用了既有 main 对应生产源码的 Windows CLI，exe 仅只读且 SHA 保全。不声明本期 Linux/macOS 或独立审查已通过。

本期工程交付是可运行、可重读/恢复、能明确拒绝的源证据闭环。后续只有另行授权共享财务会计增量，才可讨论跨断点回放；正式历史 PIT、真实开盘或实盘资格仍未取得。
