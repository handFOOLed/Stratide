# PR #60 R1：质量字段一致性与官方因子语义

针对 [唯一剩余 P1 的审查更正](https://github.com/handFOOLed/Stratide/pull/60#issuecomment-6580297638) 和 [Owner 增量验证规则](https://github.com/handFOOLed/Stratide/pull/60#issuecomment-6580342886)。修复起点是 `4135268e2d3fe6c46a2d5ee85e3c8b81b345e395`；新的固定 HEAD 见同一 Draft PR 正文。本轮无真实采集、无既有数据库写入、无全量历史校验。

## 本轮修改

- `verify` 依据原始响应重新解析出的行、来源请求范围、真实返回容量、质量标记及分片情况，重算 `status/reason/row_count/a_share_count`；任一不一致均拒绝。停复牌 COMPLETE 仍要求 S/R 来源齐全。核对来自 source，不能靠对同一可变数据库字段再做哈希放行。
- [官方文档](https://tushare.pro/document/2?doc_id=28) 支持单日全部股票因子，未声明数字行上限。新响应不再因 1000/6000 等整数量触发截断/分片；合法非空全日响应为 `COMPLETE / SOURCE_RESPONSE_COMPLETE_BY_DOCUMENTED_SCOPE`。其他三个接口的既有 cap 检测/分片保持。
- 新 manifest 用 `quality_rules=documented-scope-v1` 标识准入语义。未带标记的旧 manifest 按旧规则复核、保留原 PARTIAL 标签；旧的未知 cap 原因是历史准入记录，不能再据此声称 API 已截断。未改 schema、合同、数值规范化、冻结查询输出或已有数据库；没有升级既有真实分区的标签。
- 全市场覆盖仍 `PARTIAL`，`historical_pit_status=NOT_VERIFIED / forward_research_readiness=BLOCKED / paper_allowed=false / live_allowed=false`。未扩大到已降为 P2 的复权结果展示工作。

## 红绿测试

测试边界为现有 `verify` CLI 和 Recorded HTTP→collect→query 生产路径；数据全部来自本轮新建、可丢弃的 synthetic SQLite/raw。CLI 测试在隔离目录复制同份生产源码运行，不打开本机真实 store。

| 阶段 | 实际结果 | 证据 |
| --- | --- | --- |
| P1 红测 | exit 1；四 API 的 status/reason/a_share_count 共 12 个篡改场景被旧 verify 误放行；row_count 原检查已拒绝 | [quality-red.txt](quality-red.txt) |
| P1 首轮转绿 | exit 0；16 个字段篡改子用例均使真实 CLI exit 2，且合成库 bytes/SHA/mtime 不变 | [quality-green.txt](quality-green.txt) |
| 因子语义红测 | exit 1；1000 行及 6000 行合法全日响应均被旧逻辑错判为 TRUNCATION_SUSPECTED | [semantics-red.txt](semantics-red.txt) |
| 因子语义转绿 | exit 0；上述两种响应均按官方范围完成，无额外分片请求；旧 manifest 兼容/篡改拒绝同步通过 | [semantics-green.txt](semantics-green.txt) |
| 最终关联回归 | exit 0，8/8；两项新测试 + 四 API/40 日期、三类已知 cap、多分片、修订/下降拒绝、只读无网络、可选字段下降拒绝 | [targeted-green.txt](targeted-green.txt) |

准确命令、执行时间、退出码及各阶段/最终源 SHA 见 [validation.json](validation.json)。发布日志统一清理行尾空白，并将本机工作树路径替换为 `<worktree>`，原日志保留在本地 ignored；JSON 同时记录原日志和发布日志 SHA。没有把两项红测的中间源码当成最终测试源码。

## 复用基线与未重新验证范围

复用 **`4135268`** 的 [真实采集及存储绑定基线](https://github.com/handFOOLed/Stratide/blob/4135268e2d3fe6c46a2d5ee85e3c8b81b345e395/docs/evidence/m2-pr13/README.md)：6068 attempts / 4848 versions / 19221401 rows，原始响应/行/manifest 校验通过；旧 V2 16 项通过、V1 28 通过 + 2 Windows symlink 权限跳过。该基线不包含本次新增的质量字段防篡改结论，不能扩称为新 HEAD 的真实库质量校验。

本轮仅执行上述合成反例及关联回归。未重新打开/校验真实历史数据库，未重算 6068 raw 或 V1/V2 全量文件指纹，未重跑不受影响的 V1、Rust、云/财务套件；无真实 Token 读取和行情请求。`no change to historical data; prior baseline retained`。新的质量校验逻辑尚未在 8.93GB 真实库上重跑；本轮不是独立验收。保持 Draft，等待固定 HEAD 复审，不 Ready、不合并。
