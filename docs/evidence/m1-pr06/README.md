# M1-PR06 Sol 自测证据（脱敏）

此处仅记录来源类型、范围/缺失、必要 SHA、汇总结论和执行证据。raw/OHLC 行、完整 dataset/评估/账本/六报告及失败副本均仅存本机 ignore 目录。**Sol 自测不是 Terra 独立验收；后者 NOT VERIFIED。**

## 固定顺序与输入

base `de043bf1146b8256cf5218465c9a3004e3ec24fe`，分支 `codex/m1-pr06-evaluation`。

- 2026-10-29 13:15:56（Asia/Taipei）：协议先提交 `26d4fca`。
- 13:16:51.993：已授权 Tushare MCP 四接口采集批次实际完成；精确文本 payload 本地冻结，不是 HTTP wire response。参数：600000.SH/SSE，20240101–20261028；字段同原 adapter。
- 13:17:30：技术更正提交 `78e10f0`。静态检查发现原 reducer 必须在前一交易日提交订单，因此把独立基准从首日开盘改为首日收盘提交、次日开盘一次尝试。**此时尚未审计新源或运行新收益**，没有改动策略或引擎，也没有按表现择入场日。
- 之后先跑 audit/prepare 冻结 47/21 划分，再运行新 replay/evaluation。最后断点后一日与原规则有效期决定 20260717–20261028 区段；未因收益移动。

实际源 681 日线 / 681 开市日 / 1032 自然日日历 / 681 价格带，停复牌空；日历/日线/价格带缺失 0，未知日历 0。三个连续性断点：20240718、20250716、20260716。长区段原 prepare 实际报 `corporate-action/adjustment discontinuity`；更早规则/费用尚不支持。目标覆盖 **DATA_BLOCKED**，选中区段 COMPLETE / 68 日 / 缺失 0。

| 必要绑定对象 | SHA-256 |
| --- | --- |
| 最终协议 v1 | `0e2fb1253c879a3caf0154c186eb47080d3d8e6b96081bd0c8ae5986d07f3576` |
| 精确 daily MCP 文本 | `5689c59e8fa92b5ca2499141c3b4e199b168ea02f70b385c8a24eb81340d2075` |
| 精确 calendar MCP 文本 | `284cbb28d12f576ae93e54b0bd8abf516a595cc668f56363cd2cfbb68a4d5bf9` |
| 精确 limits MCP 文本 | `dabd396dc7594bf90c74118d92be256c87667bc0cfd46af08b7c9f1861ceec2f` |
| 精确 suspensions MCP 文本 | `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945` |
| 新 dataset（含本轮来源清单） | `ccf8eceb5e5844b32c4f6470c4dc29637c05612f779c1fcef79218ba3d5879a2` |
| 新策略账本 HEAD | `87a12d081d69acfb2379b8ed01376b497259d355a319ed7faccee76eaeadc556` |
| 最终 evaluation.json | `b870bfca427b50809fb4ac1e843a936ea1954053d9ef3037cdeebbe450a9aa17` |
| 最终 evaluation.csv | `c17d1effee018b2838e29b831c9afa63e7d3c145f55c0fbf7830a131112c17f6` |

本轮 dataset 与 PR12 原 hash 不同，因为来源清单/查询范围/实际提取时间不同；不是覆盖旧证据。两者共享的 68 日得到同样净结果不等于相同输入快照。

## Windows 实际执行

Windows x64 / Rust 1.98.1 / Python 3.12.10 / 现有 MSVC，无新依赖或付费 CI。

| 命令/流程 | 实际结果 |
| --- | --- |
| `cargo fmt --all -- --check` | exit 0 |
| `./scripts/with-msvc.ps1 check --workspace --locked --offline` | exit 0 |
| `./scripts/with-msvc.ps1 test --workspace --locked --offline` | exit 0，110 Rust 测试通过 |
| `./scripts/with-msvc.ps1 clippy --workspace --all-targets --locked --offline '--' -D warnings` | exit 0 |
| `./scripts/with-msvc.ps1 build -p stratide-cli --locked --offline` | exit 0 |
| `python scripts/test-historical-data.py` | exit 0，3 单测通过 |
| `python scripts/test-research-evaluation.py` | exit 0，5 单测通过 |
| audit + 新评价器实际子进程 + `paper-benchmark` + 两个原 replay ledgers | exit 0，完整探针和逐字节比较通过 |

完整实际自测命令（21 个原/冻结文件的只读字节核对包含原 PR12 raw、输入和六报告；无原库打开或写入）：

```powershell
python scripts/research-evaluate.py audit --source-dir state/issue13-source-02 --out state/issue13-audit-02
python scripts/test-research-evaluation.py --exe target/debug/stratide-cli.exe --audit-dir state/issue13-audit-02 --source-dir state/issue13-source-02 --out state/issue13-selftest-05 --preserve-dir F:/Desktop/Documents/Codex/Stratide/m1-pr05b-worktree/state/issue11-source-20261029-01 --preserve-dir F:/Desktop/Documents/Codex/Stratide/m1-pr05b-worktree/state/issue11-input-20261029-02 --preserve-dir F:/Desktop/Documents/Codex/Stratide/m1-pr05b-worktree/state/issue11-selftest-03/a/report
```

这些已存在的目录不能复用作输出；重跑时换新目录。`state/issue13-source-02` 为精确原工具文本；`state/issue13-audit-02` 为最终审计/输入/split；`state/issue13-selftest-05/{a,b}/evaluation` 为最终评价。各目录均已核实 Git ignore。

实际反证与结果：

- 双独立策略 ledger 的六报告逐字节一致，两个 evaluation.json/csv、三个窗口的 benchmark.json 也一致；评价前后策略原 DB 与六报告字节不变。
- T+1 open/high/low/close/volume 合成变异改变后日模型成交价格，T 日及以前提案完全相同。合成变异、截断副本均明确标注非新增市场/forward 证据。
- 真实 full / 47 日 development / 21 日 holdout 均从同一原始 ledger 投影；跨持仓边界另取切片保留 100 股与前日 NAV，改动冻结 split 被拒绝，没有新事件。单位测试另检查 pending carry。
- 独立基准 full 于 20260720 入场，holdout 于 20260923 入场；不跟随策略第一笔买入。首日停牌和无次日的独立故障副本均 NOT_EVALUATED，没有以后择日重试；pending 如实显示。
- 缺交易日日线和跨公司行为断点实际 prepare BLOCKED；篡改报告被原链校验后重导出比较拒绝。
- 逐日现金/持仓/费用/NAV/已实现与未实现 P&L 独立恒等式复算通过。缺边界/中间 NAV、负收益、无成交、低于1bps的损失、末日 pending 和 null 推断指标均有针对性检查。
- full 净损失 3349 分、费用1549分、末期100股、pending0；holdout 净增加899分、仅1笔买入、未完成买卖回合0。两个窗口相对独立买入持有净表现均负；研究证据 **INSUFFICIENT_EVIDENCE**。

## 保留的失败与局限

第一次新增 Decimal 格式测试得到科学计数法文本，失败1项；改成固定小数文本后 5 项通过。第一次 Clippy 调用未对 PowerShell `--` 正确引用，参数转发失败；按仓库文档加引号后严格检查通过。初次工具文本落盘由写入工具附加一个 LF，`source-01/audit-01/selftest-02` 全部保留；`source-02` 根据原工具返回长度恢复精确文本，旧副本不改，最终评价仅绑定 source-02。未删除失败证据或绕过测试。

已有110项Rust测试覆盖原风险/费用/持久锁、重启和旧报告路径；本 PR 未再增加共享财务故障矩阵。没有以测试通过声称真实 PIT/市场可成交、统计优势、整个 M1 或实盘资格。来源许可仍为 Owner 既有个人本地研究授权，不是供应商独立许可认证；未使用本机 HTTP Token 路径，未读取别的项目凭据。Linux/macOS、公司行为完整会计、真实 forward/券商成交、物理断电/磁盘满均未验证。Issue #10 保持 OPEN。
