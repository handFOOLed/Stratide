# M1-PR07B：离线公司行为证据包 V1

[Issue #37](https://github.com/handFOOLed/Stratide/issues/37)，2026-10-31，Asia/Singapore。固定 base `a522c2925ac3163358bb2b32c84119f2a3ef4a3f`；Sol 单人实现和自测，`agents=0`。本功能只核验来源，不给数据、策略或交易授予资格。

```text
可信本机来源清单 + 原文/人工核对的逐页文本 + 原冻结历史 JSON
  → schema / SHA / 引用 / 日期与单位校验
  → 新 ignored 原子证据包 → status 只读重算
  → 事件事实、历史 PIT、共享会计分别报告；回放资格始终 false
```

## 使用及退出码

Python 3.12，只有标准库；无需新依赖、Token、网络或 Rust 构建。在本 worktree 根目录执行：

```powershell
# 可跨机器复现的真实缺证路径：退出 2，同时生成可重读的 DATA_BLOCKED 包。
python scripts/corporate-action-evidence.py audit --source-manifest research/fixtures/corporate-action-missing.json --out state/ca-missing-v1
python scripts/corporate-action-evidence.py status --bundle state/ca-missing-v1

# 本次机器已有的真实来源（资料不随 Git 分发）：两条预期退出 1 / PARTIAL。
python scripts/corporate-action-evidence.py audit --source-manifest state/issue37-final/source-manifest.json --out state/ca-real-v1
python scripts/corporate-action-evidence.py status --bundle state/ca-real-v1

# 从冻结包恢复到新目录，不再依赖原来源绝对路径。
python scripts/corporate-action-evidence.py audit --source-manifest state/ca-real-v1/manifest.json --out state/ca-real-restored-v1

python scripts/test-corporate-action-evidence.py
python scripts/test-historical-data.py
```

| 退出码 / `status` | 含义 |
| --- | --- |
| 0 / `FOUND_VERIFIABLE_EVENT` | 事件字段完整且原文引用一致；合成输入的 `event_fact_status` 只能是 `SYNTHETIC_PASS` |
| 1 / `PARTIAL` | 来源可读，事件字段仍缺；每个空字段为 `null`，附具体 blocker |
| 2 / `DATA_BLOCKED` | 无有效实施公告或版本冲突；合法缺证清单仍发布拒绝包 |
| 2 / `DATA_BLOCKED + error_code` | schema、SHA、路径或 I/O 校验拒绝；不会把残包发布为成功 |

退出 0 只说明来源审计完成。V1 在所有输入下固定 `historical_pit_status=NOT_VERIFIED`、`accounting_support_status=NOT_IMPLEMENTED`、`historical_replay_eligible=false`、`ELIGIBILITY_DENIED` 和 `opening_source=BLOCKED`。

## 可信清单契约

清单的完整机器 schema 由 `research/corporate_actions.py` 中 `evaluate`、`FIELDS` 定义，未知字段拒绝；[缺证例子](../research/fixtures/corporate-action-missing.json) 可直接执行。顶层必须包含：

| 字段 | V1 约束 |
| --- | --- |
| `schema_version / evidence_kind` | `1`；`public_document` 或 `synthetic_test`，不混合两类证据 |
| `symbol / breakpoint / decision_at` | 只支持 `600000.SH / 2026-07-16`，决策时刻为带时区时间戳，按上海事件日期限定当日，精确时刻归一为 UTC；不把研究期望当作收到时间 |
| `documents` | 最多 8 份，见下方；原文和逐页文本必须都存在 |
| `events` | 最多 8 个 `{source_id, facts, references}`；`facts` 必须明确列出全部 19 个字段，未知填 `null` |
| `historical_source` | `null` 或 `{directory, sha256}`；固定五文件 `daily/calendar/limits/suspensions/extraction.json`，每个有 SHA；只读，不接受 SQLite |

每份 document 的全部字段为：`id, role, version, supersedes, document_id, path, sha256, text_path, text_sha256, public_url, obtained_at, disclosed_on, published_at, disclosure_basis, review_method`。`role` 为 `initial/implementation/correction`；`supersedes` 为已列文档 ID 或 `null`，关系不得成环。文档版本冲突保留全部，不自动挑最新或最有利版本。

- `path/text_path` 只允许清单目录内的相对路径，无 `..`、符号链接或 junction；每文件最多 4 MB，原文限定 PDF/TXT/HTML。历史来源目录可显式指向旧冻结目录，但文件名固定；读前后校验字节。
- `public_url` 仅允许列出的发行人、上交所、巨潮 HTTPS 公共链接，无用户信息、查询参数或 fragment；CLI **不 fetch URL**。缺少公共来源的声明不能取得真实来源 PASS。
- `obtained_at` 为真实获得时刻；`disclosed_on` 连同 `disclosure_basis` 区分文档落款日、发布目录日期或未核实。`published_at=null` 明示精确披露时刻未知，绝不补当天零点。晚披露/事后获取均列 blocker。
- `review_method` 固定为 `operator_manual_document_text_crosscheck`。先由可信操作人核对 PDF、文本和列含义；PDF 转写以 form-feed 分页。每个非空事实引用 `{page, quote}`，CLI 验证引用出现在该页，日期/数字/单位字面支持其值。**SHA 和 quote 验证不认证网站身份，也不能证明任意 PDF 与转写语义一致**；不将可信清单改造成任意外来文件的自动认证器。
- 19 个事实字段：`symbol, event_id, event_type, announcement_date, record_date, ex_date, scheduled_pay_date, cash_amount, cash_unit, currency, tax_basis, tax_terms, net_cash_amount, stock_dividend_ratio, capitalization_ratio, rights_ratio, stock_listing_date, sellable_date, actual_account_cash_received_at`。数值用十进制字符串；单位明确为每股或每十股人民币，税前后分开；公告安排的发放日不是账户实际到账。
- 相同公告/事实重复不会增加证据；字段冲突输出 `SOURCE_CONFLICT`。未知字段不补零；未知送转比例不等同于确认存在送转，也不等同于确认比例为零。

## 存储、幂等与恢复

`--out` 必须是仓库 `state/` 下受 Git ignore 的新目录。包内包含 `bundle.json`、规范化 `manifest.json`、内容寻址原文/文本及五份历史 JSON 副本；不含原账本/数据库。对新 sibling 临时目录逐文件 `fsync`，完整重算验证后一次 rename 发布。异常只留下未发布 sibling；重试使用新 sibling，不把半写入目录视为成功，也不删除旧证据。

`bundle_sha256` = 按 UTF-8、排序 key、紧凑分隔、禁止 NaN 的 canonical JSON 计算的**业务内容** SHA。来源 bytes/版本、事实/引用、解析版本、原历史 SHA、缺口结论都参与；实际 `verified_at`、`obtained_at` 和本机路径不参与。获取时刻跨越历史决策边界会改变可得性 blocker，这属于业务差异。单独 `verification_sha256` 绑定核验时间和获得时间，避免元数据意外修改。Hash 是一致性校验，不是独立认证签名。

相同来源重新 audit 同一输出时只读原包，保留首次核验时间；不同业务内容必须换新输出。`status` 从冻结文档、转写、清单和历史 JSON 重算全部结论，检查业务和元数据摘要；它不仅读一个缓存 PASS。恢复时将包的 `manifest.json` 用作新 audit 输入即可；所有原始材料只保存在 ignored 本地。

## 本次真实结论及下一条边界

已实际取得[巨潮实施公告](https://static.cninfo.com.cn/finalpage/2026-07-10/1225416710.PDF)，公告编号临 2026-021。原文支持每股税前现金红利 0.42 元、2026-07-15 登记、2026-07-16 除息及安排发放；文档落款为 7 月 9 日，URL 日期为 7 月 10 日，精确首发时刻未核实。页面路径日期未被回填为本机历史实收。金额来自公告，之后才与原 `pre_close` 断点做只读比较。[本次运行证据](evidence/m1-pr07b/README.md) 列 SHA、字段及保全结果。

事实 `FACTS_PARTIAL`：12/19 字段有字面支持；账户净额和实际到账、三类股份比例、上市及可卖日仍为 null。只核实了自然人/基金在派发时暂不扣税这一局部条款，不认定最终税负或适用账户身份。未取得首次预案原文，未核实修订全史，历史 PIT 仍未认证。原 v3 ledger 缺登记日权益、应收/到账、递延税务、股份可卖及统一 NAV/报告事件，`ACCOUNTING_NOT_IMPLEMENTED`。

旧 68 日、47/21 已暴露 split、策略/费用、六报告、历史评价与 forward journal 均不变；本次没有扩大可回放日数，没有新收益结论。共享会计、历史 PIT 和真实开盘证据须按后续独立任务处理，本期不授权跨断点回放。
