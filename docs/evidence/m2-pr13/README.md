# M2-PR13 开发自测与真实回填证据

执行 [Issue #59](https://github.com/handFOOLed/Stratide/issues/59)，基于真实 fetch 的 `main 9a030459127da60028098a43adc8316c3988da35`，独立分支 `codex/issue59-historical-sidecar`。唯一 Draft PR 的固定 HEAD 以 PR 正文为准。[契约与命令](../../M2_PR13.md)；[最终源码 SHA](tested-source.json)。本目录是开发者自测及真实采集证据，不是独立验收、历史 PIT 认证或交易授权。

## 真实执行结果

固定 **2021-11-01—2026-10-30，1212 个已核实沪深开放日**，四个接口均按完整区间运行。总请求 **6068 / 6979**，所有实际成功/失败/未知均计数；实际磁盘 **8926085760 bytes**。首/末真实取得 UTC：`2026-11-02T10:23:45.353764+00:00` / `2026-11-02T14:23:42.415409+00:00`。准确状态、数量、未覆盖日期、原因分布及 API 级来源收据整体 SHA 见 [real-summary.json](real-summary.json)。

| API | 当前版本记录 | A 股代码家族记录 | 证券代码数（含非 A 股/身份未核实） | COMPLETE / PARTIAL / 未发布日期 |
| --- | ---: | ---: | ---: | ---: |
| adj_factor | 6416218 | 6416218 | 5783 | 0 / 1212 / 0 |
| daily_basic | 6336488 | 6336488 | 5772 | 1212 / 0 / 0 |
| stk_limit | 6424625 | 6351150 | 5862 | 1179 / 33 / 0 |
| suspend_d | 44070 | 44070 | 1758 | 1212 / 0 / 0 |

`adj_factor` 未有官方明确行上限，不把正常响应自行升级为穷尽，日期保留 PARTIAL。`stk_limit` 真实出现代码后缀与来源 exchange 冲突，原因子/参考价格/来源 exchange 均未纠正或覆写，只标质量；B 股和其他非 A 股不会冒充 A 股。`daily_basic` 保留 NULL、负估值、零和官方单位。停复牌 S/R 分开请求，空事件不证明可交易。

总体始终 `coverage=PARTIAL / historical_pit_status=NOT_VERIFIED / forward_research_readiness=BLOCKED / paper_allowed=false / live_allowed=false`。没有完整历史身份名录或独立 BSE 日历，不因日期均下载就认证全市场完整。

## 预检、网络中断与显式续传

[真实命令/exit/起止时间/耗时](real-runs.json)、[真实预检收据](preflight-receipts.json)、[25/50/75/100% 里程碑](milestones.json) 保留实际执行，不用 exit 0 代替日期质量。预检先因来源 exchange 冲突返回 exit 2；保留原响应，标 PARTIAL 后预检通过并立即全区间回填。

全区间执行共记录 **3 次网络未知结果**，HTTP/供应商码及 raw 均未取得，未计成功。Owner 反馈前两次与本机网络切换相关；该原因是 [Owner 反馈](network-cause.json)，后一次网络中断原因未独立核实，不是供应商故障或额度拒绝的独立结论。原未知尝试和恢复位置保留；没有后台自动重试。无凭据 DNS/TCP/TLS 检查连通后，V2 复用原安全 HTTPS 链路，将读取等待由 40 延至 120 秒、降速至 30 次/分钟，再显式续传。遇到单日失败后先让普通 resume 跳过已知失败 scope、继续其余日期，最后单独恢复缺口。累计硬上限没有扩张。[首次中断](network-interruption.json) / [后续诊断](network-interruptions.json)。

原始 HTTP、SQLite、目录、完整请求审计及含数值查询都留在本地 ignored `state/`；本目录只公开统计、哈希、必要审计和测试输出。新环境按授权重新取得数据，不上传 GB 级仓库，也不强制复制旧库。

## 全量来源校验和查询

[真实最终命令与 exit](verification-runs.json) 中 `verify` 对全部 **6068 attempts / 4848 versions / 19221401 rows** 执行 SQLite integrity/FK、合同/元数据/原字节 SHA、真实 JSON→Decimal→规范化→逐日行集合→manifest 的复算。结论仅为 `VERIFIED_STORAGE_SOURCE_BINDING`。

[查询证据](queries.json) 包括 600000.SH、000001.SZ、600519.SH 的固定 20 个交易日四 API 查询、四 API 单日全市场读取、三证券冻结锚点前复权。只公开结果行数、SHA、版本和质量；具体市场数值留在本机。零停牌事件也返回覆盖日期来源和缺口，不补“正常交易”事实。

全部只读命令前后 **6067 文件 / 8926085760 bytes** 的 SHA/长度/mtime 相同；不读 Token、不联网。随后真实运行固定 20 日 `resume`，**0 新请求、0 新数据行**，原历史失败记录仍保留。原 V1 库及指定 Operator/Shadow/Multimodal/RiskPortfolio/旧 Agent 状态共 **4298 文件 / 4605406031 bytes** 的 SHA/长度/mtime 与采集前基线相同。完整本地基线不对外发布路径/内容；整体 SHA 在 summary 中。

## 测试、源码时间线与限制

- [V2 16 项定向离线测试](sidecar-tests.txt) / [命令、exit 与源码绑定](test-run.json)：四 API、40 日期、多市场/退市证券、精确值/NULL/负值/单位、S/R/日内暂停、四种恰好 cap、多分区和目录外代码、重复/修订/回改/下降拒绝、网络未知/429/额度/权限、预算、双进程、真实子进程强制退出、只读 CLI、junction/异类 SQLite 和冻结锚点。最终 16/16 通过。
- [V1 兼容回归](v1-tests.txt) / [准确说明](v1-test-run.json)：30 项中 28 通过，2 个文件 symlink 用例因 Windows `SeCreateSymbolicLinkPrivilege` 不可用跳过；真实目录 junction 拒绝用例通过。V1 生产及原测试文件未修改。没有重跑无影响的 Rust/云/策略/财务回归；其他 OS 与物理掉电未验证。
- 初始采集进程载入的源码 SHA 为 `c4b4ae48bdbe8430ba93388a3edfea8d7c54b147b8a78886dfd81763b6f42ad4`；运行期间完善了查询/校验与显式重试门禁，后续续传又应用了读取等待调整。各真实运行分别记录实际载入的源码 SHA，不能把结束时磁盘文件 SHA 当成起始进程源码。[初始采集源码至最终源码的补丁](collection-to-final.patch) 可重建该差异（零上下文补丁，使用 `--unidiff-zero`）；最终全部已取得原响应均用本次测试源码再次校验，成功数据的规范化/Decimal/单位未改写。

唯一 Draft，不 Ready、不合并；无真实云调用/额外付费、新前向观察、提案、Paper/Live 订单、成交或 NAV。本期保留原工作树和所有旧数据。
